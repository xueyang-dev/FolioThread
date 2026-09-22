# FolioThread 品牌与视觉基准

本文是 FolioThread 的**唯一 logo 与视觉基准**记录。界面上出现的任何 logo、
图标、主色都必须回到这里，而不是各自另画一个。

## 0. 品牌来源

界面与 README 使用 `foliothread-source-lockup.png`，标签页使用
`foliothread-source-icon.png`。两者直接裁切自用户提供的品牌图（1448×1086），
**没有重绘、重新排字、变形或重采样**：

| 裁切资产 | 裁切框 (x0,y0,x1,y1) |
| --- | --- |
| `foliothread-source-lockup.png` | (110,140,1345,480) |
| `foliothread-source-icon.png` | (112,140,398,420) |

CSS 只指定宽度，高度自动计算——裁切资产不得再被拉伸到固定宽高。

## 1. Logo

logo 由三个元素组成，缺一不可：

| 元素 | 含义 |
| --- | --- |
| 两页叠放的圆角页面（后页钴蓝、前页横向渐变） | 一篇长文档，以及"文档不止一页"的结构 |
| 页面上的 **文** 和 **A** | 中文 ↔ 英文的翻译对 |
| 覆盖两页的白色指针光标 | agent 在文档上操作 |

页面整体顺时针倾斜（右上抬起），前页相对后页向右上错位。
这个"两页 + 光标"的组合就是品牌锚点：看到它就知道是 FolioThread。

### 资产矩阵

界面与对外材料优先使用**原图裁切**（保真、不重绘）；SVG 是同一 logo 的向量版本，
用于需要任意缩放或改色的场景。

| 版本 | 文件 | 用在哪里 |
| --- | --- | --- |
| 横向组合（原图裁切） | `foliothread-source-lockup.png` | 界面侧栏品牌位、README 首屏 |
| 图标（原图裁切） | `foliothread-source-icon.png` | 浏览器标签页（`st.set_page_config(page_icon=...)`） |
| 彩色图标（向量） | `foliothread-mark.svg` | 任意缩放的图标；`scripts/render_brand_assets.py` 的源 |
| 单色图标（向量） | `foliothread-mark-mono.svg` | 单色印刷、需要跟随前景色的场景；用 `currentColor` |
| 横向组合（向量渲染） | `foliothread-logo.png` | 需要与界面同一套排版的文档 / 深色底材料 |
| 深色底横向组合 | `foliothread-logo-dark.png` | 深色背景材料 |
| 竖向组合 | `foliothread-logo-stacked.png` | 窄栏、正方形版位的场景 |
| App 图标 | `foliothread-app-icon.png` | 深海军蓝圆角方块 + 图标，桌面/应用入口 |
| 标签页图标（向量） | `foliothread-favicon.svg` | 需要向量的标签页场景 |

单色版刻意做成"字形镂空"：**文**、**A** 与光标是从页面里打穿的洞，不是叠上去的
白色图层。这样在只有一个颜色的情况下仍然读得出三个元素。

### 不要做的事

- 不要重绘、重新排字、拉伸或改角度原图裁切资产——它们是品牌的保真基准；
- 不要把图标单独拉伸、换色，或只取其中一页；
- 不要在图标上叠加阴影、描边、外发光（原图里的高光已经是最终形态）；
- 不要新增色板之外的品牌蓝。

## 2. 色板

色值取自 logo 源文件本身；`app.py` 的 `:root` token 必须与下表一致
（`tests/brand_assets_test.py` 会强制执行）。

| 名称 | 色值 | 用途 |
| --- | --- | --- |
| Navy 深海军蓝 | `#000D2D` | 字标、App 图标底、品牌位最深色 |
| Cobalt 钴蓝 | `#004CFD` | 图标后页；**界面主色 / 主按钮 / 链接** |
| Azure 蔚蓝 | `#0088FD` | 图标渐变中段 |
| Cyan 青 | `#00E8FE` | 图标渐变亮端；强调点 |
| Ink 正文墨色 | `#0B1F3B` | 标题与当前项（`--tp-brand-ink`） |
| Sub 次要文字 | `#3E495D` | 副标题、说明文字 |

派生规则：

- hover = Cobalt 加深一阶（`#003FD6`），active 再深一阶（`#0034B0`）；
- 浅底强调面 = Cobalt 的 4% 冷调（`--tp-primary-soft: #EEF4FF`）；
- 语义色（成功 / 警告 / 危险）不参与品牌色板，继续用各表面既有的绿/橙/红。

## 3. 字体

- 主字体：**Manrope**（`400/500/600/700/800`），字标用 `800`、字距 `-0.022em`；
- 中文回退：`PingFang SC` → `Hiragino Sans GB` → `Microsoft YaHei` → `Noto Sans SC`；
- 界面已经在 `app.py` 全局声明这套字体栈，品牌位不要另设字体。

副标题固定两行：`Agentic Translation Workspace` / `智能体翻译工作台`。
中文副标题字距 `0.14em`，英文保持默认。

## 4. 改品牌时的固定流程

分两种情况，别混：

**A. 换品牌图（当前界面/README 的来源）**

```bash
# 1) 用原图重新裁切，不要重绘；裁切框同步更新本文第 0 节
#    foliothread-source-lockup.png / foliothread-source-icon.png

# 2) 若色板随之变化，更新 app.py 的 :root 品牌 token 与 gui.py 的
#    --theme.primaryColor，并同步本文「2. 色板」

# 3) 品牌约束回归
python -m pytest tests/brand_assets_test.py -q
```

**B. 改向量版（SVG 派生产物）**

```bash
# 1) 只改 SVG 源
$EDITOR transpraxis/resources/brand/foliothread-mark.svg

# 2) 重新生成全部位图（需要 node + playwright-core + Chromium）
python scripts/render_brand_assets.py

# 3) 校验产物与向量源一致
python scripts/render_brand_assets.py --check

# 4) 品牌约束回归
python -m pytest tests/brand_assets_test.py -q
```

`scripts/render_brand_assets.py` 只产出 SVG 派生的那几张位图，**不会**覆盖
`foliothread-source-*.png` 裁切资产。

## 5. 产品定位

品牌副标题已经说明定位：**Agentic Translation Workspace / 智能体翻译工作台**。
长文档仍然是主场景（见 README、`docs/architecture-boundaries.md`），
但 logo 表达的是"agent 在文档上翻译"，而不是某一种文档类型。

## 6. 工作台视觉应用（2026-09-14）

沿用现有叠页、文/A 与指针品牌资产。侧栏品牌位无边框、无阴影，原图通过 multiply 混合融入侧栏底色，
新建任务使用钴蓝实底；当前步骤用浅蓝背景与钴蓝侧线区分。
画布为 `#F4F7FC`，侧栏为 `#F8FAFF`，内容面为白色。
大内容面统一采用 16px 圆角、轻阴影与浅分隔线，输入控件采用 10px 圆角。
页面标题使用深海军蓝；页面引导眉题使用品牌钴蓝。
上传图标采用钴蓝以提升白底对比度，青色保留在 logo 中。
任务工作台顶栏以钴蓝顶线与白色内容面延续品牌，同时保持正文阅读密度。
