# Project Context 与 Project Center：交互语义分离

状态：已实现（`app.py`），回归测试见 §6。
范围：**侧栏「项目」分组内两个条目的交互语义 + 它们的路由/状态契约**。不动翻译内核、
不动 Project 数据模型、不新增第二套 Project 状态。

前置文档：[`sidebar-project-group-ia.md`](sidebar-project-group-ia.md)（把两个条目归并进
同一个「项目」分组）。本文处理归并之后的**遗留问题**：归并解决了"看起来是两套系统"，
但两个条目仍然会打开同一个大型 Modal，于是"切换上下文"和"进入管理页"在行为上还是一件事。

---

## 0. 问题归因

改造前：

```text
[ ↔ 未选择项目 ▾ ]   → 打开大型「切换项目」Modal
[ 📁 项目中心 ]      → 也打开同一个大型「切换项目」Modal（Modal 里有「管理所有项目」）
```

三个具体病灶：

1. **state action 与 navigation 混成一个**：两个视觉层级完全不同的条目（主控件 vs 扁平
   次级入口）打开同一个 Modal，用户无法从交互结果反推它们的职责差别；
2. **Modal 里塞了四种职责**：项目切换 / 未分类任务 / 新建项目 / 管理所有项目。后两者
   与「项目中心」直接重复——同一个页面里出现两个指向管理页的入口；
3. **Modal 是"重"的语法**：切换上下文是高频轻动作，用全屏浮层 + 遮罩表达，代价是每次
   都要"进入一个界面再退出来"。

---

## 1. 调整后的交互模型

| 条目 | 职责 | 点击行为 | 视觉权重 |
| --- | --- | --- | --- |
| 上下文 selector | **Project Context**：state / switch action | 在触发器下方展开**轻量下拉面板**：搜索 + 项目列表 + 新建项目 | 主控件：42px、`primary-soft` 填充、650 字重 |
| 项目中心 | **Project Center**：navigation | 进入管理页路由（`projects_route="list"`）；不展开面板、不弹 Modal、不改上下文 | 次级入口：36px、透明底、500 字重、灰色 |

三条硬边界：

- **面板里没有「管理所有项目」**：管理入口只有「项目中心」一个，重复入口必须删除；
- **「项目中心」绝不打开切换面板**：它是纯导航项，因此"点它会不会弹出 switcher"在结构
  上不可能发生，而不是靠约定禁止；
- **面板内也不做完整项目生命周期管理**：重命名 / 归档 / 删除仍然只在项目页完成。

### 为什么是"就地展开的下拉面板"而不是 `st.popover`

`st.popover` 有两个不能接受的代价（实测，见 §7）：

1. **内容默认常驻渲染**。惰性要靠 `.open`，而 `.open` 只在 `on_change="rerun"` 下才存在；
   切换面板的数据（`list_active_project_options()` + 每行 `project_summary()`）一次约
   **377 ms**。常驻渲染等于给**每一次重跑**都加上这笔开销，而当前 Modal 只在打开时付；
2. **开合状态由前端驱动**，服务端读不到也关不掉。"选中后立即关闭"与"点项目中心不得弹
   switcher"会退化成不可验证的约定。

因此展开态由**会话标记**驱动（`sidebar_project_switcher_open` /
`task_project_switcher_open`）：展开才渲染，关闭是确定性的，且两条边界都能被回归测试
以真实点击路径验证。

---

## 2. 低保真结构

```text
[Logo]  →  [+ 新建任务]

项目
  [ ↔ 未选择项目 / 项目名   ▾ ]      ← 主控件（42px / primary-soft / 650）
  ┌───────────────────────────┐
  │ 新任务将默认加入所选项目…  │      ← 展开后才渲染（收起时零成本）
  │ [ 搜索项目… ]              │      项目多时才出现
  │ ✓ 未分类任务  `系统工作区` │      ← inbox 图标；是 system collection
  │    示例项目                │      ← folder 图标；当前项 = primary 行
  │   ─────────────────────   │
  │   ＋ 新建项目              │      ← 唯一的底部动作
  └───────────────────────────┘
  [ 📁 项目中心 ]                    ← 纯导航；列表路由上带左侧 3px 竖条

────────────────────────────
当前任务  01 / 02 / 03 / 04
工作区    历史任务 / 术语与翻译记忆 / 设置
```

