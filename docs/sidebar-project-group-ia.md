# 侧栏「项目」分组：Project Context 与 Project Management 归并

状态：已实现（`app.py`），回归测试见 §6。
范围：**只动侧栏信息架构与它的样式契约**——不动路由表、数据模型、项目页内容，
也不动翻译内核。

> **更新（入口收敛轮）**：Project Center 的入口已从"标题下面一个独立行"**收敛到分组
> 标题本身**。原因是同一条：同一个分组里出现两个指向管理页的入口、而且其中一行还在和
> selector 争视觉重量。§1–§4 已按收敛后的结构改写；交互语义（导航 vs 状态）不变，
> 细节见 [`sidebar-context-vs-center.md`](sidebar-context-vs-center.md)。
>
> 同时 switcher 面板改为 **compact switcher**（单行 row、名称可省略、计数靠右、
> 列表内滚动、面板不横向溢出），并移除了面板里常驻的说明文案。
>
> **更新（AI Engine 入口收敛轮）**：「工作区」分组里的独立「⚙ 设置」行**已删除**。
> 当前产品没有独立的 General Settings 信息架构——它唯一的落点就是 AI Engine /
> Model Center，与贴底 status module 上的「管理」完全同义。同一页面在侧栏出现两个
> 入口，正是这一轮要消除的重复导航。「工作区」因此只剩跨项目的**资料**：
> 历史任务 / 术语与翻译记忆。AI Engine 入口只保留 `provider_status` 上的「管理」。
> 恢复「设置」的条件见 §9。

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

心智模型收敛为：**Project 在侧栏只占一个分组**，组内按"读 / 管"分主次，而管理入口
**就是分组标题**。

| 对象 | 语义 | 位置 | 视觉权重 | 动作 |
| --- | --- | --- | --- | --- |
| 分组标题「项目」 | **Project Center**：我拥有哪些项目 | 「项目」分组标题（组内最上） | 轻量 section header：**17px 行盒**、透明底、12px/500，与「工作区」**同一条水平基线**；左对齐，chevron 紧跟标题（不贴侧栏最右），hover 才变色 + 下划线 + chevron 右移 | 进入 `/projects` 管理页（**纯导航**）；不展开面板、不弹 Modal、**不**改变上下文 |
| 上下文 selector | **Project Context**：我此刻在哪个项目里工作 | 「项目」分组第 2 行，紧贴标题下方 | 主控件但**权重低于 CTA**：46px、11px 圆角、1px 细边、中性 surface、12.5px/600；focus ring 只有一条 2px outline | 在触发器下方展开**轻量下拉面板**（可选搜索 / 列表 / 新建项目），切换全局上下文 |

> 交互语义的细节（为什么是就地面板而不是大型 Modal、「管理所有项目」为什么被删除、
> 路由与上下文如何分离、为什么管理入口收敛到标题）见
> [`sidebar-context-vs-center.md`](sidebar-context-vs-center.md)。
| 当前任务 | **Task flow**：本次任务的四步 | 独立分组 | 步骤条（竖线 + done/current/pending 三态） | 在创建流程里跳步 |
| 历史任务 / 术语与翻译记忆 | **Global navigation**：跨项目的资料 | 「工作区」分组 | 常规导航项 | 进入各自页面 |
| AI引擎（贴底 status module） | **Runtime status**：当前模型 / 连接状态 | 侧栏底部，`provider_status` | status module（不是导航行）：13px/600 status label + 11px 两行读数 + 右对齐文字 action | 「管理」进入 AI Engine / Model Center（**唯一入口**） |

三条边界：

- **不把 Project Center 放进「工作区」**：那一组是 global navigation，Project 不属于它；
- **不把上下文留在顶部、管理入口留在底部**：拆分布局本身就是"两套系统"的成因；
- **不给 Project Center 一个独立行**：标题与独立入口各说一遍同一件事，是这一分组里
  最后一种重复形式；收敛后标题的视觉权重必须**低于** selector（17px/12px/500/透明底
  vs 46px/12.5px/600/中性面 + 1px 细边），"能点"只体现在 hover、下划线与 chevron 上。
  而 selector 自己也必须**低于**「新建任务」CTA（CTA 是实心主色）。


