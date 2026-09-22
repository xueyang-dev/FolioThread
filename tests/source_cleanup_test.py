"""LLM OCR source cleanup contract and pipeline checkpoint tests."""

import json
from pathlib import Path

import fitz

import core


def test_cleanup_repairs_ocr_and_reflows_without_changing_item_order():
    calls = []

    def llm(provider, api_key, model, system, user, **kwargs):
        calls.append((system, user, kwargs))
        return json.dumps({
            "segments": [
                {"index": 0, "text": "The: \"Midnight", "break_after": False},
                {"index": 1, "text": "Library —", "break_after": False},
                {"index": 2, "text": "Infinite lives.", "break_after": True},
                {"index": 3, "text": "Nora Seed finds herself.", "break_after": True},
            ]
        })

    cleaned, metadata, warnings = core.cleanup_source_paragraphs(
        ["The: “Midnacht", "Library —", "Infinite", "Nora Seed finds herself."],
        "DeepSeek", "key", "model", call_llm_fn=llm,
    )

    assert warnings == []
    assert cleaned == ['The: "Midnight Library — Infinite lives.',
                       "Nora Seed finds herself."]
    assert metadata["status"] == "completed"
    assert metadata["input_count"] == 4
    assert metadata["output_count"] == 2
    assert metadata["changed_segments"][0]["after"] == 'The: "Midnight'
    assert metadata["paragraph_merges"][0]["input_indices"] == [0, 1, 2]
    assert calls and calls[0][2]["response_format"]["json_schema"]["name"] == \
        "foliothread_source_cleanup"


def test_cleanup_failed_batch_keeps_original_source():
    def llm(*args, **kwargs):
        return "not json"

    cleaned, metadata, warnings = core.cleanup_source_paragraphs(
        ["The: “Midnacht", "Library —"],
        "DeepSeek", "key", "model", call_llm_fn=llm,
    )

    assert cleaned == ["The: “Midnacht", "Library —"]
    assert metadata["status"] == "partial"
    assert metadata["failed_batches"] == 1
    assert len(warnings) == 1 and "已保留提取文本" in warnings[0]


