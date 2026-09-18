# 侧栏「项目」分组：Project Context 与 Project Management 归并

状态：已实现（`app.py`），回归测试见 §6。
范围：**只动侧栏信息架构与它的样式契约**——不动路由表、数据模型、项目页内容，
也不动翻译内核。

## 0. 问题归因

改造前的侧栏有两个"看起来各管一套"的区块：

```text
（顶部）
项目上下文              ← 分组标题
📁 未选择项目 ▾
...
（底部）
工作区
项目中心                ← 却属于 Project Management
历史任务
术语与翻译记忆
设置
```

三处认知代价：

1. **同属 Project 却被拆散**：上下文回答"我在哪个项目里工作"，项目中心回答"我拥有
   哪些项目"——它们只是同一对象（Project）的读与管两种动作，却被一个 spacer + 分组
   标题隔开，用户读到的是"两套系统"；
2. **「项目中心」与「历史任务 / 术语与翻译记忆」混成同类**：它被排进「工作区」列表，
   于是"打开项目列表"看起来像"打开第三个资料库"，而不是 Project 的管理入口；
3. **分组标题「项目上下文」歧义**：它既是分组名又是概念名，正文里同一句话既指侧栏
   控件又指任务归属说明。

## 1. 调整后的 IA 说明

心智模型收敛为：**Project 在侧栏只占一个分组**，组内按"读 / 管"分主次。

| 对象 | 语义 | 位置 | 视觉权重 | 动作 |
| --- | --- | --- | --- | --- |
| 上下文 selector | **Project Context**：我此刻在哪个项目里工作 | 「项目」分组第 1 项 | 主控件：42px、`primary-soft` 填充、650 字重、带边框 | 在触发器下方展开**轻量下拉面板**（搜索 / 列表 / 新建项目），切换全局上下文 |
| 项目中心 | **Project Center**：我拥有哪些项目 | 「项目」分组第 2 项，紧贴 selector 下方 | 次级入口：36px、透明底、500 字重、灰色 | 进入 `/projects` 管理页（**纯导航**）；不展开面板、不弹 Modal、**不**改变上下文 |

> 交互语义的细节（为什么是就地面板而不是大型 Modal、「管理所有项目」为什么被删除、
> 路由与上下文如何分离）见 [`sidebar-context-vs-center.md`](sidebar-context-vs-center.md)。
| 当前任务 | **Task flow**：本次任务的四步 | 独立分组 | 步骤条（竖线 + done/current/pending 三态） | 在创建流程里跳步 |
| 历史任务 / 术语与翻译记忆 / 设置 | **Global navigation**：跨项目的资料与全局设置 | 「工作区」分组 | 常规导航项 | 进入各自页面 |

三条边界：

- **不把「项目中心」放进「工作区」**：那一组是 global navigation，Project 不属于它；
- **不把上下文留在顶部、管理入口留在底部**：拆分布局本身就是"两套系统"的成因；
- **不把「项目中心」做成第二颗主按钮**：它和 selector 同级会读成"两个入口在抢同一个
  位置"，而降级成扁平行之后，主次一眼可辨。

## 2. Sidebar 低保真结构

