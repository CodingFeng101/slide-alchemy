---
name: slide-alchemy
description: Use when converting image-based PPT/PPTX files, slide screenshots, scanned slide pages, or visual decks into editable component-based PowerPoint files; restoring slide images into editable text, shapes, and generated PNG assets; or running a lightweight image-to-editable-PPT workflow.
---

# Slide Alchemy

## Purpose

Rebuild visual slide pages into editable PPTX by separating each page into:

1. clean base background PNG,
2. editable geometry from SVG/OOXML,
3. transparent PNG icon assets,
4. editable text boxes.

Keep this workflow lightweight. Do not use page workers or an editppt-style state machine.

## Non-Negotiable Rules

Any request to convert slides into an editable PPTX must run the complete workflow. Do not use a shortcut path for small decks, first pages only, quick demos, outputs-only requests, or final-PPTX requests. The workflow is mandatory even when the user asks for only one page.

The following steps must always happen in order:

1. source page rendering,
2. base grouping,
3. clean base generation with an image generation/editing model,
4. element analysis,
5. SVG/OOXML generation for true layout geometry,
6. PNG asset sheet generation with an image generation/editing model for icons and complex visuals,
7. PNG slicing and contact-sheet QA,
8. visual text extraction,
9. PPTX composition,
10. preview export and visual QA.

Image generation/editing model use is mandatory for:

- clean base backgrounds;
- `icon_png` asset sheets;
- `complex_png_whole` asset sheets;
- any regenerated visual asset that must match the image PPT.

Do not replace those model steps with local white masks, local inpainting, direct source-image crops, copied screenshot fragments, PPT native shape approximations, or generic presentation templates.

## Execution Discipline

Follow the workflow in order. Do not skip ahead, merge phases, or compose the final PPTX before required upstream artifacts exist.

Before starting each step, check that the prior step's required artifact exists:

1. source page images exist before base grouping is proposed;
2. accepted base grouping exists before clean base generation;
3. approved clean base previews, or unattended-run clean bases, exist before element analysis;
4. `element_analysis.json` exists before SVG or PNG asset generation;
5. generated PNG asset sheets exist before slicing PNG assets;
6. sliced PNG assets and contact sheets exist before text extraction and composition;
7. `texts_layout.json` exists before final PPTX composition;
8. preview images exist before claiming the rebuild is complete.

If an artifact is missing, stop and produce that artifact instead of continuing. If a user asks for a later output directly, still run the required earlier steps first unless they explicitly override the workflow.

Do not infer unattended mode from urgency, page count, an output directory, or a request for a finished PPTX. Unattended mode requires an explicit phrase such as "run unattended", "full automatic run", "no intermediate confirmation", or "不要中途确认". Otherwise, the two base-stage review stops are hard gates.

Generic presentation-generation workflows, PowerPoint libraries, or presentation plugin instructions may help with final PPTX composition only after this skill's required artifacts exist. They must not replace source rendering, base grouping, clean-base generation, element analysis, generated asset sheets, text extraction, or visual QA.

## Parallel Page Reconstruction

Parallel work is allowed only after clean bases are generated and approved. In an unattended full run, skip the approval wait, but still generate clean bases before dispatching page-level subagents.

The lead agent must complete source rendering, base grouping, and clean base generation before dispatching page-level subagents. Do not dispatch page-level subagents before the base images and grouping are ready.

After base approval, the lead agent may assign one subagent per slide, or one subagent per small group of visually similar slides. Each subagent must still follow the workflow for its assigned page. A page subagent may produce only page-level artifacts:

- per-page element analysis,
- per-page text layout,
- per-page geometry specs,
- per-page PNG asset requirements,
- per-page compose entries,
- page-specific QA notes.

Page subagents must not compose the final deck, invent shared components independently, skip element analysis, rasterize normal text, crop icons from source slides, or bypass PNG asset QA.

The lead agent must merge all page-level outputs, deduplicate shared components, normalize categories and naming, generate or reuse shared assets, check for missing pages or missing elements, compose the full PPTX, export previews, and run final visual QA. If a page is incomplete, return that page to the page-level workflow instead of guessing.

## Required Workflow

1. Render or obtain source page images.
   Treat even a PPTX input as visual source pages unless the user explicitly asks to reuse existing PPTX objects. Do not shortcut by deleting existing PPTX objects to create the base.

2. Propose base grouping before extraction.
   Inspect the source page images first, identify likely cover/content/ending/custom base groups, then present a recommended grouping to the user. This is the first hard gate: ask the user to accept or modify the recommendation before generating bases, unless the user explicitly asked for an unattended full run. Do not continue in the same turn after presenting the grouping.

3. Generate clean bases with an image generation/editing model.
   The default base is a general background: keep outer background, edge decoration, ambient texture, and theme visuals; remove all text, icons, cards, boxes, title bars, and central content. Only preserve central layout containers if the user explicitly asks for template containers.

   This is the second hard gate: after generating base preview images, show the bases to the user and wait for approval before extracting elements, unless the user explicitly requested an unattended full run. Do not continue in the same turn after presenting base previews.

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

These are hard gates. After presenting either gate, stop work and wait for the user's next message unless unattended mode was explicitly requested before the gate.

Do not stop after PNG asset generation. Contact sheets and classification summaries are QA artifacts, not approval gates. When the user asks to run all steps automatically, skip only the waiting/approval pauses; still execute every workflow step in order.

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
