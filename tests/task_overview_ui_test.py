"""Task Banner acceptance: one canonical state, stated once.

`task_overview_state_test.py` pins the derivation itself.  This module renders
the real Streamlit workspace and checks the page-level acceptance rules:

* the workspace has no "overview" page — an old/unknown section degrades to the
  translation workbench;
* review disabled → no review CTA and no review indicator;
* report disabled → no active "查看报告" CTA;
* blocking findings → the primary CTA is "查看问题" and no delivery CTA exists;
* suggestions → described as non-blocking, never as "必须处理";
* the Banner is the **only** surface that states the canonical verdict;
* the Banner is a compact **two-row** card — the task details live in the
  workbench toolbar, not as a third row inside the Banner;
* a running/interrupted task can be resumed from the Banner (the runtime
  controls used to live on the deleted overview page);
* runtime details open in a side-drawer surface, with technical information
  kept behind a second collapsed disclosure.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import core
from transpraxis import task_overview as to

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

_STYLE = re.compile(r"<style[\s\S]*?</style>", re.I)


def _function_source(name):
    """取 app.py 里某个顶层函数的源码（到下一个顶层 `def ` 为止）。

    AppTest 只能看到"页面上有哪些元素"，看不到容器嵌套。所以"这个入口挂在
    Banner 里还是工具栏里"这类结构约定只能钉在代码事实这一层；嵌套的 `def`
    都有缩进，`\\ndef ` 因此不会误切。
    """
    source = APP_PATH.read_text(encoding="utf-8")
    start = source.index(f"\ndef {name}(")
    body = source[start + 1:]
    end = body.find("\ndef ", 1)
    return body if end == -1 else body[:end]


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


def _interrupted_state():
    """有段落但译文为空、且没有 runtime_state.json：真实的中断/未完成形态。"""
    return {
        "p1_done": True,
        "p2_done": False,
        "stage": "TRANSLATING",
        "paras": ["First", "Second"],
        "pairs": [{"source": "First", "target": ""},
                  {"source": "Second", "target": ""}],
        "filename": "interrupted.docx",
        "findings": [],
        "review_evidence": [],
        "human_actions": [],
    }


def _save(job_id, state):
    core.save_job_state(job_id, state)
    core.save_source(job_id, b"Folith task banner fixture")


def _open_workspace(tmp_path, monkeypatch, job_id, state, section="translation"):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    _save(job_id, state)
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()
    at.session_state["active_job_id"] = job_id
    at.session_state["app_view"] = "workspace"
    at.session_state["workspace_mode"] = True
    at.session_state["workspace_section"] = section
    at.run()
    assert not at.exception, at.exception
    return at


def _markup(at):
    """注入的 <style> 里含界面文案与类名，做否定断言前必须先剥掉。"""
    return _STYLE.sub("", "\n".join(str(item.value) for item in at.markdown))


def _banner_markup(at):
    """只取 Banner 自己的那几个表面，避免正文里的同类文本混进来。"""
    return "\n".join(
        str(item.value) for item in at.markdown
        if "tp-workspace-verdict" in str(item.value)
        or "tp-workspace-status-detail" in str(item.value)
        or "tp-banner-metric" in str(item.value)
        or "tp-banner-runtime is-" in str(item.value))


def _buttons(at):
    return [button.label for button in at.button]


def _has_button(at, text):
    return any(text in label for label in _buttons(at))


def _banner_metrics(at):
    """Banner 指标行里的 (tone, 显示文字)，不含 title 提示语。"""
    return re.findall(r'class="tp-banner-metric is-([a-z]+)"[^>]*>([^<]+)</span>',
                      _banner_markup(at))


def _banner_metric_texts(at):
    return [text for _tone, text in _banner_metrics(at)]


# ---------------- acceptance ----------------

def test_unknown_section_degrades_to_the_translation_workbench(tmp_path, monkeypatch):
    """「概览」路由已经删除：旧 session 值必须掉到翻译工作台，而不是空白页。"""
    at = _open_workspace(tmp_path, monkeypatch, "bannerlegacy",
                         _state(2), section="overview")
    page = _markup(at)

    assert at.session_state["workspace_section"] == "translation"
    assert "tp-overview-hero" not in page
    assert "tp-stage-card" not in page
    assert "tp-overview-progress" not in page
    assert "查看概览" not in _buttons(at)


def test_the_banner_is_the_only_surface_stating_the_canonical_verdict(
        tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerone",
                         _state(1, review_required=True))
    state = core.load_job_state("bannerone")
    expected = to.derive_task_overview_state(state)
    page = _markup(at)

    assert page.count('class="tp-workspace-verdict is-') == 1, \
        "Banner 只允许有一个 canonical 状态 chip"
    assert page.count('class="tp-workspace-status-detail"') == 1
    assert expected["label"] in page
    assert f'title="{expected["detail"]}"' in page
    # 工具栏不再挂第二份 canonical chip（那是同一句话的第三次复述）。
    assert "tp-nav-canonical" not in page


def test_blocking_state_is_red_on_the_banner(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerred",
                         _state(1, targets=["TODO: replace before delivery"]))
    banner = _banner_markup(at)

    assert 'class="tp-workspace-verdict is-blocked"' in banner
    assert 'class="tp-banner-metric is-blocked"' in banner


def test_blocking_findings_replace_the_delivery_cta(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerblocking",
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
    at = _open_workspace(tmp_path, monkeypatch, "bannersuggestion", state)

    page = _markup(at)
    assert "建议" in page
    assert "0 项必须处理" in page
    assert "不会阻止交付" in page
    assert _has_button(at, "准备交付"), "只有建议时仍可进入交付准备"


def test_ready_for_delivery_prep_never_claims_final_delivery(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerready", _state(2))

    page = _markup(at)
    assert "可以准备交付" in page
    assert "Ready for delivery" not in page
    assert "可以正式交付" not in page
    assert "已交付" not in page


def test_review_disabled_shows_no_review_indicator_or_cta(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannernoreview",
                         _state(2, review_required=False))
    metrics = _banner_metric_texts(at)

    assert not any(text.startswith("审校") for text in metrics), \
        f"未启用独立审校时 Banner 不应挂审校指标：{metrics}"
    assert not _has_button(at, "查看审校")


def test_review_enabled_shows_the_review_indicator(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerreview",
                         _state(2, review_required=True))

    assert any(text.startswith("审校") for text in _banner_metric_texts(at))


def test_report_disabled_never_shows_an_active_report_cta(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannernoreport",
                         _state(2, report=False))

    assert not _has_button(at, "查看报告"), \
        "未启用研究报告时不允许出现查看报告 CTA"


def test_blocking_and_suggestion_are_separate_indicators(tmp_path, monkeypatch):
    """「必须处理 N」与「建议 N」是两个口径，不能合并成一个数字。"""
    at = _open_workspace(tmp_path, monkeypatch, "bannersplit",
                         _state(1, targets=["TODO: replace before delivery"]))
    metrics = _banner_metrics(at)

    assert ("blocked", "必须处理 1") in metrics, metrics
    assert not any(tone == "attention" and text.startswith("建议")
                   for tone, text in metrics), \
        "blocking 与 suggestion 是两种语义，不能都写成 is-attention"


def test_suggestion_only_job_has_no_blocking_indicator(tmp_path, monkeypatch):
    state = _state(1, targets=["短"])
    state["pairs"][0]["source"] = "A" * 200
    state["paras"] = ["A" * 200]
    at = _open_workspace(tmp_path, monkeypatch, "bannersuggestonly", state)
    metrics = _banner_metrics(at)

    assert not any(tone == "blocked" for tone, _text in metrics), \
        "只有建议时不得常驻一个红色的「必须处理」指标"
    assert any(text.startswith("建议") for _tone, text in metrics), metrics


def test_delivered_requires_a_real_snapshot(tmp_path, monkeypatch):
    """DELIVERED 只能来自真实冻结交付，不能凭 p2_done 自称"已交付"。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    job_id = "bannerdelivered"
    _save(job_id, _state(2))
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()
    at.session_state["active_job_id"] = job_id
    at.session_state["app_view"] = "workspace"
    at.session_state["workspace_mode"] = True
    at.session_state["workspace_section"] = "translation"
    at.run()
    assert not at.exception, at.exception
    assert "可以准备交付" in _markup(at)
    assert "已交付" not in _banner_markup(at)

    _, ok, errors = core.approve_delivery(job_id, note="task banner test")
    assert ok, errors
    at.run()
    assert not at.exception, at.exception
    page = _markup(at)
    assert "已交付" in page
    assert "冻结交付 v1" in page


