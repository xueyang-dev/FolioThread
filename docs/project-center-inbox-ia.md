# Project Center / New Task：Inbox 语义分离与项目卡密度改造

2026-09-17。范围：`app.py` 的 Project Hub（`/projects`）、Task Inbox（系统工作区）、
以及新建任务第 1 步的「项目上下文」区块。不涉及翻译内核、路由表或数据模型。

判定：**ready for review**。信息架构与组件契约已落地，回归测试见第 5 节。

---

## 0. 问题归因

| 现象 | 真实原因 | 归属层 |
| --- | --- | --- |
| New Task 里 Inbox 像一张小项目卡 | 未分类态与"已选项目"态**共用同一块 markup 的形状**，只换了文字与描边色 | 组件语法 |
| Project Center 里两者语义区分不明显 | 未分类入口与项目卡**同处一个列表流**，都是 1px 实线 + 白面 + 12px 圆角；差别只在一句副标题 | 页面结构 |
| 项目卡信息拥挤、层级不清 | 卡片把 5 类事实（名称/描述/任务分布/最近工作/知识+时间）压进同一列，靠 6px gap 硬排；底部 CTA 与元信息争行 | 视觉密度 |
| 说明文案过长 | 空态写了一句完整长句作为 onboarding，占两行且与 CTA 抢注意力 | 文案 |
| **英文 `inbox` 成为主视觉** | **不是文案问题**：`.tp-project-context` 的图标规则漏了 `font-family`，图标名被当**字面文本**画了出来 | CSS 缺陷 |

一句话结论：**这不是配色问题，是"系统容器"与"用户对象"用了同一套元素语法。**
因此没有改主色、没有改字体，只改了元素语法、区块结构、留白节奏和文案长度。

> **实施期发现（截图验证）：** `inbox` / `folder_open` 原本就被渲染成了界面上的
> 文字，而不是图标。本项目没有全局的 `.material-symbols-rounded { font-family }`，
> 每个使用点都要自己声明；漏掉不报错，只是静默退化成文本。这解释了为什么
> "英文 Inbox 抢主视觉"——它本来就是一行真的英文。已修复并补结构性回归测试。

---

## 1. 信息架构调整方案

### 1.1 语义矩阵（改造后口径）

| 维度 | Inbox / 未分类任务 | Project |
| --- | --- | --- |
| 本体 | system collection（默认收纳区） | user-created knowledge container |
| 所有权 | 系统所有，用户不拥有 | 用户创建、可重命名/归档/删除 |
| 承载 | 尚未归入任何项目的 Task | 任务 + 术语 + 规则 + 翻译记忆 + 人工决定 |
| 上下文继承 | 不继承任何项目术语 / TM / 规则 | 任务继承本项目的术语 / TM / 规则 |
| 元素语法 | sunken 面 + 虚线 + 零阴影 + 单行说明 | 白面 + 实线 + 静置无阴影 + 三段式 |
| 次级动作 | 无（无 overflow menu、无生命周期动作） | 重命名 / 编辑 / 归档 / 导出 / 删除 |
| 点击落点 | 未分类任务列表（Task Inbox） | Project Detail（概览 / 任务 / 知识 / 设置） |
| 计数口径 | "N 个未归入项目的任务" | "N 个任务" + 分布 |

### 1.2 Project Center（`/projects`）结构

```text
Page header        标题「项目」            [+ 新建项目 ▾]
                   └ 副标题：管理翻译任务、项目知识与语言资产

Toolbar           [搜索]      [状态]      [排序]      [▦ | ☰]

系统任务区         未分类任务（Inbox）· 数量 ·「查看 →」
                   └ section note：系统工作区 · 不属于任何项目

我的项目  [N]      ┌ 项目卡 ┐ ┌ 项目卡 ┐
                   └────────┘ └────────┘
```

三条结构规则：

1. **区块顺序固定**：Toolbar → 系统任务区 → 我的项目。未分类不再"漂"在工具栏与
   项目列表之间，而是有自己的 section head，读者先知道"这里不是你的项目"。
