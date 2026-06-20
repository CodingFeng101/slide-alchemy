#!/usr/bin/env python3
import argparse
from pathlib import Path
from PIL import Image, ImageDraw


def checker(size):
    img = Image.new("RGB", size, (245, 245, 245))
    draw = ImageDraw.Draw(img)
    for y in range(0, size[1], 20):
        for x in range(0, size[0], 20):
            if (x // 20 + y // 20) % 2 == 0:
                draw.rectangle([x, y, x + 19, y + 19], fill=(220, 220, 220))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir")
    ap.add_argument("output_png")
    ap.add_argument("--thumb-w", type=int, default=220)
    ap.add_argument("--thumb-h", type=int, default=160)
    ap.add_argument("--cols", type=int, default=3)
    args = ap.parse_args()

    files = sorted(Path(args.input_dir).glob("*.png"))
    if not files:
        raise SystemExit(f"ERROR: no PNG files found in {args.input_dir}")
    if args.cols <= 0:
        raise SystemExit("ERROR: --cols must be positive")
    cell_w = args.thumb_w + 80
    cell_h = args.thumb_h + 60
    rows = max(1, (len(files) + args.cols - 1) // args.cols)
    sheet = Image.new("RGB", (cell_w * args.cols, cell_h * rows), (235, 235, 235))
    draw = ImageDraw.Draw(sheet)

    for i, file in enumerate(files):
        im = Image.open(file).convert("RGBA")
        im.thumbnail((args.thumb_w, args.thumb_h), Image.LANCZOS)
        col = i % args.cols
        row = i // args.cols
        x = col * cell_w + 30
        y = row * cell_h + 20
        bg = checker((args.thumb_w + 20, args.thumb_h + 10))
        sheet.paste(bg, (x - 10, y - 10))
        sheet.paste(im, (x + (args.thumb_w - im.width) // 2, y + (args.thumb_h - im.height) // 2), im)
        draw.text((x - 10, y + args.thumb_h + 8), file.name, fill=(20, 20, 20))

    output = Path(args.output_png)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    print(args.output_png)


if __name__ == "__main__":
    main()
