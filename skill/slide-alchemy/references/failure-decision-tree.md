# Failure Decision Tree

This document provides remediation guidance when a workflow step fails or produces unsatisfactory results. Follow the decision tree for the failing step to determine the correct course of action.

---

## Base Problems

### Base still contains visible text, icons, cards, title bars, or central content

1. Regenerate the base with a more explicit prompt listing the unwanted retained objects by name.
2. If the second attempt still has remnants, switch to generating the base from a text description of the background instead of editing the source image.
3. If remnants persist, split the page into multiple base regions with simpler content per region and regenerate each region.
4. Do NOT hide the problem by covering it with white boxes, solid fills, or local masks. Regeneration is the only acceptable fix.

### Base removes important outer decoration or edge elements

1. Regenerate and explicitly list what to keep (e.g., "Preserve the decorative border on the left side and the accent line at the bottom").
2. Keep central content removal unchanged.
3. If decorative elements are consistently lost, consider moving them to `simple_geometry_svg_ooxml` instead of relying on the base image.

### Base colors or gradients do not match the source

1. Include explicit color references in the prompt (e.g., "Preserve the exact teal-to-navy gradient (#00B4D8 to #1B263B) on the left half").
2. If the model cannot match colors, consider splitting the page into multiple base regions with simpler gradients.

---

## Element Analysis Problems

### `validate_element_analysis.py` reports errors

1. Read the error messages from the validator.
2. Fix the reported fields in `element_analysis.json`.
3. Re-run the validator. Repeat until no errors remain.
4. If the validator itself has a bug, report it as an issue.

### Elements misclassified between categories

Common misclassifications:
- A simple icon (e.g., a star) classified as `icon_png` instead of `simple_geometry_svg_ooxml`.
- A complex gradient card classified as `simple_geometry_svg_ooxml` instead of `complex_png_whole`.
- A semantic icon (e.g., a trophy) forced into `simple_geometry_svg_ooxml`.

Remediation:
1. Apply the core judgment rule: "If an element can be described by outline, fill color, and stroke alone, it is `simple_geometry_svg_ooxml`. If it depends on texture, lighting, gradients, or fine detail stacking, it is a PNG category."
2. When in doubt, classify semantic icons as `icon_png` (they are more stable as generated PNGs).
3. Update `element_analysis.json` and re-validate.

### Duplicate components not detected

1. Group elements by visual similarity rather than exact bounding-box match.
2. Create one component definition and reference it from multiple per-slide instances with appropriate position and scale transforms.

---

## Icon Sheet Problems

### Icon asset was cropped directly from the original/source slide

1. Discard the crop.
2. Generate a new solid-key asset sheet with an image generation/editing model.
3. Slice the regenerated asset with transparent padding.

### Icon touches a crop edge

1. Recrop with more padding (add 8-16px on each side).
2. If padding pulls in neighboring objects, regenerate the asset sheet with more spacing or fewer icons per sheet.

### Icon crop contains red lines, card fragments, text, or other neighbors

1. Do NOT manually erase fragments.
2. Regenerate the asset sheet with only PNG icons.
3. Put complex icons one per sheet if needed.

### Generated icon does not match the source icon

1. Regenerate with a more specific prompt describing the exact style, proportions, and color.
2. If the icon consistently differs, try generating at a larger size and scaling down.
3. For critical icons where visual fidelity is paramount, consider using the source icon as an image-editing reference rather than generating from scratch.

### Asset sheet has poor contrast or key-color bleeding