## 2. Sidebar 低保真结构

```text
┌ 侧栏 ────────────────────────┐
│ [Logo]                      │
│                             │
│ ┌─────────────────────────┐ │
│ │ ＋ 新建任务              │ │  ← 全局创建动作（流程内退成 secondary）
│ └─────────────────────────┘ │
│                             │
│ 项目 ›                       │  ← 分组标题 = Project Center 入口（左对齐 / chevron 紧跟）
│ ┌─────────────────────────┐ │
│ │ 📁 示例项目        ▾    │ │  ← 主控件：中性面 / 1px 细边 / 46px / 11px 圆角
│ └─────────────────────────┘ │
│   ┌───────────────────────┐ │  ← 展开才渲染的轻量下拉面板
│   │ ✓ 未分类任务  Inbox 20│ │  ← compact row：38px / 名称省略 / 计数靠右 / 行间 2px
│   │   示例项目          3 │ │
│   │ ──────────────────     │ │  ← 细 divider（8/6px，不是段落间距）
│   │ ＋ 新建项目            │ │  ← footer action row：透明、hover 才出浅底、40px
│   └───────────────────────┘ │
│                             │
│ ───────────────────────────  │  ← 分隔线：项目 ▸ 任务
│ 当前任务                     │
│  ● 01 文档与画像            │
│  ○ 02 翻译策略              │
│  ○ 03 交付内容              │
│  ○ 04 确认运行              │
│                             │
│ 工作区                       │  ← 只有跨项目的资料（AI Engine 不在这里）
│  ⏱ 历史任务                 │
│  ▤ 术语与翻译记忆           │
│                             │
│ ───────────────────────────  │  ← 分隔线：导航 / runtime status
│ ○ AI引擎              管理  │  ← status label（左）+ 唯一 action（右）
│   deepseek-v4-flash-0731    │  ← secondary text：当前模型
│   尚未验证连接               │  ← tertiary/status text：连接状态
└─────────────────────────────┘
```

三种状态下的差异：

| 状态 | selector | 分组标题「项目」 |
| --- | --- | --- |
| 未选项目（新建任务 / 无上下文） | 中性态：`#f6f8fb` 底 + 1px 边框 + 「未选择项目 ▾」；下方一行 `正在查看未分类任务`（仅未分类任务视图） | 标题字型，无当前页标记 |
| 已进入项目（项目详情 / 任务工作区） | 填充态：`primary-soft` 底 + 项目名 + `folder_open` 图标 | 标题字型，无当前页标记（当前态属于 selector） |
| 展开切换面板 | 触发器变"已按下"（`.tp-nav-open` → 更深的 `primary-soft` 面 + 边框），面板在它下方展开 | 不受影响 |
| 停在 `/projects` 列表页 | **与上一行相同**：上下文保留、文案不变（管理页是纯导航，不修改上下文） | 文字升到 ink + chevron 上色 = "你在这儿" |


## 3. 具体组件改动清单

