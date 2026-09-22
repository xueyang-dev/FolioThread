# 第一阶段视觉验收：几何实测

这是 `docs/ui-audit/24-minimal-workspace/README.md` 第一阶段（UX-01/02/03/05/06/11）
的**几何取证**。它补的是审计报告明确要求、但第一版施工记录里还欠着的那部分：

> 验收：1440×900、有段落的翻译页面中，首段起始位置目标位于视口顶部 360 CSS px 以内
> （高度的 40%），不要求长段落完整显示。… 该几何目标是待截图验证的设计目标，
> 不是当前测量结论。

（README 第 168 行，原文把它列在第二阶段验收下，但第一阶段的重排已经决定性地影响了它，
因此在这里一并取证。）

数值全部来自 `getBoundingClientRect()` / `getComputedStyle()`，不是肉眼看截图。

## 复现

```bash
# 1) 起应用（仓库根目录）
venv/bin/streamlit run app.py

# 2) 造一个真正处于 interrupted 的任务（其余 fixture 已由
#    scripts/ui_audit_fixtures.py 产出）
venv/bin/python docs/ui-audit/24-minimal-workspace/phase1/make_interrupted_fixture.py

# 3) 实测几何 + 截图
cd docs/ui-audit/24-minimal-workspace/phase1
FOLIO_PLAYWRIGHT_CORE=~/Dev/grok-workspace/node_modules/playwright-core \
FOLIO_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
node audit.js http://127.0.0.1:8501 .

# 4) 所有工作台分区的渲染扫描（工具栏是所有 section 共用的，不能只看翻译页）
TMPDIR=$(mktemp -d) venv/bin/python section_sweep.py
```

只读：不改任务数据，不调用付费模型。

目录里还有两个排错用的探测脚本（不是验收脚本）：

- `probe.js`——按选择器逐层打印 `top/height` 与 computed style，用来回答"首屏被什么吃掉"；
- `probe3.js`——打印任意子树的 DOM 骨架（标签 / testid / class / 盒模型），
  用来在写 CSS 选择器前确认 Streamlit 组件的真实结构。

## 结论

| 任务 | 视口 | Banner 高 | 工具栏高 | **首段 top** | 横向溢出 | verdict chip | 运行区 | 主动作 |
| -- | -- | -- | -- | -- | -- | -- | -- | -- |
| `ui-audit-clean` | 1440×900 | 46 | 46 | **338** ✅ | 无 | 1 | 无 | 准备交付 |
| `ui-audit-interrupted` | 1440×900 | 142 | 46 | 434 | 无 | 1 | 上次运行已中断 | 继续处理（运行区） |
| `ui-audit-new-untranslated` | 1440×900 | 142 | 46 | — 无段落 | 无 | 1 | 未完成 | 继续处理（运行区） |
| `ui-audit-clean` | 1024×768 | 46 | 46 | **350** ✅ | 无 | 1 | 无 | 准备交付 |
| `ui-audit-clean` | 720×450（≈200% 缩放） | 46 | 48 | **352** ✅ | 无 | 1 | 无 | 准备交付 |

**360px 目标在三个视口下都达成**（338 / 350 / 352）。带运行区的任务首段更靠下，
是因为运行区本身承载「继续处理」——那是本阶段的验收要求（"中断可恢复"），不是留白。

200% 缩放这一列不是走过场：它**查出一条一直没生效的响应式规则**（见下）。

另外用 `section_sweep.py` 扫了 **5 个任务 × 7 个 `workspace_section` = 35 种组合**：
全部无异常渲染，`任务详情` 在每一个分区都可达，`tp-workspace-toolbar-head` 一处都不再出现。
工具栏是所有 section 共用的，只测翻译页不足以说明问题。

上一节的所有结论都对应一个**冻结版本**（本目录写完后再未改过 `app.py`）：

```text
$ venv/bin/python scripts/run_regression.py --tsv .regression-logs/phase1-geometry.tsv
EXIT=0
  pytest 文件数       : 66
  脚本式 smoke      : 1
pytest cases 通过   : 965
有效失败文件        : 0
总耗时              : 20m36s
```

66 个 pytest 文件 + `app_boot_test.py`（脚本式冒烟，不是 pytest 用例）= 67 行，
逐行 `exit_code` 均为 0。上一轮同规模是 960 cases，本阶段净增 5 条（
`task_overview_ui_test` 18→22、`ui_console_test` 10→11）。

