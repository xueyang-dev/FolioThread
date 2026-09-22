# 译文保存流：浏览器实测

这份证据包回答一个问题，而且是**只能用真实浏览器回答**的问题：

> 新人打开任务、在译文框里打字，能不能看到保存入口、保存成功、改到一半不丢稿、
> 交出去不漏内容？

它的触发点是发布计划里的一条明确要求：保存机制必须**用浏览器真实输入**验证，
"而不是只改测试状态"。这个要求不是形式主义——上一轮的缺陷恰好是"保存按钮永远不出现"，
而这一轮又抓出一条**在 `AppTest` 里永远不会失败**的缺陷（见「服务端换内容时输入框没换」）。

两个脚本，两类问题：

| 脚本 | 回答的问题 | 检查项 |
| -- | -- | -- |
| `audit.js` | 直线：输入 → 保存 → 刷新，内容还在吗？ | 17 项 |
| `runtime_edit_audit.js` | 并发：轮询、后台写回、双标签页、服务端换内容 | 16 项 |

## 为什么 `AppTest` 证明不了这件事

`AppTest` 即使走 `.set_value()`，也仍然在**同一个 Python 进程**里读写**同一个
`session_state`**。它证明的是"服务端拿到新值后会渲染保存入口"，而不是：

1. 前端会把用户刚敲的内容送回服务端（`on_change` 真的触发了）；
2. 保存按钮真的出现在**用户眼前**（而不只是出现在元素树里）；
3. **刷新之后**内容还在（真的落盘了，而不是留在会话内存里）；
4. **前端组件会不会松手**（见下）。

第 1、2 条正是"`st.form` 死循环"这类缺陷的藏身处：表单输入在提交前不到达服务端，
而后端"要不要显示提交按钮"依赖后端值——两边互等，`AppTest` 里手动 `set_value` 就跳过了
整条真实链路。第 3 条更简单：`AppTest` 从不刷新。

第 4 条是这一轮新认识的，也是最需要提防的一条：`st.text_area` 的 element id 只由
`(user_key, max_chars)` 决定（`streamlit/elements/lib/utils.py:
compute_and_register_element_id`，text_area 传的是 `key_as_main_identity={"max_chars"}`），
**默认值不参与**。所以"清掉 `session_state` 里的 key、让 widget 用新默认值重建"这条
常见做法，对**已经被敲过字**的输入框无效：前端组件实例不重挂载，它保留自己的输入。
`AppTest` 里清 key 之后下一轮就用新默认值重建，断言照样通过——**测试是绿的，用户在浏览器里
看到的是没变**。这类缺陷只有真实浏览器能证伪。

## 复现

```bash
# 1) 起一个隔离 OUTPUT_DIR 的工作台（真实 outputs/ 不会被写脏）
cd "$(git rev-parse --show-toplevel)"
venv/bin/streamlit run docs/ui-audit/25-save-flow/serve_fixture.py \
    --server.port 8505 --server.address 127.0.0.1

# 2) 另一终端：直线实测
cd docs/ui-audit/25-save-flow
FOLIO_PLAYWRIGHT_CORE=~/Dev/grok-workspace/node_modules/playwright-core \
FOLIO_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
node audit.js http://127.0.0.1:8505 .

# 3) 并发实测（两轮之间请重启夹具，拿干净状态）
pkill -f serve_fixture.py && rm -f ../../.audit/fixture-output-dir.txt
# 重新起夹具后：
node runtime_edit_audit.js http://127.0.0.1:8505 .
```

两个脚本都由 Node 直接读夹具任务目录下的 `state.json` / `translation_drafts.json`
做**磁盘断言**（不只看界面）。目录路径从 `.audit/fixture-output-dir.txt` 这个固定交接
文件取；`FOLIO_OUTPUT_DIR` 可以覆盖它。

只读之外唯一会写的，是那个**进程私有**的临时 `OUTPUT_DIR`。

### 夹具的三个陷阱（都踩过）

- **`OUTPUT_DIR` 必须按进程创建，不能按 rerun 创建**。Streamlit 每次交互都会重跑入口
  脚本；如果在模块级 `tempfile.mkdtemp()`，那么**每一次输入、每一次点按钮都换一个新目录**，
  夹具看起来被"重置"，表现正是**"保存成功但刷新后内容不见"**——一个纯粹的夹具缺陷，
  很容易被误读成产品缺陷。所以临时目录用 `st.cache_resource` 按进程建一次，
  夹具也只在 `state.json` 不存在时播种一次。