| # | 组件 | 改动 | 为什么 |
| --- | --- | --- | --- |
| 1 | 分组标题 | `项目上下文` → `项目`，并**升级为 Project Center 导航入口**（按钮 + 右侧 chevron + hover 态 + `cursor:pointer`） | 「项目」是分组名；「项目上下文」降为概念名，只出现在正文说明里。管理入口收敛到标题，避免同一分组里出现两个指向管理页的入口 |
| 2 | 分组容器 | `st.container(key="project_nav_group")`：标题 + selector 包进同一容器，`gap: 4px` | 同一分组 = 同一容器：相邻关系由容器保证，而不是靠视觉巧合 |
| 3 | 上下文 selector | 降视觉权重：46px / 11px 圆角 / 1px 细边 / 中性 surface / 12.5px/600，focus ring 只留一条 2px outline；规则**钉在触发器自己的 key**（`st-key-current_project_selector`）上 | 它仍是组内最重的一件，但必须低于「新建任务」CTA；旧的 `primary-soft` + `#c8dcff` 边框 + Streamlit 自带 ring 叠成"双层粗蓝框"。钉在自己的 key 上是为了防止规则泄漏给面板（见 §8 风险） |
| 4 | Project Center 入口 | 独立行（`project_center_entry`）**删除**，收敛为标题 `project_section_header` / `project_section_header_button` | 独立行与标题各说一遍同一件事，还和 selector 争视觉重量 |
| 5 | Project Center "当前页" | 空语义标记 `<span class="tp-nav-current">` 移到标题容器，仅在列表页渲染；样式改为"文字升 ink + chevron 上色" | 同组里"你在这儿"只亮一次；标题是 22px 的窄行，左侧竖条那种语法在这里会显得笨重 |
| 6 | 「工作区」分组 | 只保留 历史任务 / 术语与翻译记忆。独立「⚙ 设置」行**删除** | 防止"Project Center = 第三个资料库"的误读回归；同时消除"设置行 = AI Engine 管理"的重复导航 |
| 6b | AI Engine 贴底区 | 保留 `provider_status` 作为 runtime status module：`AI引擎` 是 status label、「管理」是唯一 action、模型名 secondary、连接状态 tertiary/status；不套 `library_nav` 导航行样式，整块不可点 | 它承担的是 runtime 状态 + 配置入口，不是「工作区」分组的第四行导航；与 历史任务 / 术语与翻译记忆 使用不同的视觉语法 |
| 7 | 切换面板 | 行从"两行大卡"改为一句话的 **compact row**：`switcher_row_*` 可见行 + `switcher_pick_*` 透明点击层；单行 30px、名称 ellipsis、计数靠右；列表内滚动；面板/列表/行/名称四级 overflow 硬化 | 侧栏宽度本来就窄，两行文案 + 固定 52px 高必然换行溢出；快速切换只需要"名称 + 数量" |
| 8 | 面板文案 | 移除常驻说明「新任务将默认加入所选项目，已有任务不会移动」，改到 selector 的 `help` | switcher 只负责 switching，不负责产品教育 |
| 9 | 正文上下文块 | 文案微调：`[更改]` / `[选择项目]` 的 help 指向侧栏同一个选择器 | 明示唯一来源，正文不制造第二个答案 |
| 10 | 新建任务按钮 / 任务步骤 | **不变** | 不碰创建流程与 task flow |


## 4. 实现修改

`app.py`

- **CSS**：`st-key-current_project` 段落之后是「项目」分组与切换面板两段。
  - 分组标题（`[class*="st-key-project_section_header"]`）：`display:flex` +
    `min-height:17px`（12 × 1.4）+ `margin: 18px 0 6px` + 12px/500/`#7c8799`
    —— 与 `.tp-nav-label` **同一条水平基线**；`justify-content:flex-start`（左对齐），
    内层 `> div` 是 `flex: 0 0 auto`（**不能**是 `flex:1`，否则 chevron 被顶到侧栏最右、
    读成一级大导航）；hover 只给"升色 + `p` 下划线 + chevron `translateX(2px)`"，
    不加卡片底；`::after { content: "›" }` 是唯一的导航 affordance；
    `:focus-visible` 有 outline；当前页态只把文字升到 `--tp-brand-ink` + chevron 上色，
    **刻意不复用** `--tp-primary-soft`（那是 selector"已进入项目"的语法）；
    - ⚠️ 标题里的 `p` 必须显式 `font-size: 12px !important`：Streamlit 给 button 里
      的 markdown 容器打了正文级 14px 且**不继承**按钮字号（`font-size: inherit`
      在这里拿到的还是 14px），不压回来标题会比「工作区」大一号、还会在 17px 行盒里溢出；
  - `.tp-nav-current { display: none }` + 它所在的空元素容器 `display: none`，不占用分组 `gap`；
  - 切换面板：`[class*="switcher_panel"]` / `[class*="switcher_list"]` 全部
    `box-sizing:border-box; min-width:0; max-width:100%`，面板 `overflow-x:hidden`，
    列表 `max-height:min(42vh,300px); overflow-y:auto; overflow-x:hidden`；
  - 行：`[class*="switcher_row_"] { position:relative; min-width:0 }` + `.tp-switch-row`
    （`display:flex; align-items:center; min-height:38px; border:0`）+ `.tp-switch-name`
    （`flex:1 1 auto; min-width:0` + ellipsis）+ `.tp-switch-count`（`flex:0 0 auto` +
    `tabular-nums`）+ `[class*="switcher_pick_"] { position:absolute; inset:0; opacity:0 }`
    （透明点击层，同历史任务卡套路）；当前行只加 `background: var(--tp-tint-active)`，
    hover 只加 `--tp-tint-hover`，**都不描边**；
  - 行间距：`row-gap: 2px` 必须写在 `[class*="switcher_list"]` **自己**身上 ——
    `st.container(key=…)` 的 key 是打在 stVerticalBlock 上的，不是外面再包一层，
    `> [data-testid="stVerticalBlock"]` 那种写法会静默落空、退回默认 8px；
  - footer「＋ 新建项目」：action row（`min-height:40px`、透明、无边框、无阴影，
    hover 才 `--tp-tint-hover`），与列表之间是 `hr`（margin 收到 8/6px）；
  - ⚠️ **对勾必须写字面 `✓`**：这段 CSS 是普通 Python 字符串，写成「反斜杠 + 2713」
    会被 Python 的**八进制转义**吃掉，渲染出 `¹3`。测试已钉住（见 §6）。