---

## 3. 退休的 legacy Modal code

| # | 被删除的东西 | 原来的作用 | 处置 |
| --- | --- | --- | --- |
| 1 | `_open_project_switcher()` | 置 `project_switcher_open=True` 打开 Modal | 删除；`_toggle_project_switcher(anchor)` 取代 |
| 2 | `_close_project_switcher()`（无参版，pop Modal 标记） | 关掉 Modal | 重写为按锚点写回会话标记 |
| 3 | `_render_project_switcher()`（带 `_modal_container("切换项目")`） | 渲染 Modal 壳 | 删除；正文抽成 `_render_project_switcher_body(anchor)`（不再是 Modal） |
| 4 | 全局分派里的 `if project_switcher_open: _render_project_switcher()` | 跨页面弹 Modal | 删除；该分派现在只剩**管理类**弹窗 |
| 5 | `switcher_manage_all`（「管理所有项目」按钮） | Modal 内的管理入口 | 删除：与侧栏「项目中心」重复 |
| 6 | `section[role="dialog"]:has(.st-key-project_switcher_dialog)` 一整组 CSS（宽度 440px、`stDialogContent` padding、dialog 内的 `hr` 收紧） | 给 Modal 定宽/收紧 | 删除；换成 `[class*="switcher_*"]` 的下拉面板规则 |
| 7 | 旧测试 2 组用例（`test_switch_project_modal_uses_compact_selectable_rows`、`test_switch_project_footer_actions_are_secondary`） | 断言 Modal 的存在与收紧 | 改写为面板版本；新增源码级守卫防回归 |

仍然保留的 Modal：`新建 / 导入 / 重命名 / 编辑 / 归档 / 恢复 / 删除 / 移入任务`。
它们是**低频、需要输入或破坏性**的动作，留在 Modal 里是正确的语法；切换项目不是。

---

## 4. route / state：仍然只有一个 source of truth

| 状态 | 键 | 唯一写入者 | 语义 |
| --- | --- | --- | --- |
| Project Context | `active_project_id` | `_apply_project_context()`（全应用唯一写入口） | "我此刻在哪个项目里工作" |
| Task 归属 | `task_project_id` | `_sync_task_project_context()`（上下文投影） | "本次任务落在哪里" |
| 路由（项目页） | `projects_route`（`list` / `detail`） | `_open_project()` / `_open_project_list()` | "在看列表还是在看某个项目" |
| 面板开合 | `sidebar_project_switcher_open` / `task_project_switcher_open` | `_toggle/_close_project_switcher()` | **纯 UI chrome**，不参与任何 Project 推导 |

### 本轮修掉的隐藏耦合

`active_project_id` 以前同时兼任**路由**和**上下文**：进管理页必须 `pop` 掉它，否则
`_render_projects_view` 会以为要渲染项目详情。于是"逛一次项目中心"会把上下文清空，侧栏
selector 从「项目 A」翻成「未选择项目」——用户读到的是"我的上下文没了"。

现在拆开：

- `projects_route` 表达路由，`_open_project_list()` **不再清 `active_project_id`**；
- `_render_projects_view` 用 `_projects_route()` 决定渲染详情还是列表；
- 依赖"我是不是在项目详情里"的三处（侧栏 `+ 新建任务` 的主/次降级、"正在查看未分类
  任务"提示、「项目中心」的当前页标记）全部改看路由，不再看"有没有上下文"。

因此需求 B 的两条同时成立：**管理页不修改当前上下文**，且**位于管理页时保持 active
state**。没有引入第二套 Project 状态——新增的只是"路由"这一个维度。

