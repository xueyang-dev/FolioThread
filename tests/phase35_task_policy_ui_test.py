"""Phase 3.5 task-scoped AI prerequisite regression."""
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _step4_app(review_required):
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state["app_view"] = "new"
    at.session_state["workspace_mode"] = False
    at.session_state["task_step"] = 4
    at.session_state["task_files"] = [{"name": "source.docx", "bytes": b"source"}]
    at.session_state["translation_preset"] = "学术增强" if review_required else "快速"
    at.session_state["strategy_config"] = {
        "auto_term": True,
        "use_tm": True,
        "enable_understanding": True,
        "enable_review": review_required,
        "strict_terminology_governance": review_required,
    }
    at.session_state["provider_choice"] = "DeepSeek"
    at.session_state["model_choice_DeepSeek"] = "deepseek-chat"
    at.session_state["api_key_DeepSeek"] = "translator-key"
    at.session_state["reviewer_mode"] = "separate"
    at.session_state["reviewer_provider_choice"] = "OpenAI"
    at.session_state["reviewer_model"] = "reviewer-model"
    at.session_state["reviewer_api_key"] = ""
    at.session_state["reviewer_base_url"] = ""
    at.run()
    assert not at.exception, at.exception
    return at


def test_no_review_presets_do_not_require_unused_reviewer_credentials():
    for preset in ("快速", "标准"):
        at = _step4_app(False)
        at.session_state["translation_preset"] = preset
        at.run()
        assert next(button for button in at.button
                    if button.label == "开始任务").disabled is False
        assert not any("已选择 AI 模型，但 API 凭据未配置" in item.value
                       for item in at.warning)


def test_review_enabled_preset_requires_separate_reviewer_credentials():
    at = _step4_app(True)

    assert next(button for button in at.button
                if button.label == "开始任务").disabled is True
    assert any("API 凭据未配置" in item.value for item in at.warning)
