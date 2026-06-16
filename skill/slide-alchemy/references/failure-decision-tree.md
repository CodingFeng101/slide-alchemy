# Failure Decision Tree

This document provides remediation guidance when a workflow step fails or produces unsatisfactory results. Follow the decision tree for the failing step to determine the correct course of action.

---

## Clean Base Generation Failures

### Problem: Base still contains visible text or icons

- **Cause**: The image generation model did not fully remove content elements.
- **Remediation**:
  1. Regenerate with a more explicit prompt: "Remove ALL text, ALL icons, ALL cards. Keep only the background gradient, decorative edge elements, and ambient texture."
  2. If the second attempt still has remnants, try generating the base from a text description of the background instead of editing the source image.
  3. As a last resort, manually mask the remaining content with a solid fill matching the surrounding area. Document this fallback in QA notes.

### Problem: Base loses important decorative elements

- **Cause**: The model was too aggressive in removing content.
- **Remediation**:
  1. Regenerate with a more specific prompt: "Preserve the decorative border on the left side and the accent line at the bottom."
  2. If decorative elements are consistently lost, consider moving them to `simple_geometry_svg_ooxml` instead of relying on the base image.

### Problem: Base colors or gradients do not match the source

- **Cause**: The image model shifted the color palette during editing.
- **Remediation**:
  1. Include explicit color references in the prompt: "Preserve the exact teal-to-navy gradient (#00B4D8 to #1B263B) on the left half."
  2. If the model cannot match colors, consider splitting the page into multiple base regions with simpler gradients.

---

## Element Analysis Failures

### Problem: `validate_element_analysis.py` reports errors

- **Cause**: Missing required fields, invalid categories, or inconsistent component IDs.
- **Remediation**:
  1. Read the error messages from the validator.
  2. Fix the reported fields in `element_analysis.json`.
  3. Re-run the validator. Repeat until no errors remain.
  4. If the validator itself has a bug, report it as an issue.

### Problem: Elements misclassified between categories

- **Common misclassifications**:
  - A simple icon (e.g., a star) classified as `icon_png` instead of `simple_geometry_svg_ooxml`.
  - A complex gradient card classified as `simple_geometry_svg_ooxml` instead of `complex_png_whole`.
  - A semantic icon (e.g., a trophy) forced into `simple_geometry_svg_ooxml`.
- **Remediation**:
  1. Apply the core judgment rule: "If an element can be described by outline, fill color, and stroke alone, it is `simple_geometry_svg_ooxml`. If it depends on texture, lighting, gradients, or fine detail stacking, it is a PNG category."
  2. When in doubt, classify semantic icons as `icon_png` (they are more stable as generated PNGs).
  3. Update `element_analysis.json` and re-validate.

### Problem: Duplicate components not detected

- **Cause**: Slightly different bounding boxes or visual sizes for the same icon prevent deduplication.
- **Remediation**:
  1. Group elements by visual similarity rather than exact bounding-box match.
  2. Create one component definition and reference it from multiple per-slide instances with appropriate position and scale transforms.

---

## SVG/OOXML Conversion Failures

### Problem: SVG does not render correctly in PowerPoint

- **Common causes**: Use of `<mask>`, `<style>` with CSS classes, `foreignObject`, external `<use>` references, or non-standard fonts.
- **Remediation**:
  1. Replace all `<style>` blocks with inline `style` attributes.
  2. Convert CSS classes to direct attribute values.
  3. Remove `<mask>` and replace with solid fills or opacity-based workarounds.
  4. Replace `foreignObject` text with SVG `<text>` elements.
  5. Inline any `<use>` references that point to external resources.
  6. Use standard font families (Arial, Calibri, etc.) or font names that exist in the target system.

### Problem: SVG shapes are misaligned or incorrectly sized in PPTX

- **Cause**: Coordinate system mismatch between SVG (pixel-based) and OOXML (EMU-based).
- **Remediation**:
  1. Verify the conversion uses the correct scale factor: 1 px = 914400 / 96 EMU.
  2. Check that `viewBox` coordinates are correctly mapped to the PPTX canvas dimensions.
  3. Use `scripts/simple_svg_to_pptx.py` for validation on a single element before batch conversion.

---

## PNG Asset Generation Failures

### Problem: Generated icon does not match the source icon

- **Cause**: The image model produced a stylistically different icon.
- **Remediation**:
  1. Regenerate with a more specific prompt: "Recreate this exact icon: a line-art trophy in teal on a white background. Match the style, proportions, and color of the original."
  2. If the icon consistently differs, try generating at a larger size and scaling down.
  3. For critical icons where visual fidelity is paramount, consider using the source icon as an image-editing reference rather than generating from scratch.