同一个规则的可见后果：从「未分类任务」点「← 返回项目中心」（`inbox_back_to_hub`）走的也是
`_open_project_list()`，所以它**同样不再清掉当前上下文**——换的是路由，不是"我在哪个
项目里工作"。旧断言 `not _has_key(active_project_id)` 已按需求 B 改写。

**文案与语义对齐**：该入口叫「返回项目**中心**」（旧文案「← 返回项目」会被读成"回到某个
项目"）。它是 navigation，不是 Project Context mutation —— 产品已确认 `inbox_back_to_hub`
**不作为例外**。

### 冻结的 state model（产品已确认，不再改动）

| 维度 | 键 | 语义 |
| --- | --- | --- |
| Project Context | `active_project_id` | "我此刻在哪个项目里工作" |
| Task membership / projection | `task_project_id` | "本次任务落在哪里" |
| Project Center route | `projects_route`（`list` / `detail`） | "在看列表还是在看某个项目" |
| Switcher chrome | `sidebar_project_switcher_open` / `task_project_switcher_open` | 面板开合，纯 UI |

不可违反的约束：

- **Navigation 不修改 Project Context**（含从 Inbox 返回项目中心）；
- **只有 Project Context switch 才写 `active_project_id`**——唯一写入口
  `_apply_project_context()`（`_switch_project_context()` 是它的调用方）；
- **Project Center nav 不打开 switcher**；重复点击保持 route 与 active state；
- **Switcher 不承担完整 Project Management**：面板底部只有「＋新建项目」，「管理所有项目」
  已退休；
- **Inbox 是 system collection / context，不是普通 Project**，不参与 Project 语义。

---

## 5. 组件改动清单

| # | 组件 | 改动 |
| --- | --- | --- |
| 1 | 侧栏 selector | 仍是 `current_project_selector` 按钮（42px / 填充态不变）；改为**切换面板开合**，并新增空语义标记 `.tp-nav-open` 表达"已按下" |
| 2 | 切换面板 | 新增 `_render_project_switcher_body(anchor)`：同一份列表实现，两处锚点共用；容器 key 都含 `switcher_*` 片段，CSS 一份覆盖两处 |
| 3 | 面板底部 | 只留 `＋ 新建项目`；删除「管理所有项目」 |
| 4 | 正文上下文块 | `[更改]` / `[选择项目]` 从"打开 Modal"改为"展开同一份列表"（就近锚点，key 前缀 `task_switcher_*`） |
| 5 | 同一时刻只开一个面板 | `_toggle_project_switcher()` 先 `_close_all_project_switchers()`：两处锚点展开同一份列表，同时开着会被读成两套系统 |
| 6 | 导航收尾 | `_open_project_list()` 收起所有面板：从侧栏展开的下拉不该漂到管理页上 |
| 7 | 路由 | `_open_project` / `_open_project_list` / `_restore_route_from_params` / 新建项目收尾写 `projects_route`；`_projects_route()` 对没有标记的旧路径沿用旧推断 |
| 8 | 项目中心入口 | 行为不变（纯导航）；当前页判据由 `not sidebar_project_id` 改为 `_projects_route() == "list"` |

---

## 6. 测试覆盖

新增 `tests/sidebar_project_switcher_test.py`，8 条验收逐条对应：

