---
name: slide-alchemy
description: Rebuild image-based PPT/PPTX slides, slide screenshots, or visual slide pages into an editable component-based PowerPoint deck. Use when the user asks to convert picture-style PPT to editable PPTX, restore slide screenshots into editable slides, extract slide bases/icons/text, rebuild slides with editable text, or create a lightweight alternative to full image-to-editable-ppt workflows. This skill emphasizes base-background generation, element classification, SVG-to-OOXML for simple geometry, generated PNG assets for complex icons, visual-model text extraction, conservative icon slicing QA, and two base-stage review stops.
---

# Slide Alchemy

## Purpose

Rebuild visual slide pages into editable PPTX by separating each page into:

1. clean base background PNG,
2. editable geometry from SVG/OOXML,
3. transparent PNG icon assets,
4. editable text boxes.

Keep this workflow lightweight. Do not use page workers or an editppt-style state machine.

## Required Workflow

1. Propose base grouping before extraction.
   Inspect the source page images first, identify likely cover/content/ending/custom base groups, then present a recommended grouping to the user. This is the first allowed stop: ask the user to accept or modify the recommendation before generating bases, unless the user explicitly asked for an unattended full run.

2. Render or obtain source page images.
   Treat even a PPTX input as visual source pages unless the user explicitly asks to reuse existing PPTX objects. Do not shortcut by deleting existing PPTX objects to create the base.

3. Generate clean bases with an image generation/editing model.
   The default base is a general background: keep outer background, edge decoration, ambient texture, and theme visuals; remove all text, icons, cards, boxes, title bars, and central content. Only preserve central layout containers if the user explicitly asks for template containers.

   This is the second allowed stop: after generating base preview images, show the bases to the user and wait for approval before extracting elements, unless the user explicitly requested an unattended full run.

4. Analyze every non-text visual element before slicing.
   Create `element_analysis.json` with reusable components and per-slide instances. Do not put all elements into an icon sheet first.

5. Classify each element:
   - `simple_geometry_svg_ooxml`: non-semantic layout geometry such as straight lines, dividers, stars, circles, rings, rounded rectangles, card bases, title bars, simple borders, and simple circuit-line decorations. Generate SVG first, then convert or recreate as editable OOXML/PPT shapes.
   - `icon_png`: standalone illustrative or semantic icons such as trophies, flowers, books, hands/heart, computer, chain link, organization badges, app pictograms, people, devices, buildings, or any recognizable object icon. Even if an icon looks like simple line art, keep it as generated PNG unless it is just a primitive layout shape.
   - `complex_png_whole`: complex composite visuals that would look worse if split, such as swirls, layered badges, heavy gradients, glow assemblies, illustrations. Generate as one PNG and do not split.

   Validate the result against `references/element-analysis.schema.json` when practical.

6. Reuse repeated components.
   Generate one star and copy/scale it. Generate one card base and one title bar and reuse them. Do not generate separate PNGs for repeated simple geometry.

7. Generate PNG asset sheets only for PNG categories.
   Keep `simple_geometry_svg_ooxml` elements out of PNG sheets. PNG sheets must be generated with an image generation/editing model on a high-contrast solid key color and large empty space around each icon. Complex icons may be generated one per sheet. Never crop `icon_png` or `complex_png_whole` assets directly from the original/source slide image; the source slide is only a visual reference or edit target for regeneration.

8. Slice PNG assets conservatively.
   Preserve padding around every transparent PNG. Run edge-touch checks and create contact sheets. If any icon touches a crop edge, is truncated, or includes neighboring elements, regenerate the sheet or recrop with more space.

   Do not stop for approval after generating assets. Continue to text extraction and composition after edge checks and contact sheets are ready.

9. Extract text with a visual model.
   Record text content, source bbox, font size, color, bold/weight, alignment, line breaks, and approximate font family/style in `texts_layout.json`. PPTX XML may help verify, but visual extraction is the default method.

10. Compose the final PPTX in this layer order:
    base PNG -> SVG/OOXML editable geometry -> PNG icons -> editable text boxes.
    Use `scripts/compose_component_pptx.py` with a compose spec when possible; do not rewrite ad hoc composition logic for every task.

11. Export previews and QA visually.
    Compare preview pages with source pages. Check for over-preserved bases, missing elements, cut-off icons, polluted icon crops, duplicated elements, and text overflow.
    Use `scripts/compare_preview.py` after preview PNGs exist.

## Review Stops

Use at most two review stops by default:

1. Base grouping review: deliver the proposed base groups and wait for user approval or edits.
2. Base preview review: deliver clean base previews and wait for user approval or regeneration requests.

Do not stop after PNG asset generation. Contact sheets and classification summaries are QA artifacts, not approval gates. Only skip the two base-stage stops when the user explicitly asks to run all steps automatically.

## Output Files

Use a run directory with this shape:

```text
run/
  source/
    slide_001.png
  base/
    slide_001_base.png
  analysis/
    element_analysis.json
    texts_layout.json
  assets/
    svg/
    png/
    contact_sheets/
  out/
    editable.pptx
    preview/
```

## References

Read only the relevant reference before acting:

- `references/workflow.md`: detailed end-to-end sequence and required artifacts.
- `references/element-classification.md`: classification rules, reuse rules, and common traps.
- `references/icon-slicing-qa.md`: PNG asset sheet, chroma key, padding, edge-touch, and contact sheet rules.
- `references/text-extraction.md`: visual text extraction schema and style fields.
- `references/base-prompt-template.md`: prompt template for clean base generation.
- `references/base-grouping.md`: how to infer and present recommended base groups.
- `references/icon-sheet-prompt-template.md`: prompt template for PNG icon asset sheets.
- `references/svg-to-ooxml.md`: SVG-to-OOXML strategy, supported component SVG subset, and ppt-master notes.
- `references/element-analysis.schema.json`: schema for component and instance analysis.
- `references/compose-spec.md`: JSON format consumed by the final PPTX composer.
- `references/failure-decision-tree.md`: what to do when bases, icons, text, SVG conversion, or QA fail.
- `references/checkpoints.md`: base-stage review stops and what to deliver.

## Scripts

Script dependencies are listed in `requirements.txt` inside this skill directory. Install them from the installed skill folder when the runtime does not already provide them.

Use bundled scripts for deterministic checks:

- `scripts/inspect_edges.py`: report transparent PNGs that touch crop edges.
- `scripts/build_contact_sheet.py`: make contact sheets for sliced PNG assets.
- `scripts/slice_asset_sheet.py`: slice a solid-key asset sheet from a JSON crop spec while preserving padding.
- `scripts/simple_svg_to_pptx.py`: convert simple component SVG primitives into editable PPTX shapes for quick validation or component reuse.
- `scripts/validate_element_analysis.py`: lightweight validation for `element_analysis.json` without external dependencies.
- `scripts/compose_component_pptx.py`: compose base images, editable shapes, PNG assets, and editable text into a PPTX from JSON.
- `scripts/compare_preview.py`: create side-by-side and difference images from source/preview PNGs.
