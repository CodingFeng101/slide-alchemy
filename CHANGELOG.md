# Changelog

This file records the notable changes in each Slide Alchemy release.

## [0.2.0] - 2026-07-10

Compared with `v0.1.0`, this release focuses on safer inputs, reproducible asset slicing, stricter QA, and clearer failure recovery.

### Reliability and validation

- Validate required fields, types, positive dimensions, bounding boxes, and component references in `element_analysis.json`.
- Reject unsafe or empty crop IDs and prevent crop output paths from escaping the selected output directory.
- Reject invalid contact-sheet dimensions and column counts.
- Make the default `unittest` discovery command run the bundled regression suite.

### SVG conversion

- Correctly map SVGs whose `viewBox` starts at a non-zero origin.
- Reject non-positive SVG and slide dimensions.
- Fail clearly on unsupported visible SVG elements instead of silently producing incomplete PPTX output.

### Asset slicing and QA

- Allow crop specs to store their key color while remaining compatible with the original crop-array format and CLI overrides.
- Store the magenta key color in all bundled strict-run crop specs, so the example sheets can be reproduced without extra arguments.
- Recursively inspect PNG assets and build contact sheets from nested directories.
- Fail asset QA when no PNG files are found instead of reporting a false success.

### Recovery guidance

- Expand the failure decision tree with concrete recovery steps for base generation, element classification, asset sheets, SVG conversion, text layout, PPTX composition, and preview QA.

### Tests

- Add regression coverage for SVG coordinate mapping, unsupported SVG elements, element-analysis validation, nested and empty asset directories, and crop-spec key colors.

## [0.1.0]

- Initial public workflow for rebuilding image-based slides into editable, component-based PPTX files.
