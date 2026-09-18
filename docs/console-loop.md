# 控制台闭环（Console Loop）

本文件记录 FolioThread 界面层的闭环：用户在哪一屏做什么、系统在哪些点必须
停下来等人、以及这些承诺如何被自动化验证。

- 界面闭环测试：`tests/ui_console_test.py`
- 后端闭环测试：`tests/scenario_gate_test.py`（见[场景验收门禁](scenario-gate.md)）
- 蓝图依据：[开发蓝图](foliothread-agentic-native-blueprint.md) §4.2、§7 Phase 3

## 一屏一阶段

任务工作区（`app.py` 的 `_render_workspace_shell`）把整条闭环放在同一套导航里，
蓝图 §7 Phase 3 要求的默认路径即由此承载：

| 阶段 | 工作区导航 | 界面负责 | 人负责 |
| --- | --- | --- | --- |
| Job Overview | 概览 | 当前阻塞点、下一步动作、风险与待确认项、交付是否有效 | 决定是否继续 |
| Translate | 翻译 | 逐段译文、术语与上下文、编辑入口 | 修改译文、重新翻译 |
| Prepare | 术语 | 术语候选编辑、锁定、冻结 | 确认术语并冻结（Memory gate） |
| Review | 审校 | 审校队列、发现详情、建议译文 | 确认已解决 / 保留当前译文 / 重新翻译（Review gate） |
| Deliver | 交付 | 交付门禁状态、资产、不可变快照与版本历史 | 确认并冻结最终版本（Delivery gate） |
| Research（可选） | 案例 / 报告 / QA | 研究报告下游的状态与重建 | 报告与合规确认 |

导航项带状态徽标（已完成 / 需处理 / 待处理），因此用户不必理解内部状态机
就能看出"卡在哪、下一步做什么"。概览页的主按钮随阻塞状态变化，例如存在必须
处理的问题时直接给出「继续处理 N 个必须处理的问题 →」。

## 人类控制点在界面上的落点

| 控制点 | 界面动作 | 落盘结果 |
| --- | --- | --- |
| Memory gate | 术语页「锁定选中」「冻结并继续翻译」 | `glossary_frozen` v*N* + `glossary_hash`，随后继续翻译 |
| Review gate | 审校页「确认已解决」「保留当前译文」「重新翻译并复审」 | `HumanDecision` 审计记录（`actor_type="human"`） |
| Delivery gate | 交付页「确认并冻结最终版本」 | `delivery_status="final"` + 不可变快照 + `delivery_manifest.json` |

风险接受（`accept_blocking`）只对"审校发现 + 人工显式接受"生效；结构破坏
（保留项丢失等）由 `validate_delivery_translation_state` 在更早的位置拦截，
不可通过风险接受放行。

## 自动化验证的闭环环节

`tests/ui_console_test.py` 用真实 `app.py` + Streamlit `AppTest` 驱动，全程离线：

| 测试 | 验证的承诺 |
| --- | --- |
| `test_ui_new_task_journey_lands_in_the_workspace` | 配置就绪后点「开始任务」，离开四步向导并进入任务工作区；工作区显示当前任务源文件 |
| `test_ui_terminology_gate_freezes_and_continues_translation` | 术语未冻结时界面明说阻塞；人工冻结写入 v1 + hash，并真的继续翻译 |
| `test_ui_workspace_shows_the_closed_loop_navigation` | 概览/翻译/术语/审校/交付五个入口齐全，且不存在第二套工作区表面 |
| `test_ui_delivery_freezes_a_final_snapshot` | 交付页可以冻结最终版本 → `final` + 快照 v1 + 可下载资产 |
| `test_ui_review_gate_blocks_delivery_then_human_decision_unblocks` | 未决 blocking 时不得冻结交付；人工决定后解除阻塞并可交付 |
| `test_ui_does_not_render_other_jobs_into_the_active_workspace` | 打开任务 A 时界面不得出现任务 B 的内容（防"多任务串页"回归） |
| `test_ui_app_boot_smoke_runs_in_ci` | 把 `tests/app_boot_test.py` 纳入 `pytest` 收集（此前它从未在 CI 运行） |
| `test_ui_delivery_gate_matrix_is_consistent` | 冻结按钮可用性与"下一步"的门禁判断一致（翻译未完成/审校未就绪必须禁用） |
| `test_ui_delivery_does_not_invent_downstream_work` | 纯翻译任务不得被要求重建报告产物 |
| `test_ui_audit_fixtures_match_real_job_state` | 审计 fixture 的运行状态与业务状态一致；已完成任务不渲染运行面板 |
| `test_reading_projects_never_writes_to_disk` | 列出/渲染项目不创建任何文件；默认项目仍作为选项出现 |
| `test_translation_workspace_master_detail_selection_and_editing` | CAT 网格渲染、段号选段、筛选只渲染命中段落、**长句整句可见不被省略号截断** |

