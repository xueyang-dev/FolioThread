"""Phase 3 Streamlit review-workbench interaction regressions."""
from pathlib import Path

import core
from transpraxis import assets, delivery, translation_evidence
from transpraxis.translation_core import fingerprint, normalize_finding
from transpraxis.workbench_view import review_workbench_view


APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _event(segment_id, event_id, value, decision="findings"):
    return {
        "phase": "formal_review",
        "review_scope": "current_translation",
        "review_event_id": event_id,
        "segment_ids": [segment_id],
        "decision": decision,
        "freshness_status": "current",
        "stale_segment_ids": [],
        "completion_receipt": {
            "status": "completed", "reviewed_segment_ids": [segment_id],
        },
        "translation_core": {"final_consumed_input_fingerprint": value},
    }


def _finding(segment_id, event_id, value, summary, location, *,
             suggested_target="", category="completeness"):
    finding = normalize_finding({
        "category": category,
        "severity": "blocking",
        "status": "open",
        "segment_id": segment_id,
        "location_key": location,
        "requires_human_confirmation": True,
        "summary": summary,
        "source_span": "Source",
        "target_span": "译文",
        "explanation": "当前译文需要人工确认。",
        "recommendation": "核对后选择安全动作。",
        "detector": "Semantic QA",
    }, input_fingerprint=value)
    finding.update({
        "type": "review", "segment_index": segment_id,
        "review_event_id": event_id, "reason": summary,
    })
    if suggested_target:
        finding["suggested_target"] = suggested_target
    return finding


def _state(findings_by_segment, *, suggested=False, style=False):
    state = core.new_job_state("phase3-workbench.docx")
    pairs = [
        {"source": f"Source {index + 1}", "target": f"译文 {index + 1}",
         "initial_target": f"译文 {index + 1}", "reviewed": False}
        for index in range(max(findings_by_segment) + 1)
    ]
    findings, events = [], []
    for segment_id, count in findings_by_segment.items():
        value = fingerprint({"segment": segment_id, "target": pairs[segment_id]["target"]})
        event_id = f"review-{segment_id}"
        events.append(_event(segment_id, event_id, value))
        for ordinal in range(count):
            findings.append(_finding(
                segment_id, event_id, value,
                f"第 {segment_id + 1} 段问题 {ordinal + 1}",
                f"source-offset:{ordinal}",
                suggested_target="建议译文" if suggested and ordinal == 0 else "",
                category="style" if style and ordinal == 0 else "completeness",
            ))
    state.update(
        p1_done=True,
        p2_done=True,
        report_enabled=False,
        translation_core_review_required=True,
        target_lang="简体中文",
        paras=[pair["source"] for pair in pairs],
        pairs=pairs,
        findings=findings,
        review_evidence=events,
        human_actions=[],
        review_stats={"reviewed_segments": 0},
        delivery_status="review_required",
    )
    return state


def _open_workspace(job_id, section, *, api_key=""):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state["provider_choice"] = "DeepSeek"
    at.session_state["api_key_DeepSeek"] = api_key
    at.session_state["active_job_id"] = job_id
    at.session_state["app_view"] = "workspace"
    at.session_state["workspace_mode"] = True
    at.session_state["workspace_section"] = section
    at.run()
    assert not at.exception, at.exception
    return at


def _queue(at):
    return next(item for item in at.radio if item.label == "审校队列")


def test_suggested_target_action_edits_rereviews_and_clears_current_work(
        tmp_path, monkeypatch):
    old_output = core.OUTPUT_DIR
    core.OUTPUT_DIR = tmp_path
    try:
        job_id = "phase3suggested01"
        state = _state({0: 1}, suggested=True)
        core.save_job_state(job_id, state)

        def fake_review(job_id_, indexes, provider, api_key, model, target_lang,
                        *, style_rules="", call_llm_fn=None):
            current = core.load_job_state(job_id_)
            reviewed = []
            for segment_id in indexes:
                pair = current["pairs"][segment_id]
                value = fingerprint({"segment": segment_id,
                                     "target": pair["target"], "refresh": True})
                event_id = f"review-refresh-{segment_id}"
                translation_evidence.register_runtime_review_event(
                    current, _event(segment_id, event_id, value, decision="clean"),
                    [], event_id, [segment_id])
                pair.update(reviewed=True, review_status="reviewed_clean",
                            accepted_target=pair["target"],
                            target_provenance="reviewed")
                reviewed.append(segment_id)
            current["delivery_status"] = delivery.compute_delivery_status(current)
            core.save_job_state(job_id_, current)
            return current, {"reviewed_segment_ids": reviewed,
                             "failed_segment_ids": []}

        monkeypatch.setattr(core, "review_translation_segments", fake_review)
        at = _open_workspace(job_id, "review", api_key="test-key")

        assert any(button.label == "应用建议并复审" and button.disabled is False
                   for button in at.button)
        assert any(button.label == "修改译文" for button in at.button)
        assert any(button.label == "保留当前译文" for button in at.button)
        assert any(button.label == "重新翻译并复审" for button in at.button)
        next(button for button in at.button
             if button.label == "应用建议并复审").click()
        at.run()

        assert not at.exception, at.exception
        updated = core.load_job_state(job_id)
        assert updated["pairs"][0]["target"] == "建议译文"
        old_finding = updated["findings"][0]
        assert old_finding["status"] == "stale"
        assert old_finding["status_before_stale"] == "open"
        assert old_finding.get("resolved") is not True
        assert any(action.get("decision") == "request_revision"
                   for action in updated["human_actions"])
        assert review_workbench_view(updated)["queue_items"] == []
        assert review_workbench_view(updated)["delivery"]["title"] == "翻译审校已完成"
        assert any("建议译文已应用" in item.value for item in at.success)
        assert any(button.label == "前往交付" for button in at.button)
    finally:
        core.OUTPUT_DIR = old_output