- **`session_state` 只在首次会话播种**。`app.py` 只在 key 缺失时填默认值，
  所以 `active_job_id` / `app_view` 必须自己判一次再写，否则每次 rerun 都把用户
  切走的页面拉回来。
- **别用 `ls -dt $TMPDIR/folio-save-flow-*` 去猜目录**。同一台机器上留着历次运行的目录，
  而本次进程的目录要到**第一个会话连上**才被创建（`st.cache_resource` 首次执行才跑），
  所以"最新的那个"既可能不是本次的、也可能还不存在，磁盘断言会断言在错误的目录上
  而且看起来一切正常。夹具因此把目录写到固定位置 `.audit/fixture-output-dir.txt`。

夹具任务 `saveflowbrowser01` 共 6 段，前两段标为已审校——用来制造"切筛选会把第 3 段
筛掉"的场景。

## 结论 A：直线实测 17 项，0 失败（`audit.js`）

| # | 检查 | 结果 | 依据 |
| -- | -- | -- | -- |
| 1 | 当前段落常驻保存入口（真实渲染） | ok | 找到 1 个 |
| 2 | 未修改的其它段落不常驻保存入口 | ok | 找到 0 个 |
| 3 | 初始状态没有"未保存"提示 | ok | — |
| 4 | 输入框保留了刚敲的内容 | ok | 逐字键入 + 失焦后 `inputValue()` 等于键入串 |
| 5 | 输入后出现"未保存"提示 | ok | 服务端确实收到了输入 |
| 6 | 输入后该行出现保存入口（**真实输入路径**） | ok | 找到 1 个 |
| 7 | 筛掉之后该行不再渲染输入框 | ok | 找到 0 个（证明"切筛选"是真的卸载，不是隐藏） |
| 8 | 切筛选回来仍是自己敲的内容（**不是旧译文**） | ok | 本轮修过的真实缺陷，见下 |
| 9 | 横幅说明草稿不是正式译文、不会获得审校结论 | ok | 断言文案含"不是正式译文" |
| 10 | 刷新前横幅报出未保存处数 | ok | 断言文案含"未保存的译文修改" |
| 11 | **刷新（新会话）后未保存草稿被恢复** | ok | 刷新后输入框仍是键入串 |
| 12 | 恢复必须被明确告知（不能静默恢复） | ok | 断言文案含"已从本机任务目录恢复" |
| 13 | 保存后有成功反馈 | ok | 横幅出现"已保存" |
| 14 | 保存后"未保存"提示消失 | ok | — |
| 15 | 刷新后已保存内容持久化（**真落盘**） | ok | 刷新后输入框仍是键入串 |
| 16 | 刷新后没有残留的"未保存"提示 | ok | — |
| 17 | 浏览器控制台没有未捕获异常 | ok | `pageerror` 计数 0 |

第 11、12 条取代了上一版的"刷新后未保存草稿不再存在"。那一版把 Streamlit **会话**
会重置这件事，写成了"草稿必然丢"——不准确：会话确实会重置，但应用可以另外把草稿落盘。
现在草稿存在任务目录里，刷新后恢复并**明确告知**（静默恢复比不恢复更糟：用户会以为自己
记错了，或以为系统自动保存了）。

### 独立核验磁盘（不只看界面）

界面说"已保存"不算数，另开一个进程读 `state.json`。

直线实测（保存第 3 段，这一段**没有**审校结论）：

```text
pairs[2].target       = 浏览器实测：第三段译文（输入 → 筛切 → 保存 → 刷新）
pairs[2].human_edited = True
segment_uid           = seg-saveflowbrowser01-0002
review_stats          = {reviewed_segments: 2, ...}   ← 保存前也是 2
```

并发实测（保存了第 1、2、4 段，其中前两段**原本已审校**）：

```text
targets       = ['轮询实测：先提交的内容（未失焦追加）', '轮询实测：我这一份草稿',
                 '待审译文 3', '第一页写的第四段', '待审译文 5', '待审译文 6']
human_edited  = [True, True, False, True, False, False]
segment_uid   = ['seg-saveflowbrowser01-0000', 'seg-saveflowbrowser01-0001', ...]
review_stats  = {reviewed_segments: 0, ...}           ← 保存前是 2
```

最后一行把"保存与审校是两件事"说得更准确，也**纠正了本文档早先一句话的不准确说法**：

- 保存**未审校**的段落，审校计数不变（第 3 段那一次：2 → 2）；
- 保存**已审校**的段落，**那一段的审校结论会作废**（`core.save_translation_edit` 会把
  `reviewed` / `review_status` 清回未审校并重算计数），所以第 1、2 段被编辑后计数 2 → 0；
