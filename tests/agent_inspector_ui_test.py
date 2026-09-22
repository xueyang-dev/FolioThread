"""Agent Inspector 工作区的结构回归。

这一版界面把"编辑译文"收敛到中央段落网格里，右栏改成只读的 Agent Inspector，
并新增了文档级 Agent 发现与四维进度。这里的断言守住这几个结构约定，
避免以后又长回"中间一列译文 + 右栏第二个编辑器"的重复状态。
"""
from pathlib import Path

import core
from transpraxis import assets

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _ui_state(count=6):
    state = core.new_job_state("sensorium-part3.pdf")
    pair_specs = [
        ("The sensorium of drones is volumetric and multispectral.",
         "无人机的感知中枢是体积化、多光谱的。"),
        ("Volumetric sensing and postcarbon communities [1] shift the frame.",
         "体积感知与后碳社区[1]改变了讨论框架。"),
        ("This chapter analyses the sensorium as a technical milieu.",
         "本章把感知中枢作为一种技术环境来分析。"),
        ("Drones flatten the earth with their aerial view from above.",
         "无人机以其高空俯视视角把地球压平。"),
        ("TODO: replace this placeholder before delivery.",
         "TODO：交付前替换这个占位内容。"),
        ("Earth-sensing drones monitor the surface and its in-between spaces.",
         "地球感知无人机监测地表及其间隙空间。"),
    ]
    pairs = []
    for index, (source, target) in enumerate(pair_specs[:count]):
        pairs.append({
            "source": source,
            "target": target,
            "initial_target": target,
            "reviewed": index in {0, 1},
            "from_tm": index == 3,
        })
    state.update(
        p1_done=True,
        p2_done=True,
        paras=[pair["source"] for pair in pairs],
        pairs=pairs,
        glossary=[{
            "id": "term-aerial",
            "source": "aerial view",
            "preferred": "鸟瞰视角",
            "target": "鸟瞰视角",
            "status": "locked",
        }],
        translation_core_review_required=False,
        delivery_status="draft",
    )
    return state


def _open_workspace(tmp_path, job_id):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP_PATH), default_timeout=40)
    at.run()
    at.session_state["active_job_id"] = job_id
    at.session_state["app_view"] = "workspace"
    at.session_state["workspace_mode"] = True
    at.session_state["workspace_section"] = "translation"
    at.run()
    assert not at.exception, at.exception
    return at


def _markdown(at):
    return "\n".join(str(item.value) for item in at.markdown)


def test_center_grid_is_the_only_translation_editor(tmp_path, monkeypatch):
    """中间网格即主编辑区：右栏不再出现第二个译文编辑器与"保存修改"。"""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    job_id = "agentinspector01"
    state = _ui_state()
    core.save_job_state(job_id, state)
    at = _open_workspace(tmp_path, job_id)

    # 每一行都有可编辑的译文框
    editor_keys = {area.key for area in at.text_area}
    for index in range(len(state["pairs"])):
        assert f"translation_editor_{assets.segment_id(job_id, index)}" in editor_keys
    # 但没有改动时完全不渲染保存操作：正常浏览状态不该有一列重复的"保存"按钮
    assert not any(str(button.key).startswith(f"cat_save_btn_{job_id}_")
                   for button in at.button), \
        "未修改的段落不应常驻保存按钮"
    assert "未保存" not in _markdown(at)

    # 旧的右栏编辑器与全局保存按钮必须消失
    assert not any(button.label == "保存修改" for button in at.button), \
        "右栏不应再出现第二个译文编辑器"
    assert not any(button.label == "重译" for button in at.button), \
        "重译应作为 Agent 动作出现，而不是并列的编辑器按钮"


def test_inspector_shows_segment_facts_and_agent_actions(tmp_path, monkeypatch):
    """右栏是 Inspector：段落事实 + Agent 动作 + 发现，而不是编辑器。"""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    job_id = "agentinspector02"
    core.save_job_state(job_id, _ui_state())
    at = _open_workspace(tmp_path, job_id)

    page = _markdown(at)
    assert "段落事实" in page, "Inspector 必须显示段落事实"
    # 有值的字段必须出现；没有值的字段不渲染，不显示比显示"—"更好。
    for label in ("状态", "术语"):
        assert any(label in item.value for item in at.markdown), \
            f"Inspector 缺少事实项：{label}"
    # 注意断言的是渲染出的 HTML——`at.markdown` 里也含 <style> 块，
    # 不能用整页文本判断"某词是否出现"。
    assert 'class="tp-inspector-facts-list"' in page
    # 这个夹具没有 sections，所以"章节"也必须消失——显示"章节 —"只是把
    # "我没有这个信息"画成一个占位符。
    for absent in ("人工修改", "AI 置信度", "章节"):
        assert f'<span>{absent}</span>' not in page, \
            f"没有值的字段不应渲染成空字段：{absent}"
    assert "Agent 动作" in page

    action_keys = {button.key for button in at.button}
    for action in ("rewrite", "faithful", "natural", "academic", "terms", "context"):
        assert any(str(key).startswith(f"translation_agent_{action}_")
                   for key in action_keys), f"缺少 Agent 动作：{action}"


