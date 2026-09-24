"""Segment Inspector column component.

Renders segment facts, AI findings, Agent actions, relevant terms, and TM reuse.
Shares the translation interaction fragment boundary with CAT Grid to eliminate
any cross-fragment state drift.
"""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import streamlit as st

import core
from transpraxis import profiler
from transpraxis import translation_planner as _planner

_CAT_BASELINE_PREFIX = "cat_baseline_"
_AGENT_STATUS_OK = "ok"
_AGENT_STATUS_ERROR = "error"
_AGENT_STATUS_EMPTY = "empty"


def render_workspace_translation_context(
    job_id: str,
    state: Dict[str, Any],
    overview: Optional[Dict[str, Any]] = None,
    *,
    review_runtime_fn: Optional[Callable[..., Any]] = None,
    issues_panel_fn: Optional[Callable[..., Any]] = None,
    selected_segment_fn: Optional[Callable[..., Any]] = None,
    document_agent_panel_fn: Optional[Callable[..., Any]] = None,
    pairs_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
    segment_records_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
    terms_for_pair_fn: Optional[Callable[..., Sequence[Tuple[str, str, str]]]] = None,
    findings_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
    plan_findings_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
    status_label_fn: Optional[Callable[..., str]] = None,
    navigate_fn: Optional[Callable[..., Any]] = None,
    draft_for_fn: Optional[Callable[..., Any]] = None,
    commit_row_fn: Optional[Callable[..., Any]] = None,
    next_unconfirmed_fn: Optional[Callable[..., Optional[int]]] = None,
    set_flash_fn: Optional[Callable[..., Any]] = None,
    seed_editor_fn: Optional[Callable[..., Any]] = None,
    retranslate_fn: Optional[Callable[..., Any]] = None,
    edit_count_fn: Optional[Callable[..., int]] = None,
    confidence_fn: Optional[Callable[..., Tuple[str, Optional[float]]]] = None,
    term_hits_fn: Optional[Callable[..., int]] = None,
    section_label_fn: Optional[Callable[..., str]] = None,
    segment_findings_fn: Optional[Callable[..., Any]] = None,
    select_review_item_fn: Optional[Callable[..., Any]] = None,
    agent_actions: Optional[Sequence[Tuple[str, str, str, str]]] = None,
    agent_suggestion_fn: Optional[Callable[..., Any]] = None,
    run_agent_action_fn: Optional[Callable[..., Any]] = None,
    save_translation_edit_fn: Optional[Callable[..., Any]] = None,
    reset_editor_fn: Optional[Callable[..., Any]] = None,
    drop_draft_fn: Optional[Callable[..., Any]] = None,
    translation_preview_fn: Optional[Callable[..., str]] = None,
    editor_key_fn: Optional[Callable[..., str]] = None,
    explain_fn: Optional[Callable[..., str]] = None,
    restore_pair_fn: Optional[Callable[..., Any]] = None,
    api_ready: bool = False,
) -> None:
    """Render the right-hand Agent Inspector within the Translation Fragment."""
    with profiler.span("inspector", job_id=job_id):
        review_runtime = review_runtime_fn() if review_runtime_fn else {}
        review_required = bool(state.get("translation_core_review_required"))

        if st.session_state.get("issues_panel_open"):
            if issues_panel_fn:
                issues_panel_fn(job_id, state)
            else:
                st.info("问题抽屉已打开。")
            return

        selected_segment = selected_segment_fn(job_id, state) if selected_segment_fn else None
        if selected_segment is None:
            if document_agent_panel_fn:
                document_agent_panel_fn(job_id, state, overview)
            else:
                st.markdown(
                    '<div class="tp-context-empty"><strong>未选择段落</strong>'
                    '<p>点击左侧段落编号查看该段落的上下文、识别术语与审校结果。</p></div>',
                    unsafe_allow_html=True)
            return

        pairs = pairs_fn(state) if pairs_fn else (state.get("pairs") or [])
        index = selected_segment["index"]
        pair = selected_segment["pair"]
        selected_id = selected_segment["segment_id"]

        terms = terms_for_pair_fn(state, pair) if terms_for_pair_fn else []
        findings = findings_fn(state, index) if findings_fn else []
        plan_findings = (
            plan_findings_fn(state, job_id=job_id, limit=40)
            if plan_findings_fn else _planner.plan_findings(state, job_id=job_id, limit=40)
        )
        plan_findings = [item for item in plan_findings if index in (item.get("segments") or [])]

        transport_issue = next(
            (issue for issue in (state.get("delivery_validation") or {}).get("issues") or []
             if issue.get("code") == "transport_wrapper"
             and issue.get("segment_index") == index), None)
        review_task = next((item for item in findings
                            if item.get("kind") in {"failed", "stale", "missing"}), None)

        if review_task and review_task.get("status_label"):
            status_label = review_task["status_label"]
        elif status_label_fn:
            status_label = status_label_fn(pair, state, index)
        else:
            status_label = "待审校"

        st.markdown(
            f'<div class="tp-translation-inspector-head"><div><h3>段落 #{index + 1}</h3></div>'
            f'<span class="tp-translation-inspector-position">{index + 1} / {len(pairs)}</span></div>',
            unsafe_allow_html=True)

        nav_prev, nav_next = st.columns(2, gap="small")
        prev_kwargs: Dict[str, Any] = {
            "key": f"translation_prev_{job_id}",
            "help": "上一段",
            "disabled": index == 0,
            "width": "stretch",
        }
        if navigate_fn:
            prev_kwargs["on_click"] = navigate_fn
            prev_kwargs["args"] = (job_id, state, index - 1)
            prev_kwargs["kwargs"] = {"reveal": False}
        nav_prev.button("← 上一段", **prev_kwargs)

        next_kwargs: Dict[str, Any] = {
            "key": f"translation_next_{job_id}",
            "help": "下一段",
            "disabled": index >= len(pairs) - 1,
            "width": "stretch",
        }
        if navigate_fn:
            next_kwargs["on_click"] = navigate_fn
            next_kwargs["args"] = (job_id, state, index + 1)
            next_kwargs["kwargs"] = {"reveal": False}
        nav_next.button("下一段 →", **next_kwargs)

        # ---- 编辑动作 ----
        segment_id = selected_id
        draft = draft_for_fn(job_id, segment_id) if draft_for_fn else None
        ed_key = editor_key_fn(segment_id) if editor_key_fn else f"translation_editor_{segment_id}"
        baseline = str(st.session_state.get(
            f"{_CAT_BASELINE_PREFIX}{ed_key}",
            str(pair.get("target") or "")))

        st.markdown('<div class="tp-inspector-section"><h4>编辑动作</h4>', unsafe_allow_html=True)
        if draft:
            st.markdown('<div class="tp-inspector-status"><span>●</span>'
                        '<strong>这一段有未保存的修改</strong></div>',
                        unsafe_allow_html=True)

        save_col, next_unconfirmed_col = st.columns([1.2, 1.6], gap="small")
        if save_col.button("保存本段译文", type="primary" if draft else "secondary",
                           key=f"translation_inspector_save_{job_id}",
                           width="stretch"):
            if commit_row_fn and commit_row_fn(job_id, state, index, segment_id, baseline=baseline):
                st.rerun()

        if next_unconfirmed_col.button(
                "保存并进入下一未确认段",
                key=f"translation_inspector_save_next_open_{job_id}",
                width="stretch",
                help="保存当前段，然后跳到下一个还没有译文或还没有通过审校的段落。"):
            if commit_row_fn:
                commit_row_fn(job_id, state, index, segment_id, baseline=baseline, quiet=True)
            fresh = core.load_job_state(job_id) or state
            target = next_unconfirmed_fn(fresh, index) if next_unconfirmed_fn else None
            if target is None:
                if set_flash_fn:
                    set_flash_fn("没有其它待处理段落了。", "info")
                st.rerun()
            else:
                if navigate_fn:
                    navigate_fn(job_id, fresh, target)
                else:
                    st.session_state["selected_segment_id"] = str(target)
                st.session_state["pending_focus_segment_id"] = target
                st.rerun()

        copy_col, ai_col = st.columns([1.1, 1.1], gap="small")
        if copy_col.button("复制原文到译文", key=f"translation_inspector_copy_{job_id}",
                           width="stretch", disabled=not str(pair.get("source") or "").strip(),
                           help="适合专名、代码、公式或译者自带内容；仍然需要点保存。"):
            if seed_editor_fn:
                seed_editor_fn(job_id, index, segment_id,
                               str(pair.get("source") or "").strip(),
                               target=str(pair.get("target") or ""))
            st.rerun()

        empty_target = not str(pair.get("target") or "").strip()
        if ai_col.button("翻译本段" if empty_target else "重译本段",
                         key=f"translation_inspector_retranslate_{job_id}",
                         width="stretch",
                         disabled=not api_ready or not str(pair.get("source") or "").strip()):
            if retranslate_fn:
                retranslate_fn(job_id, index)
        if not api_ready:
            st.caption("定点翻译需要先完成 AI 引擎配置。")
        st.markdown('</div>', unsafe_allow_html=True)

        # ---- 段落事实 ----
        edit_count = edit_count_fn(state, index, pair) if edit_count_fn else 0
        if confidence_fn:
            confidence, confidence_value = confidence_fn(findings)
        else:
            confidence, confidence_value = ("—", None)
        term_hits = term_hits_fn(state, pair) if term_hits_fn else 0
        review_note = "不适用" if not review_required else (
            "已审校" if not findings and pair.get("reviewed") else "待审校")
        sec_label = section_label_fn(state, index) if section_label_fn else "—"

        facts = [("状态", status_label, True),
                 ("人工修改", f"{edit_count} 次", edit_count > 0),
                 ("术语", f"{term_hits} 条" if term_hits else "", term_hits > 0),
                 ("审校", review_note, review_required),
                 ("AI 置信度", confidence if confidence_value is not None else "",
                  confidence_value is not None),
                 ("章节", sec_label, True)]
        facts = [(label, value) for label, value, show in facts
                 if show and value and value != "—"]
        facts_html = "".join(
            f'<div class="tp-inspector-fact"><span>{escape(label)}</span>'
            f'<strong>{escape(value)}</strong></div>' for label, value in facts)
        st.markdown(
            '<div class="tp-inspector-section"><h4>段落事实</h4>'
            f'<div class="tp-inspector-facts-list">{facts_html}</div></div>',
            unsafe_allow_html=True)

        if plan_findings:
            st.markdown('<div class="tp-inspector-section"><h4>Agent 发现</h4>', unsafe_allow_html=True)
            if segment_findings_fn:
                segment_findings_fn(plan_findings, job_id, index)
            else:
                for pf in plan_findings[:5]:
                    st.caption(f"• {escape(str(pf.get('title') or pf.get('kind') or ''))}")
            st.markdown('</div>', unsafe_allow_html=True)

        if findings:
            issue_label = (review_task["status_label"] if review_task and review_task.get("status_label")
                           else f"{len(findings)} 个审校问题")
            st.markdown(f'<div class="tp-inspector-section"><div class="tp-inspector-status">'
                        f'<span>!</span><strong>{escape(issue_label)}</strong></div></div>',
                        unsafe_allow_html=True)
            if st.button("查看审校", key=f"translation_open_review_{job_id}_{selected_id}",
                         width="stretch", type="secondary"):
                if select_review_item_fn:
                    select_review_item_fn(findings[0])
                st.session_state.workspace_section = "review"
                st.rerun()

        if transport_issue:
            st.markdown(
                '<div class="tp-transport-alert">'
                '<strong>译文结构异常</strong>'
                '<p>检测到 JSON / Markdown transport wrapper。原文仍安全保留；当前译文不能作为普通正文交付。</p>'
                '<span>修复路径：在中央网格编辑当前译文，或重新翻译当前段；修复后再运行交付检查。</span>'
                '</div>', unsafe_allow_html=True)

        # ---- Agent 动作 ----
        st.markdown('<div class="tp-inspector-section"><h4>Agent 动作</h4>', unsafe_allow_html=True)
        suggestion_key = f"translation_agent_suggestion_{selected_id}"
        actions_list = agent_actions or [
            ("polish", "润色", ":material/auto_fix_high:", "微调译文表达，保持忠实原意"),
            ("continue", "续写", ":material/edit_note:", "根据原文和既有译文接续未完翻译"),
            ("formal", "严谨", ":material/gavel:", "使用更正式、严谨的用词与句型"),
            ("concise", "精简", ":material/compress:", "在不丢失要点的前提下缩短译文篇幅"),
        ]

        with st.container(key=f"translation_agent_actions_{selected_id}"):
            action_cols = st.columns(2, gap="small")
            for position, (action, label, icon, help_text) in enumerate(actions_list):
                with action_cols[position % 2]:
                    if st.button(label, icon=icon, help=help_text,
                                 key=f"translation_agent_{action}_{selected_id}",
                                 disabled=not api_ready, width="stretch"):
                        if run_agent_action_fn and agent_suggestion_fn:
                            with st.spinner(f"Agent 正在{label}…"):
                                res = run_agent_action_fn(action, job_id, index, state)
                                st.session_state[suggestion_key] = agent_suggestion_fn(
                                    action, res, label=label)
                        st.rerun()

            if st.button("术语检查", icon=":material/rule:",
                         help="检查本段术语是否按项目术语表使用（只诊断，不改写）",
                         key=f"translation_agent_terms_{selected_id}",
                         disabled=not api_ready, width="stretch"):
                if run_agent_action_fn and agent_suggestion_fn:
                    with st.spinner("Agent 正在检查术语…"):
                        res = run_agent_action_fn(
                            "term_check", job_id, index, state,
                            custom=("只做术语检查：逐条说明本段是否遵守了项目术语，"
                                    "以及是否有术语被漏用或误用。用简体中文回答，"
                                    "不要输出改写后的译文。"))
                        st.session_state[suggestion_key] = agent_suggestion_fn(
                            "term_check", res, label="术语检查")
                st.rerun()

            if st.button("上下文一致性", icon=":material/hub:",
                         help="检查本段与前后段的衔接、指代与逻辑连贯（只诊断，不改写）",
                         key=f"translation_agent_context_{selected_id}",
                         disabled=not api_ready, width="stretch"):
                if run_agent_action_fn and agent_suggestion_fn:
                    with st.spinner("Agent 正在检查上下文…"):
                        res = run_agent_action_fn(
                            "context_check", job_id, index, state,
                            custom=("只做上下文一致性检查：说明本段与上一段、下一段在"
                                    "指代、逻辑衔接和术语延续上是否有问题。用简体中文回答，"
                                    "不要输出改写后的译文。"))
                        st.session_state[suggestion_key] = agent_suggestion_fn(
                            "context_check", res, label="上下文一致性")
                st.rerun()

            custom = st.text_input("自定义指令", key=f"translation_agent_custom_{selected_id}",
                                   placeholder="例如：保留引用标注，压缩到一句…",
                                   label_visibility="collapsed")
            custom_as_rewrite = st.checkbox(
                "作为改写候选（可写回译文）",
                key=f"translation_agent_custom_rewrite_{selected_id}",
                help="不勾选时，结果只作为诊断说明展示，不会覆盖当前译文。")
            if st.button("按指令处理", key=f"translation_agent_custom_run_{selected_id}",
                         disabled=not api_ready or not custom.strip(), width="stretch"):
                if run_agent_action_fn and agent_suggestion_fn:
                    with st.spinner("Agent 正在处理…"):
                        res = run_agent_action_fn("custom", job_id, index, state, custom=custom)
                        st.session_state[suggestion_key] = agent_suggestion_fn(
                            "custom", res, as_rewrite=custom_as_rewrite, label="自定义")
                st.rerun()

        if not api_ready:
            st.caption("AI 动作需要先完成引擎配置。")

        suggestion = st.session_state.get(suggestion_key)
        if isinstance(suggestion, dict) and suggestion.get("text"):
            status = str(suggestion.get("status") or _AGENT_STATUS_OK)
            is_failure = status in {_AGENT_STATUS_ERROR, _AGENT_STATUS_EMPTY}
            is_rewrite = suggestion.get("kind") == "rewrite" and not is_failure
            display = str(suggestion.get("label") or suggestion.get("action") or "")
            if is_failure:
                kind_label = "失败" if status == _AGENT_STATUS_ERROR else "没有结果"
            else:
                kind_label = "改写候选" if is_rewrite else "诊断"
            tone = " is-failure" if is_failure else ""
            st.markdown(
                f'<div class="tp-inspector-suggestion{tone}"><span>Agent · '
                f'{escape(display)} · {kind_label}</span>'
                f'<p>{escape(suggestion["text"])}</p></div>', unsafe_allow_html=True)
            if is_failure:
                st.caption("这次没有可写回的候选译文；当前译文未被改动。")
                if st.button("知道了", key=f"translation_agent_discard_{selected_id}",
                             width="stretch"):
                    st.session_state.pop(suggestion_key, None)
                    st.rerun()
            elif is_rewrite:
                apply_col, dismiss_col = st.columns([1.4, 1], gap="small")
                if apply_col.button("应用到译文", type="primary",
                                    key=f"translation_agent_apply_{selected_id}",
                                    width="stretch"):
                    if save_translation_edit_fn:
                        save_translation_edit_fn(job_id, index, suggestion["text"])
                    st.session_state.pop(suggestion_key, None)
                    if reset_editor_fn:
                        reset_editor_fn(selected_id)
                    if drop_draft_fn:
                        drop_draft_fn(job_id, selected_id)
                    if set_flash_fn:
                        set_flash_fn(
                            f"第 {index + 1} 段已应用 Agent 候选译文。"
                            + ("上一次审校已过期，需要重新审校。" if review_required else ""),
                            "warning" if review_required else "success")
                    st.rerun()
                if dismiss_col.button("丢弃", key=f"translation_agent_discard_{selected_id}",
                                      width="stretch"):
                    st.session_state.pop(suggestion_key, None)
                    st.rerun()
            else:
                st.caption("这是诊断结果，不会写回译文；如需改写请使用上方的改写动作。")
                if st.button("收起诊断", key=f"translation_agent_discard_{selected_id}",
                             width="stretch"):
                    st.session_state.pop(suggestion_key, None)
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        # ---- 相关术语 ----
        st.markdown('<div class="tp-inspector-section"><h4>相关术语</h4>', unsafe_allow_html=True)
        if terms:
            rows = "".join(
                f'<div class="tp-inspector-term"><span>{escape(source)}<br/>'
                f'<small>{escape(provenance)}</small></span><b>→ {escape(target)}</b></div>'
                for source, target, provenance in terms)
            st.markdown(f'<div class="tp-inspector-terms">{rows}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="tp-inspector-empty">本段无项目术语</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # ---- 翻译记忆 ----
        if pair.get("from_tm"):
            prev_src = translation_preview_fn(pair.get("source"), 100) if translation_preview_fn else str(pair.get("source") or "")[:100]
            prev_tgt = translation_preview_fn(pair.get("target"), 100) if translation_preview_fn else str(pair.get("target") or "")[:100]
            st.markdown('<div class="tp-inspector-section"><h4>翻译记忆</h4>'
                        '<div class="tp-inspector-status"><span>✓</span><strong>已匹配并复用</strong></div>'
                        f'<p class="tp-inspector-preview" style="margin-top:8px">源：{escape(prev_src)}</p>'
                        f'<p class="tp-inspector-preview">译：{escape(prev_tgt)}</p>'
                        '</div>', unsafe_allow_html=True)

        # ---- 上下文 ----
        with st.expander("上下文", expanded=False):
            if index:
                previous = pairs[index - 1].get("source") or "—"
                p_text = translation_preview_fn(previous, 180) if translation_preview_fn else str(previous)[:180]
                st.markdown(f'<p class="tp-inspector-preview"><strong>上一段</strong>{escape(p_text)}</p>',
                            unsafe_allow_html=True)
            if index + 1 < len(pairs):
                following = pairs[index + 1].get("source") or "—"
                f_text = translation_preview_fn(following, 180) if translation_preview_fn else str(following)[:180]
                st.markdown(f'<p class="tp-inspector-preview"><strong>下一段</strong>{escape(f_text)}</p>',
                            unsafe_allow_html=True)
            if not index and index + 1 >= len(pairs):
                st.caption("没有相邻段落。")

        # ---- 当前译法依据 ----
        with st.expander("当前译法依据", expanded=False):
            explanation_key = f"translation_explanation_{selected_id}"
            if st.session_state.get(explanation_key):
                st.write(st.session_state[explanation_key])
            else:
                st.caption("可让 AI 解释当前译法的语义、术语与上下文决策。")
            if st.button("解释当前译法", key=f"translation_explain_{selected_id}",
                         disabled=not api_ready, width="stretch"):
                if explain_fn:
                    with st.spinner("正在分析当前译法…"):
                        st.session_state[explanation_key] = explain_fn(job_id, index, state)
                st.rerun()
            if pair.get("human_edited"):
                if st.button("恢复原译", key=f"translation_restore_{selected_id}", width="stretch"):
                    if restore_pair_fn:
                        restore_pair_fn(job_id, index)
                    if reset_editor_fn:
                        reset_editor_fn(selected_id)
                    if set_flash_fn:
                        set_flash_fn(
                            f"第 {index + 1} 段已恢复原译"
                            + ("；当前内容需要重新审校。" if review_required else "。"),
                            "warning" if review_required else "success")
                    st.rerun()

        # ---- 翻译设置 ----
        with st.expander("翻译设置", expanded=False):
            profile = state.get("document_profile") or {}
            st.caption(f"风格：{profile.get('register') or '正式书面语'}")
            st.caption(f"文档画像：{profile.get('domain') or '未标注领域'} · {profile.get('genre') or '未标注文本类型'}")
            st.caption("源文件：" + str(state.get("filename") or "—"))
            review_runtime_label = ("独立审校：" + (review_runtime.get("model") or "已配置")
                                    if review_required else "当前任务未启用独立审校")
            st.caption(review_runtime_label)


# Backward compatibility alias
render_workspace_inspector_fragment = render_workspace_translation_context
