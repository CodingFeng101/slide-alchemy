"""Install checked font assets and expand low-confidence matches remotely."""
import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

import cv2

from match_fonts import font_directories, index_fonts

CATALOG = Path(__file__).resolve().parents[1] / "references/font-catalog.json"


def default_cache():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "slide-alchemy/fonts/v1"


class FontStore:
    def __init__(self, server, cache=None, catalog_path=CATALOG):
        self.server = server.rstrip("/")
        if not self.server.startswith(("http://", "https://")):
            raise ValueError("font server must be an HTTP(S) URL")
        # Resolve MSIX/AppData redirection before atomic renames on Windows.
        self.cache = (Path(cache) if cache else default_cache()).expanduser().resolve()
        self.catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        self.assets = {asset["id"]: asset for asset in self.catalog["assets"]}

    def fetch(self, path, digest, size=None):
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("font asset must have a relative path")
        destination = self.cache / relative
        if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == digest:
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            request = urllib.request.Request(self.server + "/" + relative.as_posix())
            with urllib.request.urlopen(request, timeout=60) as response, tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                checksum = hashlib.sha256()
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > (size if size is not None else 1024 * 1024):
                        raise ValueError("font asset exceeds its expected size")
                    checksum.update(chunk)
                    stream.write(chunk)
            if checksum.hexdigest() != digest or (size is not None and total != size):
                raise ValueError("font asset checksum or size mismatch")
            temporary.replace(destination)
            return destination
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def install_asset(self, asset_id):
        asset = self.assets[asset_id]
        # Keep each font's redistribution license alongside the cached font.
        self.fetch(asset["license_path"], asset["license_sha256"])
        return self.fetch(asset["path"], asset["sha256"], asset["bytes"])

    def download(self, assets):
        for position, asset in enumerate(assets, 1):
            self.install_asset(asset["id"])
            print(f"Ready {position}/{len(assets)} {asset['family']} {asset['style']}", file=sys.stderr, flush=True)
        manifest = {"release": self.catalog["release"], "fonts": assets}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.cache, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
            temporary.replace(self.cache / "font-manifest.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {"directory": str(self.cache), "families": len({asset["family"] for asset in assets}),
                "styles": len(assets), "font_bytes": sum(asset["bytes"] for asset in assets)}

    def install_core(self, include_system=False):
        fonts = [self.install_asset(asset["id"]) for asset in self.assets.values()
                 if "core" in asset["profiles"]
                 or (include_system and (self.cache / asset["path"]).exists())]
        sources = [*fonts, *font_directories()] if include_system else fonts
        index = index_fonts(sources)
        path = self.cache / ("local-index.json" if include_system else "core-index.json")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.cache, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(index, stream, ensure_ascii=False)
        temporary.replace(path)
        model = self.catalog["model"]
        bundled = Path(__file__).resolve().parents[1] / "assets/font_encoder.onnx"
        if bundled.exists() and hashlib.sha256(bundled.read_bytes()).hexdigest() == model["sha256"]:
            model_path = bundled
        else:
            model_path = self.fetch(model["path"], model["sha256"], model["bytes"])
        return path, model_path

    def match(self, mask, text, top_k):
        ok, encoded = cv2.imencode(".png", mask.astype("uint8"))
        if not ok:
            raise ValueError("cannot encode font matching mask")
        payload = json.dumps({"text": text, "top_k": top_k,
                              "mask_png": base64.b64encode(encoded).decode("ascii")}).encode()
        request = urllib.request.Request(self.server + "/match", data=payload,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("font match response is too large")
        result = json.loads(data)
        if not isinstance(result.get("candidates"), list):
            raise ValueError("font match response is missing candidates")
        return result


class RemoteFontMatcher:
    def __init__(self, local, store):
        self.local = local
        self.store = store

    def rank_fonts(self, mask, text, top_k=10):
        return self.local.rank_fonts(mask, text, top_k)

    def match(self, mask, text, top_k=10):
        result = self.local.match(mask, text, top_k)
        candidates = result["candidates"]
        if candidates and candidates[0]["shape_error"] <= 0.12:
            return result
        try:
            remote = self.store.match(mask, text, top_k)
            remote_candidates = remote["candidates"]
            result["remote"] = {"status": "no_better_match", "candidates": remote_candidates}
            if not remote_candidates:
                return result
            best = remote_candidates[0]
            if candidates and best["shape_error"] >= candidates[0]["shape_error"]:
                return result
            best = dict(best)
            best["path"] = str(self.store.install_asset(best["asset_id"]))
            best["index"] = 0
            # Publish one usable remote candidate. Keep the server's full
            # shortlist in the diagnostic report without server-local paths.
            result.update(status="ranked", candidates=[best, *candidates][:top_k],
                          needs_review=remote.get("needs_review", True),
                          review_reasons=remote.get("review_reasons", []))
            result["margin"] = result["candidates"][1]["shape_error"] - best["shape_error"] if len(result["candidates"]) > 1 else None
            if result["margin"] is not None and result["margin"] < 0.005:
                result["needs_review"] = True
                result["review_reasons"] = list(dict.fromkeys([*result["review_reasons"], "ambiguous_candidates"]))
            result["remote"]["status"] = "used"
        except (OSError, ValueError, KeyError, TypeError) as error:
            result["remote"] = {"status": "unavailable", "error": str(error)}
            result["needs_review"] = True
            result["review_reasons"] = list(dict.fromkeys([*result.get("review_reasons", []), "remote_unavailable"]))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, help="Font release URL ending in /fonts/v1")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--include-system", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--download-pack", choices=["core", "server"], help="Download a font pack to --output-dir")
    selection.add_argument("--download-font", nargs="+", help="Download font family names or asset IDs to --output-dir")
    parser.add_argument("--output-dir", type=Path, help="Destination directory for downloaded fonts and licenses")
    args = parser.parse_args()
    download_only = bool(args.download_pack or args.download_font)
    if download_only != bool(args.output_dir):
        parser.error("download selections and --output-dir must be supplied together")
    if download_only and (args.cache or args.include_system):
        parser.error("download selections accept --server and --output-dir")
    store = FontStore(args.server, args.output_dir if download_only else args.cache)
    if download_only:
        if args.download_pack:
            assets = [asset for asset in store.assets.values() if args.download_pack in asset["profiles"]]
        else:
            requested = {name.casefold() for name in args.download_font}
            available = {value.casefold() for asset in store.assets.values() for value in [asset["id"], asset["family"]]}
            if requested - available:
                parser.error("Unknown font selection " + ", ".join(sorted(requested - available)))
            assets = [asset for asset in store.assets.values()
                      if asset["id"].casefold() in requested or asset["family"].casefold() in requested]
        print(json.dumps(store.download(assets), ensure_ascii=False))
        return
    index, model = store.install_core(args.include_system)
    print(json.dumps({"index": str(index), "model": str(model)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