2. **两个 section 各自独立**（`project_system_zone` / `project_section`），
   不共用一个列表容器 —— 结构分离优先于视觉分离。
3. **系统任务区只有一个成员**：未分类任务。它是"收纳区"这个词的唯一承载者。

### 1.3 New Task（第 1 步）「项目上下文」

区块只回答"这次任务会落在哪里"，两种状态共用同一个 context block：

```text
未分类态（默认）                    已选项目态
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ 项目上下文                    │   │ 项目上下文                    │
│ [inbox] 未分类任务    Inbox   │   │ [folder] 沙特教材本地化        │
│ 任务将保存到系统工作区，       │   │ 继承项目术语、翻译记忆和规则   │
│ 不继承项目术语、翻译记忆与规则 │   │                 [更改]        │
│ [选择项目]                    │   └──────────────────────────────┘
└──────────────────────────────┘
```

- 英文 `Inbox` 从"主标题"退成状态行右侧的 11px 低对比 tag；
- 说明文案改为**面向后果**：说清"不继承什么"，而不是只说"未分类"；
- 归属仍只有一个来源（侧栏 switcher），这里**只读**，不新增第二个选择器。

---

## 2. 低保真布局建议

### 2.1 项目卡：三段式（152px 最小高度，18/20px 内边距）

```text
┌────────────────────────────────────────────────────┐
│  ▤  项目名称                          已归档   ⋯   │  ① 身份
│                                                    │
│  2 个任务   2 待开始                               │  ② 状态（主）
│  教材本地化                                        │     辅助说明（次）
│  最近  第一章.docx  待开始                         │
│  ──────────────────────────────────────────────    │  hairline
│  + 创建任务        术语 1 · 规则 1    刚刚更新      │  ③ 行动
└────────────────────────────────────────────────────┘
```

空项目是同一条骨架，只换两个元素：

```text
│  尚无任务                                          │
│  可开始积累术语与翻译记忆                          │  ← 一行，取代原长句
│  + 创建任务                        刚刚更新        │
```

要点：

- **垂直节奏**由 body 的 5px gap + head 的 12px 下边距承担，不是靠分割线；
- **footer 用一条 hairline 分隔**，并把「CTA」与「弱元信息」分到两侧；
- **CTA 槽位固定 88px**（`tp-pcard-cta-slot`），真实按钮绝对定位在 `left:20px /
  bottom:16px`，因此文字永远不会压住按钮；
- **静置零阴影**，hover 才出现 `--tp-shadow-md`：网格里多张卡不再像并列浮层。

### 2.2 系统任务区：与项目卡刻意不同构

```text
系统任务区   系统工作区 · 不属于任何项目
┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
  [inbox]  未分类任务   Inbox          2 个   查看 → 
           尚未归入任何项目的任务
└ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```

| 属性 | 项目卡 | 未分类入口 | 意图 |
| --- | --- | --- | --- |
| 边框 | `1px solid` | `1px dashed` | 虚线 = 系统兜底容器 |
| 面 | `--tp-surface` 白 | `--tp-surface-sunken` | 降一级，不与项目同面 |
| 阴影 | 静置无 / hover 有 | 始终无 | 不表达"可拾取的对象" |
| 圆角 | 14px | 12px | 避免读成同一类对象 |
| 图标底 | `--tp-primary-soft` 蓝 | 中性 `#e7eaf0` | 蓝色图标会读成"又一个项目" |
| 高度 | ≥152px | 72px | 收纳区不需要卡片面积 |
| hover | 边框 + 阴影 | 边框 + 面色 | 无"抬升"反馈 |

---

## 3. 组件层级梳理

### 3.1 组件树

