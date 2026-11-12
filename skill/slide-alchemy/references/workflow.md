# Workflow

Every editable-PPTX conversion must run the full workflow. Do not skip steps for small decks, partial decks, quick demos, outputs-only requests, or final-output requests.

Evaluate every phase against the analyzed components. When zero non-text PNG
components exist, an empty PNG sheet plan completes the generation, slicing and
contact-sheet phases. Text-only pages can have empty `components` and
`instances` collections.

Every slide word remains native editable PowerPoint text, including artistic,
warped, gradient, outlined, extruded and metallic lettering. Preserve actual
characters in text runs, recreate supported effects and approximate unsupported
ones. Record visual differences in QA. Classify separate non-text decorations
independently. Continue to composition and preview to evaluate text fidelity.

Image generation/editing model use is mandatory for clean bases, `icon_png` asset sheets, `complex_png_whole` asset sheets, and regenerated visual assets. Do not replace those steps with local masking, local inpainting, direct source-image crops, copied screenshot fragments, PPT native shape approximations, or generic presentation templates.

Use the runtime's own image tool when it has one. Otherwise run `scripts/generate_image.py`, passing the source page (or an existing sheet) as `--reference` for edits:

```bash
python scripts/generate_image.py @run/prompts/base_A.txt run/base/slide_001_base.png --reference run/source/slide_001.png
python scripts/generate_image.py @run/prompts/icons_sheet_01.txt run/assets/sheets/icons_sheet_01.png --reference run/source/slide_003.png
```

It reads `SLIDE_ALCHEMY_IMAGE_API_KEY` (or `OPENAI_API_KEY`), `SLIDE_ALCHEMY_IMAGE_BASE_URL` (or `OPENAI_BASE_URL`), and `SLIDE_ALCHEMY_IMAGE_MODEL` (default `gpt-image-2`), and falls back to `/chat/completions` on gateways without an images endpoint. Keep prompts in files under `run/prompts/` so each regenerated image can be traced to its prompt.

When regenerating any image asset, remove image noise and high-frequency visual artifacts while preserving all kept linework. Keep colors and brightness unchanged.

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

Page-level subagents must not create the final deck, skip element analysis, crop icons from source slides, rasterize any slide text, or create their own incompatible shared component naming.

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

The generated base must be visually clean: remove noise and high-frequency artifacts from kept background areas, preserve kept linework, and keep colors and brightness unchanged.

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

- clean base image for each accepted base group, with the same aspect ratio as its source pages,
- user approval or unattended-run instruction.

## 4. Element Analysis

For each page, create `element_analysis.json` before making PNG sheets.

The file should contain:

- `components`: reusable component definitions and category decisions,
- `instances`: per-slide placements with `bbox_px` and `bbox_frac`. For PNG components the bbox covers everything the generated asset will contain (a glyph and its backing disc, if the disc is part of the asset), because the composer fits the asset's drawn pixels to it,
- `png_asset_sheet_plan`: only the components that should become PNGs.

Repeated elements must reference one component.

Run `scripts/validate_element_analysis.py` or validate against `element-analysis.schema.json` before composing.

Required output before step 5:

- `analysis/element_analysis.json`,
- validated component categories,
- `png_asset_sheet_plan` for PNG components.

When no PNG components exist, the plan contains a valid `key_color` and
`sheets: []`. PNG image files, crop outputs and contact sheets are then not
applicable, and text extraction can proceed after any required geometry work.

## 5. Asset Generation

Create SVGs only for simple layout geometry and generated PNGs for semantic icons or complex composites.

PNG sheets must be generated with an image generation/editing model, then sliced. Never crop `icon_png` or `complex_png_whole` assets directly from the original/source slide image. The source slide can be used as a visual reference or edit target, but the deliverable icon assets must come from regenerated asset sheets.

Real photographs are the exception: classify them `photo_source_crop` and cut them from the source pages.

```bash
python scripts/crop_source_photos.py run/analysis/element_analysis.json --source-dir run/source --out-dir run/assets/png/photos
```

Each photograph is written as `<instance id>.png`. Place it in the compose spec with the instance bbox and `"fit": "frame"`.

PNG sheets must not mix simple geometry with icons. If a PNG icon is near a frame, line, or card in the sheet, regenerate the sheet with more whitespace or isolate that icon. Do not rebuild semantic icons with native PPT shapes just because they are made of simple lines; use generated PNG unless the user explicitly prioritizes editability over visual fidelity for that icon.

Regenerated PNG sheets must be clean and low-noise. Remove high-frequency visual artifacts, preserve icon linework, and keep colors and brightness unchanged.

Use `icon-sheet-prompt-template.md` for PNG sheets and `svg-to-ooxml.md` for simple geometry SVG conversion.

After PNG assets are sliced, create contact sheets and summarize the element classification for QA. Do not stop for approval here; continue to text extraction and composition unless a hard QA failure requires regeneration.

Required output before step 6:

- SVG or shape specs for `simple_geometry_svg_ooxml`,
- generated PNG asset sheets for any `icon_png` and `complex_png_whole` components,
- sliced PNG assets with padding when PNG components exist,
- contact sheets and clean edge-touch checks when PNG components exist, or a validated empty PNG sheet plan.

## 6. Text Extraction

Run `scripts/extract_text.py` on the source page images. OCR reads the characters, and position, size, colour, weight, bullets, and line spacing are measured from the pixels. Do not use a visual model for text. See `text-extraction.md`.

Font matching and `--rich-text` are enabled by default. The command prepares core and system-font candidates and matches locally. Remote matching is off unless `--remote-match` is passed. An unreachable font server no longer stops the run: cached and installed fonts are used and the skipped downloads are listed on stderr. Progress is printed per text line. See `font-distribution.md` for setup. Preserve `font_matches`, the selected `font_face`, `runs`, and their `effects` in the compose spec. Review entries flagged in `style_report`. A setup failure, empty font shortlist or missing run match stops extraction. Resolve the reported cause before continuing. `--ocr-only` supports explicit measurement analysis.

Text boxes are produced by this command only. Do not hand-write or estimate them when extraction is slow or fails; follow the text section of `failure-decision-tree.md`.

Store all text separately from visual elements as editable text runs, including artistic lettering. Symbols such as arrows and chevrons belong in `element_analysis.json` as editable geometry or suitable non-text assets.

Required output before step 7:

- `analysis/texts_layout.json` with text content, measured style, compose-ready text boxes, ink bboxes, and usable matching records for every visible text run.

## 7. Compose and QA

Compose in this order:

1. base PNG,
2. editable SVG/OOXML geometry,
3. transparent PNG icons,
4. editable text.

Use `compose-spec.md` and `scripts/compose_component_pptx.py` for deterministic composition when possible.

Set `font_matching_required: true` in the reconstruction spec. The composer validates font evidence before saving, and stops when a matched font is not installed, since PowerPoint would substitute it without warning. Install the cached fonts once per machine, then compose:

```bash
python scripts/font_store.py --install-fonts
```

Restart PowerPoint after installing. If the command reports a redirected font folder, compose with `--allow-missing-fonts` and pass the missing font list and this command on to the user. Check matched faces, original bounds and line breaks when text overflows, and rerun measurement before adjusting sizes. Avoid automatic shrinking of source text.

Export preview PNGs. Use `scripts/compare_preview.py` to build side-by-side and diff images. Do not claim completion until the preview is visually checked.

When something fails, follow `failure-decision-tree.md` before inventing a workaround.

Required final output:

- `out/editable.pptx`,
- preview images,
- comparison images or a visual QA note.
