#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


VALID = {
    "simple_geometry_svg_ooxml": "svg_to_ooxml",
    "icon_png": "generate_png_asset",
    "complex_png_whole": "generate_png_whole",
}


def err(errors, msg):
    errors.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("element_analysis_json")
    args = ap.parse_args()

    data = json.loads(Path(args.element_analysis_json).read_text(encoding="utf-8-sig"))
    errors = []

    for key in ("ref_width", "ref_height", "components", "slides"):
        if key not in data:
            err(errors, f"missing top-level key: {key}")

    components = data.get("components", {})
    if not isinstance(components, dict):
        err(errors, "components must be an object")
        components = {}

    for cid, comp in components.items():
        cat = comp.get("category")
        plan = comp.get("asset_plan")
        if cat not in VALID:
            err(errors, f"component {cid}: invalid category {cat}")
        elif plan != VALID[cat]:
            err(errors, f"component {cid}: category {cat} expects asset_plan {VALID[cat]}, got {plan}")

    for slide in data.get("slides", []):
        sid = slide.get("slide", "?")
        for inst in slide.get("instances", []):
            iid = inst.get("id", "?")
            comp = inst.get("component")
            if comp not in components:
                err(errors, f"slide {sid} instance {iid}: unknown component {comp}")
            for field in ("bbox_px", "bbox_frac"):
                box = inst.get(field)
                if not isinstance(box, list) or len(box) != 4:
                    err(errors, f"slide {sid} instance {iid}: {field} must be [x,y,w,h]")
                    continue
                if box[2] <= 0 or box[3] <= 0:
                    err(errors, f"slide {sid} instance {iid}: {field} width/height must be positive")

    if errors:
        for e in errors:
            print(f"ERROR\t{e}")
        raise SystemExit(1)

    print("element_analysis is valid")


if __name__ == "__main__":
    main()
