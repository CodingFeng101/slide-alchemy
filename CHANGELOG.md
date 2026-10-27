# Changelog

This file records the notable changes in each Slide Alchemy release.

## [Unreleased]

### Text extraction

- Replace visual-model text extraction with `scripts/extract_text.py`: RapidOCR reads the characters; position, font size, colour, weight, bullets, and paragraph merging are measured from the pixels. Ported from slide-alchemy-pipeline.
- Write compose-ready text boxes (`bbox_*`, with font-substitution slack and baseline lift) next to the measured glyph bounds (`ink_bbox_*`), and keep raw stroke metrics for bold calibration.
- Decide bold from the stroke width with the anti-aliased fringe removed, so that it no longer depends on which other text is on the page. Drop the stroke-variation serif guess, which flagged heavy sans titles as serif.
- Calibrate the glyph-to-em ratio against Microsoft YaHei as PowerPoint renders it (CJK 0.94), so that rebuilt text matches the source glyph height.
- Ignore baseline specks, such as a badge edge, when detecting bullets.
- Use RapidOCR 3.x, which runs on Python 3.13+ and bundles its models, and fall back to `rapidocr-onnxruntime` when only that is installed.
- Read images from bytes so that page paths with non-ASCII characters work on Windows.

### Composition

- Split text on `\n` into separate paragraphs; a run cannot hold a line break.
- Apply `line_spacing_pt` as exact line spacing, so merged paragraphs keep the source's line pitch.
- Place PNG images by their drawn pixels (`fit: visible`, the new default): the image bbox is the drawing's bounds from element analysis, and the transparent padding falls outside it. `fit: frame` (or spec-level `image_fit`) keeps the old whole-PNG stretch; the bundled example specs now set it explicitly.
- Default the slide height to the source page's aspect ratio when `slide_height_in` is omitted, instead of always 7.5in.
- Make `fill_transparency` take effect. It is a 0-100 percentage written as colour alpha; python-pptx had silently ignored it.
- Add `corner_radius_px` for `round_rect`.

### SVG conversion

- Read paint from inline `style` attributes and inherit it from `<g>`; apply `transform` (translate, scale, rotate, matrix) instead of silently dropping it.
- Scale stroke widths from viewBox units onto the slide; they were taken as points, so they came out twice as thick on a 1920-wide viewBox.
- Accept CSS colour names, `rgb()`/`rgba()`, and `#rrggbbaa`; apply `fill-opacity`, `stroke-opacity`, and `opacity`.
- Convert polygons, polylines, and straight-segment paths into freeform shapes, so diamonds and other outlines work and 10-point polygons are no longer forced into stars.
- Use the `rx`/`ry` radius for rounded rectangles, and rotate rects and ellipses natively.
- Remove the drop shadow that the theme's default effect added to every shape.
- Default `fill` to black as SVG does, and reject curves, skewed boxes, gradients, and nested `<svg>` with a clear error.

### Validation

- Require `png_asset_sheet_plan` when PNG components exist, and reject PNG components that are on no sheet or on more than one; require a sheet `id`. Plans without a `sheets` array produce a warning.

### Documentation

- Base generation keeps the source aspect ratio, and failure guidance covers a mismatched base.
- Correct the failure decision tree: no `z_order` field exists (array order stacks), the SVG scale note now matches the converter, and SVG text belongs in `texts_layout.json`.
- List `compose_spec.json`, `sheets/`, `crop_specs/`, and `out/compare/` in the run directory layout.
- README: describe measured text layout and the script dependency install; CONTRIBUTING: align the SVG rules with the converter; examples README: note which formats the strict run predates.

## [0.2.0] - 2026-07-10

Compared with `v0.1.0`, this release focuses on safer inputs, reproducible asset slicing, stricter QA, and clearer failure recovery.

### Reliability and validation

- Validate required fields, types, positive dimensions, bounding boxes, and component references in `element_analysis.json`.
- Reject unsafe or empty crop IDs and prevent crop output paths from escaping the selected output directory.
- Reject invalid contact-sheet dimensions and column counts.
- Make the default `unittest` discovery command run the bundled regression suite.

### SVG conversion

- Correctly map SVGs whose `viewBox` starts at a non-zero origin.
- Reject non-positive SVG and slide dimensions.
- Fail clearly on unsupported visible SVG elements instead of silently producing incomplete PPTX output.

### Asset slicing and QA

- Allow crop specs to store their key color while remaining compatible with the original crop-array format and CLI overrides.
- Store the magenta key color in all bundled strict-run crop specs, so the example sheets can be reproduced without extra arguments.
- Recursively inspect PNG assets and build contact sheets from nested directories.
- Fail asset QA when no PNG files are found instead of reporting a false success.

### Recovery guidance

- Expand the failure decision tree with concrete recovery steps for base generation, element classification, asset sheets, SVG conversion, text layout, PPTX composition, and preview QA.

### Tests

- Add regression coverage for SVG coordinate mapping, unsupported SVG elements, element-analysis validation, nested and empty asset directories, and crop-spec key colors.

## [0.1.0]

- Initial public workflow for rebuilding image-based slides into editable, component-based PPTX files.