- 两个方向都说明：**保存不会把段落变成"已审校"，反过来说，编辑一份已审校的译文必须让
  那次审校失效**——否则用户会以为改过的文字还带着旧结论。

早先这里写的是"保存不改变审校状态"，那是把"不增加"误写成了"不改变"。夹具里恰好
有一段已审校的段落被编辑，才把这个错误暴露出来。

另外，`segment_uid` 是稳定身份（见 `CHANGELOG.md`「拆分 / 合并 / 插入后的数据对应与撤销」），
它证明这些写入是按身份落盘的，而不是又按位置索引写的。

## 结论 B：并发实测 16 项，0 失败（`runtime_edit_audit.js`）

工作台整体跑在 `@st.fragment(run_every="3s")` 里（`app.py:14543`），也就是说
用户每打两个字，就可能被一次轮询重渲染穿过。`AppTest` 没有计时器、没有前端状态机，
也拿不到 `document.activeElement`。

| # | 节 | 检查 | 结果 |
| -- | -- | -- | -- |
| 1 | 1 | 轮询穿过未失焦的输入后，DOM 内容没有被清空或回滚 | ok |
| 2 | 1 | 轮询期间没有抢走输入焦点 | ok |
| 3 | 1 | 失焦后输入落进草稿层（轮询没有破坏同步链路） | ok |
| 4 | 2 | 保存并下一段把内容写进了磁盘 | ok |
| 5 | 2 | 保存并下一段后**焦点直接落进下一段的输入框** | ok |
| 6 | 3 | 后台写回后，正在输入的内容没有被覆盖 | ok |
| 7 | 3 | 保存时发现磁盘译文已变 → 提示而不是静默覆盖 | ok |
| 8 | 3 | 冲突未解决前，磁盘上仍是对方的版本 | ok |
| 9 | 3 | 选择"用我的草稿覆盖"之后才写入我的内容 | ok |
| 10 | 4 | 第一页保存写入磁盘 | ok |
| 11 | 4 | 第二页保存时被告知"译文在别处已经改过" | ok |
| 12 | 4 | 第二页没有静默覆盖第一页的内容 | ok |
| 13 | 4 | 第二页选择"采用磁盘上的版本"后，输入框回到磁盘内容 | ok |
| 14 | 4 | "采用磁盘上的版本"不改写磁盘 | ok |
| 15 | 5 | 点了复制原文到译文之后，输入框换成原文（不留着自己写的字） | ok |
| 16 | — | 浏览器控制台没有未捕获异常 | ok |

方法与判据：

- "未失焦的输入"用 `keyboard.type` 直接打、**不按 Tab**；一次轮询周期是 3s，等 9s（≥3 个周期）；
- 判定"没被吞字"读的是 textarea 的 **DOM 值**，不是服务端 `session_state`；
- 判定"没被覆盖"读的是磁盘上的 `state.json`（Node 直接读，不经过应用）；
- "后台写回"用 Node **原子改写** `state.json` 来模拟，而不是等模型——它和模型写回在应用
  眼里是同一件事（下一次轮询读到不同的 target）；
- 第 4 节是**两个真实的 Playwright page**（两个会话），不是同一会话里模拟两次点击。

第 1 节里有一条**曾经写错的断言**值得记下来：初版第 3 项写的是"未失焦的输入已到达服务端"。
Streamlit 的 `text_area` 只在**失焦 / ⌘+Enter** 时把值交给服务端，所以那是在要求逐字提交——
一条**永远不可能通过**的断言，而且会把注意力从真正该守的事实（失焦后确实落进草稿层）引开。
现在它守的是正确的契约。

## 截图

| 文件 | 时刻 |
| -- | -- |
| `1-initial.png` | 打开任务：只有当前段落有保存入口 |
| `2-typed.png` | 真实键入后：出现"未保存"提示 + 该行保存入口 |
| `3-filter-round-trip.png` | 切"已审校"再切回"全部"：仍是自己敲的内容 |
| `4-after-reload.png` | 刷新（新会话）后：草稿被恢复回来并明确告知 |
| `5-saved.png` | 点保存后："已保存"反馈 |
| `6-reload-persisted.png` | 再刷新：内容还在（真落盘） |
| `7-polling-typing.png` | 3s 轮询穿过正在输入的框：文字在、焦点在 |
| `8-focus-after-save-and-next.png` | "保存并下一段"之后焦点落在下一段输入框 |
| `9-background-writeback.png` | 后台改过磁盘译文：正在输入的内容没被覆盖 |
| `10-save-conflict.png` | 保存撞上冲突：摆出两边内容 + 三种处置 |
| `11-two-tabs-conflict.png` | 第二页保存被拦下（第一页的内容没被静默覆盖） |
| `12-two-tabs-take-theirs.png` | 第二页"采用磁盘上的版本"：输入框回到磁盘内容 |
| `13-copy-source-resets-editor.png` | 「复制原文到译文」：输入框真的换成了原文 |

