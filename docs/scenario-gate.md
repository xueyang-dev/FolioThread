# 场景验收门禁（Scenario Gate）

本文件说明蓝图 §8 定义的三个端到端场景如何被自动化验证。它取代"完成了多少模块"
这种进度表达。涉及翻译、恢复或交付主路径的变更应运行相关门禁；纯文档修改只检查文档一致性与链接，不要求运行产品测试。

2026-09-14 范围澄清：这些场景验证既有工作流，不证明原 DOCX package 保真、真实模型翻译质量或 UI 人工效率。下一阶段的 [DOCX Contract v1](docx-contract-v1.md#验收与-fixtures) 需要独立的结构/资源保留、混合结构及实际打开检查；该组验收尚未实现。近期正式发布不以完成此未来契约为前提，见[发布计划](release-plan.md)。

- 门禁实现：`tests/scenario_gate_test.py`
- 源文档生成器：`scripts/make_scenario_fixtures.py`
- 蓝图依据：[Agentic Native Translation Studio 开发蓝图](foliothread-agentic-native-blueprint.md) §8

## 为什么需要它

单元测试验证函数，场景门禁验证"产品承诺"。两者发现的缺陷类型不同：

- 一个 60 秒的单元测试无法发现"第 2 批之后的所有 QA 发现都从 state.json 里消失"，
  因为那需要一篇超过一个批次、且在第一批之后出现缺陷的文档；
- 一个只在内存里构造 state 的测试无法发现"100 页 PDF 的页眉混进正文"，
  因为那需要真实版面。

这三个场景是目前唯一能产生这类信号的机制。

## 运行

```bash
# 只跑场景门禁（默认离线，约 8 秒）
python -m pytest tests/scenario_gate_test.py -q

# 通过既有 CI 命令运行（门禁已被 pytest 自动收集）
python -m pytest -q

# 生成源文档供人工检查
python scripts/make_scenario_fixtures.py --out tmp/scenarios
```

门禁**完全离线**：所有 provider 调用由 `tests/scenario_gate_test.py` 中的
`OfflineProvider` 承接，无网络、无 API key、无 skip 标记。
翻译**质量**不在门禁范围内——离线替身产出的是"结构有效"的译文，用于驱动状态机；
语言质量评估属于 `eval/`，见 `eval/README.md`。

仓库不提交二进制 fixture。三份源文档由生成器按固定内容重建，不使用随机数，
因此不存在"fixture 漂移"。

**确定性边界**：文本内容可重复（manifest 中每个场景的 `content_sha256` 是内容
指纹，`test_scenario_fixtures_are_content_deterministic` 会重新生成一次并比对），
但**容器字节不保证一致**——DOCX 的 zip 条目带写入时间戳，PDF 内部有文档 ID 与
交叉引用偏移。因此判断 fixture 是否漂移要用 `content_sha256`，不要用文件 sha256。

## 三个场景

| 场景 | 规模 | 门禁断言 |
| --- | --- | --- |
| 20 页 DOCX | 175 段 / 8 章节 / 约 19,500 词 | 导入无警告；文档画像成功；全部段落有译文；保留项（URL/DOI/邮箱/占位符/引用）原样回填；独立审校覆盖每段且无未决 blocking；人工确认后进入 `final` 并可冻结快照 |
| 100 页 PDF | 100 页 / 600 段 | 页眉与页码被识别为版面噪声并剔除（各 100 个）；段落边界按首行缩进恢复为 600 段；跨行连字符 `can-`/`opy` 还原为 `canopy`；中断后从磁盘状态恢复，且已提交批次不重译 |
| 术语密集文档 | 90 段 / 6 条锁定术语 | 严格治理下候选术语阻止翻译开始；人工冻结产生 v1 与 `glossary_hash`；首选译名被遵守、禁止译名不出现；交付清单绑定当时冻结的术语版本；第二次运行命中翻译记忆 |

### 快照与偏离

冻结后的交付快照必须与当前译文绑定：译文一旦被修改，
`core.delivery_snapshot_status` 必须报告 `diverged=True`，而不是继续显示"可交付"。
旧快照保留，不被覆盖。

### 人类控制点（蓝图 §4.2）

| 控制点 | 门禁验证 |
| --- | --- |
| Memory gate | 严格治理下存在未审核候选术语时，翻译不得开始，且必须向用户解释原因；冻结后可继续 |
| Review gate | 语义 blocking 必须进入人工决定队列，未决时不得交付；非人类 actor 记录决定必须被拒绝（模型不能为自己的输出背书） |
| Delivery gate | 存在未决 blocking 时 `approve_delivery` 必须拒绝，且拒绝原因必须可定位到段落；人工接受语义风险后可以交付，并把风险接受记录写入快照清单 |

结构破坏（保留项丢失）不属于可接受风险：它由 `validate_delivery_translation_state`
在风险接受路径之前拦截，`accept_blocking=True` 不能放行。

## 门禁发现并修复的缺陷

这两个缺陷都是**先被门禁发现**、之后才被修复的。保留这段记录的目的是说明门禁的
价值，以及为什么删除它会让同类问题重新变得不可见。

### 1. 多批次文档的 QA 发现被静默丢弃（高）

`translate_stage` 在整篇文档范围内持有
`findings_all = state.setdefault("findings", [])`（`core.py:1566`），而
`_commit_translation_batch` 每批结束都会调用 `save_job_state`，后者经过
`delivery.normalize_state_findings`。该函数当时执行 `state["findings"] = merged`，
**重新绑定了列表对象**，于是第一批之后的所有发现都被追加到一个已被丢弃的列表。

后果：`state.json` 里没有这些发现，但 `review_stats` 与 `has_blocking`
（由孤儿列表统计）仍然计数——即交付门禁看不到这些 blocking，
界面显示的发现数也少于实际产生数。用户可见的表现是"系统说有问题，但列不出来"。

修复：`normalize_state_findings` 改为就地更新（`state["findings"][:] = merged`）。
回归测试：`test_findings_alias_survives_per_batch_checkpoint`。

### 2. 交付拒绝不给原因（中）

`core.approve_delivery` 的拒绝理由只从 `validation["issues"]` 构造，
而 `blocking` 也可能来自 `core.validate_translation_pairs` 返回的
`blocking_findings`（确定性 QA 的 blocking）。当阻塞来自后者时，
用户只会看到泛化的"译文未通过最终交付检查"，无法知道是哪一段、什么问题。

修复：拒绝理由同时包含 `blocking_findings` 的段落位置与摘要。

## 维护约定

- 门禁断言的是**产品承诺**，不是实现细节。修改实现不应要求修改门禁；
  如果一次改动必须改门禁才能通过，先确认改变的是不是产品承诺。
- 现有工作流变更优先扩展相关场景；原 package 写回等新承诺增加专门契约验收，不强行塞入不能检测该类失败的旧场景。
- 场景规模的调整（页数、段落数）必须保持"超过一个批次"这一性质，
  否则上面第 1 类缺陷会重新变得不可见。