def test_bare_state_still_gets_a_canonical_verdict(tmp_path, monkeypatch):
    """State 里没有报告/审校配置时也必须给出合法 canonical 状态。"""
    at = _open_workspace(tmp_path, monkeypatch, "bannerbare", {})

    assert "尚未开始" in _markup(at)


def test_delivery_page_headline_matches_the_canonical_state(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerdelivery",
                         _state(2), section="delivery")
    page = _markup(at)

    assert "tp-readiness-card is-success" in page
    assert "可以准备交付" in page
    assert "可以冻结交付" not in page, \
        "'可以准备交付' 不得被写成 '可以冻结交付'"


# ---------------- 运行控制（原概览页承载的动作） ----------------

def test_runtime_controls_are_visible_in_the_banner(tmp_path, monkeypatch):
    """中断/未完成的任务必须能在 Banner 上直接继续处理。

    这些动作原先由概览页承载；概览删除后它们不能连同页面一起消失，
    否则"已保存的进度"会变成用户无法触达的死数据。
    """
    at = _open_workspace(tmp_path, monkeypatch, "bannerruntime",
                         _interrupted_state(), section="overview")
    banner = _banner_markup(at)
    labels = _buttons(at)

    assert "tp-banner-runtime is-" in banner, "运行区必须在 Banner 内渲染"
    assert labels.count("继续处理") == 1, \
        f"「继续处理」只能出现一次（运行区提供）：{labels}"
    # 运行区给了主动作，Banner 不得再渲染第二个 canonical 主动作按钮。
    assert not any(str(button.key).startswith("workspace_topbar_cta_")
                   for button in at.button), \
        "运行区已经承担主动作时，Banner 不能再挂一个 CTA"


