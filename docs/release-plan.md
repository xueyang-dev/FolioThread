# 近期正式版发布计划

记录日期：2026-09-14（最近更新：2026-09-21）。用户已确定在近期 UI 全面打磨之后发布正式版，并在 GitHub、小红书、X 发布与宣传。版本号已定为 `0.4.0`（见 `pyproject.toml`）；**具体发布日期尚未确定**。本文记录计划，不表示已发布，也不代表本次文档更新要执行上传或发帖。

## 范围与顺序

1. 完成当前 UI 全面打磨，覆盖新建任务、项目切换、语言资产、翻译审校、恢复与交付的实际使用路径。
2. 修复本次打磨引入的问题，核验候选版本的安装/启动、核心场景与用户可见能力，准备发布资产。
3. 确定版本号和日期，整理 GitHub release 说明、安装方式与已知限制。
4. 准备并发布小红书、X 的产品介绍与演示，链接到 GitHub 正式版。
5. 发布后推进 DOCX Contract v1 → TM V2 → Source Update / Project Analysis，见[蓝图](foliothread-agentic-native-blueprint.md#7-当前进度与开发路线)。

CAT 内核的未来工作不阻塞这次正式发布；正式发布也不表示已成为 Trados / memoQ 的完整替代品。

## 候选版完成标准

- UI：真实任务的主要操作可完成；空态、运行中、失败/中断、stale、可交付状态准确且有可执行下一步。使用候选版截图与演示，不混入设计稿。
- 安装与启动：验证发布包在实际测试环境中安装和启动，记录已测平台，不把单平台结果宣传为全平台验证。
- 翻译主路径：运行相关回归与既有离线场景门禁，发现失败则修复或明确收缩发布范围。离线替身不证明模型质量，真实演示的模型、配置和人工修订应能说明。
- 交付：候选版输出、批准和冻结快照对应当前任务；README、安装命令、版本号和 release 资产一致。
- 对外边界：明确当前 DOCX 是生成式输出、TM 主要为 exact / normalized、TMX 为基础支持；不宣传未验收的 surgical round-trip、fuzzy TM 或完整 CAT 文件兼容。

## 渠道材料

| 渠道 | 准备内容 |
| --- | --- |
| GitHub | 正式 release、安装资产、变更说明、快速上手、已知限制和后续路线链接 |
| 小红书 | 中文使用场景、当前 UI 截图/短演示、适用用户、上手方式和 GitHub 地址 |
| X | 简短产品说明、实际工作流演示、正式 release 链接；语言在文案准备时确定 |

核心表达：本地长文档 AI 翻译工作台，结合文档上下文、术语、人工审校、证据和可恢复交付。演示材料使用可公开的文档，不包含 API key 或用户私有内容。未来计划与已交付能力分开呈现。

## 当前状态

- [x] 发布意图与渠道已记录。
- [x] 候选版安装、主路径与交付验证完成（2026-09-19，见「候选版验收证据」）。
- [x] **保存 / 分段 / 排除 / Agent / 导入范围五项发布阻断问题补齐**（2026-09-21，见下一节）。
      注意：09-19 的候选版验收证据**不覆盖**这些新增与修复——它们在那之后才做。
- [x] **编辑不丢 / 交付不漏 / 异常可恢复闭环补齐**（2026-09-21 第二轮，见下下节）：草稿落盘
      与恢复提示、交付前草稿门禁、覆盖冲突提示、运行中编辑安全实测。
- [ ] UI 全面打磨完成并验收。（侧栏 IA 打磨仍在进行中，尚未验收；保存流已单独取证）
- [x] 用一个全新任务走完"导入含噪声文档 → 排除噪声 → 拆合段 → 人工修改 → 中断恢复 → 审校 → 导出"；
      离线确定性验收见 `tests/release_e2e_acceptance_test.py` 与本节记录。
- [x] 当前工作树已构建临时 wheel/sdist，并在隔离环境安装后完成 `release_smoke.py` **9/9**；
      临时产物位于系统临时目录，不覆盖 `dist/`。
- [ ] **重建验收发布包**（09-19 的包不含本节功能）：应在确定新的发布 commit/tag 后重新构建、
      安装并运行 wheel smoke；当前只会构建临时候选包，不覆盖 `v0.4.0` 的既有产物。
- [ ] 版本号、日期、发布包及 GitHub release 文案确定。（**版本号已定为 `0.4.0`**；日期未定；release 文案未写）
- [ ] 小红书与 X 文案、截图/演示准备完成。
- [ ] 正式发布及渠道内容上线。

### 候选版验收证据（2026-09-19）

| 项目 | 结果 |
| --- | --- |
| 全量回归 | 66 个测试文件 / 947 个用例，失败 0；`tests/app_boot_test.py` 启动冒烟 `exit=0`（在干净检出里为 946 passed + 1 个**有意**跳过：该用例依赖本机 `outputs/` 真实产物，而 `outputs/` 不入版本控制） |
| 时序敏感用例连跑 | 合计 300 次重复运行、0 失败（`gui_launcher_test` 0/150，另 5 个文件各 0/30） |
| 构建 | `python -m build` 产出 wheel + sdist（包文件仍为 `foliothread-0.4.0`，兼容已发布身份） |
| 全新环境安装 | 干净 venv 安装、依赖解析、模块导入、`folith --help` 均通过；旧入口继续保留 |
| 语法兼容 | Python 3.10 / 3.12 编译通过；完整测试在 Python 3.11 执行 |
| 发布包内容 | 不含 `outputs/`、API 配置、任务状态或缓存文件 |
| 已修功能问题 | 默认监听地址、TM 语言隔离、Unicode 正文识别、任务身份隔离、响应式测试 |

### 保存与分段闭环补齐（2026-09-21）

09-19 的候选版验收证明了"发布包能装上、主路径能走通"，但没有回答一个更基础的问题：
**新人能不能安全地改完、保存并交付。** 本次按用户提出的五项发布阻断问题逐个补齐，
每项都附了产出物与验证方式。DOCX 原格式保真、模糊 TM、Source Update 仍按蓝图留到发布后。

| # | 问题 | 处理 | 回归防线 |
| --- | --- | --- | --- |
| 1 | 保存入口依赖后端"已修改"判断，而输入框在 `st.form` 内 → 循环依赖，入口可能永不出现 | 段落编辑去掉表单，改**草稿层**（`on_change` 即时同步）+ 当前段落常驻入口 + "保存全部/丢弃全部"；后续又补上草稿落盘与恢复 | `tests/translation_save_flow_ui_test.py`（25 例）；浏览器实测见 `docs/ui-audit/25-save-flow/` |
| 2 | 拆分/合并/插入后按**位置索引**关联编辑缓存 → 旧位置的新段落继承旧值；合并确认框在表单内、按钮按后端值禁用 → 无法解锁 | 引入稳定段落身份 `segment_uid`（单调递增、永不复用）；合并确认移出表单；提供**内容快照撤销**；排除/恢复改为**整表判过期** | `tests/translation_segment_lifecycle_test.py`（22 例） |
| 3 | 原文清理缺通用的"排除无效段落"（OCR 垃圾行、页码、重复页眉） | 新增**排除本段**：保留原文、可恢复、不进翻译、不计入待完成、导出清单化 | 同上 |
| 4 | 改写按钮传中文动作名、候选分类按英文内部名 → "改写"可能被归为只读诊断；模型失败返回普通错误串 → 勾选"作为改写候选"时错误文字可被应用 | 分类改用内部动作名；成功/空/失败三态分开，**失败永不写回译文** | `tests/agent_inspector_ui_test.py` + 保存流测试 2 例 |
| 5 | DOCX 提取只遍历正文段落，表格等内容**静默**不进翻译 | 提取时检测并统计未纳入部件（表格/页眉页脚/文本框/图片/公式/脚注尾注/批注），在任务里出具报告，并说明"导出是重建译文文档" | `tests/translation_segment_lifecycle_test.py` 的报告用例 |

建议同批的效率功能也已落地：**保存并进入下一段 / 下一未确认段**、**复制原文到译文**、
**翻译（重译）当前段落**。已有能力（项目术语、基础 TM、独立审校、交付快照、恢复、连接测试）
直接复用，未另建一套。

本次实测**查出的真实缺陷**（静态核对与 `AppTest` 都没抓到）：

- **草稿没有回填输入框 → 静默丢稿**。段落被筛掉或滚出渲染窗口时 Streamlit 丢弃该 keyed
  widget 的值；修复前只回填已保存译文，于是用户切回来看到**旧译文**，点保存把旧值写回
  文档、同时把草稿当已保存丢弃——一次点击同时丢掉用户输入与磁盘上的正确内容。
- **横幅只承诺"切换不丢"**，未披露刷新会丢未保存修改。（**此条在下一轮已被推翻**：草稿
  改为落盘后刷新不再丢稿，见下节。把它留在这里是为了保留"当时的边界"这个事实。）

### 编辑不丢 / 交付不漏 / 异常可恢复（2026-09-21 第二轮）

上一节补的是"改完能保存"。这一节补的是"改到一半不会丢、交出去不漏"。范围**刻意收紧**：
不再扩功能，只补三件事，加上一条对上一轮结论的**更正**。

| # | 缺口 | 处理 | 验证 |
| --- | --- | --- | --- |
| 1 | **未保存草稿只存在会话里**，刷新/关标签页即丢（上一版把这条写成"修不掉"，不准确） | 草稿落盘到任务目录 `translation_drafts.json`（`core.save/load/clear_translation_drafts`，原子写、空则删文件、损坏按"没有草稿"处理）；新会话恢复回输入框并**明确告知**"已从本机任务目录恢复"。草稿不进 `state.json`、不改 `reviewed`/`review_status` | `tests/translation_save_flow_ui_test.py::test_a_persisted_draft_comes_back_in_a_new_session`、`test_draft_file_round_trip_and_removal`；浏览器 `audit.js` |
| 2 | **交付入口不检查未保存草稿** → 冻结出的快照不含用户眼前的修改 | 冻结/风险接受交付前检查当前任务草稿：有未保存则阻止并给出"保存这 N 处并继续 / 返回编辑"；同一门禁挂到**两处**交付入口（含那个此前从未被调用的 `_render_delivery_gate`），避免将来重新接线时绕过 | `tests/translation_save_flow_ui_test.py::test_delivery_refuses_to_freeze_while_drafts_are_unsaved` |
| 3 | **并发编辑无提示**（同一任务两个标签页） | 保存时对比**草稿自己的 baseline** 与磁盘现值，不一致则摆出两边内容让用户选：覆盖 / 采用磁盘版本 / 稍后处理。绝不静默覆盖 | `test_saving_over_someone_elses_change_asks_before_overwriting`、`test_conflict_can_take_the_version_already_on_disk`；浏览器 `runtime_edit_audit.js` 第 3、4 节（真实双标签页） |
| 4 | **运行中的编辑安全（3s 轮询）未实测** | 用真实 Chrome 实测：轮询穿过未失焦的输入不吞字、不抢焦点、失焦后仍落进草稿层；后台写回不覆盖正在输入的内容 | `docs/ui-audit/25-save-flow/runtime_edit_audit.js` 第 1–2 节 |
| 5 | **服务端换内容时输入框不跟着换**（浏览器实测查出，`AppTest` 无法证伪） | 统一走 `_reset_translation_editor`：换 key 强制前端重挂载。覆盖「复制原文到译文」「采用磁盘上的版本」「丢弃未保存的修改」「丢弃全部」「恢复原译」「保存」「结构操作」 | `runtime_edit_audit.js` 第 5 节 + `test_server_side_edits_force_the_editor_to_remount`（守"必须换 key"这个契约） |

第 5 条的机制值得单独记一笔：`st.text_area` 的 element id 只由 `(user_key, max_chars)` 决定
（`streamlit/elements/lib/utils.py: compute_and_register_element_id`，text_area 传
`key_as_main_identity={"max_chars"}`），**默认值不参与**。所以"清 session_state 里的 key
让 widget 用新默认值重建"这条常见做法对**已经被敲过字的输入框无效**。`AppTest` 里清 key
之后下一轮就用新默认值重建，断言照样通过 —— 这类缺陷**只有真实浏览器能证伪**。

**范围外（有意不做）**：DOCX 原格式保真、模糊 TM、Source Update 仍按蓝图留到发布后；
`docs/ui-audit/README.md` 保留 09-01 的历史基线，并在顶部指向后续独立证据包；
各后续目录的 README 记录自己的日期、范围与验证命令。

浏览器实测（`docs/ui-audit/25-save-flow/audit.js`）**17 项检查 0 失败**，
`runtime_edit_audit.js` **16 项检查 0 失败**，并由独立进程读 `state.json` 与
`translation_drafts.json` 核验真的落盘。键盘顺序、屏幕阅读器朗读顺序、200% 缩放几何、
草稿容量边界和真实旧任务升级仍未做辅助技术或压力验收，不把这两份实测读成完整无障碍认证。

当前工作树全量回归（包含端到端验收用例；发布 tag 仍未改动）：

```text
$ venv/bin/python scripts/run_regression.py --tsv .regression-logs/full-20260921-final2.tsv
EXIT=0
测试文件总数        : 72   （pytest 71 + 脚本式 smoke 1）
pytest cases 通过   : 1031
有效失败文件        : 0
总耗时              : 7m46s
```

与 `24-minimal-workspace/phase1` 的冻结基线（66 pytest + 1 脚本 / 965 cases）相比净增
**6 个文件 / 66 cases**，其中本轮新增保存流、段落生命周期与端到端验收用例。

### 新任务端到端验收（2026-09-21）

`tests/release_e2e_acceptance_test.py` 在隔离 `OUTPUT_DIR` 中用确定性 provider 替身跑通：

```text
venv/bin/python -m pytest tests/release_e2e_acceptance_test.py -q
1 passed
```

覆盖导入含页码噪声的 DOCX、翻译中断后从磁盘恢复、排除噪声、拆分、合并、人工修改、
独立审校、生成译文/双语文档与排除清单，最后冻结 `v1` 交付快照。它验证工作流与数据
持久化，不证明真实 provider 的语言质量。

另外补上了历史任务兼容路径：没有 `delivery_config` 的旧任务也会把排除段写入
`excluded_segments.md/json`，由 `test_legacy_delivery_fallback_keeps_excluded_manifest`
守护，避免升级后的交付出现静默删除。

### 发布卫生收尾（阻塞正式发布）

> 下面的机械检查已固化为两条只读命令：
>
> - `python scripts/release_preflight.py [--ref v0.4.0]` —— 静态事实：空白 /
>   CHANGELOG 结构 / 已跟踪文件里的密钥字面量 / **已跟踪文件里的本机绝对路径** /
>   凭据是否被忽略 / `outputs/` 是否入版本控制 / 构建产物是否含敏感路径 /
>   **产物是否与发布版本逐字节一致**。
> - `python scripts/release_smoke.py` —— 行为事实：把 wheel 装进干净环境后，
>   验证导入来源是 site-packages（不是仓库）、4 个缺陷的修复行为、控制台入口点、
>   `folith --help`、以及真实 socket 的绑定语义；`foliothread` 和 `transpraxis` 入口继续作为兼容别名。
>
> 两条都全部通过才退出 0。它们**不**创建 commit / tag——那需要人判断发布单元如何切分。

- [x] `git diff --check` 干净——修掉 `docs/sidebar-project-group-ia.md` 文件末尾多余空行。
- [x] `CHANGELOG.md` 只保留一个 `## [Unreleased]` 区块，并写明它与 `0.4.0` 的边界。
- [x] 已跟踪文件与构建产物中均无密钥；`outputs/` 从未进入 git 历史。
- [x] **形成可发布的确定 commit / tag**。发布单元已合并为**单个 commit**（工作区两条工作流的
      改动在 `app.py` 上交错，无法按 diff 干净切分，故合并），并在其上创建**注解 tag
      `v0.4.0`**；`main` 已快进到该 commit，**发布自 `main`**。
      工作区里**另一条工作流**的 13 处未提交改动原样保留，未被卷入发布。
      这两句是冻结时的历史记录，不代表当前远端状态。

      2026-09-21 复核：远端 `origin/main` 已是合并提交 `fe1ad41`，本地 `v0.4.0`
      仍未推送为远端 tag；当前工作区的 UI 改动也没有进入该 tag。

      > **这里为什么不写 commit 哈希**：哈希不能写进它自己所在的提交——写进去就改变了
      > 哈希，永远自相矛盾。**以 tag 名为准**（tag 名在打 tag 之前就已知，不自我指涉）；
      > 需要哈希时现查：
      >
      > ```bash
      > git rev-parse 'v0.4.0^{commit}'        # 发布单元（= 本文件所在提交）
      > git describe --tags --exact-match HEAD
      > ```
      >
      > 曾经的教训：这里写过 `a66317a`，随后又 amend 了两次（并入脱敏、并入预检修复），
      > 文档里的哈希立刻变成错的，被发布复核当成一条"文档与 tag 不一致"的问题报了出来。
      > **自指的哈希是一个必然过期的字段——不要写。**
- [x] **本机路径与凭据脱敏**。已跟踪文件中的本机绝对路径清零（`design-qa.md` 的参考
      素材改为描述、`docs/ui-audit/21-sidebar-project-group/README.md` 的复现命令改用
      `git rev-parse --show-toplevel`、`skills/.redskill-lock.json` 不再入库）；
      `.gitignore` 凭据规则补齐（`.env` / 密钥证书 / SSH 私钥 / `credentials.json` /
      `service-account*.json` / `secrets.toml` / `.netrc` / `.pypirc` / `.npmrc` /
      `*.token` / `*.secret`）。当前已跟踪文件里 `/Users/<name>` 为 **0 处**。
- [ ] **凭据轮换（待定）**。`outputs/provider_config.json` 含一个非占位的 `api_key`。
      该文件已被 `.gitignore` 忽略、也未进入 wheel/sdist，**发布时不要打包整个工作区**。
      若该 key 曾真实可用，建议到 provider 平台重置——属平台侧操作，不在代码范围。
- [ ] **旧提交中的本机路径（待定）**。`v0.4.0` 之前的提交里仍留有 `/Users/<name>`。
      本次只清理了当前发布内容；彻底清除需重写历史（如 `git filter-repo`），
      属破坏性操作，需要单独确认后再做。
