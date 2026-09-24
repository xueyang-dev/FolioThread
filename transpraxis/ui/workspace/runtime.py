"""Lightweight isolated runtime status polling fragment.

Guarantees:
1. Polling (run_every) is isolated strictly to the runtime status bar fragment.
2. The CAT table, Inspector, and PDF viewer DO NOT re-evaluate every 2 seconds.
3. Polling only activates when the job runtime status is active (running, queued, etc.).
4. Status changes to terminal state trigger a single full-page rerun.
"""
from __future__ import annotations

from html import escape
import re
from typing import Any, Dict, Optional
import streamlit as st

import core
from transpraxis import profiler

_RUNTIME_DRAWER_KEY = "workspace_runtime_drawer_job"


@st.fragment(run_every="2s")
def render_runtime_strip_fragment(
    job_id: str,
    state: Optional[Dict[str, Any]] = None,
    view: Optional[Dict[str, Any]] = None,
) -> bool:
    """Compact running status rendered in an isolated 2-second polling fragment."""
    with profiler.span("runtime_fragment", job_id=job_id):
        view = core.read_runtime_view(job_id) if view is None else view
        status = view.get("status") or view.get("runtime_status") or "idle"
        if status in {"idle", "completed"}:
            return False

        runtime = view.get("runtime") or {}
        label = view.get("status_label") or view.get("headline_status") or status
        tone = ("danger" if status in {"failed", "interrupted"} else
                "warning" if status in {"stalled", "cancelling", "waiting_manual"} else
                "active")

        # Format progress and pipeline details
        pipeline_label, completed, total = _runtime_pipeline_label(view)
        pipeline_html = f'<span class="tp-banner-runtime-pipeline-label">{escape(pipeline_label)}</span>'
        if total:
            progress_pct = round(min(1.0, completed / total) * 100)
            pipeline_html += (
                f'<span class="tp-banner-runtime-bar" role="img" '
                f'aria-label="流程进度 {escape(pipeline_label)}">'
                f'<i style="width:{progress_pct}%"></i></span>')

        started_at = runtime.get("started_at") or runtime.get("operation_started_at")
        last_update = runtime.get("last_progress_at") or runtime.get("last_heartbeat_at")
        stage = _runtime_stage_label(view)
        action = _runtime_action_label(view, status)

        st.markdown(
            f'<div class="tp-banner-runtime is-{tone}" role="status" aria-live="polite">'
            f'<div class="tp-banner-runtime-main">'
            f'<div class="tp-banner-runtime-state is-{tone}"><i></i>{escape(label)}</div>'
            f'<strong class="tp-banner-runtime-headline">{escape(stage)}</strong>'
            f'<span class="tp-banner-runtime-detail">{escape(action)}</span>'
            '</div>'
            f'<div class="tp-banner-runtime-pipeline"><span>流程进度</span>{pipeline_html}</div>'
            f'<div class="tp-banner-runtime-meta"><span>已运行 {_runtime_duration(_runtime_age(started_at) or 0)}</span>'
            f'<span>最近更新 {_runtime_clock(last_update)}</span></div>'
            '</div>', unsafe_allow_html=True)

        with st.container(key=f"workspace_runtime_actions_{job_id}"):
            action_col, detail_col = st.columns([1.15, 2.85], gap="small")
            with action_col:
                if status in {"resume_requested", "queued", "starting"}:
                    st.button("正在恢复…", key=f"runtime_resuming_{job_id}",
                              disabled=True, width="stretch")
                elif status == "cancelling":
                    st.button("正在取消…", key=f"runtime_cancelling_{job_id}",
                              disabled=True, width="stretch")
                elif status in {"running", "waiting_external"}:
                    if st.button("取消任务", key=f"runtime_cancel_{job_id}",
                                 width="stretch"):
                        core.request_job_cancel(job_id)
                        st.rerun()
                elif status in {"interrupted", "idle_incomplete", "cancelled"}:
                    if st.button("继续处理", type="primary",
                                 key=f"runtime_resume_{job_id}", width="stretch"):
                        core.resume_job(job_id)
                        st.rerun()
                elif status == "stalled" and core.is_job_worker_alive(job_id):
                    if st.button("放弃当前运行", type="primary",
                                 key=f"runtime_abandon_{job_id}", width="stretch"):
                        core.request_job_cancel(job_id)
                        st.rerun()
                elif status in {"failed", "stalled"}:
                    if st.button("重试当前步骤", type="primary",
                                 key=f"runtime_retry_{job_id}", width="stretch"):
                        core.retry_job_step(job_id)
                        core.resume_job(job_id)
                        st.rerun()

            with detail_col:
                drawer_open = st.session_state.get(_RUNTIME_DRAWER_KEY) == job_id
                if st.button("运行详情 ›" if not drawer_open else "运行详情 · 已打开",
                             key=f"runtime_details_{job_id}", width="stretch"):
                    st.session_state[_RUNTIME_DRAWER_KEY] = job_id
                    drawer_open = True
                if drawer_open:
                    _runtime_drawer_dialog(job_id)

        return True


def _runtime_pipeline_label(view: Dict[str, Any]) -> tuple[str, int, int]:
    stage = view.get("stage_label") or view.get("pipeline_stage") or ""
    completed = int(view.get("progress_done") or 0)
    total = int(view.get("progress_total") or 0)
    if total > 0:
        return f"{stage} ({completed}/{total})", completed, total
    return str(stage or "准备中"), completed, total


def _runtime_stage_label(view: Dict[str, Any]) -> str:
    return str(view.get("stage_label") or view.get("operation_label") or "正在执行")


def _runtime_action_label(view: Dict[str, Any], status: str) -> str:
    if status == "running":
        return str(view.get("operation_detail") or "模型正在生成翻译")
    if status == "waiting_external":
        return "等待 API 响应"
    if status == "failed":
        return "步骤遇到错误，可重试"
    return str(view.get("detail") or "")


def _runtime_age(timestamp: Any) -> float:
    if not timestamp:
        return 0.0
    import datetime
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        if isinstance(timestamp, str):
            dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return max(0.0, (now - dt).total_seconds())
    except Exception:
        pass
    return 0.0


def _runtime_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}秒"
    m = s // 60
    return f"{m}分{s % 60}秒"


def _runtime_clock(timestamp: Any) -> str:
    if not timestamp:
        return "刚刚"
    return str(timestamp).replace("T", " ")[:19]


@st.dialog("任务运行详情", width="large")
def _runtime_drawer_dialog(job_id: str) -> None:
    st.caption(f"任务 ID: {job_id}")
    runtime = core.load_runtime_state(job_id) or {}
    st.json(runtime)
    if st.button("关闭", key=f"close_runtime_drawer_{job_id}"):
        st.session_state.pop(_RUNTIME_DRAWER_KEY, None)
        st.rerun()
