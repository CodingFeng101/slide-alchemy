# Element Classification

## Categories

### Editable text

All slide lettering belongs in `texts_layout.json` as native PowerPoint text
boxes/runs containing editable characters. This includes artistic, gradient,
outlined, warped, extruded and metallic lettering. Recreate supported native
effects and approximate unsupported effects while preserving editable text.
Record residual visual differences in preview QA. Rasterized lettering and
letters converted to vector outlines violate the editable-text requirement.

Classify separate underlines, backing plates and non-text decorations below.
Text-only pages may have empty `components` and `instances`. When no PNG
components exist, use a valid `key_color` with `sheets: []` in the PNG plan.
Proceed through OCR/font matching and composition to evaluate the text result.

### simple_geometry_svg_ooxml

Use only for non-semantic layout geometry that can become editable vector objects:

- straight lines and dividers,
- stars,
- circles and rings,
- rounded rectangles,
- card bases,
- title bars,
- question frames and border frames,
- simple circuit-line decorations.

Generate or describe these as SVG first, then convert/recreate as PPT OOXML objects. Do not use this category for recognizable icons, pictograms, object illustrations, people, devices, badges, buildings, or UI/app symbols. If it represents a thing rather than layout geometry, classify it as PNG even when the drawing is made from simple strokes.

Do not cut true simple geometry as PNG unless the user explicitly wants visual-only fidelity.

### icon_png

Use for standalone illustrative icons:

- trophy,
- flowers,
- book,
- hands and heart,
- computer/code,
- chain link,
- organization/building badge,
- small themed pictograms,
- people or avatars,
- device, app, classroom, cloud, chart, data, security, or building symbols.

Generate these as transparent PNG assets with an image generation/editing model, then slice them from the generated asset sheet. They are editable as movable/scalable images, not internal vector parts. Never crop these assets directly from the original/source slide image.

Default to this category for semantic icons. Do not recreate icons from PPT native shapes just because their source style is flat, outline-only, or visually simple; that usually drifts from the image PPT.

### complex_png_whole

Use for non-text visuals that become worse when split:

- large swirls,
- multi-layer badges,
- glow-heavy decorations,
- complex illustrations,
- non-text compositions with many gradients, shadows, and masks.

Generate as one whole transparent PNG with an image generation/editing model, then slice it from the generated asset sheet. Do not split. Never crop this asset directly from the original/source slide image.

### photo_source_crop

Use only for real photographs: group photos, event and venue shots, portraits,
product or equipment photos, scanned certificates and screenshots of real
documents. Set `asset_plan` to `crop_from_source`.

Crop these from the source page with `scripts/crop_source_photos.py`. Do not
regenerate them. An image model redraws faces, removes the writing on banners
and signs, and leaves key-colour fringes, which turns a record of a real event
into a different picture. Keep photographs off PNG asset sheets.

Record the bbox of the picture area itself. A rounded frame, border or shadow
around the photograph is separate `simple_geometry_svg_ooxml`. Text printed
inside the photograph stays part of the photograph and is not extracted.

Drawn artwork does not belong here. Icons, flat illustrations, 3D renders and
decorative scenes remain `icon_png` or `complex_png_whole`.

## Reuse Rules

- One star component should serve all star instances through copy/scale.
- One card base should serve repeated cards.
- One title bar should serve repeated title bars.
- Left/right variants may be mirrored if visually acceptable.
- Do not generate `card_left`, `card_center`, `card_right` as separate PNGs when they are the same component.

## Common Mistakes To Avoid

- Keeping cards or title bars in the clean base when the user wanted a general base.
- Rebuilding semantic icons as native PPT shapes and losing visual fidelity.
- Putting stars, frames, title bars, and icon PNGs in the same asset sheet.
- Cropping `icon_png` or `complex_png_whole` assets directly from the source slide instead of regenerating them first.
- Regenerating a real photograph instead of classifying it `photo_source_crop`.
- Cropping icon assets tightly to their nontransparent bbox.
- Splitting a complex decorative composition into many pieces that cannot be reassembled cleanly.
- Classifying any slide lettering as a PNG component or replacing editable characters with vector outlines.