def test_agent_findings_surface_document_level_issues(tmp_path, monkeypatch):
    """文档级 Agent 发现必须主动出现：术语不一致、占位符、引用缺失。"""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    job_id = "agentinspector03"
    state = _ui_state()
    core.save_job_state(job_id, state)
    at = _open_workspace(tmp_path, job_id)

    page = _markdown(at)
    assert "项发现" in page, "缺少 Agent 发现条"
    assert "aerial view" in page, "锁定的术语在原文出现但译文未采用时必须被指出"
    # 问题详情在右栏 Issues 抽屉里，锚点是按钮（不是 pills——pills 的选中值
    # 会在 rerun 后重放，是之前 rerun loop 的成因）。
    assert any(str(button.key) == f"agent_all_{job_id}" for button in at.button), \
        "issue bar 必须提供「查看全部」以打开问题抽屉"
    next(button for button in at.button if button.key == f"agent_all_{job_id}").click()
    at.run()
    assert not at.exception, at.exception
    anchors = [str(button.key) for button in at.button
               if str(button.key).startswith(f"issue_anchor_{job_id}_")]
    assert anchors, "问题抽屉必须提供可点击的段落锚点"


def test_progress_reports_four_dimensions_not_one_number(tmp_path, monkeypatch):
    """进度 = Translation / Terminology / Review / Issues，而不是单一 82/82。"""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    job_id = "agentinspector04"
    core.save_job_state(job_id, _ui_state())
    at = _open_workspace(tmp_path, job_id)

    page = _markdown(at)
    for metric in ("翻译", "术语已确认", "审校", "发现"):
        assert metric in page, f"进度缺少维度：{metric}"
    assert "不适用" in page, "未启用独立审校时必须如实标注不适用"


def test_header_is_compressed_and_keeps_delivery_verdict(tmp_path, monkeypatch):
    """顶栏只留文档身份 + 交付判断，不再堆四行元信息。"""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    job_id = "agentinspector05"
    core.save_job_state(job_id, _ui_state())
    at = _open_workspace(tmp_path, job_id)

    page = _markdown(at)
    assert 'class="tp-workspace-topbar"' in page
    assert "tp-workspace-verdict" in page, "顶栏必须保留一句交付判断"
    assert "FOLIOTHREAD · LONG-DOCUMENT TRANSLATION WORKSPACE" not in page, \
        "顶栏不应再重复产品标语"


def test_saving_from_the_grid_row_persists_and_clears_the_draft(
        tmp_path, monkeypatch):
    """行内保存：写入持久状态，并清掉草稿基线（不会残留"未保存"）。"""
    monkeypatch.setattr(core, "OUTPUT_DIR", tmp_path)
    job_id = "agentinspector06"
    core.save_job_state(job_id, _ui_state())
    at = _open_workspace(tmp_path, job_id)

    selected_id = assets.segment_id(job_id, 0)
    editor_key = f"translation_editor_{selected_id}"
    at.session_state[editor_key] = "保存后的第一段译文"
    at.run()
    # 内容变化后，"未保存 + 保存"才浮现出来
    assert not at.exception, at.exception
    assert any(button.key == f"cat_save_btn_{job_id}_0" for button in at.button), \
        "有未保存改动时必须出现保存操作"
    next(button for button in at.button
         if button.key == f"cat_save_btn_{job_id}_0").click()
    at.run()
    assert not at.exception, at.exception

    updated = core.load_job_state(job_id)
    assert updated["pairs"][0]["target"] == "保存后的第一段译文"
    assert updated["pairs"][0]["human_edited"] is True
    assert any("已修改" in item.value for item in at.success)
    # 保存后草稿被丢弃、基线重建为新的已保存值：行内状态回到"已翻译"而不是"未保存"
    refreshed = next(area for area in at.text_area if area.key == editor_key)
    assert refreshed.value == "保存后的第一段译文"
    assert at.session_state[f"cat_baseline_{editor_key}"] == "保存后的第一段译文"
    assert "未保存" not in _markdown(at)
    assert not any(button.key == f"cat_save_btn_{job_id}_0" for button in at.button), \
        "保存完成后行内操作应当消失"
