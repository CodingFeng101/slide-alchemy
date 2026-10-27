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

`scripts/simple_svg_to_pptx.py` converts this subset. Anything outside it raises an error rather than being dropped or approximated.

| SVG | PowerPoint result |
| --- | --- |
| `<rect x y width height>` | rectangle |
| `<rect ... rx ry>` | rounded rectangle; one radius for all corners (the smaller of `rx`/`ry`) |
| `<circle>`, `<ellipse>` | oval |
| `<line>` | straight connector; skipped when it has no stroke, as in SVG |
| `<polygon>`, `<polyline>` | freeform shape (diamonds, stars, chevrons, any straight-edged outline) |
| `<path d>` with `M L H V Z` (absolute or relative) | freeform shape; several subpaths become one shape, so a hole stays a hole |
| `<g>` | grouping only; its paint and `transform` apply to its children |

Paint and geometry:

- `fill`, `stroke`, `stroke-width`, `fill-opacity`, `stroke-opacity`, `opacity`, as attributes or inline `style`, inherited from `<g>`.
- Colours: `#rgb`, `#rrggbb`, `#rrggbbaa`, `rgb()`, `rgba()`, CSS colour names, `none`. As in SVG, an element with no `fill` is filled black.
- `transform`: `translate`, `scale`, `rotate`, `matrix`, and nesting. A rect or ellipse may be rotated or scaled, but not skewed or mirrored; polygons and paths accept any transform.
- Stroke widths are in viewBox units and are scaled onto the slide.
- Group `opacity` is multiplied into each child, which differs from SVG only where children overlap.
- Shapes carry no shadow; the theme's default effect is switched off.

Not supported (error):

- curves in paths (`C S Q T A`): flatten to straight segments or reclassify as PNG,
- gradients, patterns, `url(#...)` paints,
- `<style>` blocks, CSS classes, filters, masks, clip paths, markers,
- `<use>`, `<image>`, `<text>`, nested `<svg>`,
- skewed or mirrored rects and ellipses.

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