## 这两轮实测查出的真实缺陷

浏览器实测的价值在这里——下面每一条**都不是**静态核对或 `AppTest` 能发现的：

1. **草稿没有回填输入框（会静默丢稿）**。段落被筛掉或滚出渲染窗口时，Streamlit 会丢弃
   该 keyed widget 的值。修复前只回填**已保存的译文**，于是用户切回来看到的是**旧译文**，
   点"保存"就把旧值写回文档、同时把草稿当成已保存丢弃——**一次点击同时丢掉用户输入和
   磁盘上的正确内容**，而横幅还显示"有未保存修改"。结论 A 第 8 项就是为它写的。
2. **横幅没有覆盖"刷新会丢"**（上一轮的边界）。后来草稿改为落盘，这条边界本身消失了；
   现在横幅说的是"刷新页面或关闭标签页都不会再丢失"，结论 A 第 11、12 项锁住它。
3. **服务端换内容时输入框不跟着换**（本轮）。点「复制原文到译文」/「采用磁盘上的版本」/
   「丢弃未保存的修改」/「丢弃全部」之后，框里还是自己刚才写的字。根因是上面的
   element-id 机制；修法是换 key 强制前端重挂载（`app.py: _reset_translation_editor`）。
   `AppTest` 对此**完全无感**——所以 `AppTest` 只守"必须换 key"这个契约，
   真实行为由结论 B 第 13、15 项负责。
4. **「丢弃全部」只清草稿、不复位输入框**（本轮，与第 3 条同源）。用户点"丢弃全部"会看见
   文字**还在**，然后困惑地再点一次。

第 1 条还顺带说明了一件事：**"切换不丢稿"和"刷新不丢稿"是两个不同的承诺**，
前者是草稿层与渲染窗口解耦，后者要靠**落盘**。把它们混在一句话里，就是在用一个真承诺
为另一个假承诺背书。

## 回归防线（不依赖浏览器）

浏览器实测不能进 CI，所以每个可断言的点在 `AppTest` 里都有一份对应：

| 检查 | 守卫用例（`tests/translation_save_flow_ui_test.py`，25 个） |
| -- | -- |
| 真实输入触发保存入口与成功反馈 | `test_typing_in_the_grid_reveals_the_save_entry_and_persists` |
| 切筛选回来仍是自己敲的内容 | `test_unsaved_draft_survives_a_filter_change_and_saves_what_was_typed`（回归：曾回填旧译文） |
| 切段落 / 切任务不丢稿 | `test_switching_the_selected_segment_keeps_the_draft` / `test_drafts_survive_switching_to_another_task` |
| 批量保存 / 丢弃（含输入框复位） | `test_save_all_commits_every_pending_draft` / `test_discard_all_drops_pending_drafts_and_restores_the_committed_text` |
| **服务端换内容必须换 key**（前端重挂载契约） | `test_server_side_edits_force_the_editor_to_remount` |
| 草稿落盘 / 新会话恢复 | `test_draft_file_round_trip_and_removal` / `test_a_persisted_draft_comes_back_in_a_new_session` |
| 交付前必须先处理未保存草稿 | `test_delivery_refuses_to_freeze_while_drafts_are_unsaved` |
| 覆盖冲突：先问，不静默覆盖 / 可采用磁盘版本 | `test_saving_over_someone_elses_change_asks_before_overwriting` / `test_conflict_can_take_the_version_already_on_disk` |
| 保存并下一段 / 下一未确认段 | `test_save_and_next_persists_then_moves_to_the_following_segment` / `test_save_and_go_to_next_unconfirmed_segment` / `test_save_and_next_reports_when_nothing_is_left` |
| 复制原文到译文 / 无引擎时禁用 | `test_copy_source_to_target_seeds_an_unsaved_draft` / `test_retranslate_needs_an_engine_and_says_so` |
| 拆分后撤销还原 | `test_split_then_undo_restores_the_original_row` |
| 合并确认解锁 | `test_merge_confirmation_unlocks_the_submit_button` |
| 撤销入口在工作台可达 | `test_structure_undo_is_reachable_from_the_workbench` |
| 排除段落在工作台可见 / 可恢复 | `test_excluded_segment_is_listed_and_restorable_from_the_workbench` |
| 导入范围可见 | `test_import_scope_is_visible_in_the_workspace` |
| Agent 失败 / 空结果不可写回 | `test_agent_failure_never_offers_to_apply` / `test_agent_empty_result_is_also_read_only` |
| Agent 分类按内部动作名 | `test_agent_suggestion_classifies_by_internal_action_name` |

