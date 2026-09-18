"""Task Overview acceptance: one canonical state drives every surface.

`task_overview_state_test.py` pins the derivation itself.  This module renders
the real Streamlit workspace and checks the page-level acceptance rules that the
state-model refactor exists for:

* review disabled → the pipeline shows a skipped stage, never a green check;
* report disabled → no active "查看报告" CTA anywhere;
* blocking findings → the primary CTA is "查看问题" and no delivery CTA exists;
* suggestions → described as non-blocking, never as "必须处理";
* header, sidebar and hero show the same canonical label with the same colour.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import core
from transpraxis import task_overview as to

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


# ---------------- fixtures ----------------

def _state(count=2, *, review_required=False, targets=None, report=False):
    targets = targets or [f"译文 {index}" for index in range(count)]
    pairs = [{"source": f"Source {index}", "target": targets[index]}
             for index in range(count)]
    return {
        "p1_done": True,
        "p2_done": True,
        "paras": [pair["source"] for pair in pairs],
        "pairs": pairs,
        "translation_core_review_required": review_required,
        "report_enabled": report,
        "findings": [],
        "review_evidence": [],
        "human_actions": [],
    }


def _save(job_id, state):
    core.save_job_state(job_id, state)
    core.save_source(job_id, b"FolioThread task overview fixture")


def _open_overview(tmp_path, monkeypatch, job_id, state, section="overview"):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    _save(job_id, state)
    at = AppTest.from_file(str(APP_PATH), default_timeout=40)
    at.run()
    at.session_state["active_job_id"] = job_id
    at.session_state["app_view"] = "workspace"
    at.session_state["workspace_mode"] = True
    at.session_state["workspace_section"] = section
    at.run()
    assert not at.exception, at.exception
    return at


def _markup(at):
    return "\n".join(str(item.value) for item in at.markdown)


def _overview_markup(at):
    """Only the main column, so header/sidebar assertions stay meaningful."""
    return "\n".join(str(item.value) for item in at.markdown
                     if "tp-overview-hero" in str(item.value)
                     or "tp-overview-progress" in str(item.value)
                     or "tp-capability-strip" in str(item.value))


def _buttons(at):
    return [button.label for button in at.button]


def _has_button(at, text):
    return any(text in label for label in _buttons(at))


# ---------------- acceptance ----------------

def test_review_disabled_pipeline_marks_the_stage_skipped(tmp_path, monkeypatch):
    at = _open_overview(tmp_path, monkeypatch, "overviewnoreview",
                        _state(2, review_required=False))
    page = _markup(at)
    hero = _overview_markup(at)

    assert "独立审校" in hero, "pipeline 必须保留独立审校这一可选阶段"
    assert 'class="tp-progress-step is-skipped"' in hero, \
        "未启用的独立审校必须是 skipped"
    assert '独立审校未启用' in hero
    # skipped 阶段不能出现绿色勾：勾只属于 completed。
    assert ">✓</i>独立审校" not in hero
    assert ">—</i>独立审校" in hero
    # 也不允许出现"查看审校"的强 CTA。
    assert not _has_button(at, "查看审校")


def test_review_enabled_pipeline_can_mark_the_stage_current(tmp_path, monkeypatch):
    at = _open_overview(tmp_path, monkeypatch, "overviewreview",
                        _state(2, review_required=True))
    hero = _overview_markup(at)

    assert 'class="tp-progress-step is-active"' in hero
    assert ">●</i>独立审校" in hero
    assert _has_button(at, "查看审校")


def test_completed_translation_card_is_green_not_gray(tmp_path, monkeypatch):
    """卡片颜色取自 canonical tone：完成的翻译是绿勾，不是"未启用"的破折号。"""
    at = _open_overview(tmp_path, monkeypatch, "overviewcardtone", _state(2))
    page = _markup(at)

    assert 'class="tp-stage-card-content is-done"><strong>翻译</strong>' in page
    assert 'class="tp-stage-card-content is-muted"><strong>翻译</strong>' not in page


def test_report_disabled_never_shows_an_active_report_cta(tmp_path, monkeypatch):
    at = _open_overview(tmp_path, monkeypatch, "overviewnoreport",
                        _state(2, report=False))

    assert not _has_button(at, "查看报告"), \
        "未启用研究报告时不允许出现查看报告 CTA"
    assert ">—</i>研究报告" in _overview_markup(at) or \
        "报告未启用" in _overview_markup(at)


def test_blocking_findings_replace_the_delivery_cta(tmp_path, monkeypatch):
    at = _open_overview(tmp_path, monkeypatch, "overviewblocking",
                        _state(1, targets=["TODO: replace before delivery"]))

    labels = _buttons(at)
    assert any("问题" in label for label in labels), \
        f"blocking 时 primary CTA 必须是查看问题：{labels}"
    for forbidden in ("准备交付", "生成冻结交付", "继续准备交付"):
        assert not _has_button(at, forbidden), \
            f"blocking 时不得出现交付 CTA：{forbidden}"
    assert "需要处理问题" in _markup(at)


def test_suggestions_are_never_described_as_blocking(tmp_path, monkeypatch):
    state = _state(1, targets=["短"])
    state["pairs"][0]["source"] = "A" * 200
    state["paras"] = ["A" * 200]
    at = _open_overview(tmp_path, monkeypatch, "overviewsuggestion", state)

    page = _markup(at)
    assert "建议" in page
    assert "0 项必须处理" in page
    assert "不会阻止交付" in page
    assert _has_button(at, "准备交付"), "只有建议时仍可进入交付准备"


def test_ready_for_delivery_prep_never_claims_final_delivery(tmp_path, monkeypatch):
    at = _open_overview(tmp_path, monkeypatch, "overviewready", _state(2))

    page = _markup(at)
    assert "可以准备交付" in page
    assert "Ready for delivery" not in page
    assert "可以正式交付" not in page
    assert "已交付" not in page


def test_header_sidebar_and_hero_share_one_canonical_status(tmp_path, monkeypatch):
    at = _open_overview(tmp_path, monkeypatch, "overviewconsistent",
                        _state(1, review_required=True))
    state = core.load_job_state("overviewconsistent")
    expected = to.derive_task_overview_state(state)["label"]

    page = _markup(at)
    # amber → 三个表面各自的 token（verdict=attention、nav=attention、hero=amber），
    # 但标签必须是同一句 canonical 状态。
    assert 'class="tp-workspace-verdict is-attention"' in page
    assert f'title="{to.derive_task_overview_state(state)["detail"]}"' in page
    assert '<div class="tp-nav-canonical is-warning"' in page
    assert 'class="tp-overview-hero is-amber"' in page
    assert page.count(expected) >= 3, \
        "顶栏 / 侧栏 / Hero 必须显示同一句 canonical 状态"


def test_blocking_state_is_red_on_every_surface(tmp_path, monkeypatch):
    """同一个 canonical 状态在顶栏/侧栏/Hero 必须是同一套颜色语义。"""
    at = _open_overview(tmp_path, monkeypatch, "overviewred",
                        _state(1, targets=["TODO: replace before delivery"]))
    page = _markup(at)

    assert 'class="tp-workspace-verdict is-blocked"' in page
    assert '<div class="tp-nav-canonical is-danger"' in page
    assert 'class="tp-overview-hero is-red"' in page
    assert 'class="tp-stage-card-content is-blocked"' in page


def test_delivery_page_headline_matches_the_canonical_state(tmp_path, monkeypatch):
    state = _state(2)
    at = _open_overview(tmp_path, monkeypatch, "overviewdelivery",
                        state, section="delivery")
    page = _markup(at)

    assert "tp-readiness-card is-success" in page
    assert "可以准备交付" in page
    assert "可以冻结交付" not in page, \
        "'可以准备交付' 不得被写成 '可以冻结交付'"


def test_delivered_requires_a_real_snapshot(tmp_path, monkeypatch):
    """DELIVERED 只能来自真实冻结交付，不能凭 p2_done 自称"已交付"。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    job_id = "overviewdelivered"
    _save(job_id, _state(2))
    at = AppTest.from_file(str(APP_PATH), default_timeout=40)
    at.run()
    at.session_state["active_job_id"] = job_id
    at.session_state["app_view"] = "workspace"
    at.session_state["workspace_mode"] = True
    at.session_state["workspace_section"] = "overview"
    at.run()
    assert not at.exception, at.exception
    assert "可以准备交付" in _markup(at)
    assert "已交付" not in _overview_markup(at)

    _, ok, errors = core.approve_delivery(job_id, note="task overview test")
    assert ok, errors
    at.run()
    assert not at.exception, at.exception
    page = _markup(at)
    assert "已交付" in page
    assert "冻结交付 v1" in page
    assert 'class="tp-progress-step is-done"' in page


def test_unknown_section_state_degrades_to_a_canonical_state(tmp_path, monkeypatch):
    """State 里没有报告/审校配置时也必须给出合法 canonical 状态。"""
    at = _open_overview(tmp_path, monkeypatch, "overviewbare", {})

    assert "尚未开始" in _markup(at)
