# Text Extraction

Extract text with OCR plus pixel measurement, not with a visual model. Run `scripts/extract_text.py` on the source page images.

Division of labour: the OCR model (RapidOCR 3.x on onnxruntime, models bundled in the wheel; the older `rapidocr-onnxruntime` package is used if that is what is installed) only turns pixels into characters. Position, font size, colour, weight, bullets, and line merging are all measured from the pixels. A visual model asked for every text box on a dense page returns approximations, and approximate boxes are what make a rebuild look misaligned. OCR returns glyph-level bounds in seconds on CPU.

## Command

```bash
python scripts/extract_text.py run/source/slide_*.png --out run/analysis/texts_layout.json
```

Options:

- `--bold-mode auto|off|on|ratio:<value>`: how weight is decided. Default `auto`.
- `--no-merge-lines`: keep one text box per OCR line instead of merging paragraphs.
- `--expected <file>`: UTF-8 file of known text, one string per line (for example text pulled from PPTX XML). Near-miss OCR readings of the same length are corrected to it; it never adds text that OCR did not find.
- `--slide-width-in <inches>`: must match `slide_width_in` in the compose spec. Default `13.333333`.

Slide numbers come from the trailing digits of each file name (`slide_003.png` -> 3).

## Schema

`texts_layout.json`:

```json
{
  "method": "ocr",
  "ocr_engine": "rapidocr",
  "bold_mode": "auto",
  "slide_width_in": 13.333333,
  "ref_width": 1672,
  "ref_height": 941,
  "slides": [
    {
      "slide": 1,
      "source": "slide_001.png",
      "width": 1672,
      "height": 941,
      "texts": [
        {
          "id": "s1_t7",
          "text": "统一数据汇聚\n实时分析看板\n多端协同共享",
          "bbox_px": [427, 337, 218, 129],
          "bbox_frac": [0.255383, 0.358144, 0.130383, 0.137552],
          "ink_bbox_px": [427, 350, 146, 106],
          "ink_bbox_frac": [0.255383, 0.371945, 0.087321, 0.112646],
          "font_size_pt": 12.83,
          "color": "#242E5C",
          "bold": false,
          "italic": false,
          "align": "left",
          "font_family": "Microsoft YaHei",
          "bullet": false,
          "script": "cjk",
          "conf": 0.998,
          "line_spacing_pt": 24.4,
          "metrics": {
            "stroke_px": 1.91,
            "stroke_ratio": 0.085,
            "stroke_ratio_net": 0.041,
            "stroke_cv": 0.075,
            "slant": -0.02
          }
        }
      ]
    }
  ]
}
```

Field meanings:

- `bbox_px` / `bbox_frac`: the text box to compose. It is wider than the ink (1.35x + 12pt) because the opening machine substitutes fonts and a box cut to the measured width wraps. It also starts a little above the ink because PowerPoint draws leading above the first line. Copy these into the compose spec unchanged.
- `ink_bbox_px` / `ink_bbox_frac`: the measured glyph bounds. Use them for QA and overlap checks, not for composing.
- `font_size_pt`: points on a slide `slide_width_in` wide.
- `line_spacing_pt`: present only on merged paragraphs. It is the page's own line pitch, and the composer applies it as exact line spacing.
- `bullet`: a leading bullet was detected. The text already carries a `• ` prefix on each line.
- `metrics`: raw measurements, kept so a bold threshold can be calibrated once and reused across a batch.
- `align` is always `left`, because the box is anchored at the measured left edge of the ink.

## How the Measurement Works

These points are load-bearing. Do not "simplify" them away.

- **Filtering.** Results below 0.5 confidence are dropped, along with short strings below 0.75 confidence and lone Latin characters below 0.90, because these are usually icons misread as glyphs. Slanted lines are left in the background, because a horizontal box would place them wrong.
- **Background colour.** Taken as the median of a ring just outside the OCR box, never from inside it.
- **Ink mask.** Requires both distance from the background *and* saturation no higher than the text colour's plus a margin. Colour distance alone is not enough: a green tick is 136 away from dark grey text, against a threshold of 130. Without the saturation test, small coloured icons become text.
- **Bounds.** Re-derived from the ink mask. OCR boxes routinely swallow a neighbouring icon.
- **Font size.** The 80th percentile of connected-component heights, after dropping fragments shorter than half the tallest component. Thin CJK strokes break into pieces, and keeping those pieces would make the size a third too small. Divide by the face ratio to get the em. The ratio belongs to the face the composer renders (Microsoft YaHei in PowerPoint), not to the source face, because the rebuilt ink is what has to match: CJK 0.94, Latin 0.75. An all-lowercase Latin line without ascenders measures small, because its components are mostly x-height.
- **Colour.** The median of the *eroded* mask. Anti-aliased edges are a blend of text and background, and sampling them washes the colour out.
- **Weight.** Use a distance transform, never ink coverage. Coverage cannot tell a dense regular glyph from a simple bold one. About 1px of anti-aliased fringe is subtracted before dividing by the em (`stroke_ratio_net`). `auto` calls CJK text bold at 0.067 or above and Latin text at 0.09 or above. Below about 18px, bold and regular overlap, and no threshold separates them.
- **Bullets.** A small leading component in the middle band of the line, followed by a gap, is a bullet. So is a leading bullet character in the OCR text. A speck at the top or baseline of the line is the edge of a badge, not a bullet.
- **Line merging.** Each block is chained to its own successor below it, with similar left edge, size, colour, weight, and bullet state. Do not merge in reading order: reading order interleaves side-by-side columns and severs every paragraph on a two-column page.

## Bold Calibration

Bold is relative to the regular weight of the same family, and a page may contain no regular sample to compare against. If `auto` gets a template wrong:

1. Read `metrics.stroke_ratio` for blocks you know are bold and blocks you know are regular.
2. Re-run with `--bold-mode ratio:<value between them>`.
3. Reuse that value for every page of the same template.

Use `off` or `on` when the whole deck is a single weight.

## Limits

- No serif detection. Every box gets `Microsoft YaHei`. Stroke variation rises with size and weight, not with serifs, so it cannot tell Songti from a heavy sans. If the source is clearly a serif face, set `font_family` in the compose spec by hand.
- Arrows, chevrons, and other symbols (→, ›, ✓) are not text. OCR drops them. They belong in `element_analysis.json` as geometry or icons.
- Rotated or vertical text is left out.
- Artistic lettering with gradient, warped shape, or texture may be treated as a PNG decoration only when normal text cannot approximate it.
- Prefer editable text over raster text for all normal Chinese and English content.
