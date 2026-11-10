#!/usr/bin/env python3
"""Index local fonts and match text crops using an ONNX encoder and OpenCV."""
import argparse
import hashlib
import json
import os
import unicodedata
import warnings
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

INPUT_HEIGHT = 48
INPUT_WIDTH = 256
DEFAULT_FONT_SERVER = "http://182.254.211.241/fonts/v1"


def validate_font_matches(item):
    """Require usable matching evidence for extracted text before composition."""
    if not item.get("text", "").strip():
        return
    label = item.get("id", item["text"][:30])
    reports = item.get("font_matches", [])
    if not reports or any(not report.get("candidates") for report in reports):
        raise ValueError(f"{label} requires font matching results before composition")
    styles = [run for run in item.get("runs", []) if run["text"].strip()]
    if styles and len(styles) != len(reports):
        raise ValueError(f"{label} requires a font match for every text run")
    if not styles:
        styles = [item] * len(reports)
    for style, report in zip(styles, reports):
        selected = report.get("selected_candidate", report["candidates"][0])
        if selected not in report["candidates"]:
            raise ValueError(f"{label} selected font must appear in the matching candidates")
        face = style.get("font_face") or style.get("font_family")
        if face != selected.get("face_name", selected["family"]):
            raise ValueError(f"{label} font face differs from its matching result")
        for key in ("bold", "italic"):
            if bool(style.get(key, False)) != bool(selected.get(key, False)):
                raise ValueError(f"{label} {key} differs from its matching result")


def font_directories():
    if os.name == "nt":
        return [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
                Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Microsoft/Windows/Fonts"]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
            Path.home() / ".local/share/fonts", Path("/Library/Fonts"),
            Path("/System/Library/Fonts"), Path.home() / "Library/Fonts"]


def index_fonts(directories):
    from fontTools.ttLib import TTCollection, TTFont, TTLibError

    paths = set()
    for directory in directories:
        source = Path(directory)
        candidates = [source] if source.is_file() else source.rglob("*")
        paths.update(p.resolve() for p in candidates
                     if p.suffix.lower() in (".ttf", ".otf", ".ttc", ".otc"))
    fonts, errors, seen = [], [], set()
    for path in sorted(paths):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            count = 1
            if path.suffix.lower() in (".ttc", ".otc"):
                with path.open("rb") as stream, TTCollection(stream, lazy=True) as collection:
                    count = len(collection.fonts)
            for face in range(count):
                with path.open("rb") as stream, TTFont(stream, fontNumber=face, lazy=True) as font:
                    name = font["name"]
                    # Office selects the legacy family plus bold/italic. The
                    # typographic family can group distinct faces such as Arial
                    # Narrow and Arial Black under Arial, losing the actual face.
                    family = name.getDebugName(1) or name.getDebugName(16)
                    style = name.getDebugName(2) or name.getDebugName(17) or "Regular"
                    if not family or (family, style) in seen:
                        continue
                    # Store the default face of variable fonts. Named instances
                    # need their own static font files to become candidates.
                    cmap = font.getBestCmap() or {}
                    if not cmap:
                        continue
                    weight = font["OS/2"].usWeightClass if "OS/2" in font else 400
                    permissions = font["OS/2"].fsType if "OS/2" in font else None
                    italic = bool(font["head"].macStyle & 2)
                    fonts.append({"path": str(path), "index": face, "family": family,
                                  "style": style, "weight": weight, "italic": italic,
                                  "face_name": name.getDebugName(4) or family,
                                  "bold": bool(font["head"].macStyle & 1),
                                  "sha256": digest, "fs_type": permissions,
                                  "characters": "".join(chr(c) for c in sorted(cmap)
                                                        if c <= 0x10ffff)})
                    seen.add((family, style))
        except (OSError, TTLibError) as error:
            errors.append({"path": str(path), "error": str(error)})
    return {"version": 1, "fonts": fonts, "errors": errors}


