# Slide Alchemy

<p align="center">
  <strong>🧪 把图片式幻灯片重新炼成</strong><br>
  <span style="font-size: 42px; color: #ff2d2d; font-weight: 900;">完全完全</span><br>
  <strong>可编辑的 PowerPoint。</strong>
</p>

Slide Alchemy 是一个 Codex Skill，用来把图片型 PPT/PPTX、幻灯片截图、扫描版视觉页面还原成可编辑的 `.pptx`。它不是把整页截图塞回 PowerPoint 后称为"可编辑"，而是把页面拆成干净底图、可编辑几何形状、生成式 PNG 素材和真实文本框。

```text
原始幻灯片图片
-> 干净底图
-> 组件分类
-> 可编辑几何元素 + 生成式 PNG 素材 + 真实文本
-> 可编辑 PPTX
```

## ✨ 核心优势

| 优势 | 说明 |
| --- | --- |
| 🪙 **更省 token** | 先把页面分析成可复用组件，避免每一页都从零描述和重建。 |
| ⚡ **还原更快** | 重复的卡片、星星、线条、标题条和图标素材只生成一次，再跨页面复用。 |
| ✍️ **文字可编辑** | 普通文字会还原为 PowerPoint 文本框，而不是截图文字。 |
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

### 与其他方案的对比

| 方案 | 产物 | 文字可编辑 | 几何可编辑 | 图标质量 | 底图质量 |
| --- | --- | --- | --- | --- | --- |
| 整页截图放回 PPT | 图片 PPTX | ❌ 不可编辑 | ❌ 不可编辑 | — | — |
| 全部切 PNG 拼回 | PNG 拼图 PPTX | ❌ 不可编辑 | ❌ 不可编辑 | ⚠️ 易切残 | ⚠️ 白块遮罩 |
| 通用 PPT 转换工具 | 转换后 PPTX | ⚠️ 部分可编辑 | ⚠️ 有限 | ⚠️ 模板替代 | ⚠️ 通用模板 |
| **Slide Alchemy** | **组件化 PPTX** | **✅ 真实文本框** | **✅ 可编辑 OOXML 形状** | **✅ 生成式透明 PNG** | **✅ AI 清理底图** |

### 常见图片转 PPT 流程的问题

1. ❌ 把整页截图放进 PPT，然后说"可编辑"。
2. ❌ 把所有元素都切成 PNG，导致线条、星星、卡片、边框这些简单元素无法编辑，而且图标容易被切残。

Slide Alchemy 使用组件化还原策略：

- ✅ **底图是图像编辑生成的，不是遮罩糊出来的。**
- ✅ **简单几何保持可编辑。**
- ✅ **复杂图标保持视觉稳定。**
- ✅ **重复组件直接复用。**

## ⚠️ 诚实说明

Slide Alchemy 是一个工具，不是一个许愿池。

- **还原质量取决于源图质量**：模糊、低分辨率或严重压缩的源图会降低所有步骤的输出质量。
- **生成式模型有偏差**：AI 清理底图和生成图标时可能产生细微的风格偏移，不会 100% 复刻原图。
- **文字定位是近似的**：视觉模型提取的文字位置可能有像素级偏移，复杂排版可能需要手动微调。
- **复杂装饰性页面效果有限**：全页插画式设计、手绘风格或重度光效页面的还原效果不如简洁的商务风格页面。
- **模型越弱，人工补偿越多**：使用更强大的视觉/图像模型会显著提升各步骤的输出质量。

如果追求像素级完美还原，Slide Alchemy 可能无法满足。它的目标是：在合理的人工微调范围内，把"完全不可编辑的图片 PPT"变成"大部分可编辑的 PPTX"。

## 📦 安装

### 前置条件

- Codex（支持 Skill 安装）
- Python 3.10+（脚本依赖）
- 支持图像生成/编辑的 AI 模型

### 安装步骤

1. 让 Codex 从这个仓库安装 skill：

```text
Install the Codex skill from https://github.com/CodingFeng101/slide-alchemy.git
```

2. 安装后重启 Codex。

3. （可选）安装脚本依赖：

```bash
pip install -r skill/slide-alchemy/requirements.txt
```

## 🚀 使用

### 基本用法

在 Codex 中调用：

```text
Use $slide-alchemy to convert these image-style PPT slides into an editable PPTX.
```

### 完全自动模式

如果不需要中途确认：

```text
Use $slide-alchemy to convert these slides. Run unattended, no intermediate confirmation.
```

或中文：

```text
用 slide-alchemy 还原这些幻灯片，不要中途确认，全自动运行。
```

### 仅还原指定页面

```text
Use $slide-alchemy to convert pages 1-5 of this PPT into an editable PPTX.
```

> 注意：即使只请求部分页面，工作流仍会完整运行（包括所有页面的底图生成和组件分析），因为组件复用需要全局分析。

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

## 🗂️ 工作流概览

Slide Alchemy 采用 10 步串行管线，每步有严格的前置验证门：

| 步骤 | 说明 | 交互 |
| --- | --- | --- |
| 1. 源页面渲染 | 获取/渲染源图 | — |
| 2. 底图分组 | 提议分组方案 | ⛔ 需用户确认 |
| 3. 清洁底图生成 | AI 模型生成底图 | ⛔ 需用户确认 |
| 4. 元素分析 | 分类所有非文字元素 | — |
| 5. SVG/OOXML 生成 | 几何元素转可编辑形状 | — |
| 6. PNG 素材图生成 | 图标/复杂元素生成素材 | — |
| 7. PNG 切片 + QA | 裁剪、边缘检查 | — |
| 8. 文字提取 | 视觉模型提取文字 | — |
| 9. PPTX 组合 | 按层序组合最终文件 | — |
| 10. 预览 + QA | 对比源图和结果 | — |

## 🤝 参与贡献

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何提交 Bug 报告、修复和功能建议。

## 📄 许可证

MIT
