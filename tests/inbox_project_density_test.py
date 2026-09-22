"""Inbox（系统工作区）与 Project 的信息架构分离 + 项目卡密度回归测试。

本文件守住的边界（Project Center / New Task 两页）：

1. **Inbox 不是 Project**。`未分类任务` 是 system collection / 默认收纳区，
   Project 是用户创建的知识容器。两者必须用**不同的元素语法**表达：
   项目卡 = 白面 + 实线 + 圆角 14 + 静置无阴影 + 富文本三段式；
   未分类入口 = sunken 面 + 虚线 + 零阴影 + 单行说明 + 无 overflow menu。
   英文 `Inbox` 只能作为低对比小标签，不能成为主视觉标题。

2. **Project Center 是两个区块**：`系统任务区`（未分类任务）在前，
   `我的项目` 在后，各自是独立 section，不只是"同一列表里换了个颜色"。

3. **点击行为不同**：Inbox 条目 → 未分类任务列表（Task Inbox）；
   Project 卡片 → Project Detail（有 tabbar / 概览）。两者不共用落点。

4. **项目卡是低密度三段式**：身份 / 状态 / 行动。长句式说明被压成一行短文案，
   底部有一条 hairline 把"CTA + 元信息"与正文分开，更新时间是卡上最弱的元素。

5. **归属规则**：从项目中心创建任务时若已带项目上下文，则任务继承该项目；
   未选择项目时落到系统工作区。

运行：`python -m pytest tests/inbox_project_density_test.py -q`
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
sys.path.insert(0, str(ROOT / "tests"))

import core  # noqa: E402


@contextmanager
def ia_env():
    """隔离的输出目录；应用与核心层共用同一个 `core.OUTPUT_DIR`。"""
    tmp = Path(tempfile.mkdtemp(prefix="inbox-project-ia-"))
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
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)


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


def _markdown_text(at):
    return "\n".join(str(m.value) for m in at.markdown)


def _style_text(at):
    """应用注入的 `<style>` 原文（CSS 契约断言用）。"""
    return "\n".join(str(m.value) for m in at.markdown
                     if str(m.value).lstrip().startswith("<style"))


def _page_text(at):
    """页面可见文案：去掉 `<style>`。

    CSS 注释里也写着"未分类任务""Inbox"这些词，按整页文本做否定断言会误报。
    """
    return re.sub(r"<style>.*?</style>", "", _markdown_text(at), flags=re.S)


def _markdown_with(at, marker):
    """第一个包含 `marker` 的**内容** markdown 原文（跳过注入的 `<style>`）。"""
    for element in at.markdown:
        value = str(element.value)
        if value.lstrip().startswith("<style"):
            continue
        if marker in value:
            return value
    return ""


def _css_rule(at, selector):
    """取出某条 CSS 规则的声明体（选择器必须逐字出现在样式表里）。

    两个精度要求：

    1. **行首匹配**：`[class*="st-key-project_row_"]` 这类片段也会出现在
       `.st-key-project_grid [class*="st-key-project_row_"] { … }` 里，不加行首
       约束会取到别的规则体。
    2. **取最后一条**：项目卡容器有两条**行首**同选择器规则 —— 一条锚点
       （`position: relative`，见 `test_project_row_rule_holds_only_the_overlay_anchor`）
       与 Project hub 段落的紧凑卡规则。同权重下**后者生效**，所以断言必须看最后
       一条；取第一条会测到锚点那段，什么视觉契约都验不到。
    """
    table = _style_text(at)
    for marker in ("\n" + selector + " {", selector + " {"):
        index = table.rfind(marker)
        if index != -1:
            start = index + len(marker)
            return table[start:].split("}")[0]
    raise AssertionError(f"样式表里找不到规则：{selector}")


def _color_value(at, rule_body):
    """规则里的 `color:` 值，`var(--token)` 会按样式表里的色板解析成 hex。"""
    match = re.search(
        r"color:\s*(var\(--[a-z0-9-]+\)|#[0-9a-fA-F]{6})", rule_body)
    assert match, rule_body
    token = match.group(1)
    if token.startswith("#"):
        return token
    name = token[len("var("):-1]
    table = _style_text(at)
    declared = re.search(re.escape(name) + r":\s*(#[0-9a-fA-F]{6})", table)
    assert declared, f"样式表里找不到色板 {name}"
    return declared.group(1)


def _button(at, key):
    for element in at.button:
        if element.key == key:
            return element
    return None


def _find_container(at, key):
    for node, _ancestors in _walk(at.main):
        if getattr(node, "key", None) == key:
            return node
    return None


def _container_order(at):
    """主区域里带 key 的容器出现顺序。"""
    return [getattr(node, "key", None) for node, _ in _walk(at.main)
            if getattr(node, "key", None)]


def _state(at, key, default=None):
    return at.session_state[key] if key in at.session_state else default


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


def _seed_job(job_id="member", filename="member.docx", project_id=None):
    state = core.new_job_state(filename)
    state["project_id"] = project_id
    core.save_job_state(job_id, state)
    return state


def _switch_to(at, project_id):
    """走**唯一**的 switcher 切换上下文（与用户点击路径一致）。"""
    at.button(key="current_project_selector").click()
    at.run()
    at.button(key=f"switcher_pick_{project_id}").click()
    at.run()
    return at


def _relative_luminance(hex_color):
    """sRGB 相对亮度：数值越大越浅，在白底上越"弱"。"""
    value = hex_color.lstrip("#")
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


# ================= 1. 未分类任务：system collection 语义 =================


def test_project_center_separates_system_zone_from_my_projects():
    """Project Center 是「系统任务区 → 我的项目」两个区块，未分类不是列表里的一项。"""
    with ia_env():
        core.create_project("学术专著")
        at = _project_page()
        assert not at.exception, [e.value for e in at.exception]

        assert _find_container(at, "project_system_zone") is not None, \
            "系统任务区必须是一个独立 section"
        assert _find_container(at, "project_uncategorized") is not None
        assert _find_container(at, "project_section") is not None

        order = _container_order(at)
        assert order.index("project_system_zone") < order.index("project_section"), \
            f"系统任务区必须在「我的项目」之前：{order}"
        assert order.index("project_toolbar") < order.index("project_system_zone"), \
            "搜索 / 筛选 / 视图切换必须在两个区块之前"

        page = _page_text(at)
        assert "系统任务区" in page, page[:800]
        assert "系统工作区 · 不属于任何项目" in page, page[:800]
        assert "我的项目" in page, page[:800]


def test_every_icon_rule_binds_the_icon_font():
    """每条图标规则都必须声明图标字体，否则图标会退化成字面文本。

    这个项目**没有**全局的 `.material-symbols-rounded { font-family: … }`，
    每个使用点都要自己声明 `font-family: "Material Symbols Rounded"`。漏掉它
    不会报错，只会把 `inbox` / `folder_open` 当成文字画在界面上 ——
    「英文 Inbox 看起来像主视觉标题」正是这么来的。

    修饰类规则（`.is-loading` / `_selected`）只改字重与动画，继承基础规则即可豁免。
    """
    with ia_env():
        at = _project_page()
        table = _style_text(at)
        rules = re.findall(r'(?m)^([^\n{}]*\.material-symbols-rounded)\s*\{([^}]*)\}',
                           table)
        assert rules, "样式表里必须有图标规则"
        offenders = []
        for selector, body in rules:
            selector = selector.strip()
            if any(token in selector for token in (".is-", "_selected")):
                continue
            if "font-family" not in body:
                offenders.append(selector)
        assert not offenders, f"这些图标规则没绑定图标字体：{offenders}"
        # 本次改动的那一条必须在其中，且显式指向图标字体。
        context_rule = _css_rule(at, ".tp-project-context > .material-symbols-rounded")
        assert '"Material Symbols Rounded" !important' in context_rule, context_rule


def test_uncategorized_entry_uses_system_syntax_not_card_syntax():
    """未分类入口与项目卡必须是两套元素语法：虚线 + sunken + 零阴影 vs 白面 + 实线。"""
    with ia_env():
        _seed_job("loose", "loose.docx", None)
        at = _project_page()
        system_rule = _css_rule(at, ".st-key-project_uncategorized")
        assert "dashed" in system_rule, system_rule
        assert "var(--tp-surface-sunken)" in system_rule, system_rule
        assert "box-shadow" not in system_rule, \
            "系统入口不得有卡片阴影——那是「你拥有的对象」才有的语法"
        assert "min-height: 72px" in system_rule, system_rule

        card_rule = _css_rule(at, '[class*="st-key-project_row_"]')
        assert "dashed" not in card_rule, card_rule
        assert "var(--tp-surface)" in card_rule, card_rule
        assert "border-radius: 14px" in card_rule, card_rule
        assert "border-radius: 12px" in system_rule, \
            "两者圆角必须不同，避免读成同一类对象"


def test_uncategorized_inbox_word_is_a_tag_not_a_title():
    """英文 Inbox 只做状态行右侧的低对比标签，不得成为主视觉标题。"""
    with ia_env():
        _seed_job("loose", "loose.docx", None)
        at = _project_page()
        strip = _markdown_with(at, "tp-uncat")
        assert strip, "必须渲染未分类入口"
        assert '<span class="tp-uncat-tag">Inbox</span>' in strip, strip
        assert '<strong>未分类任务</strong>' in strip or \
            '<span class="tp-uncat-title">未分类任务' in strip, strip
        # 标题上不能出现 Inbox；它也不能单独占一行。
        assert "<h1>Inbox" not in strip and "<h1>未分类任务</h1>" not in strip, strip
        assert "<strong>Inbox</strong>" not in strip, strip

        tag_rule = _css_rule(at, ".tp-uncat-tag")
        assert "font-size: 11px" in tag_rule, tag_rule
        assert "var(--tp-faint)" in tag_rule, tag_rule


def test_uncategorized_entry_describes_itself_without_repeating_the_count():
    """说明文案回答"这是什么"，数量只在右侧出现一次。"""
    with ia_env():
        _seed_job("a", "a.docx", None)
        _seed_job("b", "b.docx", None)
        at = _project_page()
        strip = _markdown_with(at, "tp-uncat")
        assert strip.count("2 个") == 1, strip
        assert "尚未归入任何项目的任务" in strip, strip
        assert "个任务尚未归入项目" not in strip, "副标题不得重复 count"


# ================= 2. Inbox 与 Project 的点击落点差异 =================


def test_inbox_entry_lands_on_the_task_list_not_a_project_page():
    """Inbox 点击 → 未分类任务列表；它不是任何 Project Detail。"""
    with ia_env():
        core.create_project("真实项目")
        _seed_job("loose", "loose.docx", None)
        at = _project_page()
        system_id = core.system_project_id()

        at.button(key=f"project_open_{system_id}").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        assert _find_container(at, "project_inbox") is not None, \
            "未分类的落点必须是 Task Inbox"
        assert _find_container(at, "inbox_header") is not None
        assert _find_container(at, "project_detail_header") is None, \
            "未分类不得渲染成 Project Detail"
        assert _find_container(at, "project_tabbar") is None, \
            "Task Inbox 没有 概览/任务/知识/设置 四个 tab"
        assert _state(at, "active_project_id") == system_id
        # 这一页讲的是"任务收纳区"，用的是任务语言，不是项目语言。
        assert _button(at, "inbox_back_to_hub") is not None
        page = _page_text(at)
        assert "尚未归入任何项目的翻译任务" in page, page[:800]
        assert "项目知识与语言资产" not in page, "不得复用项目 hub 的副标题"


def test_project_card_lands_on_the_project_detail_page():
    """Project 点击 → Project Detail（带一级 tab），不是任务列表。"""
    with ia_env():
        project = core.create_project("真实项目")
        _seed_job("member", "member.docx", project["project_id"])
        at = _project_page()

        at.button(key=f"project_open_{project['project_id']}").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        assert _find_container(at, "project_detail_header") is not None
        assert _find_container(at, "project_tabbar") is not None
        assert _find_container(at, "project_inbox") is None, \
            "Project Detail 不得复用 Task Inbox 的外壳"
        assert _state(at, "active_project_id") == project["project_id"]
        assert _state(at, "active_project_tab") == "overview"


def test_inbox_has_no_project_lifecycle_actions_on_the_hub():
    """未分类入口没有重命名 / 归档 / 删除：它不是一件被创建的对象。"""
    with ia_env():
        _seed_job("loose", "loose.docx", None)
        at = _project_page()
        system_id = core.system_project_id()
        assert _find_container(at, "project_uncategorized") is not None
        assert _button(at, f"project_open_{system_id}") is not None, "整条可点"

        zone = _find_container(at, "project_system_zone")
        keys = {getattr(node, "key", None) for node, _ in _walk(zone)}
        for action in ("rename", "edit", "archive", "export", "delete"):
            assert f"pm_{action}_{system_id}" not in keys, action
        assert not any(str(key or "").startswith("project_menu_") for key in keys), \
            f"系统入口不得有 overflow menu：{keys}"


# ================= 3. 项目卡片：空状态与三段式密度 =================


def test_empty_project_card_is_a_short_hint_plus_one_real_cta():
    """空项目卡：`尚无任务` + 一行短辅助文案 + 一个真实 CTA，没有长句式说明。"""
    with ia_env():
        project = core.create_project("空项目")
        at = _project_page()
        page = _page_text(at)

        assert "尚无任务" in page
        assert "可开始积累术语与翻译记忆" in page, page[:1200]
        for long_copy in ("创建第一个翻译任务，开始积累术语、规则和项目记忆。",
                          "打开项目创建第一个翻译任务",
                          "暂无描述", "暂无任务"):
            assert long_copy not in page, long_copy
        for zero in ("0 术语", "0 规则", "0 决定", "0 记忆", "0 个任务"):
            assert zero not in page, zero

        assert _button(at, f"project_card_create_{project['project_id']}") is not None
        assert _button(at, f"project_card_view_{project['project_id']}") is None, \
            "空项目的槽位动词是「创建任务」，不是「查看项目」"


def test_project_card_with_tasks_swaps_the_cta_verb_in_the_same_slot():
    """有任务的项目：同一个底部槽位换成「查看项目」。"""
    with ia_env():
        project = core.create_project("在跑的项目")
        _seed_job("member", "第一章.docx", project["project_id"])
        at = _project_page()
        page = _page_text(at)

        assert _button(at, f"project_card_view_{project['project_id']}") is not None
        assert _button(at, f"project_card_create_{project['project_id']}") is None
        assert "尚无任务" not in page, "有任务时不得出现空态文案"
        assert "可开始积累术语与翻译记忆" not in page
        assert ">1</strong> 个任务" in page, page[:1200]

        # 同一个槽位 → 两个 CTA 的定位规则必须一致。
        empty_cta = _css_rule(
            at, '.st-key-project_section [class*="st-key-project_empty_cta_"]')
        view_cta = _css_rule(
            at, '.st-key-project_section [class*="st-key-project_view_cta_"]')
        for prop in ("position: absolute", "left: 20px", "bottom: 16px", "z-index: 4"):
            assert prop in empty_cta, (prop, empty_cta)
            assert prop in view_cta, (prop, view_cta)


def test_project_card_is_a_three_zone_layout_with_a_separated_footer():
    """卡片是三段式：head / body / foot；foot 用 hairline 与正文分开。"""
    with ia_env():
        project = core.create_project("学术专著", description="教材本地化")
        _seed_job("member", "第一章.docx", project["project_id"])
        at = _project_page()
        card = _markdown_with(at, "tp-pcard-head")
        assert card, "必须渲染项目卡"

        for zone in ("tp-pcard-head", "tp-pcard-body", "tp-pcard-foot"):
            assert zone in card, zone
        # 顺序固定：身份 → 状态 → 行动。
        assert card.index("tp-pcard-head") < card.index("tp-pcard-body") \
            < card.index("tp-pcard-foot"), card
        # foot 里是"CTA 槽位 + 弱元信息组"，不是又一堆正文。
        foot = card[card.index("tp-pcard-foot"):]
        assert "tp-pcard-cta-slot" in foot, foot
        assert "tp-pcard-meta" in foot and "tp-pcard-knowledge" in foot, foot
        assert "tp-pcard-updated" in foot, foot

        foot_rule = _css_rule(at, ".tp-pcard-foot")
        assert "margin-top: auto" in foot_rule, foot_rule
        assert "border-top: 1px solid var(--tp-hairline)" in foot_rule, foot_rule
        assert "padding-top: 11px" in foot_rule, foot_rule


def test_project_card_updated_time_is_the_weakest_element():
    """更新时间必须比知识摘要更弱：更小字号 + 更低对比度，且不与 CTA 争行。"""
    with ia_env():
        core.create_project("学术专著")
        at = _project_page()

        updated_rule = _css_rule(at, ".tp-pcard-updated")
        knowledge_rule = _css_rule(at, ".tp-pcard-knowledge")
        assert "font-size: 11.5px" in updated_rule, updated_rule

        updated_color = _color_value(at, updated_rule)
        knowledge_color = _color_value(at, knowledge_rule)
        assert updated_color != knowledge_color, (updated_rule, knowledge_rule)
        assert _relative_luminance(updated_color) > \
            _relative_luminance(knowledge_color), \
            "更新时间必须比知识摘要更浅（更弱）"

        # 底部是弹性布局：CTA 在左、元信息组在右，两者不会互相挤压。
        assert "justify-content: space-between" in _css_rule(at, ".tp-pcard-foot")
        assert "var(--tp-hairline)" in _css_rule(at, ".tp-pcard-foot")


def test_card_zones_stretch_so_footers_align_across_a_row():
    """卡片所在子树必须被拉满：否则 `margin-top:auto` 失效，同排卡片底边参差。

    Streamlit 的列是 block 容器，markdown 容器默认不参与拉伸 —— 只给 footer 写
    `margin-top:auto` 是不够的（footer 会紧贴正文）。这条断言守住"拉满链"。
    """
    with ia_env():
        core.create_project("学术专著")
        at = _project_page()

        table = _style_text(at)
        assert ':has(.tp-pcard)' in table, \
            "必须用 :has() 命中卡片所在子树并把它拉满"
        assert "flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0" \
            in table, "拉满链的声明缺失"

        card_rule = _css_rule(at, ".tp-pcard")
        assert "min-height: 114px" in card_rule, \
            "还需要一个兜底高度，避免拉满链失配时 footer 贴不到底"
        assert "justify-content: flex-start" in card_rule, \
            "贴合必须只由 footer 的 auto margin 负责，不能与 space-between 叠加"
        assert "margin-top: auto" in _css_rule(at, ".tp-pcard-foot")


def test_project_card_has_breathing_room_and_no_resting_shadow():
    """卡片靠留白分层，而不是靠阴影和更小的 padding 塞信息。"""
    with ia_env():
        core.create_project("学术专著")
        at = _project_page()
        card_rule = _css_rule(at, '[class*="st-key-project_row_"]')
        assert "padding: 18px 20px" in card_rule, card_rule
        assert "min-height: 152px" in card_rule, card_rule
        assert "box-shadow: none" in card_rule, \
            "静置态不得有阴影：网格里多张卡各带阴影会互相争注意力"
        hover_rule = _css_rule(at, '[class*="st-key-project_row_"]:hover')
        assert "var(--tp-shadow-md)" in hover_rule, hover_rule

        body_rule = _css_rule(at, ".tp-pcard-body")
        assert "flex-direction: column" in body_rule, body_rule
        assert "gap: 5px" in body_rule, body_rule


def test_project_row_rule_holds_only_the_overlay_anchor():
    """卡片容器只剩 `position: relative` 一个声明，而且它必须还在。

    该选择器有两条**行首**同权重规则：一条锚点、一条 Project hub 的紧凑卡规则。
    清理前锚点那条还堆着一整套被后者整条覆盖的旧声明（`padding` / `border-radius` /
    `transition` / 一条 `:hover`），已删除。两条断言缺一不可：

    - 删掉锚点：绝对定位的整卡点击层（`.stButton { inset: 0 }`）会逃逸到更外层的
      定位祖先上，整卡的点击区域与视觉错位；
    - 堆回死声明：读代码的人会按第一条规则误判卡片的真实 padding / 圆角。

    `AppTest` 只读元素树，两件事它都看不见，所以在这里锁住。
    """
    with ia_env():
        core.create_project("学术专著")
        at = _project_page()
        table = _style_text(at)
        bodies = re.findall(r'(?m)^\[class\*="st-key-project_row_"\]\s*\{(.*?)\}',
                            table, flags=re.S)
        assert len(bodies) == 2, \
            f"行首规则应恰好是「锚点 + 项目 hub」两条：{bodies}"
        assert bodies[0].strip() == "position: relative;", \
            f"锚点规则不得再堆叠被覆盖的旧声明：{bodies[0]!r}"
        assert "min-height: 152px" in bodies[1], \
            f"第二条必须仍是项目 hub 的紧凑卡规则：{bodies[1]!r}"


# ================= 4. 从项目中心创建任务 =================


def test_create_task_from_the_empty_project_card_carries_the_context():
    """空项目卡的 CTA 进入新建任务，并**自动带上下文**（继承术语 / TM / 规则）。"""
    with ia_env():
        project = core.create_project("从卡片创建")
        at = _project_page()
        at.button(key=f"project_card_create_{project['project_id']}").click()
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        assert _state(at, "app_view") == "new", "不得被拽去看项目详情"
        assert _state(at, "active_project_id") == project["project_id"]
        assert _state(at, "task_project_id") == project["project_id"], \
            "从卡片创建的任务必须继承该项目上下文"

        page = _page_text(at)
        assert "项目上下文" in page, page[:900]
        assert "从卡片创建" in page, page[:900]
        assert "继承项目术语、翻译记忆和规则" in page, page[:900]
        assert 'class="tp-project-context is-selected"' in page, \
            "已带上下文时必须是 selected 态"
        assert "未分类任务" not in page, "已选项目时不得再显示未分类状态"


def test_new_task_without_a_project_falls_back_to_the_inbox_context():
    """没有项目上下文时，新建任务页显示 Inbox context block，而不是一张项目卡。"""
    with ia_env():
        at = _new_task_page()
        assert not at.exception, [e.value for e in at.exception]
        assert _state(at, "task_project_id") == core.system_project_id()

        page = _page_text(at)
        assert "项目上下文" in page, page[:900]
        assert "未分类任务" in page
        assert "任务将保存到系统工作区，不继承项目术语、翻译记忆与规则" in page, \
            page[:900]
        assert 'class="tp-project-context is-empty"' in page, page[:900]
        assert "选择项目" in [b.label for b in at.button], [b.label for b in at.button]


# ================= 5. New Task：上下文状态切换 =================


def test_new_task_context_block_switches_between_inbox_and_project():
    """未分类 ⇄ 项目：同一个容器换状态，且始终只有一个来源。"""
    with ia_env():
        project = core.create_project("上下文项目")
        at = _new_task_page()

        # ① 初始：Inbox 态。
        assert 'class="tp-project-context is-empty"' in _page_text(at)

        # ② 切到一个真实项目：selected 态，且不再声称是未分类。
        at = _switch_to(at, project["project_id"])
        page = _page_text(at)
        assert _state(at, "app_view") == "new", "切换上下文不得离开创建流程"
        assert _state(at, "task_project_id") == project["project_id"]
        assert 'class="tp-project-context is-selected"' in page, page[:900]
        assert "上下文项目" in page, page[:900]
        assert "未分类任务" not in page, page[:900]
        assert "更改" in [b.label for b in at.button]

        # ③ 切回系统工作区：重新显示 Inbox 态。
        at = _switch_to(at, core.system_project_id())
        page = _page_text(at)
        assert _state(at, "app_view") == "new"
        assert _state(at, "task_project_id") == core.system_project_id()
        assert 'class="tp-project-context is-empty"' in page, page[:900]
        assert "任务将保存到系统工作区，不继承项目术语、翻译记忆与规则" in page
        assert "选择项目" in [b.label for b in at.button]


def test_new_task_context_block_is_not_a_project_card():
    """项目上下文是 context block：没有 overflow menu、没有项目卡 markup。"""
    with ia_env():
        project = core.create_project("上下文项目")
        at = _new_task_page()
        at = _switch_to(at, project["project_id"])

        block = _markdown_with(at, "tp-project-context")
        assert block, "必须渲染项目上下文块"
        assert "tp-pcard" not in block, "上下文块不得复用项目卡 markup"
        assert "tp-project-icon" not in block, "不得使用项目卡图标语法"

        container = _find_container(at, "task_project_context")
        assert container is not None
        keys = {getattr(node, "key", None) for node, _ in _walk(container)}
        assert not any(str(key or "").startswith("project_menu_") for key in keys), \
            f"上下文块不得有 overflow menu：{keys}"

        # 它仍然是**只读**的：全页只有一个上下文来源（侧栏 switcher）。
        assert not any(str(key or "").startswith("switcher_pick_") for key in keys), \
            "上下文块内不得内嵌第二个项目选择器"


def test_context_heading_marks_the_block_in_both_states():
    """两种状态都必须有一个「项目上下文」标签，读者才知道这块在回答什么。"""
    with ia_env():
        project = core.create_project("上下文项目")
        at = _new_task_page()
        assert '<div class="tp-context-head">项目上下文</div>' in _markdown_text(at)

        at = _switch_to(at, project["project_id"])
        assert '<div class="tp-context-head">项目上下文</div>' in _markdown_text(at)

        head_rule = _css_rule(at, ".tp-context-head")
        assert "font-size: 11px" in head_rule, head_rule
