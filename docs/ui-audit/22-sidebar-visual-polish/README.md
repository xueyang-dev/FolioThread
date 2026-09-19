# 22 · Sidebar Project 区视觉收敛（最后一轮，纯视觉）

IA / state / routing / behavior **全部冻结**，本轮只改视觉：分组标题的基线、selector
的权重、行的高度、Inbox 标签的层级、footer 的形态。

## 复现步骤

```bash
# 1) 起应用（仓库根目录）
streamlit run app.py

# 2) 截图（本机 playwright-core + Chrome）
FOLIO_PLAYWRIGHT_CORE=~/Dev/grok-workspace/node_modules/playwright-core \
FOLIO_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
node /tmp/folio_shots.js http://127.0.0.1:8501 docs/ui-audit/22-sidebar-visual-polish
```

`/tmp/folio_shots.js` 依次截：侧栏（面板收起）→ 「项目」分组（面板收起）→ 点开
selector 后的侧栏 / 分组 → footer hover 态 → 整页。

## 截图

| 文件 | 内容 |
|---|---|
| `01-sidebar-closed.png` | 侧栏全貌（切换面板收起） |
| `02-project-group-closed.png` | 「项目」分组（标题 + selector，收起） |
| `03-sidebar-switcher-open.png` | 侧栏全貌（切换面板展开） |
| `04-project-group-open.png` | 「项目」分组（面板展开：行 / Inbox / footer） |
| `05-footer-hover.png` | footer「＋ 新建项目」hover 态（浅底） |
| `06-full-page.png` | 整页（看与「工作区」标题的基线关系） |

## 实测值（浏览器 computed style，非代码推断）

| 元素 | 关键值 |
|---|---|
| 「工作区」标题 | 12px / 500 / line-height 16.8 / margin 18px 0 6px / #7c8799 |
| 「项目」标题按钮 | 12px / 500 / line-height 16.8 / **margin 18px 0 6px** / min-height **17px** / 透明底 / `justify-content: flex-start` / 内容 `flex: 0 0 auto`（chevron 紧跟） |
| 标题内 `p` | **12px !important**（Streamlit markdown 容器自带 14px 且不继承） |
| selector | min-height **46px** / radius **11px** / `border: 1px solid var(--tp-sidebar-line)` / `background: var(--tp-surface)` / 12.5px / 600 |
| focus ring | `outline: 2px solid var(--tp-primary)` + `box-shadow: none`（只有一条） |
| switcher 行 | min-height **38px** / `border: 0` / 当前行仅 `background: var(--tp-tint-active)` |
| 行间距 | `row-gap: 2px`（写在 stVerticalBlock 自己身上） |
| Inbox 标签 | 9.5px / #a8b1c0 / 500（名字 13 → 计数 11.5 → Inbox 9.5） |
| footer「＋ 新建项目」 | min-height **40px** / `background: transparent` / `border: 0` / `box-shadow: none` / hover 才 `--tp-tint-hover` |

## 本轮抓到的两个真问题

1. **「＋ 新建项目」是浅蓝卡片 —— 根因是 selector 规则泄漏。**
   `.st-key-current_project .stButton button` 是**后代**选择器，而展开后的面板（列表行 +
   footer）就渲染在同一个 `current_project` 容器里，于是 selector 的填充色 / 高度 / 圆角
   被一并继承给 footer。修复：所有 selector 规则改钉在**触发器自己的 key 容器**
   `[class*="st-key-current_project_selector"]` 上；状态标记（`.tp-nav-empty` /
   `.tp-nav-open`）是触发器的兄弟节点，`:has()` 只能写在外层、再往下指回触发器。
   同理修了 task 锚点（`.st-key-task_project_context` → `task_project_change` /
   `task_project_pick`）。
2. **`st.container(key=…)` 的 key 打在 stVerticalBlock 自己身上**，不是外面再包一层。
   所以 `> [data-testid="stVerticalBlock"] { gap: … }` 这类"收紧间距"的规则会静默落空
   （退回默认 8px）。现在改成 `[class*="…"][data-testid="stVerticalBlock"]` 自匹配。