数据层（排除 / 恢复 / 撤销 / 稳定身份 / 导入报告 / 交付清单）另由
`tests/translation_segment_lifecycle_test.py` 的 22 个用例守护；其中包含没有
`delivery_config` 的旧任务 fallback 仍输出排除清单的回归。

**"换 key"这件事本身也有守卫**：用例断言复位前后输入框的 key 集合分别是
`{base}` 和 `{base}#1`。它不保证浏览器里一定重建（那要浏览器证），但能拦住
"以后有人把换 key 改回清 key"——那正是这条缺陷的原始形态。

## 冻结版本

本页所有结论对应同一个冻结版本：**先跑完全量回归，然后在同一份代码上重跑两个浏览器实测**
（`audit.js` 17/17、`runtime_edit_audit.js` 16/16），此后未再改过 `app.py`。

```text
$ venv/bin/python scripts/run_regression.py --tsv .regression-logs/full-20260921-final2.tsv
EXIT=0
测试文件总数        : 72
  pytest 风格       : 71
  脚本式 smoke      : 1
pytest cases 通过   : 1031
有效失败文件        : 0
总耗时              : 7m46s
```

71 个 pytest 文件 + `app_boot_test.py`（脚本式冒烟，不是 pytest 用例）= 72 行，
逐行 `exit_code` 均为 0。

与上一轮冻结基线（同一证据包早先的 71 文件 / 1023 cases / 32m44s）相比：新增端到端
验收文件后为 72 文件 / 1031 cases；耗时从 32m44s 降到 7m46s，差别来自执行环境与
浏览器负载，不应解读为产品性能提升。

## 仍未验证

这一节是**清单，不是免责声明**。下面每一条都没有证据，谁也别把本页读成"保存流已全面验收"：

- **键盘 Tab 顺序是否符合视觉顺序**。本次输入用 `Tab` 失焦触发 `on_change`
  （即"离开输入框才提交"），所以它顺带证明了 `Tab` 能触发提交；但整页的 Tab 顺序没有逐格走过。
- **屏幕阅读器朗读顺序**。保存入口、未保存横幅、段落身份（"第 3 段"）在 DOM 里的顺序是用
  代码顺序推断的，没有用辅助技术实测。尤其**保存成功反馈**是 `st.success` 插入的一次性
  消息——屏幕阅读器会不会播报、播放的时机，未知。
- **200% 缩放 / 窄屏几何**。`24-minimal-workspace/phase1` 量的是工作台首段位置，不是保存流。
  编辑器在 200% 缩放下的换行、保存按钮与输入框的对齐没有量过。
- **草稿层的容量边界**。`translation_edit_drafts` 只存未保存内容，但一次改很多段、
  或很长的段落时它的内存、写盘频率与渲染开销没有量过（窗口化渲染是 400 行）。
- **结构操作之后的输入框复位**。本轮把"服务端换内容 → 换 key"覆盖到了保存/复制/丢弃/冲突/
  恢复原译/重译；**拆分、合并、插入、排除、撤销**之后输入框是否一定与文档对齐，没有单独实测
  （它们走 `_purge_translation_edit_state`，逻辑上应一致，但没有浏览器证据）。
- **真实 `outputs/` 上的回归**。本次全程在隔离 `OUTPUT_DIR` 里跑，好处是不写脏用户数据，
  代价是没覆盖"旧任务升级时补齐 `segment_uid`"这条路径在真实数据上的表现——
  那条由 `translation_segment_lifecycle_test.py` 的 legacy 用例覆盖，属单元级证据。
- **真实 provider 与浏览器贯通流程**。确定性 provider 的完整新人链路已由
  `26-release-e2e` 覆盖；真实 provider 的语言质量、浏览器视觉和原 DOCX 格式保真仍由
  各自验收项负责，且正式发布包仍需在新的发布 commit/tag 上重建。

（同 `24-minimal-workspace/phase1/README.md` 的做法：留一份明确的"没有证据"清单，
比让读者从"没写"里推断"应该没问题"要诚实。）
