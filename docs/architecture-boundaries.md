# FolioThread Phase 1：产品与架构边界

本文是 Phase 1 的边界记录。它完成产品重定位，不引入新的 agent loop、状态迁移或核心运行时行为。

## 1. 产品定位

FolioThread 的一级产品是 **长文档翻译工作空间**。用户首先看到并使用的是一条可恢复的翻译主路径：

```text
文档解析 → 文档上下文 → 术语与翻译记忆 → 翻译 → 人工审校 → 交付
```

MTI、论文和翻译实践报告不再作为产品的默认解释，而是“研究与报告”专用能力：

- 只在用户选择研究资产或报告输出时进入；
- 继续复用翻译主路径产生的证据，不另造一份译文真值；
- 保留现有 MTI 合规、案例 provenance、文献证据和报告 QA 能力；
- 不占据普通翻译任务的首屏，也不限制 FolioThread 的使用对象。

## 2. v0.4 基础设施：继续保留

这些能力服务于所有长文档翻译任务，Phase 1 不重写、不迁移：

| 基础设施 | 当前实现 | Phase 1 决策 |
| --- | --- | --- |
| 文档输入与结构恢复 | `pdf_ingestion.py`、`document_profile.py` | 保留，作为长文档入口 |
| 可恢复任务与运行状态 | `core.py`、`checkpoint.py`、`state_migration.py` | 保留，继续支持中断恢复 |
| 上下文与语义单元 | `context.py`、`entity_registry.py`、`knowledge.py` | 保留，作为长文档连续性的基础 |
| 术语治理与翻译记忆 | `terminology.py`、`assets.py`、`checkpoint.py` | 保留，术语与 TM 仍是主路径资产 |
| 翻译、审校与证据 | `translation_protocol.py`、`translation_evidence.py`、`repair.py` | 保留，不改变真值和审校语义 |
| 交付、快照与页面 QA | `delivery.py`、`snapshots.py`、`rendered_qa.py`、`finalization.py` | 保留，作为可追溯交付基础 |
| Provider 与模型配置 | `core.py`、`model_roles.py`、`gui.py` | 保留，Phase 1 不改变调用方式 |

公共品牌已经改为 FolioThread，但 v0.4 的 Python import namespace `transpraxis`、既有状态字段、内部 artifact ID、`transpraxis:` 导出字段和 `TRANSPRAXIS_*` 环境变量继续保留。这些是技术兼容边界，不是产品定位。

## 3. MTI / 论文能力：legacy / specialized

以下能力继续存在，但属于可选、专用的研究下游，而非 FolioThread 的默认产品中心：

| 专用能力 | 组成 | 进入条件 |
| --- | --- | --- |
| 研究模型与学术写作 | `academic_writer.py`、`academic_evidence.py`、`academic_validator.py`、`academic_quality.py` | 开启研究报告 |
| 案例与人工证据 | `case_analysis.py`、`case_presentation.py`、`case_provenance.py`、`human_evidence.py` | 需要案例分析或人工补充 |
| 文献与报告结构 | `literature_evidence.py`、`report_evidence.py`、`report_template.py` | 选择研究资料或报告模板 |
| MTI 规则与终稿 QA | `thesis_constraints.py`、`compliance.py`、`final_docx.py`、`rendered_qa.py` | 使用 MTI/报告型交付 |
| 专用 UI | “研究与报告（专用能力）”、案例、合规与报告工作区 | 用户主动进入专用工作流 |

`MTI_PRACTICE_REPORT_DEFAULT`、`translation_practice_report` 等内部 profile/schema 名称暂不改动。它们描述的是现有专用能力的技术契约，不应被误读为 FolioThread 的全局产品定位。

## 4. v0.5 演化方向

v0.5 在现有边界上演化，不在 Phase 1 提前实现：

| 方向 | 目标 | 复用 v0.4 的什么 | Phase 1 不做什么 |
| --- | --- | --- | --- |
| **Project Memory** | 保存跨文档、跨任务可复用的术语、实体、风格和人工决策 | 术语、TM、entity registry、任务状态 | 不把 TM 直接改造成通用记忆库 |
| **Agentic Context** | 为每个工作步骤提供有边界、可追溯的上下文包与证据 | `context.py`、evidence、document profile | 不加入自主循环或无界检索 |
| **Human Decision** | 将审校、批准、拒绝、覆盖和风险接受变成明确决策记录 | review findings、case review、finalization | 不让模型批准自己的输出 |
| **Delivery** | 将资产、验证事实、版本和交接统一为发布包 | `delivery.py`、snapshots、manifest、QA | 不新建第二套交付流水线 |

其中 Delivery 是 v0.4 已有能力的演化方向，不意味着 Phase 1 要重写交付；Project Memory、Agentic Context 和 Human Decision 也不要求现在修改现有状态 schema。

## 5. 命名与迁移规则

- 用户可见产品名、页面标题、启动器、README、发布链接和资源名使用 `FolioThread`。
- `transpraxis/` 目录继续作为 v0.4 稳定内部模块边界；当前阶段不进行全仓库 import rename。
- `foliothread` 是新的公开安装包名和 console 入口；`transpraxis` 入口作为 v0.4 legacy alias 保留。
- 现有 `TRANSPRAXIS_API_KEY`、`TRANSPRAXIS_EVAL_API_KEY` 等环境变量保留，避免把品牌迁移误变成运行时迁移。
- 旧的论文全文、渲染页面、临时截图和旧 logo 不属于产品资产；它们不应进入仓库。`.codex_tmp/` 已加入忽略规则。

## 6. Phase 1 明确不做

- 不改翻译、审校、报告生成、快照、交付门禁或状态恢复的核心行为；
- 不改现有 MTI profile 的判断规则和 artifact schema；
- 不加入 agent loop、自动决策、Project Memory 数据库或新的检索层；
- 不通过 feature flag、迁移框架或兼容 wrapper 预留尚未发生的运行时分支。
