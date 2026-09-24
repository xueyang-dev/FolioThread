"""CAT Translation Workspace and Grid component with isolated fragment re-rendering.

Optimizations:
1. Viewport pagination: `CAT_GRID_ROWS = 40` (drastic reduction from 400).
2. Action Menu: non-active rows render lightweight triggers; only the active row
   builds the full multi-action popover, reducing widget explosion by >95%.
3. Shared Fragment scope: CAT Grid and Inspector share ONE fragment boundary via
   `transpraxis.ui.workspace.translation.render_translation_workspace_fragment`.
4. Robust Draft preservation: drafts survive viewport scrolling and filter toggles.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import streamlit as st

import core
from transpraxis import profiler
from transpraxis import translation_planner as _planner

CAT_GRID_ROWS = 40
_CAT_BASELINE_PREFIX = "cat_baseline_"
_TRANSLATION_SEGMENT_EDITOR_KEY = "translation_segment_editor_target"
_TRANSLATION_EDITOR_SEED = "translation_editor_seed"
_NAV_PENDING_SCROLL = "pending_scroll_segment_id"
_NAV_PENDING_FOCUS = "pending_focus_segment_id"
_NAV_NOTICE = "workspace_nav_notice"


def cat_status_tone(status: str) -> str:
    """Map segment review status to a compact visual tone class."""
    return {
        "已审校": "is-reviewed",
        "已修改": "is-edited",
        "待审校": "is-pending",
        "待翻译": "is-pending",
    }.get(str(status or ""), "")


def render_translation_segment_actions(
    job_id: str,
    state: Dict[str, Any],
    index: int,
    pair: Dict[str, Any],
    *,
    is_active: bool = True,
    segment_id_fn: Optional[Callable[..., str]] = None,
    navigate_fn: Optional[Callable[..., Any]] = None,
    structure_edit_blocked_fn: Optional[Callable[..., Tuple[bool, str]]] = None,
    flush_draft_fn: Optional[Callable[..., Any]] = None,
    open_editor_fn: Optional[Callable[..., Any]] = None,
    purge_edit_state_fn: Optional[Callable[..., Any]] = None,
    structure_flash_fn: Optional[Callable[..., Any]] = None,
    workspace_flash_fn: Optional[Callable[..., Any]] = None,
    seed_editor_fn: Optional[Callable[..., Any]] = None,
    commit_row_fn: Optional[Callable[..., Any]] = None,
    retranslate_fn: Optional[Callable[..., Any]] = None,
    draft_for_fn: Optional[Callable[..., Any]] = None,
    drop_draft_fn: Optional[Callable[..., Any]] = None,
    reset_editor_fn: Optional[Callable[..., Any]] = None,
    api_ready: bool = False,
) -> None:
    """Render row actions.

    Optimized: Non-active rows only render a lightweight select button;
    only the active/focused row builds the full 8-button popover menu.
    """
    editor_spec = st.session_state.get(_TRANSLATION_SEGMENT_EDITOR_KEY) or {}
    if str(editor_spec.get("job_id") or "") == str(job_id):
        return

    pair = pair if isinstance(pair, dict) else {}
    pairs = state.get("pairs") or []
    segment_id = segment_id_fn(job_id, index, pair) if segment_id_fn else (
        core.segment_uid(pair) or str(pair.get("segment_id") or index)
    )

    if not is_active:
        # Lightweight affordance: 0 popovers and 0 hidden child buttons
        with st.container(key=f"cat_action_col_{job_id}_{index}"):
            if st.button("⋯", key=f"cat_actions_sel_{job_id}_{index}",
                         help=f"第 {index + 1} 段 · 点击展开操作菜单",
                         width="stretch"):
                if navigate_fn:
                    navigate_fn(job_id, state, index, reveal=False)
                else:
                    st.session_state["selected_segment_id"] = segment_id
                    st.session_state[_NAV_PENDING_SCROLL] = index
                try:
                    st.rerun(scope="fragment")
                except Exception:
                    st.rerun()
        return

    # Active row: construct full popover menu
    if structure_edit_blocked_fn:
        blocked, runtime_status = structure_edit_blocked_fn(job_id, state)
    else:
        runtime_view = core.build_job_runtime_view(job_id, state)
        runtime_status = runtime_view.get("status") or "idle"
        blocked = runtime_status in {"running", "waiting_external", "queued", "starting"}

    with st.popover("⋯", key=f"cat_actions_{job_id}_{index}", use_container_width=True):
        st.markdown('<div class="tp-cat-action-menu-title">段落操作</div>',
                    unsafe_allow_html=True)
        if blocked:
            st.caption("任务运行中，完成或暂停后可编辑段落结构。")
        if st.button("编辑原文", key=f"cat_action_source_{job_id}_{index}",
                     disabled=blocked, width="stretch"):
            if flush_draft_fn:
                flush_draft_fn(job_id, state, index, segment_id)
            if open_editor_fn:
                open_editor_fn(job_id, index, "source")
            st.rerun()
        if st.button("拆分段落", key=f"cat_action_split_{job_id}_{index}",
                     disabled=blocked, width="stretch"):
            if flush_draft_fn:
                flush_draft_fn(job_id, state, index, segment_id)
            if open_editor_fn:
                open_editor_fn(job_id, index, "split")
            st.rerun()
        has_next = index + 1 < len(pairs)
        if st.button("与下一段合并", key=f"cat_action_merge_{job_id}_{index}",
                     disabled=blocked or not has_next, width="stretch"):
            if flush_draft_fn:
                flush_draft_fn(job_id, state, index, segment_id)
                if has_next:
                    next_seg_id = segment_id_fn(job_id, index + 1, pairs[index + 1]) if segment_id_fn else (
                        core.segment_uid(pairs[index + 1]) or str(pairs[index + 1].get("segment_id") or (index + 1))
                    )
                    flush_draft_fn(job_id, state, index + 1, next_seg_id)
            if open_editor_fn:
                open_editor_fn(job_id, index, "merge")
            st.rerun()
        if st.button("在下方插入空段", key=f"cat_action_insert_{job_id}_{index}",
                     disabled=blocked, width="stretch"):
            if flush_draft_fn:
                flush_draft_fn(job_id, state, index, segment_id)
            try:
                core.mutate_translation_segments(job_id, index, "insert")
            except (RuntimeError, ValueError, IndexError) as exc:
                st.error(str(exc))
            else:
                new_state = core.load_job_state(job_id) or state
                if purge_edit_state_fn:
                    purge_edit_state_fn(job_id, new_state)
                inserted_index = index + 1
                new_pairs = new_state.get("pairs") or []
                if inserted_index < len(new_pairs):
                    st.session_state["selected_segment_id"] = (
                        segment_id_fn(job_id, inserted_index, new_pairs[inserted_index])
                        if segment_id_fn else (
                            core.segment_uid(new_pairs[inserted_index])
                            or str(new_pairs[inserted_index].get("segment_id") or inserted_index)
                        )
                    )
                if structure_flash_fn:
                    structure_flash_fn("insert", index, inserted_index=inserted_index)
                if open_editor_fn:
                    open_editor_fn(job_id, inserted_index, "source")
                st.rerun()

        st.markdown('<div class="tp-cat-action-menu-title">原文清理</div>',
                    unsafe_allow_html=True)
        has_content = bool(str(pair.get("source") or "").strip()
                           or str(pair.get("target") or "").strip())
        if st.button("排除本段（保留原文）",
                     key=f"cat_action_exclude_{job_id}_{index}",
                     disabled=blocked or not has_content, width="stretch",
                     help="排除后才不会进入翻译、待完成数量与译文文档；"
                          "原文完整保留，可在「已排除」里恢复。"):
            if flush_draft_fn:
                flush_draft_fn(job_id, state, index, segment_id)
            try:
                core.mutate_translation_segments(
                    job_id, index, "exclude", exclude_reason="人工判定为无效原文")
            except (RuntimeError, ValueError, IndexError) as exc:
                st.error(str(exc))
            else:
                fresh = core.load_job_state(job_id) or {}
                if purge_edit_state_fn:
                    purge_edit_state_fn(job_id, fresh)
                if workspace_flash_fn:
                    workspace_flash_fn(
                        f"第 {index + 1} 段已排除：不进入翻译与交付；"
                        "原文保留，可在「已排除」中恢复。", "success")
                st.rerun()

        if pair.get("manual_segment"):
            empty = not str(pair.get("source") or "").strip() and not str(
                pair.get("target") or "").strip()
            if st.button("删除空段", key=f"cat_action_delete_{job_id}_{index}",
                         disabled=blocked or not empty, width="stretch"):
                try:
                    core.mutate_translation_segments(job_id, index, "delete")
                except (RuntimeError, ValueError, IndexError) as exc:
                    st.error(str(exc))
                else:
                    fresh = core.load_job_state(job_id) or {}
                    if purge_edit_state_fn:
                        purge_edit_state_fn(job_id, fresh)
                    if structure_flash_fn:
                        structure_flash_fn("delete", index)
                    st.rerun()

        st.markdown('<div class="tp-cat-action-menu-title">快捷动作</div>',
                    unsafe_allow_html=True)
        source_text = str(pair.get("source") or "").strip()
        if st.button("复制原文到译文", key=f"cat_action_copy_{job_id}_{index}",
                     disabled=blocked or not source_text, width="stretch",
                     help="适合专名、代码、公式或译者自带内容；仍然需要点保存。"):
            if seed_editor_fn:
                seed_editor_fn(job_id, index, segment_id, source_text,
                               target=str(pair.get("target") or ""))
            st.rerun()

        if st.button("复制原文到译文并保存",
                     key=f"cat_action_copy_save_{job_id}_{index}",
                     disabled=blocked or not source_text, width="stretch"):
            if seed_editor_fn:
                seed_editor_fn(job_id, index, segment_id, source_text,
                               target=str(pair.get("target") or ""))
            if commit_row_fn:
                if commit_row_fn(
                        job_id, state, index, segment_id,
                        baseline=str(pair.get("target") or "")):
                    st.rerun()

        empty_target = not str(pair.get("target") or "").strip()
        label = "翻译本段" if empty_target else "重译本段"
        if st.button(label, key=f"cat_action_retranslate_{job_id}_{index}",
                     disabled=blocked or not api_ready or not source_text,
                     width="stretch",
                     help="只处理当前段落；已有的术语与项目记忆照常注入。"):
            if retranslate_fn:
                retranslate_fn(job_id, index)
        if not api_ready:
            st.caption("定点翻译需要先完成 AI 引擎配置。")

        draft = draft_for_fn(job_id, segment_id) if draft_for_fn else None
        if draft:
            st.markdown('<div class="tp-cat-action-menu-title">未保存的修改</div>',
                        unsafe_allow_html=True)
            if st.button("保存这一段", key=f"cat_action_save_{job_id}_{index}",
                         type="primary", width="stretch"):
                if commit_row_fn:
                    if commit_row_fn(
                            job_id, state, index, segment_id,
                            baseline=str(draft.get("baseline") or "")):
                        st.rerun()
            if st.button("丢弃这一段未保存的修改",
                         key=f"cat_action_discard_{job_id}_{index}",
                         width="stretch"):
                if drop_draft_fn:
                    drop_draft_fn(job_id, segment_id)
                if reset_editor_fn:
                    reset_editor_fn(segment_id)
                if workspace_flash_fn:
                    workspace_flash_fn("已丢弃该段落未保存的修改。", "info")
                st.rerun()

        if runtime_status == "completed":
            st.caption("段落结构修改会使当前交付回到草稿状态。")


def render_translation_row_actions(
    job_id: str,
    state: Dict[str, Any],
    index: int,
    segment_id: str,
    pair: Dict[str, Any],
    *,
    baseline: str,
    is_dirty: bool,
    anomaly: Optional[Tuple[str, str]] = None,
    commit_row_fn: Optional[Callable[..., Any]] = None,
    go_to_neighbour_fn: Optional[Callable[..., Any]] = None,
) -> None:
    """行内保存区：状态 + 保存 + 保存并进入下一段。"""
    foot_col, save_col, next_col = st.columns([1.35, 0.62, 1.05], gap="small")
    if is_dirty:
        chips = ('<span class="tp-cat-status is-dirty">● 未保存</span>'
                 '<span class="tp-cat-status is-hint">'
                 '⌘/Ctrl+Enter 提交输入后点保存</span>')
    elif anomaly is not None:
        label, text = anomaly
        chips = f'<span class="tp-cat-status {label}">{escape(text)}</span>'
    else:
        chips = ""
    foot_col.markdown(chips, unsafe_allow_html=True)
    with save_col:
        with st.container(key=f"cat_save_{job_id}_{index}"):
            if st.button("保存", key=f"cat_save_btn_{job_id}_{index}",
                         type="primary" if is_dirty else "secondary",
                         width="stretch"):
                if commit_row_fn and commit_row_fn(
                        job_id, state, index, segment_id, baseline=baseline):
                    try:
                        st.rerun(scope="fragment")
                    except Exception:
                        st.rerun()
    with next_col:
        with st.container(key=f"cat_save_next_{job_id}_{index}"):
            if st.button("保存并下一段", key=f"cat_save_next_btn_{job_id}_{index}",
                         width="stretch"):
                saved = commit_row_fn(
                    job_id, state, index, segment_id,
                    baseline=baseline, quiet=True) if commit_row_fn else False
                if go_to_neighbour_fn:
                    go_to_neighbour_fn(job_id, state, index, +1, saved=saved)


def render_translation_row(
    job_id: str,
    state: Dict[str, Any],
    index: int,
    pair: Dict[str, Any],
    segment_id: str,
    selected_index: int,
    blocking_segments: set,
    *,
    status_label_fn: Optional[Callable[..., str]] = None,
    editor_key_fn: Optional[Callable[..., str]] = None,
    draft_for_fn: Optional[Callable[..., Any]] = None,
    row_anomaly_fn: Optional[Callable[..., Any]] = None,
    navigate_fn: Optional[Callable[..., Any]] = None,
    editor_changed_fn: Optional[Callable[..., Any]] = None,
    row_actions_fn: Optional[Callable[..., Any]] = None,
    segment_actions_fn: Optional[Callable[..., Any]] = None,
) -> None:
    """Render a single CAT row: index + source + editable target + actions."""
    pair = pair if isinstance(pair, dict) else {}
    status = status_label_fn(pair, state, index) if status_label_fn else "待审校"
    cell_class = f"tp-cat-rowcell {cat_status_tone(status)}".strip()
    is_active = index == selected_index
    source_text = str(pair.get("source") or "").strip()
    target_text = str(pair.get("target") or "")
    editor_key = editor_key_fn(segment_id) if editor_key_fn else f"translation_editor_{segment_id}"
    baseline_key = f"{_CAT_BASELINE_PREFIX}{editor_key}"

    seeds = st.session_state.get(_TRANSLATION_EDITOR_SEED)
    if isinstance(seeds, dict) and str(segment_id) in seeds:
        st.session_state.pop(baseline_key, None)
        seeded = seeds.pop(str(segment_id))
        if not seeds:
            st.session_state.pop(_TRANSLATION_EDITOR_SEED, None)
        else:
            st.session_state[_TRANSLATION_EDITOR_SEED] = seeds
    else:
        seeded = None

    draft = draft_for_fn(job_id, segment_id) if draft_for_fn else None
    if (seeded is None and draft is not None
            and editor_key not in st.session_state):
        st.session_state.pop(baseline_key, None)
        seeded = str(draft.get("text") or "")
    if editor_key not in st.session_state:
        st.session_state[baseline_key] = target_text
    baseline = st.session_state.get(baseline_key, target_text)
    current = (seeded if seeded is not None
               else st.session_state.get(editor_key, target_text))

    is_dirty = bool(draft) or str(current) != str(baseline)
    row_class = f"{cell_class}{' is-active' if is_active else ''}".strip()
    anomaly = row_anomaly_fn(
        pair, index, blocking_segments, is_dirty,
        bool(state.get("translation_core_review_required"))) if row_anomaly_fn else None

    issue_badge = ('<div class="tp-cat-badges">'
                   '<span class="tp-cat-badge is-issue">必须处理</span></div>'
                   if index in blocking_segments else "")

    with st.container(key=f"cat_row_{job_id}_{index}"):
        st.markdown(f'<span class="{row_class}" data-segment="{index}"></span>',
                    unsafe_allow_html=True)
        number_col, source_col, target_col, action_col = st.columns(
            [0.42, 3.42, 3.52, 0.34], gap="medium")
        with number_col:
            with st.container(key=f"cat_num_{job_id}_{index}"):
                btn_kwargs: Dict[str, Any] = {
                    "key": f"cat_sel_{job_id}_{index}",
                    "help": f"第 {index + 1} 段 · {status}" + ("（当前段落）" if is_active else ""),
                    "type": "primary" if is_active else "secondary",
                    "width": "stretch",
                }
                if navigate_fn:
                    btn_kwargs["on_click"] = navigate_fn
                    btn_kwargs["args"] = (job_id, state, index)
                    btn_kwargs["kwargs"] = {"reveal": False}
                st.button(str(index + 1), **btn_kwargs)
        source_col.markdown(
            f'<div class="tp-cat-source{" is-empty" if not source_text else ""}">'
            f'{escape(source_text) or "（空段落）"}</div>{issue_badge}',
            unsafe_allow_html=True)
        with target_col:
            with st.container(key=f"cat_editor_{job_id}_{index}"):
                ta_kwargs: Dict[str, Any] = {
                    "height": 48,
                    "label_visibility": "collapsed",
                    "placeholder": "尚未翻译——在这里写译文",
                }
                if editor_changed_fn:
                    ta_kwargs["on_change"] = editor_changed_fn
                    ta_kwargs["args"] = (job_id, index, segment_id, baseline)
                st.text_area("译文", value=current, key=editor_key, **ta_kwargs)
            if is_dirty or is_active:
                if row_actions_fn:
                    row_actions_fn(
                        job_id, state, index, segment_id, pair,
                        baseline=baseline, is_dirty=is_dirty, anomaly=anomaly)
                else:
                    render_translation_row_actions(
                        job_id, state, index, segment_id, pair,
                        baseline=baseline, is_dirty=is_dirty, anomaly=anomaly)
        with action_col:
            if segment_actions_fn:
                segment_actions_fn(job_id, state, index, pair, is_active=is_active)
            else:
                render_translation_segment_actions(
                    job_id, state, index, pair, is_active=is_active)


def render_cat_grid_table(
    job_id: str,
    state: Dict[str, Any],
    visible_indexes: Sequence[int],
    records: Sequence[Dict[str, Any]],
    blocking_segments: set,
    selected_index: int,
    pending_scroll: Optional[int] = None,
    pending_focus: Optional[int] = None,
    *,
    render_row_fn: Optional[Callable[..., Any]] = None,
    navigate_fn: Optional[Callable[..., Any]] = None,
    scroll_trigger_fn: Optional[Callable[..., Any]] = None,
    focus_trigger_fn: Optional[Callable[..., Any]] = None,
) -> None:
    """Render CAT grid table within the surrounding Translation Fragment.

    Viewport pagination: CAT_GRID_ROWS = 40.
    Rerun scope: fragment (reruns the enclosing translation workspace fragment,
    ensuring CAT Grid and Inspector stay atomically in sync without drifting).
    """
    pairs = state.get("pairs") or []
    position = (visible_indexes.index(selected_index)
                if selected_index in visible_indexes else 0)
    start = max(0, min(position - CAT_GRID_ROWS // 2,
                       len(visible_indexes) - CAT_GRID_ROWS))
    window_indexes = visible_indexes[start:start + CAT_GRID_ROWS]

    st.markdown('<div class="tp-cat-head">'
                '<span class="tp-cat-num">段</span>'
                '<span class="tp-cat-col">原文</span>'
                '<span class="tp-cat-col is-tgt">译文 · 可直接编辑</span>'
                '<span class="tp-cat-act" aria-label="段落操作"></span></div>',
                unsafe_allow_html=True)
    if len(window_indexes) < len(visible_indexes):
        st.caption(f"显示第 {start + 1}–{start + len(window_indexes)} 段"
                   f"（筛选后共 {len(visible_indexes)} 段）；搜索或切换筛选可查看其余段落。")

    with st.container(key=f"cat_grid_{job_id}"):
        for index in window_indexes:
            if render_row_fn:
                render_row_fn(job_id, state, index, pairs[index],
                              records[index]["segment_id"],
                              selected_index, blocking_segments)
            else:
                render_translation_row(
                    job_id, state, index, pairs[index],
                    records[index]["segment_id"],
                    selected_index, blocking_segments,
                    navigate_fn=navigate_fn)

    # 40-row viewport pagination
    if len(visible_indexes) > CAT_GRID_ROWS:
        nav_cols = st.columns([1.5, 1, 1, 1.5], gap="small")
        has_prev = start > 0
        has_next = start + len(window_indexes) < len(visible_indexes)
        with nav_cols[1]:
            if st.button("◀ 上 40 段", key=f"cat_page_prev_{job_id}",
                         disabled=not has_prev, width="stretch"):
                new_idx = visible_indexes[max(0, start - CAT_GRID_ROWS)]
                if navigate_fn:
                    navigate_fn(job_id, state, new_idx, reveal=False)
                else:
                    st.session_state["selected_segment_id"] = records[new_idx]["segment_id"]
                try:
                    st.rerun(scope="fragment")
                except Exception:
                    st.rerun()
        with nav_cols[2]:
            if st.button("下 40 段 ▶", key=f"cat_page_next_{job_id}",
                         disabled=not has_next, width="stretch"):
                new_idx = visible_indexes[min(len(visible_indexes) - 1, start + len(window_indexes))]
                if navigate_fn:
                    navigate_fn(job_id, state, new_idx, reveal=False)
                else:
                    st.session_state["selected_segment_id"] = records[new_idx]["segment_id"]
                try:
                    st.rerun(scope="fragment")
                except Exception:
                    st.rerun()

    if scroll_trigger_fn:
        scroll_trigger_fn(pending_scroll)
    if focus_trigger_fn:
        focus_trigger_fn(job_id, pending_focus)


# Backward compatibility alias
render_cat_grid_fragment = render_cat_grid_table
