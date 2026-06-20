#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from PIL import Image


SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


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
    if len(value) != 6:
        raise ValueError(f"key color must be a 6-digit hex color, got {value!r}")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def safe_asset_name(asset_id):
    asset_id = str(asset_id)
    if not SAFE_ID.fullmatch(asset_id):
        raise ValueError(f"invalid asset id for filename: {asset_id!r}")
    return f"{asset_id}.png"


def validated_bbox(item, sheet_size):
    box = item.get("bbox")
    asset_id = item.get("id", "?")
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError(f"invalid bbox for {asset_id!r}: {box!r}")
    x, y, w, h = box
    if w <= 0 or h <= 0:
        raise ValueError(f"bbox width/height must be positive for {asset_id!r}: {box!r}")
    sheet_w, sheet_h = sheet_size
    return x, y, w, h, sheet_w, sheet_h


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
    if not isinstance(crops, list):
        raise ValueError("crops JSON must be a list of crop objects")

    for item in crops:
        if not isinstance(item, dict):
            raise ValueError(f"crop item must be an object, got {item!r}")
        output_name = safe_asset_name(item.get("id"))
        x, y, w, h, sheet_w, sheet_h = validated_bbox(item, (sheet.width, sheet.height))
        l = max(0, x - args.pad)
        t = max(0, y - args.pad)
        r = min(sheet_w, x + w + args.pad)
        b = min(sheet_h, y + h + args.pad)
        if l >= r or t >= b:
            raise ValueError(
                f"crop bbox outside sheet for {item.get('id')!r}: "
                f"bbox={item.get('bbox')!r}, sheet_size={[sheet_w, sheet_h]}"
            )
        crop = sheet.crop((l, t, r, b))
        if args.trim:
            bbox = crop.getbbox()
            if bbox:
                tl = max(0, bbox[0] - args.pad)
                tt = max(0, bbox[1] - args.pad)
                tr = min(crop.width, bbox[2] + args.pad)
                tb = min(crop.height, bbox[3] + args.pad)
                crop = crop.crop((tl, tt, tr, tb))
        if crop.getbbox() is None:
            raise ValueError(f"empty transparent crop for {item.get('id')!r}: bbox={item.get('bbox')!r}")
        crop.save(out / output_name)


if __name__ == "__main__":
    main()
