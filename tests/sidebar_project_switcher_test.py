"""侧栏 Project Context ↔ Project Center 的**交互语义**回归。

同一个心智模型（Project）在这里有两个成分，但它们不是同一件事：

    Project Context Selector  = state / switch action —— "我此刻在哪个项目里工作"
    Project Center            = navigation            —— "我拥有哪些项目"

两者在侧栏同一个「项目」分组里相邻，但功能上严格分离。本文件守住这条边界，
覆盖 8 条验收：

  1. 点 selector → 展开 switcher（轻量下拉面板），**不是**大型 Modal；
  2. 点项目 → 更新 current project，面板立刻收起；
  3. 选 Inbox → 回到系统工作区上下文，而不是"选中了一个叫未分类的项目"；
  4. 点「项目中心」→ 进入管理页路由，不展开 switcher、不弹 Modal；
  5. 已经在管理页时再点 → 保持 route 与 active state，仍不展开 switcher；
  6. 「项目中心」导航**不改变** current project；
  7. switcher 里的「新建项目」走既有 create-project flow，创建成功即成为上下文；
  8. 不存在"两个入口打开同一个大型 project modal"：两处锚点共用**同一份**列表实现，
     且旧 Modal 的状态位 / CSS / 入口全部退休；两处锚点的 widget key（含底部动作）
     按锚点隔离，不共用。

为什么不用 `st.popover`：它的开合由前端驱动，服务端既读不到也关不掉——"选中后
立即关闭"和"点项目中心不得弹 switcher"会退化成不可验证的约定；而且它的内容默认
**常驻渲染**，面板数据一次约 0.4 s，等于给每一次重跑都加上这笔开销。因此展开态由
会话标记驱动：展开才渲染，关闭是确定性的。

运行：`python -m pytest tests/sidebar_project_switcher_test.py -q`
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core  # noqa: E402

APP_SOURCE = ROOT / "app.py"
SIDEBAR_OPEN = "sidebar_project_switcher_open"
TASK_OPEN = "task_project_switcher_open"


@contextmanager
def switcher_env():
    """隔离的输出目录；应用与核心层共用同一个 `core.OUTPUT_DIR`。"""
    tmp = Path(tempfile.mkdtemp(prefix="sidebar-switcher-"))
    old_output = core.OUTPUT_DIR
    core.OUTPUT_DIR = tmp
    try:
        yield tmp
    finally:
        core.OUTPUT_DIR = old_output
        shutil.rmtree(tmp, ignore_errors=True)


# ================= AppTest 辅助 =================


def _app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP_SOURCE), default_timeout=60)


def _state(at, key, default=None):
    """AppTest 的 session_state 没有 `.get()`：先 `in` 再取值。"""
    return at.session_state[key] if key in at.session_state else default


def _has_key(at, key):
    return key in at.session_state


def _button(at, key):
    for element in at.button:
        if element.key == key:
            return element
    return None


def _children(node):
    children = getattr(node, "children", None)
    if isinstance(children, dict):
        return list(children.values())
    if isinstance(children, list):
        return list(children)
    return []


def _walk(node, ancestors=()):
    for child in _children(node):
        yield child, ancestors
        yield from _walk(child, ancestors + (child,))


def _find_in(node, key):
    """在给定根的子树里按容器 key 找 Block（找不到返回 None）。"""
    for child, _ancestors in _walk(node):
        if getattr(child, "key", None) == key:
            return child
    return None


def _sidebar_rows(at):
    """侧栏面板里的项目行（按渲染顺序）。"""
    return [b for b in at.sidebar.button
            if b.key and b.key.startswith("switcher_pick_")]


def _task_rows(at):
    """正文锚点面板里的项目行。"""
    return [b for b in at.button
            if b.key and b.key.startswith("task_switcher_pick_")]


def _markdown_text(at):
    return "\n".join(str(m.value) for m in at.markdown)


def _visible_text(at):
    return re.sub(r"<style>.*?</style>", "", _markdown_text(at), flags=re.S)


def _flashes(at):
    return [item["message"] for item in (_state(at, "app_flash_log") or [])]


def _project_page(*, state=None):
    at = _app()
    at.session_state["app_view"] = "projects"
    for key, value in (state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def _new_task_page():
    at = _app()
    at.session_state["app_view"] = "new"
    at.session_state["task_step"] = 1
    at.session_state["task_files"] = [{"name": "a.docx", "bytes": b"x"}]
    at.run()
    return at


def _open_sidebar_switcher(at):
    at.button(key="current_project_selector").click()
    at.run()
    return at


def _pick(at, project_id, *, key=None):
    at.button(key=key or f"switcher_pick_{project_id}").click()
    at.run()
    return at


# ================= 1. selector → 轻量面板，不是 Modal =================


def test_selector_opens_a_light_switcher_panel_not_a_modal():
    """点 selector 展开的是就地下拉面板：有列表 / 搜索 / 新建项目，且不是 Modal。"""
    with switcher_env():
        project = core.create_project("面板项目")
        at = _project_page()
        assert not at.exception, [e.value for e in at.exception]

        # 收起时**不渲染任何一行**：quick switcher 空闲不该有成本（列表数据约 0.4s）。
        assert not _sidebar_rows(at), "面板收起时不该渲染项目列表"
        assert not _has_key(at, SIDEBAR_OPEN)

        at = _open_sidebar_switcher(at)
        assert not at.exception, [e.value for e in at.exception]
        assert _state(at, SIDEBAR_OPEN) is True

        # 面板是侧栏里的一个块（就地展开），不是挂在另一个根上的浮层 Modal。
        for container_key in ("project_switcher_panel", "project_switcher_list",
                              "project_switcher_footer"):
            assert _find_in(at.sidebar, container_key) is not None, \
                f"{container_key} 必须渲染在侧栏里：{container_key}"
        rows = _sidebar_rows(at)
        assert rows, [b.key for b in at.sidebar.button]
        assert any(b.key == f"switcher_pick_{project['project_id']}" for b in rows)

        # 底部只有一个低频动作：新建项目。管理入口不在 switcher 里重复一份。
        footer = _find_in(at.sidebar, "project_switcher_footer")
        footer_keys = {getattr(c, "key", None) for c, _ in _walk(footer)} - {None}
        assert "switcher_new_project" in footer_keys, footer_keys
        assert not any(k.startswith("switcher_manage") for k in footer_keys), \
            f"管理入口属于「项目中心」，不能在这里再出现一次：{footer_keys}"

        # 旧的大型「切换项目」Modal 必须彻底退休。
        assert not _has_key(at, "project_switcher_open")
        assert not any(str(c.key or "").startswith("project_switcher_dialog")
                       for c in at.container)
        css = _markdown_text(at)
        assert 'section[role="dialog"]:has(.st-key-project_switcher' not in css, \
            "切换项目不该再有 dialog 规则"


def test_selector_toggles_the_same_panel():
    """再点一次收起：开与合是同一个控件、同一个面板。"""
    with switcher_env():
        core.create_project("面板项目")
        at = _open_sidebar_switcher(_project_page())
        assert _state(at, SIDEBAR_OPEN) is True

        at = _open_sidebar_switcher(at)
        assert _state(at, SIDEBAR_OPEN) is False
        assert not _sidebar_rows(at)


# ================= 2. 选中 → 更新上下文 + 收起 =================


def test_picking_a_project_updates_the_context_and_closes_the_panel():
    with switcher_env():
        project = core.create_project("切换目标")
        at = _open_sidebar_switcher(_project_page())
        at = _pick(at, project["project_id"])
        assert not at.exception, [e.value for e in at.exception]

        assert _state(at, "active_project_id") == project["project_id"]
        assert _state(at, "task_project_id") == project["project_id"], \
            "Task 归属必须与上下文同步（同一件事的两种读法）"
        assert _state(at, SIDEBAR_OPEN) is False, "选中后必须立刻收起"
        assert not _sidebar_rows(at), "收起后不该再渲染列表"
        assert f"已切换到「{project['name']}」" in _flashes(at)


# ================= 3. Inbox 是系统容器，不是项目 =================


def test_picking_inbox_returns_to_the_system_workspace_context():
    with switcher_env():
        project = core.create_project("真实项目")
        at = _open_sidebar_switcher(_project_page())
        at = _pick(at, project["project_id"])
        assert _state(at, "active_project_id") == project["project_id"]

        at = _open_sidebar_switcher(at)
        inbox = _button(at, f"switcher_pick_{core.SYSTEM_PROJECT_ID}")
        assert inbox is not None, [b.key for b in at.sidebar.button]
        # Inbox 是特殊 system collection：带「系统工作区」badge + 未归入项目的措辞。
        assert "系统工作区" in inbox.label, inbox.label
        assert "个未归入项目的任务" in inbox.label, inbox.label

        at = _pick(at, core.SYSTEM_PROJECT_ID)
        assert core.is_system_project_id(str(_state(at, "active_project_id") or "")), \
            _state(at, "active_project_id")
        assert _state(at, "active_project_id") == core.system_project_id()
        assert _state(at, "task_project_id") == core.system_project_id()
        assert _state(at, SIDEBAR_OPEN) is False
        # 侧栏说的是「未选择项目」，而不是一个叫未分类的项目。
        assert _button(at, "current_project_selector").label.startswith("未选择项目")
        assert not any(core.SYSTEM_PROJECT_NAME in b.label
                       for b in at.sidebar.button if b.key is None), \
            "「未分类」不得被渲染成一个普通项目项"


# ================= 4/5/6. 项目中心 = 纯导航 =================


def test_project_center_navigates_and_never_opens_the_switcher():
    with switcher_env():
        project = core.create_project("被管理的项目")
        at = _project_page(state={"active_project_id": project["project_id"]})
        assert not at.exception, [e.value for e in at.exception]

        at.button(key="project_center_entry_button").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        assert _state(at, "app_view") == "projects"
        assert _state(at, "projects_route") == "list", "必须落在管理页路由上"
        # 既不展开 switcher，也不弹 Modal。
        assert _state(at, SIDEBAR_OPEN) is False
        assert not _sidebar_rows(at)
        assert not _has_key(at, "project_switcher_open")
        assert not _has_key(at, "project_modal")
        # 管理页真的渲染了（"我的项目" 区块），而不是停在项目详情上。
        assert "我的项目" in _visible_text(at), _visible_text(at)[:400]


def test_clicking_project_center_again_keeps_route_and_active_state():
    with switcher_env():
        core.create_project("项目一")
        at = _project_page()
        at.button(key="project_center_entry_button").click()
        at.run()
        assert _state(at, "projects_route") == "list"

        at.button(key="project_center_entry_button").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert _state(at, "app_view") == "projects"
        assert _state(at, "projects_route") == "list", "重复点击不允许改变 route"
        assert _state(at, SIDEBAR_OPEN) is False, "重复点击不得弹出 switcher"
        assert not _has_key(at, "project_modal")
        assert '<span class="tp-nav-current"' in "\n".join(
            str(m.value) for m in at.sidebar.markdown), \
            "已经在项目中心时，active state 必须保持"


def test_project_center_navigation_does_not_change_the_current_project():
    """需求 B：管理页是纯导航，当前 Project Context 必须原样保留。"""
    with switcher_env():
        project = core.create_project("保留上下文的项目")
        at = _project_page(state={"active_project_id": project["project_id"]})
        assert _state(at, "active_project_id") == project["project_id"]
        label_before = _button(at, "current_project_selector").label

        at.button(key="project_center_entry_button").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        assert _state(at, "active_project_id") == project["project_id"], \
            "项目中心不得抹掉当前上下文"
        assert _state(at, "task_project_id") == project["project_id"]
        assert _button(at, "current_project_selector").label == label_before, \
            "selector 的文案不该因为逛了一次管理页而翻成「未选择项目」"


# ================= 7. 新建项目 =================


def test_new_project_from_the_switcher_goes_through_the_create_flow():
    with switcher_env():
        at = _open_sidebar_switcher(_project_page())
        at.button(key="switcher_new_project").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        assert _state(at, SIDEBAR_OPEN) is False, "进入创建流程前面板必须收起"
        assert _state(at, "project_modal") == "new"
        assert any(t.key == "project_form_name" for t in at.text_input), \
            "走的是既有 create-project flow，不是 switcher 内的简易表单"

        at.text_input(key="project_form_name").set_value("从切换器新建")
        at.button(key="project_form_create").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        created = core.find_project_by_name("从切换器新建")
        assert created is not None, "项目必须真的落盘"
        assert _state(at, "active_project_id") == created["project_id"], \
            "按既有产品规则：新建的项目立即成为上下文"
        assert _state(at, "task_project_id") == created["project_id"]
        assert any("已新建项目「从切换器新建」" in message for message in _flashes(at))


# ================= 8. 只有一个 switcher 实现 =================


def test_both_anchors_share_one_switcher_implementation():
    """两处锚点是同一份列表的两个入口，不是两套并行的 project switching UX。"""
    with switcher_env():
        first = core.create_project("项目 A")
        second = core.create_project("项目 B")

        at = _new_task_page()
        assert not at.exception, [e.value for e in at.exception]

        # 侧栏锚点
        at = _open_sidebar_switcher(at)
        sidebar_labels = [b.label for b in _sidebar_rows(at)]
        assert len(sidebar_labels) >= 3, sidebar_labels

        # 正文锚点（新建任务第 1 步的「项目上下文」块）
        at.button(key="task_project_pick").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert _state(at, SIDEBAR_OPEN) is False, \
            "两处锚点展开同一份列表：打开一处必须收起另一处"
        task_rows = _task_rows(at)
        assert task_rows, [b.key for b in at.button]
        # 同一批项目、同样的行结构 —— 只有 widget key 前缀不同。
        assert [b.label for b in task_rows] == sidebar_labels
        assert {b.key for b in task_rows}.isdisjoint({b.key for b in _sidebar_rows(at)}), \
            "两处锚点的 widget key 必须两两不同，否则同一页面里会撞 key"

        at = _pick(at, second["project_id"], key=f"task_switcher_pick_{second['project_id']}")
        assert not at.exception, [e.value for e in at.exception]
        # 在「新建任务」流程里切换上下文不跳页，只换归属。
        assert _state(at, "app_view") == "new"
        assert _state(at, "task_project_id") == second["project_id"]
        assert _state(at, TASK_OPEN) is False, "选中后必须立刻收起"
        assert not _task_rows(at)
        assert first["project_id"] != second["project_id"]


def test_switcher_footer_keys_are_scoped_to_the_anchor():
    """底部动作的 widget key 跟着锚点走：两处展开态各有一套，**不共用**。

    这是 `_PROJECT_SWITCHER_ANCHORS` 的直接后果，也是容易踩的坑：在正文锚点展开时，
    侧栏锚点的 `switcher_new_project` 并不存在，存在的是 `task_switcher_new_project`。
    混用会得到一个"点了但什么都没发生"的静默失败（AppTest 里表现为 KeyError），
    所以在这里钉死，避免以后再有人把两个锚点的 key 当成同一个。
    """
    with switcher_env():
        at = _new_task_page()
        at = _open_sidebar_switcher(at)
        sidebar_keys = {b.key for b in at.button}
        assert "switcher_new_project" in sidebar_keys, sidebar_keys
        assert "task_switcher_new_project" not in sidebar_keys, \
            "侧栏锚点展开时不该出现正文锚点的 key"

        at.button(key="task_project_pick").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        task_keys = {b.key for b in at.button}
        assert "task_switcher_new_project" in task_keys, task_keys
        assert "switcher_new_project" not in task_keys, \
            "底部动作 key 必须按锚点隔离：混用会静默吞掉点击"


def test_the_duplicate_switching_modal_is_retired_in_source():
    """源码级守卫：旧 Modal 的状态位 / 入口 / 调用点都已删除，两处锚点共用一份实现。

    AppTest 只能看到"跑起来是什么样"，看不到"有没有留下第二个并行入口"。这里直接
    核对源码，防止旧 Modal 被重新引入。
    """
    source = APP_SOURCE.read_text(encoding="utf-8")
    # 精确到字符串字面量：新锚点的 `sidebar_project_switcher_open` /
    # `task_project_switcher_open` 是 `project_switcher_open` 的**超串**，
    # 用裸子串检查会误报。
    assert '"project_switcher_open"' not in source, \
        "旧「切换项目」Modal 的状态位必须退休"
    assert "_open_project_switcher" not in source
    assert "switcher_manage_all" not in source, \
        "「管理所有项目」与侧栏「项目中心」重复，必须删除"
    assert "_render_project_switcher()" not in source, \
        "旧 Modal 渲染器不该还被调用"
    assert "def _render_project_switcher_body(anchor=" in source
    # 1 处定义 + 3 处调用：侧栏锚点 1 处；正文锚点 2 处（已选态的 [更改] 与未选态的
    # [选择项目]，二者互斥，每个 run 只渲染其中一个）。多出来的调用点意味着又长出了
    # 第三个入口，那正是本轮要消除的东西。
    assert source.count("_render_project_switcher_body(") == 4, \
        "两处锚点必须共用同一个渲染函数"