- **侧栏渲染**（`with st.sidebar:`）
  - `project_nav_group` 容器内：`project_section_header`（可选 `tp-nav-current` →
    `project_section_header_button`「项目」→ `_open_project_list()`）→
    `_sync_task_project_context()` → `_sidebar_project_switcher(...)`；
  - `_project_center_current = app_view == "projects" and not workspace_mode
    and _projects_route() == "list"`：只在**列表路由**打当前页标记。判据从
    "有没有上下文"改为"路由是列表"，因为管理页不再清空上下文（见
    [`sidebar-context-vs-center.md`](sidebar-context-vs-center.md)）；
  - 独立的「项目中心」行与它的 CSS / key 全部删除。
- **切换面板正文**
  - 新增 `_render_project_switcher_row(ids, project, context_id)`：渲染 `tp-switch-row`
    可见行（check 槽 + 名称 + 可选 `Inbox` 标签 + 计数）+ 铺满它的透明按钮；
  - 锚点注册表新增 `row_frame`（`switcher_row_` / `task_switcher_row_`）；
  - 搜索阈值抽出为 `_PROJECT_SWITCHER_SEARCH_MIN = 5`；
  - 移除面板常驻 caption；`switch_effect = "仅影响新任务，已有任务不会移动"` 进
    selector 的 `help`。
- **文案 / 文档字符串**：`_sidebar_project_switcher` docstring 与两个 help 文案改为指向
  「项目」分组标题；修正"轻量 Popover"这类陈旧措辞（实际是受控会话标记驱动的就地面板）。


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
| `test_sidebar_project_group_holds_context_and_management` | 纯标题只剩 `["工作区"]`（「项目」已是导航按钮）；标题在 selector 之前、整组在「历史任务」之前；侧栏没有独立「项目中心」行 |
| `test_project_center_header_is_lighter_than_the_selector` | CSS：selector 46px + `border-radius:11px` + 1px 细边 + 中性 surface + 600；标题 17px + 透明底 + 12px/500 + `justify-content:flex-start` + `::after` chevron；当前页规则里**不得**出现 `--tp-primary-soft` |
| `test_project_center_current_marker_shows_only_on_the_list_page` | 列表页有 `tp-nav-current`；项目详情页没有（当前态归 selector） |
| `test_sidebar_and_body_never_disagree_about_the_context` | 侧栏与正文在两个状态下同时改口，且 `task_project_id` 与上下文一致 |
| `test_project_center_does_not_switch_the_context` | 标题导航**纯导航**：路由落到 `list`、上下文原样保留、管理页真的渲染 |
| `test_context_selector_is_one_compact_control_in_both_states`（沿用） | 未选态仍是同一个 compact 控件，不是虚线大卡片 |
| `test_task_page_change_opens_the_same_switcher_list` | 正文锚点展开同一份列表（`task_switcher_pick_*`），且侧栏锚点保持收起 |