测试用离线 provider 真实跑一遍管线产生任务状态，因此界面读到的就是管线真正
写下的状态，而不是手写 fixture。

### 为什么 worker 用桩

「开始任务」与「继续处理」会在后台进程里跑管线。子进程不会继承测试进程的
monkeypatch，会真的发起网络请求，因此在 UI 测试里把 `start_job_worker` /
`resume_job` 替换为桩。测试验证的是**界面的路由与状态迁移**，后台进程本身
由 `scenario_gate_test.py` 覆盖。

## UX / UI 审查（工作台）

### 方法与边界

审查方式是用 Streamlit `AppTest` 驱动**真实 `app.py`**，逐个 dump 每一屏的元素树
（标题、导航状态、按钮及其禁用态、提示、网格、空状态），覆盖 5 个工作区阶段 ×
11 个任务状态（未翻译 / 翻译中 / 干净 / 阻塞有建议 / 阻塞无建议 / 过期 / 审校失败 /
未审校 / 旧任务 / 报告过期 / QA 未完成）。

**边界（重要）**：这里审的是信息架构与行为一致性，**不是**视觉/像素层。
本模型无法读取图片，因此没有复核 `docs/ui-audit/` 的 63 张截图；键盘可达性、
屏幕阅读器语义、对比度、真实浏览器渲染都不在本次范围内。视觉层仍以
`docs/ui-audit/` 为准。

### 结论：工作台的设计是成立的

蓝图 §7 Phase 3 要求每屏优先显示"当前阻塞点 / 下一步动作 / 风险与待确认项 /
交付是否有效"。逐状态核对后，**概览的 hero 确实按阻塞状态给出不同的结论与主行动**，
且主行动标签直接描述该做什么：

| 状态 | hero 结论 | 主行动 |
| --- | --- | --- |
| 未翻译 / 翻译中 | 正在翻译 0/0 · 2/4 | — |
| 干净 | 可以准备交付 | 查看翻译 → |
| 审校阻塞 | 暂不满足交付条件 · 还有 1 个必须处理的问题 | 继续处理 1 个必须处理的问题 → |
| 译文过期 | 1 段译文在上次审校后发生变化，需要重新审校 | 重新审校 1 段 → |
| 审校失败 | 1 段审校未完成，请重试 | 重试失败的 1 段 → |
| 审校缺失 | 还有 2 段尚未完成审校 | 审校尚未完成的 2 段 → |
| 报告过期 | 报告需要更新 | 按影响范围继续重建 |
| QA 未完成 | 需要完成交付检查 | 打开合规与 QA |

导航项带状态徽标（已完成 / 需处理 / 待处理 + tooltip），交付页有独立的
「交付判断」网格与「下一步」卡片，引擎内部细节（worker / lease / PID /
checkpoint / finding id）都在折叠面板内，符合蓝图 §1.3。

### 本次修复的两个缺陷

**1. 交付页提供了必然失败的主按钮，且与同页判断自相矛盾。**

冻结按钮的 `disabled` 只检查报告与 QA 门禁，**不检查翻译完成度与审校就绪**。
于是 0/0 段、2/4 段、审校过期/失败/缺失的任务都显示**可点击**的
「确认并冻结最终版本」，点击后由后端拒绝并弹错；而报告/QA 阻塞时按钮却是禁用的。
同一页两种口径。

修复：复用该页既有的 `next_target` 判断（它已经完整覆盖翻译完成 / 审校就绪 /
无阻塞 / 报告与 QA 就绪），`next_target == "freeze"` 时才允许冻结；并在
「交付判断」网格里补上此前完全缺失的**翻译完成**一项，让阻塞原因可见。

**2. 纯翻译任务被要求"重建 9 项下游产物"。**

