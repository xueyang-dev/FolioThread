"""Authoritative state storage repository and derived summary read-model.

Architectural guarantees:
1. `state.json` remains the single authoritative ground truth.
2. `load_job_state` employs a file signature cache (mtime_ns, size) to eliminate
   expensive repeated disk parsing and migration while auto-invalidating on atomic replace.
3. Cache returns deep-copied snapshots to prevent caller mutations from polluting the cache.
4. `summary.json` is a lightweight derived read model written ONLY during mutation paths.
5. The read path has strictly NO write side-effects: missing summaries fall back to
   loading state without creating or touching files on disk.
"""
from __future__ import annotations

import collections
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from transpraxis import profiler

# Cache mapping (job_id, mtime_ns, file_size) -> normalized state dict
_STATE_CACHE: collections.OrderedDict[Tuple[str, int, int], Dict[str, Any]] = collections.OrderedDict()
_STATE_CACHE_MAX_ENTRIES = 256

_STATS = {
    "cache_hits": 0,
    "cache_misses": 0,
    "disk_reads": 0,
}


def get_cache_stats() -> Dict[str, int]:
    return dict(_STATS)


def reset_cache_stats() -> None:
    _STATS["cache_hits"] = 0
    _STATS["cache_misses"] = 0
    _STATS["disk_reads"] = 0


def invalidate_cache(job_id: Optional[str] = None) -> None:
    """Clear cached state snapshots for a specific job or all jobs."""
    if job_id is None:
        _STATE_CACHE.clear()
        return
    job_str = str(job_id)
    keys_to_remove = [k for k in _STATE_CACHE if k[0] == job_str]
    for k in keys_to_remove:
        _STATE_CACHE.pop(k, None)


def _get_output_dir(output_dir: Optional[Path] = None) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    import core
    return Path(core.OUTPUT_DIR)


def get_job_state_path(job_id: str, output_dir: Optional[Path] = None) -> Path:
    return _get_output_dir(output_dir) / str(job_id) / "state.json"


def get_job_summary_path(job_id: str, output_dir: Optional[Path] = None) -> Path:
    return _get_output_dir(output_dir) / str(job_id) / "summary.json"


def load_job_state_cached(
    job_id: str,
    output_dir: Optional[Path] = None,
    force_reload: bool = False,
) -> Optional[Dict[str, Any]]:
    """Load job state with safe file signature caching and caller isolation.

    Returns a deepcopy of the normalized state to guarantee caller mutations
    cannot corrupt the cached internal representation.
    """
    p = get_job_state_path(job_id, output_dir=output_dir)
    try:
        stat = p.stat()
    except OSError:
        return None

    signature = (str(job_id), stat.st_mtime_ns, stat.st_size)

    if not force_reload and signature in _STATE_CACHE:
        _STATS["cache_hits"] += 1
        profiler.count("load_job_state_cache_hit")
        # Move to end for LRU
        _STATE_CACHE.move_to_end(signature)
        return copy.deepcopy(_STATE_CACHE[signature])

    _STATS["cache_misses"] += 1
    _STATS["disk_reads"] += 1
    profiler.count("load_job_state_cache_miss")
    profiler.count("load_job_state_disk_read")

    with profiler.span("load_job_state_disk", job_id=job_id):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

        import core
        from transpraxis import delivery as _delivery
        from transpraxis import state_migration as _state_migration
        from transpraxis import translation_evidence as _translation_evidence

        state = _delivery.normalize_state_findings(_state_migration.migrate_state(raw))
        _translation_evidence.reconcile_runtime_review_truth(state)
        state = core._reconcile_final_delivery_snapshot(job_id, state)

        # Store in LRU cache
        if len(_STATE_CACHE) >= _STATE_CACHE_MAX_ENTRIES:
            _STATE_CACHE.popitem(last=False)
        _STATE_CACHE[signature] = state

        return copy.deepcopy(state)


def save_job_state_atomic(
    job_id: str,
    state: Dict[str, Any],
    output_dir: Optional[Path] = None,
) -> None:
    """Atomically save state.json and update the derived summary.json."""
    import core
    from transpraxis import delivery as _delivery
    from transpraxis import translation_evidence as _translation_evidence

    _translation_evidence.reconcile_runtime_review_truth(state)
    _delivery.normalize_state_findings(state)
    core._reconcile_final_delivery_snapshot(job_id, state)

    d = _get_output_dir(output_dir) / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    dest = d / "state.json"
    tmp.replace(dest)

    # Invalidate cache for this job_id so next read picks up the new file stat
    invalidate_cache(job_id)

    # Derived read-model: save summary.json during this write path
    try:
        save_job_summary(job_id, state, output_dir=output_dir)
    except Exception:
        pass


