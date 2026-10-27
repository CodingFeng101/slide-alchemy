# Examples

Each example contains:

- `source.png`: the original full-slide image.
- `image-ppt.pptx`: a picture-based PPTX with the source image as one full-slide image.
- `editable.pptx`: the strict Slide Alchemy rebuild with editable text, editable geometry, and movable PNG icons.
- `image-ppt-screenshot.png`: screenshot of the image PPT.
- `editable-selected-textboxes.png`: screenshot of the editable PPT with all text boxes selected.

The full intermediate strict run is stored in `_strict-rebuild-run/`, including bases, `element_analysis.json`, `texts_layout.json`, icon sheets, sliced PNGs, contact sheets, previews, and comparison images.

That run predates two later changes, so do not use it as a format reference for them:

- Its `texts_layout.json` came from visual-model extraction. Current runs write it with `scripts/extract_text.py`, which adds `ink_bbox_*`, `line_spacing_pt`, `metrics`, and compose-ready text boxes (see `references/text-extraction.md`).
- Its compose specs give image bboxes that already include the PNG padding, so they set `"image_fit": "frame"`. Current runs use the drawing's own bbox with the default `fit: visible` (see `references/compose-spec.md`).

| Folder | Scenario |
| --- | --- |
| `01-smart-campus` | Blue smart-campus module slide. |
| `02-project-overview` | Green project-content overview slide. |
