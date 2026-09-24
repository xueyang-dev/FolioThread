"""Step 03 Deliverables Builder interaction regressions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _step3_app(*, research=False):
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state["task_files"] = [{"name": "source.docx", "bytes": b"source"}]
    at.session_state["task_step"] = 3
    if research:
        at.session_state["translation_preset"] = "学术增强"
        at.session_state["strategy_config"] = {
            "auto_term": True,
            "use_tm": True,
            "enable_understanding": True,
            "enable_review": True,
            "strict_terminology_governance": True,
        }
    at.run()
    assert not at.exception, at.exception
    return at


def test_standard_delivery_is_recommended_and_counts_real_files():
    at = _step3_app()

    preset = next(item for item in at.selectbox if item.label == "交付方案")
    assert preset.value == "standard"
    assert any("标准交付" in option and "推荐" in option for option in preset.options)
    assert any("译文文件" in item.value and "已选 2" in item.value
               for item in at.markdown)
    assert any("语言资产" in item.value and "已选 1" in item.value
               for item in at.markdown)
    assert not any("研究产物" in item.value for item in at.markdown)
    assert any("将生成 3 个文件" in item.value and "DOCX ×2" in item.value
               and "XLSX ×1" in item.value for item in at.markdown)
    assert not at.toggle


def test_manual_delivery_change_marks_preset_and_complete_overwrites_it():
    at = _step3_app()

    next(item for item in at.checkbox if item.key == "deliver_pdf").check()
    at.run()
    assert at.session_state["delivery_preset"] == "standard"
    assert at.session_state["delivery_preset_modified"] is True
    assert any("将生成 4 个文件" in item.value for item in at.markdown)
    assert any("已修改" in item.value for item in at.markdown)

    next(item for item in at.selectbox if item.label == "交付方案").select("complete")
    at.run()
    config = at.session_state["output_config"]
    assert at.session_state["delivery_preset"] == "complete"
    assert at.session_state["delivery_preset_modified"] is False
    assert all(config[key] for key in (
        "deliver_plain_docx", "deliver_bilingual_docx", "deliver_pdf",
        "deliver_terms_xlsx", "deliver_tmx", "deliver_tbx"))
    assert not config["deliver_jsonl"]
    assert any("将生成 6 个文件" in item.value
               and "TMX ×1" in item.value and "TBX ×1" in item.value
               for item in at.markdown)


def test_annotation_is_a_disabled_child_of_bilingual_docx():
    at = _step3_app()
    next(item for item in at.checkbox if item.key == "output_annotate").check()
    at.run()
    assert at.session_state["output_config"]["enable_annotate"] is True

    next(item for item in at.checkbox if item.key == "deliver_bilingual_docx").uncheck()
    at.run()
    annotation = next(item for item in at.checkbox if item.key == "output_annotate")
    assert annotation.disabled is True
    assert annotation.value is False
    assert at.session_state["output_config"]["enable_annotate"] is False


def test_research_outputs_follow_step2_strategy_visibility():
    ordinary = _step3_app()
    assert not any(item.key == "output_report" for item in ordinary.checkbox)
    assert not any(item.label == "理论框架" for item in ordinary.selectbox)

    research = _step3_app(research=True)
    report = next(item for item in research.checkbox if item.key == "output_report")
    assert report.value is False
    assert not any(item.label == "理论框架" for item in research.selectbox)

    report.check()
    research.run()
    assert any(item.label == "理论框架" and item.value == "自动推荐（建议）"
               for item in research.selectbox)
    assert any("翻译实践报告" in item.label for item in research.checkbox)


def test_switching_delivery_preset_does_not_raise_keyerror_on_outputs():
    """切换交付方案与单独切换输出勾选（如 deliver_tmx）不抛出任何 KeyError。"""
    at = _step3_app()
    preset = next(item for item in at.selectbox if item.label == "交付方案")
    for choice in ("complete", "compact", "standard", "complete"):
        preset.select(choice)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        tmx = next(item for item in at.checkbox if item.key == "deliver_tmx")
        if tmx.value:
            tmx.uncheck()
        else:
            tmx.check()
        at.run()
        assert not at.exception, [e.value for e in at.exception]
