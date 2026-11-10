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

Every slide word must remain native editable PowerPoint text, including artistic,
outlined, gradient, warped, extruded and metallic lettering. Preserve the actual
characters in text boxes/runs. PNG lettering and glyph outlines converted to
vector shapes violate this requirement. Recreate supported effects as native
text properties. Approximate unsupported effects while keeping the characters
editable, then disclose the visual difference in preview QA.

Any request to convert slides into an editable PPTX must run the complete workflow. Do not use a shortcut path for small decks, first pages only, quick demos, outputs-only requests, or final-PPTX requests. The workflow is mandatory even when the user asks for only one page.

The following steps must always happen in order:

1. source page rendering,
2. base grouping,
3. clean base generation with an image generation/editing model,
4. element analysis,
5. SVG/OOXML generation for true layout geometry,
6. PNG asset sheet generation with an image generation/editing model when non-text PNG components are present,
7. PNG slicing and contact-sheet QA when PNG components are present,
8. OCR text extraction with pixel measurement,
9. PPTX composition,
10. preview export and visual QA.

Image generation/editing model use is mandatory for:

- clean base backgrounds;
- `icon_png` asset sheets;
- `complex_png_whole` asset sheets;
- any regenerated visual asset that must match the image PPT.

Text effects follow the editable text path. Classify separate backing plates,
underlines and other non-text decorations independently. When element analysis
finds zero PNG components, record an empty sheet plan and continue to OCR/font
matching, composition and preview. Unsupported text effects require an editable
approximation and a QA note. They are insufficient grounds to abandon the page
before trying the available text pipeline.

Use the runtime's own image generation/editing tool when it has one, as Codex does. When it has none, as in Claude Code, run `scripts/generate_image.py`: it sends the prompt, plus the source page as `--reference` for edits, to an OpenAI-compatible Images API configured by `SLIDE_ALCHEMY_IMAGE_API_KEY`, `SLIDE_ALCHEMY_IMAGE_BASE_URL`, and `SLIDE_ALCHEMY_IMAGE_MODEL`. If neither is available, stop and tell the user how to configure the script; do not fall back to any of the replacements forbidden below.

Every regenerated image asset must remove image noise and high-frequency visual artifacts while preserving all kept linework. Colors and brightness must remain unchanged.

Do not replace those model steps with local white masks, local inpainting, direct source-image crops, copied screenshot fragments, PPT native shape approximations, or generic presentation templates.

## Execution Discipline

Follow the workflow in order. Do not skip ahead, merge phases, or compose the final PPTX before required upstream artifacts exist.

Before starting each step, check that the prior step's required artifact exists:

1. source page images exist before base grouping is proposed;
2. accepted base grouping exists before clean base generation;
3. approved clean base previews, or unattended-run clean bases, exist before element analysis;
4. `element_analysis.json` exists before SVG or PNG asset generation;
5. when PNG components exist, generated PNG asset sheets exist before slicing them;
6. when PNG components exist, sliced PNG assets and contact sheets exist before text extraction and composition. A validated element analysis with zero PNG components and an empty sheet plan satisfies this phase for other pages;
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

Page subagents must not compose the final deck, invent shared components independently, skip element analysis, rasterize any slide text, crop icons from source slides, or bypass PNG asset QA.

The lead agent must merge all page-level outputs, deduplicate shared components, normalize categories and naming, generate or reuse shared assets, check for missing pages or missing elements, compose the full PPTX, export previews, and run final visual QA. If a page is incomplete, return that page to the page-level workflow instead of guessing.

## Required Workflow

1. Render or obtain source page images.
   Treat even a PPTX input as visual source pages unless the user explicitly asks to reuse existing PPTX objects. Do not shortcut by deleting existing PPTX objects to create the base.

2. Propose base grouping before extraction.
   Inspect the source page images first, identify likely cover/content/ending/custom base groups, then present a recommended grouping to the user. This is the first hard gate: ask the user to accept or modify the recommendation before generating bases, unless the user explicitly asked for an unattended full run. Do not continue in the same turn after presenting the grouping.

3. Generate clean bases with an image generation/editing model.
   The default base is a general background: keep outer background, edge decoration, ambient texture, and theme visuals; remove all text, icons, cards, boxes, title bars, and central content. Remove image noise and high-frequency visual artifacts from kept areas while preserving kept linework, colors, and brightness. Only preserve central layout containers if the user explicitly asks for template containers. The base must keep the source page's aspect ratio; regenerate it if it does not, and never stretch it to fit.

   This is the second hard gate: after generating base preview images, show the bases to the user and wait for approval before extracting elements, unless the user explicitly requested an unattended full run. Do not continue in the same turn after presenting base previews.

4. Analyze every non-text visual element before slicing.
   Create `element_analysis.json` with reusable components and per-slide instances. Do not put all elements into an icon sheet first.

   Keep all lettering and text effects in `texts_layout.json`. Text-only pages can have `components: {}` and per-slide `instances: []`. Pages containing text and backing geometry list only that non-text geometry here. If no PNG components are needed, use `png_asset_sheet_plan` with a valid `key_color` and `sheets: []`.

5. Classify each element:
   - `simple_geometry_svg_ooxml`: non-semantic layout geometry such as straight lines, dividers, stars, circles, rings, rounded rectangles, card bases, title bars, simple borders, and simple circuit-line decorations. Generate SVG first, then convert or recreate as editable OOXML/PPT shapes.
   - `icon_png`: standalone illustrative or semantic icons such as trophies, flowers, books, hands/heart, computer, chain link, organization badges, app pictograms, people, devices, buildings, or any recognizable object icon. Even if an icon looks like simple line art, keep it as generated PNG unless it is just a primitive layout shape.
   - `complex_png_whole`: complex non-text composite visuals that would look worse if split, such as swirls, layered badges, glow assemblies and illustrations. Generate as one PNG and do not split. All lettering follows the editable text path.

   Validate the result against `references/element-analysis.schema.json` when practical.

