# Compose Spec

`scripts/compose_component_pptx.py` reads a JSON compose spec and creates a PPTX.

The script expects positions as source-pixel bboxes by default. It can also use fraction bboxes.

## Minimal Example

```json
{
  "ref_width": 1920,
  "ref_height": 1080,
  "slide_width_in": 13.333333,
  "slide_height_in": 7.5,
  "slides": [
    {
      "base": "base/slide_001_base.png",
      "geometry": [
        {
          "id": "title_line",
          "kind": "line",
          "bbox_px": [220, 250, 600, 4],
          "fill": "#C00000"
        },
        {
          "id": "card",
          "kind": "round_rect",
          "bbox_px": [200, 300, 450, 420],
          "fill": "#FFF7EE",
          "line": "#EBC8A7",
          "line_width": 1.2
        }
      ],
      "images": [
        {
          "id": "code_icon",
          "path": "assets/png/code_icon.png",
          "bbox_px": [360, 410, 140, 120]
        }
      ],
      "texts": [
        {
          "id": "title",
          "text": "Example",
          "bbox_px": [300, 100, 500, 80],
          "font_size_pt": 36,
          "color": "#A52922",
          "bold": true,
          "align": "center"
        }
      ]
    }
  ]
}
```

## Geometry Kinds

Supported editable geometry:

- `rect`
- `round_rect`
- `oval`
- `star`
- `line`

Use these for the same objects classified as `simple_geometry_svg_ooxml`. For complex SVG paths, use the full ppt-master pipeline if available, or reclassify as PNG.

## Layering

The composer always adds:

1. `base`,
2. `geometry` in array order,
3. `images` in array order,
4. `texts` in array order.

This avoids accidental duplicate full-slide screenshots above editable content.
