# Slide Alchemy

<p align="center">
  <a href="README.md">English</a> | <b>简体中文</b>
</p>

<p align="center">
  <strong>🧪 把图片式幻灯片重新炼成</strong><br>
  <span style="font-size: 42px; color: #ff2d2d; font-weight: 900;">真正可编辑</span><br>
  <strong>组件化的 PowerPoint。</strong>
</p>

> 把幻灯片截图、扫描版 PPT 或图片型 PPTX 变成真正能修改的 PowerPoint：文字是文本框，几何元素是原生对象，复杂视觉素材保持稳定。

[![GitHub stars](https://img.shields.io/github/stars/CodingFeng101/slide-alchemy?style=flat-square)](https://github.com/CodingFeng101/slide-alchemy/stargazers)
[![License](https://img.shields.io/github/license/CodingFeng101/slide-alchemy?style=flat-square)](LICENSE)

如果它帮你省下了手工重做幻灯片的时间，欢迎给仓库点个 **Star**，让更多需要处理 AI 幻灯片的人找到它。

Slide Alchemy 是一个可用于 Codex 和 Claude Code 的 Skill，用来把图片型 PPT/PPTX、幻灯片截图、扫描版视觉页面还原成可编辑的 `.pptx`。它不是把整页截图塞回 PowerPoint 后称为“可编辑”，而是把页面拆成干净底图、可编辑几何形状、生成式 PNG 素材和真实文本框。

```text
原始幻灯片图片
-> 干净底图
-> 组件分类
-> 可编辑几何元素 + 生成式 PNG 素材 + 真实文本
-> 可编辑 PPTX
```

## 🎬 演示视频

https://github.com/user-attachments/assets/da4675ac-5296-4938-b162-6c674a16d19f

## ✨ 核心优势

| 优势 | 说明 |
| --- | --- |
| 🪙 **更省 token** | 先把页面分析成可复用组件，避免每一页都从零描述和重建。 |
| ⚡ **还原更快** | 重复的卡片、星星、线条、标题条和图标素材只生成一次，再跨页面复用。 |
| ✍️ **文字可编辑** | 普通文字会还原为 PowerPoint 文本框，而不是截图文字。 |
| 📏 **文字位置实测** | OCR 只负责认字，位置、字号、颜色、粗细、项目符号和行距都从像素量出来，不靠视觉模型估算。 |
| 📐 **几何元素可编辑** | 线条、星星、卡片、标题条、圆形、边框等会尽量还原为 PPT 可编辑对象。 |
| 🧩 **复杂图标更稳定** | 奖杯、徽章、插画、光效等复杂图标保留为透明 PNG，避免硬拆后变丑。 |
| 🖼️ **底图由 AI 清理** | 底图由图像编辑模型补全，不用白块遮罩或本地粗糙 inpaint。 |
| ✨ **图标素材更干净** | PNG 图标和复杂 PNG 组件必须用图像生成/编辑模型生成素材图，再从素材图里裁剪，不能直接从原始截图上裁剪。 |

具体 token 消耗和耗时数据会在实测后补充。

## 🖥️ 示例

### 1. 智慧校园核心模块

| 图片 PPT 截图 | 可编辑 PPT 截图（所有文本框已选中） |
| --- | --- |
| ![智慧校园图片 PPT](examples/01-smart-campus/image-ppt-screenshot.png) | ![智慧校园可编辑 PPT](examples/01-smart-campus/editable-selected-textboxes.png) |

📎 文件：[`image-ppt.pptx`](examples/01-smart-campus/image-ppt.pptx) / [`editable.pptx`](examples/01-smart-campus/editable.pptx)

### 2. 项目内容概览

| 图片 PPT 截图 | 可编辑 PPT 截图（所有文本框已选中） |
| --- | --- |
| ![项目内容概览图片 PPT](examples/02-project-overview/image-ppt-screenshot.png) | ![项目内容概览可编辑 PPT](examples/02-project-overview/editable-selected-textboxes.png) |

📎 文件：[`image-ppt.pptx`](examples/02-project-overview/image-ppt.pptx) / [`editable.pptx`](examples/02-project-overview/editable.pptx)

## 🎯 为什么需要它

常见图片转 PPT 流程容易有两个问题：

1. ❌ 把整页截图放进 PPT，然后说“可编辑”。
2. ❌ 把所有元素都切成 PNG，导致线条、星星、卡片、边框这些简单元素无法编辑，而且图标容易被切残。

Slide Alchemy 使用组件化还原策略：

- ✅ **底图是图像编辑生成的，不是遮罩糊出来的。**
- ✅ **简单几何保持可编辑。**
- ✅ **复杂图标保持视觉稳定。**
- ✅ **重复组件直接复用。**

## 📦 安装

### Codex

让 Codex 从这个仓库安装 skill，装好后重启 Codex：

```text
Install the Codex skill from https://github.com/CodingFeng101/slide-alchemy.git
```

### Claude Code

让 Claude Code 帮你安装：

```text
从 https://github.com/CodingFeng101/slide-alchemy.git 安装 skill：把其中的 skill/slide-alchemy 文件夹复制到 ~/.claude/skills/
```

也可以手动复制：

```bash
git clone https://github.com/CodingFeng101/slide-alchemy.git
cp -r slide-alchemy/skill/slide-alchemy ~/.claude/skills/
```

装好后重启 Claude Code，让它加载这个 skill。

Claude Code 没有自带的生图工具，skill 会改用 `scripts/generate_image.py` 调用兼容 OpenAI 的 Images API。启动 Claude Code 前先设置：

```bash
export SLIDE_ALCHEMY_IMAGE_API_KEY=sk-...
export SLIDE_ALCHEMY_IMAGE_BASE_URL=https://api.openai.com/v1   # 也可以换成兼容的中转地址
export SLIDE_ALCHEMY_IMAGE_MODEL=gpt-image-2                     # 可选，默认就是这个
```

Windows PowerShell 用 `$env:SLIDE_ALCHEMY_IMAGE_API_KEY = "sk-..."`；想长期生效可以用 `setx`。

### Python 依赖

Skill 自带的脚本需要安装 Python 依赖，其中包括文字提取用的 OCR 引擎。OCR 模型随包附带，运行时不需要联网下载：

```bash
pip install -r skill/slide-alchemy/requirements.txt
```

## 🚀 使用

在 Codex 中调用：

```text
Use $slide-alchemy to convert these image-style PPT slides into an editable PPTX.
```

在 Claude Code 中调用：

```text
/slide-alchemy 把 deck.pptx 转成可编辑的 PPTX
```

## 🧱 元素分类策略

| 分类 | 适合元素 | 输出 |
| --- | --- | --- |
| 📐 `simple_geometry_svg_ooxml` | 线条、星星、圆形、圆环、卡片、标题条、边框、简单电路线 | PPT 可编辑几何元素 |
| 🖼️ `icon_png` | 奖杯、花、书本、爱心托举、电脑、链条、徽章 | 透明 PNG |
| 🧩 `complex_png_whole` | 漩涡、复杂光效、多层徽章、复杂插画 | 整体透明 PNG |

核心判断：

> 如果一个元素能用几何轮廓、填充色、描边描述，就做成可编辑对象；如果它依赖纹理、光影、渐变、细节堆叠，就保留为 PNG。

PNG 图标和复杂 PNG 组件必须用图像生成/编辑模型生成素材图，再从生成的素材图里裁剪。绝对不能直接从原始幻灯片截图上裁剪。

语义图标默认保留为 PNG，即使它是扁平图标或线稿图标。SVG/OOXML 只用于简单版式几何，不用于把可识别图标强行拼成 PPT 原生形状。

## 📄 许可证

MIT
