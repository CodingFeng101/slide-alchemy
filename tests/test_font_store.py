import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "skill/slide-alchemy/scripts"
sys.path.insert(0, str(SCRIPTS))
from font_store import FontStore, RemoteFontMatcher, main


class FontStoreTests(unittest.TestCase):
    def store(self, root, source):
        path = root / "catalog.json"
        path.write_text(json.dumps({"assets": []}), encoding="utf-8")
        store = FontStore("http://localhost/fonts/v1", root / "cache", path)
        store.server = source.as_uri()
        return store

    def test_checked_download_reuses_cache_and_repairs_corrupt_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "font.ttf").write_bytes(b"font data")
            digest = hashlib.sha256(b"font data").hexdigest()
            store = self.store(root, source)
            cached = store.fetch("font.ttf", digest, 9)
            self.assertEqual(b"font data", cached.read_bytes())
            (source / "font.ttf").unlink()
            self.assertEqual(cached, store.fetch("font.ttf", digest, 9))
            (source / "font.ttf").write_bytes(b"font data")
            cached.write_bytes(b"bad")
            self.assertEqual(b"font data", store.fetch("font.ttf", digest, 9).read_bytes())

    def test_wrong_checksum_does_not_replace_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "font.ttf").write_bytes(b"incorrect")
            store = self.store(root, source)
            store.cache.mkdir()
            cached = store.cache / "font.ttf"
            cached.write_bytes(b"existing")
            with self.assertRaisesRegex(ValueError, "checksum"):
                store.fetch("font.ttf", "0" * 64, 9)
            self.assertEqual(b"existing", cached.read_bytes())
            self.assertEqual([cached], list(store.cache.iterdir()))

    def test_paths_cannot_escape_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.store(root, root)
            with self.assertRaisesRegex(ValueError, "relative path"):
                store.fetch("../escape.ttf", "0" * 64)

    def test_next_local_index_includes_previously_cached_remote_face(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.store(root, root)
            store.cache.mkdir()
            cached = store.cache / "remote.ttf"
            cached.write_bytes(b"font")
            store.assets = {"core": {"id": "core", "path": "core.ttf", "profiles": ["core"]},
                            "remote": {"id": "remote", "path": "remote.ttf", "profiles": ["server"]}}
            store.catalog["model"] = {"path": "model.onnx", "sha256": "0" * 64, "bytes": 1}
            store.install_asset = Mock(side_effect=lambda name: store.cache / (name + ".ttf"))
            store.fetch = Mock(return_value=store.cache / "model.onnx")
            with patch("font_store.index_fonts", return_value={"version": 1, "fonts": []}) as index:
                store.install_core(include_system=True)
            self.assertIn(cached, index.call_args.args[0])
            self.assertEqual(2, store.install_asset.call_count)

    def candidate(self, error, **values):
        return {"family": "Sample", "shape_error": error, "path": "local.ttf", **values}

    def test_good_local_match_does_not_query_server(self):
        local, store = Mock(), Mock()
        expected = {"candidates": [self.candidate(0.05)]}
        local.match.return_value = expected
        self.assertIs(expected, RemoteFontMatcher(local, store).match(np.ones((2, 2)), "test"))
        store.match.assert_not_called()

    def test_better_remote_match_downloads_selected_face_only(self):
        local, store = Mock(), Mock()
        local.match.return_value = {"candidates": [self.candidate(0.2)]}
        store.match.return_value = {"candidates": [self.candidate(0.03, asset_id="one"), self.candidate(0.05, asset_id="two")], "needs_review": False}
        store.install_asset.return_value = Path("cache/one.ttf")
        result = RemoteFontMatcher(local, store).match(np.ones((2, 2)), "test")
        self.assertEqual("used", result["remote"]["status"])
        self.assertEqual("cache/one.ttf", result["candidates"][0]["path"].replace("\\", "/"))
        store.install_asset.assert_called_once_with("one")

    def test_failed_server_preserves_local_candidate_and_marks_review(self):
        local, store = Mock(), Mock()
        original = self.candidate(0.2)
        local.match.return_value = {"candidates": [original]}
        store.match.side_effect = OSError("offline")
        result = RemoteFontMatcher(local, store).match(np.ones((2, 2)), "test")
        self.assertEqual([original], result["candidates"])
        self.assertTrue(result["needs_review"])
        self.assertIn("remote_unavailable", result["review_reasons"])

    def test_worse_remote_match_keeps_local_face_without_download(self):
        local, store = Mock(), Mock()
        local.match.return_value = {"candidates": [self.candidate(0.2)]}
        store.match.return_value = {"candidates": [self.candidate(0.3, asset_id="one")]}
        result = RemoteFontMatcher(local, store).match(np.ones((2, 2)), "test")
        self.assertEqual("no_better_match", result["remote"]["status"])
        self.assertEqual(0.2, result["candidates"][0]["shape_error"])
        store.install_asset.assert_not_called()

    def test_explicit_download_writes_fonts_licenses_and_selection_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "fonts").mkdir(parents=True)
            (source / "licenses").mkdir()
            (source / "fonts/sample.ttf").write_bytes(b"font")
            (source / "licenses/sample.txt").write_bytes(b"license")
            store = self.store(root, source)
            store.catalog["release"] = "test"
            asset = {"id": "sample", "family": "Sample", "style": "Regular", "path": "fonts/sample.ttf", "bytes": 4,
                     "sha256": hashlib.sha256(b"font").hexdigest(), "license_path": "licenses/sample.txt",
                     "license_sha256": hashlib.sha256(b"license").hexdigest()}
            store.assets = {"sample": asset}
            with patch("font_store.sys.stderr"):
                result = store.download([asset])
            self.assertEqual(1, result["families"])
            self.assertEqual(b"font", (store.cache / asset["path"]).read_bytes())
            self.assertEqual(b"license", (store.cache / asset["license_path"]).read_bytes())
            manifest = json.loads((store.cache / "font-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([asset], manifest["fonts"])

    def test_download_command_selects_family_and_individual_face(self):
        assets = [{"id": "sample-regular", "family": "Sample", "profiles": ["server", "core"]},
                  {"id": "sample-bold", "family": "Sample", "profiles": ["server"]},
                  {"id": "other-regular", "family": "Other", "profiles": ["server"]}]
        for flags, expected in [(["--download-font", "sample"], assets[:2]),
                                (["--download-font", "sample-bold"], assets[1:2]),
                                (["--download-pack", "core"], assets[:1]),
                                (["--download-pack", "server"], assets)]:
            with self.subTest(flags=flags), patch("font_store.FontStore") as factory, patch("builtins.print"):
                store = factory.return_value
                store.assets = {asset["id"]: asset for asset in assets}
                store.download.return_value = {}
                with patch.object(sys, "argv", ["font_store.py", "--server", "http://localhost", *flags, "--output-dir", "downloads"]):
                    main()
                store.download.assert_called_once_with(expected)
                store.install_core.assert_not_called()

    def test_download_command_requires_explicit_destination(self):
        with patch.object(sys, "argv", ["font_store.py", "--server", "http://localhost", "--download-pack", "server"]), patch("sys.stderr"):
            with self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(2, error.exception.code)

    def test_legacy_install_command_keeps_its_original_behavior(self):
        with patch("font_store.FontStore") as factory, patch("builtins.print"):
            store = factory.return_value
            store.install_core.return_value = (Path("index.json"), Path("model.onnx"))
            with patch.object(sys, "argv", ["font_store.py", "--server", "http://localhost", "--include-system"]):
                main()
            store.install_core.assert_called_once_with(True)
            store.download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
