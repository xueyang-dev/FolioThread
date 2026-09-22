# Folith / 译页扫描 PDF ingestion / OCR / 原文纠错性能审计

## 结论先行

原始慢点是两个串行等待叠加：扫描 PDF 的 OCR 是主线程逐页
`render -> subprocess.run(tesseract) -> next page`，而原文纠错虽然内部曾经
保留过线程池分支，生产调用没有传 `parallelism`，实际等价于
`for batch: await/call model`。因此 CPU / GPU / RAM 不高并不能说明流程健康：
墙钟时间被远程模型响应和逐页外部进程等待占满。

当前实现把这两处都改成有界并发，但保留顺序合并、逐项校验和 checkpoint：

* LLM cleanup 默认最多 4 个同时请求，可由任务参数或
  `FOLIOTHREAD_LLM_CLEANUP_CONCURRENCY` 配置，结果按原始 batch 顺序应用。
* OCR 默认 2 个 Tesseract worker，producer / bounded queue / worker 结构由
  `FOLIOTHREAD_OCR_WORKERS`、`FOLIOTHREAD_OCR_QUEUE_SIZE` 配置；PDF 页面只在队列
  和当前渲染对象中驻留，不一次性缓存整本图片。
* 每个成功 OCR 页和每个成功 cleanup batch 都会原子写入 checkpoint；失败 batch
  不会伪装成完成，已完成结果不会因单个 batch 失败而丢失。

## 实际调用链

正常任务入口是 `core.run_job_pipeline`。扫描 PDF 的实际路径如下：

```text
run_job_pipeline
  └─ extract_document_paragraphs_with_report
       ├─ _pdf_extraction_facts                 PDF 分类事实：页数、文本页、空页、图片数
       ├─ transpraxis.pdf_ingestion.extract_pdf_paragraphs
       │    ├─ extract_layout_blocks             PyMuPDF text/image blocks
       │    ├─ classify_blocks                   header/footer/page-number/caption 等角色
       │    ├─ _line_groups                     行与缩进分组
       │    └─ reconstruct_paragraphs            断行、跨页、段落恢复
       └─ 若没有正文段落：_ocr_pdf_text_with_warnings
            ├─ PyMuPDF page.get_pixmap(dpi=220)  rasterize
            ├─ bounded queue                    backpressure
            ├─ _ocr_page_with_tesseract         本地 Tesseract TSV OCR
            ├─ _parse_tesseract_tsv             block 文本与真实 confidence
            ├─ edge page-number/header/footer    确定性噪声剔除
            └─ _ocr_text_to_paragraphs           OCR block → 段落
  └─ core.cleanup_source_paragraphs
       └─ transpraxis.source_cleanup.cleanup_source_paragraphs
            ├─ deterministic cleanup            whitespace / obvious line join / hyphenation
            ├─ confidence gate                  high-confidence OCR bypasses LLM
            ├─ bounded LLM batches               retry / request gate / strict JSON schema
            └─ ordered merge                     source item order preserved
  └─ segment_build
       ├─ transpraxis.segmentation.segment_paragraphs
       │    ├─ cleaned paragraph → sentence-sized CAT units
       │    ├─ conservative exceptions: heading/list/table/URL/abbreviation
       │    └─ ordered paragraph range map for audit and export
       ├─ state["source_paras"] / state["source_paragraphs"] / state["paras"] checkpoint
       ├─ source quality gate
       └─ 后续 `translate_stage` 使用 `state["paras"]` 构造可翻译 segment
```

显式的“重新扫描 PDF”入口 `rescan_pdf_source` 复用同一条 extraction / cleanup
链，不会偷偷进入后续翻译阶段。

## 审计矩阵

| 阶段 | 模块 / 函数 | 原始行为 | 当前行为 | 网络等待 / worker |
| --- | --- | --- | --- | --- |
| pdf_classify | `core._pdf_extraction_facts` | 同步 | 同步，按页读取事实 | 1 个本地执行流，无网络 |
| layout_recovery | `transpraxis.pdf_ingestion.*` | 同步 | 同步，PyMuPDF layout classifier | 1 个本地执行流，无网络 |
| rasterize | `core._ocr_pdf_text_with_warnings` | 与 OCR 串行、逐页渲染 | producer + bounded queue | 1 个 renderer；queue 默认 4 |
| ocr | `_ocr_page_with_tesseract` | 每页 `subprocess.run`，主流程串行 | worker threads，有序回收 | 默认 2 个 Tesseract worker |
| deterministic_cleanup | `source_cleanup._deterministic_prepare` | 没有独立可见 stage | 同步、低成本 | 1 |
| llm_cleanup | `source_cleanup.cleanup_source_paragraphs` | 生产默认 `parallelism=1`，batch-by-batch 串行；网络等待占主墙钟 | 有界 worker queue，默认 4；结果按 batch index 合并 | 最大 4 个请求；可选 request interval |
| segment_build | `transpraxis.segmentation.segment_paragraphs` + `run_job_pipeline` | 与 state 写入混在阶段末尾；清洗段落直接作为翻译段 | 清洗段落先保留在 `source_paragraphs`，普通 prose 按句生成有序 CAT 单元；标题、列表、表格、缩写等保守不拆 | 1 |