```text
┌ 侧栏 ────────────────────────┐
│ [Logo]                      │
│                             │
│ ┌─────────────────────────┐ │
│ │ ＋ 新建任务              │ │  ← 全局创建动作（流程内退成 secondary）
│ └─────────────────────────┘ │
│                             │
│ 项目                        │  ← 分组标题（取代旧「项目上下文」）
│ ┌─────────────────────────┐ │
│ │ 📁 示例项目        ▾    │ │  ← 主控件：填充底 / 42px / 650
│ └─────────────────────────┘ │
│   ┌───────────────────────┐ │  ← 展开才渲染的轻量下拉面板
│   │ 搜索项目…             │ │
│   │ ✓ 未分类任务 系统工作区│ │
│   │   示例项目             │ │
│   │ ──────────────────     │ │
│   │ ＋ 新建项目            │ │
│   └───────────────────────┘ │
│   项目中心                  │  ← 次级入口：透明底 / 36px / 500 / 灰色
│                             │
│ ───────────────────────────  │  ← 分隔线：项目 ▸ 任务
│ 当前任务                     │
│  ● 01 文档与画像            │
│  ○ 02 翻译策略              │
│  ○ 03 交付内容              │
│  ○ 04 确认运行              │
│                             │
│ 工作区                       │  ← 只有跨项目的资料与全局设置
│  ⏱ 历史任务                 │
│  ▤ 术语与翻译记忆           │
│  ⚙ 设置                     │
│                             │
│ ── AI引擎            管理 ── │  ← provider 状态（贴底）
└─────────────────────────────┘
```

三种状态下的差异：

| 状态 | selector | 项目中心 |
| --- | --- | --- |
| 未选项目（新建任务 / 无上下文） | 中性态：`#f6f8fb` 底 + 1px 边框 + 「未选择项目 ▾」；下方一行 `正在查看未分类任务`（仅未分类任务视图） | 扁平行，无标记 |
| 已进入项目（项目详情 / 任务工作区） | 填充态：`primary-soft` 底 + 项目名 + `folder_open` 图标 | 扁平行，无标记（当前态属于 selector） |
| 展开切换面板 | 触发器变"已按下"（`.tp-nav-open` → 更深的 `primary-soft` 面 + 边框），面板在它下方展开 | 不受影响 |
| 停在 `/projects` 列表页 | **与上一行相同**：上下文保留、文案不变（管理页是纯导航，不修改上下文） | 中性面 + 左侧 3px 蓝色竖条 = "你在这儿" |

## 3. 具体组件改动清单

| # | 组件 | 改动 | 为什么 |
| --- | --- | --- | --- |
| 1 | 分组标题 | `项目上下文` → `项目` | 「项目」是分组名；「项目上下文」降为概念名，只出现在正文说明里 |
| 2 | 分组容器 | 新增 `st.container(key="project_nav_group")`，把标题 + selector + 项目中心包进同一容器，`gap: 4px` | 同一分组 = 同一容器：相邻关系由容器保证，而不是靠视觉巧合 |
| 3 | 上下文 selector | 视觉**不变**（仍是 `current_project` + 42px + `primary-soft` + 650 字重）；行为改为展开轻量面板 | 它已经是主控件；本轮只保证它仍然是组内最重的一件，并让它的点击结果与主控件身份相称 |
| 4 | 项目中心入口 | 从「工作区」组的 `library_nav` 移到「项目」分组；`type="primary"` → 默认 secondary + 独立扁平行样式（36px / 透明底 / 500 字重 / `#536176` / 17px 灰图标） | 与 selector 拉开层级；不再和「历史任务」同列 |
| 5 | 项目中心"当前页" | 新增空语义标记 `<span class="tp-nav-current">`，仅在列表页渲染 | 同组里"你在这儿"只亮一次：列表页亮在入口，项目详情亮在 selector |
| 6 | 「工作区」分组 | 只保留 历史任务 / 术语与翻译记忆 / 设置；注释说明它是 global navigation | 防止"项目中心 = 第三个资料库"的误读回归 |
| 7 | 正文上下文块 | 文案微调：`[更改]` / `[选择项目]` 的 help 指向"侧栏「项目」分组里的同一个选择器" | 明示唯一来源，正文不制造第二个答案 |
| 8 | 新建任务按钮 / 任务步骤 | **不变** | 本轮不碰创建流程与 task flow |

## 4. 实现修改

`app.py`