def load_index(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1 or not data.get("fonts"):
        raise ValueError("font index must contain version 1 and at least one font")
    base = Path(path).resolve().parent
    hashes = {}
    for font in data["fonts"]:
        font["path"] = str((base / font["path"]).resolve())
        if font["path"] not in hashes:
            hashes[font["path"]] = hashlib.sha256(Path(font["path"]).read_bytes()).hexdigest()
        if hashes[font["path"]] != font["sha256"]:
            raise ValueError(f'font file changed; rebuild the index: {font["path"]}')
        if "face_name" not in font or "bold" not in font:
            from fontTools.ttLib import TTFont
            with Path(font["path"]).open("rb") as stream, TTFont(stream, fontNumber=font["index"], lazy=True) as face:
                font["face_name"] = face["name"].getDebugName(4) or font["family"]
                font["bold"] = bool(face["head"].macStyle & 1)
    return data["fonts"]


def supports(font, text):
    return set(text) - set(" \t\r\n") <= set(font["characters"])


@lru_cache(maxsize=256)
def load_face(path, index, size):
    return ImageFont.truetype(path, size, index=index)


def trim(mask):
    rows, cols = np.nonzero(mask > 0)
    if not len(rows):
        raise ValueError("text crop has no visible ink")
    return mask[rows.min():rows.max() + 1, cols.min():cols.max() + 1]


def render_text(font, text, size):
    face = load_face(font["path"], font["index"], max(1, int(round(size))))
    stroke = max(1, int(round(size / 32))) if font.get("synthetic_bold") else 0
    left, top, right, bottom = face.getbbox(text, stroke_width=stroke)
    canvas = Image.new("L", (max(1, right - left + 4), max(1, bottom - top + 4)))
    ImageDraw.Draw(canvas).text((2 - left, 2 - top), text, font=face, fill=255, stroke_width=stroke)
    return trim(np.asarray(canvas))


def model_input(mask):
    mask = trim(mask).astype(np.float32)
    scale = min((INPUT_HEIGHT - 8) / mask.shape[0], (INPUT_WIDTH - 8) / mask.shape[1])
    width = max(1, int(round(mask.shape[1] * scale)))
    height = max(1, int(round(mask.shape[0] * scale)))
    resized = cv2.resize(mask, (width, height), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((INPUT_HEIGHT, INPUT_WIDTH), np.float32)
    y = (INPUT_HEIGHT - height) // 2
    x = (INPUT_WIDTH - width) // 2
    canvas[y:y + height, x:x + width] = resized / 255.0
    return canvas[None]


def crop_mask(image, bbox):
    # Reuse extraction's colour-aware mask, including its background ring.
    from extract_text import OcrBox, ink_mask, ring_background

    x, y, w, h = (int(round(v)) for v in bbox)
    page_h, page_w = image.shape[:2]
    left, top = max(0, x), max(0, y)
    right, bottom = min(page_w, x + w), min(page_h, y + h)
    if right <= left or bottom <= top:
        raise ValueError("text crop falls outside the image")
    box = OcrBox(text="", conf=1.0, x=left, y=top, w=right - left, h=bottom - top)
    crop = image[top:bottom, left:right]
    background = ring_background(image, box)
    mask, text_colour = ink_mask(crop, background)
    if mask.any() and float(np.ptp(text_colour)) > 50:
        # Grow the reliable text-colour seeds into their lighter gradient edges.
        # Keeping only connected regions that touch those seeds rejects unrelated
        # marks while recovering strokes lost by the strict extraction mask.
        distance = np.abs(crop.astype(np.float32) - background).sum(axis=2)
        threshold = max(25.0, float(np.percentile(distance[mask > 0], 20)) * 0.2)
        _, labels = cv2.connectedComponents((distance >= threshold).astype(np.uint8))
        keep = np.unique(labels[mask > 0])
        expanded = np.isin(labels, keep[keep != 0]).astype(np.uint8)
        core = cv2.erode(expanded, np.ones((3, 3), np.uint8))
        values = crop[core > 0] if core.any() else crop[mask > 0]
        colour_range = np.percentile(values, 90, axis=0) - np.percentile(values, 10, axis=0)
        if float(colour_range.max()) > 45:
            mask = expanded
    return trim(mask * 255)


def shape_error(source, candidate):
    """Symmetric stroke distance and dimensions, with translation tolerance."""
    source = (source >= 96).astype(np.uint8)
    candidate = (candidate >= 96).astype(np.uint8)
    if not source.any() or not candidate.any():
        return float("inf")
    source = trim(source)
    candidate = trim(candidate)
    h = max(source.shape[0], candidate.shape[0]) + 8
    w = max(source.shape[1], candidate.shape[1]) + 8
    a = np.zeros((h, w), np.uint8)
    b = np.zeros_like(a)
    a[4:4 + source.shape[0], 4:4 + source.shape[1]] = source
    b[4:4 + candidate.shape[0], 4:4 + candidate.shape[1]] = candidate
    distance_a = cv2.distanceTransform(1 - a, cv2.DIST_L2, 3)
    distance_b = cv2.distanceTransform(1 - b, cv2.DIST_L2, 3)
    best = float("inf")
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            shifted = np.roll(b, (dy, dx), axis=(0, 1))
            distance = (distance_a[shifted > 0].mean()
                        + np.roll(distance_b, (dy, dx), axis=(0, 1))[a > 0].mean()) / 2
            overlap_error = np.abs(a.astype(np.float32) - shifted).sum() / (a.sum() + b.sum())
            best = min(best, float(distance) / max(1, source.shape[0]) + 0.25 * overlap_error)
    dimensions = (abs(source.shape[1] - candidate.shape[1]) / source.shape[1]
                  + abs(source.shape[0] - candidate.shape[0]) / source.shape[0])
    return best + 0.25 * dimensions


def glyph_masks(mask, text):
    """Split full-width CJK lines at nearby ink valleys, tolerating tracking."""
    if len(text) < 2 or any(unicodedata.east_asian_width(c) not in ("W", "F") for c in text):
        return []
    width = mask.shape[1]
    cell = width / len(text)
    if cell < 3:
        return []
    columns = (mask >= 96).sum(axis=0) / mask.shape[0]
    cuts = [0]
    for index in range(1, len(text)):
        center = index * cell
        left = max(cuts[-1] + 1, int(round(center - cell * 0.22)))
        right = min(width - (len(text) - index), int(round(center + cell * 0.22)))
        positions = np.arange(left, right + 1)
        costs = columns[positions] + 0.05 * np.abs(positions - center) / cell
        cuts.append(int(positions[np.argmin(costs)]))
    cuts.append(width)
    pieces = [mask[:, left:right] for left, right in zip(cuts, cuts[1:])]
    if any(not (piece >= 96).any() for piece in pieces):
        return []
    return [trim(piece) for piece in pieces]


def text_shape_error(source, candidate, source_glyphs, text):
    line_error = shape_error(source, candidate)
    candidate_glyphs = glyph_masks(candidate, text) if source_glyphs else []
    if not candidate_glyphs:
        return line_error
    glyph_error = np.mean([shape_error(a, b) for a, b in zip(source_glyphs, candidate_glyphs)])
    return float(0.9 * glyph_error + 0.1 * line_error)


class FontMatcher:
    def __init__(self, index_path, model_path):
        import onnxruntime as ort

        self.fonts = load_index(index_path)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        self.session = ort.InferenceSession(str(model_path), sess_options=options,
                                            providers=["CPUExecutionProvider"])
        metadata = self.session.get_modelmeta().custom_metadata_map
        if metadata.get("slide_alchemy_font_encoder") != "1":
            raise ValueError("expected a trained Slide Alchemy font encoder")
        self.trained_faces = set(json.loads(metadata["trained_faces"]))

    def encode(self, masks):
        batches = []
        for start in range(0, len(masks), 32):
            batch = np.stack([model_input(m) for m in masks[start:start + 32]])
            batches.append(self.session.run(["embedding"], {"ink": batch})[0])
        return np.concatenate(batches)

    def rank_fonts(self, mask, text, top_k=10):
        text = text.strip()
        if not text or "\n" in text or top_k < 1:
            raise ValueError("matching needs a nonempty single line and top_k >= 1")
        mask = trim(mask)
        eligible = [f for f in self.fonts if supports(f, text)]
        if not eligible:
            return [], 0
        # Normalize every candidate to the source ink height using uniform scale.
        rendered = []
        sizes = []
        renderable = []
        for font in eligible:
            try:
                probe = render_text(font, text, 48)
                size = 48 * mask.shape[0] / probe.shape[0]
                reference = render_text(font, text, size)
            except OSError as error:
                warnings.warn(f"Skipping unrenderable font {font['family']}. {error}", RuntimeWarning)
                continue
            rendered.append(reference)
            sizes.append(size)
            renderable.append(font)
        if not rendered:
            return [], len(eligible)
        features = self.encode([mask, *rendered])
        similarities = features[1:] @ features[0]
        shortlist = np.argsort(-similarities, kind="stable")[:top_k]
        return [(renderable[position], sizes[position], float(similarities[position]))
                for position in shortlist], len(eligible)

    def match(self, mask, text, top_k=10):
        ranking, eligible_count = self.rank_fonts(mask, text, top_k)
        if not ranking:
            return {"status": "no_supported_font", "candidates": []}
        mask = trim(mask)
        candidates = []
        # At small body sizes, glyph valleys become unreliable. Keep whole-line
        # comparison there and use glyph detail when enough pixels are present.
        source_glyphs = glyph_masks(mask, text) if mask.shape[0] >= 40 else []
        bold_families = {f["family"] for f in self.fonts if f.get("bold", f["weight"] >= 700)}
        for font, size_estimate, similarity in ranking:
            variants = [font]
            if font["weight"] < 600 and font["family"] not in bold_families:
                variants.append(dict(font, synthetic_bold=True))
            best_error, best_size = float("inf"), None
            best_font = font
            center = max(1, int(round(size_estimate)))
            radius = max(2, int(round(center * 0.08)))
            for variant in variants:
                for size in range(max(1, center - radius), center + radius + 1):
                    error = text_shape_error(mask, render_text(variant, text, size), source_glyphs, text)
                    if error < best_error:
                        best_error, best_size, best_font = error, size, variant
                # Compare uniformly resized references for screenshot resampling.
                for reference_size in (48, 96):
                    reference = render_text(variant, text, reference_size)
                    for height in range(max(1, mask.shape[0] - 1), mask.shape[0] + 2):
                        scale = height / reference.shape[0]
                        width = max(1, int(round(reference.shape[1] * scale)))
                        resized = cv2.resize(reference, (width, height), interpolation=cv2.INTER_AREA)
                        error = text_shape_error(mask, resized, source_glyphs, text)
                        if error < best_error:
                            best_error, best_size, best_font = error, round(reference_size * scale, 2), variant
            candidates.append({"family": font["family"], "style": font["style"],
                               "face_name": font.get("face_name", font["family"]),
                               "path": font["path"], "index": font["index"],
                               "bold": font.get("bold", font["weight"] >= 700) or bool(best_font.get("synthetic_bold")),
                               "synthetic_bold": bool(best_font.get("synthetic_bold")), "italic": font["italic"],
                               "model_similarity": round(similarity, 6),
                               "shape_error": round(best_error, 6), "size_px": best_size,
                               "seen_in_training": f'{font["sha256"]}:{font["index"]}'
                               in self.trained_faces})
        candidates.sort(key=lambda c: c["shape_error"])
        margin = (candidates[1]["shape_error"] - candidates[0]["shape_error"]
                  if len(candidates) > 1 else None)
        review_reasons = []
        if margin is not None and margin < 0.005:
            review_reasons.append("ambiguous_candidates")
        if candidates[0]["shape_error"] > 0.12:
            review_reasons.append("poor_shape_match")
        if not candidates[0]["seen_in_training"]:
            review_reasons.append("face_absent_from_training")
        # Deliberately report a ranking, not an uncalibrated probability.
        return {"status": "ranked", "eligible_fonts": eligible_count,
                "margin": margin, "needs_review": bool(review_reasons),
                "review_reasons": review_reasons, "candidates": candidates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index")
    index.add_argument("directories", nargs="*", type=Path)
    index.add_argument("--text", help="Keep only fonts covering this text (excludes symbol fonts)")
    index.add_argument("--out", required=True, type=Path)
    match = commands.add_parser("match")
    match.add_argument("image", type=Path)
    match.add_argument("--text", required=True)
    match.add_argument("--font-index", required=True, type=Path)
    match.add_argument("--font-model", required=True, type=Path)
    match.add_argument("--top-k", type=int, default=10)
    match.add_argument("--font-server", help="Expand poor matches using a font release URL ending in /fonts/v1")
    match.add_argument("--font-cache", type=Path)
    match.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "index":
        result = index_fonts(args.directories or font_directories())
        if args.text:
            result["fonts"] = [f for f in result["fonts"] if supports(f, args.text)]
        print(f'Indexed {len(result["fonts"])} font faces; {len(result["errors"])} unreadable files')
    else:
        from extract_text import read_image
        image = read_image(args.image)
        mask = crop_mask(image, (0, 0, image.shape[1], image.shape[0]))
        matcher = FontMatcher(args.font_index, args.font_model)
        if args.font_server:
            from font_store import FontStore, RemoteFontMatcher
            matcher = RemoteFontMatcher(matcher, FontStore(args.font_server, args.font_cache))
        result = matcher.match(mask, args.text, args.top_k)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