```text
Project Hub (project_hub)
├── project_header ─────────────── 标题 + 新建项目 popover
├── project_toolbar ────────────── 搜索 / 状态 / 排序 / 视图切换（一个工具栏）
├── project_system_zone ────────── 【系统容器区】
│   ├── section head「系统任务区」+ note
│   └── project_uncategorized ──── 整条可点的 system row
│       ├── tp-uncat-icon        中性图标
│       ├── tp-uncat-title       未分类任务 + tp-uncat-tag「Inbox」
│       ├── tp-uncat-right       数量 + 「查看 →」
│       └── tp-uncat-meta        尚未归入任何项目的任务
└── project_section ────────────── 【用户对象区】
    ├── section head「我的项目」+ count badge + filter note
    └── project_grid / project_list
        └── project_row_{id}
            ├── tp-pcard
            │   ├── tp-pcard-head ── icon + name + chip
            │   ├── tp-pcard-body ── tp-pcard-work / -desc / -recent|-hint
            │   └── tp-pcard-foot ── cta-slot + tp-pcard-meta(knowledge + updated)
            ├── (整卡点击层) project_open_{id}
            ├── project_empty_cta_{id} →「+ 创建任务」
            │   或 project_view_cta_{id} →「查看项目」
            └── project_menu_{id}（⋯ overflow，secondary only）

New Task step 1 (task_settings_grid)
└── task_setting_project
    └── task_project_context
        ├── tp-context-head「项目上下文」
        ├── tp-project-context.is-selected | .is-empty
        │   └── icon + tp-context-copy(status + tag + note)
        └── task_project_change / task_project_pick
```

### 3.2 组件契约（改了什么）

| 组件 | 契约变化 | 兼容性 |
| --- | --- | --- |
| `_uncategorized_strip` | 包进 `project_system_zone`；标题加 `Inbox` tag；meta 文案不变 | 容器 key、按钮 key、count 位置全部保留 |
| `_project_card_markup` | 三段式；新增 `tp-pcard-body` / `tp-pcard-meta`；空态长句 → `可开始积累术语与翻译记忆` | `tp-pcard-recent`、`>N</strong> 个任务`、知识摘要、description 全部保留 |
| `_project_card` | 有任务的项目新增 `查看项目` ghost CTA（`project_card_view_{id}`） | 空项目的 `project_card_create_{id}` 不动 |
| `_render_task_project_context` | 增加 `tp-context-head` 标签；拆出 `tp-context-status` + `tp-context-tag`；note 文案改为"不继承项目术语、翻译记忆与规则" | `is-selected` / `is-empty`、按钮 key 保留 |
| CSS `.tp-pcard-*` | 去掉静置阴影、footer 加 hairline、padding 14/16 → 18/20、min-height 126 → 152 | 未删任何类名 |
| CSS `.st-key-project_view_cta_` | 新增（与 empty_cta 同构，独立规则块） | `empty_cta` 规则块**逐字未动**（被测试按字面匹配） |

### 3.3 交互一致性（第 5 条要求的核对结果）

| 场景 | 期望 | 现状 |
| --- | --- | --- |
| 点 Inbox | 进未分类任务列表，非 Project Detail | 既有实现，本次加测试固化 |
| 点 Project | 进 Project Detail | 既有实现，本次加测试固化 |
| 建任务未选项目 | 默认落 Inbox（落盘 `project_id: null`） | 既有实现，测试覆盖 |
| 建任务已选项目 | 继承该 Project context | 既有实现，测试覆盖 |
| 从空项目卡建任务 | 进创建流程且自动带该项目 | 既有实现，测试覆盖 |

---

## 4. 实际改动清单

| 文件 | 位置 | 改动 |
| --- | --- | --- |
| `app.py` | CSS `.tp-project-context*` | 新增 `tp-context-head` / `tp-context-status` / `tp-context-copy` / `tp-context-tag`；未分类态改 sunken 面；min-height 44 → 56；**补上缺失的 `font-family: "Material Symbols Rounded"`** |
| `app.py` | CSS `.st-key-project_system_zone` / `.st-key-project_uncategorized` | 新增 zone 样式（含 section head 左对齐）；入口改虚线 + sunken + 零阴影 + 72px；新增 `.tp-uncat-tag` |
| `app.py` | CSS `[class*="st-key-project_row_"]` / `.tp-pcard-*` | 卡片瘦身：18/20 padding、152 min-height、零静置阴影、`tp-pcard-body`、hairline footer、`tp-pcard-meta`、updated 降到 `#b0b8c4`；新增"拉满链"（否则 `margin-top:auto` 失效、同排卡底边参差） |
| `app.py` | CSS `.st-key-project_view_cta_` | 新增「查看项目」ghost action 规则 |
| `app.py` | `_project_card_markup` | 三段式重构 + 空态短文案 + 常驻 CTA 槽位 |
| `app.py` | `_project_card` | 按任务数切换底部 CTA 动词 |
| `app.py` | `_uncategorized_strip` | 包进系统任务区 section + `Inbox` tag |
| `app.py` | `_render_project_list` | 更新注释以固化"两个 section"的口径 |
| `app.py` | `_render_task_project_context` | context block 重构（标签 + 状态行 + tag + 新说明文案） |