### 手抄一遍，就不会退化

`audit.js` 的原始输出：

```text
1440-clean  {"banner":{"top":89,"w":1376,"h":46},"toolbar":{"top":151,"w":1376,"h":46},
             "bannerCols":[748,392,166],"firstRowTop":338,"rowCount":3,"mainOverflowX":false,
             "hasContextColumn":true,"verdictChips":1,"navCanonicalChips":0,"overviewHero":0,
             "overlapCards":0,"bannerMetrics":["已译 3 / 3 段","术语 1","审校 3 / 3",
             "最近保存 9 月 11 日 01:17"],"runtimeRow":false,"primaryCta":"准备交付",
             "taskDetailsChip":{"top":159,"w":94,"h":30}}
1024-clean  {"banner":{"top":101,"h":46},"toolbar":{"top":163,"h":46},
             "bannerCols":[521,272,113],"firstRowTop":350,"rowCount":3,
             "mainOverflowX":false,"verdictChips":1,"navCanonicalChips":0}
zoom200-clean {"banner":{"top":95,"h":46},"toolbar":{"top":143,"h":48},
             "firstRowTop":352,"rowCount":3,"mainOverflowX":false,
             "verdictChips":1,"navCanonicalChips":0}
1440-interrupted {"banner":{"top":89,"h":142},"runtimeRow":true,"runtimeState":"上次运行已中断",
             "runtimeButtons":["继续处理"],"primaryCta":null,"firstRowTop":434}
```

## 这一轮是怎么把首段从 504 提到 338 的

第一版施工（上一轮）的实测是 `firstRowTop = 504`（1440）/ `535`（1024）。逐层量下来，
吃掉首屏的是四段各自独立的间距，不是某一处"大留白"：

| # | 来源 | 改动前 | 改动后 | 依据 |
| -- | -- | -- | -- | -- |
| 1 | Banner 实际是**三行**：身份 86 + 间距 15 + 「任务详情」展开器 42 | 158 | **46** | 报告 §"Banner 的具体设计约束"明写"紧凑两行" |
| 2 | 状态块 `flex-direction:column` 把右列撑到 86px | 含在上面 | 含在上面 | 它只装一行的内容（chip + detail），改横排 |
| 3 | 工具栏的「工作台」kicker（7px）+ 间距 23px | 69 | **46** | UX-02 整改原话："工具栏只保留当前页面导航" |
| 4 | `.tp-cat-title h2` 被 Streamlit 默认 `padding:16px/16px` 撑成 54px 的盒子 | 60 | **28** | 作用域规则只重置了 `margin`，是漏写，不是设计 |

第 4 条值得单独说明：`<h2>翻译</h2>` 的行内文字只有 21.6px，盒子却有 54px——
比 Banner 的指标行还高。这类"全局默认值泄漏进作用域组件"的问题在截图里看起来只是
"上面空了一点"，只有读 computed style 才会暴露。回归断言见
`tests/task_overview_ui_test.py::test_the_translation_heading_is_not_padded_by_the_global_rule`。

## 关键结构变化

- 「任务详情」从 Banner 内的整行展开器移到**工具栏右端**：30px 高的 chip，收起时
  贴合文字宽度并右对齐，展开时用满整列（1440 下 315px 宽，够放完整文件名 + 复制按钮）。
  一句话：一个低频入口不再要求每个任务的正文让出 57px。
- 「工作台」kicker 与 canonical status chip 一起删除。
- **窄屏 / 200% 缩放改回"堆叠"**：这是 200% 缩放那一列查出来的**一直没生效的规则**。
  `@media (max-width: 900px)` 里"正文与 Inspector 堆叠"的选择器写的是
  `:has(.st-key-workspace_nav_col)`，而 `st-key-workspace_nav_col` **只存在于 CSS**——
  页面导航早已改成 Banner 下的横向工具条，渲染代码从不产出这个 key。于是
  720 CSS px 下正文只剩约 500px，搜索框和「筛选 ▾」被截断成 `筛..`（正是 `MEMORY.md`
  里记过的"一眼像 bug 的截断"）。同一批死规则的还有 761–1199px 那组网格：
  它瞄的是**已经不存在的三列布局**，实际生效的一直是 `st.columns([4.25, 1.55])`。
  现在锚点改为真实渲染的 `st-key-workspace_context_col`，并删掉那组死网格。
  1024 / 1440 的实测值**一个都没变**（因为死规则本来就没生效），只有 <901px 从"挤压"
  变成"堆叠"（截图 `06-workbench-zoom200.png`）。
