# Slide Alchemy

<p align="center">
  <strong>🧪 Reforge image-based slides into</strong><br>
  <span style="font-size: 42px; color: #ff2d2d; font-weight: 900;">FULLY FULLY</span><br>
  <strong>editable, component-based PowerPoint decks.</strong>
</p>

Slide Alchemy is a Codex skill for rebuilding picture-style PPT/PPTX files, slide screenshots, and scanned visual decks into editable `.pptx` files. It does not place a full-slide screenshot back into PowerPoint and call it editable. It separates each page into a clean base background, editable geometry, generated PNG assets, and real text boxes.

```text
source slide image
-> clean base background
-> component classification
-> editable geometry + generated PNG assets + real text
-> editable PPTX
```

## ✨ Core Strengths

| Strength | What It Means |
| --- | --- |
| 🪙 **Lower token use** | Pages are analyzed into reusable components, so repeated slide objects do not need to be described and rebuilt from scratch. |
| ⚡ **Faster reconstruction** | Repeated cards, stars, lines, title bars, and icon assets are generated once, then reused across slides. |
| ✍️ **Editable text** | Normal slide text becomes real PowerPoint text boxes, not rasterized text. |
| 📐 **Editable geometry** | Lines, stars, cards, title bars, circles, borders, and other simple shapes become editable PPT objects when practical. |
| 🧩 **Stable complex icons** | Badges, illustrations, glow effects, and detailed icons stay as transparent PNG assets instead of brittle over-splitting. |
| 🖼️ **AI-cleaned bases** | Backgrounds are regenerated with an image editing model, not covered with white masks or rough local inpainting. |
| ✨ **Generated icon assets** | PNG icons and complex PNG components are generated with an image generation/editing model, then sliced from the generated asset sheet. They are never cropped directly from the original slide screenshot. |

Token and timing benchmarks will be added after measurement.

## 🖥️ Examples

### 1. Smart Campus Core Modules

| Image PPT screenshot | Editable PPTX screenshot, all text boxes selected |
| --- | --- |
| ![Smart campus image PPT](examples/01-smart-campus/image-ppt-screenshot.png) | ![Smart campus editable PPTX](examples/01-smart-campus/editable-selected-textboxes.png) |

📎 Files: [`image-ppt.pptx`](examples/01-smart-campus/image-ppt.pptx) / [`editable.pptx`](examples/01-smart-campus/editable.pptx)

### 2. Project Content Overview

| Image PPT screenshot | Editable PPTX screenshot, all text boxes selected |
| --- | --- |
| ![Project overview image PPT](examples/02-project-overview/image-ppt-screenshot.png) | ![Project overview editable PPTX](examples/02-project-overview/editable-selected-textboxes.png) |

📎 Files: [`image-ppt.pptx`](examples/02-project-overview/image-ppt.pptx) / [`editable.pptx`](examples/02-project-overview/editable.pptx)

## 🎯 Why It Exists

Most image-to-PPT workflows fail in one of two ways:

1. ❌ They put the original slide screenshot into PPT and call it "editable".
2. ❌ They slice every visual element into PNGs, making simple shapes hard to edit and icons easy to crop badly.

Slide Alchemy uses a component-based reconstruction strategy:

- ✅ **Bases are image-edited, not masked.**
- ✅ **Simple geometry stays editable.**
- ✅ **Complex icons stay visually stable.**
- ✅ **Repeated pieces are reused.**

## 📦 Installation

Ask Codex to install this skill from the repository:

```text
Install the Codex skill from https://github.com/CodingFeng101/slide-alchemy.git
```

Restart Codex after installation.

## 🚀 Usage

Invoke the skill in Codex:

```text
Use $slide-alchemy to convert these image-style PPT slides into an editable PPTX.
```

## 🧱 Element Strategy

| Category | Use For | Output |
| --- | --- | --- |
| 📐 `simple_geometry_svg_ooxml` | lines, stars, circles, rings, cards, title bars, borders, simple circuit lines | editable PPT geometry |
| 🖼️ `icon_png` | trophy, flowers, book, hands/heart, computer, chain link, badges | transparent PNG |
| 🧩 `complex_png_whole` | swirls, glow-heavy decorations, multi-layer badges, complex illustrations | one whole transparent PNG |

Core rule:

> If the element can be described by geometry, fill, and stroke, make it editable. If it depends on texture, glow, shadow, or dense detail, keep it as PNG.

PNG icons and complex PNG components must be generated with an image generation/editing model and then sliced from the generated asset sheet. They must not be cropped directly from the original slide image.

Semantic icons stay PNG by default, even when they are flat or line-art icons. SVG/OOXML is for simple layout geometry, not for rebuilding recognizable icons out of native PPT shapes.

## 📄 License

MIT
