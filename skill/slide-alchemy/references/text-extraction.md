# Text Extraction

Extract text with OCR plus pixel measurement, not with a visual model. Run `scripts/extract_text.py` on the source page images.

Division of labour: the OCR model (RapidOCR 3.x on onnxruntime, models bundled in the wheel; the older `rapidocr-onnxruntime` package is used if that is what is installed) only turns pixels into characters. Position, font size, colour, weight, bullets, and line merging are all measured from the pixels. A visual model asked for every text box on a dense page returns approximations, and approximate boxes are what make a rebuild look misaligned. OCR returns glyph-level bounds in seconds on CPU.

## Command

```bash
python scripts/extract_text.py run/source/slide_*.png --out run/analysis/texts_layout.json
```

The standard command enables local/remote font matching and rich text by default.
It prepares the core font cache, scans system fonts and uses the bundled model.
Every visible run must have a usable match before a layout is written. Setup
failures and incomplete matches stop with an error. The output marks
`font_matching_required: true`. Preserve the matching records when composing.

Options:

- `--bold-mode auto|off|on|ratio:<value>`: how weight is decided. Default `auto`.
- `--no-merge-lines`: keep one text box per OCR line instead of merging paragraphs.
- `--expected <file>`: UTF-8 file of known text, one string per line (for example text pulled from PPTX XML). Near-miss OCR readings of the same length and whitespace-only differences are corrected to it; it never adds text that OCR did not find.
- `--slide-width-in <inches>`: must match `slide_width_in` in the compose spec. Default `13.333333`.
- `--font-index <file>` and `--font-model <file>`: select an explicit local font index and ONNX encoder. Supply both together. The encoder ranks eligible fonts and OpenCV refines the first 10. Otherwise the core pack, system fonts and bundled encoder are prepared automatically.
- `--rich-text` / `--no-rich-text`: enable or disable inline style/effect extraction. The default is enabled. Disabling rich text keeps per-line font matching active.
- `--font-server <release-url>`: select the remote library used to expand poor local matches. Defaults to `http://182.254.211.241/fonts/v1`. Use `--font-cache <directory>` to select the download cache. See `font-distribution.md` for file verification and review limits.
- `--ocr-only`: explicit legacy OCR measurement analysis with the Microsoft YaHei estimation path. Font matching and rich text are disabled in this mode. Reconstructed slides require matching records before composition.

Slide numbers come from the trailing digits of each file name (`slide_003.png` -> 3).

## Local Font Matching

Install the main requirements for inference. Training and ONNX export additionally require `requirements-font-training.txt`.

```bash
python scripts/match_fonts.py index --text "Campus2026" --out run/fonts/index.json
python scripts/train_font_matcher.py --font-index run/fonts/index.json --out run/fonts/encoder.onnx --steps 4000
python scripts/extract_text.py run/source/slide_*.png --font-index run/fonts/index.json --font-model run/fonts/encoder.onnx --out run/analysis/texts_layout.json
```

The index command accepts font files or directories, and scans system font directories when none are supplied. Use a curated font directory to control the candidate set. It indexes individual TTC faces, deduplicates family/style pairs, checks character coverage, and records file hashes. Rebuild the index after replacing a font file. Variable fonts contribute their default face. Export separate static font files for additional variable-font instances. The index records `fs_type` for later embedding work. Font licensing and embedding are separate from matching.

Training generates synthetic text with paired augmentations and hard negative metric learning. Each batch renders the same text across several fonts. The small convolutional encoder exports 64-dimensional normalized features. ONNX Runtime handles inference without PyTorch. The training command also writes `encoder.evaluation.json` using held-out phrases and scale/blur/threshold perturbations. These results measure synthetic performance. Verify recognition separately on real slide screenshots.

