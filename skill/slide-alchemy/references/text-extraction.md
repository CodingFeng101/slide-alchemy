# Text Extraction

Use a visual model as the default source for text layout. If a PPTX exists, its XML may be used only as a helper or verification source.

## Schema

Use `texts_layout.json`:

```json
{
  "ref_width": 1920,
  "ref_height": 1080,
  "slides": [
    {
      "slide": 1,
      "texts": [
        {
          "id": "title_left",
          "text": "Example",
          "bbox_px": [100, 100, 500, 80],
          "bbox_frac": [0.052083, 0.092593, 0.260417, 0.074074],
          "font_size_pt": 36,
          "color": "#A52922",
          "bold": true,
          "align": "center",
          "font_family": "Microsoft YaHei",
          "style_notes": "heavy title"
        }
      ]
    }
  ]
}
```

## Extraction Notes

- Preserve line breaks when visible line breaks matter.
- Record source pixel bboxes, then convert to fractions.
- Estimate font size from visual height, then correct after preview.
- Prefer editable text over raster text for all normal Chinese and English content.
- Artistic lettering with gradient, warped shape, or texture may be treated as a PNG decoration only when normal text cannot approximate it.