6. Reuse repeated components.
   Generate one star and copy/scale it. Generate one card base and one title bar and reuse them. Do not generate separate PNGs for repeated simple geometry.

7. Generate PNG asset sheets only for PNG categories.
   Keep `simple_geometry_svg_ooxml` elements out of PNG sheets. Choose one high-contrast solid key color for the run and reuse that exact color on every PNG sheet and crop spec. Pack `icon_png` assets 9 per sheet in a 3x3 layout and `complex_png_whole` assets 4 per sheet in a 2x2 layout; only the final sheet of each category may contain fewer assets. Remove noise and high-frequency visual artifacts from regenerated PNG assets while preserving icon linework, colors, and brightness. Never crop `icon_png` or `complex_png_whole` assets directly from the original/source slide image; the source slide is only a visual reference or edit target for regeneration.

8. Slice PNG assets conservatively.
   Preserve padding around every transparent PNG. Run edge-touch checks and create contact sheets. If any icon touches a crop edge, is truncated, or includes neighboring elements, regenerate the sheet or recrop with more space.

   Do not stop for approval after generating assets. Continue to text extraction and composition after edge checks and contact sheets are ready.

9. Extract text with OCR and pixel measurement.
   Run `scripts/extract_text.py` on the source page images to write `texts_layout.json`. OCR reads the characters. Position, font size, colour, weight, bullets, and paragraph line merging are measured from the pixels. Do not use a visual model to read text or estimate text boxes, because its coordinates are approximations. Copy each text's `bbox_px`/`bbox_frac`, style fields, and `line_spacing_pt` into the compose spec unchanged. If bold is wrong for a template, calibrate `--bold-mode ratio:<value>` from the recorded `metrics` instead of editing weights one by one. PPTX XML text may be passed with `--expected` to correct near-miss readings.

   Font matching and mixed-style extraction are enabled by default. Read `references/font-distribution.md` for cache setup and server details. The standard command is `python scripts/extract_text.py run/source/slide_*.png --out run/analysis/texts_layout.json`. It prepares the core pack, scans installed fonts, matches locally, and expands poor matches through the remote library. Every visible text run must have a nonempty `font_matches` candidate record. Review low-confidence matches before composition. If setup or matching fails, stop and report the cause. `--ocr-only` is an explicit measurement-analysis mode. Reconstruction requires matching results.

10. Compose the final PPTX in this layer order:
    base PNG -> SVG/OOXML editable geometry -> PNG icons -> editable text boxes.
    Use `scripts/compose_component_pptx.py` with a compose spec when possible; do not rewrite ad hoc composition logic for every task.
    Set `font_matching_required: true` in the reconstruction compose spec. Preserve each OCR text record's `font_matches`, `font_face`, `runs`, and `style_report`. Composition checks the selected face and weight against the matching evidence and stops on missing results or conflicting styles. For text overflow, check the matched face, source bounds, line breaks and size estimates, then rerun matching or measurement. Avoid automatic font shrinking as an overflow repair.
    Give each PNG image the drawing's own bbox from `element_analysis.json`; the default `fit: visible` aligns the PNG's drawn pixels to it and lets the transparent padding fall outside. Leave `slide_height_in` out so the slide follows the source page's aspect ratio. Record `corner_radius_px` for rounded cards.

11. Export previews and QA visually.
    Ensure the selected font faces are installed in the environment rendering the preview and check PowerPoint's rendered text against the source.
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
  prompts/
  base/
    slide_001_base.png
  analysis/
    element_analysis.json
    texts_layout.json
    compose_spec.json
  assets/
    svg/
    sheets/
    crop_specs/
    png/
    contact_sheets/
  out/
    editable.pptx
    preview/
    compare/
```

## References

Read only the relevant reference before acting:

- `references/workflow.md`: detailed end-to-end sequence and required artifacts.
- `references/element-classification.md`: classification rules, reuse rules, and common traps.
- `references/icon-slicing-qa.md`: PNG asset sheet, chroma key, padding, edge-touch, and contact sheet rules.
- `references/text-extraction.md`: OCR text extraction command, schema, measurement method, and bold calibration.
- `references/font-distribution.md`: core font cache, remote expansion, release catalog, and installation commands.
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

- `scripts/generate_image.py`: generate an image, or edit one given `--reference`, through an OpenAI-compatible Images API when the runtime has no image tool. Pass long prompts as `@prompt.txt`.
- `scripts/inspect_edges.py`: report transparent PNGs that touch crop edges.
- `scripts/build_contact_sheet.py`: make contact sheets for sliced PNG assets.
- `scripts/slice_asset_sheet.py`: slice a solid-key asset sheet from a JSON crop spec while preserving padding.
- `scripts/simple_svg_to_pptx.py`: convert simple component SVG primitives into editable PPTX shapes for quick validation or component reuse.
- `scripts/validate_element_analysis.py`: lightweight validation for `element_analysis.json` without external dependencies.
- `scripts/extract_text.py`: OCR the source pages and measure text position, size, colour, weight, bullets, and line spacing into `texts_layout.json`.
- `scripts/font_store.py`: install the checked core font pack and cache selected remote matches.
- `scripts/serve_fonts.py`: serve the expanded font matcher behind Nginx.
- `scripts/compose_component_pptx.py`: compose base images, editable shapes, PNG assets, and editable text into a PPTX from JSON.
- `scripts/compare_preview.py`: create side-by-side and difference images from source/preview PNGs.