- **CSS**（在 `.st-key-current_project` 段落后新增一段，约 L449–L500）
  - `.st-key-project_nav_group` / `> [data-testid="stVerticalBlock"] { gap: 4px }` /
    `.tp-nav-label { margin: 18px 0 2px }`：分组容器的相邻节奏；
  - `[class*="st-key-project_center_entry"] .stButton button`：扁平行（36px / 透明底 /
    500 字重 / 灰），用**后代选择器**——带 `help=` 的按钮会被 Streamlit 包进 tooltip
    span，`button` 不是 `.stButton` 的直接子元素；
  - `.tp-nav-current { display: none }` + `…:has(.tp-nav-current) .stButton button`：
    当前页态 = 中性面 `#f2f5f9` + `inset 3px 0 var(--tp-primary)`。**刻意不复用**
    `--tp-primary-soft`，否则会与 selector 的"已进入项目"填充态撞衫；
  - `…:has(.tp-nav-current)` 所在的空元素容器 `display: none`，不占用分组 `gap`。
- **侧栏渲染**（`with st.sidebar:`，约 L15233–L15250）
  - 新增 `project_nav_group` 容器：`tp-nav-label` 「项目」→ `_sync_task_project_context()`
    → `_sidebar_project_switcher(...)` → 项目中心按钮；
  - `_project_center_current = app_view == "projects" and not workspace_mode
    and _projects_route() == "list"`：只在**列表路由**打当前页标记。判据从
    "没有上下文"改为"路由是列表"，因为管理页不再清空上下文（见
    [`sidebar-context-vs-center.md`](sidebar-context-vs-center.md)）；
  - 「工作区」的 `library_nav` 移除项目中心按钮。
- **文案 / 文档字符串**：`_sidebar_project_switcher` docstring、
  `_render_task_project_context` docstring 与两个 help 文案改为指向「项目」分组。

`docs/project-memory.md`：§「侧栏」整节重写为"Project 只占一个分组"，
含新的低保真结构与主次说明。

## 5. 与正文的联动契约

- **侧栏是全局 source of truth**。正文里新建任务第 1 步的「项目上下文」块是**只读**的：
  它只说明"这个任务会落在哪里 + 继承什么"，不提供第二个选择器；
- 两处状态必须永远一致，且这种一致性由**状态投影**保证，不靠 UI 巧合：
  `task_project_id` 是上下文的投影（`_sync_task_project_context()` 每次运行对齐），
  `[更改]` / `[选择项目]` 展开的就是**同一份**切换列表（只是锚点在正文），因此不存在
  "侧栏说 A、正文说 B"的中间态；两处锚点同一时刻只展开一个；
- 已选：侧栏 selector = 项目名，正文 = `tp-project-context is-selected` + 同一个项目名；
  未选：侧栏 = 「未选择项目」，正文 = `is-empty` + 「未分类任务（Inbox）」+ "任务将保存
  到系统工作区"。两种表述是同一答案的两种说法，不是两个答案。

## 6. 测试覆盖

`tests/project_context_hierarchy_test.py`

| 用例 | 守住什么 |
| --- | --- |
| `test_sidebar_project_group_holds_context_and_management` | 分组标题序列 `["项目", "工作区"]`；不再有「项目上下文」/「当前项目」标题；「项目中心」紧贴 selector 之下，且在「历史任务」之前 |
| `test_project_center_is_a_subordinate_entry_not_a_second_primary` | CSS：selector 42px + `primary-soft` + 650；入口 36px + 透明底 + 500；当前页规则里**不得**出现 `--tp-primary-soft`，必须有 `inset 3px 0` |
| `test_project_center_current_marker_shows_only_on_the_list_page` | 列表页有 `tp-nav-current`；项目详情页没有（当前态归 selector） |
| `test_sidebar_and_body_never_disagree_about_the_context` | 侧栏与正文在两个状态下同时改口，且 `task_project_id` 与上下文一致 |
| `test_project_center_does_not_switch_the_context` | 管理入口**纯导航**：路由落到 `list`、上下文原样保留、管理页真的渲染 |
| `test_context_selector_is_one_compact_control_in_both_states`（沿用） | 未选态仍是同一个 compact 控件，不是虚线大卡片 |
| `test_task_page_change_opens_the_same_switcher_list` | 正文锚点展开同一份列表（`task_switcher_pick_*`），且侧栏锚点保持收起 |

