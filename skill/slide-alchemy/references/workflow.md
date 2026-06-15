# Workflow

Every editable-PPTX conversion must run the full workflow. Do not skip steps for small decks, partial decks, quick demos, outputs-only requests, or final-output requests.

Image generation/editing model use is mandatory for clean bases, `icon_png` asset sheets, `complex_png_whole` asset sheets, and regenerated visual assets. Do not replace those steps with local masking, local inpainting, direct source-image crops, copied screenshot fragments, PPT native shape approximations, or generic presentation templates.

Run this workflow in order. Each section produces an artifact that is required by the next section. Do not jump to final PPTX composition until source pages, base grouping, approved or unattended-run bases, element analysis, generated assets, sliced assets, text layout, and compose spec are ready.

If a required artifact is missing, create it before continuing. Do not replace missing artifacts with assumptions.

Do not infer unattended execution from urgency, page count, output-directory requests, or a request for a finished PPTX. The user must explicitly ask to run unattended, run fully automatically, or skip intermediate confirmation.

Generic presentation tooling may be used only for final PPTX composition after this workflow's artifacts exist. Do not let presentation-generation instructions replace slide-alchemy source rendering, base grouping, clean-base generation, element analysis, generated asset sheets, text extraction, or QA.

## Parallel Page Reconstruction

Do not parallelize before source rendering, base grouping, and clean base generation are complete. In an unattended full run, skip approval waits only; all workflow steps still run in order before page-level subagents are dispatched.

After clean bases are approved, the lead agent may dispatch page-level subagents. Each subagent owns one slide, or a small group of similar slides, and produces only intermediate artifacts:

- page element analysis,
- page text layout,
- page geometry specs,
- page PNG asset requirements,
- page compose entries,
- page QA notes.

Page-level subagents must not create the final deck, skip element analysis, crop icons from source slides, rasterize normal text, or create their own incompatible shared component naming.

The lead agent merges all page outputs, deduplicates shared components, normalizes categories, generates or reuses assets, verifies all pages are complete, composes the final PPTX, exports previews, and performs visual QA.

## 1. Source Page Rendering

Render or obtain one image per source page before any base grouping or visual analysis. Treat PPTX, PDF, screenshots, or scanned decks as visual source pages unless the user explicitly asks to reuse existing PPTX objects.

Required output before step 2:

- `source/slide_001.png` style page images,
- source page count,
- source image dimensions.

## 2. Base Grouping

Before image editing, inspect the source page images and propose which pages should share a base:

- one base per page,
- cover/content/ending bases,
- user-specified page groups.

Do not ask a blank question first. Give a concrete recommendation such as:

```text
I recommend:
- base A: page 1 (cover)
- base B: pages 2-8 (content)
- base C: page 9 (ending)

Use this grouping, or tell me which pages should be grouped differently.
```

Read `base-grouping.md` for the inference rules. This is the first hard gate: the user decides whether to accept the recommendation, unless they explicitly asked for an unattended full run. After presenting the grouping, stop and wait for the user's next message.

Required output before step 3:

- source page list,
- proposed and accepted base groups.

## 3. Clean Base Generation

Use the rendered source slide as the edit target. Generate a clean base that keeps the page theme and outer background only.

Use `base-prompt-template.md` unless the user supplies a stronger prompt.

Default removal targets:

- all text and page numbers,
- icons and badges,
- cards, content boxes, title bars, frames,
- central diagrams and decorative content elements.

Default keep targets:

- outer ribbons and edge decoration,
- background gradients and light effects,
- skyline or ambient illustration that belongs to the background,
- technology textures, circuits, or other background motifs,
- large background subject only when it is clearly part of the page theme.

If the generated base keeps card frames or central layout blocks without user approval, regenerate it.

Review stop: after base images are generated, show the base previews and wait for user approval. Do not continue to element extraction until the user approves, unless the user explicitly asked for an unattended full run. After presenting base previews, stop and wait for the user's next message.

Required output before step 4:

- clean base image for each accepted base group,
- user approval or unattended-run instruction.

## 4. Element Analysis

For each page, create `element_analysis.json` before making PNG sheets.

The file should contain:

- `components`: reusable component definitions and category decisions,
- `instances`: per-slide placements with `bbox_px` and `bbox_frac`,
- `png_asset_sheet_plan`: only the components that should become PNGs.

Repeated elements must reference one component.

Run `scripts/validate_element_analysis.py` or validate against `element-analysis.schema.json` before composing.

Required output before step 5:

- `analysis/element_analysis.json`,
- validated component categories,
- `png_asset_sheet_plan` for PNG components.

## 5. Asset Generation

Create SVGs only for simple layout geometry and generated PNGs for semantic icons or complex composites.

PNG sheets must be generated with an image generation/editing model, then sliced. Never crop `icon_png` or `complex_png_whole` assets directly from the original/source slide image. The source slide can be used as a visual reference or edit target, but the deliverable icon assets must come from regenerated asset sheets.

PNG sheets must not mix simple geometry with icons. If a PNG icon is near a frame, line, or card in the sheet, regenerate the sheet with more whitespace or isolate that icon. Do not rebuild semantic icons with native PPT shapes just because they are made of simple lines; use generated PNG unless the user explicitly prioritizes editability over visual fidelity for that icon.

Use `icon-sheet-prompt-template.md` for PNG sheets and `svg-to-ooxml.md` for simple geometry SVG conversion.

After PNG assets are sliced, create contact sheets and summarize the element classification for QA. Do not stop for approval here; continue to text extraction and composition unless a hard QA failure requires regeneration.

Required output before step 6:

- SVG or shape specs for `simple_geometry_svg_ooxml`,
- generated PNG asset sheets for `icon_png` and `complex_png_whole`,
- sliced PNG assets with padding,
- contact sheets and clean edge-touch checks.

## 6. Text Extraction

Use visual extraction by default. Store text separately from visual elements. Do not rasterize normal text into icon assets.

Required output before step 7:

- `analysis/texts_layout.json` with text content, style, and bboxes.

## 7. Compose and QA

Compose in this order:

1. base PNG,
2. editable SVG/OOXML geometry,
3. transparent PNG icons,
4. editable text.

Use `compose-spec.md` and `scripts/compose_component_pptx.py` for deterministic composition when possible.

Export preview PNGs. Use `scripts/compare_preview.py` to build side-by-side and diff images. Do not claim completion until the preview is visually checked.

When something fails, follow `failure-decision-tree.md` before inventing a workaround.

Required final output:

- `out/editable.pptx`,
- preview images,
- comparison images or a visual QA note.
