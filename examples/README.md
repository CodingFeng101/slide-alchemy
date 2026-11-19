# Examples

## Complex Chinese slides

[Image-based PPTX](03-complex-chinese/image-ppt.pptx) · [Editable PPTX](03-complex-chinese/editable.pptx)

| Slide | Image input | Objects selected in PowerPoint | Clean rebuild |
| --- | --- | --- | --- |
| 01. Retail performance | [Source](03-complex-chinese/source-01.jpg) | [Selected objects](03-complex-chinese/selected-01.jpg) | [Clean rebuild](03-complex-chinese/rebuilt-01.jpg) |
| 02. Cross-region release architecture | [Source](03-complex-chinese/source-02.jpg) | [Selected objects](03-complex-chinese/selected-02.jpg) | [Clean rebuild](03-complex-chinese/rebuilt-02.jpg) |
| 03. Warehouse redesign | [Source](03-complex-chinese/source-03.jpg) | [Selected objects](03-complex-chinese/selected-03.jpg) | [Clean rebuild](03-complex-chinese/rebuilt-03.jpg) |
| 04. Pendulum experiment | [Source](03-complex-chinese/source-04.jpg) | [Selected objects](03-complex-chinese/selected-04.jpg) | [Clean rebuild](03-complex-chinese/rebuilt-04.jpg) |
| 05. Office space planning | [Source](03-complex-chinese/source-05.jpg) | [Selected objects](03-complex-chinese/selected-05.jpg) | [Clean rebuild](03-complex-chinese/rebuilt-05.jpg) |
| 06. Self-service pilot | [Source](03-complex-chinese/source-06.jpg) | [Selected objects](03-complex-chinese/selected-06.jpg) | [Clean rebuild](03-complex-chinese/rebuilt-06.jpg) |
| 07. Assembly downtime improvement | [Source](03-complex-chinese/source-07.jpg) | [Selected objects](03-complex-chinese/selected-07.jpg) | [Clean rebuild](03-complex-chinese/rebuilt-07.jpg) |
| 08. City archive exhibition | [Source](03-complex-chinese/source-08.jpg) | [Selected objects](03-complex-chinese/selected-08.jpg) | [Clean rebuild](03-complex-chinese/rebuilt-08.jpg) |

The selection screenshots were captured in PowerPoint with all objects selected. The rebuilt deck has native text boxes and shapes, with movable image components. Chart marks and table grids are editable shapes. Complex illustrations were regenerated and can differ from the source. All slides use generated demonstration material.

## Basic examples

Each basic example contains:

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
| [`01-smart-campus`](01-smart-campus) | Blue smart-campus module slide. |
| [`02-project-overview`](02-project-overview) | Green project-content overview slide. |