Matching runs on individual OCR lines before paragraph merging. Every eligible font renders the recognized text. The encoder selects up to 10 candidates, then OpenCV compares stroke distances, overlap, and dimensions. Refinement searches native pixel sizes and uniformly resized references to account for screenshot resampling. Full-width CJK lines at least 40 pixels high also use per-glyph comparison, which reduces the influence of tracking. Colour-connected growth recovers lighter edges around coloured gradient text. Neutral-colour text keeps the original mask. Fonts without an indexed bold face also try synthetic bold during refinement.

Matching updates `font_family`, `font_face`, `bold`, `italic`, and `font_size_pt`. The fitted `size_px` is converted to points using the extraction slide width. `font_face` carries the full face name, including Medium/Light faces that a family name and bold flag cannot represent. The composer prefers this field and writes both Latin and East Asian typefaces. Older indexes are enriched with face metadata when loaded, and older layout files continue to use `font_family`.

Blocks measured as the same size, colour, script, weight and slant can select a common near-best candidate. This uses the existing sibling-style measurements. The selected face must occur in every line's shortlist, with mean score penalty at most 0.025 and individual penalty at most 0.08. Original rankings remain available, while `selected_candidate` and `selection: shared_style` record the group choice. These grouping thresholds are heuristics and require verification when a page intentionally mixes fonts within otherwise similar styles.

Each text record gains `font_matches`, with one report per original OCR line. Reports contain ranked candidates, model similarities, shape errors, the gap between the best two shape errors, and whether each face appeared in training. These are diagnostic scores, not calibrated probabilities. `needs_review` flags score gaps below 0.005, best shape errors above 0.12, or faces absent from training. These thresholds are provisional. OCR mistakes and very short strings also require review. `no_supported_font` leaves the original font selection in place.

To match an existing tightly cropped single-line image directly, use the following command.

```bash
python scripts/match_fonts.py match line.png --text "Campus2026" --font-index run/fonts/index.json --font-model run/fonts/encoder.onnx --out run/fonts/match.json
```

## Schema

With `--rich-text`, text entries additionally contain `runs` and `style_report`. Run text concatenation preserves the full recognized string, including explicit newlines and bullet prefixes. Character boxes from RapidOCR 3.x locate colour/script changes. Persistent stroke-width changes propose weight boundaries. Explicit spaces propose boundaries when both sides contain at least three characters. Overlapping four-character retrieval also proposes boundaries when two confident windows on each side consistently favour different faces, with model similarity gaps above 0.08. These thresholds are heuristic. Short same-colour font changes can be missed and require review. Plain punctuation inherits the neighbouring writing system. The fitting uses antialias coverage near strong fill and an outer exclusion band to separate ordinary edges and outlines from displaced shadows. Stroke-covered fills are expanded before font matching to account for outlines. Close font candidates within 0.005 shape error use model similarity to resolve ties. The original rankings remain available.

Automatic effect fitting currently covers two-stop linear gradients, coloured outlines up to four source pixels, and one outer shadow with offsets from -4 to 4 pixels and blur candidates 0, 1 and 2 pixels. Fitted parameters are converted to points. Native writing also accepts explicit multistop gradients and arbitrary valid effect parameters. Complex bevels, textured/metallic fills and low-confidence boundaries require review. The `style_fit.pixel_rmse` and `needs_review` fields expose approximation error. Missing character positions also mark the result for review. Weak shadows and shadows combined with outlines can be missed even when `needs_review` is false. Validate on held-out real renderings before relying on automatic segmentation or effect recovery.

Example command for mixed styles and effects follows.

```bash
python scripts/extract_text.py run/source/slide_*.png --rich-text --font-index run/fonts/index.json --font-model run/fonts/encoder.onnx --out run/analysis/texts_layout.json
```

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
            "stroke_ratio_area": 0.0951,
            "em_ref_px": 36.0,
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
- `metrics`: raw measurements, kept so a bold threshold can be calibrated once and reused across a batch. `stroke_ratio_area` is what weight is decided on; `em_ref_px` is the em on a page scaled to 1920px wide.
- `bold_offset` (top level): where this deck's regular and bold clusters part, relative to the size-based threshold. `0` means no clear split was found and the threshold was used as is.
- `align` is always `left`, because the box is anchored at the measured left edge of the ink.

