"""Regression test for in-place AI connection testing on task step 4 (confirm run)."""
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _step4_app(connection_status="unverified"):
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    at.session_state["app_view"] = "new"
    at.session_state["workspace_mode"] = False
    at.session_state["task_step"] = 4
    at.session_state["task_files"] = [{"name": "source.docx", "bytes": b"source"}]
    at.session_state["translation_preset"] = "快速"
    at.session_state["strategy_config"] = {
        "auto_term": False,
        "use_tm": True,
        "enable_understanding": False,
        "enable_review": False,
        "strict_terminology_governance": False,
    }
    at.session_state["provider_choice"] = "DeepSeek"
    at.session_state["model_choice_DeepSeek"] = "deepseek-chat"
    at.session_state["api_key_DeepSeek"] = "valid-key"
    at.session_state["provider_connection_status"] = connection_status
    at.session_state["reviewer_mode"] = "same"
    at.run()
    assert not at.exception, at.exception
    return at


def test_step4_test_button_success_stays_in_step4():
    at = _step4_app("unverified")

    # 验证初始状态：提示未验证，且显示「测试」按钮
    assert any("模型已配置，但连接尚未验证" in w.value for w in at.warning)
    test_btn = next((b for b in at.button if b.label == "测试"), None)
    assert test_btn is not None, "步骤4应提供就地「测试」按钮"

    with patch("core.test_provider", return_value=(True, "响应「OK」· 耗时 0.2s")):
        test_btn.click().run()

    assert not at.exception, at.exception
    # 关键断言：不再跳转到设置页，保持在 new 任务流程
    assert at.session_state["app_view"] == "new"
    assert at.session_state["provider_connection_status"] == "connected"
    # 警告条消失，开始任务按钮可用
    assert not any("模型已配置，但连接尚未验证" in w.value for w in at.warning)
    start_btn = next(b for b in at.button if b.label == "开始任务")
    assert not start_btn.disabled


def test_step4_test_button_failure_and_retry():
    at = _step4_app("unverified")
    test_btn = next(b for b in at.button if b.label == "测试")

    with patch("core.test_provider", return_value=(False, "鉴权失败 401")):
        test_btn.click().run()

    assert not at.exception, at.exception
    # 依然留在步骤4，未跳转到设置页
    assert at.session_state["app_view"] == "new"
    assert at.session_state["provider_connection_status"] == "error"
    assert any("最近一次连接测试未通过" in e.value for e in at.error)

    # 错误提示中包含重试按钮与检查设置按钮
    retry_btn = next((b for b in at.button if b.label == "重试"), None)
    settings_btn = next((b for b in at.button if b.label == "检查设置"), None)
    assert retry_btn is not None, "连接失败后应允许就地重试"
    assert settings_btn is not None, "连接失败后允许前往设置"

    # 点击重试成功后留在当前页面且变为 connected
    with patch("core.test_provider", return_value=(True, "响应「OK」· 耗时 0.1s")):
        retry_btn.click().run()

    assert at.session_state["app_view"] == "new"
    assert at.session_state["provider_connection_status"] == "connected"
    assert not any("最近一次连接测试未通过" in e.value for e in at.error)