`tests/project_task_navigation_test.py`

| 用例 | 守住什么 |
| --- | --- |
| `test_sidebar_project_group_sits_above_the_workspace_group` | 侧栏分组标题恰为 `["项目", "工作区"]`；「项目中心」与 selector 相邻且排在「工作区」三项之前 |
| `test_sidebar_context_is_unselected_without_a_real_project`（沿用） | 「未分类」不被渲染成项目；selector 只有一行 |
| `test_sidebar_selector_stays_compact_without_a_project`（沿用） | 未选态样式契约不变 |
| `test_project_center_entry_returns_to_the_project_list` | 进入的是管理页路由（`projects_route == "list"`），且当前上下文不被清空 |
| `test_project_switcher_actions_are_context_only` | switcher 底部只有「新建项目」；「管理所有项目」已退休；侧栏只有一颗管理入口 |

`tests/sidebar_project_switcher_test.py`（本轮新增，11 个用例）逐条覆盖 8 项交互验收，
明细见 [`sidebar-context-vs-center.md §6`](sidebar-context-vs-center.md)。

**回归结果（2026-09-18）**：本轮的定向回归（`-k project`，7 个文件，235 passed / 0 failed，
耗时 128m5s）已被**收尾轮的全量回归**取代 —— 全套 **63 个文件 = 62 pytest + 1 脚本式冒烟**，
**888 passed / 0 failed / 0 error / 0 skipped / 0 xfailed**，有效失败 0，耗时 101m26s，
runner exit code 0。逐文件数字见
[`sidebar-context-vs-center.md §9`](sidebar-context-vs-center.md)。

（AppTest 在本机 shim 下慢 5–12 倍属环境开销，判别方法是纯逻辑测试的 pytest 内部耗时不变。）

## 7. 视觉验收（真实渲染）

截图归档：[`docs/ui-audit/21-sidebar-project-group/`](ui-audit/21-sidebar-project-group/README.md)
（3 张：未选上下文 / 列表页当前页标记 / 已选上下文的侧栏↔正文一致）。用
`scripts/ui_screenshot.py` + 一次「项目中心」点击，在 1440×900 下核对：

- 新建任务页：分组标题「项目」→ 中性 selector → 扁平的「项目中心」→ 分隔线 → 当前任务
  四步 → 「工作区」三项；层级一眼可辨；
- `/projects` 列表页：「项目中心」出现中性面 + 左侧 3px 竖条；selector 仍是最重的控件；
- 已选上下文：selector 显示项目名（填充态），正文上下文块显示同一个项目名，
  「项目中心」无当前页标记。

两个会让截图骗人的坑（本轮踩过）：首次渲染约 20s，截早了只有 Logo；点击后指针停在
按钮上会命中 `:hover`，把当前页样式盖掉 —— 两张意图不同的图会截出**字节相同**的文件，
截图前必须移开指针。

## 8. 风险与未做

- **未做**：`项目中心` 仍是 Streamlit `st.button`（不是原生导航项），因此"当前页"只能
  靠语义标记 + CSS 表达，并且"点击它是导航而不是弹层"由代码结构保证（它不调用任何
  面板 / Modal 开关）；如果以后引入真正的 nav component，这套标记可以直接删除。
- **未做**：本轮没有给「项目」分组加展开 / 折叠；分组内只有两项，折叠没有收益。
- **风险**：`.st-key-current_project:has(.tp-nav-empty)`、`…:has(.tp-nav-current)` 依赖
  `:has()`。项目已有多处使用（`st-key-project_row_*`、`library_nav`），属于既有约定，
  但这两个选择器一旦失效，"中性态/当前态"会静默退回默认样式——因此 §6 的 CSS 断言是
  必需的，不是可选的。