### Problem: Asset sheet has poor contrast or key-color bleeding

- **Cause**: The key-color background is too close to icon colors, or the model blended the key color into the icon edges.
- **Remediation**:
  1. Use a key color that maximizes contrast with all icon colors (pure magenta #FF00FF or pure green #00FF00 are common choices).
  2. Regenerate with explicit instructions: "Generate the icon on a pure magenta (#FF00FF) background. Do not blend the background color into the icon edges."
  3. If bleeding persists, increase the padding around the icon in the asset sheet.

### Problem: Sliced icon is truncated or includes neighboring elements

- **Cause**: Crop coordinates are too tight or misaligned.
- **Remediation**:
  1. Run `scripts/inspect_edges.py` to detect edge-touch issues.
  2. Re-crop with increased padding (add 8-16px on each side).
  3. If the neighboring element is from the same asset sheet, recrop with a more generous bounding box.
  4. If the neighboring element is a different icon, regenerate with more spacing between icons on the sheet.

---

## Text Extraction Failures

### Problem: Extracted text is incorrect or incomplete

- **Cause**: The visual model misread characters, missed small text, or confused decorative text with content text.
- **Remediation**:
  1. Cross-reference with PPTX XML if available (some source files embed extractable text).
  2. Re-extract with a focused prompt: "Extract every visible text string from this slide image, including small labels and captions. Preserve line breaks and approximate font sizes."
  3. For CJK text, ensure the model supports the target language and script.

### Problem: Text positioning is significantly off in the final PPTX

- **Cause**: Bounding box coordinates from visual extraction are approximate.
- **Remediation**:
  1. If the source is a PPTX file, parse the XML for exact text positions as a cross-check.
  2. For image-only sources, accept approximate positioning and note that manual adjustment may be needed.
  3. Align text boxes to the nearest logical anchor point (e.g., center of a card, top of a title bar) rather than absolute pixel coordinates.

---

## PPTX Composition Failures

### Problem: Elements overlap incorrectly in the final PPTX

- **Cause**: Layer order or z-index mismatch.
- **Remediation**:
  1. Verify the composition follows the correct layer order: base PNG (bottom) -> SVG/OOXML geometry -> PNG icons -> text boxes (top).
  2. Check `scripts/compose_component_pptx.py` compose spec for correct `z_order` values.
  3. If using ad hoc composition, ensure each element is added in the correct sequence.

### Problem: Final PPTX file size is unexpectedly large

- **Cause**: Uncompressed PNG images or redundant asset copies.
- **Remediation**:
  1. Verify that shared components reference the same image file rather than embedding duplicates.
  2. Check that PNG assets are not saved at unnecessarily high resolution.
  3. Compress base images with reasonable quality settings if file size is critical.

---

## Visual QA Failures

### Problem: Preview shows missing elements compared to source

- **Cause**: An element was not classified in the analysis, or its asset was not generated.
- **Remediation**:
  1. Re-examine the source page and the element analysis for the affected slide.
  2. If an element was missed, add it to `element_analysis.json`, generate the appropriate asset, and re-compose the slide.
  3. If the asset was generated but not placed, check the compose spec for the missing entry.

### Problem: Preview shows visual artifacts not in the source

- **Cause**: Key-color residue, inpainting artifacts, or misaligned crops.
- **Remediation**:
  1. Use `scripts/compare_preview.py` to generate difference images.
  2. Identify the artifact source (base generation, icon generation, or slicing).
  3. Follow the relevant failure tree above for the identified source.
  4. Regenerate the problematic asset and re-compose the affected slide.

### Problem: Colors in the preview do not match the source

- **Cause**: Color space conversion issues, or the image model shifted colors during generation.
- **Remediation**:
  1. Check if the source uses CMYK colors that were converted to RGB with the wrong profile.
  2. If the base or icon generation shifted colors, regenerate with explicit color values in the prompt.
  3. For small color discrepancies, accept the variance and note it in QA. Perfect color matching is not always achievable with generative models.

---

## Escalation

If you have followed the relevant decision tree and the issue persists:

1. Document the failure: which step, what was expected, what was produced, what remediation was attempted.
2. Check GitHub Issues for similar problems.
3. Open a new issue with the documented failure information.
4. If the workflow is completely blocked, the user may need to manually adjust the output PPTX. This is expected for complex or heavily decorated slides.
