# 23 · 「术语与翻译记忆」信息层级减法重构

捕获日期：2026-09-19 · Streamlit 1.63.0 · Python 3.11.3 · 视口 1440 / 1280 / 1024 × 900/800

本轮是**信息层级减法**：减少同屏并存的元素数量，而不是把字号、间距、圆角调小。
页面入口 `app_view == "library"`（侧栏「术语与翻译记忆」），数据直接取本机 `outputs/`
（术语库 72 / 翻译记忆 0 / 待审核 318 / 冲突 0）。**未改动数据模型、schema、API。**

## 复现步骤

```bash
# 1) 起应用（仓库根目录；本轮验证时应用常驻 127.0.0.1:8501）
./venv/bin/streamlit run app.py --server.headless true --server.port 8501 \
  --server.address 127.0.0.1

# 2) 截图 + 实测（本机 playwright-core + Chrome）
FOLIO_PLAYWRIGHT_CORE=~/Dev/grok-workspace/node_modules/playwright-core \
FOLIO_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
node docs/ui-audit/23-language-assets-hierarchy/audit.js \
  http://127.0.0.1:8501 docs/ui-audit/23-language-assets-hierarchy
```

`audit.js` 依次：进入「术语与翻译记忆」→ 截默认列表态 → 展开高级筛选 → 打开 Inspector
→ 关闭 Inspector → 缩到 1280 / 1024 各截开/关 → hover 侧栏「项目」入口截 tooltip。
每一步同时 `page.evaluate()` 读 **computed style / getBoundingClientRect**，输出到 stdout。
**看截图看不出「规则写了但没生效」，所以实测值才是验收依据。**

## 截图

| 文件 | 内容 |
|---|---|
| `01-terms-1440-default.png` | 1440 默认态：PageHeader + Tab(计数) + Toolbar + 结果元信息 + 表格全宽（**无 Inspector**） |
| `02-terms-1440-filters-open.png` | 展开「更多筛选」后的面板（状态 / 目标语言等） |
| `03-terms-1440-inspector.png` | 选中一行后 Inspector 展开（380px，右侧） |
| `04-terms-1280-inspector.png` / `05-terms-1280-closed.png` | 1280：Inspector 改为整列堆叠 / 收起 |
| `04-terms-1024-inspector.png` / `05-terms-1024-closed.png` | 1024：同上 |
| `06-sidebar-tooltip.png` | 侧栏「项目」入口 tooltip（短文案 + 宽度上限） |
| `07-table-head-hairline-before.png` | **修复前**：表头 hairline 穿过文字（表头区放大裁剪） |
| `08-table-head-hairline-after.png` | **修复后**：hairline 落在文字下方 |

## 实测值（浏览器 computed style，非代码推断）