`core.dependency_impact_view` 只要译文发生变化，就把所有已知下游产物标为 stale，
包括该任务根本不存在的报告/QA 产物。于是纯翻译任务的交付页一边在网格里显示
"学术产物同步：当前任务未启用 ✓"（pass），一边在「下一步」要求
"先按影响范围重建 9 项下游产物"。概览 hero 也同样会说"报告需要更新"。

修复：概览与交付页在把"影响 stale"当作阻塞之前，先确认**确实存在会随译文变化的
学术下游**（`report_enabled` 或已有学术产物），与网格使用同一判据。

两个修复都有回归防线：
`test_ui_delivery_gate_matrix_is_consistent` 与
`test_ui_delivery_does_not_invent_downstream_work`，并经过反向验证——
把缺陷改回去，它们会失败。

修复后交付门禁矩阵（11 个状态实测）：

| 状态 | 冻结按钮 |
| --- | --- |
| 干净 / 旧任务 / 术语任务 | 可用 |
| 未翻译 / 翻译中 / 审校过期 / 审校失败 / 未审校 / 报告过期 / QA 未完成 | 禁用（并说明原因） |
| 审校阻塞（可风险接受） | 不显示冻结，改为「确认风险并继续交付」（需勾选确认） |

### 被纠正的误判（记下来以免重复）

审查过程中有三条"看着像缺陷"的观察，核对后**不是**缺陷，因此没有改动：

1. **"术语页是空白死胡同"** —— 实际是审查工具只打印了 caption、没打印 markdown。
   真正的运行时有完整的空状态（`暂无项目术语。`）、说明文案与「术语详情」信息卡。
2. **"概览出现「继续处理」等竞争性按钮、暴露 worker/lease 细节"** —— 那是审查
   fixture 的产物：合成的审计任务从未跑过 worker，`runtime_state.json` 停在
   `idle_incomplete`，于是概览渲染了运行面板。真实完成的任务
   `runtime_status = completed`，面板根本不渲染（已实测确认）。
3. **"非研究任务仍然显示「查看报告 →」"** —— 该卡片带 `is-muted` 语气并写明
   "当前任务未启用"，是三阶段概览的一致表达，属于设计选择。

### 只读访问不得写盘（已修复）

审查 fixture 时发现一个更普遍的问题：`core.list_projects()` 会在"列出项目"时
顺手创建默认项目。于是**只读**访问——渲染新建任务页、渲染项目页、脚本、eval、
测试——都会在 `outputs/` 下写出 `projects/default/project.json`。

后果是真实的：跑一次 `pytest` 就会在你自己的工作目录里留下与本次测试毫无关系的
项目记录（我是在核对"测试是否污染 outputs/"时发现的）。

修复：`list_projects()` 变成纯读取；默认项目改由变更路径
（`ensure_default_project()`）创建，只读展示走内存中的
`default_project_view()`。同时把"默认项目不可归档/删除"的保护从"读取时判断"
改为"按项目 ID 判断"，因为保护不应依赖磁盘上是否存在该记录。

回归防线：`test_reading_projects_never_writes_to_disk`（渲染项目页与新建任务页
后断言目录未被创建），并经过反向验证——把"读取即创建"改回去，该测试会失败。

同一轮还把剩下的两处写副作用一并去掉了（`get_job_runtime_status` 的推断落盘、
`list_jobs` 创建输出目录），完整清单与唯一保留的例外见
[架构边界说明](architecture-boundaries.md) 第 7 节。

### 审计 fixture 的工具问题（已修复）

`scripts/ui_audit_fixtures.py` 生成的合成任务与真实任务不一致：缺少
`enable_annotate` / `enable_report` / `provider` / `stage` 等 `run_job_pipeline`
一定会写入的字段，也完全不写 `runtime_state.json`。加上完成判定过严（见下），
结果是**已完成**的 fixture 被判为 `idle_incomplete`，概览随之渲染运行面板并出现
「继续处理」—— `docs/ui-audit/` 里已完成状态的截图因此比真实情况杂乱。

修复（三处）：

1. fixture 补齐真实任务的 pipeline 顶层字段，使就绪与门禁判断和真实任务一致；
2. `_save` 按业务状态写入 `runtime_state.json`（已完成 → `completed`；
   进行中 → `idle_incomplete` 并记录**真实进度** `2/4`，而不是 `0/—`）；
