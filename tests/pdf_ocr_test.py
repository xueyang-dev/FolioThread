"""扫描 PDF 的本地 OCR 回退与主流程接入测试。"""

from pathlib import Path

import fitz

import core
from offline_provider import OfflineProvider


def test_scanned_pdf_uses_ocr_fallback(monkeypatch):
    calls = []

    monkeypatch.setattr(core, "extract_pdf_paragraphs", lambda _bytes: [])

    def fake_ocr(file_bytes, max_pages=None, on_progress=None):
        calls.append((file_bytes, max_pages))
        if on_progress:
            on_progress("OCR progress")
        return (
            "The first OCR line.\ncontinues here.\n\n第二个段落。",
            ["OCR 使用 eng 语言包"],
        )

    monkeypatch.setattr(core, "_ocr_pdf_text_with_warnings", fake_ocr)
    progress = []

    paragraphs, warnings = core.extract_document_paragraphs(
        "scan.pdf", b"fake-pdf", ocr_max_pages=3,
        on_progress=progress.append)

    assert calls == [(b"fake-pdf", 3)]
    assert progress == ["OCR progress"]
    assert paragraphs == ["The first OCR line. continues here.", "第二个段落。"]
    assert "OCR 使用 eng 语言包" in warnings


def test_missing_tesseract_returns_actionable_warning(monkeypatch):
    monkeypatch.setattr(core, "extract_pdf_paragraphs", lambda _bytes: [])
    monkeypatch.setattr(core, "_find_tesseract", lambda: "")

    paragraphs, warnings = core.extract_document_paragraphs(
        "scan.pdf", b"fake-pdf")

    assert paragraphs == []
    assert any("未找到本机 Tesseract OCR" in warning for warning in warnings)
    assert any("FOLIOTHREAD_TESSERACT_CMD" in warning for warning in warnings)


def test_tesseract_language_selection_does_not_require_chinese_pack():
    assert core._select_tesseract_language(["eng", "osd"]) == "eng"
    assert core._select_tesseract_language(["chi_sim", "eng"]) == "chi_sim+eng"
    assert core._select_tesseract_language(["osd", "snum"]) == ""


def test_pipeline_persists_full_document_ocr(tmp_path: Path, monkeypatch):
    old_output, old_call = core.OUTPUT_DIR, core.call_llm
    core.OUTPUT_DIR = tmp_path
    provider = OfflineProvider()
    core.call_llm = provider
    monkeypatch.setattr(core, "extract_pdf_paragraphs", lambda _bytes: [])
    ocr_calls = []

    def fake_ocr(file_bytes, max_pages=None, on_progress=None):
        ocr_calls.append(max_pages)
        return (
            "Scanned first paragraph.\n\nScanned second paragraph.",
            ["PDF 无文本层，已使用本地 OCR"],
        )

    monkeypatch.setattr(core, "_ocr_pdf_text_with_warnings", fake_ocr)
    try:
        document = fitz.open()
        document.new_page()
        pdf_bytes = document.tobytes()
        document.close()

        result = core.run_job_pipeline(
            "ocr-pipeline-test", "scan.pdf", pdf_bytes,
            provider="DeepSeek", api_key="k", model="m",
            target_lang="简体中文", auto_term=False, enable_report=False,
            translation_theory="", user_glossary=[], enable_review=False,
            enable_annotate=False, use_tm=False, enable_understanding=False,
            delivery_config={"deliver_report": False},
        )

        assert ocr_calls == [None]
        assert result["p1_done"] is True
        assert result["paras"] == [
            "Scanned first paragraph.", "Scanned second paragraph."
        ]
        assert any("本地 OCR" in warning for warning in result["warnings"])
        technical_log = (tmp_path / "ocr-pipeline-test" / "runtime_technical.log")
        assert technical_log.is_file()
        assert "document extraction" in technical_log.read_text(encoding="utf-8")
    finally:
        core.OUTPUT_DIR, core.call_llm = old_output, old_call
