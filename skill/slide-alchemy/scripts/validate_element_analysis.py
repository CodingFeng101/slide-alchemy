#!/usr/bin/env python3
import argparse
import json
from numbers import Real
from pathlib import Path


VALID = {
    "simple_geometry_svg_ooxml": "svg_to_ooxml",
    "icon_png": "generate_png_asset",
    "complex_png_whole": "generate_png_whole",
}


def err(errors, msg):
    errors.append(msg)


def is_number(value):
    return isinstance(value, Real) and not isinstance(value, bool)


def is_positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def validate_required(errors, context, obj, keys):
    for key in keys:
        if key not in obj:
            err(errors, f"{context}: missing required key: {key}")


def validate_string(errors, context, field, value):
    if not isinstance(value, str):
        err(errors, f"{context}: {field} must be a string")


def validate_positive_int_field(errors, context, field, value):
    if not is_positive_int(value):
        err(errors, f"{context}: {field} must be an integer >= 1")


def validate_box(errors, context, field, box, frac=False):
    if not isinstance(box, list) or len(box) != 4:
        err(errors, f"{context}: {field} must be [x,y,w,h]")
        return
    if not all(is_number(value) for value in box):
        err(errors, f"{context}: {field} values must be numbers")
        return
    if frac and (box[0] < 0 or box[1] < 0):
        err(errors, f"{context}: {field} x/y must be non-negative")
    if box[2] <= 0 or box[3] <= 0:
        err(errors, f"{context}: {field} width/height must be positive")


def report(errors):
    for e in errors:
        print(f"ERROR\t{e}")
    raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("element_analysis_json")
    args = ap.parse_args()

    data = json.loads(Path(args.element_analysis_json).read_text(encoding="utf-8-sig"))
    errors = []

    if not isinstance(data, dict):
        report(["top-level JSON must be an object"])

    for key in ("ref_width", "ref_height", "components", "slides"):
        if key not in data:
            err(errors, f"missing top-level key: {key}")

    for field in ("ref_width", "ref_height"):
        if field in data:
            validate_positive_int_field(errors, "top-level", field, data.get(field))

    components = data.get("components", {})
    if not isinstance(components, dict):
        err(errors, "components must be an object")
        components = {}

    for cid, comp in components.items():
        if not isinstance(comp, dict):
            err(errors, f"component {cid}: must be an object")
            continue
        validate_required(errors, f"component {cid}", comp, ("category", "asset_plan", "reuse"))
        cat = comp.get("category")
        plan = comp.get("asset_plan")
        if cat not in VALID:
            err(errors, f"component {cid}: invalid category {cat}")
        elif plan != VALID[cat]:
            err(errors, f"component {cid}: category {cat} expects asset_plan {VALID[cat]}, got {plan}")
        if "reuse" in comp:
            validate_string(errors, f"component {cid}", "reuse", comp.get("reuse"))

    slides = data.get("slides", [])
    if not isinstance(slides, list):
        err(errors, "slides must be an array")
        slides = []

    for slide in slides:
        if not isinstance(slide, dict):
            err(errors, "slide entries must be objects")
            continue
        validate_required(errors, "slide entry", slide, ("slide", "instances"))
        sid = slide.get("slide", "?")
        if "slide" in slide:
            validate_positive_int_field(errors, f"slide {sid}", "slide", sid)
        instances = slide.get("instances", [])
        if not isinstance(instances, list):
            err(errors, f"slide {sid}: instances must be an array")
            continue
        for inst in instances:
            if not isinstance(inst, dict):
                err(errors, f"slide {sid}: instance entries must be objects")
                continue
            validate_required(errors, f"slide {sid} instance {inst.get('id', '?')}", inst, ("component", "id", "bbox_px", "bbox_frac"))
            iid = inst.get("id", "?")
            comp = inst.get("component")
            if "id" in inst:
                validate_string(errors, f"slide {sid} instance {iid}", "id", iid)
            if "component" in inst:
                validate_string(errors, f"slide {sid} instance {iid}", "component", comp)
            if comp not in components:
                err(errors, f"slide {sid} instance {iid}: unknown component {comp}")
            validate_box(errors, f"slide {sid} instance {iid}", "bbox_px", inst.get("bbox_px"))
            validate_box(errors, f"slide {sid} instance {iid}", "bbox_frac", inst.get("bbox_frac"), frac=True)

    if errors:
        report(errors)

    print("element_analysis is valid")


if __name__ == "__main__":
    main()