1. Use a key color that maximizes contrast with all icon colors (pure magenta #FF00FF or pure green #00FF00 are common choices).
2. Regenerate with explicit instructions: "Generate the icon on a pure magenta (#FF00FF) background. Do not blend the background color into the icon edges."
3. If bleeding persists, increase the padding around the icon in the asset sheet.

### A simple shape is being sliced as PNG

1. Reclassify it as `simple_geometry_svg_ooxml`.
2. Rebuild it as editable geometry.

### A recognizable icon was rebuilt as PPT native geometry and no longer matches the source

1. Reclassify it as `icon_png` or `complex_png_whole`.
2. Regenerate it on a solid-key asset sheet with the image generation/editing model.
3. Slice it with transparent padding and update the compose spec placement.

---

## SVG / OOXML Problems

### SVG does not render correctly in PowerPoint

Common causes: Use of `<mask>`, `<style>` with CSS classes, `foreignObject`, external `<use>` references, or non-standard fonts.

Remediation:
1. Replace all `<style>` blocks with inline `style` attributes.
2. Convert CSS classes to direct attribute values.
3. Remove `<mask>` and replace with solid fills or opacity-based workarounds.
4. Replace `foreignObject` text with SVG `<text>` elements.
5. Inline any `<use>` references that point to external resources.
6. Use standard font families (Arial, Calibri, etc.) or font names that exist in the target system.

### SVG shapes are misaligned or incorrectly sized in PPTX

1. Verify the conversion uses the correct scale factor: 1 px = 914400 / 96 EMU.
2. Check that `viewBox` coordinates are correctly mapped to the PPTX canvas dimensions.
3. Use `scripts/simple_svg_to_pptx.py` for validation on a single element before batch conversion.

### `simple_svg_to_pptx.py` cannot represent a component

1. Simplify the SVG to the supported subset.
2. If it still cannot convert, use ppt-master's full SVG pipeline when available.
3. If fidelity matters more than editability, reclassify as `complex_png_whole`.

Do not claim arbitrary SVG path conversion works unless verified in a generated PPTX.

---

## Text Problems

### Text overflows its bounding box

1. Reduce font size.
2. Adjust line breaks and line spacing.
3. Then adjust bbox.

### Text position is wrong

1. Check the source bbox coordinate system.
2. Verify `ref_width` and `ref_height`.
3. Re-export preview and compare visually.

### Visual model misreads content

1. Re-extract that text region only.
2. Do not rasterize normal text as an icon.

### Extracted text is incorrect or incomplete

1. Cross-reference with PPTX XML if available (some source files embed extractable text).
2. Re-extract with a focused prompt: "Extract every visible text string from this slide image, including small labels and captions. Preserve line breaks and approximate font sizes."
3. For CJK text, ensure the model supports the target language and script.

---

## PPTX Composition Problems

### Elements overlap incorrectly in the final PPTX

1. Verify the composition follows the correct layer order: base PNG (bottom) -> SVG/OOXML geometry -> PNG icons -> text boxes (top).
2. Check `scripts/compose_component_pptx.py` compose spec for correct `z_order` values.
3. If using ad hoc composition, ensure each element is added in the correct sequence.

### Final PPTX file size is unexpectedly large

1. Verify that shared components reference the same image file rather than embedding duplicates.
2. Check that PNG assets are not saved at unnecessarily high resolution.
3. Compress base images with reasonable quality settings if file size is critical.

---

## Preview QA Problems

### Source and preview differ

Priority order for fixes:
1. Fix missing or duplicated objects first.
2. Fix icon crop quality second.
3. Fix text size and line breaks third.
4. Fix minor color/position drift last.

### Preview shows missing elements compared to source

1. Re-examine the source page and the element analysis for the affected slide.
2. If an element was missed, add it to `element_analysis.json`, generate the appropriate asset, and re-compose the slide.
3. If the asset was generated but not placed, check the compose spec for the missing entry.

### Preview shows visual artifacts not in the source

1. Use `scripts/compare_preview.py` to generate difference images.
2. Identify the artifact source (base generation, icon generation, or slicing).
3. Follow the relevant failure tree above for the identified source.
4. Regenerate the problematic asset and re-compose the affected slide.

---

## Escalation

If you have followed the relevant decision tree and the issue persists:

1. Document the failure: which step, what was expected, what was produced, what remediation was attempted.
2. Check GitHub Issues for similar problems.
3. Open a new issue with the documented failure information.
4. If the workflow is completely blocked, the user may need to manually adjust the output PPTX. This is expected for complex or heavily decorated slides.