---

## 5. 测试覆盖

新增 `tests/inbox_project_density_test.py`（20 项），并在两处**主动**改写了旧契约断言。

| 需求 | 测试 |
| --- | --- |
| 未分类任务显示逻辑 | `test_project_center_separates_system_zone_from_my_projects`、`test_uncategorized_entry_uses_system_syntax_not_card_syntax`、`test_uncategorized_inbox_word_is_a_tag_not_a_title`、`test_uncategorized_entry_describes_itself_without_repeating_the_count` |
| Inbox 与 Project 点击行为差异 | `test_inbox_entry_lands_on_the_task_list_not_a_project_page`、`test_project_card_lands_on_the_project_detail_page`、`test_inbox_has_no_project_lifecycle_actions_on_the_hub` |
| 空项目状态显示 | `test_empty_project_card_is_a_short_hint_plus_one_real_cta` |
| 从项目中心创建任务 | `test_create_task_from_the_empty_project_card_carries_the_context`、`test_project_card_with_tasks_swaps_the_cta_verb_in_the_same_slot` |
| New Task 上下文切换 | `test_new_task_context_block_switches_between_inbox_and_project`、`test_new_task_context_block_is_not_a_project_card`、`test_context_heading_marks_the_block_in_both_states`、`test_new_task_without_a_project_falls_back_to_the_inbox_context` |
| 视觉密度控制 | `test_project_card_is_a_three_zone_layout_with_a_separated_footer`、`test_project_card_updated_time_is_the_weakest_element`、`test_project_card_has_breathing_room_and_no_resting_shadow`、`test_card_zones_stretch_so_footers_align_across_a_row` |
| 实施期发现的缺陷防线 | `test_every_icon_rule_binds_the_icon_font`（图标规则必须绑定图标字体）、`test_card_zones_stretch_so_footers_align_across_a_row`（同排卡片底边对齐） |
| 死 CSS 清理防线 | `test_project_row_rule_holds_only_the_overlay_anchor`（`[class*="st-key-project_row_"]` 恰好两条规则：锚点 + hub 紧凑卡） |

被改写的旧断言（因为文案契约本身按要求变了）：

| 文件 | 旧断言 | 新断言 |
| --- | --- | --- |
| `tests/project_task_navigation_test.py` | `创建第一个翻译任务，开始积累术语、规则和项目记忆。` in page | `可开始积累术语与翻译记忆` in page，且旧长句 **not in** page |
| `tests/project_context_hierarchy_test.py` | `不继承项目上下文` in page | `不继承项目术语、翻译记忆与规则` in page + Inbox 不得是 `<strong>` / `<h1>` |
| `tests/project_context_hierarchy_test.py` | `"未分类任务" in page`（只要求出现过） | `"<strong>未分类任务</strong>" in page`（收紧：必须是主视觉状态，不是随便出现一次） |

运行（推荐用仓库内 runner，它逐文件独立进程并自动分流两类测试）：

```bash
venv/bin/python scripts/run_regression.py -k inbox_project
venv/bin/python scripts/run_regression.py -k project
venv/bin/python scripts/run_regression.py            # 全量
```

> **不要**把三个 project 系列文件串在一条 pytest 命令里跑：AppTest 每项约 10s，
> 串进一个进程会触发 OOM（进程被 SIGTERM 137 杀掉）。runner 天然逐文件隔离。

### 5.1 真实渲染验证（截图）

`AppTest` 只看元素树，看不到留白、底部对齐与图标字形。因此用真实浏览器补了一轮：