## How the Measurement Works

These points are load-bearing. Do not "simplify" them away.

- **Filtering.** Results below 0.5 confidence are dropped, along with short strings below 0.75 confidence and lone Latin characters below 0.90, because these are usually icons misread as glyphs. Slanted lines are left in the background, because a horizontal box would place them wrong.
- **Background colour.** Taken as the median of a ring just outside the OCR box, never from inside it.
- **Ink mask.** Requires both distance from the background *and* saturation no higher than the text colour's plus a margin. Colour distance alone is not enough: a green tick is 136 away from dark grey text, against a threshold of 130. Without the saturation test, small coloured icons become text.
- **Bounds.** Re-derived from the ink mask. OCR boxes routinely swallow a neighbouring icon.
- **Font size.** The 80th percentile of connected-component heights, after dropping fragments shorter than half the tallest component. Thin CJK strokes break into pieces, and keeping those pieces would make the size a third too small. Divide by the face ratio to get the em. The ratio belongs to the face the composer renders (Microsoft YaHei in PowerPoint), not to the source face, because the rebuilt ink is what has to match: CJK 0.94, Latin 0.75. An all-lowercase Latin line without ascenders measures small, because its components are mostly x-height.
- **Colour.** The median of the *eroded* mask. Anti-aliased edges are a blend of text and background, and sampling them washes the colour out.
- **Weight.** Stroke width is twice the ink area over the outline length, with anti-aliased pixels counted by their coverage, divided by the em (`stroke_ratio_area`). Do not use ink coverage of the box, which cannot tell a dense regular glyph from a simple bold one, and do not use a distance transform, which moves in whole-pixel steps and put 15-18pt regular text on the same step as bold headings. The threshold is `0.0915 + 0.75 / em_ref_px`: high for small text, easing with size. Generated decks draw body text heavier than a true regular, and how much heavier varies by deck, so `auto` then looks across all pages for the valley between the deck's own regular and bold clusters and shifts the threshold there (`bold_offset`). Finally, blocks on one page with the same size and colour, such as a row of card titles, take the majority weight. Bold below about 13pt (a 26px em) is usually read as regular.
- **Bullets.** A small leading component in the middle band of the line, followed by a gap, is a bullet. So is a leading bullet character in the OCR text. A speck at the top or baseline of the line is the edge of a badge, not a bullet.
- **Line merging.** Each block is chained to its own successor below it, with similar left edge, size, colour, weight, and bullet state. Do not merge in reading order: reading order interleaves side-by-side columns and severs every paragraph on a two-column page.

## Bold Calibration

Bold is relative to the regular weight of the same family. `auto` finds that split per deck, so run the whole deck in one call rather than page by page. If it still gets a template wrong:

1. Read `metrics.stroke_ratio_area` for blocks you know are bold and blocks you know are regular.
2. Re-run with `--bold-mode ratio:<value between them>`.
3. Reuse that value for every page of the same template.

Use `off` or `on` when the whole deck is a single weight.

## Limits

- Without the optional font matcher, every box gets `Microsoft YaHei`. Stroke measurements alone cannot reliably distinguish Songti from a heavy sans. Set `font_family` by hand or use the trained font matcher.
- Arrows, chevrons, and other symbols (→, ›, ✓) are not text. OCR drops them. They belong in `element_analysis.json` as geometry or icons.
- Rotated or vertical text is left out.
- All lettering remains native editable PowerPoint text, including artistic, warped, metallic and extruded lettering. Recreate available native effects and approximate unsupported effects, recording the visual differences in preview QA.
- Preserve the recognized characters in text boxes/runs. Rasterized lettering and glyph outlines converted to shapes violate this requirement.