| 断言 | 1440 | 1280 | 1024 |
|---|---|---|---|
| 默认态列表宽 `st-key-la_list` | **992px（= 主区全宽）** | 948px | 724px |
| 默认态 Inspector | **`null`（不渲染）** | `null` | `null` |
| 选中后 Inspector 宽 | **380px**（固定，`@media min-width:1281`） | 948px（整列） | 724px（整列） |
| 选中后列表宽 | 992px（不变，**push 而非挤压**） | 948px | 724px |
| 主区横向溢出 `mainOverflowX` | false | false | false |
| 标题 `h1` 字号 | 26px | 26px | 26px |
| 一级 Tab 文案 | 术语库 72 / 翻译记忆 0 / 待审核 318 | 同 | 同 |
| 表头列宽 术语/推荐译法/分类·作用域/使用次数/状态/操作 | 284/235/185/76/66/**66** | 271/224/176/72/63/63 | 204/168/131/52/45/45 |
| 表头是否折行 | 全部 1 行（`clientWidth == scrollWidth`） | 1 行 | 1 行 |
| 高级筛选面板 | 收起 `display:none` 0×0 → 展开 `display:flex` 992×70 | — | — |
| 行高（未选中 / 选中） | 47px / 63px | 同 | 同 |
| PageHeader 高 | 100px | 100px | 100px |
| 「＋ 新建术语」按钮 | 250×34 | 238×34 | 180×34 |
| tooltip `max-width` / 实际宽 | **260px / 150px**（实测就是 hover「项目」入口那条） | — | — |

对照点（差异只在「有没有选中项」这一维上）：改造前右侧 Inspector 即使**没有选中任何条目**
也照样渲染，其内容宽实测约 285px、且列表区被这一列永久占去一部分；现在默认态
`inspector === null`（这一列根本不存在）、列表 992px，选中后才出现固定 380px 的面板，
且**列表宽度保持 992px 不变**（推挤而非压缩 —— 见上表「选中后列表宽」一行）。

## 本轮定位到的五个真问题（都会让「看起来改了但没生效」）

1. **空 Inspector 常驻挤压主表 —— 根因是 `st.columns` 无条件渲染。**
   旧实现先建两列再往里填，于是没有选中项时右列依旧占位、渲染一张空提示卡。
   修复：`_la_selected_row()` 返回 `None` 时**完全不建列**、只渲染 Tab 主体（走全宽）；
   有选中项才 `st.columns([0.62, 0.38])`。列宽比例只表达「推挤意图」，真实宽度由 CSS
   固定在 380px。
2. **标题字号改了但没生效 —— 根因是全局 `!important` 级联。**
   `h1 { font-size: 34px !important }`（app.py 约第 194 行）会压过任何**不带 `!important`**
   的选择器，与特异性无关。所以 `:has(.st-key-la_page_header) .tp-title h1 { font-size: 26px }`
   是死规则（连更早的移动端 `26px` 规则也是同一个原因一直在失效）。
   修复：给作用域覆写加 `!important`。实测 computed = 26px。
3. **Inspector 宽度只有 285px（低于 360–400 目标）—— 根因是「比例列」不等于「固定宽」。**
   `st.columns([0.68, 0.32])` 在 1440 下右列只有 285px。修复：加
   `@media (min-width:1281px)` 把最后一列钉成 `flex: 0 0 380px !important`，主列
   `flex: 1 1 auto !important`。
4. **「操作」列塌到 19px —— 根因是 6 列按比例分，最小列拿不到可用宽度。**
   修复：`_LA_TERM_TABLE_COLUMNS` 里操作 0.05 → 0.08，并把推荐译法 0.26→0.25、
   分类·作用域 0.21→0.20、状态 0.09→0.08。实测 1440 表头 66px、1280 63px、1024 45px。
5. **表头那条 hairline 穿过文字（产品复核时发现）—— 根因是 Streamlit 注入的
   `-16px` 对 `<div>` 是纯塌陷。** 表头单元格渲染成 `<div class="la-head">`，没有 `<p>`
   的默认段落边距；但 Streamlit 照样给每个 `stMarkdownContainer` 注入 `margin-bottom:-16px`
   去补偿段落边距。对 `<div>` 就是白白扣掉 16px：**表头容器被压成 1.6px 高**，而
   `border-bottom`（hairline）画在容器底边，于是线被抬到文字腰上、把
   「术语 / 推荐译法 / 分类·作用域 / 使用次数 / 状态 / 操作」齐齐划掉。
   修复：`[class*="st-key-la_head_row"] [data-testid="stMarkdownContainer"] { margin-bottom:0; }`
   （同类修法仓库里已有先例：侧栏品牌块、`.st-key-advanced_body`）。

### 表头修复实测（`probe-table-head.js`）

| 量 | 修复前 | 修复后 |
|---|---|---|
| 表头容器高 `st-key-la_head_row` | **6.6px**（文字实际 17.6px → 溢出） | **22.6px** = 17.6 文字 + 4 padding + 1 边框 |
| 单元格 `stMarkdownContainer` 下边距 | **−16px** | **0px** |
| hairline 相对文字底部的偏移 | **−11.5px（在文字内部 → 穿过文字）** | **+4.5px（在文字下方）** |
| 表格首行高 | 47px | **47px（未变）** |
| 行内单元格下边距 | −16px | −16px（**有意不动**，见下） |

前后对照见 `07-table-head-hairline-before.png` / `08-table-head-hairline-after.png`。

> **行内单元格的 −16px 本轮不动。** 行的 `border-bottom` 挂在 47px 高的行容器上，
> 容器没有被压塌，所以横线没有出问题；改它会让行高/密度一起变（行 CSS 注释里的目标
> 其实是 56–76px，当前 47px 就是这条注入边距"吃"出来的）。这是**另一个**待决策项，
> 不属于"修表头横线"的范围 —— 已记录为后续问题，未擅自改动。

## 一个需要记住的 Streamlit 行为（决定了「更多筛选」的实现方式）

**一个本轮没有渲染的 keyed widget，它的旧值会被丢弃（下次挂载 → 回到默认值）。**
所以「更多筛选」**不能**做成「收起时 `if` 掉、不渲染」，否则收起一次筛选状态就归零、
结果元信息里的「筛选 · N」与真实结果不一致。
采用：面板内 widget **始终挂载**，收起时只注入一段 `<style>` 把
`[class*="st-key-la_terms_adv_panel"]` 设成 `display:none`。
于是 session_state 始终是唯一事实源，DOM 里也没有可见占位（实测收起 0×0）。
`_la_advanced_panel()` 返回当前开合态，供测试断言这个契约。

## 测试

直接相关的一批（`scripts/run_regression.py` 逐文件独立进程，`--tsv` 落盘）：

```bash
venv/bin/python scripts/run_regression.py \
  -k language_assets,app_boot,context_knowledge,sidebar_project_switcher,\
inbox_project_density,ui_console,terminology_governance,history_library,phase35_workspace_view \
  --tsv /tmp/folio_round23b.tsv
# → 9 文件 / 172 pytest cases + 1 脚本式 smoke / 0 失败 / 3m17s
```

| 文件 | 结果 | 与本轮的关系 |
|---|---|---|
| `tests/language_assets_workspace_test.py` | **45 passed** | 主回归。**新增 7 个契约用例**：计数落在一级 Tab、冲突不成为第四视图、「新建术语」是页级主动作且任意 Tab 可用、**未选中时 Inspector 不存在**、高级筛选收起后仍有可见入口且不丢状态、表格合并低优先元数据并保留术语在前、**表头 hairline 落在文字下方（含行内密度不许顺带改动）** |
| `tests/context_knowledge_ui_test.py` | 4 passed | 断言从「必须有 `la-summary`」翻转为「顶部统计卡必须删掉」 |
| `tests/sidebar_project_switcher_test.py` | 21 passed | 新增「项目 tooltip 是短语且有宽度上限」 |
| `tests/terminology_governance_test.py` | 32 passed | 术语治理**业务逻辑**未动，作为反证 |
| `tests/history_library_test.py` | 32 passed | 库页导航/深链未受影响 |
| `tests/phase35_workspace_view_test.py` | 8 passed | Phase 3.5 工作区视图 |
| `tests/inbox_project_density_test.py` | 20 passed | 含「每条图标规则必须绑定图标字体」的防线 |
| `tests/ui_console_test.py` | 10 passed | 应用外壳 / 控制台 |
| `tests/app_boot_test.py` | exit=0 | 脚本式整应用启动冒烟 |

单文件跑法（如需复验单个文件）：

```bash
TMPDIR=$(mktemp -d) venv/bin/python -m pytest tests/language_assets_workspace_test.py \
  -q --no-header -p no:cacheprovider --basetemp "$TMPDIR/base"
```

> 单文件跑必须用私有 `TMPDIR`：本沙箱 python shim 会把 pytest basetemp 的 `EEXIST`
> 抛成致命错误，第二次起每个 pytest 进程都在 setup 阶段炸掉（症状：exit 1 且没有
> `N passed` 汇总行）。走 `scripts/run_regression.py` 则不需要自己设。

## 相关文档

- 上一轮同页面重构：[`docs/ui-audit/language-assets/REFACTOR-REPORT.md`](../language-assets/REFACTOR-REPORT.md)
- 侧栏 IA 冻结约定：[`docs/sidebar-project-group-ia.md`](../../sidebar-project-group-ia.md)