def build_job_summary(job_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a lightweight read-model dictionary from a full job state."""
    state = state if isinstance(state, dict) else {}
    pairs = state.get("pairs") or []
    paras = state.get("paras") or []
    seg_count = len(pairs) if pairs else len(paras)
    delivery = state.get("delivery") or {}
    findings = delivery.get("findings") or []
    runtime = state.get("runtime") or {}
    progress_info = state.get("progress") or ""

    runtime_status = runtime.get("status")
    if not runtime_status or runtime_status == "idle":
        import core
        runtime_status = "idle" if core._runtime_business_complete(state) else "idle_incomplete"

    return {
        "job_id": str(job_id),
        "filename": str(state.get("filename") or ""),
        "project_id": state.get("project_id"),
        "target_lang": state.get("target_lang") or "zh",
        "stage": state.get("academic_stage") or state.get("stage") or "translation",
        "updated_at": state.get("updated_at") or state.get("created_at") or "",
        "created_at": state.get("created_at") or "",
        "runtime_status": runtime_status,
        "progress": progress_info,
        "segment_count": seg_count,
        "review_count": len(findings),
    }


def save_job_summary(
    job_id: str,
    state: Dict[str, Any],
    output_dir: Optional[Path] = None,
) -> None:
    """Atomically write summary.json for a job during a mutation path."""
    d = _get_output_dir(output_dir) / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    summary = build_job_summary(job_id, state)
    tmp = d / "summary.json.tmp"
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(d / "summary.json")


def load_job_summary(
    job_id: str,
    output_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Read summary.json if available; returns None if missing."""
    p = get_job_summary_path(job_id, output_dir=output_dir)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_job_summaries(output_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List lightweight summaries for all jobs.

    STRICT INVARIANT: This is a read path. If summary.json is missing for a job,
    it falls back to reading state.json in-memory without creating any files on disk.
    """
    out = _get_output_dir(output_dir)
    summaries: List[Dict[str, Any]] = []
    if not out.is_dir():
        return summaries

    for d in sorted(out.iterdir()):
        if not d.is_dir():
            continue
        job_id = d.name
        summary_path = d / "summary.json"
        if summary_path.is_file():
            try:
                data = json.loads(summary_path.read_text(encoding="utf-8"))
                summaries.append(data)
                profiler.count("summary_cache_hit")
                continue
            except Exception:
                pass

        # Fallback to state.json if summary.json missing (DO NOT WRITE TO DISK)
        state_path = d / "state.json"
        if state_path.is_file():
            state = load_job_state_cached(job_id, output_dir=out)
            if state is not None:
                summary = build_job_summary(job_id, state)
                summaries.append(summary)
                profiler.count("summary_fallback_miss")

    return summaries


def read_runtime_view(
    job_id: str,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Lightweight read-only view of a job's runtime status.

    Reads only lightweight artifacts (`runtime.json` and optionally `summary.json`),
    avoiding the overhead of loading, migrating, and reconciling full `state.json`.
    Includes `state_revision` (mtime_ns) to allow caller fragments to detect
    business state updates.
    """
    import core
    runtime = core.load_runtime_state(job_id) or {}
    summary = load_job_summary(job_id, output_dir=output_dir)

    state_p = get_job_state_path(job_id, output_dir=output_dir)
    try:
        state_mtime_ns = state_p.stat().st_mtime_ns
    except OSError:
        state_mtime_ns = 0

    status = runtime.get("status")
    if not status or status == "idle":
        if summary and summary.get("runtime_status"):
            status = summary.get("runtime_status")
        else:
            state = load_job_state_cached(job_id, output_dir=output_dir)
            if state:
                status = "idle" if core._runtime_business_complete(state) else "idle_incomplete"
            else:
                status = "idle"

    labels = {
        "resume_requested": "正在恢复任务",
        "queued": "正在恢复任务",
        "starting": "正在恢复任务",
        "running": "正在运行",
        "waiting_external": "正在运行",
        "stalled": "暂无运行信号",
        "interrupted": "上次运行已中断",
        "failed": "当前步骤失败",
        "cancelling": "正在取消",
        "cancelled": "任务已取消",
        "completed": "已完成",
        "idle_incomplete": "未完成",
        "waiting_manual": "待术语确认",
        "idle": "空闲",
    }
    status_label = labels.get(status, status)
    stage_label = runtime.get("stage") or runtime.get("phase_label") or (
        summary.get("stage") if summary else "任务处理"
    )
    operation_label = runtime.get("operation_label") or runtime.get("operation") or "正在执行"

    completed = int(runtime.get("completed_units") or 0)
    total = int(runtime.get("total_units") or 0)
    if total == 0 and summary:
        total = int(summary.get("segment_count") or 0)

    events = runtime.get("events") or []

    return {
        "job_id": str(job_id),
        "status": status,
        "runtime_status": status,
        "status_label": status_label,
        "headline_status": status_label,
        "stage_label": stage_label,
        "pipeline_stage": stage_label,
        "operation_label": operation_label,
        "operation_detail": runtime.get("phase_label") or "",
        "detail": runtime.get("last_event") or runtime.get("error") or "",
        "progress_done": completed,
        "progress_total": total,
        "runtime": runtime,
        "state_revision": state_mtime_ns,
        "events": events,
    }