3. 脚本自带 `self_check()`：已完成 fixture 若被判定为未完成、或会渲染运行面板，
   脚本直接失败，而不是等人工看截图才发现。

另外发现并加固了一个数据安全点：本脚本会就地改写 `ui-audit-*` 目录并**替换全局
翻译记忆**（`outputs/translation_memory.json`）。审计包的做法是事后手工恢复
`outputs/`；现在脚本在写入前会打印它将要覆盖的内容，并列出未受影响的真实任务
目录，避免静默覆盖。

回归防线：`test_ui_audit_fixtures_match_real_job_state`（重建全部 fixture，
校验运行状态与业务状态一致，并端到端确认已完成任务的概览不出现运行面板与
「继续处理」），且经过反向验证——去掉 fixture 的运行状态写入，该测试会失败。

### 另一处修复：旧任务被误报为"未完成"

同一轮审查还发现完成判定过严：`_runtime_business_complete` 把**缺失**的
`enable_annotate` 当作"要求标注"，而产品自身默认是关闭
（`DELIVERY_CONFIG_DEFAULTS["enable_annotate"] = False`）。后果是
`p1/p2/p3` 全部完成、报告已生成的旧任务被报成 `idle_incomplete`，
于是概览一边说"可以准备交付"、一边渲染运行面板与「继续处理」。

修复：只有**显式**要求标注（`enable_annotate is True`）且未完成时才阻止"业务完成"。
回归防线：`tests/recovery_ui_test.py` 中断点继续后的断言（已完成任务不得再出现
运行面板与「继续处理」），并经过反向验证。

## 工作台改版：CAT 段落网格（MemoQ / Trados 风格）

改版前的实测问题（1440×900，82 段任务）：

| 问题 | 实测 |
| --- | --- |
| 顶部占满 | 项目标题区约 160px + 「交付与审校依据」大卡片约 110px，**列表开始前已用掉约 30% 屏高** |
| 左侧过宽 | 5 个导航项占约 200px，且带一行装饰性说明 |
| 列浪费 | 「状态」+「#」两列约 200px |
| **句子读不全** | 原文与译文两列都用 `_translation_preview(limit=170)` 截断并加省略号——译者无法在列表里读完整句子 |

根因是列表用了 `st.dataframe`：它按单行渲染单元格并在其中截断，Streamlit 不提供换行。
因此改用自绘的 CAT 网格：

- **原文与译文并排、整句换行**，行高随内容增长；
- **状态不再占列**，改成单元格左侧色条（已审校=绿 / 已修改=蓝 / 待审=琥珀）；
- **段号是唯一的选择入口**（窄栏按钮，点击即选段，鼠标悬停显示"第 N 段 · 状态"）；
- 顶部压缩为一行元信息（版本、段数、交付依据、最近变更），去掉大卡片与装饰性副标题；
- 导航与主栏比例从 `[0.82, 3.35, 1.28]` 调成 `[0.62, 4.15, 1.23]`，正文宽度占比由 61% 提升到约 69%；
- 网格固定高度（520px）内部滚动，右侧编辑器始终可见。

**性能**：逐行按钮是主要成本。实测 82 行 ≈ 0.05s 脚本时间 / 836ms 首屏 / 2.3k DOM 节点；
300 行 ≈ 0.11s / 650ms / 8k 节点；纯 HTML 单块则是 0.02s / 210ms / 166 节点。
因此逐行可选是**可负担**的，网格上限设为 400 行，超出部分靠搜索与筛选收敛。

改版同时修掉两个只有真实渲染才看得见的问题：

1. **检查器把状态显示了两遍**（"已翻译 已翻译"）——`_translation_pair_status` 与
   `_translation_pair_status_label` 返回同一段文字，而头部把两者并排渲染。当时用
   `_translation_status_glyph`（✓ / ✎ / ● / ○）把文字收敛成符号。后续版本把状态语义
   整体收进行内徽标与 Agent Inspector，符号函数与 `_translation_pair_flags` 一并删除
   （全仓已无调用方），以免留下"还有另一套状态语义"的维护噪音。
2. **窄栏里「重新翻译并复审」被截断成「重新…」**——改短标签「重译」，完整语义放进 tooltip。

### 长文档的导航与"虚拟滚动"