`tests/project_task_navigation_test.py`

| 用例 | 守住什么 |
| --- | --- |
| `test_sidebar_project_group_sits_above_the_workspace_group` | 侧栏纯标题只剩 `["工作区"]`；「项目」标题在 selector 之前且排在「历史任务」之前；没有独立「项目中心」行；**没有独立「设置」行**（见 §9） |
| `test_sidebar_context_is_unselected_without_a_real_project`（沿用） | 「未分类」不被渲染成项目；selector 只有一行 |
| `test_sidebar_selector_stays_compact_without_a_project`（沿用） | 未选态样式契约不变 |
| `test_project_center_entry_returns_to_the_project_list` | 标题进入的是管理页路由（`projects_route == "list"`），且当前上下文不被清空 |
| `test_project_switcher_actions_are_context_only` | switcher 底部只有「新建项目」；「管理所有项目」已退休；侧栏只有一颗管理入口（就是标题） |
| `test_sidebar_switcher_changes_the_context_project` | 面板里**不常驻**说明文案（改到 selector 的 `help`）；当前项 = check + 轻 active 面；Inbox 行保留 `tp-switch-tag` 语义 |

`tests/sidebar_project_switcher_test.py`（**20 个用例**）逐条覆盖交互验收、标题导航、
compact row 版式、长名不溢出、列表滚动与搜索阈值、无常驻文案、**Inbox 只有一个焦点**、
**footer 是 action row 而不是卡片** —— 明细见
[`sidebar-context-vs-center.md §6`](sidebar-context-vs-center.md)。

**回归结果**：本组文件的最新一次运行见
[`sidebar-context-vs-center.md §9`](sidebar-context-vs-center.md)（全套 888 passed 的
基线来自收尾轮；收敛轮改动后的定向回归结果同节记录）。


## 7. 视觉验收（真实渲染）

截图归档：[`docs/ui-audit/21-sidebar-project-group/`](ui-audit/21-sidebar-project-group/README.md)
（3 张：未选上下文 / 列表页当前页标记 / 已选上下文的侧栏↔正文一致）。用
`scripts/ui_screenshot.py` + 一次标题点击，在 1440×900 下核对：

- 新建任务页：分组标题「项目」(带 chevron) → 中性 selector → 分隔线 → 当前任务四步 →
  「工作区」三项；层级一眼可辨，标题明显比 selector 轻；
- `/projects` 列表页：标题文字升到 ink + chevron 上色；selector 仍是最重的控件；
- 已选上下文：selector 显示项目名，正文上下文块显示同一个项目名，标题无当前页标记。

> 视觉收敛轮的截图单独归档在
> [`docs/ui-audit/22-sidebar-visual-polish/`](ui-audit/22-sidebar-visual-polish/README.md)
> （6 张：收起 / 展开 / footer hover / 整页），并附一份**浏览器 computed style 实测值**
> （标题 17px 与「工作区」同基线、selector 46px/11px/1px 细边、行 38px、行间 2px、
> Inbox 9.5px、footer 40px 透明）。那一份比 §6 的 CSS 断言更硬：断言只能证明样式表
> 里有这条规则，实测值能证明它真的生效。

两个会让截图骗人的坑（踩过）：首次渲染约 20s，截早了只有 Logo；点击后指针停在
按钮上会命中 `:hover`，把当前页样式盖掉 —— 两张意图不同的图会截出**字节相同**的文件，
截图前必须移开指针。

## 8. 风险与未做

- **未做**：分组标题仍是 Streamlit `st.button`（不是原生导航项），因此"当前页"只能靠
  语义标记 + CSS 表达，并且"点击它是导航而不是弹层"由代码结构保证（它只调用
  `_open_project_list()`，不碰任何面板 / Modal 开关）；如果以后引入真正的 nav
  component，这套标记可以直接删除。
- **未做**：`chevron` 用 CSS `::after { content: "›" }` 表达，因此它**不参与可达性**
  （读屏看不到"这是导航"）。帮助信息由按钮的 `help` 承担。
