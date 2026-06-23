#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from PIL import Image


SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def safe_output_path(output_dir, item_id):
    item_id = str(item_id)
    if not SAFE_ID.fullmatch(item_id):
        raise ValueError(f"unsafe crop id: {item_id!r}")

    output_dir = output_dir.resolve()
    path = (output_dir / f"{item_id}.png").resolve()
    if output_dir != path.parent and output_dir not in path.parents:
        raise ValueError(f"output path escapes output_dir: {item_id!r}")
    return path


def key_to_alpha(img, key=(0, 255, 0), tolerance=70):
    img = img.convert("RGBA")
    pix = img.load()
    kr, kg, kb = key
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pix[x, y]
            if abs(r - kr) <= tolerance and abs(g - kg) <= tolerance and abs(b - kb) <= tolerance:
                pix[x, y] = (r, g, b, 0)
    return img


def parse_hex_color(value):
    value = value.strip().lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet_png")
    ap.add_argument("crops_json", help="JSON list of {id, bbox:[x,y,w,h]}")
    ap.add_argument("output_dir")
    ap.add_argument("--key-color", default="#00ff00")
    ap.add_argument("--tolerance", type=int, default=70)
    ap.add_argument("--pad", type=int, default=16)
    ap.add_argument("--trim", action="store_true", help="Trim alpha bbox but keep --pad. Off by default.")
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sheet = key_to_alpha(Image.open(args.sheet_png), parse_hex_color(args.key_color), args.tolerance)
    crops = json.loads(Path(args.crops_json).read_text(encoding="utf-8-sig"))

    for item in crops:
        x, y, w, h = item["bbox"]
        l = max(0, x - args.pad)
        t = max(0, y - args.pad)
        r = min(sheet.width, x + w + args.pad)
        b = min(sheet.height, y + h + args.pad)
        crop = sheet.crop((l, t, r, b))
        if args.trim:
            bbox = crop.getbbox()
            if bbox:
                tl = max(0, bbox[0] - args.pad)
                tt = max(0, bbox[1] - args.pad)
                tr = min(crop.width, bbox[2] + args.pad)
                tb = min(crop.height, bbox[3] + args.pad)
                crop = crop.crop((tl, tt, tr, tb))
        crop.save(safe_output_path(out, item["id"]))


if __name__ == "__main__":
    main()
