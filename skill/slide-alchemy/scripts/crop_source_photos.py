#!/usr/bin/env python3
"""Crop real photographs out of the source pages.

A photograph records real people, places and documents. Regenerating it with
an image model changes faces and wipes banner text, so `photo_source_crop`
components are the one asset kind taken straight from the source pixels.
"""
import argparse
import json
from pathlib import Path

from PIL import Image

CATEGORY = "photo_source_crop"


def source_page(source_dir, slide):
    matches = sorted(p for p in Path(source_dir).glob(f"slide_{slide:03d}.*")
                     if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    if not matches:
        raise ValueError(f"no source image for slide {slide} in {source_dir}")
    return matches[0]


def crop_photos(analysis_path, source_dir, out_dir):
    data = json.loads(Path(analysis_path).read_text(encoding="utf-8-sig"))
    components = data.get("components", {})
    out_dir = Path(out_dir)
    written = []
    for slide in data.get("slides", []):
        photos = [inst for inst in slide.get("instances", [])
                  if components.get(inst.get("component"), {}).get("category") == CATEGORY]
        if not photos:
            continue
        with Image.open(source_page(source_dir, slide["slide"])) as page:
            page = page.convert("RGB")
            # Boxes are measured on the reference page, which a re-rendered
            # source image may not match pixel for pixel.
            scale_x = page.width / data["ref_width"]
            scale_y = page.height / data["ref_height"]
            for inst in photos:
                x, y, w, h = inst["bbox_px"]
                box = (max(0, round(x * scale_x)), max(0, round(y * scale_y)),
                       min(page.width, round((x + w) * scale_x)), min(page.height, round((y + h) * scale_y)))
                if box[2] <= box[0] or box[3] <= box[1]:
                    raise ValueError(f"slide {slide['slide']} photo {inst['id']}: bbox falls outside the page")
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"{inst['id']}.png"
                page.crop(box).save(path)
                written.append(path)
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("element_analysis_json")
    ap.add_argument("--source-dir", required=True, help="Directory holding slide_001.png, slide_002.png, ...")
    ap.add_argument("--out-dir", required=True, help="Destination, e.g. run/assets/png/photos")
    args = ap.parse_args()
    try:
        written = crop_photos(args.element_analysis_json, args.source_dir, args.out_dir)
    except ValueError as error:
        ap.exit(2, f"Photo cropping failed. {error}\n")
    for path in written:
        print(path)
    print(f"{len(written)} photo(s) cropped")


if __name__ == "__main__":
    main()