- **未做**：本轮没有给「项目」分组加展开 / 折叠；分组内只有两项，折叠没有收益。
- **未做**：没有做键盘导航（列表行是可聚焦按钮，但面板没有焦点陷阱 / 方向键移动）。
- **风险**：`.st-key-current_project:has(.tp-nav-empty)`、`…:has(.tp-nav-current)`、
  `.st-key-project_section_header:has(.tp-nav-current)` 依赖 `:has()`。项目已有多处使用
  （`st-key-project_row_*`、`library_nav`），属于既有约定，但这些选择器一旦失效，
  "中性态 / 当前态"会静默退回默认样式——因此 §6 的 CSS 断言是必需的，不是可选的。
- **风险**：`.tp-switch-row` 的 overflow 契约分散在面板 / 列表 / 行 / 名称四个选择器上。
  只改其中一处（例如给名称去掉 `min-width: 0`）就会让长项目名把面板顶出侧栏，而且
  **AppTest 看不到**（它不布局）——只能靠
  `test_long_project_names_cannot_overflow_the_sidebar` 断言 CSS 契约本身。
- **风险**：对勾写在 CSS 里，而这段 CSS 是普通 Python 字符串。任何"反斜杠 + 数字"的
  转义写法都会被 Python 吃掉（八进制）。测试已钉住字面 `✓` 并显式禁止 `¹3`。
- **风险（本轮踩到的真 bug）**：selector / 触发器这类按钮规则**不能挂在外层容器上**。
  `.st-key-current_project .stButton button` 是后代选择器，而展开后的面板（列表行 +
  「＋ 新建项目」）就渲染在同一个容器里，于是 selector 的填充色 / 高度 / 圆角被一并
  泄漏给它们——这就是"＋ 新建项目"长成一块浅蓝卡片的根因。现在规则钉在触发器自己的
  key 容器 `[class*="st-key-current_project_selector"]` 上，状态标记（`.tp-nav-empty` /
  `.tp-nav-open`）因为是**兄弟**节点，`:has()` 只能写在外层再指回触发器；
  `sidebar_project_switcher_test.py` 里有一条断言显式禁止 `.st-key-current_project
  .stButton button {` 重新出现。task 锚点同理（`task_project_change` / `task_project_pick`）。
- **风险**：`st.container(key=…)` 的 key 打在 **stVerticalBlock 自己身上**，不是外面再包
  一层。所以"收紧组内间距"必须写成 `[class*="…"][data-testid="stVerticalBlock"]`，
  只写 `> [data-testid="stVerticalBlock"]` 会静默落空、退回 Streamlit 默认的 8px
  （看起来就是"行与行之间有卡片式大间隔"）。


## 9. AI Engine 入口收敛（本轮）

### 9.1 删除了什么

| # | 被删除的东西 | 原来的作用 | 处置 |
| --- | --- | --- | --- |
| 1 | `library_nav` 里的 `st.button("设置", icon=":material/settings:")` | 侧栏「工作区」分组的第三行导航 | **删除**。它当时唯一的落点是 `app_view == "settings"`（AI Engine / Model Center），与贴底「管理」完全同义 |
| 2 | 该行的点击分支 `st.session_state.app_view = "settings"` | 进入 Model Center | 随行删除；侧栏里指向 Model Center 的赋值现在**只剩 `manage_provider` 一处**（AST 守卫） |
| 3 | `:material/settings:` 图标用法 | 该行的图标 | 随行删除；`app.py` 里已无引用 |

**没有删除**（重要）：`app_view == "settings"` 这个 route 本身，以及它渲染的
AI Engine / Model Center 页面。它不是「设置行」的私有实现——主工作区里还有多处
就地入口复用它（新建任务第 4 步的「前往设置 / 检查设置 / 测试连接」、翻译与审校
流程里的「前往 AI 设置 / 配置 API Key」，以及 `_open_provider_settings()`）。
删掉的只是**侧栏这一层重复的导航 surface**。

### 9.2 AI Engine 贴底区的最终职责

`provider_status`（`st.container(key="provider_status")`）是一个 **runtime status
module**，同时承担四件事：

