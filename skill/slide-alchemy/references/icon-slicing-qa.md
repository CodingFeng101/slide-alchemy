# Icon Slicing QA

## Asset Sheet Rules

PNG asset sheets are only for `icon_png` and `complex_png_whole` components.

Rules:

- Generate the asset sheet with an image generation/editing model before slicing.
- Never crop icon assets directly from the original/source slide image.
- Use a solid key color not present in the icons, often green `#00ff00` or magenta `#ff00ff`.
- Leave large whitespace around each icon.
- Do not draw grid lines.
- Do not place frame, line, star, title bar, or card components in the same sheet.
- Put complex icons one per sheet when they have glow, shadows, or fine edges.

## Cropping Rules

- Preserve transparent padding around each PNG.
- Never crop exactly to the visible bbox.
- After slicing, run `inspect_edges.py`.
- If an icon touches any edge, treat it as suspect.
- If increasing crop padding pulls in neighboring elements, regenerate a cleaner asset sheet instead of accepting pollution.
- If an asset came from a direct crop of the source slide, discard it and generate an asset sheet instead.

## Contact Sheet Rules

Always create contact sheets after slicing.

Check:

- no missing edges,
- no clipped glow/shadow,
- no unrelated frame/line/card fragments,
- no text labels unless the icon is intentionally artistic text,
- transparent padding exists on every side.

## Failure Modes From Prior Runs

- Tight bbox trimming cut round badges and star edges.
- Direct source-slide crops preserved unwanted backgrounds and neighboring slide fragments.
- Mixing cards and blue icons in one sheet made expanded crops pull in red lines and card fragments.
- Simple geometry did not need PNG slicing at all; it should have gone to SVG/OOXML.