`docs/ui-audit/19-project-center-inbox/` —— Project Center 首屏、新建任务的未分类态
与已选项目态共 3 张 1440 × 1080 截图。**这一轮抓到了两个 AppTest 看不见的问题**：

1. 图标被渲染成字面文本（见第 0 节），已修复；
2. `.tp-pcard-foot` 的 `margin-top:auto` 因 Streamlit 的 markdown 容器不参与拉伸而
   失效，同排卡片底边会参差 —— 补了"拉满链"与兜底 min-height，并加了回归测试。

复现步骤见该目录的 `README.md`。

### 5.2 全量回归（改动是否波及其他模块）

为了确认 `app.py` 的 CSS / markup 改动没有外溢，跑了一遍**全仓测试**。统计口径把两类
测试分开，避免把 `app_boot_test.py` 重复计入（否则会被误读成 63 个文件）：

| 指标 | 值 |
| --- | --- |
| 测试文件总数 | **62** |
| ├ pytest 风格 | **61** → **874 passed / 0 failed / 0 skipped / 0 xfailed** |
| └ 脚本式 smoke | **1**：`tests/app_boot_test.py`，`venv/bin/python tests/app_boot_test.py` → passed |
| 有效失败 | **0** |
| 总耗时 | 106m48s |

跑法是**逐文件独立进程**，不是串在一个 pytest 进程里 —— 本项目的 `AppTest` 会为每个
文件构建完整应用树，串跑多文件会撞内存峰值被 SIGTERM 137 杀掉，那样得到的"失败"是假阳性。

两类测试由 `scripts/run_regression.py` 按**文件内容**自动分流，不写死文件名：

- pytest 风格（有 `def test_*` / `class Test*`）→ `python -m pytest <file> -q --no-header -p no:cacheprovider`
- 脚本式（无 test 函数、有 `__main__`）→ `python <file>`

```bash
venv/bin/python scripts/run_regression.py                 # 全量
venv/bin/python scripts/run_regression.py -k project      # 定向（逗号分隔可多选）
```

一个易被误判为回归的点：`tests/app_boot_test.py` 由 pytest 跑时退出码为 **5**
（"未收集到任何测试"）。该文件是**脚本式测试**（`def main()` + `if __name__ == "__main__"`），
本就不走 pytest；正确跑法是 `venv/bin/python tests/app_boot_test.py`，实测输出
`AppTest 启动测试通过 ✅`。**这不是失败，也不应"修"成 pytest 风格** ——
改成 pytest 风格会把它的断言散成一堆用例，失去"整应用能否起来"的单点信号。

另一个环境陷阱（会让同一批测试"第二次跑"整片报错，与代码无关）：受限环境把 Python 的
文件操作代理给宿主后，`mkdir(exist_ok=True)` 的 `EEXIST` 会被抛成致命错误，而 pytest 的
basetemp 是固定名 `$TMPDIR/pytest-of-<user>`，于是后续每个 pytest 进程都在 setup 阶段
报错（退出码 1 且没有汇总行）。`scripts/run_regression.py` 为每个文件分配全新的私有
临时目录并同时指定 `TMPDIR` 与 `--basetemp`，从根上规避。

逐文件结果留档：`docs/ui-audit/19-project-center-inbox/regression.md`
与同目录 `regression-summary.tsv`（机器可读）。

---

## 6. 风险与后续

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| 卡片上的事实变多 | 有任务且有 description 的卡会显示 3 行 body | description 单行截断并按 `--tp-sub` 弱化；若仍嫌重，下一步把 description 挪进 hover tooltip 或详情页 |
| `查看项目` 与整卡可点重复 | 两个入口做同一件事 | 有意为之：显式 affordance 优于"猜整块能点"；两者都走 `_open_project` |
| LD 断言脆弱 | 依赖具体 hex 值 | `_color_value` 会把 `var(--token)` 解析到色板，改 token 值不会误报；但改语义（更新时间不再最弱）会立刻失败 —— 这是期望行为 |
| 图标静默退化成文本 | 漏写 `font-family` 不报错，只在渲染时把图标名当文字画出来 | 已补 `test_every_icon_rule_binds_the_icon_font`；新增图标使用点时仍须先声明字体 |
| 静置留白观感 | 卡片 152px 起跳，空项目卡也会占满一行高度 | 与"低密度、可扫描"的目标一致；若觉得偏高，优先调 body 的 gap 而不是砍 padding |
| 测试耗时 | AppTest 每项约 10s，本文件 20 项约 3.5 min | 与既有 project 系列一致，可接受 |