1. 当前 AI runtime 状态（左侧圆点 + `is-*` 语义 class）
2. 当前模型展示（`ai_model`，secondary text）
3. 连接状态展示（`ai_view["label"]`，tertiary / status text）
4. AI Engine / Model Center 的**唯一**管理入口（「管理」action）

视觉语义：

| 成分 | 语义 | 实现 |
| --- | --- | --- |
| `AI引擎` | status label | `13px/600` + 状态圆点（`::before`），**不可点击** |
| `管理` | 明确 action | 文字按钮（透明底、右对齐、`--tp-primary`），唯一可点元素 |
| 模型名 | secondary text | `.tp-engine-model`（`--tp-sub`） |
| 连接状态 | tertiary / status text | `.tp-engine-state`（`--tp-faint`；`is-connected` / `is-error` 换成语义色） |

约束：**不套用** `.st-key-library_nav` 的导航行语法（48px 行高 + hover 面 + primary
选中态），整块**不做成** clickable card——否则它会与「历史任务 / 术语与翻译记忆」
读成同一类东西。

### 9.3 「设置」的恢复条件（本轮**不实现**）

只有当产品真的拥有**应用级**配置信息架构时才恢复「设置」，届时两者必须语义不同：

```text
Settings（General）      -> /settings            语言 / 外观 / 存储与导出默认值 /
                                                 隐私与数据 / 快捷键 / 应用默认值 /
                                                 更新与偏好
AI Engine 管理           -> /model-center        或 /settings/ai-engine
```

在这些能力存在之前，**不要**造一个空的 General Settings 页面来"填上"那个位置。

### 9.4 本轮测试

`tests/sidebar_ai_engine_footer_test.py`（7 个用例）：

| 用例 | 守住什么 |
| --- | --- |
| `test_sidebar_source_has_no_standalone_settings_nav_row` | 侧栏源码不再渲染「设置」行；「管理」action 仍在 |
| `test_sidebar_has_exactly_one_entry_into_the_model_center` | AST：侧栏里 `app_view = "settings"` 的赋值**恰好一处**，且落在 `manage_provider` 分支里 |
| `test_ai_engine_footer_still_renders_as_a_status_module` | status module 仍在，且不伪装成 `.tp-nav-label` 分组标题、不是可点导航项 |
| `test_manage_action_still_opens_the_model_center` | 「管理」仍进入 Model Center（服务商 / 模型选择框可见） |
| `test_model_center_route_is_unaffected_by_the_removed_row` | 直接落到 `app_view == "settings"` 仍渲染配置页；工作流内「前往设置」仍在 |
| `test_current_model_is_shown_in_the_footer` | 当前模型正确显示，切换后不残留旧模型名 |
| `test_connection_state_is_shown_in_the_footer` | 凭据缺失 / 未验证 / 连接正常 / 连接失败四种状态与 `is-*` 语义同步 |

同时更新：`tests/app_boot_test.py`（原来点侧栏「设置」，改点「管理」）、
`tests/project_task_navigation_test.py::test_sidebar_project_group_sits_above_the_workspace_group`
（断言 `"设置" not in sidebar_labels` 且 `"管理" in sidebar_labels`）。

### 9.5 视觉验收（真实渲染）

截图归档：[`docs/ui-audit/24-sidebar-ai-engine-entry/`](ui-audit/24-sidebar-ai-engine-entry/README.md)
（1 张：收敛后的侧栏整页）。核对点：「工作区」只剩两行；贴底 status module 是
`AI引擎` + 右对齐 `管理` + 两行读数，且 `管理` **不是**描边按钮。

⚠️ 一个静默失效点：**不要**给「管理」加 `help=`。tooltip 会把 `button` 包进
`stTooltipHoverTarget`，而把「管理」压成文字 action 的那条规则
（`.st-key-provider_status .stButton > button`）是**直接子选择器**——加 tooltip 会让它
静默落空，退回 Streamlit 默认描边按钮。`test_manage_action_has_no_tooltip_wrapper`
钉住了这一条；要加 tooltip 必须先把它改成 `.stButton button` 后代写法。
