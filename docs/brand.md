# Folith / 译页 品牌与视觉基准

本文是 **Folith / 译页** 的唯一 logo 与视觉基准。品牌迁移只更新文字品牌和
对外定位，保留现有 icon mark、色板与工作台视觉系统，不改变产品信息架构。

## 0. 正式品牌

| 语言 | 品牌名 | 定位 |
| --- | --- | --- |
| English | `Folith` | `Agentic Localization Workspace` |
| 中文 | `译页` | `Agentic 本地化工作台` |

正文统一写 `Folith` 或 `译页`。需要同时说明中英文品牌时写 `译页 Folith`。
不要把品牌扩展成 `Folith AI`、`译页AI` 或普通的 AI Translator。

## 1. Logo

logo 继续使用两页、文/A 字形和白色指针组成的 icon mark：

| 元素 | 含义 |
| --- | --- |
| 两页叠放的圆角页面（后页钴蓝、前页横向渐变） | 长文档及其结构 |
| 页面上的 **文** 和 **A** | 中文 ↔ 英文的本地化工作 |
| 覆盖两页的白色指针光标 | Agent 在文档上执行工作 |

本轮不重绘、不换色、不加阴影，也不重新设计图形。`folith-*` 是当前正式品牌
资源；原有 `foliothread-*` 资源作为历史/兼容素材保留，但不再由当前 UI 或
README 引用。

### 资产矩阵

| 版本 | 文件 | 用在哪里 |
| --- | --- | --- |
| 彩色图标（向量） | `folith-mark.svg` | SVG 图标源 |
| 单色图标（向量） | `folith-mark-mono.svg` | 单色、需跟随 `currentColor` 的场景 |
| 横向组合 | `folith-logo.png` | 侧栏品牌位、README 首屏、浅色材料 |
| 中文横向组合 | `folith-logo-zh.png` | 中文界面侧栏品牌位 |
| 深色底横向组合 | `folith-logo-dark.png` | 深色背景材料 |
| 竖向组合 | `folith-logo-stacked.png` | 窄栏或正方形版位 |
| App 图标 | `folith-app-icon.png` | 桌面/应用入口 |
| 标签页图标 | `folith-favicon.svg` / `folith-favicon.png` | 浏览器与安装入口 |

位图都由 `scripts/render_brand_assets.py` 从 SVG 源生成，禁止手工替换为不同
比例或不同字标的图片。旧的 `foliothread-source-lockup.png` 与
`foliothread-source-icon.png` 仍随包保留，供历史数据或旧文档读取。

## 2. 色板

色值取自 icon mark；`app.py` 的 `:root` token 与 `gui.py` 的 Streamlit 主题
必须与这里一致，`tests/brand_assets_test.py` 会检查：

| 名称 | 色值 | 用途 |
| --- | --- | --- |
| Navy 深海军蓝 | `#000D2D` | 字标、App 图标底、最深色 |
| Cobalt 钴蓝 | `#004CFD` | 图标后页、界面主色、主按钮与链接 |
| Azure 蔚蓝 | `#0088FD` | 图标渐变中段 |
| Cyan 青 | `#00E8FE` | 图标渐变亮端与强调点 |
| Ink 正文墨色 | `#0B1F3B` | 标题与当前项 |
| Sub 次要文字 | `#3E495D` | 副标题与说明文字 |

hover 和 active 只使用 Cobalt 的更深阶；语义色继续使用既有绿、橙、红。

## 3. 字体与副标题

- 主字体：Manrope `400/500/600/700/800`，字标使用 `800`；
- 中文回退：`PingFang SC` → `Hiragino Sans GB` → `Microsoft YaHei` → `Noto Sans SC`；
- 英文副标题：`Agentic Localization Workspace`；
- 中文副标题：`Agentic 本地化工作台`。

界面和品牌资产使用同一字体栈，中文副标题保留现有字距规则。

## 4. 资源生成与回归

只修改 SVG 源，然后生成全部位图并运行检查：

```bash
$EDITOR transpraxis/resources/brand/folith-mark.svg
python scripts/render_brand_assets.py
python scripts/render_brand_assets.py --check
python -m pytest tests/brand_assets_test.py -q
```

脚本只管理 `folith-*` 向量派生位图，不覆盖旧的 `foliothread-source-*.png`。

## 5. 工作台应用

侧栏、浏览器标题、启动器、README 和导出署名使用当前品牌；中文界面优先显示
`译页`，英文界面使用 `Folith`。页面仍保持既有侧栏、任务步骤、内容面、圆角、
间距和颜色，不借 rebrand 之机改动导航或交互流程。

## 6. 兼容边界

`foliothread` Python 包名、`foliothread` / `transpraxis` console 入口、
`FOLIOTHREAD_*` 环境变量、项目 schema、内存格式、导出字段和历史资源名都属于
兼容性边界，不能仅为品牌整洁而删除或重命名。它们不改变产品表层品牌。
