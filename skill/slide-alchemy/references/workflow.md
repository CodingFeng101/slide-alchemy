# Workflow

## 1. Base Grouping

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

Read `base-grouping.md` for the inference rules. This is the first allowed stop: the user decides whether to accept the recommendation, unless they asked for an unattended full run.

## 2. Clean Base Generation

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

Review stop: after base images are generated, show the base previews and wait for user approval. Do not continue to element extraction until the user approves, unless the user asked for an unattended full run.

## 3. Element Analysis

For each page, create `element_analysis.json` before making PNG sheets.

The file should contain:

- `components`: reusable component definitions and category decisions,
- `instances`: per-slide placements with `bbox_px` and `bbox_frac`,
- `png_asset_sheet_plan`: only the components that should become PNGs.

Repeated elements must reference one component.

Run `scripts/validate_element_analysis.py` or validate against `element-analysis.schema.json` before composing.

## 4. Asset Generation

Create SVGs only for simple layout geometry and generated PNGs for semantic icons or complex composites.

PNG sheets must be generated with an image generation/editing model, then sliced. Never crop `icon_png` or `complex_png_whole` assets directly from the original/source slide image. The source slide can be used as a visual reference or edit target, but the deliverable icon assets must come from regenerated asset sheets.

PNG sheets must not mix simple geometry with icons. If a PNG icon is near a frame, line, or card in the sheet, regenerate the sheet with more whitespace or isolate that icon. Do not rebuild semantic icons with native PPT shapes just because they are made of simple lines; use generated PNG unless the user explicitly prioritizes editability over visual fidelity for that icon.

Use `icon-sheet-prompt-template.md` for PNG sheets and `svg-to-ooxml.md` for simple geometry SVG conversion.

After PNG assets are sliced, create contact sheets and summarize the element classification for QA. Do not stop for approval here; continue to text extraction and composition unless a hard QA failure requires regeneration.

## 5. Text Extraction

Use visual extraction by default. Store text separately from visual elements. Do not rasterize normal text into icon assets.

## 6. Compose and QA

Compose in this order:

1. base PNG,
2. editable SVG/OOXML geometry,
3. transparent PNG icons,
4. editable text.

Use `compose-spec.md` and `scripts/compose_component_pptx.py` for deterministic composition when possible.

Export preview PNGs. Use `scripts/compare_preview.py` to build side-by-side and diff images. Do not claim completion until the preview is visually checked.

When something fails, follow `failure-decision-tree.md` before inventing a workaround.