| 用例 | 守住什么 |
| --- | --- |
| `test_selector_opens_a_light_switcher_panel_not_a_modal` | 收起时零渲染；展开后面板 / 列表 / 底部动作都在**侧栏子树**里；底部只有「新建项目」；无 `project_switcher_open`、无 `project_switcher_dialog`、CSS 里无 `section[role="dialog"]:has(.st-key-project_switcher…)` |
| `test_selector_toggles_the_same_panel` | 再点收起，开与合是同一个控件 |
| `test_picking_a_project_updates_the_context_and_closes_the_panel` | 选中 → `active_project_id` + `task_project_id` 同步、面板收起、列表不再渲染、toast |
| `test_picking_inbox_returns_to_the_system_workspace_context` | Inbox 行带「系统工作区」badge 与"未归入项目的任务"措辞；选中后回到 system context；侧栏说「未选择项目」而不是把它当一个项目 |
| `test_project_center_navigates_and_never_opens_the_switcher` | 路由落到 `list`、管理页真的渲染；不展开面板、无 Modal 状态位 |
| `test_clicking_project_center_again_keeps_route_and_active_state` | 重复点击不改 route、不弹面板、active state 保持 |
| `test_project_center_navigation_does_not_change_the_current_project` | 上下文与 selector 文案原样保留（需求 B / 测试 6） |
| `test_new_project_from_the_switcher_goes_through_the_create_flow` | 走既有 `project_modal == "new"` 流程；创建成功即成为上下文并落盘 |
| `test_both_anchors_share_one_switcher_implementation` | 两处锚点的行文案完全一致、key 两两不同、同时只有一个展开（需求 8） |
| `test_switcher_footer_keys_are_scoped_to_the_anchor` | 底部动作的 widget key **按锚点隔离**：侧栏展开时 `switcher_new_project` 在、`task_switcher_new_project` 不在，正文锚点展开时反之 |
| `test_the_duplicate_switching_modal_is_retired_in_source` | 源码级守卫：旧状态位 / 旧渲染器调用 / 「管理所有项目」不存在；`_render_project_switcher_body` 恰好 1 处定义 + 3 处调用（侧栏 1 + 正文 2，正文两处互斥） |

该文件共 **11 个用例**（上表 8 条验收 + 开合 / anchor-scope / 源码守卫）。

同时更新了 3 个既有文件里依赖旧交互的断言：

- `project_context_hierarchy_test.py`：`test_project_center_does_not_switch_the_context`
  改为断言"路由变 list + 上下文保留 + 管理页真的渲染"；
  `…change_opens_the_same_switcher_list` 改用 `task_switcher_pick_*` 与
  `task_project_switcher_open`，并补"另一处锚点保持收起"；
- `project_task_navigation_test.py`：`test_project_center_entry_returns_to_the_project_list`
  改断言 `projects_route == "list"` 且上下文保留；`test_project_switcher_actions_are_context_only`
  改为断言"底部只有新建项目、侧栏只有一颗管理入口"；
- `project_detail_visual_system_test.py`：两个 Modal 用例改写为面板版本（`switcher_panel` /
  `switcher_list` / `switcher_footer` 前缀 + 无 dialog 规则）。

### 回归中额外发现并修掉的 4 处

首跑 8 文件 **112 passed / 4 failed**，成因各不相同（3 处是测试没跟上"key 按锚点隔离"，
1 处是产品行为变更）：

| 位置 | 病因 | 修法 |
| --- | --- | --- |
| `project_context_hierarchy:464`、`project_task_navigation:931` / `:1682` | 在**正文锚点**展开时点了**侧栏锚点**的 key（`switcher_new_project` / `switcher_pick_*`）→ `KeyError` | 改用 `task_switcher_new_project` / `task_switcher_pick_*`。注意 `:400` 用的确实是侧栏锚点，**不**在此列 |
| `project_detail_visual_system:623` | `_css_rule` 用裸 `css.find()`，被更长的覆写选择器 `.st-key-task_project_context [class*="switcher_panel"]` 抢先命中，只拿到一条 `margin` 规则 | 选择器**锚定行首**：`'\n[class*="switcher_panel"] {'` |
| `project_task_navigation:400` | 把 `current_project_selector` 当幂等 open 连点两次，第二次把面板关掉 | 删掉多余的第二次点击 |
| `project_task_navigation:1295` | 旧断言要求"返回项目中心后清空 `active_project_id`"，与需求 B 冲突 | 改断言**保留**上下文 + `projects_route == "list"` |

4 处均已定向复验通过。**教训**：`project_task_navigation_test.py` 有 85 个用例 / 27.5 分钟，
整文件重跑极不划算 —— 复验请用节点 ID（`pytest tests/x_test.py::test_name`，单个约 20s，
配 `TMPDIR=$(mktemp -d)` 避开 shim 的 `EEXIST` 坑）。

---

