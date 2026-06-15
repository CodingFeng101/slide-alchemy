# Icon Sheet Prompt Template

Use this template only for components classified as `icon_png` or `complex_png_whole`. This image generation/editing model step is mandatory for PNG icon and complex visual assets; do not replace it with direct crops from the source slide or PPT native shape approximations.

```text
Use the displayed slide image only as the visual reference/edit target. Regenerate these PNG icon assets into a new asset sheet; do not crop or paste pixels directly from the source slide:
<list icon ids and descriptions>

Make one 16:9 asset sheet with solid key-color background <#00ff00 or #ff00ff>.
Do not include any normal text, labels, page numbers, grid lines, frames, title bars, card boxes, stars, simple lines, or other simple geometry.
Each icon must have large empty space on all sides. Icons must not touch each other.
Preserve the original icon style, colors, highlights, shadows, and proportions.
For complex composite icons, place each whole composite as one isolated asset; do not split it.
Output only the asset sheet, not the slide background.
```

Hard limits:

- Put at most 6 simple icons on one sheet.
- Put at most 3 detailed icons on one sheet.
- Put one complex composite icon per sheet when it has glow, transparency, or many nested details.

If an asset sheet causes polluted crops, regenerate the sheet with fewer icons instead of trying to rescue it with tighter crops.

Never use this prompt to request direct crops from the source slide. Source crops are forbidden for `icon_png` and `complex_png_whole`; only generated asset sheets may be sliced.