def test_runtime_details_open_in_drawer_and_technical_info_stays_collapsed(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerruntimedetails",
                         _interrupted_state())

    assert not any(expander.label == "运行详情" for expander in at.expander), \
        "运行详情不能继续使用 inline accordion"
    assert any(button.label.startswith("运行详情") for button in at.button)
    banner = _banner_markup(at)
    assert "worker id" not in banner and "checkpoint" not in banner

    next(button for button in at.button if button.label.startswith("运行详情")).click()
    at.run()
    assert not at.exception, at.exception
    drawer = _markup(at)
    assert "运行概要" in drawer
    assert "当前阶段" in drawer and "Pipeline" in drawer
    assert "最近活动" in drawer
    assert any(expander.label == "技术信息" for expander in at.expander)


def test_runtime_drawer_can_close_without_changing_workspace(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerruntimeclose",
                         _interrupted_state())
    next(button for button in at.button if button.label.startswith("运行详情")).click()
    at.run()
    assert "runtime_drawer_job_id" in at.session_state
    next(button for button in at.button if button.label == "关闭运行详情").click()
    at.run()
    assert "runtime_drawer_job_id" not in at.session_state
    assert not any(expander.label == "技术信息" for expander in at.expander)
    assert any("<h2>翻译</h2>" in str(item.value) for item in at.markdown)


def test_completed_task_has_no_runtime_row(tmp_path, monkeypatch):
    at = _open_workspace(tmp_path, monkeypatch, "bannerruntimeidle", _state(2))
    captions = " ".join(str(c.value) for c in at.caption)

    assert "tp-banner-runtime is-" not in _banner_markup(at)
    assert "worker id" not in captions
    assert not any(label == "继续处理" for label in _buttons(at))


# ---------------- 任务详情 ----------------