### CAT 断句契约

原文纠错仍以“恢复后的段落”为输入，避免模型在缺少版面上下文时误判断行；扫描 PDF 的
翻译和 CAT 工作台则使用句级 `state["paras"]`。PDF 默认模式是 `sentence`，每个输入段落只在
本段内部拆分，不跨段拼接。以下内容保持一个结构单元：标题、列表项、表格行、URL / 邮箱、
小数、常见缩写和没有可靠终止标点的短行。逗号、冒号、分号也不会被当成句界。

清洗后的段落仍可从 `state["source_paragraphs"]` 和 stage-1 原文产物中读取；
`state["segmentation"]` 记录规则版本、输入段落数、输出翻译单元数和段落范围映射。
非 PDF 导入默认保留既有段落级 contract；如需让 DOCX/text 也按句，可给
`run_job_pipeline(..., segmentation_mode="sentence")`；如需兼容旧的 PDF 段落级导入，
可传 `segmentation_mode="paragraph"` 或设置 `FOLIOTHREAD_SEGMENTATION_MODE=paragraph`。
任务一旦完成原文阶段，模式会随状态保存，恢复时不会因环境变化而重新解释已有单元。
已有翻译任务不会被后台静默重分段；显式 PDF 重扫会重新建立源段落、CAT 单元和下游对齐。

### LLM cleanup 的并发、重试和 checkpoint

配置优先级是显式任务参数 → 已保存 `pipeline_config` → 环境变量 → 默认值：

* `source_cleanup_concurrency` / `FOLIOTHREAD_LLM_CLEANUP_CONCURRENCY`：默认 4，上限 16。
* `source_cleanup_max_retries` / `FOLIOTHREAD_LLM_CLEANUP_MAX_RETRIES`：默认 2。
* `source_cleanup_request_interval` / `FOLIOTHREAD_LLM_CLEANUP_REQUEST_INTERVAL`：默认 0，按 provider 限额设置秒数。
* `max_batch_chars=6200`、`max_batch_items=32` 是 cleanup 默认 batch 上限，仍可按任务覆盖。

只有 transport / timeout / provider unavailable / rate-limit 会自动重试；协议 JSON
错误不会盲目重试，而是保留该 batch 的 deterministic source 文本并给出 warning。
成功结果写入 `source_cleanup_checkpoint.json`，成功之后才进入 ordered merge；
因此取消或 provider 失败不会清掉已经完成的 batch。

### OCR runtime 事实

当前实现实际使用的是：

```text
backend=tesseract
model=tesseract-lstm
device=cpu
provider=tesseract
execution_provider=native_cpu
gpu_name=null
```

这不是“配置宣称支持 GPU”而是运行时事实。若 `FOLIOTHREAD_OCR_DEVICE` 请求
`cuda` / `gpu` 等非 CPU 值，会记录可见 warning，说明当前 Tesseract 实际仍为 CPU；
当前代码没有 PaddleOCR / ONNX CUDA backend，也不会把 Tesseract 假报成 GPU。

## 结构化性能统计

每个任务的 `outputs/<job_id>/performance.json` 记录：

* stage name、UTC started / finished、wall time；
* item / page / batch count 与 per-item latency；
* queue wait、API latency、retry count、实际并发数；
* OCR backend / model / device / execution provider / GPU name；
* OCR 页 checkpoint/cache 数量、LLM bypass ratio、deterministic merge 数量。

覆盖的 stage 名称固定为：
`pdf_classify`、`rasterize`、`ocr`、`layout_recovery`、
`deterministic_cleanup`、`llm_cleanup`、`segment_build`。
不适用阶段会记录为 `skipped`，而不是伪造耗时。

## deterministic cleanup / confidence gate

OCR block 的真实 confidence 进入 extraction report。cleanup 在 LLM 前执行：

* 空白规范化；
* 明确的英文行末连字符拼接；
* 明确未结束句 + 小写开头下一项的 line join；
* replacement character、重复标点、低文本密度或低于阈值的 OCR item 进入 LLM。

默认阈值为 88。高 confidence 且没有明显不确定性信号的 item 直接走 deterministic
路径，并在 `source_cleanup` metadata 中报告：
`llm_input_count`、`llm_bypassed_count`、`llm_bypass_ratio`、
`uncertainty_counts`。这不是按比例随机抽样，未知 confidence 会保守地进入 LLM。
低 confidence item 的请求会附带相邻高 confidence 原文作为只读上下文，模型只返回目标
item；这样可以判断跨项断行，同时不把上下文重新计入 LLM 请求。该策略版本也纳入
cleanup checkpoint fingerprint，升级后不会错误复用旧语义结果。