未做（刻意）：

- 没有引入新的设计 token、没有新建组件文件 —— 全部在既有 CSS/markup 契约内完成；
- 没有改 `_empty_projects_state`（"一个项目都没有"的首屏）文案，它不属于本次问题范围；
- 没有动路由表：Inbox 与 Project 的落点差异本来就是对的，本次只是把它**测住**。

### 6.1 死 CSS 清理（本轮已处理）

`app.py` 里 `[class*="st-key-project_row_"]` 曾有**两条**同权重规则：

| 位置 | 内容 | 处置 |
| --- | --- | --- |
| 早期基础规则 | `margin-bottom: 12px` / `padding: 12px 16px` / `border-radius: 10px` / `transition` / `:hover{border-color:#b9c4d4}` | 视觉声明**全部被后置同权重规则覆写**（死代码）→ **删除**，只保留仍被依赖的 `position: relative` |
| Project hub 段落 | 紧凑卡的 padding / radius / background / 阴影 | 生效，**未动** |

`position: relative` 不能一起删：它是 `.stButton { inset: 0 }` 整卡点击层的定位锚点，
删了会让整卡可点失效。因此清理后的规则只剩这一个声明，并加了守卫测试
`test_project_row_rule_holds_only_the_overlay_anchor`（断言该选择器恰好两条行首规则、
第一条只含 `position: relative`、第二条仍是 hub 紧凑卡规则）—— 这个声明承重，而
AppTest 看不见覆盖层逃逸，必须显式测住。

另删 `.st-key-project_row_system`（3 条：`border-style: dashed` / `:hover` / `border-style: solid`）：
该 key 全仓**只有 CSS 引用**，markup 从不生成（系统任务区现在是 `project_uncategorized`
+ `project_system_zone`），属旧设计残留。

清理只删除从未被 markup 生成的 key 的样式、以及被整条覆写的声明，**未触及任何存活的选择器**，
也没有顺带重构其它 CSS。

逐属性核对（证明删除是**中性**的 —— 每条被删声明都有一条同权重、位置更后的规则重新声明，
同权重下 CSS 层叠取后者）：

| 被删声明（原基础规则） | 承接者（Project hub 紧凑卡规则，位置更后） |
| --- | --- |
| `margin-bottom: 12px` | `margin-bottom: 0` |
| `padding: 12px 16px` | `padding: 18px 20px` |
| `border: 1px solid var(--tp-line)` | 同值重声明 |
| `border-radius: 10px` | `border-radius: 14px` |
| `background: var(--tp-surface)` | 同值重声明 |
| `transition: border-color .15s ease` | `transition: border-color .15s ease, box-shadow .15s ease` |
| `:hover { border-color: #b9c4d4 }` | `:hover { border-color: #a9b6c9; box-shadow: var(--tp-shadow-md) }` |
| `position: relative` | **无承接者 → 保留**（`margin-bottom` 等已删，但它必须留下） |

列视图的 `.st-key-project_list [class*="st-key-project_row_"]`（更高优先级，设 `min-height` / `padding`）
完全不受影响。

### 6.2 报告但未处理的遗留

| 项 | 说明 | 为什么不在这轮动 |
| --- | --- | --- |
| `.tp-pcard-row` ×2 | 该类从不出现在 markup 里（项目卡的 list 视图早已不用它） | 属另一类族，超出本轮"只动 `st-key-project_row_` 相关 CSS"的边界 |
| `.tp-chip.is-archived` 早期重复规则 | 被后面一条同选择器规则覆写 | 同上；改动会影响归档 chip 的既有视觉，需要单独一轮评估 |

