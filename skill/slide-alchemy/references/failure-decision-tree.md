# Failure Decision Tree

## Base Problems

If the base still contains cards, title bars, central frames, icons, or text:

1. Regenerate the base with `base-prompt-template.md`.
2. Explicitly list the unwanted retained objects.
3. Do not hide the problem by covering it with white boxes.

If the base removes important outer decoration:

1. Regenerate and explicitly list what to keep.
2. Keep central content removal unchanged.

## Icon Sheet Problems

If an icon asset was cropped directly from the original/source slide:

1. Discard the crop.
2. Generate a new solid-key asset sheet with an image generation/editing model.
3. Slice the regenerated asset with transparent padding.

If an icon touches a crop edge:

1. Recrop with more padding.
2. If padding pulls in neighboring objects, regenerate the asset sheet with more spacing or fewer icons.

If an icon crop contains red lines, card fragments, text, or other neighbors:

1. Do not manually erase fragments.
2. Regenerate the asset sheet with only PNG icons.
3. Put complex icons one per sheet if needed.

If a simple shape is being sliced as PNG:

1. Reclassify it as `simple_geometry_svg_ooxml`.
2. Rebuild it as editable geometry.

If a recognizable icon was rebuilt as PPT native geometry and no longer matches the source:

1. Reclassify it as `icon_png` or `complex_png_whole`.
2. Regenerate it on a solid-key asset sheet with the image generation/editing model.
3. Slice it with transparent padding and update the compose spec placement.

## SVG / OOXML Problems

If `simple_svg_to_pptx.py` cannot represent a component:

1. Simplify the SVG to the supported subset.
2. If it still cannot convert, use ppt-master's full SVG pipeline when available.
3. If fidelity matters more than editability, reclassify as `complex_png_whole`.

Do not claim arbitrary SVG path conversion works unless verified in a generated PPTX.

## Text Problems

If text overflows:

1. Reduce font size.
2. Adjust line breaks and line spacing.
3. Then adjust bbox.

If text position is wrong:

1. Check the source bbox coordinate system.
2. Verify `ref_width` and `ref_height`.
3. Re-export preview and compare visually.

If the visual model misreads content:

1. Re-extract that text region only.
2. Do not rasterize normal text as an icon.

## Preview QA Problems

If source and preview differ:

1. Fix missing or duplicated objects first.
2. Fix icon crop quality second.
3. Fix text size and line breaks third.
4. Fix minor color/position drift last.