def test_review_actions_select_same_segment_next_then_cross_navigate(tmp_path):
    old_output = core.OUTPUT_DIR
    core.OUTPUT_DIR = tmp_path
    try:
        job_id = "phase3selection01"
        core.save_job_state(job_id, _state({0: 2, 1: 1}))
        loaded = core.load_job_state(job_id)
        current = review_workbench_view(loaded)["queue_items"]
        first_segment_items = [item for item in current if item["segment_id"] == 0]
        second_segment_item = next(item for item in current if item["segment_id"] == 1)

        at = _open_workspace(job_id, "review")
        filter_control = next(item for item in at.segmented_control
                              if item.label == "筛选审校任务")
        filter_control.set_value("待处理 3")
        at.run()
        queue = _queue(at)
        first_label = next(label for label in queue.options
                           if first_segment_items[0]["summary"] in label)
        queue.set_value(first_label)
        at.run()
        next(button for button in at.button if button.label == "确认已解决").click()
        at.run()

        assert not at.exception, at.exception
        assert at.session_state["selected_finding_id"] == \
            first_segment_items[1]["finding_id"]
        assert any("已确认问题解决" in item.value for item in at.success)

        next(button for button in at.button if button.label == "保留当前译文").click()
        at.run()
        assert at.session_state["selected_finding_id"] == second_segment_item["finding_id"]
        assert any("已保留当前译文" in item.value for item in at.success)

        next(button for button in at.button if button.label == "修改译文").click()
        at.run()
        assert at.session_state["workspace_section"] == "translation"
        assert at.session_state["selected_segment_id"] == assets.segment_id(job_id, 1)
        assert any("当前段落 · #2" in item.value for item in at.markdown)

        next(button for button in at.button if button.label == "查看审校").click()
        at.run()
        assert at.session_state["workspace_section"] == "review"
        assert at.session_state["selected_finding_id"] == second_segment_item["finding_id"]
    finally:
        core.OUTPUT_DIR = old_output


def test_style_rule_requires_explicit_confirmation(tmp_path):
    old_output = core.OUTPUT_DIR
    core.OUTPUT_DIR = tmp_path
    try:
        job_id = "phase3style00001"
        core.save_job_state(job_id, _state({0: 1}, style=True))
        at = _open_workspace(job_id, "review")

        assert not core.load_job_state(job_id).get("confirmed_style_rules")
        assert any(expander.label == "保存为项目风格规则"
                   for expander in at.expander)
        rule = next(item for item in at.text_area if item.label == "规则")
        rule.set_value("采用正式、克制的书面语。")
        next(button for button in at.button if button.label == "确认保存").click()
        at.run()

        saved = core.load_job_state(job_id)["confirmed_style_rules"]
        assert [item["rule"] for item in saved] == ["采用正式、克制的书面语。"]
        assert any("项目风格规则已由你确认保存" in item.value for item in at.success)
    finally:
        core.OUTPUT_DIR = old_output


def test_delivery_risk_action_is_visible_only_for_current_blockers(tmp_path):
    old_output = core.OUTPUT_DIR
    core.OUTPUT_DIR = tmp_path
    try:
        job_id = "phase3risk000001"
        core.save_job_state(job_id, _state({0: 1}))
        at = _open_workspace(job_id, "delivery")

        assert any("仍要交付" in item.value for item in at.markdown)
        assert any(button.label == "确认风险并继续交付" for button in at.button)
        assert any(item.label == "我确认理解这些问题仍然存在，并决定继续交付"
                   for item in at.checkbox)

        core.save_translation_edit(job_id, 0, "人工修改后的译文")
        at.run()
        assert not at.exception, at.exception
        assert not any(button.label == "确认风险并继续交付" for button in at.button)
        assert any("需要重新审校" in item.value or "上次审校后发生变化" in item.value
                   for item in [*at.markdown, *at.error, *at.warning])
    finally:
        core.OUTPUT_DIR = old_output