def test_task_details_expose_the_source_filename(tmp_path, monkeypatch):
    """完整文件名必须可读可复制，而不是只活在一个 hover 气泡里。"""
    state = _state(2)
    state["filename"] = "Part 3 提取自 The Sensorium of Animals.docx"
    at = _open_workspace(tmp_path, monkeypatch, "bannerdetails", state)

    code = " ".join(str(item.value) for item in at.code)
    assert "The Sensorium of Animals.docx" in code
    assert any(expander.label == "任务详情" for expander in at.expander)
    assert not any(expander.label == "项目详情" for expander in at.expander), \
        "同一个「任务详情」不应该以「项目详情」再复制一份"


def test_a_cleared_job_gets_no_resume_action(tmp_path, monkeypatch):
    """任务已被清掉后的空工作区不得挂出「继续处理」。

    `build_job_runtime_view` 对不存在的 job 会推出 `idle_incomplete`（读不到
    state 就判定业务未完成），于是一个空 shell 会显示可点的恢复按钮，
    并顺手把 canonical 主动作压掉——用户点下去也恢复不了任何东西。
    """
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()
    at.session_state["active_job_id"] = "cleared-job"
    at.session_state["app_view"] = "workspace"
    at.session_state["workspace_mode"] = True
    at.session_state["workspace_section"] = "translation"
    at.run()

    assert not at.exception, at.exception
    assert "还没有打开的任务" in _markup(at)
    assert "tp-banner-runtime is-" not in _banner_markup(at), \
        "空 shell 没有运行可恢复，不该渲染运行区"
    assert not any(label == "继续处理" for label in _buttons(at))


# ---------------- Banner 的两行契约 ----------------

def test_the_task_details_are_not_a_third_banner_row():
    """报告要求 Banner 是紧凑两行；「任务详情」是工具栏右端的入口。

    上一轮的 Banner 实际是**三行**（身份 / 指标 / 任务详情展开器）：一个低频
    入口每天都固定吃掉 42px + 上下间距。AppTest 看不到容器嵌套，所以这里钉
    调用关系——Banner 不再渲染它，工具栏渲染它。
    """
    topbar = _function_source("_render_workspace_topbar")
    nav = _function_source("_render_workspace_nav")

    assert "_workspace_task_details(" not in topbar, \
        "「任务详情」不能让 Banner 长出第三行"
    assert "_workspace_task_details(" in nav, \
        "「任务详情」必须挂在工具栏里，否则完整文件名就无处可看"


def test_the_toolbar_carries_page_navigation_only(tmp_path, monkeypatch):
    """UX-02：工具栏只保留当前页面导航。

    它一度还挂着「工作台」kicker 与 canonical status chip——前者在说"你在
    工作台里"（用户已经在里面了），后者是同一句交付判断的第三次复述。
    """
    at = _open_workspace(tmp_path, monkeypatch, "bannertoolbar", _state(1))
    page = _markup(at)

    assert "tp-workspace-toolbar-head" not in page
    assert "tp-workspace-nav-title" not in page
    assert "tp-nav-canonical" not in page


def test_the_translation_heading_is_not_padded_by_the_global_rule(
        tmp_path, monkeypatch):
    """`.tp-cat-title h2` 必须连 padding 一起重置，只重置 margin 不够。

    Streamlit 给标题带了 16px/16px 的默认 padding。作用域规则原来只写了
    `margin:0`，于是 `<h2>翻译</h2>` 的盒子实测 54px，而它只有 21.6px 的行内
    文字——整块正文头因此吃掉 60px，比 Banner 指标行还抢眼。这条断言守住
    "作用域规则要连 padding 一起重置"，否则下次重构又会静默地把它长回来。
    """
    at = _open_workspace(tmp_path, monkeypatch, "bannerheading", _state(2))
    css = "\n".join(_STYLE.findall(
        "\n".join(str(item.value) for item in at.markdown)))
    rule = re.search(r"\.tp-cat-title h2\s*\{([^}]*)\}", css)

    assert rule, "缺少 .tp-cat-title h2 作用域规则"
    declared = " ".join(rule.group(1).split()).replace(": ", ":")
    assert "padding:0 !important" in declared, \
        f"标题块会被 Streamlit 的默认 padding 撑高：{declared}"
