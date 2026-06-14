# SVG to OOXML

## Why SVG First

Follow the same rationale as ppt-master: AI and humans can read and debug SVG, while raw DrawingML is verbose and hard to author directly. The conversion step should translate SVG primitives into editable PowerPoint OOXML objects rather than embedding the SVG as a picture.

ppt-master's published pipeline is:

```text
AI generates SVG -> finalize_svg.py -> svg_to_pptx.py -> native editable PPTX
```

Its docs describe `svg_to_pptx.py` as the native conversion command and `finalize_svg.py` as the cleanup step that aggregates SVG post-processing such as embedding icons, fixing aspect ratios, flattening tspan, and converting rounded rects to paths when needed.

## Use in This Skill

This skill is not a full ppt-master replacement. Use SVG-to-OOXML only for reusable non-semantic slide geometry:

- lines,
- stars,
- circles and rings,
- rounded rectangles,
- card bases,
- title bars,
- simple circuit lines,
- simple frames.

Use PNG for standalone icons and complex composites. A line-art icon is still an icon if it represents a recognizable object, person, device, badge, app symbol, building, cloud, chart, security mark, or themed pictogram. Do not recreate those icons with PPT native shapes unless the user explicitly accepts visual drift for editability.

## PowerPoint-Safe SVG Subset

Prefer this subset for generated component SVGs:

- `<rect x y width height rx ry fill stroke stroke-width fill-opacity stroke-opacity>`
- `<circle cx cy r ...>`
- `<ellipse cx cy rx ry ...>`
- `<line x1 y1 x2 y2 ...>`
- `<polyline points ...>`
- `<polygon points ...>` for simple stars or diamonds
- `<path d ...>` only for simple curves that cannot be expressed by primitives

Avoid:

- CSS stylesheets,
- filters and blur,
- masks and clip paths,
- marker-based arrows,
- `rgba(...)`; use hex color plus opacity attributes,
- deeply nested transforms.

## Conversion Strategy

Use one of these approaches:

1. If a local ppt-master checkout is available, use its project-level pipeline for full SVG pages:
   `finalize_svg.py` then `svg_to_pptx.py --only native`.
2. For this skill's small reusable components, use `scripts/simple_svg_to_pptx.py` or equivalent python-pptx shape generation. It maps the safe SVG subset to editable PPT shapes, which serialize as OOXML.
3. If a component is a semantic icon or contains unsupported SVG features, reclassify it as `icon_png` or `complex_png_whole` unless the user explicitly requires native editability.

## Validation

After conversion, open or export the PPTX preview and verify:

- the object is selectable as a shape, not a raster screenshot,
- fill and stroke can be recolored,
- the object scales cleanly,
- the visual position matches the recorded `bbox_px`.

If visual fidelity and editability conflict, prefer editability only for true layout geometry in `simple_geometry_svg_ooxml`. Prefer PNG for semantic icons and complex graphics.
