"""LLM-assisted OCR source cleanup with a strict, auditable contract.

The PDF ingester owns layout extraction.  This module only repairs the text
that extraction produced: obvious OCR substitutions, broken line joins, and
paragraph boundaries that are artifacts of the PDF text layer.  Every input
item must be returned exactly once, so the model cannot silently omit or add
source material.
"""
from __future__ import annotations

import hashlib
import json
import queue
import re
import threading
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple

from .textual import has_textual_content


MAX_BATCH_CHARS = 6200
MAX_BATCH_ITEMS = 32
DEFAULT_PARALLELISM = 4
DEFAULT_CONFIDENCE_THRESHOLD = 88.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0
CHECKPOINT_VERSION = 1
CONTEXT_WINDOW_VERSION = 1

SYSTEM_PROMPT = """你是扫描版 PDF 原文的 OCR 纠错与排版整理器。
你的工作对象是 OCR/文本层的原文，不是翻译。只做有证据的最小修复：
1. 修正常见 OCR 错字、混淆字符、乱码和明显的标点识别错误；
2. 把 PDF 版面造成的错误换行拼回自然句子；英文行末连字符只有在确实是断词时才去掉；
3. 判断相邻输入项是否属于同一段或标题，并用 break_after 表示段落边界。

不要翻译、改写、摘要、润色、补写原文没有的信息，也不要删除任何内容。
每个输入 index 必须原样出现一次，顺序不能改变。通常只修改明显错误的字符；不确定时保留原文。
必须只返回 JSON，不要 Markdown 或解释，格式为：
{"segments":[{"index":0,"text":"修复后的原文","break_after":false}]}
其中 break_after=true 表示该项后开始新段落；如果当前请求的最后一项显然还在句子中，
可以返回 false，它会与下一批的第一项继续合并。整个文档的最后一项必须为 true。
"""


def _normalise_text(value: Any) -> str:
    """Collapse physical line breaks while retaining meaningful spacing."""
    text = str(value or "").replace("\u00a0", " ")
    text = re.sub(r"[\t\r\n]+", " ", text)
    return re.sub(r" {2,}", " ", text).strip()


def _is_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value or "")


def _join(left: str, right: str) -> str:
    left, right = _normalise_text(left), _normalise_text(right)
    if not left:
        return right
    if not right:
        return left
    if left.endswith(("-", "‐", "‑")) and right[:1].islower():
        return left[:-1] + right
    if ((_is_cjk(left[-1:]) and _is_cjk(right[:1]))
            or right.startswith(tuple(",.!?;:%)]}»”’。，！？；：％）】」』"))):
        return left + right
    return f"{left} {right}"


def _is_sentence_terminal(text: str) -> bool:
    value = _normalise_text(text)
    if not value:
        return False
    value = re.sub(r"[\]\)}」』”’]+$", "", value).rstrip()
    return value[-1:] in set('.!?"”’…:;)')


def _schema(expected: int) -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "foliothread_source_cleanup",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "segments": {
                        "type": "array",
                        "minItems": expected,
                        "maxItems": expected,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "index": {"type": "integer", "minimum": 0},
                                "text": {"type": "string", "minLength": 1},
                                "break_after": {"type": "boolean"},
                            },
                            "required": ["index", "text", "break_after"],
                        },
                    },
                },
                "required": ["segments"],
            },
        },
    }


