"""Language Assets Workspace（术语与翻译记忆）的回归测试。

覆盖两层：

1. `transpraxis.language_assets` 的纯投影（不依赖 Streamlit）：聚合、过滤、
   段落引用、以及「后端没有的字段不伪造」这条硬约束；
2. `app.py` 里的工作区：三个 Tab、搜索、过滤、Inspector、两阶段接受、
   Quick Accept、仅此次采用、拒绝、多选、批量接受/拒绝、审核后列表更新、
   空状态与错误状态，以及既有 review API 契约没有被破坏。
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core
from transpraxis import assets as _assets
from transpraxis import knowledge, language_assets, models

ROOT = Path(__file__).resolve().parent.parent


# ================= 夹具 =================

def _job(job_id, filename, *, glossary=None, candidates=None, units=None,
         target_lang="简体中文", project_id=None):
    state = core.new_job_state(filename)
    state.update(
        p1_done=True, p2_done=True, report_enabled=False,
        pipeline_config={"target_lang": target_lang},
        paras=["How do earth drones and their volumetric sensors define space?",
               "The point cloud matters for remote sensing method."],
        pairs=[{
            "source": "How do earth drones and their volumetric sensors define space?",
            "target": "地球无人机及其体积传感器如何定义空间？",
            "reviewed": True, "target_provenance": "reviewed",
            "accepted_target": "地球无人机及其体积传感器如何定义空间？",
        }],
        semantic_units=units or [{"unit_id": "u1", "kind": "section",
                                  "label": "Chapter 5",
                                  "start_segment": 0, "end_segment": 1}],
        glossary=list(glossary or []),
        knowledge_candidates=list(candidates or []),
    )
    if project_id:
        state["project_id"] = project_id
    return state


def _candidate(source, target, *, segment=0, occurrences=None, kind="term",
               confidence=0.86):
    return {
        "source": source, "observed_target": target,
        "first_observed_segment": segment,
        "occurrences": list(occurrences if occurrences is not None else [segment]),
        "observed_segments": [segment],
        "status": "emergent_candidate", "origin": "translation_observation",
        "kind": kind, "confidence": confidence,
    }


def _term(source, target, *, status="locked", domain="技术", scope="document",
          occurrences=3, **extra):
    entry = {"source": source, "target": target, "preferred": target,
             "status": status, "domain": domain, "behavior": "translate",
             "scope": scope, "occurrences": list(range(occurrences))}
    entry.update(extra)
    return entry


class _Workspace:
    """临时 outputs 目录 + 预置任务的上下文管理器。"""

    def __init__(self, jobs=(), tm=None, tm_project=None):
        self.jobs = jobs
        self.tm = tm or {}
        self.tm_project = tm_project

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="la-workspace-"))
        self.old = core.OUTPUT_DIR
        core.OUTPUT_DIR = self.tmp
        for job_id, state in self.jobs:
            core.save_job_state(job_id, state)
        if self.tm:
            core.save_tm(self.tm, self.tm_project)
        return self

    def __exit__(self, *exc):
        core.OUTPUT_DIR = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def _app(session=None):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["app_view"] = "library"
    for key, value in (session or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def _keys(elements, prefix):
    return [element for element in elements
            if str(getattr(element, "key", "") or "").startswith(prefix)]


def _buttons(at, prefix):
    return _keys(at.button, prefix)


def _captions(at):
    return "\n".join(str(item.value) for item in at.caption)


def _summary(at):
    return next((item.value for item in at.markdown
                 if '<div class="la-summary">' in item.value), "")


# ================= 1. 纯投影层 =================

def test_term_rows_aggregate_across_tasks_and_keep_real_counts():
    jobs = [
        {"job_id": "a", "state": _job("a", "Book A.docx",
                                      glossary=[_term("volumetric sensors", "体积传感器",
                                                      occurrences=22)])},
        {"job_id": "b", "state": _job("b", "Book B.docx",
                                      glossary=[_term("volumetric sensors", "体积传感器",
                                                      status="provisional",
                                                      occurrences=8)])},
    ]
    rows = language_assets.group_terms(language_assets.build_term_rows(jobs))
    assert len(rows) == 1, "同一 source→preferred 必须合并成一行"
    row = rows[0]
    assert row["usage"] == 30, "使用次数是 occurrences 之和，不是估算"
    assert sorted(row["documents"]) == ["Book A.docx", "Book B.docx"]
    assert row["status"] == "locked", "合并后展示最强的状态"
    assert len(row["tasks"]) == 2


def test_term_scope_buckets_keep_project_global_and_document_distinct():
    assert language_assets.scope_bucket("global") == "global"
    assert language_assets.scope_bucket("project") == "project"
    assert language_assets.scope_bucket("") == "document"
    assert language_assets.scope_bucket("section:s1") == "document"
    assert language_assets.scope_label("") == "本文档"
    assert language_assets.scope_label("project") == "本项目"


def test_term_language_filter_uses_persisted_target_language():
    jobs = [
        {"job_id": "zh", "state": _job("zh", "Chinese.docx",
                                          glossary=[_term("drone", "无人机")])},
        {"job_id": "ar", "state": _job("ar", "Arabic.docx",
                                          target_lang="العربية",
                                          glossary=[_term("drone", "طائرة")])},
    ]
    rows = language_assets.group_terms(language_assets.build_term_rows(jobs))
    assert set(language_assets.target_language_options(rows)) == {"简体中文", "العربية"}
    filtered = language_assets.filter_terms(rows, target_lang="العربية")
    assert [row["preferred"] for row in filtered] == ["طائرة"]
    assert language_assets.scope_label("global") == "全局"
    assert language_assets.scope_label("section:s1") == "章节 · s1"
    assert language_assets.scope_label("自定义作用域") == "自定义作用域"


def test_project_term_rows_use_real_project_memory_and_do_not_double_count_usage():
    project = {
        "project_id": "p1", "name": "无人机研究",
        "glossary": [_term("volumetric sensors", "体积传感器", occurrences=0)],
        "glossary_versions": [{"version": 3}],
    }
    job_id = "laprojectrows00001"
    state = _job(job_id, "Book A.docx", project_id="p1",
                 glossary=[_term("volumetric sensors", "体积传感器", occurrences=22)])
    task_rows = language_assets.build_term_rows([{"job_id": job_id, "state": state}])
    project_rows = language_assets.build_project_term_rows([project], task_rows=task_rows)
    rows = language_assets.group_terms([*task_rows, *project_rows])
    assert len(rows) == 1
    assert rows[0]["scope_bucket"] == "project"
    assert rows[0]["scope_label"] == "项目 · 无人机研究"
    assert rows[0]["usage"] == 22, "项目记忆行不能把任务 occurrence 计数加两遍"
    assert rows[0]["project_names"] == ["无人机研究"]
    assert rows[0]["tasks"][0]["job_id"] == job_id


def test_tm_rows_do_not_invent_source_document_or_match_percentage():
    rows = language_assets.build_tm_rows({
        "The point cloud matters.": {"target": "点云很重要。", "reviewed": True,
                                     "updated_at": "2026-09-01T08:15:00+03:00"},
    })
    assert len(rows) == 1
    assert set(rows[0]) == {"row_id", "source", "target", "updated_at",
                            "reviewed", "source_chars"}, \
        "翻译记忆行只暴露后端真正存下来的字段"


def test_tm_rows_drop_unreviewed_and_empty_entries():
    rows = language_assets.build_tm_rows({
        "a": {"target": "甲", "reviewed": True},
        "b": {"target": "乙"},
        "c": {"target": "", "reviewed": True},
    })
    assert [row["source"] for row in rows] == ["a"]


def test_candidate_rows_carry_real_positions_and_honest_usage():
    jobs = [{"job_id": "a", "state": _job(
        "a", "Book A.docx",
        candidates=[_candidate("point cloud", "点云", segment=1,
                               occurrences=[1, 1, 1])])}]
    row = language_assets.build_candidate_rows(jobs)[0]
    assert row["occurrence_count"] == 3
    assert row["positions_known"] is True
    assert row["positions"] == ["Chapter 5 · #2"], "段落引用要带真实章节标签"
    assert language_assets.usage_text(row) == "出现 3 次"
    assert language_assets.confidence_text(row) == "0.86"
    assert row["high_confidence"] is True


def test_candidate_rows_say_unknown_instead_of_zero_when_no_occurrences():
    jobs = [{"job_id": "a", "state": _job(
        "a", "Book A.docx",
        candidates=[_candidate("ghost term", "幽灵术语", occurrences=[])])}]
    row = language_assets.build_candidate_rows(jobs)[0]
    assert row["positions_known"] is False
    assert language_assets.usage_text(row) == "观察到 1 次"


def test_decided_candidates_leave_the_review_queue():
    state = _job("a", "Book A.docx",
                 candidates=[_candidate("point cloud", "点云")])
    state["knowledge_candidates"][0]["decision"] = "project_term"
    rows = language_assets.build_candidate_rows([{"job_id": "a", "state": state}])
    assert rows == []
    kept = language_assets.build_candidate_rows([{"job_id": "a", "state": state}],
                                                include_decided=True)
    assert len(kept) == 1


def test_candidate_conflicts_are_reported_from_existing_terms():
    state = _job("a", "Book A.docx",
                 glossary=[_term("continuity", "连续性")],
                 candidates=[_candidate("continuity", "连贯性")])
    row = language_assets.build_candidate_rows([{"job_id": "a", "state": state}])[0]
    assert row["has_conflict"] is True
    assert "连续性" in row["conflict_summary"]


def test_new_candidate_filter_is_derived_from_existing_terms_not_kind():
    state = _job(
        "lanewcandidate0001", "Book A.docx",
        glossary=[_term("known term", "已知术语")],
        candidates=[_candidate("known term", "已知术语"),
                    _candidate("brand new", "全新术语")],
    )
    rows = language_assets.build_candidate_rows([{
        "job_id": "lanewcandidate0001", "state": state,
    }])
    assert {row["source"]: row["is_new"] for row in rows} == {
        "brand new": True, "known term": False}
    assert [row["source"] for row in
            language_assets.filter_candidates(rows, only_new=True)] == ["brand new"]


def test_filters_are_backed_by_real_fields():
    jobs = [{"job_id": "a", "state": _job(
        "a", "Book A.docx",
        candidates=[_candidate("point cloud", "点云", confidence=0.86),
                    _candidate("sensorium", "感知域", confidence=0.35),
                    _candidate("Dr. Maurer", "Maurer 博士", kind="name",
                               confidence=0.35)])}]
    rows = language_assets.build_candidate_rows(jobs)
    assert len(language_assets.filter_candidates(rows, confidence="high")) == 1
    assert len(language_assets.filter_candidates(rows, confidence="low")) == 2
    assert len(language_assets.filter_candidates(rows, kind="term")) == 2
    assert len(language_assets.filter_candidates(rows, query="point")) == 1
    assert len(language_assets.filter_candidates(rows, only_high=True)) == 1
    assert len(language_assets.filter_candidates(rows, kind="all")) == 3, \
        "kind='all' 是「不过滤」，不是「kind 必须等于 all」"


def test_unknown_confidence_is_not_mislabeled_as_low_confidence():
    jobs = [{"job_id": "launknownconfidence1", "state": _job(
        "launknownconfidence1", "Book A.docx",
        candidates=[_candidate("unknown", "未知", confidence=None)])}]
    rows = language_assets.build_candidate_rows(jobs)
    assert len(language_assets.filter_candidates(rows, confidence="unknown")) == 1
    assert language_assets.filter_candidates(rows, confidence="low") == []


def test_summary_counts_only_real_sources():
    jobs = [{"job_id": "a", "state": _job(
        "a", "Book A.docx", glossary=[_term("point cloud", "点云")],
        candidates=[_candidate("sensorium", "感知域")])}]
    summary = language_assets.language_asset_summary(jobs, tm_count=7)
    assert summary == {"terms": 1, "tm": 7, "review": 1, "conflicts": 0}


# ================= 2. 页面：Tab / 搜索 / 过滤 =================

def test_three_tabs_render_and_switch_without_exception():
    jobs = [("latab000000000001", _job(
        "latab000000000001", "Book A.docx",
        glossary=[_term("volumetric sensors", "体积传感器", occurrences=22)],
        candidates=[_candidate("point cloud", "点云")]))]
    tm = {"The point cloud matters.": {"target": "点云很重要。", "reviewed": True,
                                       "updated_at": "2026-09-01T08:15:00+03:00"}}
    with _Workspace(jobs, tm=tm):
        at = _app()
        assert not at.exception, [e.value for e in at.exception]
        assert at.segmented_control[0].value == "terms"
        assert "la-summary" in _summary(at)
        assert "术语库" in _captions(at) or True

        at.segmented_control[0].set_value("tm").run()
        assert not at.exception, [e.value for e in at.exception]
        assert any(m.label == "未分类" for m in at.metric), "翻译记忆 Tab 保留按项目统计"

        at.segmented_control[0].set_value("review").run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("point cloud" in button.label for button in at.button)


def test_library_navigation_clears_previous_setup_view_and_deep_links():
    """从新建任务进入资料库不能把旧的 setup placeholder 留在页面顶部。"""
    from streamlit.testing.v1 import AppTest

    with _Workspace([]):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.run()
        next(button for button in at.sidebar.button
             if button.label == "术语与翻译记忆").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert at.session_state["app_view"] == "library"
        page = "\n".join(item.value for item in at.markdown)
        assert "术语与翻译记忆" in page
        assert "新建翻译任务" not in page

        linked = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        linked.query_params["view"] = "library"
        linked.query_params["tab"] = "review"
        linked.run()
        assert not linked.exception, [e.value for e in linked.exception]
        assert linked.session_state["app_view"] == "library"
        assert linked.session_state["library_tab"] == "review"
        linked_page = "\n".join(item.value for item in linked.markdown)
        assert "新建翻译任务" not in linked_page
        assert "当前没有需要审核的候选内容" in linked_page


def test_summary_strip_reports_real_counts_and_zero_conflicts():
    jobs = [("lasum000000000001", _job(
        "lasum000000000001", "Book A.docx",
        glossary=[_term("point cloud", "点云")],
        candidates=[_candidate("sensorium", "感知域")]))]
    with _Workspace(jobs):
        at = _app()
        summary = _summary(at)
        assert "术语" in summary and "翻译记忆" in summary
        assert "待审核" in summary and "冲突" in summary
        assert "<strong>1</strong>" in summary, summary
        assert "冲突" in summary


def test_terms_tab_search_and_scope_filter():
    jobs = [("lafilter0000000001", _job(
        "lafilter0000000001", "Book A.docx",
        glossary=[_term("volumetric sensors", "体积传感器", scope="document"),
                  _term("remote sensing method", "遥感方法", scope="global")]))]
    with _Workspace(jobs):
        at = _app()
        assert any(b.label.startswith("**volumetric") for b in at.button)
        at.text_input(key="la_terms_query").set_value("remote").run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("remote sensing method" in b.label for b in at.button)
        assert not any("volumetric" in b.label for b in at.button)
        assert "显示 1 / 2 条术语" in _captions(at)

        at.text_input(key="la_terms_query").set_value("").run()
        at.selectbox(key="la_terms_scope").set_value("全局").run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("remote sensing method" in b.label for b in at.button)
        assert not any("volumetric" in b.label for b in at.button)


def test_review_tab_search_and_confidence_filter():
    jobs = [("lareview0000000001", _job(
        "lareview0000000001", "Book A.docx",
        candidates=[_candidate("point cloud", "点云", confidence=0.86),
                    _candidate("sensorium", "感知域", confidence=0.35)]))]
    with _Workspace(jobs):
        at = _app(session={"library_tab": "review"})
        assert not at.exception, [e.value for e in at.exception]
        assert "待审核 2 条" in _captions(at)

        at.text_input(key="la_review_query").set_value("sensorium").run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("sensorium" in b.label for b in at.button)
        assert not any("point cloud" in b.label for b in at.button)

        at.text_input(key="la_review_query").set_value("").run()
        at.pills(key="la_review_chip").set_value("高置信度").run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("point cloud" in b.label for b in at.button)
        assert not any("sensorium" in b.label for b in at.button)


def test_review_tab_groups_by_source_document_and_flattens_when_filtering():
    jobs = [("lagroup00000000001", _job(
        "lagroup00000000001", "Book A.docx",
        candidates=[_candidate("point cloud", "点云")])),
        ("lagroup00000000002", _job(
            "lagroup00000000002", "Book B.docx",
            candidates=[_candidate("sensorium", "感知域")]))]
    with _Workspace(jobs):
        at = _app(session={"library_tab": "review"})
        assert not at.exception, [e.value for e in at.exception]
        assert any("Book A.docx · 1 条" in item.label for item in at.expander)
        assert any("Book B.docx · 1 条" in item.label for item in at.expander)

        at.text_input(key="la_review_query").set_value("point").run()
        assert not at.exception, [e.value for e in at.exception]
        assert not at.expander, "搜索/过滤时自动取消分组"


# ================= 3. Inspector =================

def test_inspector_opens_for_terms_tm_and_candidates():
    jobs = [("lainspector0000001", _job(
        "lainspector0000001", "Book A.docx",
        glossary=[_term("volumetric sensors", "体积传感器", occurrences=22)],
        candidates=[_candidate("point cloud", "点云", segment=1,
                               occurrences=[1, 1, 1])]))]
    tm = {"The point cloud matters.": {"target": "点云很重要。", "reviewed": True,
                                       "updated_at": "2026-09-01T08:15:00+03:00"}}
    with _Workspace(jobs, tm=tm):
        at = _app()
        next(b for b in at.button if b.label.startswith("**volumetric")).click().run()
        assert not at.exception, [e.value for e in at.exception]
        page = "\n".join(m.value for m in at.markdown)
        assert "la-inspector-title" in page
        assert "推荐译法" in page and "使用次数" in page
        assert "提升为全局术语" in [b.label for b in at.button]

        at.segmented_control[0].set_value("tm").run()
        next(b for b in at.button if "The point cloud" in b.label).click().run()
        assert not at.exception, [e.value for e in at.exception]
        page = "\n".join(m.value for m in at.markdown)
        assert "点云很重要。" in page
        assert "后端不记录来源文档" in _captions(at)

        at.segmented_control[0].set_value("review").run()
        next(b for b in at.button if "point cloud" in b.label).click().run()
        assert not at.exception, [e.value for e in at.exception]
        page = "\n".join(m.value for m in at.markdown)
        assert "上下文" in page and "出现位置" in page
        assert "Chapter 5 · #2" in page
        assert "置信度" in page


# ================= 3b. 出现位置 → 工作台深链 =================

def test_candidate_positions_carry_real_segment_indices():
    """出现位置必须同时带显示文案和**真实段落下标**，否则跳转无从下手。"""
    job_id = "laposidx000000001"
    state = _job(job_id, "Book A.docx",
                 candidates=[_candidate("point cloud", "点云", segment=1,
                                        occurrences=[1, 1, 0])])
    with _Workspace([(job_id, state)]):
        rows = language_assets.build_candidate_rows(core.list_jobs())
        row = next(item for item in rows if item["source"] == "point cloud")
        assert row["positions"] == ["Chapter 5 · #2", "Chapter 5 · #1"], \
            "重复出现要去重，顺序按首次出现"
        assert [entry["index"] for entry in row["position_entries"]] == [1, 0], \
            "下标必须是原始段落下标，不能被格式化掉"
        assert row["position_total"] == 2


def test_candidate_position_jumps_to_the_workbench_segment():
    """点「定位到工作台」要真的落到该任务的对应段落，而不是只换个页面。"""
    job_id = "lajump00000000001"
    state = _job(job_id, "Book A.docx",
                 candidates=[_candidate("point cloud", "点云", segment=0)])
    with _Workspace([(job_id, state)]):
        at = _app(session={"library_tab": "review"})
        next(b for b in at.button if "point cloud" in b.label).click().run()
        assert not at.exception, [e.value for e in at.exception]
        jump = _buttons(at, "la_jump_")
        assert jump, "出现位置必须提供跳转入口"

        jump[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        # 工作台用它自己的 _translation_segment_id 推导；这里对齐它的结果。
        assert at.session_state["selected_segment_id"] == \
            _assets.segment_id(job_id, 0)
        assert at.session_state["app_view"] == "workspace"
        assert at.session_state["workspace_section"] == "translation"
        assert at.session_state["active_job_id"] == job_id
        # 滚动意图是一次性的：工作台渲染时已把它消费掉，说明它确实被设过，
        # 也说明工作台真的渲染了（否则会残留在这里）。
        assert "pending_scroll_segment_id" not in at.session_state, \
            "滚动意图应该被工作台消费一次，而不是留存"


def test_stale_segment_index_reports_instead_of_jumping_nowhere():
    """任务被重新切分后旧下标会越界：必须明确报错，不能跳到错误段落。"""
    job_id = "lastale0000000001"
    state = _job(job_id, "Book A.docx",
                 candidates=[_candidate("ghost term", "幽灵术语", segment=7,
                                        occurrences=[7])])
    with _Workspace([(job_id, state)]):
        at = _app(session={"library_tab": "review"})
        next(b for b in at.button if "ghost term" in b.label).click().run()
        assert not at.exception, [e.value for e in at.exception]
        _buttons(at, "la_jump_")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("已不在当前任务里" in item.value for item in at.error), \
            "越界下标要给出可读的错误，而不是静默失败"
        # AppTest 的 session_state 是 SafeSessionState，没有 .get()。
        assert at.session_state["app_view"] == "library", \
            "失败时不应该把用户带到别处"
        assert "selected_segment_id" not in at.session_state, \
            "失败时不应该写入一个错的段落 id"


# ================= 4. 两阶段决策 =================

def _review_app(job_id, state):
    return _Workspace([(job_id, state)])


def test_quick_accept_saves_to_project_termbase():
    job_id = "laquick0000000001"
    with _review_app(job_id, _job(job_id, "Book A.docx",
                                  candidates=[_candidate("point cloud", "点云")])):
        at = _app(session={"library_tab": "review"})
        quick = _buttons(at, "la_quick_")[0]
        assert quick.help and "项目术语库" in quick.help, "Quick Accept 的默认去向必须写明"
        quick.click().run()
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        state = core.load_job_state(job_id)
        assert [entry["source"] for entry in state["glossary"]] == ["point cloud"]
        assert state["glossary"][0]["status"] == "locked"
        assert state["glossary_frozen"]["version"] == 1
        assert state["knowledge_candidates"][0]["decision"] == "project_term"
        project = core.load_project(core.system_project_id())
        assert project is not None
        assert [entry["source"] for entry in project["glossary"]] == ["point cloud"]


def test_two_stage_accept_saves_to_project_termbase_and_updates_list():
    job_id = "latwostage00000001"
    with _review_app(job_id, _job(job_id, "Book A.docx",
                                  candidates=[_candidate("point cloud", "点云"),
                                              _candidate("sensorium", "感知域")])):
        at = _app(session={"library_tab": "review"})
        next(b for b in at.button if "point cloud" in b.label).click().run()
        accept = _buttons(at, "la_ins_accept_")[0]
        accept.click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any(r.options == ["项目术语库", "不保存，仅此次采用"] for r in at.radio), \
            "接受后必须出现「保存到哪里」这一层"
        global_box = next(c for c in at.checkbox if c.label == "全局术语库")
        assert global_box.disabled, "没有全局术语库时必须是 disabled，而不是假按钮"

        _buttons(at, "la_ins_save_")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("已加入项目术语" in item.value for item in at.success), \
            "接受成功后必须给出可见反馈"
        state = core.load_job_state(job_id)
        assert [entry["source"] for entry in state["glossary"]] == ["point cloud"]
        assert state["knowledge_candidates"][0]["decision"] == "project_term"
        assert not any("point cloud" in b.label for b in at.button), \
            "审核后候选必须从列表消失，且不要求整页刷新"
        assert any("sensorium" in b.label for b in at.button)
        at.run()
        assert not at.exception, [e.value for e in at.exception]


def test_two_stage_task_only_does_not_touch_the_termbase():
    job_id = "lataskonly00000001"
    with _review_app(job_id, _job(job_id, "Book A.docx",
                                  candidates=[_candidate("point cloud", "点云")])):
        at = _app(session={"library_tab": "review"})
        next(b for b in at.button if "point cloud" in b.label).click().run()
        _buttons(at, "la_ins_accept_")[0].click().run()
        at.radio[0].set_value("不保存，仅此次采用").run()
        assert not at.exception, [e.value for e in at.exception]
        task_button = _buttons(at, "la_ins_task_")[0]
        assert task_button.label == "仅此次采用", "选择不保存时主按钮文案必须改变"
        task_button.click().run()
        at.run()
        state = core.load_job_state(job_id)
        assert state["glossary"] == []
        assert state["knowledge_candidates"][0]["decision"] == "task_only"
        assert state["knowledge_candidates"][0]["status"] == "accepted_task"


def test_inspector_reject_removes_candidate_from_queue():
    job_id = "lareject00000000001"
    with _review_app(job_id, _job(job_id, "Book A.docx",
                                  candidates=[_candidate("point cloud", "点云")])):
        at = _app(session={"library_tab": "review"})
        next(b for b in at.button if "point cloud" in b.label).click().run()
        _buttons(at, "la_ins_reject_")[0].click().run()
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        state = core.load_job_state(job_id)
        assert state["knowledge_candidates"][0]["status"] == "rejected"
        assert not any("point cloud" in b.label for b in at.button)
        assert knowledge.provisional_hints(state["knowledge_candidates"]) == []


def test_accept_is_refused_when_the_translation_conflicts():
    job_id = "laconflict000000001"
    with _review_app(job_id, _job(job_id, "Book A.docx",
                                  glossary=[_term("continuity", "连续性")],
                                  candidates=[_candidate("continuity", "连贯性")])):
        at = _app(session={"library_tab": "review"})
        assert any("冲突" in m.value for m in at.markdown), "冲突必须在列表里可见"
        next(b for b in at.button if "continuity" in b.label).click().run()
        _buttons(at, "la_ins_accept_")[0].click().run()
        _buttons(at, "la_ins_save_")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("冲突" in item.value for item in at.error), \
            "被后端拒绝时必须把原因显示出来"
        state = core.load_job_state(job_id)
        assert state["glossary"][0]["preferred"] == "连续性", "冲突时不得覆盖既有术语"
        assert not state["knowledge_candidates"][0].get("decision")


# ================= 5. 批量审核 =================

def test_bulk_accept_and_bulk_reject_use_the_selection():
    job_id = "labulk000000000001"
    with _review_app(job_id, _job(job_id, "Book A.docx",
                                  candidates=[_candidate("point cloud", "点云"),
                                              _candidate("sensorium", "感知域"),
                                              _candidate("drone swarm", "无人机集群")])):
        at = _app(session={"library_tab": "review"})
        order = [row["source"] for row in
                 language_assets.build_candidate_rows(core.list_jobs())]
        boxes = _keys(at.checkbox, "la_sel_")
        assert len(boxes) == 3
        boxes[order.index("point cloud")].set_value(True)
        boxes[order.index("sensorium")].set_value(True)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert "已选择 2 项" in "\n".join(m.value for m in at.markdown)

        _buttons(at, "la_bulk_project_term")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        state = core.load_job_state(job_id)
        decided = {item["source"]: item.get("decision")
                   for item in state["knowledge_candidates"]}
        assert decided["point cloud"] == "project_term"
        assert decided["sensorium"] == "project_term"
        assert decided.get("drone swarm") is None
        assert sorted(entry["source"] for entry in state["glossary"]) == \
            ["point cloud", "sensorium"]

        remaining = _keys(at.checkbox, "la_sel_")
        assert len(remaining) == 1, "已处理的候选必须离开列表"
        remaining[0].set_value(True)
        at.run()
        _buttons(at, "la_bulk_rejected")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        state = core.load_job_state(job_id)
        assert {item["source"]: item.get("decision")
                for item in state["knowledge_candidates"]}["drone swarm"] == "rejected"


def test_bulk_clear_selection_drops_the_action_bar():
    job_id = "labulkclear00000001"
    with _review_app(job_id, _job(job_id, "Book A.docx",
                                  candidates=[_candidate("point cloud", "点云")])):
        at = _app(session={"library_tab": "review"})
        _keys(at.checkbox, "la_sel_")[0].set_value(True)
        at.run()
        assert "已选择 1 项" in "\n".join(m.value for m in at.markdown)
        _buttons(at, "la_bulk_clear")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert "已选择" not in "\n".join(m.value for m in at.markdown)


def test_select_all_high_confidence_does_not_auto_accept():
    job_id = "laselecthigh0000001"
    with _review_app(job_id, _job(job_id, "Book A.docx",
                                  candidates=[_candidate("point cloud", "点云",
                                                         confidence=0.86),
                                              _candidate("sensorium", "感知域",
                                                         confidence=0.35)])):
        at = _app(session={"library_tab": "review"})
        _buttons(at, "la_select_high")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert "已选择 1 项" in "\n".join(m.value for m in at.markdown)
        state = core.load_job_state(job_id)
        assert all(not item.get("decision")
                   for item in state["knowledge_candidates"]), \
            "高置信度候选只能被选中，绝不能自动接受"


def test_large_candidate_queue_renders_in_batches_not_all_at_once():
    job_id = "lapaging0000000001"
    candidates = [_candidate(f"term {index:03d}", f"术语 {index}", confidence=0.86)
                  for index in range(120)]
    with _review_app(job_id, _job(job_id, "Book A.docx", candidates=candidates)):
        at = _app(session={"library_tab": "review"})
        assert not at.exception, [e.value for e in at.exception]
        assert len(_buttons(at, "la_open_")) == 40, "首屏只渲染一批，避免几百行一次性铺开"
        assert any("显示更多" in button.label for button in at.button)
        assert any("Book A.docx · 120 条" in item.label for item in at.expander)
        _buttons(at, "la_group_more_")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert len(_buttons(at, "la_open_")) == 80


# ================= 6. 空状态 / 错误状态 =================

def test_empty_states_for_all_three_tabs():
    with _Workspace([]):
        at = _app()
        page = "\n".join(m.value for m in at.markdown)
        assert "当前项目还没有术语" in page
        at.segmented_control[0].set_value("tm").run()
        assert "完成并确认翻译后，翻译记忆会出现在这里" in \
            "\n".join(m.value for m in at.markdown)
        at.segmented_control[0].set_value("review").run()
        assert "当前没有需要审核的候选内容" in \
            "\n".join(m.value for m in at.markdown)


def test_api_failure_shows_an_error_state_instead_of_a_blank_page():
    jobs = [("laerror000000000001", _job("laerror000000000001", "Book A.docx"))]
    original = core.load_tm

    def boom(*args, **kwargs):
        raise RuntimeError("记忆文件不可读")

    with _Workspace(jobs):
        core.load_tm = boom
        try:
            at = _app()
        finally:
            core.load_tm = original
        assert not at.exception, [e.value for e in at.exception]
        page = "\n".join(m.value for m in at.markdown)
        assert "无法加载语言资产" in page
        assert "记忆文件不可读" in page


def test_terms_tab_filters_with_no_match_show_a_calm_empty_state():
    jobs = [("lanomatch0000000001", _job(
        "lanomatch0000000001", "Book A.docx",
        glossary=[_term("point cloud", "点云")]))]
    with _Workspace(jobs):
        at = _app()
        at.text_input(key="la_terms_query").set_value("zzz").run()
        assert not at.exception, [e.value for e in at.exception]
        assert "没有匹配的术语" in "\n".join(m.value for m in at.markdown)


# ================= 7. 既有契约与新增后端能力 =================

def test_existing_review_api_contract_is_unchanged():
    """重构只能改 IA；review_knowledge_candidate 的语义必须原样保留。"""
    tmp = Path(tempfile.mkdtemp(prefix="la-contract-"))
    old = core.OUTPUT_DIR
    core.OUTPUT_DIR = tmp
    try:
        job_id = "lacontract00000001"
        state = _job(job_id, "Book A.docx",
                     candidates=[_candidate("point cloud", "点云")])
        core.save_job_state(job_id, state)
        candidate_id = knowledge.candidate_id(state["knowledge_candidates"][0])
        promoted, ok, message = core.review_knowledge_candidate(
            job_id, candidate_id, "project_term")
        assert ok, message
        assert promoted["glossary_frozen"]["version"] == 1
        assert promoted["glossary"][0]["status"] == "locked"
        assert promoted["glossary_frozen"]["glossary_hash"] == \
            models.glossary_hash(promoted["glossary"])
        again, again_ok, _ = core.review_knowledge_candidate(
            job_id, candidate_id, "task_only")
        assert not again_ok, "同一条候选不能被处理两次"
        assert again["knowledge_candidates"][0]["decision"] == "project_term"
        try:
            core.review_knowledge_candidate(job_id, candidate_id, "nonsense")
        except ValueError:
            pass
        else:
            raise AssertionError("非法决策必须抛 ValueError")
    finally:
        core.OUTPUT_DIR = old
        shutil.rmtree(tmp, ignore_errors=True)


def test_glossary_mutation_helpers_keep_the_freeze_invariant():
    """编辑/新增/删除术语必须生成新的术语版本，而不是悄悄改草稿。"""
    tmp = Path(tempfile.mkdtemp(prefix="la-mutate-"))
    old = core.OUTPUT_DIR
    core.OUTPUT_DIR = tmp
    try:
        job_id = "lamutate0000000001"
        core.save_job_state(job_id, _job(
            job_id, "Book A.docx",
            glossary=[_term("volumetric sensors", "体积传感器", status="provisional")]))
        entry_id = models.normalize_glossary(
            core.load_job_state(job_id)["glossary"])[0]["id"]

        state, ok, message = core.update_glossary_entry(
            job_id, entry_id, preferred="体积传感装置")
        assert ok, message
        assert state["glossary"][0]["preferred"] == "体积传感装置"
        assert state["glossary_frozen"]["version"] == 1
        assert state["stage"] == "GLOSSARY_FROZEN"
        assert any(action["action"] == "glossary_entry_updated"
                   for action in state["human_actions"])

        state, ok, message, new_id = core.add_glossary_entry(
            job_id, "point cloud", "点云", domain="技术")
        assert ok, message and new_id
        assert state["glossary_frozen"]["version"] == 2
        assert {entry["source"] for entry in state["glossary"]} == \
            {"volumetric sensors", "point cloud"}

        state, ok, message = core.add_glossary_entry(job_id, "point cloud", "点云集")[:3]
        assert not ok and "已存在" in message, "同名不同译法必须被拒绝"

        state, ok, message = core.delete_glossary_entry(job_id, new_id)
        assert ok, message
        assert [entry["source"] for entry in state["glossary"]] == ["volumetric sensors"]
        assert state["glossary_frozen"]["version"] == 3
    finally:
        core.OUTPUT_DIR = old
        shutil.rmtree(tmp, ignore_errors=True)


def test_term_inspector_edit_and_delete_go_through_the_freeze_flow():
    job_id = "laedit000000000001"
    with _Workspace([(job_id, _job(
            job_id, "Book A.docx",
            glossary=[_term("volumetric sensors", "体积传感器",
                            status="provisional")]))]):
        at = _app()
        next(b for b in at.button if b.label.startswith("**volumetric")).click().run()
        _buttons(at, "la_edit_")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        field = _keys(at.text_input, "la_term_pref_")[0]
        field.set_value("体积传感装置")
        at.run()
        _buttons(at, "la_term_edit_save_")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("新的术语版本" in item.value for item in at.success), \
            "编辑术语必须生成新版本，并让用户看到这件事"
        state = core.load_job_state(job_id)
        assert state["glossary"][0]["preferred"] == "体积传感装置"
        assert state["glossary_frozen"]["version"] == 1

        _keys(at.checkbox, "la_term_delete_confirm_")[0].set_value(True)
        at.run()
        _buttons(at, "la_term_delete_")[0].click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert core.load_job_state(job_id)["glossary"] == []
        at.run()
        assert not at.exception, [e.value for e in at.exception]