def test_cleanup_can_join_across_batch_boundary():
    calls = {"count": 0}

    def llm(provider, api_key, model, system, user, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return json.dumps({"segments": [
                {"index": 0, "text": "A sentence", "break_after": False},
                {"index": 1, "text": "continues", "break_after": False},
            ]})
        return json.dumps({"segments": [
            {"index": 0, "text": "here.", "break_after": True},
        ]})

    cleaned, metadata, warnings = core.cleanup_source_paragraphs(
        ["A sentence", "continues", "here."],
        "DeepSeek", "key", "model", call_llm_fn=llm,
        max_batch_items=2,
    )

    assert warnings == []
    assert cleaned == ["A sentence continues here."]
    assert metadata["paragraph_merges"][0]["input_indices"] == [0, 1, 2]


def test_pdf_pipeline_persists_cleaned_source_before_translation(tmp_path: Path,
                                                                 monkeypatch):
    old_output, old_call = core.OUTPUT_DIR, core.call_llm
    core.OUTPUT_DIR = tmp_path
    calls = {"cleanup": 0, "translation": 0}

    def llm(provider, api_key, model, system, user, **kwargs):
        if "OCR 纠错" in system:
            calls["cleanup"] += 1
            return json.dumps({
                "segments": [
                    {"index": 0, "text": "The: \"Midnight", "break_after": False},
                    {"index": 1, "text": "Library.", "break_after": True},
                ]
            })
        calls["translation"] += 1
        return json.dumps(["午夜图书馆。"])

    monkeypatch.setattr(core, "extract_pdf_paragraphs",
                        lambda _bytes: ["The: “Midnacht", "Library."])
    document = fitz.open()
    document.new_page()
    pdf_bytes = document.tobytes()
    document.close()
    core.call_llm = llm
    try:
        state = core.run_job_pipeline(
            "source-cleanup-pipeline", "scan.pdf", pdf_bytes,
            provider="DeepSeek", api_key="key", model="model",
            target_lang="简体中文", auto_term=False, enable_report=False,
            translation_theory="", user_glossary=[], enable_review=False,
            enable_annotate=False, use_tm=False, enable_understanding=False,
            enable_source_cleanup=True,
        )
        assert calls["cleanup"] == 1
        assert state["source_cleanup_done"] is True
        assert state["source_paras"] == ["The: “Midnacht", "Library."]
        assert state["paras"] == ['The: "Midnight Library.']
        assert state["pairs"][0]["source"] == 'The: "Midnight Library.'
        performance = json.loads(
            (tmp_path / "source-cleanup-pipeline" / "performance.json")
            .read_text(encoding="utf-8")
        )
        assert set(("pdf_classify", "layout_recovery", "rasterize", "ocr",
                    "deterministic_cleanup", "llm_cleanup", "segment_build")) \
            <= set(performance["stages"])
        assert performance["stages"]["llm_cleanup"]["batch_count"] == 1
    finally:
        core.OUTPUT_DIR, core.call_llm = old_output, old_call


def test_pdf_pipeline_translates_sentence_units_but_keeps_cleaned_paragraph(
        tmp_path: Path, monkeypatch):
    old_output, old_call = core.OUTPUT_DIR, core.call_llm
    core.OUTPUT_DIR = tmp_path

    def llm(provider, api_key, model, system, user, **kwargs):
        if "OCR 纠错" in system:
            return json.dumps({
                "segments": [
                    {"index": 0,
                     "text": "The first sentence. The second sentence.",
                     "break_after": True},
                ]
            })
        return json.dumps(["第一句。", "第二句。"])

    monkeypatch.setattr(core, "extract_pdf_paragraphs",
                        lambda _bytes: ["The first sentence. The second sentence."])
    document = fitz.open()
    document.new_page()
    pdf_bytes = document.tobytes()
    document.close()
    core.call_llm = llm
    try:
        state = core.run_job_pipeline(
            "sentence-unit-pipeline", "scan.pdf", pdf_bytes,
            provider="DeepSeek", api_key="key", model="model",
            target_lang="简体中文", auto_term=False, enable_report=False,
            translation_theory="", user_glossary=[], enable_review=False,
            enable_annotate=False, use_tm=False, enable_understanding=False,
            enable_source_cleanup=True,
        )
        assert state["source_paragraphs"] == [
            "The first sentence. The second sentence."
        ]
        assert state["paras"] == ["The first sentence.", "The second sentence."]
        assert [pair["source"] for pair in state["pairs"]] == state["paras"]
        assert [pair["target"] for pair in state["pairs"]] == ["第一句。", "第二句。"]
        assert state["segmentation"]["input_paragraph_count"] == 1
        assert state["segmentation"]["output_segment_count"] == 2
        assert state["source_cleanup"]["paragraph_count"] == 1
        assert state["source_cleanup"]["segment_count"] == 2
    finally:
        core.OUTPUT_DIR, core.call_llm = old_output, old_call


def test_legacy_partial_pdf_is_rebased_before_resume(tmp_path: Path, monkeypatch):
    old_output, old_call = core.OUTPUT_DIR, core.call_llm
    core.OUTPUT_DIR = tmp_path
    monkeypatch.setattr(core, "extract_pdf_paragraphs",
                        lambda _bytes: ["The: “Midnacht", "Library."])

    def llm(provider, api_key, model, system, user, **kwargs):
        if "OCR 纠错" in system:
            return json.dumps({
                "segments": [
                    {"index": 0, "text": "The: \"Midnight", "break_after": False},
                    {"index": 1, "text": "Library.", "break_after": True},
                ]
            })
        return json.dumps(["新的译文。"])

    document = fitz.open()
    document.new_page()
    pdf_bytes = document.tobytes()
    document.close()
    state = core.new_job_state("legacy.pdf")
    state.update(
        p1_done=True,
        p2_done=False,
        paras=["The: “Midnacht", "Library."],
        pairs=[{"source": "The: “Midnacht", "target": "旧译文"}],
    )
    core.save_job_state("legacy-source-cleanup", state)
    core.call_llm = llm
    try:
        result = core.run_job_pipeline(
            "legacy-source-cleanup", "legacy.pdf", pdf_bytes,
            provider="DeepSeek", api_key="key", model="model",
            target_lang="简体中文", auto_term=False, enable_report=False,
            translation_theory="", user_glossary=[], enable_review=False,
            enable_annotate=False, use_tm=False, enable_understanding=False,
        )
        assert result["source_cleanup_done"] is True
        assert result["source_cleanup"]["previous_pair_count"] == 1
        assert result["pairs"][0]["source"] == 'The: "Midnight Library.'
        assert result["pairs"][0]["target"] == "新的译文。"
    finally:
        core.OUTPUT_DIR, core.call_llm = old_output, old_call