def _decode(response: Any, expected: int) -> List[Dict[str, Any]]:
    if not isinstance(response, str) or not response.strip():
        raise ValueError("原文纠错模型返回为空")
    raw = response.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        # A few compatible endpoints prepend a short sentence.  Recover only
        # a JSON object, never arbitrary plain text.
        start = raw.find("{")
        if start < 0:
            raise ValueError("原文纠错响应不是 JSON") from exc
        try:
            value = json.JSONDecoder().raw_decode(raw[start:])[0]
        except (TypeError, ValueError) as nested:
            raise ValueError("原文纠错响应不是 JSON") from nested
    rows = value.get("segments") if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) != expected:
        raise ValueError(f"原文纠错响应段数错误：期望 {expected} 项")
    indexes: List[int] = []
    parsed: List[Dict[str, Any]] = []
    for row in rows:
        if (not isinstance(row, dict)
                or isinstance(row.get("index"), bool)
                or not isinstance(row.get("index"), int)):
            raise ValueError("原文纠错响应缺少连续 index")
        if not isinstance(row.get("text"), str):
            raise ValueError("原文纠错响应缺少文本字段")
        # Some compatible relays emit an empty string for a punctuation-only
        # OCR item even though the schema asks for a non-empty string.  Keep
        # the row and let ``_safe_candidate`` fall back to the extracted text;
        # rejecting the whole batch would discard valid corrections for every
        # neighbouring item.
        text = _normalise_text(row.get("text"))
        break_after = row.get("break_after")
        if not isinstance(break_after, bool):
            raise ValueError("原文纠错响应缺少 break_after")
        indexes.append(row["index"])
        parsed.append({"index": row["index"], "text": text,
                       "break_after": break_after})
    if indexes != list(range(expected)):
        raise ValueError("原文纠错响应 index 不连续")
    return parsed


def _safe_candidate(before: str, after: str) -> str:
    """Reject clearly destructive model rewrites while accepting OCR fixes."""
    before, after = _normalise_text(before), _normalise_text(after)
    if not after:
        return before
    if has_textual_content(before) and not has_textual_content(after):
        return before
    # A correction should stay close to the OCR text.  This catches a model
    # that followed the translation instruction accidentally or hallucinated a
    # paragraph while still allowing long-word and punctuation repairs.
    if len(before) >= 24:
        lower = max(8, int(len(before) * 0.35))
        upper = max(160, int(len(before) * 3.0))
        if len(after) < lower or len(after) > upper:
            return before
    source_words = re.findall(r"[A-Za-z]{2,}", before)
    target_words = {word.casefold() for word in re.findall(r"[A-Za-z]{2,}", after)}
    if len(source_words) >= 4:
        overlap = sum(word.casefold() in target_words for word in source_words)
        similarity = SequenceMatcher(None, before.casefold(), after.casefold()).ratio()
        if overlap / len(source_words) < 0.25 and similarity < 0.2:
            return before
    return after


def _call_model(
    call_llm: Callable[..., Any], provider: str, api_key: str, model: str,
    user_prompt: str, expected: int,
) -> str:
    kwargs = {"temperature": 0.0, "response_format": _schema(expected)}
    try:
        return call_llm(provider, api_key, model, SYSTEM_PROMPT, user_prompt, **kwargs)
    except TypeError:
        # Test doubles and older provider adapters may not expose
        # response_format yet.  The response is still validated strictly.
        return call_llm(provider, api_key, model, SYSTEM_PROMPT, user_prompt,
                        temperature=0.0)


def _is_cancelled(cancel_check: Callable[[], bool] | None) -> bool:
    if cancel_check is None:
        return False
    return bool(cancel_check())


def _retryable(exc: BaseException) -> bool:
    """Retry transport/provider throttling, not malformed model output."""
    if "任务已请求取消" in str(exc):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    try:
        import core

        status = core.provider_error_status(exc).get("status")
        return status in {"rate_limited", "network_error", "provider_unavailable"}
    except Exception:  # pragma: no cover - cleanup must work without core
        text = str(exc).lower()
        return any(marker in text for marker in ("429", "rate limit", "timeout", "temporarily"))