**Streamlit 里做不到浏览器级虚拟滚动**：真正的虚拟滚动（只挂载可视行）需要自定义
JS 组件，`st.dataframe` 是唯一内建虚拟化的表格，但它在单元格里截断文本、无法满足
"整句可读"。因此这里用**有界窗口 + 导航**达到同样的目的：

- 网格最多渲染 `CAT_GRID_ROWS`（400）行，且**显示窗口跟随选中段落**，因此 DOM 规模
  与文档长度无关；
- 检查器上方提供 `←` / `→` 上一段/下一段，翻段会自动把该段滚入窗口——这是译者实际
  使用的顺序流程；
- 随机定位用搜索框（它本来就接受段落号），把窗口直接带到目标段落。

实测成本：300 行 ≈ 0.11s 脚本时间 / 650ms 首屏 / 8k DOM 节点；82 行 ≈ 0.05s / 836ms /
2.3k 节点。所以 400 行的上限留有充足余量。

> 一个踩过的坑：随机跳转最初做成 `number_input`，结果 widget 状态与选中段落互相追赶，
> 造成无限 rerun（`AppTest` 以 30s 超时暴露）。导航只保留按钮，随机定位交给搜索框。

### 视觉验证工具

`scripts/ui_screenshot.py` 用本机已有的 Chromium + playwright-core 给运行中的应用截图，
支持直接打开某个任务的某个工作区页面：

```bash
python scripts/ui_screenshot.py --out /tmp/translate.png --section 翻译
```

只在 `AppTest` 的元素树里看不出纵向留白、文字截断与列宽，必须真实渲染。本次改版的
问题（含下面两条）都是靠它发现的。

## 交付页自相矛盾（改版时发现，已修）

改版过程中截图发现：交付判断卡片一边显示「学术产物同步：当前任务未启用 ✓」，
一边在同一张卡片的小结里写「但受影响的报告产物仍需重建」。

前一轮修的是「下一步」与概览 hero，**漏了卡片小结这一处**——同一个判据
（`_academic_downstream_enabled`）现在三处统一。这条说明了为什么必须看渲染结果：
元素树里这两句话分属不同的 markdown 块，断言各自都能通过。


## 已知缺口（按影响排序）

1. **历史任务没有筛选、排序或搜索。** `app.py` 的历史视图按 `list_jobs()` 顺序
   平铺全部任务，任务多了以后只能靠滚动。管理台目前缺少"按状态/时间/名称收敛"
   的手段。
2. **没有 Project 层。** 现状是扁平的 job 列表；蓝图 §3.2 的 Project（跨任务术语、
   风格、人工确认记忆）+ jobs 结构尚未在界面上成立。跨任务记忆目前只在
   「术语库与记忆」里以术语版本与已审校记忆的形式出现。
3. **没有 Project 层。** 现状是扁平的 job 列表；蓝图 §3.2 的 Project（跨任务术语、
   风格、人工确认记忆）+ jobs 结构尚未在界面上成立。跨任务记忆目前只在
   「术语库与记忆」里以术语版本与已审校记忆的形式出现。
4. **运行细节的措辞仍是引擎语言。** worker / lease / PID / checkpoint / finding id
   等内部信息位于「运行详情」「技术详情与调试信息」折叠面板内，符合蓝图 §1.3
   的要求（不在首屏暴露），但展开后的措辞仍是引擎语言，面向译者的解释可以更好。
5. **视觉层未在本次审查范围内。** 键盘可达性、屏幕阅读器语义、对比度与真实
   浏览器渲染仍以 `docs/ui-audit/` 的截图与既有说明为准，本次未复核。

## 已删除：旧的双工作区表面

`app.py` 原 8467–9000 行是旧的「资产与交付 / 文档上下文 / 研究报告（专用）」
渲染面（534 行），入口是一个 `当前工作区` 单选器。它已按蓝图 §9 删除，原因：

- 它构造不出一组可达的会话状态（`app_view == "new"` 与 `workspace_mode == True`
  无法同时成立，所有 `app_view` 赋值都会同步重置 `workspace_mode`），因此长期
  是死代码；
- 但它一旦重新可达，就会把工作区里**每一个**任务的资产面板、审校队列和报告
  依次渲染到同一页；
- 保留为"实现参考"的成本高于收益，且与"唯一工作区表面"的承诺冲突。

`test_ui_does_not_render_other_jobs_into_the_active_workspace` 与
`test_ui_workspace_shows_the_closed_loop_navigation` 是这个承诺的回归防线。
