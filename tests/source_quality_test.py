"""Source-admission gate tests for OCR fragments."""

import json
from pathlib import Path

import core


def test_source_quality_gate_quarantines_the_reported_ocr_run():
    report = core.audit_source_quality([
        "The Midnight Library",
        "20",
        "kati",
        "stud with ber",
        "fl - oe",
        "Also by Matt Haig",
    ])

    assert report["status"] == "blocked"
    assert report["flagged_count"] == 4
    assert [item["segment_index"] for item in report["flags"]] == [1, 2, 3, 4]
    assert report["clusters"] == [[1, 2, 3, 4]]
    assert any(
        any("异常空格连字符" in reason for reason in item["reasons"])
        for item in report["flags"]
    )


def test_source_quality_gate_does_not_block_normal_titles_or_identifiers():
    report = core.audit_source_quality([
        "The Midnight Library",
        "Also by Matt Haig",
        "@matthaig1",
        "matthaig.com",
        "A sentence ends here.",
    ])

    assert report["status"] == "passed"
    assert report["flagged_count"] == 0


def test_translation_gate_does_not_submit_quarantined_fragments(tmp_path: Path):
    old_output, old_call = core.OUTPUT_DIR, core.call_llm
    calls = []
    core.OUTPUT_DIR = tmp_path

    def llm(provider, api_key, model, system, user, temperature=0.1, **kwargs):
        calls.append((system, user))
        if "学术翻译专家" in system:
            return json.dumps(["这是完整译文。"])
        if "翻译流知识抽取器" in system:
            return "[]"
        raise AssertionError(f"unexpected model call: {system[:80]}")

    core.call_llm = llm
    try:
        state = core.new_job_state("gate.pdf")
        state["paras"] = ["kati", "stud with ber", "A real sentence."]
        result = core.translate_stage(
            state, "source-quality-gate", [], "DeepSeek", "key", "model",
            "简体中文", "", enable_review=False, use_tm=False,
        )

        assert result["source_quality_gate"]["flagged_count"] == 2
        assert [pair["target_provenance"] for pair in result["pairs"]] == [
            "source_review_required", "source_review_required", "generated",
        ]
        assert result["pairs"][0]["target"] == "kati"
        assert result["pairs"][1]["target"] == "stud with ber"
        submitted = "\n".join(user for system, user in calls if "学术翻译专家" in system)
        assert "kati" not in submitted
        assert "stud with ber" not in submitted
        gate_findings = [
            item for item in result["findings"]
            if item.get("type") == "source_quality_gate"
        ]
        assert {item["segment_index"] for item in gate_findings} == {0, 1}
        assert all(item["severity"] == "blocking" for item in gate_findings)
    finally:
        core.OUTPUT_DIR, core.call_llm = old_output, old_call


def test_delivery_gate_rechecks_legacy_runs_before_export():
    state = core.new_job_state("legacy.pdf")
    state.update(
        paras=["kati"],
        pairs=[{"source": "kati", "target": "浮冰"}],
        p2_done=True,
    )

    report = core.validate_delivery_translation_state(state)

    assert report["source_quality_gate"]["flagged_count"] == 1
    assert any(
        item.get("type") == "source_quality_gate"
        and item.get("severity") == "blocking"
        for item in report["blocking_findings"]
    )


def test_source_quality_gate_is_scoped_to_pdf_jobs():
    state = core.new_job_state("notes.docx")
    state.update(paras=["kati"], pairs=[{"source": "kati", "target": "kati"}], p2_done=True)

    report = core.validate_delivery_translation_state(state)

    assert report["source_quality_gate"]["status"] == "disabled"
    assert not report["source_quality_findings"]