- 回归防线：
  - `test_the_task_details_are_not_a_third_banner_row`——Banner 不得渲染任务详情；
  - `test_the_toolbar_carries_page_navigation_only`——工具栏不得再有 kicker / canonical chip；
  - `test_the_translation_heading_is_not_padded_by_the_global_rule`——标题块 padding 归零；
  - `test_workspace_responsive_rules_anchor_on_a_rendered_column`——响应式规则不得挂
    在渲染代码里不存在的容器上（这类规则是静默失效的）；
  - `test_a_cleared_job_gets_no_resume_action`——任务被清掉后的空 shell 不得挂「继续处理」。

## 这次特意没有做的事

- **没动 `← 任务列表 / 主页`**（26→55px）。侧栏在工作区里是隐藏的，这两个按钮是回到
  任务列表 / 主页的**唯一**通道；报告也没把它们列为问题。要再压首屏只能动它，但那属于
  全局导航 IA（`docs/sidebar-context-vs-center.md` 已冻结），不在本阶段范围。
- **没动 术语 / 审校 / 报告 / 交付 这些分区页的 `tp-section-kicker + h2`**：它们有同一个
  `padding:16px` 泄漏，但那几页的留白与噪声是 UX-07（第二阶段）的范围，混进来会让
  这一轮无法按单一原因回归。**已记录为阶段性发现**（见下）。
- **没有为接近目标而调 `padding-bottom`、按钮高度之类的数字**：上面 4 条都是"这行本来
  就不该存在 / 这个属性本来就漏写了"，不是调参。

## 阶段性发现（未在本轮修）

1. **同一处 `h2` padding 泄漏还在 6 个工作台分区页 + 项目页 2 处**：`app.py` 的
   `<div class="tp-section-kicker">…</div><h2>术语</h2>`（术语 `10169` / 案例终审 `10723` /
   合规与最终 QA `10989` / 最终交付 `12420`）、审校工作台（`10484`）、报告（`12185`），
   以及项目页的两处空状态标题（`14157` / `14164`）。
   它们**连作用域规则都没有**——本该管这件事的
   `.tp-workspace-main h2 { margin:2px 0 5px; font-size:21px !important }`（`app.py:3155`）
   是一个**从未被渲染的死选择器**（`tp-workspace-main` 在渲染代码里不存在），
   所以这 6 个分区标题实际吃的是全局 `h2 { font-size:23px !important }` 加上 Streamlit 的
   默认 padding。**属于 UX-07/09（第二、三阶段）**。
2. **中断态下 Banner 的状态复述了两遍**：canonical verdict 显示「处理中断」，
   紧跟的运行区又显示「上次运行已中断」。两者语义不同（业务态 vs 运行态）且运行区
   还携带进度与动作，所以没有合并；但如果第二阶段继续压缩，这是第一个候选。
3. **`_RUNTIME_ACTION_STATUSES` 的取舍仍是硬编码清单**：它决定"运行区是否已承担主动作"。
   新增运行状态时必须同步维护，否则同屏会出现两个「继续处理」。

## 仍未验证

审计报告 §"无法仅靠截图确认的项目"要求的大部分**仍然没有**证据：

- ~~200% 缩放下 `firstRowTop`~~ —— **本次已量**（352px，无横向溢出，且改为堆叠）；
  但"长文本在 200% 缩放下的重排是否可读"仍需人眼，本页只给了几何与一张截图。
- 键盘顺序、焦点可见性、`任务详情` chip 关闭后的焦点回位。
- 屏幕阅读器朗读顺序：Banner 现在是三列（标题 / 状态 / 主动作）+ 工具栏两列
  （导航 / 任务详情），其 **DOM 顺序等于视觉顺序**（左→右、上→下），但这一点
  是用代码顺序推断的，没有用辅助技术实测。
- 自动轮询（`run_every="3s"`）期间不丢输入 / 不反复滚动。

这些需要真实浏览器 + 交互脚本。`probe.js`（垂直堆叠 + computed style）与
`probe3.js`（任意子树的 DOM 骨架）留着做后续调试。