## 进度语义

runtime state 现在保存 `stage_progress`，例如：

```text
当前阶段 9 / 84 批次 · 处理中 #10 #11 #12 #13
当前阶段 42 / 318 页
```

UI 继续使用原有视觉语言，但 banner / drawer 不再把这种阶段内部进度伪装成
“0 / 11 步骤”。只在已有实际完成数量时显示进度；没有足够样本就不显示 ETA。

## Benchmark

脚本使用确定性本地 fixture 和固定延迟 fake LLM，不产生真实 API 费用：

```bash
python3 scripts/pdf_ingestion_benchmark.py \
  --out tmp/pdf-ingestion-benchmark
```

它生成并测量：

1. text-layer PDF；
2. 20-page scanned PDF；
3. 100+ page scanned PDF（默认 120 页）。

每个 fixture 都有 `serial`（cleanup concurrency=1、confidence gate 不提供
confidence）和 `optimized`（OCR bounded workers + cleanup concurrency=4 + 实际
OCR confidence gate）两组；另有 forced-uncertain probe 专门隔离 LLM 网络等待的
并发收益。完整 JSON 和各 stage 明细写到 `benchmark.json`；两组还会比较
`segment_sha256`，并检查句级单元无重复、顺序和文本完全一致。

指标包括 total wall time、OCR pages/s、LLM cleanup wall time、fake API request
数、bypass ratio、峰值 RSS、可用时的平均 CPU，以及 OCR runtime device/provider。
CPU 指标在没有 `psutil` 时标记为 unavailable；GPU 利用率不对 Tesseract CPU
路径伪造，结果为 unavailable / null。

本机 2026-09-21 实跑（固定 fake LLM 延迟 20 ms；serial 是同一版本代码的
`parallelism=1` 对照，不是估算）摘要：

| fixture | 模式 | 总耗时 | OCR pages/s | cleanup wall | API requests | bypass | 峰值 RSS | 平均 CPU |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| scanned 20p | serial | 16.77 s | 1.22 | 0.28 s | 10 | 0% | 316 MB | 72% |
| scanned 20p | optimized | 9.80 s | 2.06 | ~0 s | 0 | 100% | 351 MB | 126% |
| scanned 120p | serial | 103.09 s | 1.19 | 1.76 s | 60 | 0% | 486 MB | 68% |
| scanned 120p | optimized | 55.12 s | 2.18 | ~0 s | 0 | 100% | 527 MB | 130% |

强制所有 item 进入 LLM 的隔离 probe 为：20p `0.423 s → 0.101 s`，120p
`1.830 s → 0.509 s`；请求数不变，说明 LLM 墙钟收益来自 bounded concurrency，
不是把请求偷偷删掉。该 fixture 的 OCR confidence 均高于 88，因此 optimized
 主跑的 0 requests / 100% bypass 是 gate 的可解释结果，不代表所有真实扫描件都会
 绕过 LLM；低 confidence / artifact 会进入 cleanup，已有单测覆盖。

benchmark 同时验证了 serial / optimized 的提取文本 digest 和 cleanup 输出 digest
一致、结构化 OCR page order 覆盖全部页且无重复 segment；20p 和 120p 两组 invariant
均为 true。OCR 内容里的页码可能被 Tesseract 误识别，这与页面执行顺序是两个指标，
因此页序检查使用 worker 的结构化 page order，页码文本仍保留在输出供质量审计。

完整原始输出在 `tmp/pdf-ingestion-benchmark/benchmark.json`；峰值 RSS 是 benchmark
进程 high-water mark，平均 CPU 统计父进程及 Tesseract 子进程，GPU 为
`device=cpu / execution_provider=native_cpu / gpu_name=null`。

## 未改变的边界与剩余瓶颈

* OCR 当前仍是 Tesseract CPU；如果真实测试中 OCR 成为主瓶颈，下一步应单独引入
  可验证的 GPU OCR backend，并记录其真实 execution provider，不能仅把配置项改成
  `cuda`。
* PyMuPDF layout recovery 仍是同步的；它通常是本地低耗时阶段，只有
  `performance.json` 显示它占比异常时才值得拆 worker。
* cleanup 并发提高吞吐会增加 provider 同时连接数；生产部署应按服务商限额设置
  concurrency / request interval，而不是无限 `gather`。
* 目前性能文件描述一次 pipeline run；恢复任务会生成新的 run_id，但 OCR / cleanup
  checkpoint 仍复用，因此恢复不会重复 OCR 已完成页或重发已成功 batch。