## 7. 实测依据（为什么这么选）

`core.list_active_project_options()` + 每行 `project_summary()`，11 个项目：

```text
run 0: 377.4 ms   run 1: 376.3 ms   run 2: 378.4 ms
run 3: 379.7 ms   run 4: 377.4 ms   run 5: 377.2 ms
```

稳定 ~377 ms/次，因此"面板内容常驻渲染"被否决（§1）。收起时不渲染 → 空闲成本为零。

另一个实测结论（决定了测试怎么写）：AppTest 里 `st.popover` 的内层控件**能**被拿到，
但交付点击的那一趟里 Popover 的 `open` 是 `False`（AppTest 不模拟前端状态），惰性内容
会让行按钮不存在、点击被丢弃；而 `st.session_state[popover_key] = False` 在自身内容里
写会抛 `StreamlitWidgetAlreadyInstantiatedError`。这是选用会话标记的第二个理由。

---

## 8. 风险与未做

- **风险**：面板开合是会话标记，如果将来有人在面板内部再加一个"关闭"动作，必须同样走
  `_close_project_switcher()`，否则会出现"选了项目但面板还挂着"。回归测试
  `test_picking_a_project_updates_the_context_and_closes_the_panel` 守住这条。
- **风险**：`projects_route` 对没有显式标记的旧路径走推断（有 `active_project_id` 即视为
  详情）。所有设置 `app_view="projects"` 的既有路径都已核对，但新增路径若忘记写
  `projects_route`，会退回旧推断——表现为"管理页上项目中心没有当前页标记"。
- **未做**：没有把 `项目中心` 换成原生导航组件（仍是 `st.button` + 语义标记 + CSS）。
- **未做**：面板没有做键盘导航 / 焦点陷阱——它是就地展开的普通内容块，跟随 Streamlit
  默认的可达性行为。
- **技术债（本轮明确不处理）**：`project_task_navigation_test.py` 有 **85 个用例、单文件
  ~27.5 分钟**（每个用例都要构建整棵 AppTest 应用树），是全套最慢的文件。本轮收尾
  **不**拆测试文件、**不**重构 runner、**不**重构 AppTest fixture —— 只登记为技术债，
  以免扩大 diff。日常复验请用节点 ID（`pytest tests/x_test.py::test_name`，单个约 20s）
  而不是整文件重跑。

---

## 9. 最终回归证据（2026-09-18，收尾轮）

用项目既定的**逐文件独立进程** runner 跑**全套**（不是只跑 `project_*`）：

```bash
./venv/bin/python scripts/run_regression.py --tsv /tmp/regression-final.tsv
# exit code 0
```

| 指标 | 值 |
| --- | --- |
| test files total | **63** |
| pytest-style files | 62 |
| script-style smoke tests | 1（`app_boot_test.py`） |
| pytest cases | **888** |
| passed | **888** |
| failed | **0** |
| error | **0** |
| skipped | **0** |
| xfailed / xpassed | **0 / 0** |
| effective failures | **0** |
| 总耗时 | 101m26s |

`app_boot_test.py` 按约定**以脚本方式运行**（`venv/bin/python tests/app_boot_test.py`，
`exit=0`），因此它的 pytest exit code 5 不进入失败统计。runner 会自动分类，无需手工指定。

本套改动涉及的文件全部通过：

| 文件 | 结果 |
| --- | --- |
| `sidebar_project_switcher_test.py` | 11 passed |
| `project_context_hierarchy_test.py` | 21 passed |
| `project_task_navigation_test.py` | 85 passed |
| `project_detail_visual_system_test.py` | 28 passed |
| `inbox_project_density_test.py` | 20 passed |
| `project_lifecycle_test.py` | 18 passed |
| `project_memory_test.py` | 45 passed |
| `project_overview_structure_test.py` | 18 passed |

尾注：上表是本轮**实际运行**的结果；历史记忆里"62 个文件 = 61 pytest + 1 script"是新增
`sidebar_project_switcher_test.py` 之前的数字，现已更正为 63 = 62 + 1。