class _RequestGate:
    """A process-local request gate that prevents retry storms."""

    def __init__(self, interval_s: float = 0.0) -> None:
        self.interval_s = max(0.0, float(interval_s or 0.0))
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self, cancel_check: Callable[[], bool] | None = None) -> float:
        waited = 0.0
        while True:
            if _is_cancelled(cancel_check):
                raise RuntimeError("任务已请求取消")
            with self._lock:
                now = time.monotonic()
                delay = max(0.0, self._next_allowed - now)
                if delay <= 0.0:
                    self._next_allowed = now + self.interval_s
                    return waited
            sleep_for = min(delay, 0.2)
            time.sleep(sleep_for)
            waited += sleep_for


def _atomic_json_write(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_cleanup_checkpoint(path: Path | None, fingerprint: str) -> Dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    if not isinstance(value, dict) or value.get("fingerprint") != fingerprint:
        return {}
    if value.get("version") != CHECKPOINT_VERSION:
        return {}
    return value


def _deterministic_prepare(items: Sequence[str]) -> Tuple[List[str], List[bool], List[Dict[str, Any]], List[str]]:
    """Normalize OCR text and mark only obvious joins as safe deterministic work."""
    cleaned = []
    changed = []
    for index, raw in enumerate(items):
        before = str(raw or "")
        after = _normalise_text(before)
        cleaned.append(after)
        if after != before:
            changed.append({"index": index, "before": before, "after": after,
                            "reason": "whitespace_normalization"})

    break_after = [True] * len(cleaned)
    deterministic_merges: List[Dict[str, Any]] = []
    for index in range(max(0, len(cleaned) - 1)):
        left, right = cleaned[index], cleaned[index + 1]
        if not left or not right:
            continue
        obvious_hyphen = left.endswith(("-", "‐", "‑")) and right[:1].islower()
        obvious_line_join = (
            len(left) < 180
            and not _is_sentence_terminal(left)
            and (right[:1].islower() or (_is_cjk(left[-1:]) and _is_cjk(right[:1])))
        )
        if obvious_hyphen or obvious_line_join:
            break_after[index] = False
            deterministic_merges.append({
                "input_indices": [index, index + 1],
                "reason": "hyphenation" if obvious_hyphen else "obvious_line_join",
            })
    return cleaned, break_after, deterministic_merges, changed


def _confidence_for(confidence_by_index: Any, index: int) -> float | None:
    if isinstance(confidence_by_index, dict):
        value = confidence_by_index.get(index, confidence_by_index.get(str(index)))
    elif isinstance(confidence_by_index, Sequence) and not isinstance(
        confidence_by_index, (str, bytes)
    ):
        value = confidence_by_index[index] if index < len(confidence_by_index) else None
    else:
        value = None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _uncertainty_reasons(text: str, confidence: float | None, threshold: float) -> List[str]:
    reasons: List[str] = []
    if confidence is None:
        reasons.append("missing_ocr_confidence")
    elif confidence < threshold:
        reasons.append("low_ocr_confidence")
    if "�" in text or "□" in text:
        reasons.append("replacement_character")
    if re.search(r"([!?.,:;])\1{2,}", text):
        reasons.append("repeated_punctuation")
    alpha_numeric = sum(1 for char in text if char.isalnum())
    if text and alpha_numeric / max(1, len(text)) < 0.28:
        reasons.append("low_text_density")
    return reasons


def _checkpoint_payload(
    fingerprint: str,
    batches: Sequence[Sequence[Tuple[int, str]]],
    results: Dict[int, Dict[str, Any]],
    *,
    status: str,
) -> Dict[str, Any]:
    return {
        "version": CHECKPOINT_VERSION,
        "fingerprint": fingerprint,
        "batch_count": len(batches),
        "selected_indices": [index for batch in batches for index, _ in batch],
        "status": status,
        "results": {str(index): value for index, value in sorted(results.items())
                     if value.get("status") == "completed"},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def cleanup_source_paragraphs(
    paragraphs: Sequence[str], provider: str, api_key: str, model: str,
    *, call_llm: Callable[..., Any], on_progress: Callable[[str], None] | None = None,
    max_batch_chars: int = MAX_BATCH_CHARS,
    max_batch_items: int = MAX_BATCH_ITEMS,
    parallelism: int = DEFAULT_PARALLELISM,
    confidence_by_index: Any = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    checkpoint_dir: str | Path | None = None,
    cancel_check: Callable[[], bool] | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    request_interval_seconds: float = 0.0,
    profiler: Any = None,
) -> Tuple[List[str], Dict[str, Any], List[str]]:
    """Repair OCR paragraphs and return ``(paragraphs, metadata, warnings)``.

    The input boundaries are preserved as indexed items in each request; the
    model may only change their text and mark joins.  A failed batch falls back
    to its deterministic input and never blocks the translation pipeline.
    """
    original = [_normalise_text(item) for item in (paragraphs or [])]
    if not original:
        if profiler is not None:
            for stage_name in ("deterministic_cleanup", "llm_cleanup"):
                profiler.skipped(stage_name, metadata={"reason": "empty_input"})
        return [], {"status": "skipped", "input_count": 0, "output_count": 0}, []

    deterministic_stage = None
    if profiler is not None:
        deterministic_stage = profiler.start_stage(
            "deterministic_cleanup", concurrency=1, item_count=len(original),
            metadata={"operations": ["whitespace_normalization", "obvious_line_join"]},
        )
    deterministic_items, break_after, deterministic_merges, changed = _deterministic_prepare(
        original
    )
    if deterministic_stage is not None:
        for index, before in enumerate(original):
            deterministic_stage.item(
                index, deterministic_stage.started_monotonic,
                metadata={"kind": "item", "changed": deterministic_items[index] != before},
            )
        deterministic_stage.finish(
            status="completed", deterministic_merge_count=len(deterministic_merges)
        )

    threshold = max(0.0, min(100.0, float(confidence_threshold or 0.0)))
    uncertainty: Dict[int, List[str]] = {}
    for index, text in enumerate(deterministic_items):
        reasons = _uncertainty_reasons(text, _confidence_for(confidence_by_index, index), threshold)
        if reasons:
            uncertainty[index] = reasons
    llm_indices = list(uncertainty)
    batches: List[List[Tuple[int, str]]] = []
    current: List[Tuple[int, str]] = []
    chars = 0
    for index in llm_indices:
        text = deterministic_items[index]
        size = len(text) + 24
        if current and (len(current) >= max_batch_items or chars + size > max_batch_chars):
            batches.append(current)
            current, chars = [], 0
        current.append((index, text))
        chars += size
    if current:
        batches.append(current)

    cleaned_items = list(deterministic_items)
    merges: List[Dict[str, Any]] = []
    warnings: List[str] = []
    failed_batches = 0
    retry_counts: Dict[int, int] = {}
    api_latencies: Dict[int, float] = {}
    queue_waits: Dict[int, float] = {}
    checkpoint_path = None
    if checkpoint_dir:
        checkpoint_path = Path(checkpoint_dir) / "source_cleanup_checkpoint.json"
    fingerprint = hashlib.sha256(json.dumps({
        "items": deterministic_items,
        "llm_indices": llm_indices,
        "context_window_version": CONTEXT_WINDOW_VERSION,
        "provider": str(provider or ""),
        "model": str(model or ""),
        "max_batch_chars": int(max_batch_chars),
        "max_batch_items": int(max_batch_items),
        "confidence_threshold": threshold,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    checkpoint = _load_cleanup_checkpoint(checkpoint_path, fingerprint)
    result_map: Dict[int, Dict[str, Any]] = {}
    for key, value in (checkpoint.get("results") or {}).items():
        try:
            batch_index = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and isinstance(value.get("rows"), list):
            result_map[batch_index] = {**value, "status": "completed"}
            retry_counts[batch_index] = int(value.get("retry_count") or 0)
            api_latencies[batch_index] = float(value.get("api_latency_s") or 0.0)
            queue_waits[batch_index] = float(value.get("queue_wait_s") or 0.0)
    checkpoint_lock = threading.RLock()

    def save_checkpoint(status: str = "running") -> None:
        if checkpoint_path is None:
            return
        with checkpoint_lock:
            try:
                _atomic_json_write(
                    checkpoint_path,
                    _checkpoint_payload(fingerprint, batches, result_map, status=status),
                )
            except OSError:
                pass

    def check_cancel() -> None:
        if _is_cancelled(cancel_check):
            raise RuntimeError("任务已请求取消")

    request_gate = _RequestGate(request_interval_seconds)

    def call_with_retry(prompt: str, expected: int) -> Tuple[List[Dict[str, Any]], int, float, float]:
        retry_count = 0
        total_api_latency = 0.0
        total_gate_wait = 0.0
        while True:
            check_cancel()
            total_gate_wait += request_gate.wait(cancel_check)
            started = time.perf_counter()
            try:
                response = _call_model(call_llm, provider, api_key, model, prompt, expected)
                total_api_latency += time.perf_counter() - started
                check_cancel()
                return _decode(response, expected), retry_count, total_api_latency, total_gate_wait
            except Exception as exc:  # noqa: BLE001 - classify before deciding to retry
                total_api_latency += time.perf_counter() - started
                if "任务已请求取消" in str(exc):
                    raise
                if not _retryable(exc) or retry_count >= max(0, int(max_retries or 0)):
                    # Preserve the attempt accounting even when the final
                    # provider/protocol error falls back to the source text.
                    # The cleanup caller must not lose evidence merely because
                    # the last retry raised instead of returning a row set.
                    setattr(exc, "_cleanup_retry_count", retry_count)
                    setattr(exc, "_cleanup_api_latency_s", total_api_latency)
                    setattr(exc, "_cleanup_gate_wait_s", total_gate_wait)
                    raise
                retry_count += 1
                delay = max(0.0, float(retry_backoff_seconds or 0.0)) * (2 ** (retry_count - 1))
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline:
                    check_cancel()
                    time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))

    def run_batch(batch_index: int, batch: List[Tuple[int, str]], queue_wait_s: float):
        numbered = "\n".join(f"{local}. {text}" for local, (_, text) in enumerate(batch))
        target_indices = {index for index, _ in batch}
        context_rows = []
        context_seen = set()
        context_budget = max(
            0, min(1200, int(max_batch_chars) - len(numbered) - 256)
        )
        context_chars = 0
        for global_index, _ in batch:
            for neighbor_index in (global_index - 1, global_index + 1):
                if (neighbor_index < 0 or neighbor_index >= len(deterministic_items)
                        or neighbor_index in target_indices
                        or neighbor_index in context_seen):
                    continue
                neighbor_text = deterministic_items[neighbor_index]
                if not neighbor_text:
                    continue
                remaining = context_budget - context_chars
                if remaining <= 0:
                    break
                clipped = neighbor_text[:remaining]
                context_rows.append(f"上下文项 {neighbor_index}（只读）：{clipped}")
                context_seen.add(neighbor_index)
                context_chars += len(clipped)
            if context_chars >= context_budget:
                break
        context_section = ""
        if context_rows:
            context_section = (
                "以下相邻项只用于判断断行和段落边界，不要修改，也不要在 JSON 中返回：\n"
                + "\n".join(context_rows) + "\n\n"
            )
        prompt = (
            "下面是按 PDF 阅读顺序提取的目标原文项。请逐项纠错并标记段落边界；"
            "只能返回目标项，index 从 0 开始且必须完整返回。\n\n"
            + context_section + numbered
        )
        try:
            rows, retries, api_latency, gate_wait = call_with_retry(prompt, len(batch))
        except Exception as exc:  # noqa: BLE001 - cleanup is a non-blocking aid
            if "任务已请求取消" in str(exc):
                raise
            try:
                import core
                provider_status = core.provider_error_status(exc)
                detail = (provider_status["message"]
                          if provider_status["status"] != "unknown"
                          else str(exc))
            except Exception:  # pragma: no cover - defensive import fallback
                detail = str(exc)
            return {
                "status": "failed", "rows": None, "error": detail,
                "context_item_count": len(context_rows),
                "retry_count": int(getattr(exc, "_cleanup_retry_count", 0) or 0),
                "api_latency_s": float(getattr(exc, "_cleanup_api_latency_s", 0.0) or 0.0),
                "queue_wait_s": queue_wait_s + float(
                    getattr(exc, "_cleanup_gate_wait_s", 0.0) or 0.0),
            }
        return {
            "status": "completed", "rows": rows, "error": None,
            "context_item_count": len(context_rows),
            "retry_count": retries, "api_latency_s": api_latency,
            "queue_wait_s": queue_wait_s + gate_wait,
        }

    # Large books benefit from a small amount of parallelism: one slow relay
    # request should not serialize every independent cleanup batch.  Results
    # are still applied in document order, and each batch keeps the same strict
    # schema/fallback contract as the sequential path.
    workers = max(1, min(int(parallelism or DEFAULT_PARALLELISM), max(1, len(batches))))
    pending = [(index, batch) for index, batch in enumerate(batches)
               if index not in result_map]
    llm_stage = None
    if profiler is not None:
        if batches:
            llm_stage = profiler.start_stage(
                "llm_cleanup", concurrency=workers, batch_count=len(batches),
                item_count=len(llm_indices),
                metadata={"max_concurrency": workers, "cached_batches": len(result_map)},
            )
        else:
            profiler.skipped("llm_cleanup", metadata={"reason": "confidence_gate"})

    progress_lock = threading.RLock()
    active_batches: set[int] = set()
    finished_count = len(result_map)
    first_error: List[BaseException] = []
    stop_event = threading.Event()
    work_queue: queue.Queue = queue.Queue(maxsize=max(1, workers * 2))

    def emit_progress() -> None:
        if not on_progress:
            return
        with progress_lock:
            active = " ".join(f"#{index + 1}" for index in sorted(active_batches))
            suffix = f"；处理中 {active}" if active else ""
            message = (
                f"【阶段一】LLM 原文纠错与断行整理（批次 {finished_count}/{len(batches)}"
                f"{suffix}）…"
            )
        on_progress(message)

    def worker_loop() -> None:
        nonlocal finished_count
        while True:
            task = work_queue.get()
            try:
                if task is None:
                    return
                batch_index, batch, enqueued_at = task
                if stop_event.is_set():
                    continue
                started = time.perf_counter()
                queue_wait_s = max(0.0, started - enqueued_at)
                with progress_lock:
                    active_batches.add(batch_index)
                result = run_batch(batch_index, batch, queue_wait_s)
                result_map[batch_index] = result
                retry_counts[batch_index] = int(result.get("retry_count") or 0)
                api_latencies[batch_index] = float(result.get("api_latency_s") or 0.0)
                queue_waits[batch_index] = float(result.get("queue_wait_s") or 0.0)
                if result.get("status") == "completed":
                    save_checkpoint()
                with progress_lock:
                    active_batches.discard(batch_index)
                    finished_count += 1
                if profiler is not None and llm_stage is not None:
                    llm_stage.item(
                        f"batch-{batch_index + 1}", started,
                        queue_wait_s=result.get("queue_wait_s") or 0.0,
                        api_latency_s=result.get("api_latency_s") or 0.0,
                        retry_count=result.get("retry_count") or 0,
                        status="completed" if result.get("status") == "completed" else "failed",
                        metadata={"kind": "batch", "batch_index": batch_index + 1,
                                  "context_item_count": result.get("context_item_count", 0)},
                    )
                emit_progress()
            except BaseException as exc:  # noqa: BLE001 - propagate cancellation
                if not first_error:
                    first_error.append(exc)
                stop_event.set()
                with progress_lock:
                    active_batches.clear()
            finally:
                work_queue.task_done()

    threads = [threading.Thread(target=worker_loop, name=f"source-cleanup-{index}", daemon=True)
               for index in range(workers)]
    cancelled = False
    try:
        for thread in threads:
            thread.start()
        emit_progress()
        for batch_index, batch in pending:
            check_cancel()
            while not stop_event.is_set():
                try:
                    work_queue.put((batch_index, batch, time.perf_counter()), timeout=0.2)
                    break
                except queue.Full:
                    check_cancel()
            if stop_event.is_set():
                break
        save_checkpoint()
    except BaseException:
        cancelled = True
        stop_event.set()
        raise
    finally:
        stop_event.set() if first_error else None
        for _ in threads:
            while True:
                try:
                    work_queue.put(None, timeout=0.2)
                    break
                except queue.Full:
                    if not any(thread.is_alive() for thread in threads):
                        break
        for thread in threads:
            thread.join(timeout=10)
        if first_error and any("任务已请求取消" in str(error) for error in first_error):
            cancelled = True
        save_checkpoint("cancelled" if cancelled else "completed")
        if llm_stage is not None:
            stage_status = ("cancelled" if cancelled else
                            "failed" if first_error else "completed")
            llm_stage.finish(
                status=stage_status,
                failed_batches=sum(
                    1 for value in result_map.values() if value.get("status") != "completed"
                ),
            )
        if first_error:
            raise first_error[0]

    for batch_index, batch in enumerate(batches):
        result = result_map.get(batch_index) or {}
        rows, error = result.get("rows"), result.get("error")
        if error is not None:
            failed_batches += 1
            warnings.append(
                f"原文纠错批次 {batch_index + 1}/{len(batches)} 失败，已保留提取文本：{error[:180]}"
            )
            continue
        for row, (global_index, before) in zip(rows, batch):
            after = _safe_candidate(before, row["text"])
            cleaned_items[global_index] = after
            break_after[global_index] = bool(row["break_after"])
            if after != before:
                changed.append({"index": global_index, "before": before, "after": after})

    output: List[str] = []
    current_indices: List[int] = []
    current_text = ""
    for index, text in enumerate(cleaned_items):
        current_text = _join(current_text, text)
        current_indices.append(index)
        if break_after[index] or index == len(cleaned_items) - 1:
            # Preserve headings, separators, page marks and other non-letter
            # items too.  They are part of the extracted reading order even
            # when translation later treats them as pass-through content.
            if current_text:
                output.append(current_text)
                if len(current_indices) > 1:
                    merges.append({"input_indices": list(current_indices),
                                   "text": current_text})
            current_text, current_indices = "", []
    if not output:
        output = list(original)
    status = "completed" if not failed_batches else "partial"
    metadata = {
        "status": status,
        "input_count": len(original),
        "output_count": len(output),
        "batch_count": len(batches),
        "failed_batches": failed_batches,
        "changed_segments": changed,
        "paragraph_merges": merges,
        "deterministic_merges": deterministic_merges,
        "llm_input_count": len(llm_indices),
        "llm_bypassed_count": len(original) - len(llm_indices),
        "llm_bypass_ratio": round((len(original) - len(llm_indices)) / len(original), 6),
        "confidence_threshold": threshold,
        "uncertainty_counts": {
            reason: sum(reason in reasons for reasons in uncertainty.values())
            for reason in sorted({reason for reasons in uncertainty.values() for reason in reasons})
        },
        "parallelism": workers,
        "max_retries": max(0, int(max_retries or 0)),
        "retry_count": sum(retry_counts.values()),
        "api_latency_s": round(sum(api_latencies.values()), 6),
        "queue_wait_s": round(sum(queue_waits.values()), 6),
        "resumed_batches": len(checkpoint.get("results") or {}),
        "checkpoint_file": str(checkpoint_path) if checkpoint_path else "",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    return output, metadata, warnings
