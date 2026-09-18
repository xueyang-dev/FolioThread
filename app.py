"""FolioThread Streamlit 界面层。

信息架构：左侧产品导航 + 四步任务创建 + 运行后任务工作台。AI Provider
与翻译记忆属于全局设置；研究与报告属于翻译后的专用下游工作流，不占据文档首屏。
"""
import base64
import hashlib
import inspect
import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import core
from transpraxis import assets as _assets
from transpraxis import academic_validator as _academic_validator
from transpraxis import case_provenance as _case_provenance
from transpraxis import context as _context
from transpraxis import delivery as _delivery
from transpraxis import finalization as _finalization
from transpraxis import history_view as _history_view
from transpraxis import knowledge as _knowledge
from transpraxis import language_assets as _language_assets
from transpraxis import literature_evidence as _literature_evidence
from transpraxis import model_roles as _model_roles
from transpraxis import report_evidence as _report_evidence
from transpraxis import report_template as _report_template
from transpraxis import compliance as _compliance
from transpraxis import task_overview as _task_overview
from transpraxis import thesis_constraints as _thesis_constraints
from transpraxis import translation_evidence as _translation_evidence
from transpraxis import translation_planner as _planner
from transpraxis import workbench_view as _workbench_view
from transpraxis import workspace_view as _workspace_view

# Older Streamlit versions (including the Python 3.9-compatible line) do not
# expose persist_state; widget keys provide the fallback there.
_PERSIST_STATE = (
    {"persist_state": "session"}
    if "persist_state" in inspect.signature(st.selectbox).parameters
    else {}
)

# ================= 页面全局设置 =================
_APP_ROOT = Path(__file__).resolve().parent
_BRAND_DIR = Path(_assets.__file__).resolve().parent / "resources" / "brand"
# 用户提供的品牌板直接裁切；保留原始像素与比例，不使用重绘版。
_BRAND_LOGO = _BRAND_DIR / "foliothread-source-lockup.png"
_BRAND_FAVICON = _BRAND_DIR / "foliothread-source-icon.png"
_BRAND_LOGO_URI = "data:image/png;base64," + base64.b64encode(
    _BRAND_LOGO.read_bytes()).decode("ascii")

# 面向用户的示例文案保持领域中性，避免把个人项目主题带进界面截图或演示。
_PROJECT_NAME_PLACEHOLDER = "例如：产品文档翻译 / 资料整理"
_STYLE_RULES_PLACEHOLDER = "例如：保持正式语气；术语与引用标注保持一致。"

st.set_page_config(page_title="FolioThread · 长文档翻译工作空间",
                   page_icon=_BRAND_FAVICON, layout="wide",
                   initial_sidebar_state="expanded")

if "doc_states" not in st.session_state:
    st.session_state.doc_states = {}
if "active_job_id" not in st.session_state:
    st.session_state.active_job_id = None
if "task_step" not in st.session_state:
    st.session_state.task_step = 1
if "app_view" not in st.session_state:
    st.session_state.app_view = "new"
if "workspace_mode" not in st.session_state:
    st.session_state.workspace_mode = False
# 新任务的默认归属是「未分类」（系统工作区）：Translation Task 不需要先有
# Project 才能开始，但"没有归属"仍然指向一个真实容器。None 是有效值
# （用户显式选择未分类），落盘时写成显式 null。
if "task_project_id" not in st.session_state:
    st.session_state.task_project_id = None
if "task_auto_profile" not in st.session_state:
    st.session_state.task_auto_profile = True
if "provider_configured" not in st.session_state:
    st.session_state.provider_configured = False
if "provider_connection_status" not in st.session_state:
    st.session_state.provider_connection_status = "unverified"
if "reviewer_connection_status" not in st.session_state:
    st.session_state.reviewer_connection_status = "unverified"
# 从本地配置恢复 AI 引擎（保存过之后，重启应用无需重新填写）
_saved_provider_cfg = core.load_provider_config()
if _saved_provider_cfg:
    _saved_provider = _saved_provider_cfg["provider"]
    if _saved_provider in core.PROVIDERS \
            and "provider_choice" not in st.session_state:
        st.session_state.provider_choice = _saved_provider
    if _saved_provider_cfg.get("api_key") \
            and f"api_key_{_saved_provider}" not in st.session_state:
        st.session_state[f"api_key_{_saved_provider}"] = \
            _saved_provider_cfg["api_key"]
    _saved_model = _saved_provider_cfg.get("model")
    _saved_models = core.PROVIDERS.get(_saved_provider, {}).get("models") or []
    if _saved_model and (not _saved_models or _saved_model in _saved_models) \
            and f"model_choice_{_saved_provider}" not in st.session_state:
        st.session_state[f"model_choice_{_saved_provider}"] = \
            _saved_model
    if _saved_provider_cfg.get("base_url") \
            and "custom_base_url" not in st.session_state:
        st.session_state.custom_base_url = _saved_provider_cfg["base_url"]
    _saved_reviewer = _saved_provider_cfg.get("reviewer") or {}
    if _saved_reviewer.get("provider") and "reviewer_mode" not in st.session_state:
        st.session_state.reviewer_mode = "separate"
        st.session_state.reviewer_provider_choice = _saved_reviewer["provider"]
        st.session_state.reviewer_model = _saved_reviewer.get("model", "")
        st.session_state.reviewer_api_key = _saved_reviewer.get("api_key", "")
        st.session_state.reviewer_base_url = _saved_reviewer.get("base_url", "")
# ================= 设计系统（FolioThread Long-document Workspace） =================
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

:root {
 --tp-sidebar-width: 236px;
 --tp-main-gutter: 80px;
 /* ---- 品牌色板（视觉基准见 docs/brand.md） ----
    取值来自用户提供的品牌板：字标/App 图标底 = 深海军蓝，
    图标 = 钴蓝→青的横向渐变。改这里等于改品牌的视觉基准，
    因此不再引入色板之外的新蓝色。 */
 --tp-navy: #000d2d;          /* 字标 / App 图标底 */
 --tp-brand-ink: #0b1f3b;     /* 正文级品牌深色（标题、当前项） */
 --tp-logo-blue: #004cfd;     /* 图标后页：钴蓝 */
 --tp-primary: #004cfd;
 --tp-primary-hover: #003fd6;
 --tp-primary-active: #0034b0;
 --tp-cyan: #00e8fe;          /* 图标渐变亮端 */
 --tp-azure: #0088fd;         /* 图标渐变中段 */
 --tp-primary-soft: #eef4ff;
 --tp-primary-soft-hover: #e3edff;
 --tp-border: #b9d1ff;
 --tp-focus-ring: rgba(0,76,253,.22);
 --tp-canvas: #f4f7fc;
 --tp-surface: #ffffff;
 --tp-ink: #131c2e;
 --tp-sub: #667085;
 --tp-faint: #8a94a6;
 --tp-line: #dee3ea;
 --tp-line-subtle: #ebeef3;
 --tp-sidebar-line: #e7eaf0;
 --tp-success: #22a06b;
 --tp-danger: #dc2626;
 /* ---- Surface hierarchy ----
    工作区靠"面的层级"分离空间，而不是靠边框。规则：
    canvas 放内容面，content 放正文，raised 放悬浮面板，
    hairline 只用于必要的分隔（表格行、栏间），border 退到兜底角色。 */
 --tp-canvas-soft: #f9fafb;
 --tp-surface-sunken: #f2f4f7;
 --tp-surface-raised: #ffffff;
 --tp-hairline: #eef0f4;
 --tp-hairline-strong: #e4e7ec;
 --tp-shadow-sm: 0 1px 2px rgba(16,24,40,.04);
 --tp-shadow-md: 0 2px 8px rgba(16,24,40,.06), 0 1px 2px rgba(16,24,40,.04);
 --tp-shadow-lg: 0 8px 24px rgba(16,24,40,.08), 0 2px 6px rgba(16,24,40,.04);
 --tp-tint-active: #eef4ff;
 --tp-tint-hover: #f7f9fc;
 --tp-warn: #b54708;
 --tp-warn-soft: #fffaeb;
 --tp-danger-soft: #fef3f2;
 --tp-success-soft: #ecfdf3;
 --tp-radius-sm: 6px;
 --tp-radius-md: 10px;
 --tp-radius-lg: 16px;
 --action-bar-height: 80px;
}

html, body, [class*="css"], .stApp, button, input, textarea, select {
 font-family: 'Manrope', ui-sans-serif, system-ui, -apple-system,
 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC',
 sans-serif !important;
}

.stApp {
 background: var(--tp-canvas);
}
[data-testid="stHeader"] { display: none; }
[data-testid="stDecoration"] { display: none; }
footer { visibility: hidden; }
[data-testid="stMainBlockContainer"] {
 width: min(100%, 1152px); max-width: 1152px; margin-left: 0; margin-right: auto;
 padding: 48px var(--tp-main-gutter) 40px;
}

/* ---------- Typography ---------- */
h1, h2, h3, h4, [data-testid="stHeadingWithActionElements"] {
 color: var(--tp-ink) !important;
 letter-spacing: -.02em; font-weight: 650;
}
h1 { font-size: 34px !important; line-height: 1.2 !important; font-weight: 700 !important; }
h2 { font-size: 23px !important; }
h3 { font-size: 16px !important; }
p, label, input, textarea, [data-baseweb="select"] { font-size: 14px !important; }
label, [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] label {
 color: var(--tp-ink) !important; opacity: 1 !important;
}
[data-testid="stCaptionContainer"], .stCaption {
 color: var(--tp-sub) !important; opacity: 1 !important;
}
[data-testid="stRadio"] [data-testid="stRadioOption"],
[data-testid="stRadio"] [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"],
[data-testid="stRadio"] [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] *,
[data-testid="stSlider"] [data-testid="stSliderThumbValue"],
[data-testid="stSlider"] [data-testid="stSliderThumbValue"] * {
 color: var(--tp-ink) !important; opacity: 1 !important;
}
[data-testid="stRadio"] [data-testid="stRadioOption"] > div > div > div:first-child {
 background: var(--tp-surface) !important; border: 2px solid #98a2b3 !important;
}
[data-testid="stRadio"] [data-testid="stRadioOption"][data-selected="true"] > div > div > div:first-child {
 background: var(--tp-primary) !important; border-color: var(--tp-primary) !important;
}
[data-testid="stRadio"] [data-testid="stRadioOption"][data-selected="true"]
 > div > div > div:first-child > div {
 background: #fff !important;
}
[data-testid="stRadio"] [data-testid="stRadioOption"]:hover > div > div > div:first-child {
 border-color: var(--tp-primary) !important;
}
[data-testid="stSlider"] div:has(> [data-testid="stSliderThumbValue"]) {
 background: var(--tp-primary) !important;
}
a { color: var(--tp-primary); text-decoration-color: var(--tp-border); text-underline-offset: 2px; }
a:hover { color: var(--tp-primary-hover); text-decoration-color: var(--tp-logo-blue); }
hr { border-color: var(--tp-line); }
::selection { background: var(--tp-focus-ring); }

/* ---------- Product shell ---------- */
[data-testid="stSidebar"] {
 background: #f8faff; border-right: 1px solid var(--tp-sidebar-line);
 width: var(--tp-sidebar-width) !important; min-width: var(--tp-sidebar-width) !important;
 overflow-x: clip;
 transform: none !important;
}
[data-testid="stSidebarContent"] {
 padding: 20px 24px 16px; position: relative;
}
[data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"] {
 min-height: calc(100dvh - 36px);
}
[data-testid="stSidebarHeader"] { display: none !important; }
[data-testid="stSidebarUserContent"] { padding-top: 0; }
[data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] { gap: .5rem; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { line-height: 1.5; }
/* Streamlit 会给 markdown 容器默认注入 -16px 下边距（补偿段落默认边距），
   品牌块没有段落默认边距，会被压缩导致副标题与下方按钮重叠，这里抵消掉。 */
[data-testid="stSidebarContent"] [data-testid="stMarkdownContainer"]:has(.tp-brand) {
 margin-bottom: 0;
}
[data-testid="stSidebar"] .stButton > button {
 min-height: 44px; justify-content: flex-start; border-color: transparent;
 background: transparent; color: #536176; font-size: 14px; font-weight: 400;
}
[data-testid="stSidebar"] .stButton > button:hover {
 background: #f6f8fb; border-color: transparent; color: #202a3a;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
 background: var(--tp-primary-soft); border-color: transparent;
 color: var(--tp-brand-ink); font-weight: 500;
}
.tp-brand {
 display: flex; flex-direction: column; align-items: center;
 padding: 16px 10px; margin-bottom: 18px; text-align: center;
 background: transparent; border: 0; box-shadow: none;
}
.tp-brand-logo {
 display: block; width: 168px; max-width: 100%; height: auto; object-fit: contain;
 margin: 0 auto; mix-blend-mode: multiply;
}
.tp-nav-label {
 margin: 18px 0 6px; color: #7c8799; font-size: 12px;
 font-weight: 500; letter-spacing: 0; line-height: 1.4;
}
.tp-nav-divider { height: 1px; margin: 24px 0; background: var(--tp-sidebar-line); }
/* 「项目上下文」在没有进入任何真实项目时仍然是**同一个 compact selector**，
   只是文案变成「未选择项目」——不是第二行说明，也不是一块大面积虚线卡片。
   `.tp-nav-empty` 是**空的语义标记**：CSS 用它把 selector 切成中性态，
   没有项目时不该看起来像已经选中了一个。 */
.tp-nav-empty { display: none; }
.tp-nav-note {
 margin: 6px 0 0; color: #98a2b3; font-size: 11.5px; line-height: 1.4;
}
.st-key-new_task_action .stButton > button {
 min-height: 44px; border: 1px solid var(--tp-primary); border-radius: 10px;
 background: var(--tp-primary); color: #fff; font-size: 14px; font-weight: 650;
 box-shadow: 0 4px 12px var(--tp-focus-ring);
}
.st-key-new_task_action .stButton > button:hover { background: var(--tp-primary-hover); border-color: var(--tp-primary-hover); color: #fff; }
.st-key-new_task_action .stButton > button:active { background: var(--tp-primary-active); }
.st-key-new_task_action_in_flow .stButton > button {
 min-height: 40px; border: 1px solid #d0d5dd; border-radius: 10px;
 background: transparent; color: #344054; font-size: 14px; font-weight: 550;
 box-shadow: none;
}
.st-key-new_task_action_in_flow .stButton > button:hover {
 background: #f6f8fb; border-color: #98a2b3; color: #202a3a;
}
.st-key-new_task_action_in_flow .stButton > button:active {
 background: #eef2f6; border-color: #98a2b3;
}
/* 进入 Project Detail 后，页面级 Primary CTA 属于 Header 的「+ 新建任务」；
   侧栏这一颗必须退成 secondary，不跟它抢层级（动作仍然是同一个）。 */
.st-key-new_task_action_in_project .stButton > button {
 min-height: 40px; border: 1px solid #d0d5dd; border-radius: 10px;
 background: transparent; color: #344054; font-size: 14px; font-weight: 550;
 box-shadow: none;
}
.st-key-new_task_action_in_project .stButton > button:hover {
 background: #f6f8fb; border-color: #98a2b3; color: #202a3a;
}
.st-key-new_task_action_in_project .stButton > button:active {
 background: #eef2f6; border-color: #98a2b3;
}
.st-key-task_steps { position: relative; gap: 0 !important; margin: 0 0 6px; }
.st-key-task_steps::before {
 content: ""; position: absolute; left: 17px; top: 28px; height: calc(100% - 56px);
 width: 1px; background: #dce2ea;
}
.st-key-task_steps .stButton { position: relative; z-index: 1; margin: 0; }
.st-key-task_steps .stButton > button {
 min-height: 56px; height: 56px; padding: 0 8px; background: transparent;
 border-color: transparent; border-radius: var(--tp-radius-md); font-size: 14px;
}
.st-key-task_steps .stButton > button > div { width: 100%; }
.st-key-task_steps .stButton > button > div > span {
 display: grid !important; grid-template-columns: 18px minmax(0,1fr);
 column-gap: 6px; align-items: center; width: 100%;
}
.st-key-task_steps .stButton > button[kind="primary"] {
 background: transparent; border-color: transparent; color: var(--tp-brand-ink); font-weight: 600;
}
.st-key-task_steps button[data-testid="stBaseButton-primary"] {
 background: var(--tp-primary-soft) !important; border-color: transparent !important;
 box-shadow: inset 3px 0 var(--tp-primary);
 color: var(--tp-brand-ink) !important;
}
.st-key-task_steps [data-testid="stIconMaterial"] {
 position: relative; z-index: 2; background: var(--tp-surface); border-radius: 50%;
 font-size: 18px;
}
[class*="st-key-task_step_done_"] [data-testid="stIconMaterial"] { color: var(--tp-success); }
[class*="st-key-task_step_current_"] [data-testid="stIconMaterial"] { color: var(--tp-logo-blue); }
[class*="st-key-task_step_pending_"] [data-testid="stIconMaterial"] { color: #a8b2c1; }
[class*="st-key-task_step_done_"] .stButton > button { color: #344054; font-weight: 500; }
[class*="st-key-task_step_current_"] .stButton > button { color: var(--tp-brand-ink); font-weight: 600; }
[class*="st-key-task_step_pending_"] .stButton > button { color: #536176; font-weight: 400; }
.tp-engine-row, .tp-summary, .tp-pipeline, .tp-confirm-card {
 border: 1px solid var(--tp-hairline-strong); border-radius: var(--tp-radius-lg);
 background: var(--tp-surface); box-shadow: var(--tp-shadow-sm);
}
.tp-engine-row { padding: 12px 14px; margin: 6px 0 18px; }
.tp-engine-row strong { font-size: 13px; color: var(--tp-ink); }
.tp-engine-row span { display: block; margin-top: 3px; font-size: 12px; color: var(--tp-sub); }
.st-key-provider_status {
 position: relative; width: 100%; flex-shrink: 0;
 margin-top: auto; padding: 16px 0 4px; border-top: 1px solid var(--tp-sidebar-line);
 background: transparent;
}
.st-key-provider_status [data-testid="stMarkdownContainer"] { margin-bottom: 0; }
.tp-engine-detail { color: var(--tp-sub); font-size: 11px; line-height: 1.6; overflow-wrap: anywhere; }
.tp-engine-detail span { display: block; }
.st-key-provider_status [data-testid="stHorizontalBlock"] {
 align-items: center; gap: 6px; flex-wrap: nowrap;
}
.st-key-provider_status [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
 min-width: 0; flex: 1 1 0; width: auto;
}
.st-key-provider_status [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
 flex: 0 0 44px;
}
.st-key-provider_status .stButton > button {
 min-height: 30px; padding: 2px 0; justify-content: flex-end;
 color: var(--tp-primary); font-size: 13px; font-weight: 500;
}
.st-key-provider_status .stButton > button:hover { color: var(--tp-primary-hover); background: transparent; }
.tp-provider { position: relative; padding-left: 17px; }
.tp-provider::before {
 content: ""; position: absolute; left: 2px; top: 5px; width: 8px; height: 8px;
 border-radius: 50%; background: var(--tp-surface); border: 1px solid #98a2b3;
}
.tp-provider.is-connected::before { background: var(--tp-success); border-color: var(--tp-success); }
.tp-provider.is-error::before { background: var(--tp-danger); border-color: var(--tp-danger); }
.tp-provider strong { display: block; color: #202a3a; font-size: 13px; font-weight: 600; }
.tp-provider span {
 display: block; margin-top: 3px; color: #7c8799; font-size: 11px; overflow-wrap: anywhere;
}
.tp-title { margin: 3px 0 28px; padding-bottom: 24px; border-bottom: 1px solid var(--tp-hairline-strong); }
.tp-brand-kicker { color: var(--tp-primary); font-size: 10px; font-weight: 800; letter-spacing: .16em; margin-bottom: 12px; }
.tp-title h1 {
 margin: 0; color: var(--tp-navy); font-size: 34px; font-weight: 700;
 line-height: 1.2; letter-spacing: -.025em;
}
.tp-title p {
 margin: 12px 0 0; color: var(--tp-sub); font-size: 15px !important; font-weight: 400;
}
.tp-history-copy { min-width: 0; padding: 2px 0; }
.tp-history-copy strong {
 display: block; overflow: hidden; color: var(--tp-ink) !important;
 font-size: 14px; font-weight: 600; line-height: 1.45;
 text-overflow: ellipsis; white-space: nowrap;
}
.tp-history-copy span {
 display: block; margin-top: 4px; color: var(--tp-sub) !important;
 font-size: 12px; line-height: 1.4;
}

/* ---------- Context project selector ----------
   侧栏这个控件是 **context selector / state action**：不是 project detail card，
   也不是第二个管理入口。它展开的是一个**轻量下拉面板**（切换 / 搜索 / 新建项目），
   而不是大型 Modal——Modal 会把它读成"一块管理页面"，与同组的「项目中心」重复。

   展开态用 `.is-open` 表达（由 `.tp-nav-open` 语义标记驱动），这样触发器不需要
   换一套样式语言：开与合是同一个 compact 控件。 */
.st-key-current_project { margin: 0 !important; }
.st-key-current_project > [data-testid="stVerticalBlock"] { gap: 6px; }
/* 带 `help=` 的按钮会被 Streamlit 包进 tooltip span，`button` 因此不是 `.stButton`
   的直接子元素——所有 selector 按钮规则都必须用后代选择器，否则样式整体失效。 */
.st-key-current_project .stButton button {
 min-height: 42px; padding: 0 10px; justify-content: flex-start;
 border: 1px solid transparent; border-radius: var(--tp-radius-md);
 background: var(--tp-primary-soft); color: var(--tp-brand-ink);
 font-size: 13px; font-weight: 650; text-align: left;
}
.st-key-current_project .stButton button:hover {
 border-color: #c8dcff; background: var(--tp-primary-soft-hover);
 color: var(--tp-brand-ink);
}
/* 没有真实项目时，selector 是**同一个 compact 控件**的中性态：文案变成
   「未选择项目」，而不是一块大面积虚线卡片——虚线 + 42px 高度会被读成"这里
   还有一个待填的容器"，反而比实心紧凑态更抢眼。 */
.st-key-current_project:has(.tp-nav-empty) .stButton button {
 min-height: 42px; border: 1px solid var(--tp-sidebar-line);
 background: #f6f8fb; color: #536176; font-size: 13px; font-weight: 550;
}
.st-key-current_project:has(.tp-nav-empty) .stButton button:hover {
 background: #eef2f6; border-color: #c8d4e4; color: #202a3a;
}
.st-key-current_project:has(.tp-nav-empty) .stButton button [data-testid="stIconMaterial"] {
 color: #7c8799;
}
/* 展开中：触发器保持"已按下"的 surface，指向它下面的面板。 */
.st-key-current_project:has(.tp-nav-open) .stButton button {
 border-color: #c8dcff; background: var(--tp-primary-soft-hover);
}
.st-key-current_project .stButton button > div { min-width: 0; width: 100%; }
.st-key-current_project .stButton button p {
 overflow: hidden; margin: 0; text-overflow: ellipsis; white-space: nowrap;
}
.st-key-current_project .stButton button [data-testid="stIconMaterial"] {
 flex: 0 0 18px; color: var(--tp-primary);
}
/* ---------- 侧栏「项目」分组：上下文 selector + 管理入口 ----------
   Project Context（我此刻在哪个项目里工作）与 Project Management（我拥有哪些
   项目）在认知上同属 Project，因此必须在侧栏里是**同一个分组**：同一个标题、
   同一个容器、上下相邻，中间不再插分隔线。但它们是主次而不是并列：

   1. 上下文 selector 是**主控件**：填充底 + 42px + 650 字重，回答"我在哪"，
      并且是全局唯一的上下文来源；
   2. 「项目中心」是**次级入口**：透明底 + 36px + 500 字重 + 灰色，只负责
      管理动作（查看 / 新建 / 重命名 / 归档 / 删除），不切换上下文。

   两种错误都被这一层排除了：同组同级会被读成两个等价入口；拆到两个分组会被
   读成两套系统——后者正是本轮要消除的割裂感。 */
.st-key-project_nav_group { margin: 0 !important; }
.st-key-project_nav_group > [data-testid="stVerticalBlock"] { gap: 4px; }
.st-key-project_nav_group .tp-nav-label { margin: 18px 0 2px; }
[class*="st-key-project_center_entry"] { margin: 0 !important; }
/* 带 `help=` 的按钮会被 Streamlit 包进 tooltip span，`button` 不是 `.stButton`
   的直接子元素，因此这里同样必须用后代选择器。 */
[class*="st-key-project_center_entry"] .stButton button {
 min-height: 36px; padding: 0 10px; justify-content: flex-start;
 border: 1px solid transparent; border-radius: var(--tp-radius-md);
 background: transparent; color: #536176;
 font-size: 13px; font-weight: 500; text-align: left;
}
[class*="st-key-project_center_entry"] .stButton button:hover {
 background: #f2f5f9; border-color: transparent; color: #202a3a;
}
[class*="st-key-project_center_entry"] .stButton button > div { min-width: 0; width: 100%; }
[class*="st-key-project_center_entry"] .stButton button p {
 overflow: hidden; margin: 0; text-overflow: ellipsis; white-space: nowrap;
}
[class*="st-key-project_center_entry"] .stButton button [data-testid="stIconMaterial"] {
 flex: 0 0 18px; color: #98a2b3; font-size: 17px;
}
/* `.tp-nav-current` 是**空的语义标记**（与 `.tp-nav-empty` 同一套路）：CSS 用它把
   入口切成"当前页"态——中性面 + 左侧 3px 竖条。刻意不复用 `--tp-primary-soft`：
   那个填充底是 selector"已进入某个项目"的语法，两者同时出现会被读成两个等价入口。 */
.tp-nav-current { display: none; }
.st-key-project_center_entry [data-testid="stElementContainer"]:has(.tp-nav-current) {
 display: none;
}
.st-key-project_center_entry:has(.tp-nav-current) .stButton button {
 background: #f2f5f9; color: var(--tp-brand-ink); font-weight: 600;
 box-shadow: inset 3px 0 var(--tp-primary);
}
.st-key-project_center_entry:has(.tp-nav-current) .stButton button [data-testid="stIconMaterial"] {
 color: var(--tp-primary);
}
/* ---------- 新建任务的「项目上下文」context block ----------
   它回答的是"这个任务会落在哪里"，不是"我拥有哪个项目"。因此：

   1. 它是 **context block**，不是 project card：没有卡片阴影、没有整卡点击层、
      没有 overflow menu——那些是用户拥有的 Project 对象的语法；
   2. 已选项目与未分类**共用同一个容器**（同一个 min-height、同一个 padding），
      只在语气上分级：选中态是 primary-soft 面 + 实心图标，未分类是 sunken 面 +
      中性图标。两者都不是"一张小项目卡"；
   3. 顶部一行小标签「项目上下文」把这块和「目标语言」之类的普通字段区分开；
   4. 它不做成第二个下拉框：两个并列的选择器迟早会给出互相矛盾的答案。 */
.tp-context-head {
 margin: 0 0 6px; color: var(--tp-faint); font-size: 11px; font-weight: 700;
 letter-spacing: .04em;
}
.tp-project-context {
 display: flex; align-items: center; gap: 10px; min-height: 56px;
 padding: 10px 12px; border: 1px solid var(--tp-hairline-strong);
 border-radius: var(--tp-radius-md); background: var(--tp-surface);
}
.tp-project-context.is-selected {
 border-color: #c8dcff; background: var(--tp-primary-soft);
}
/* 未分类：系统工作区，不是用户的项目。用 sunken 面 + 中性图标把它降一级，
   而不是给它一块和"选中项目"同色的高光面。 */
.tp-project-context.is-empty {
 border-color: var(--tp-hairline-strong); background: var(--tp-surface-sunken);
}
/* 图标字形必须显式绑定图标字体：本项目没有全局的
   `.material-symbols-rounded { font-family: … }`，每个使用点都要自己声明。
   漏掉它不会报错，只会把 `inbox` / `folder_open` 当成**字面文本**画出来 ——
   这正是"英文 inbox 看起来像主视觉标题"的根因。 */
.tp-project-context > .material-symbols-rounded {
 flex: 0 0 auto; font-size: 19px; font-family: "Material Symbols Rounded" !important;
 color: var(--tp-primary);
}
.tp-project-context.is-empty > .material-symbols-rounded { color: #98a2b3; }
.tp-context-copy { min-width: 0; flex: 1 1 auto; }
.tp-context-status {
 display: flex; align-items: baseline; gap: 8px; min-width: 0;
}
.tp-project-context strong {
 min-width: 0; overflow: hidden; color: var(--tp-ink);
 font-size: 14px; font-weight: 600; line-height: 1.35;
 text-overflow: ellipsis; white-space: nowrap;
}
.tp-project-context.is-empty strong { font-weight: 600; color: #344054; }
/* 英文 "Inbox" 只是系统容器名，不是标题：它退成状态行右边的低对比小标签。 */
.tp-context-tag {
 flex: 0 0 auto; color: var(--tp-faint); font-size: 11px; font-weight: 550;
 letter-spacing: .02em;
}
.tp-project-context span.tp-project-context-note {
 display: block; margin-top: 3px; color: var(--tp-sub);
 font-size: 12px; line-height: 1.4;
}
/* [更改] / [选择项目] 是**同一个 switcher 的就近锚点**：展开的是同一份轻量下拉
   面板，不是第二套项目列表，也不是大型 Modal。 */
.st-key-task_project_context .stButton button {
 min-height: 32px; padding: 0 10px; font-size: 13px; font-weight: 550;
}
/* 面板是就地展开的紧凑块，不该在正文里撑出一段段落级空白。 */
.st-key-task_project_context [class*="switcher_panel"] { margin-top: 8px !important; }
.st-key-task_project_context [data-testid="stCaptionContainer"] p {
 color: var(--tp-sub); font-size: 12px;
}

/* ---------- 切换项目：轻量下拉面板（不是 Modal，也不是管理页）----------
   大型「切换项目」Modal 已经退休，所以这里没有任何 `section[role="dialog"]` 规则。
   面板是**就地展开的浅色下拉面**：宽度跟随所在列（侧栏里就是侧栏宽度），高度由
   列表自己限制。

   两处锚点（侧栏 selector / 新建任务页的上下文块）共用同一份列表实现；容器 key 都
   含 `switcher_*` 片段，因此下面这组前缀选择器对两者同时生效，不必写两份 CSS。 */
[class*="switcher_panel"] {
 margin: 4px 0 2px !important; padding: 10px 10px 8px;
 border: 1px solid var(--tp-hairline-strong); border-radius: 12px;
 background: var(--tp-surface); box-shadow: 0 8px 20px rgba(15, 35, 70, .07);
}
[class*="switcher_panel"] [data-testid="stCaptionContainer"] {
 margin: 0 0 10px; line-height: 1.5;
}
[class*="switcher_search"] { margin-bottom: 8px; }
[class*="switcher_search"] [data-testid="stWidgetLabel"] { display: none; }
[class*="switcher_search"] [data-testid="stTextInput"] input {
 min-height: 38px; padding-left: 12px; border-radius: 9px !important;
}
/* 列表高度受控：项目多了滚动，面板不会长成整页。 */
[class*="switcher_list"] {
 max-height: min(46vh, 340px); overflow-y: auto; padding: 1px 4px 1px 0;
}
[class*="switcher_list"] > [data-testid="stVerticalBlock"] { gap: 4px; }
[class*="switcher_pick_"] {
 min-width: 0; margin: 0 !important; padding: 0 !important;
 border: 0 !important; background: transparent !important; box-shadow: none !important;
}
/* 每一行是 selectable row（52px 紧凑行），不是一张独立大卡。 */
[class*="switcher_pick_"] .stButton button {
 min-height: 52px; height: 52px; padding: 8px 10px; justify-content: flex-start;
 border: 1px solid transparent; border-radius: 10px; background: transparent;
 color: var(--tp-ink); text-align: left; transition: background .12s ease, border-color .12s ease;
}
[class*="switcher_pick_"] .stButton button:hover {
 border-color: var(--tp-hairline-strong); background: var(--tp-tint-hover);
}
[class*="switcher_pick_"] .stButton button[kind="primary"] {
 border-color: #dbe8ff !important; background: var(--tp-tint-active) !important;
 color: var(--tp-brand-ink) !important;
}
[class*="switcher_pick_"] .stButton button > div {
 width: 100%; justify-content: flex-start !important; align-items: center;
}
[class*="switcher_pick_"] .stButton button [data-testid="stIconMaterial"] {
 flex: 0 0 20px; color: #718096; font-size: 20px;
}
[class*="switcher_pick_"] .stButton button[kind="primary"] [data-testid="stIconMaterial"] {
 color: var(--tp-primary);
}
[class*="switcher_pick_"] .stButton button p {
 margin: 0; overflow: hidden; color: inherit; font-size: 13px !important;
 font-weight: 600; line-height: 1.4; text-align: left; text-overflow: ellipsis;
 white-space: normal;
}
[class*="switcher_pick_"] .stButton button code {
 padding: 2px 6px; border-radius: 999px; background: var(--tp-surface-sunken);
 color: var(--tp-sub); font-family: inherit; font-size: 10.5px; font-weight: 650;
}
[class*="switcher_pick_"] .stButton button[kind="primary"] code {
 background: #dceaff; color: var(--tp-brand-ink);
}
[class*="switcher_footer"] { margin-top: 2px; }
/* Streamlit 的 st.divider() 默认带 32px 上下边距，放进紧凑面板里会撑出大片空白。
   这里收到 8 / 6px：分隔线是分组提示，不是段落间距。 */
[class*="switcher_panel"] hr { margin: 8px 0 6px !important; }
/* 底部低频动作是 secondary action row，不做强 CTA。 */
[class*="switcher_footer"] .stButton > button {
 min-height: 34px; height: 34px; padding: 0 8px; border-color: transparent;
 background: transparent; color: var(--tp-primary); font-size: 12.5px; font-weight: 650;
}
[class*="switcher_footer"] .stButton > button:hover {
 border-color: transparent; background: var(--tp-primary-soft); color: var(--tp-primary-hover);
}

/* ---- 历史任务卡片（Translation Task list）----
   这一页列的是 Translation Tasks，不是 Projects：卡片是"一次具体的文档翻译执行"。
   四行结构固定：标题 / 身份（作者·类型·目标语言·领域）/ 状态·段落·问题数 /
   最近更新 + 卡片**内部**的 contextual CTA。
   定位层级（自下而上）：
     .tp-hcard（视觉，pointer-events:none）
       ← 铺满卡片的透明 button（整卡 → Task Overview）
         ← CTA button（真实按钮，z-index 更高，兄弟节点 → 不冒泡到整卡导航）
   刻意不用整块强蓝背景——保持浅 surface / hairline / low-shadow 体系。 */
[class*="st-key-history_item_"] { margin-bottom:10px; }
[class*="st-key-history_item_"] [data-testid="stMarkdownContainer"] { margin-bottom:0; }
/* 卡片盒是唯一的定位容器：点击层与 CTA 都相对它绝对定位。 */
[class*="st-key-history_cardframe_"] { position:relative; min-width:0; }
[class*="st-key-history_card_"] {
 position:absolute !important; inset:0; z-index:1; margin:0 !important;
 width:auto !important; height:auto !important; opacity:0;
}
[class*="st-key-history_card_"] button {
 width:100%; height:100%; min-height:0; padding:0; opacity:0; cursor:pointer;
 border:0 !important; background:transparent !important; box-shadow:none !important;
}
/* contextual CTA：卡片内部右下角。z-index 高于点击层 → 点击只落到 CTA 自己。 */
[class*="st-key-history_cta_"] {
 position:absolute !important; right:15px; bottom:10px; z-index:3;
 margin:0 !important; width:auto !important;
}
[class*="st-key-history_cta_"] button {
 min-height:28px; height:28px; padding:0 13px;
 font-size:12.5px; font-weight:650; white-space:nowrap;
}
.tp-hcard {
 position:relative; z-index:0; min-width:0;
 padding:10px 16px; border:1px solid var(--tp-hairline); border-radius:10px;
 background:var(--tp-surface); box-shadow:var(--tp-shadow-sm);
 transition:border-color .12s ease, background .12s ease, box-shadow .12s ease;
 /* 卡片本体不接收指针事件：点击一律穿透到铺在它上面的透明 button，
    这样"标题 / 正文空白 / 卡片任意处"是同一条导航路径，不会出现
    "标题被覆盖层挡住"这种半可点的状态。 */
 pointer-events:none;
}
/* hover / 键盘聚焦都要有明显反馈 */
[class*="st-key-history_item_"]:hover .tp-hcard {
 border-color:#c9d7ea; background:var(--tp-tint-hover);
 box-shadow:var(--tp-shadow-md);
}
[class*="st-key-history_item_"]:hover .tp-hcard-title { color:var(--tp-brand-ink); }
[class*="st-key-history_item_"]:has([class*="st-key-history_card_"] button:focus-visible) .tp-hcard {
 border-color:var(--tp-primary); box-shadow:0 0 0 3px var(--tp-focus-ring);
}
.tp-hcard-title {
 /* Streamlit 给 markdown 标题加了 padding（锚点用），会把 18px 的行撑到 47px；
    卡片密度依赖显式清零。 */
 margin:0; padding:0 !important; min-width:0; color:var(--tp-ink);
 font-size:14.5px !important; font-weight:650 !important; line-height:1.3 !important;
 overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.tp-hcard-part {
 display:inline-block; margin-right:7px; padding:1px 6px; border-radius:4px;
 background:var(--tp-surface-sunken); color:var(--tp-sub);
 font-size:10px; font-weight:700; vertical-align:1.5px;
}
.tp-hcard-sub {
 margin-top:2px; color:var(--tp-sub); font-size:11.5px; line-height:1.4;
 overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.tp-hcard-meta {
 display:flex; flex-wrap:nowrap; align-items:center; gap:4px 9px;
 margin-top:6px; min-width:0; overflow:hidden;
 font-size:11px; line-height:1.5;
}
.tp-hcard-chip {
 flex:0 0 auto;
 padding:2px 8px; border-radius:999px; font-size:10.5px; font-weight:700;
 background:var(--tp-surface-sunken); color:#536176;
}
.tp-hcard-chip.is-danger { background:var(--tp-danger-soft); color:#b42318; }
.tp-hcard-chip.is-warn { background:var(--tp-warn-soft); color:var(--tp-warn); }
.tp-hcard-chip.is-active { background:var(--tp-primary-soft); color:var(--tp-brand-ink); }
.tp-hcard-chip.is-done { background:var(--tp-success-soft); color:#147a4a; }
.tp-hcard-chip.is-neutral { background:var(--tp-surface-sunken); color:#536176; }
.tp-hcard-progress, .tp-hcard-issues, .tp-hcard-project, .tp-hcard-updated {
 color:var(--tp-faint); font-size:11px; font-variant-numeric:tabular-nums;
 white-space:nowrap;
}
.tp-hcard-progress { color:var(--tp-sub); font-weight:650; }
.tp-hcard-issues.is-flagged { color:var(--tp-warn); font-weight:650; }
.tp-hcard-project { overflow:hidden; text-overflow:ellipsis; }
/* 第 4 行：左侧最近更新，右侧空出 CTA 的位置（CTA 是绝对定位的真实按钮）。 */
.tp-hcard-foot {
 display:flex; align-items:center; margin-top:4px;
 min-height:28px; padding-right:100px;
 font-size:11px; line-height:1.5;
}
.tp-hcard-updated { margin-left:0; }
.tp-section-title {
 margin: 0 0 8px; color: #172033; font-size: 23px;
 font-weight: 650; line-height: 1.3;
}
.tp-section-sub { margin: 0 0 16px; color: #718096; font-size: 14px; }
.tp-summary { padding: 18px 20px; }
.tp-summary-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px 28px; }
.tp-confirm-card .tp-summary-grid { grid-template-columns: repeat(3,minmax(0,1fr)); }
.tp-summary-item span { display: block; font-size: 12px; color: var(--tp-sub); }
.tp-summary-item strong { display: block; margin-top: 4px; font-size: 14px; color: var(--tp-ink); font-weight: 600; }
.tp-summary-item.is-wide { grid-column: 1 / -1; }
.tp-confirm-stack { display: grid; grid-template-columns: 1.55fr 1fr; gap: 12px; }
.tp-confirm-card { padding: 14px 16px; }
.tp-confirm-head {
 display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
 color: var(--tp-ink); font-size: 14px;
}
.tp-confirm-head .material-symbols-rounded {
 color: var(--tp-primary); font-size: 18px; font-family: "Material Symbols Rounded" !important;
 font-weight: normal; font-style: normal; line-height: 1; font-feature-settings: "liga";
}
.tp-artifact-list { display: grid; grid-template-columns: 1fr; gap: 7px; }
.tp-artifact-row {
 display: grid; grid-template-columns: 28px minmax(0,1fr) auto; align-items: center; gap: 8px;
 min-height: 52px; padding: 7px 10px; border: 1px solid var(--tp-line);
 border-radius: 8px; background: #fbfcfe;
}
.tp-artifact-row > .material-symbols-rounded {
 color: var(--tp-primary); font-size: 19px; font-family: "Material Symbols Rounded" !important;
 font-weight: normal; font-style: normal; line-height: 1; font-feature-settings: "liga";
}
.tp-artifact-row strong { display: block; color: var(--tp-ink); font-size: 13px; }
.tp-artifact-row div span { display: block; margin-top: 2px; color: var(--tp-sub); font-size: 11px; }
.tp-artifact-row b { color: var(--tp-sub); font-size: 10px; font-weight: 650; }
.tp-runtime-card { margin-top: 10px; }
.tp-runtime-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 12px; }
.tp-runtime-grid span { display: block; color: var(--tp-sub); font-size: 11px; }
.tp-runtime-grid strong { display: block; margin-top: 4px; color: var(--tp-ink); font-size: 13px; }
.tp-status { position: relative; padding-left: 13px; }
.tp-status::before {
 content: ""; position: absolute; left: 0; top: 5px; width: 7px; height: 7px;
 border-radius: 50%; background: #98a2b3;
}
.tp-status.is-success::before { background: var(--tp-success); }
.tp-status.is-warning::before { background: #d97706; }
.tp-status.is-error::before { background: var(--tp-danger); }
.tp-flow { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.tp-flow span { font-size: 12px; color: var(--tp-sub); }
.tp-flow b { color: #c4c7ce; font-weight: 500; }

/* ---------- Controls & cards ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
 border: 1px solid var(--tp-line); border-radius: 10px;
 background: var(--tp-surface); box-shadow: none;
}
.stButton > button, [data-testid="stDownloadButton"] > button {
 min-height: 44px; border-radius: var(--tp-radius-md); font-weight: 500; cursor: pointer;
 border: 1px solid var(--tp-line); background: var(--tp-surface); color: var(--tp-ink);
 box-shadow: none; transition: border-color .15s ease, background .15s ease, color .15s ease;
}
.stButton > button:hover, [data-testid="stDownloadButton"] > button:hover {
 border-color: #c9d2df; color: #202a3a; background: #f7f9fc;
}
.stButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"] {
 background: var(--tp-primary); border: 1px solid var(--tp-primary); color: #fff;
 border-radius: 9px; box-shadow: none;
}
.stButton > button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover {
 background: var(--tp-primary-hover); border-color: var(--tp-primary-hover); color: #fff;
}
.stButton > button[kind="primary"]:active,
button[data-testid="stBaseButton-primary"]:active {
 background: var(--tp-primary-active); border-color: var(--tp-primary-active); color: #fff;
}
.stButton > button:disabled,
button[data-testid="stBaseButton-primary"]:disabled {
 opacity: 1; cursor: not-allowed; box-shadow: none;
 background: #d9e5f6 !important; border-color: #d9e5f6 !important; color: #8ca2c0 !important;
}
.stButton > button:focus-visible, [data-testid="stDownloadButton"] > button:focus-visible,
button[data-baseweb="tab"]:focus-visible, summary:focus-visible {
 outline: 3px solid var(--tp-focus-ring) !important;
 outline-offset: 2px;
}

/* ---------- Tooltip 包装层归一化 ----------
   Streamlit 给带 `help=` 的按钮额外包一层 <span data-testid="stTooltipHoverTarget">，
   并内联 `display:flex; justify-content:flex-end; width:100%`。副作用有两个：
   1) 按钮不再是 .stButton 的直接子元素，所有 `.stButton > button` 规则对带 help
      的按钮静默失效（实测 10 个可见按钮里只有 5 个命中）；
   2) 外层没有 flex:1，按钮撑不满容器宽度，侧栏标签会被挤成竖排。
   这里把包装层拉直成 100% 宽的块级，让上、下游选择器都能按预期命中。 */
.stButton:has([data-testid="stTooltipHoverTarget"]) { display:block; width:100%; }
[data-testid="stTooltipHoverTarget"] { flex:1 1 auto; width:100%; min-width:0; }
[data-testid="stTooltipHoverTarget"] > button { width:100%; }
[data-testid="stTooltipIcon"] { display:block; width:100%; min-width:0; }

/* ---------- Tabs ---------- */
[data-testid="stTabs"] [role="tablist"] {
 background: transparent; border-bottom: 1px solid var(--tp-line); padding: 0; gap: 22px;
}
button[data-baseweb="tab"] {
 border-radius: 0 !important; padding: 7px 0 9px; font-weight: 550; color: var(--tp-sub); background: transparent;
}
button[data-baseweb="tab"]:hover { color: var(--tp-primary-hover); }
button[data-baseweb="tab"][aria-selected="true"] {
 background: transparent; color: var(--tp-primary-hover); box-shadow: inset 0 -2px var(--tp-primary);
}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] { display: none !important; }
[data-testid="stButtonGroup"] [role="radio"][aria-checked="true"] {
 background:var(--tp-primary-soft) !important;
 border-color:#69a7f8 !important;
 color:var(--tp-brand-ink) !important;
}

/* ---------- 输入控件 ---------- */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
 border-radius: var(--tp-radius-md) !important; border-color: #dce2ea !important;
 background: var(--tp-surface) !important; color: var(--tp-ink) !important;
 caret-color: var(--tp-ink) !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stNumberInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {
 color: var(--tp-sub) !important; opacity: 1 !important;
}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
[data-baseweb="select"] > div { min-height: 44px; }
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
 border-color: #69a7f8 !important;
 box-shadow: 0 0 0 3px rgba(18,103,232,.14) !important;
}
.stSelectbox .react-aria-ComboBox > div {
 min-height: 44px; border-radius: var(--tp-radius-md) !important;
 border: 1px solid #dce2ea !important;
 background: var(--tp-surface) !important; color: var(--tp-ink) !important;
 box-shadow: none !important;
}
.stSelectbox [role="combobox"] {
 border: 0 !important; border-radius: 8px !important; background: transparent !important;
 color: var(--tp-ink) !important; box-shadow: none !important;
}
.stSelectbox [role="combobox"] *,
.stSelectbox [role="combobox"] svg { color: var(--tp-ink) !important; fill: currentColor !important; }
.stSelectbox .react-aria-ComboBox button {
 background: transparent !important; border: 0 !important; color: var(--tp-ink) !important;
 box-shadow: none !important;
}
.stSelectbox .react-aria-ComboBox button svg,
.stSelectbox .react-aria-ComboBox button [data-testid="stIconMaterial"] {
 color: var(--tp-ink) !important; fill: currentColor !important; visibility: visible !important;
}
[data-baseweb="select"] > div:focus-within {
 border-color: #69a7f8 !important;
 box-shadow: 0 0 0 3px rgba(18,103,232,.14) !important;
}
.stSelectbox .react-aria-ComboBox > div:focus-within {
 border-color: #69a7f8 !important;
 box-shadow: 0 0 0 3px rgba(18,103,232,.14) !important;
}
[role="listbox"] {
 background: var(--tp-surface) !important; color: var(--tp-ink) !important;
}
[role="listbox"] [role="option"] {
 background: var(--tp-surface) !important; color: var(--tp-ink) !important;
}
[role="listbox"] [role="option"][aria-selected="true"] {
 background: var(--tp-primary-soft) !important; color: var(--tp-brand-ink) !important;
}
[role="listbox"] [role="option"]:hover {
 background: #f6f8fb !important; color: var(--tp-ink) !important;
}
[data-testid="stFileUploaderDropzone"] {
 min-height: 148px; border-radius: var(--tp-radius-lg);
 border: 1px dashed var(--tp-border); background: var(--tp-surface);
 box-shadow: var(--tp-shadow-sm);
 transition: all .15s ease;
}
[data-testid="stFileUploaderDropzone"]:hover {
 border-color: #79b4ff; background: #f7fbff;
}
.st-key-source_documents { position: relative; }
.tp-source-label {
 margin: 0 0 8px; color: #202a3a; font-size: 15px; font-weight: 600; line-height: 20px;
}
.st-key-source_documents .tp-upload-copy {
 position: absolute; z-index: 2; pointer-events: none; top: 80px; left: 0; right: 0;
 display: flex; flex-direction: column; align-items: center; text-align: center;
}
.tp-upload-copy .material-symbols-rounded {
 margin-bottom: 5px; color: var(--tp-primary); font-size: 24px;
 font-family: "Material Symbols Rounded" !important; font-weight: normal;
 font-style: normal; line-height: 1; letter-spacing: normal; text-transform: none;
 white-space: nowrap; word-wrap: normal; direction: ltr;
 -webkit-font-feature-settings: "liga"; -webkit-font-smoothing: antialiased;
 font-feature-settings: "liga";
}
.tp-upload-copy span { color: #202a3a; font-size: 14px; font-weight: 600; }
.tp-upload-copy small { margin-top: 7px; color: #8590a2; font-size: 12px; }
.st-key-source_documents [data-testid="stFileUploaderDropzone"] {
 position: relative; padding: 0; align-items: stretch; justify-content: stretch; cursor: pointer;
}
.st-key-source_documents [data-testid="stFileUploaderDropzone"] > div { width: 100%; }
.st-key-source_documents [data-testid="stFileUploaderDropzoneInstructions"] { display: none; }
.st-key-source_documents:not(:has([data-testid="stFileChip"]))
 [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"] {
 position: absolute; inset: 0; width: 100%; height: 100%; transform: none;
 border: 0 !important; background: transparent !important; color: transparent !important;
}
.st-key-source_documents:not(:has([data-testid="stFileChip"]))
 [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"] p,
.st-key-source_documents:not(:has([data-testid="stFileChip"]))
 [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"] svg,
.st-key-source_documents:not(:has([data-testid="stFileChip"]))
 [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"] [data-testid="stIconMaterial"] {
 visibility: hidden;
}
.st-key-source_documents [data-testid="stFileUploaderDropzone"]:focus-within {
 border-color: var(--tp-primary); background: var(--tp-primary-soft);
 box-shadow: inset 0 0 0 1px rgba(18,103,232,.08), 0 0 0 3px rgba(18,103,232,.14);
}
.st-key-source_documents:has([data-testid="stFileChip"]) .tp-upload-copy {
 display: none !important;
}
.st-key-source_documents:has([data-testid="stFileChip"])
 [data-testid="stFileUploaderDropzone"] {
 min-height: 116px; padding: 14px 16px; cursor: default;
 border-style: solid; border-color: var(--tp-line); background: var(--tp-surface);
}
.st-key-source_documents:has([data-testid="stFileChip"])
 [data-testid="stFileUploaderDropzone"]:hover {
 border-color: var(--tp-line); background: var(--tp-surface);
}
.st-key-source_documents [data-testid="stFileChips"] {
 display: block; width: 100%; max-height: none; overflow: visible;
}
.st-key-source_documents [data-testid="stFileChips"] > div,
.st-key-source_documents [data-testid="stFileChip"] {
 width: 100%; max-width: none;
}
.st-key-source_documents [data-testid="stFileChip"] {
 position: relative; display: flex !important; align-items: flex-start;
 min-height: 86px; padding: 2px 0 32px; gap: 12px;
 border-radius: 0; background: transparent !important; color: var(--tp-ink);
}
.st-key-source_documents [data-testid="stFileChip"] > div:first-child {
 width: 36px; height: 36px; flex: 0 0 36px;
 border-radius: 8px; background: var(--tp-primary-soft) !important;
 color: var(--tp-primary) !important;
}
.st-key-source_documents [data-testid="stFileChipIconSpinner"] {
 display: inline-flex !important; color: var(--tp-primary) !important;
}
.st-key-source_documents [data-testid="stFileChip"] > div:nth-child(2) {
 min-width: 0; padding-top: 1px;
}
.st-key-source_documents [data-testid="stFileChipName"] {
 display: block !important; overflow: hidden; color: var(--tp-ink) !important;
 font-size: 0 !important; font-weight: 600; line-height: 20px;
 text-overflow: ellipsis; white-space: nowrap;
}
.st-key-source_documents [data-testid="stFileChipName"]::before {
 content: attr(title); display: block; overflow: hidden;
 color: var(--tp-ink); font-size: 14px; line-height: 20px;
 text-overflow: ellipsis; white-space: nowrap;
}
.st-key-source_documents [data-testid="stFileChip"] > div:nth-child(2) > div:last-child {
 color: var(--tp-sub) !important; font-size: 12px !important;
}
.st-key-source_documents [data-testid="stFileChipDeleteBtn"] {
 display: flex !important; position: absolute; top: 0; right: 0;
}
.st-key-source_documents [data-testid="stFileChipDeleteBtn"] button {
 width: 30px !important; height: 30px !important; color: #7b8493 !important;
}
.st-key-source_documents [data-testid="stFileChipDeleteBtn"] button:hover {
 color: var(--tp-danger) !important; background: #fef2f2 !important;
}
.st-key-source_documents [data-testid="stFileChip"]::before {
 content: "上传中…"; position: absolute; left: 48px; bottom: 14px;
 color: var(--tp-primary); font-size: 12px; font-weight: 600;
}
.st-key-source_documents [data-testid="stFileChip"]::after {
 content: ""; position: absolute; left: 48px; right: 0; bottom: 2px;
 height: 3px; overflow: hidden; border-radius: 999px;
 background: linear-gradient(90deg, var(--tp-primary-soft) 0%, var(--tp-primary) 50%, var(--tp-primary-soft) 100%);
 background-repeat: no-repeat; background-size: 42% 100%;
 animation: tp-upload-bar 1.15s ease-in-out infinite;
}
.st-key-source_documents [data-testid="stFileUploaderDropzone"] [aria-label="Add files"] {
 display: none !important;
}
.tp-source-file {
 position: relative; display: flex; align-items: center; gap: 12px;
 min-height: 82px; padding: 13px 14px;
 border: 1px solid var(--tp-line); border-radius: 10px; background: var(--tp-surface);
}
.tp-source-file .material-symbols-rounded {
 color: var(--tp-primary); font-size: 22px; font-family: "Material Symbols Rounded" !important;
 font-weight: normal; font-style: normal; line-height: 1; letter-spacing: normal;
 text-transform: none; white-space: nowrap; font-feature-settings: "liga";
}
.tp-source-file .material-symbols-rounded.is-loading { animation: tp-spin .8s linear infinite; }
.tp-source-file-copy { min-width: 0; flex: 1; }
.tp-source-file-copy strong {
 display: -webkit-box; overflow: hidden; color: var(--tp-ink); font-size: 14px;
 line-height: 1.4; overflow-wrap: anywhere; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
}
.tp-source-file-copy span { display: block; margin-top: 3px; color: var(--tp-sub); font-size: 12px; }
.tp-source-file-copy .tp-source-file-status {
 display: inline; margin: 0; color: var(--tp-primary-hover); font-size: 12px;
 font-weight: 600; white-space: nowrap;
}
.tp-source-file-status.is-uploaded, .tp-source-file-status.is-parsing { color: var(--tp-primary); }
.tp-source-file-status.is-parsed { color: var(--tp-success); }
.tp-source-file-status.is-error { color: var(--tp-danger); }
.tp-source-ready {
 position: absolute; right: 14px; bottom: 13px; color: var(--tp-success);
 font-size: 12px; font-weight: 650;
}
@keyframes tp-spin { to { transform: rotate(360deg); } }
@keyframes tp-upload-bar {
 from { background-position: -72% 0; }
 to { background-position: 172% 0; }
}
.st-key-source_file_summary { margin-bottom: 8px; }
.st-key-source_file_card { position: relative; min-height: 82px; }
.st-key-source_file_card .tp-source-file { padding-right: 82px; }
.st-key-source_file_card > [data-testid="stElementContainer"]:has(.tp-source-file) {
 position: relative; z-index: 1;
}
.st-key-source_file_card > [data-testid="stElementContainer"]:has(.stButton) {
 position: absolute !important; right: 8px; top: 8px; z-index: 3;
 width: 36px !important; height: 36px !important;
}
.st-key-source_file_card .stButton {
 width: 36px; height: 36px; margin: 0;
}
.st-key-source_file_card .stButton button {
 min-height: 36px !important; height: 36px !important; width: 36px; padding: 0;
 border-color: transparent !important; color: #7b8493 !important;
 background: transparent !important; box-shadow: none !important;
}
.st-key-source_file_card .stButton button:hover {
 border-color: #fecaca !important; background: #fef2f2 !important;
 color: var(--tp-danger) !important;
}
.st-key-source_file_card .stButton p {
 position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
 overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}
.st-key-target_language_field { max-width: 340px; margin-top: 12px; }
.st-key-target_language_field label,
.st-key-target_language_field [data-testid="stWidgetLabel"] {
 color: #202a3a !important; opacity: 1 !important;
 font-size: 15px !important; font-weight: 600 !important;
}
.tp-field-head { margin-top: 14px; }
.tp-field-head strong { display: block; color: #202a3a; font-size: 15px; font-weight: 600; }
.tp-field-head span { display: block; margin-top: 4px; color: #7c8799; font-size: 13px; }
.st-key-termbase_attach { max-width: 340px; margin-top: 10px; }
.st-key-termbase_attach .stButton > button {
 background: var(--tp-surface) !important; border-color: var(--tp-line) !important;
 color: var(--tp-ink) !important;
}
.st-key-termbase_attach .stButton > button:hover {
 background: #f7f9fc !important; border-color: #c9d2df !important; color: #202a3a !important;
}
.st-key-termbase_picker { max-width: 620px; margin-top: 8px; }
.st-key-termbase_picker [data-testid="stFileUploaderDropzone"] { min-height: 96px; }
.tp-attachment {
 display: flex; align-items: center; min-height: 62px; padding: 11px 13px;
 border: 1px solid var(--tp-line); border-radius: 8px; background: #fff;
}
.tp-attachment strong { display: block; color: var(--tp-ink); font-size: 13px; overflow-wrap: anywhere; }
.tp-attachment span { display: block; margin-top: 3px; color: var(--tp-sub); font-size: 12px; }
.st-key-termbase_attached { max-width: 620px; margin-top: 10px; }
.st-key-termbase_attached [data-testid="stHorizontalBlock"] { align-items: center; }
.st-key-termbase_attached .stButton > button { color: var(--tp-danger); }
/* 操作栏参与正文流：sticky 固定在滚动区底部，滚动到底时停留在文档流末尾，
   不再悬浮覆盖正文。sticky 必须设在包含操作栏的流式 wrapper 上，否则操作栏
   会被自身的短包含块限制而无法吸附到滚动区底部。 */
[data-testid="stMainBlockContainer"] [data-testid="stLayoutWrapper"]:has(.st-key-task_action_bar) {
 position: sticky; bottom: 0; z-index: 20;
}
.st-key-task_action_bar {
 /* margin-top 保证最后一个控件与操作栏之间始终有间距 */
 margin: 48px 0 0; padding: 15px 0; min-height: var(--action-bar-height);
 border-top: 1px solid #e3e8ef; background: rgba(247,248,250,.96);
 -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
}
.st-key-task_action_bar [data-testid="stHorizontalBlock"] { align-items: center; }
.tp-autosave { color: #667085; font-size: 12px; }
.tp-autosave.is-saved { color: var(--tp-success); }
.st-key-task_action_bar button[data-testid="stBaseButton-primary"] {
 min-width: 180px; min-height: 48px; height: 48px;
 border-radius: 9px; font-size: 15px; font-weight: 500;
 transition: background .18s ease, border-color .18s ease, color .18s ease;
}
.st-key-task_action_bar button[data-testid="stBaseButton-secondary"] {
 min-height: 48px; height: 48px; border-radius: 9px; font-size: 15px; font-weight: 500;
}
.st-key-library_nav .stButton > button {
 display: flex; align-items: center; justify-content: flex-start;
 min-height: 48px; height: 48px; gap: 14px; padding-inline: 10px;
 border-radius: var(--tp-radius-md); color: #536176; font-size: 14px;
 font-weight: 400; text-align: left;
}
.st-key-library_nav .stButton > button > div { width: 100%; }
.st-key-library_nav .stButton > button [data-testid="stIconMaterial"] { flex: 0 0 18px; }
.st-key-library_nav .stButton > button [data-testid="stMarkdownContainer"] { flex: 1 1 auto; min-width: 0; }
.st-key-library_nav .stButton > button > div > span {
 display: grid; grid-template-columns: 18px minmax(0,1fr); column-gap: 14px;
 align-items: center; width: 100%;
}
.st-key-library_nav .stButton > button [data-testid="stIconMaterial"] {
 width: 18px; margin: 0; color: #667085; font-size: 18px;
}
.st-key-library_nav .stButton > button:hover { background: #f6f8fb; color: #202a3a; }
.st-key-library_nav .stButton > button[kind="primary"] {
 background: var(--tp-primary-soft); color: var(--tp-brand-ink); font-weight: 500;
}
.st-key-library_nav .stButton > button p { margin: 0; }
/* ---------- Translation strategy ---------- */
.st-key-preset_cards { margin-top: 0; }
.st-key-preset_cards [data-testid="stHorizontalBlock"] { align-items: stretch; gap: 12px; }
/* 三张卡片等高：列容器已随行拉伸，这里让列内链撑满，避免窄屏下
   流程链换行导致卡片参差。 */
.st-key-preset_cards [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
 display: flex; flex-direction: column;
}
.st-key-preset_cards [data-testid="stHorizontalBlock"] [data-testid="stLayoutWrapper"] {
 flex: 1 1 auto;
}
[class*="st-key-preset_card_"] { position: relative; }
[class*="st-key-preset_card_"] > [data-testid="stElementContainer"] { flex: 1 1 auto; }
[class*="st-key-preset_card_"] [data-testid="stElementContainer"] > [data-testid="stMarkdown"],
[class*="st-key-preset_card_"] [data-testid="stMarkdown"] > div,
[class*="st-key-preset_card_"] [data-testid="stMarkdownContainer"] { height: 100%; }
.tp-preset-card {
 min-height: 210px; padding: 18px 18px 16px;
 display: grid; grid-template-rows: auto minmax(34px, auto) minmax(42px, auto) auto;
 row-gap: 10px;
 border: 1.5px solid #dce2ea; border-radius: 12px;
 background: #ffffff; transition: border-color .18s ease, background .18s ease;
}
[class*="st-key-preset_card_"]:hover .tp-preset-card {
 border-color: #c5d1e0; background: #fbfcfe;
}
[class*="st-key-preset_card_"][class*="_selected"] .tp-preset-card {
 border-color: #4e93f4; background: #f7fbff;
}
/* header 行固定 22px：推荐 badge 的行高约 22px，若不固定会让选中卡
   的头部行比其他卡高 2px，破坏三卡横向对齐。 */
.tp-preset-head { display: flex; align-items: center; gap: 10px; min-height: 22px; }
.tp-preset-head .material-symbols-rounded {
 color: #98a2b3; font-family: "Material Symbols Rounded" !important;
 font-size: 18px; font-weight: normal; line-height: 1; font-feature-settings: "liga";
}
[class*="st-key-preset_card_"][class*="_selected"] .tp-preset-head .material-symbols-rounded {
 color: var(--tp-primary);
}
.tp-preset-head strong {
 color: #172033; font-size: 16px; font-weight: 700; line-height: 1.25;
}
[class*="st-key-preset_card_"][class*="_selected"] .tp-preset-head strong {
 color: var(--tp-brand-ink);
}
.tp-preset-badge {
 margin-left: auto; padding: 2px 8px; border-radius: 999px;
 background: var(--tp-primary-soft); color: var(--tp-primary);
 font-size: 11px; font-weight: 600; line-height: 1.6;
}
/* 四个固定槽位：标题 / 结果预期 / 包含的流程 / 可比较指标。 */
.tp-preset-expectation {
 display: flex; align-items: flex-start; min-height: 34px;
}
.tp-preset-expectation strong {
 color: #344054; font-size: 13.5px; font-weight: 650; line-height: 1.5;
}
.tp-preset-flow-wrap {
 display: flex; flex-direction: column; gap: 3px; min-height: 42px;
}
.tp-preset-flow-label {
 color: #98a2b3; font-size: 11px; font-weight: 550; line-height: 1.35;
}
.tp-preset-card .tp-preset-flow {
 margin: 0; color: #536176; font-size: 13px !important;
 font-weight: 500; line-height: 1.45;
}
[class*="st-key-preset_card_"][class*="_selected"] .tp-preset-flow {
 color: #344054;
}
.tp-preset-metrics {
 display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-height: 24px;
}
.tp-preset-metric {
 display: inline-flex; align-items: center; gap: 4px; padding: 4px 7px;
 border: 1px solid #e4e7ec; border-radius: 6px; background: #f8f9fb;
 color: #475467; font-size: 11px; font-weight: 500; line-height: 1.4;
 white-space: nowrap;
}
.tp-preset-metric b { color: #7c8799; font-weight: 550; }
.tp-preset-metric-value { color: #344054; font-weight: 650; }
[class*="st-key-preset_card_"][class*="_selected"] .tp-preset-metric {
 border-color: #dbe7ff; background: var(--tp-primary-soft); color: var(--tp-brand-ink);
}
[class*="st-key-preset_card_"][class*="_selected"] .tp-preset-metric b,
[class*="st-key-preset_card_"][class*="_selected"] .tp-preset-metric-value {
 color: var(--tp-brand-ink);
}
/* ---------- Step 01 Quick Profiling（风格画像与建议） ---------- */
.tp-style-card {
 border: 1px solid #dce2ea; border-radius: 12px; background: #ffffff;
 padding: 18px 20px 16px; margin: 18px 0 10px;
}
.tp-style-card.is-selected { border-color: #4e93f4; background: #f7fbff; }
.tp-style-card-head { display: flex; align-items: center; gap: 8px; }
.tp-style-card-head .material-symbols-rounded {
 color: var(--tp-primary); font-size: 18px; line-height: 1;
 font-family: "Material Symbols Rounded" !important;
}
.tp-style-card-head strong { font-size: 14px; font-weight: 600; color: #202a3a; }
.tp-style-card-head b {
 margin-left: auto; padding: 2px 8px; border-radius: 999px;
 background: var(--tp-primary-soft); color: var(--tp-primary); font-size: 12px; font-weight: 600;
}
.tp-style-card p { margin: 10px 0 0; color: #667085; font-size: 13px; line-height: 1.55; }
.tp-style-name { margin-top: 12px; font-size: 20px; font-weight: 700; color: #172033; }
.tp-style-summary { margin-top: 4px; font-size: 13px; color: #667085; }
.tp-style-reasons { margin-top: 10px; }
.tp-style-reasons span { font-size: 11px; font-weight: 600; color: #8a94a6; }
.tp-style-reasons ul {
 margin: 4px 0 0; padding-left: 16px; color: #5f6b7a;
 font-size: 12.5px; line-height: 1.6;
}
.tp-style-source { margin-top: 10px; font-size: 12px; color: #1f8a57; }
.tp-style-adjust-head { margin: 14px 0 4px; }
.tp-style-adjust-head strong { font-size: 14px; font-weight: 600; color: #202a3a; }
.tp-style-adjust-head span {
 display: block; margin-top: 2px; font-size: 12px; color: #8a94a6;
}
/* “开始智能画像”入口：初始只保留按钮，点击后才出现风格建议卡。
   白色描边 + 品牌蓝文字/图标，与页面次级操作保持一致。 */
.st-key-run_quick_profile { max-width: 420px; }
.st-key-run_quick_profile .stButton > button {
 height: 44px; border: 1px solid var(--tp-border);
 color: var(--tp-brand-ink); font-weight: 600;
 background: var(--tp-surface);
}
.st-key-run_quick_profile .stButton > button:hover {
 border-color: var(--tp-primary); background: var(--tp-primary-soft);
 color: var(--tp-primary);
}
.st-key-run_quick_profile .stButton > button [data-testid="stIconMaterial"] {
 color: var(--tp-primary); font-size: 18px;
}
/* ---------- 首次使用引导 ---------- */
.tp-onboard-card {
 border: 1px solid #dce2ea; border-radius: 12px; background: #ffffff;
 padding: 16px 20px 14px; margin-bottom: 4px;
}
.tp-onboard-card .material-symbols-rounded {
 color: var(--tp-primary); font-size: 18px; line-height: 1;
 font-family: "Material Symbols Rounded" !important;
}
.tp-onboard-card p { margin: 10px 0 0; color: #667085; font-size: 13px; line-height: 1.6; }
.tp-onboard-card ol {
 margin: 6px 0 0; padding-left: 20px; color: #5f6b7a;
 font-size: 13px; line-height: 1.8;
}
[class*="st-key-preset_card_"] .stButton {
 position: absolute; inset: 0; z-index: 3; margin: 0;
}
/* Streamlit 给按钮的 stElementContainer 默认 position: relative，
   会让绝对定位的透明覆盖按钮以 16×22 的按钮容器为包含块，导致整卡
   只有左侧一条窄带可点击。恢复 static 后包含块回到卡片列，按钮才能
   覆盖整张卡片。 */
[class*="st-key-preset_card_"] > [data-testid="stElementContainer"]:has(.stButton) {
 position: static; flex: 0 1 auto;
}
[class*="st-key-preset_card_"] .stButton > button {
 width: 100%; height: 100%; min-height: 0; padding: 0; border: 0 !important;
 background: transparent !important; color: transparent !important; box-shadow: none !important;
}
[class*="st-key-preset_card_"] .stButton > button:focus-visible {
 outline: 3px solid var(--tp-focus-ring) !important; outline-offset: 2px;
}
/* 项目卡片：整卡可点，进入 Project Overview。与预设卡同一套覆盖层手法。
   下面这条规则**只声明 `position: relative`**：它是紧随其后的 `.stButton` 绝对
   覆盖层的定位锚点（覆盖层用 `inset: 0`，没有定位祖先时会逃逸到更外层容器上）。
   它与下面三条 `.stButton*` 规则是一组，不能拆开读。

   卡片自身的全部视觉（padding / 圆角 / 边框 / 背景 / 过渡 / hover）由下方
   Project hub 段落那条**同选择器**规则负责。这里曾残留一套旧声明
   （`margin-bottom: 12px` / `padding: 12px 16px` / `border-radius: 10px` /
   `transition` 与一条 `:hover { border-color: #b9c4d4 }`）：同权重、位置靠前，
   被后者**整条覆盖**，是死代码 —— 已删除，避免读代码时误判真实取值。 */
[class*="st-key-project_row_"] { position: relative; }
[class*="st-key-project_row_"] .stButton {
 position: absolute; inset: 0; z-index: 3; margin: 0;
}
[class*="st-key-project_row_"] > [data-testid="stElementContainer"]:has(.stButton) {
 position: static; flex: 0 1 auto;
}
[class*="st-key-project_row_"] .stButton > button {
 width: 100%; height: 100%; min-height: 0; padding: 0; border: 0 !important;
 background: transparent !important; color: transparent !important; box-shadow: none !important;
}
[class*="st-key-project_row_"] .stButton > button:focus-visible {
 outline: 3px solid var(--tp-focus-ring) !important; outline-offset: 2px;
}
/* ---- Project 管理页 / 项目详情 ----
   卡片 = 一眼看清"这个项目现在在做什么"。它只有**三个区**，中间用留白而不是
   分割线区分，底部用一条 hairline 把"操作 / 元信息"与正文分开：

       ① 身份：图标 · 项目名 · 状态 chip ·（右上 ⋯ 菜单）
       ② 状态：任务摘要（主）→ 一行辅助说明（次）
       ③ 行动：CTA（左）· 知识摘要（中）· 最近更新（右，最弱）

   整卡可点（透明覆盖按钮在 .stButton 层），右侧 overflow menu 由 popover 承担，
   它是**兄弟节点**且 z-index 更高，因此点菜单不会触发整卡导航。 */
.tp-pcard-desc {
 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
 color: var(--tp-sub); font-size: 12.5px; line-height: 1.5;
}
/* 底部操作条：它是卡片的第三个区，靠一条 hairline 与正文分开。flex-wrap 让
   「知识摘要 + 更新时间」在窄列里也不会把 CTA 挤成两行。 */
.tp-pcard-foot {
 margin-top: auto; padding-top: 11px;
 display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
 gap: 4px 14px; color: #667085; font-size: 12px;
 border-top: 1px solid var(--tp-hairline);
}
.tp-chip {
 display: inline-flex; align-items: center; height: 20px; padding: 0 8px;
 border-radius: 999px; font-size: 11.5px; font-weight: 500; line-height: 1;
 background: #eef2f7; color: #475467; border: 1px solid transparent;
}
.tp-chip.is-system { background: #eef4ff; color: #1d4ed8; border-color: #d6e2ff; }
.tp-chip.is-archived { background: #f4f5f7; color: #667085; border-color: #e4e7ec; }
.tp-chip.is-empty { background: #fff7ed; color: #b45309; border-color: #fde3c0; }
.tp-pcard-row {
 position: relative; margin-bottom: 12px; padding: 14px 16px;
 border: 1px solid var(--tp-line); border-radius: 10px;
 background: var(--tp-surface); transition: border-color .15s ease, box-shadow .15s ease;
}
.tp-pcard-row:hover { border-color: #b9c4d4; box-shadow: 0 1px 2px rgba(16,24,40,.05); }
/* overflow menu：绝对定位到卡片右上角，且**不参与整卡点击层**（z-index 更高）。
   容器必须显式 flex + 右对齐：Streamlit 的 vertical block 默认 stretch，
   会让 30px 的按钮被拉成整行宽（实测会把标题盖住）。 */
[class*="st-key-project_menu_"] {
 position: absolute; top: 8px; right: 8px; z-index: 5;
 display: flex; justify-content: flex-end; align-items: center;
 width: auto; margin: 0;
}
[class*="st-key-project_menu_"] [data-testid="stVerticalBlock"],
[class*="st-key-project_menu_"] [data-testid="stLayoutWrapper"] {
 display: flex; justify-content: flex-end; align-items: center;
 width: auto; gap: 0;
}
[class*="st-key-project_menu_"] .stButton,
[class*="st-key-project_menu_"] [data-testid="stPopover"] { width: auto; flex: 0 0 auto; }
[class*="st-key-project_menu_"] .stButton > button,
[class*="st-key-project_menu_"] [data-testid="stPopover"] > button {
 min-height: 30px; height: 30px; width: 30px; padding: 0; margin: 0;
 border: 1px solid transparent; border-radius: 8px; background: transparent;
 color: #667085; box-shadow: none; justify-content: center;
}
[class*="st-key-project_menu_"] .stButton > button:hover,
[class*="st-key-project_menu_"] [data-testid="stPopover"] > button:hover {
 background: #f2f5f9; border-color: #e0e6ef; color: #202a3a;
}
.tp-section-head {
 display: flex; align-items: baseline; justify-content: space-between;
 gap: 12px; margin: 22px 0 10px;
}
.tp-section-head strong { font-size: 14px; font-weight: 600; color: var(--tp-ink); }
.tp-section-head span { color: #7c8799; font-size: 12.5px; }

/* ---------- Project hub ----------
   项目页是一个 **Project Hub**（找到项目 / 看到最近状态 / 进入项目 / 新建 /
   管理 / 查看未分类任务），不是数据库管理页。三条布局规则：

   1. 标题与「新建项目」属于同一个受限 page container（不漂到 viewport 最右）；
   2. 搜索 / 状态 / 排序 / 视图切换是**一个** toolbar，不是散落的表单控件；
   3. 「未分类任务」是轻量系统入口（72–88px），永远不是一张项目卡。 */
[data-testid="stMainBlockContainer"]:has(.st-key-project_hub) {
 width: min(100%, 1240px); max-width: 1240px; box-sizing: border-box;
 padding: 36px 40px 56px;
}
/* 未分类任务工作区与 hub 共用同一受限 page container，返回按钮与标题对齐一致。 */
[data-testid="stMainBlockContainer"]:has(.st-key-project_inbox) {
 width: min(100%, 1240px); max-width: 1240px; box-sizing: border-box;
 padding: 32px 40px 56px;
}
/* 真实项目详情（Command Center）沿用同一个受限 container。 */
[data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header) {
 width: min(100%, 1240px); max-width: 1240px; box-sizing: border-box;
 padding: 32px 40px 56px;
}
/* margin-left / margin-right 刻意**不**在这里覆写：`:has()` 会抬高优先级，
   一旦写死就会盖掉下面窄窗口里的 `margin-left: var(--tp-sidebar-width)`，
   让项目页的内容被固定侧栏压住。 */
.st-key-project_hub { width: 100%; }
/* Vertical rhythm：hub 自己控制段间距（不再叠加 flex gap，避免"有的 40px、
   有的 8px"）。Header 30 / Toolbar 18 / 未分类 30 / 我的项目 heading 16。
   注意 `.st-key-project_hub` **本身**就是那个 stVerticalBlock。 */
.st-key-project_hub { gap: 0; }
.st-key-project_header { margin-bottom: 30px; }
.st-key-project_header [data-testid="stHorizontalBlock"] {
 align-items: center; gap: 28px;
}
.tp-project-header-copy { min-width: 0; }
.tp-project-header-copy h1 {
 margin: 0 !important; padding: 0 !important;
 color: var(--tp-navy); font-size: 30px !important; font-weight: 700;
 line-height: 1.18 !important; letter-spacing: -.025em;
}
.tp-project-header-copy p {
 margin: 7px 0 0; color: var(--tp-sub); font-size: 13.5px !important;
 line-height: 1.5;
}
/* Page header 的动作是 compact CTA（160 × 44），不是整页最重的元素：
   它不能横向吃掉 300px+，也不能在视觉上盖过 page title。
   Streamlit 的 popover 在中间还夹着 wrapper，因此这里用后代选择器。 */
.st-key-project_header_action { display: flex; align-items: flex-end; }
.st-key-project_header_action [data-testid="stPopover"] { width: auto; width: fit-content; }
.st-key-project_header_action [data-testid="stPopover"] button {
 min-width: 160px; min-height: 44px; padding: 0 16px;
 border-radius: 10px; font-weight: 650; box-shadow: none; white-space: nowrap;
}
/* ---- 系统任务区：未分类任务（Inbox）----
   它是 **system collection**（没有归属的任务收纳区），不是用户创建的 Project。
   因此元素语法必须和项目卡明显不同：

     项目卡           = 白面 + 实线 + 静置就有的克制阴影 + 圆角 14 + 富文本层级
     未分类入口       = sunken 面 + 虚线 + 零阴影 + 圆角 12 + 单行说明

   虚线在这里是**有语义的**：它表示"这是系统兜底容器，不是一件被你创建的东西"。
   同时不允许出现整卡 hover 抬升——那种反馈属于可点击的实体对象。 */
.st-key-project_system_zone { margin-bottom: 30px; }
.st-key-project_system_zone > [data-testid="stVerticalBlock"] { gap: 0; }
.st-key-project_system_zone .tp-section-head {
 margin: 0 0 10px; justify-content: flex-start; align-items: center; gap: 8px;
}
.st-key-project_system_zone .tp-section-head strong { font-size: 15px; }
.st-key-project_uncategorized {
 position: relative; min-height: 72px; box-sizing: border-box;
 padding: 14px 16px; margin-bottom: 0;
 border: 1px dashed var(--tp-line); border-radius: 12px;
 background: var(--tp-surface-sunken);
 transition: border-color .15s ease, background .15s ease;
}
.st-key-project_uncategorized:hover {
 border-color: #b9c4d4; background: #eef1f6;
}
.st-key-project_uncategorized > [data-testid="stVerticalBlock"] { gap: 0; }
.st-key-project_uncategorized .stButton {
 position: absolute; inset: 0; z-index: 3; margin: 0;
}
.st-key-project_uncategorized > [data-testid="stElementContainer"]:has(.stButton) {
 position: static; flex: 0 1 auto;
}
.st-key-project_uncategorized .stButton > button {
 width: 100%; height: 100%; min-height: 0; padding: 0; border: 0 !important;
 background: transparent !important; color: transparent !important;
 box-shadow: none !important;
}
.st-key-project_uncategorized .stButton > button:focus-visible {
 outline: 3px solid var(--tp-focus-ring) !important; outline-offset: 2px;
}
.tp-uncat { display: flex; align-items: center; gap: 12px; min-width: 0; }
/* 图标是**系统图标**：中性 sunken 底 + 灰字形，不用项目的 primary 蓝——
   蓝色图标会让未分类入口读起来像"又一个项目"。 */
.tp-uncat-icon {
 display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center;
 width: 32px; height: 32px; border-radius: 9px;
 color: #667085; background: #e7eaf0;
}
.tp-uncat-icon .material-symbols-rounded {
 font-size: 18px; font-family: "Material Symbols Rounded" !important;
}
.tp-uncat-copy { min-width: 0; flex: 1 1 auto;display: flex; flex-direction: column; gap: 4px; }
/* 标题 / count / 查看 在同一行：count 只出现一次，且与 action 右对齐。 */
.tp-uncat-head {
 display: flex; align-items: baseline; justify-content: space-between;
 gap: 14px; min-width: 0;
}
.tp-uncat-right {
 display: inline-flex; align-items: baseline; gap: 12px; flex: 0 0 auto;
}
.tp-uncat-title {
 display: inline-flex; align-items: baseline; gap: 7px; min-width: 0;
 color: var(--tp-ink); font-size: 14px; font-weight: 600;
 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* 英文 "Inbox" 只作为系统容器名出现，且必须低于中文标题一个层级。 */
.tp-uncat-tag {
 flex: 0 0 auto; color: var(--tp-faint); font-size: 11px; font-weight: 550;
 letter-spacing: .02em;
}
.tp-uncat-meta {
 color: var(--tp-sub); font-size: 12.5px;
 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tp-uncat-count {
 color: var(--tp-ink); font-size: 13px; font-weight: 650;
 font-variant-numeric: tabular-nums;
}
.tp-uncat-action {
 color: var(--tp-primary); font-size: 13px; font-weight: 600;
}
/* ---- Toolbar：一个工具栏，四个控件（统一 44px 高） ---- */
.st-key-project_toolbar { margin-top: 0; margin-bottom: 18px; }
.st-key-project_toolbar [data-testid="stHorizontalBlock"] {
 align-items: center; gap: 10px;
}
.st-key-project_toolbar [data-testid="stTextInput"] input,
.st-key-project_toolbar [data-testid="stSelectbox"] [data-baseweb="select"] > div {
 min-height: 44px; border-radius: 10px !important; background: var(--tp-surface);
}
.st-key-project_toolbar [data-testid="stSelectbox"] [data-baseweb="select"] > div {
 border-color: var(--tp-line) !important;
}
.st-key-project_toolbar [data-testid="stTextInput"] input { padding-left: 12px; }
.st-key-project_toolbar [data-testid="stTextInput"] input:focus {
 border-color: var(--tp-primary) !important; box-shadow: 0 0 0 3px var(--tp-focus-ring) !important;
}
.st-key-project_toolbar [data-testid="stWidgetLabel"] { display: none; }
/* Grid / List 是一个 **segmented control**，不是两个独立 action：外框统一、
   内部无间隙、选中态用主色实底 + 白色图标。 */
.st-key-project_view_toggle { display: flex; align-items: flex-end; }
.st-key-project_view_toggle > [data-testid="stVerticalBlock"] { width: auto; gap: 0; }
.st-key-project_view_toggle [data-testid="stHorizontalBlock"] {
 display: inline-flex; align-items: center; gap: 2px; padding: 4px;
 border: 1px solid var(--tp-line); border-radius: 11px;
 background: var(--tp-surface); flex-wrap: nowrap; width: fit-content;
}
.st-key-project_view_toggle [data-testid="stColumn"] {
 width: auto !important; min-width: 0 !important; flex: 0 0 auto !important;
}
.st-key-project_view_toggle .stButton { display: flex; }
.st-key-project_view_toggle .stButton > button {
 width: 36px; min-width: 36px; height: 36px; min-height: 36px;
 padding: 0; margin: 0; border: 0 !important; border-radius: 8px !important;
 background: transparent; color: #667085; box-shadow: none;
 font-size: 15px; line-height: 1;
}
.st-key-project_view_toggle .stButton > button:hover {
 background: #f2f5f9; color: #202a3a;
}
.st-key-project_view_toggle .stButton > button[kind="primary"] {
 background: var(--tp-primary); color: #fff !important; font-weight: 700;
}
.st-key-project_view_toggle .stButton > button[kind="primary"]:hover {
 background: var(--tp-primary-hover); color: #fff !important;
}
.st-key-project_section { margin-top: 0; }
.st-key-project_section .tp-section-head { margin: 0 0 16px; }
.st-key-project_section .tp-section-head strong { font-size: 17px; font-weight: 700; letter-spacing: -.015em; }
.st-key-project_section .tp-section-head.is-inline {
 justify-content: flex-start; align-items: center; gap: 8px;
}
.tp-count-badge {
 display: inline-flex; align-items: center; justify-content: center;
 min-width: 22px; height: 20px; padding: 0 7px; border-radius: 999px;
 background: var(--tp-surface-sunken); color: #475467;
 font-size: 12px; font-weight: 650; font-variant-numeric: tabular-nums;
}
.tp-section-note { color: #7c8799; font-size: 12.5px; }
.st-key-project_grid [data-testid="stHorizontalBlock"] {
 align-items: stretch; gap: 16px; margin-bottom: 0;
}
.st-key-project_grid [data-testid="stColumn"] { min-width: 0; }
.st-key-project_grid [data-testid="stColumn"]:empty { visibility: hidden; }
/* 同一行的卡片必须等高：内容行数不同也不该出现参差的底边。Streamlit 的列是
   block 容器，只有把 stLayoutWrapper → stVerticalBlock → 卡片整条链拉满，
   `height:100%` 才真正生效。选择器必须**只命中这条链**：overflow menu 自己也是
   一个 stVerticalBlock，被一起拉满会让 ⋯ 掉到卡片底部。 */
.st-key-project_grid [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
.st-key-project_grid [data-testid="stLayoutWrapper"]:has(
 > [class*="st-key-project_row_"]),
.st-key-project_grid [class*="st-key-project_row_"] {
 height: 100%;
}
[class*="st-key-project_menu_"] { height: auto; }
.st-key-project_grid [class*="st-key-project_row_"] { height: 100%; }
.st-key-project_grid > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] {
 margin-bottom: 16px;
}
.st-key-project_list [data-testid="stVerticalBlock"] { gap: 8px; }
/* 项目卡：低密度、subtle border、只在高 hover 时抬起来。
   卡片容器本身就是一个 stVerticalBlock，它的默认 `gap:1rem` 会为两个不可见的
   兄弟节点（整卡点击层 / overflow menu）各留出一段空白——那正是旧卡片"面积大、
   信息少"的来源，因此这里显式清零；卡内节奏全部由 `.tp-pcard*` 自己控制。

   刻意删掉静置状态的 box-shadow：网格里 6 张卡各带一层阴影，页面会读起来像
   "6 个同等重要的浮动面板"，而项目卡应该是安静的可扫描单元。阴影只在 hover
   出现，用来表达"这一张是当前指针对象"。 */
[class*="st-key-project_row_"] {
 gap: 0; min-height: 152px; box-sizing: border-box; margin-bottom: 0;
 padding: 18px 20px;
 border: 1px solid var(--tp-line); border-radius: 14px; background: var(--tp-surface);
 box-shadow: none;
 transition: border-color .15s ease, box-shadow .15s ease;
 cursor: pointer;
}
/* Hover：加强边框 + 一级非常轻的阴影。刻意**不**加位移/浮动动画，
   避免卡片在网格里"跳"起来抢注意力。 */
[class*="st-key-project_row_"]:hover {
 border-color: #a9b6c9; box-shadow: var(--tp-shadow-md);
}
/* 卡片三段式要真正"贴底"，必须把内层一起拉满：Streamlit 的列是 block 容器，
   markdown 容器默认不参与拉伸 —— 只给 `.tp-pcard-foot` 写 `margin-top:auto`
   是不够的，footer 会紧贴在正文下面，同一排卡片的底边就参差了。
   这条链只命中"卡片那一棵子树"，不会波及 overflow menu（它自己也是
   stVerticalBlock，被拉满会让 ⋯ 掉到卡片底部）。 */
[class*="st-key-project_row_"] > [data-testid="stElementContainer"]:has(.tp-pcard),
[class*="st-key-project_row_"] > [data-testid="stElementContainer"]:has(.tp-pcard)
 > [data-testid="stMarkdownContainer"] {
 flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0;
}
/* 卡片三段式：head（身份）/ body（状态 + 辅助）/ foot（行动 + 元信息）。 */
.tp-pcard {
 display: flex; flex-direction: column; justify-content: flex-start;
 flex: 1 1 auto; width: 100%; min-height: 114px; gap: 0;
}
.tp-pcard-head {
 display: flex; align-items: center; gap: 9px; min-width: 0;
 padding-right: 34px; margin-bottom: 12px;
}
.tp-pcard-head strong {
 color: var(--tp-ink); font-size: 15px; font-weight: 700; min-width: 0;
 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tp-project-icon {
 display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center;
 width: 28px; height: 28px; border-radius: 8px; color: var(--tp-primary);
 background: var(--tp-primary-soft);
}
.tp-project-icon .material-symbols-rounded {
 font-size: 16px; font-family: "Material Symbols Rounded" !important;
}
/* body：状态摘要是**主**信息，辅助说明（最近工作 / 空态提示）退到同一列的下方。
   两者共用同一条左基线，靠字号与颜色分级，而不是靠加粗 + 换行堆叠。 */
.tp-pcard-body {
 display: flex; flex-direction: column; gap: 5px; min-width: 0;
}
.tp-pcard-work {
 display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 10px;
 color: var(--tp-ink); font-size: 13px;
}
.tp-pcard-work.is-quiet { color: var(--tp-sub); }
.tp-pcard-tasks strong { font-size: 15px; font-weight: 700; }
.tp-pcard-breakdown { color: var(--tp-sub); font-size: 12.5px; }
.tp-pcard-recent {
 display: flex; align-items: baseline; gap: 6px; min-width: 0;
 color: var(--tp-sub); font-size: 12.5px;
}
.tp-pcard-recent.is-quiet { color: #98a2b3; }
/* 空项目：一句**短**的"下一步能做什么"（最长一行），不再是长句式说明。
   它占据的正是"有任务时最近工作"那一行，所以两张卡的节奏一致。 */
.tp-pcard-hint {
 color: #98a2b3; font-size: 12.5px; line-height: 1.5;
 min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tp-pcard-recent-label { flex: 0 0 auto; color: #98a2b3; }
.tp-pcard-recent em {
 flex: 0 1 auto; min-width: 0; font-style: normal; color: #475467;
 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tp-pcard-recent-meta { flex: 0 0 auto; color: var(--tp-sub); }
/* 空项目的 CTA 槽位：给绝对定位的真实按钮留出位置，避免压住更新时间。 */
.tp-pcard-cta-slot { display: inline-block; height: 26px; min-width: 88px; }
/* 底部右侧是一**组**弱元信息（知识摘要 + 最近更新）：它们必须整体右对齐、
   整体比正文轻，而不是各自和 CTA 抢横向空间。 */
.tp-pcard-meta {
 display: inline-flex; align-items: baseline; gap: 12px; min-width: 0;
}
.tp-pcard-knowledge {
 min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
 color: var(--tp-sub);
}
.tp-pcard-updated { flex: 0 0 auto; color: #b0b8c4; font-size: 11.5px; }
/* 空项目卡上的 `+ 创建任务`：lightweight ghost action，不抢「新建项目」的主 CTA。
   它是**兄弟节点**且 z-index 高于整卡点击层，所以点它不会触发 card navigation。
   选择器带 `.st-key-project_section` 前缀：section 里有一条
   `.st-key-project_section .stButton > button { min-height: 40px }` 的规则，
   同权重且更靠后——必须比它更具体，ghost action 才不会被拉成 40px 的大按钮。 */
.st-key-project_section [class*="st-key-project_empty_cta_"] {
 position: absolute; left: 20px; bottom: 16px; z-index: 4;
 width: auto; margin: 0;
}
.st-key-project_section [class*="st-key-project_empty_cta_"] > [data-testid="stVerticalBlock"] {
 width: auto; gap: 0;
}
/* 整卡点击层的 `.stButton { position:absolute; inset:0 }` 会顺着后代选择器命中
   卡内 CTA 的按钮容器，把它压成 0 宽的一条。这里显式恢复它的正常流。 */
.st-key-project_section [class*="st-key-project_empty_cta_"] .stButton {
 position: static; inset: auto; z-index: auto; margin: 0;
 width: auto; display: flex;
}
/* Streamlit 会把带 help 的按钮包在 tooltip span 里，因此 `button` 不是 `.stButton`
   的直接子元素——必须用后代选择器才能命中。 */
.st-key-project_section [class*="st-key-project_empty_cta_"] .stButton button {
 width: auto; min-height: 26px; height: 26px; padding: 0 8px;
 border: 1px solid transparent; border-radius: 7px; background: transparent;
 color: var(--tp-primary); font-size: 12.5px; font-weight: 650;
 box-shadow: none; justify-content: flex-start; white-space: nowrap;
}
.st-key-project_section [class*="st-key-project_empty_cta_"] .stButton button:hover {
 background: var(--tp-primary-soft); border-color: transparent;
 color: var(--tp-primary-hover);
}
.st-key-project_section [class*="st-key-project_empty_cta_"] .stButton button:focus-visible {
 outline: 3px solid var(--tp-focus-ring) !important; outline-offset: 2px;
}
.st-key-project_section [class*="st-key-project_empty_cta_"] .stButton button [data-testid="stIconMaterial"] {
 font-size: 15px;
}
/* 有任务的项目卡：底部左侧显示同一个 ghost CTA（`查看项目`）。
   与 `+ 创建任务` 完全同构——同一位置、同一视觉权重、同一 z-index 关系——
   所以"空项目 → 创建任务、有任务 → 查看项目"读起来是**同一个槽位换了动词**，
   而不是两张风格不同的卡。规则刻意与上面那组分开写：空项目 CTA 的样式块被
   回归测试按字面匹配（它必须是 `.stButton button {` 开头的那一条）。 */
.st-key-project_section [class*="st-key-project_view_cta_"] {
 position: absolute; left: 20px; bottom: 16px; z-index: 4;
 width: auto; margin: 0;
}
.st-key-project_section [class*="st-key-project_view_cta_"] > [data-testid="stVerticalBlock"] {
 width: auto; gap: 0;
}
.st-key-project_section [class*="st-key-project_view_cta_"] .stButton {
 position: static; inset: auto; z-index: auto; margin: 0;
 width: auto; display: flex;
}
.st-key-project_section [class*="st-key-project_view_cta_"] .stButton button {
 width: auto; min-height: 26px; height: 26px; padding: 0 8px;
 border: 1px solid transparent; border-radius: 7px; background: transparent;
 color: var(--tp-primary); font-size: 12.5px; font-weight: 650;
 box-shadow: none; justify-content: flex-start; white-space: nowrap;
}
.st-key-project_section [class*="st-key-project_view_cta_"] .stButton button:hover {
 background: var(--tp-primary-soft); border-color: transparent;
 color: var(--tp-primary-hover);
}
.st-key-project_section [class*="st-key-project_view_cta_"] .stButton button:focus-visible {
 outline: 3px solid var(--tp-focus-ring) !important; outline-offset: 2px;
}
.st-key-project_section [class*="st-key-project_view_cta_"] .stButton button [data-testid="stIconMaterial"] {
 font-size: 15px;
}
/* ---- List View：同一份卡数据，横向排布 ---- */
.tp-prow {
 display: flex; align-items: center; gap: 16px; min-width: 0; width: 100%;
 padding-right: 34px;
}
.tp-prow-main { display: flex; align-items: center; gap: 9px; min-width: 0; flex: 1 1 auto; }
.tp-prow-copy { min-width: 0; }
.tp-prow-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.tp-prow-title strong {
 color: var(--tp-ink); font-size: 14px; font-weight: 650;
 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tp-prow-recent {
 display: flex; align-items: baseline; gap: 6px; min-width: 0; margin-top: 2px;
 color: var(--tp-sub); font-size: 12px;
}
.tp-prow-recent em {
 min-width: 0; font-style: normal; color: #475467;
 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tp-prow-recent-label, .tp-prow-recent-meta { flex: 0 0 auto; color: #98a2b3; }
.tp-prow-facts {
 display: flex; flex-direction: column; align-items: flex-end; gap: 2px;
 flex: 0 0 auto; color: var(--tp-sub); font-size: 12px; text-align: right;
}
.tp-prow-tasks strong { color: var(--tp-ink); font-size: 13px; font-weight: 700; }
.tp-prow-updated {
 flex: 0 0 auto; width: 84px; text-align: right;
 color: #98a2b3; font-size: 11.5px;
}
.st-key-project_list [class*="st-key-project_row_"] { min-height: 68px; padding: 12px 16px; }
.tp-chip.is-archived { background: #f2f4f7; color: #667085; border-color: transparent; }
.tp-project-hub-empty { margin-top: 4px; }
/* Empty project page：说明 + 两个真实入口（创建 / 导入），不是一片空白。 */
.tp-hub-empty { padding: 30px 22px; }
.tp-hub-empty strong { font-size: 16px; }
.st-key-project_section .stButton > button { min-height: 40px; border-radius: 10px; }
/* ---- 未分类任务工作区（Task Inbox）----
   一个任务收纳区，不是项目详情：紧凑 Task Row，整行可点。 */
.st-key-project_inbox { width: 100%; }
.st-key-project_inbox > [data-testid="stVerticalBlock"] { gap: 0.6rem; }
.st-key-project_inbox [data-testid="stHorizontalBlock"] { align-items: center; }
.tp-inbox-title-row { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.tp-inbox-title-row h1 {
 margin: 0; color: var(--tp-navy); font-size: 28px; font-weight: 700;
 line-height: 1.18; letter-spacing: -.025em;
}
.tp-inbox-title-row .tp-count-badge { transform: translateY(-2px); }
.st-key-project_inbox .st-key-inbox_header [data-testid="stHorizontalBlock"] { gap: 14px; }
.st-key-project_inbox [data-testid="stTextInput"] input,
.st-key-project_inbox [data-testid="stSelectbox"] [data-baseweb="select"] > div {
 min-height: 38px; border-radius: 9px !important; background: var(--tp-surface);
}
.st-key-project_inbox [data-testid="stWidgetLabel"] { display: none; }
/* ---- 共享 Task Row（未分类 Inbox / Project Overview / Project Tasks）----
   一个紧凑行，整行可点。行容器用 key 前缀区分页面，样式与 markup 完全共用。 */
.st-key-inbox_list [data-testid="stVerticalBlock"],
.st-key-project_task_list [data-testid="stVerticalBlock"],
.st-key-project_overview_active [data-testid="stVerticalBlock"],
.st-key-project_overview_recent [data-testid="stVerticalBlock"] { gap: 8px; }
[class*="st-key-inbox_row_"],
[class*="st-key-projrow_"] {
 position: relative; min-height: 62px; box-sizing: border-box;
 padding: 11px 14px; margin-bottom: 0; gap: 0;
 border: 1px solid var(--tp-line); border-radius: 11px;
 background: var(--tp-surface); box-shadow: var(--tp-shadow-sm);
 transition: border-color .15s ease, box-shadow .15s ease;
 cursor: pointer;
}
[class*="st-key-inbox_row_"]:hover,
[class*="st-key-projrow_"]:hover {
 border-color: #b9c4d4; box-shadow: var(--tp-shadow-md);
}
[class*="st-key-inbox_row_"] .stButton,
[class*="st-key-projrow_"] .stButton {
 position: absolute; inset: 0; z-index: 3; margin: 0;
}
[class*="st-key-inbox_row_"] > [data-testid="stElementContainer"]:has(.stButton),
[class*="st-key-projrow_"] > [data-testid="stElementContainer"]:has(.stButton) {
 position: static; flex: 0 1 auto;
}
[class*="st-key-inbox_row_"] .stButton > button,
[class*="st-key-projrow_"] .stButton > button {
 width: 100%; height: 100%; min-height: 0; padding: 0; border: 0 !important;
 background: transparent !important; color: transparent !important; box-shadow: none !important;
}
[class*="st-key-inbox_row_"] .stButton > button:focus-visible,
[class*="st-key-projrow_"] .stButton > button:focus-visible {
 outline: 3px solid var(--tp-focus-ring) !important; outline-offset: 2px;
}
.tp-taskrow { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.tp-taskrow-head { display: flex; align-items: center; padding-right: 34px; min-width: 0; }
.tp-taskrow-title {
 color: var(--tp-ink); font-size: 14px; font-weight: 650;
 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tp-taskrow-foot {
 display: flex; align-items: baseline; gap: 8px; min-width: 0;
 color: var(--tp-sub); font-size: 12.5px;
}
.tp-taskrow-meta {
 min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tp-taskrow-meta.is-success { color: #027a48; }
.tp-taskrow-meta.is-info { color: #1d4ed8; }
.tp-taskrow-meta.is-danger { color: #b42318; }
.tp-taskrow-meta.is-warning { color: #b54708; }
.tp-taskrow-meta.is-neutral { color: #667085; }
.tp-taskrow-time { margin-left: auto; flex: 0 0 auto; color: #98a2b3; font-size: 11.5px; }
.tp-taskrow-arrow { flex: 0 0 auto; color: #b9c4d4; font-size: 13px; }
[class*="st-key-inbox_row_"]:hover .tp-taskrow-arrow,
[class*="st-key-projrow_"]:hover .tp-taskrow-arrow { color: var(--tp-primary); }
/* inbox ⋯ 菜单：与项目卡菜单同一套手法（绝对定位、z-index 高于整行点击层）。 */
[class*="st-key-inbox_menu_"] {
 position: absolute; top: 6px; right: 6px; z-index: 5;
 display: flex; justify-content: flex-end; align-items: center;
 width: auto; margin: 0;
}
[class*="st-key-inbox_menu_"] [data-testid="stVerticalBlock"],
[class*="st-key-inbox_menu_"] [data-testid="stLayoutWrapper"] {
 display: flex; justify-content: flex-end; align-items: center;
 width: auto; gap: 0;
}
[class*="st-key-inbox_menu_"] .stButton,
[class*="st-key-inbox_menu_"] [data-testid="stPopover"] { width: auto; flex: 0 0 auto; }
[class*="st-key-inbox_menu_"] .stButton > button,
[class*="st-key-inbox_menu_"] [data-testid="stPopover"] > button {
 min-height: 26px; height: 26px; width: 26px; padding: 0; margin: 0;
 border: 1px solid transparent; border-radius: 8px; background: transparent;
 color: #667085; box-shadow: none; justify-content: center;
}
[class*="st-key-inbox_menu_"] .stButton > button:hover,
[class*="st-key-inbox_menu_"] [data-testid="stPopover"] > button:hover {
 background: #f2f5f9; border-color: #e0e6ef; color: #202a3a;
}
/* 4 列 desktop / 2 列 medium；紧凑高度（84px），不再是一个个高瘦的白盒子。 */
.tp-stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; }
.tp-stat {
 border: 1px solid var(--tp-line); border-radius: 10px; background: var(--tp-surface);
 padding: 12px 14px; min-height: 84px; box-sizing: border-box;
 display: flex; flex-direction: column; justify-content: center; gap: 1px;
}
.tp-stat-label { color: #667085; font-size: 12.5px; }
.tp-stat-value { color: var(--tp-ink); font-size: 22px; font-weight: 600; line-height: 1.25; }
.tp-stat-note { color: #7c8799; font-size: 12px; }
/* summary card 只在 ACTIVE PROJECT 渲染：空项目根本不出这四张卡，因此不再需要
   "空值文案"变体——0 就是 0，配一句短注即可。 */
/* ---- 真实项目 Command Center Header ----
   Header 与 Tabs 是一个整体：`← 返回项目` + 身份行（名称 / 状态 badge / 描述 +
   右侧动作）都收在 `project_detail_header` 里，向下统一留 24px 给 tabs。

   gap / margin 同时写在元素自身和它的 stVerticalBlock 上：Streamlit 把 key class
   放在哪一层是实现细节，两处都写才能保证纵向节奏不随版本漂移。

   间距：主垂直块在相邻区块之间还会加 16px gap，所以 margin 取"目标间距 − 16px"：
   Header → Tabs 渲染值 = 8 + 16 = 24px。 */
.st-key-project_detail_header,
.st-key-project_detail_header > [data-testid="stVerticalBlock"] { gap: 12px; }
.st-key-project_detail_header { margin: 0 0 8px; }
.st-key-project_detail_header [data-testid="stHorizontalBlock"] {
 align-items: flex-start; gap: 28px; flex-wrap: nowrap;
}
.tp-project-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
/* 归一化 Streamlit 的 markdown h1：它的基础样式给 h1 加了 20px / 16px 的纵向
   padding，并且用更靠后的选择器把字号顶到 34px。结果是项目标题比 header 右侧
   的 `+ 新建任务` 低一截（实测标题盒子 77px 高、文字从 +23px 才开始），
   "Header 左右布局稳定"就无从谈起。这里显式压掉 padding 并锁死字号。 */
.tp-project-title-row h1 {
 margin: 0 !important; padding: 0 !important;
 color: var(--tp-navy); font-size: 32px !important; font-weight: 700;
 line-height: 1.18 !important; letter-spacing: -.025em;
}
.tp-project-badge {
 display: inline-flex; align-items: center; height: 22px; padding: 0 9px;
 border-radius: 999px; font-size: 11.5px; font-weight: 600;
 background: #eef4ff; color: #1d4ed8; border: 1px solid #d6e2ff;
}
.tp-project-badge.is-archived {
 background: #f2f4f7; color: #667085; border-color: #e4e7ec;
}
/* CTA 与 ⋯ 是**同一行**的两个元素：容器是 flex-row 且不允许换行，overflow 永远
   不会单独掉到下一行。按钮按内容宽度排布，不吃掉整列。

   注意：`st.container(key=…)` 的 key class 落在 Streamlit 自己的 stVerticalBlock
   上，它默认是 `flex-direction: column` —— 只写 `display: flex` 不会把 CTA 和
   ⋯ 摆成一行（这正是上一版 overflow 掉到第二行的真实原因）。 */
.st-key-project_detail_actions {
 display: flex; flex-direction: row; flex-wrap: nowrap;
 justify-content: flex-end; align-items: center; gap: 8px;
}
.st-key-project_detail_actions > [data-testid="stElementContainer"],
.st-key-project_detail_actions > [data-testid="stLayoutWrapper"] {
 width: auto; flex: 0 0 auto;
}
.st-key-project_detail_menu { width: auto; flex: 0 0 auto; display: flex; }
.st-key-project_detail_actions .stButton { width: auto; flex: 0 0 auto; }
.st-key-project_detail_actions .stButton > button {
 min-height: 40px; padding: 0 16px; width: auto; border-radius: 10px;
 font-weight: 650; white-space: nowrap;
}
.st-key-project_detail_actions [data-testid="stPopover"] { width: auto; flex: 0 0 auto; }
.st-key-project_detail_actions [data-testid="stPopover"] > button {
 min-height: 40px; width: 40px; padding: 0; border-radius: 10px;
 border: 1px solid var(--tp-line); background: var(--tp-surface);
 color: #536176; font-size: 16px; box-shadow: none;
}
.st-key-project_detail_actions [data-testid="stPopover"] > button:hover {
 background: #f2f5f9; border-color: #d0d5dd; color: #202a3a;
}
/* ---- 项目知识摘要 ---- */
.tp-knowledge-line {
 color: var(--tp-ink); font-size: 14px; font-weight: 600;
 letter-spacing: .01em;
}
.tp-knowledge-note { margin: 6px 0 0; color: var(--tp-sub); font-size: 12.5px; }
.tp-knowledge-events { margin-top: 8px; display: grid; gap: 4px; }
.tp-knowledge-event { color: var(--tp-sub); font-size: 12.5px; }
/* Active Project 但知识全为空：只给一行 compact row——不是第二个巨大 dashed 空框。 */
.tp-knowledge-empty-row {
 display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
 padding: 12px 14px; border: 1px solid var(--tp-line); border-radius: 10px;
 background: var(--tp-surface);
}
.tp-knowledge-empty-row strong { color: var(--tp-ink); font-size: 13.5px; font-weight: 600; }
.tp-knowledge-empty-row span { color: var(--tp-sub); font-size: 12.5px; }
.tp-detail-muted { color: #98a2b3; }
/* ---- 空项目 onboarding：整页唯一的 surface ----
   空项目不渲染四张 summary card，也不再并排两个 dashed 空框；所有"下一步"收在
   这一个 block 里（一个 medium CTA + 一个次要入口）。 */
.st-key-project_onboarding,
.st-key-project_onboarding > [data-testid="stVerticalBlock"] { gap: 16px; }
.st-key-project_onboarding {
 max-width: 680px; box-sizing: border-box; padding: 30px 28px;
 border: 1px solid var(--tp-line); border-radius: 14px;
 background: var(--tp-surface);
}
.tp-onboarding-copy h2 {
 margin: 0; color: var(--tp-navy); font-size: 20px; font-weight: 700;
 line-height: 1.3; letter-spacing: -.015em;
}
.tp-onboarding-copy p {
 margin: 10px 0 0; color: var(--tp-sub); font-size: 14px; line-height: 1.62;
}
/* ---- 一级 Tabs：compact left-aligned ----
   四项不四等分页面宽度，而是按内容宽度左对齐、间距 28px，下划线只横跨 tab 组。
   Tabs 与正文的间距同理取"目标 30px − 16px gap" = 14px。 */
.st-key-project_tabbar { position: relative; margin: 0 0 14px; }
.st-key-project_tabbar [data-testid="stHorizontalBlock"] {
 display: flex !important; flex-wrap: nowrap !important; align-items: center;
 gap: 28px !important; width: fit-content !important;
 border-bottom: 1px solid var(--tp-line);
}
.st-key-project_tabbar [data-testid="stColumn"] {
 width: auto !important; max-width: none !important; flex: 0 0 auto !important;
}
.st-key-project_tabbar .stButton { width: auto; }
.st-key-project_tabbar .stButton > button {
 min-height: 38px; padding: 0 2px; width: auto;
 border: 0 !important; border-bottom: 2px solid transparent !important;
 border-radius: 0; background: transparent !important; color: #536176;
 font-size: 14.5px; font-weight: 500; box-shadow: none !important;
}
.st-key-project_tabbar .stButton > button:hover { color: var(--tp-ink); background: #f7f9fc !important; }
.st-key-project_tabbar .stButton > button[kind="primary"] {
 color: var(--tp-brand-ink) !important; font-weight: 600;
 border-bottom-color: var(--tp-primary) !important;
}
/* Project Detail 的 section title 比正文高一档（18px），不再与 body 同号。 */
[data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header)
 .tp-section-head.is-inline strong {
 font-size: 18px; font-weight: 700; letter-spacing: -.015em;
}
.tp-detail-row {
 display: flex; align-items: center; justify-content: space-between; gap: 16px;
 padding: 12px 0; border-bottom: 1px solid var(--tp-line);
}
.tp-detail-row:last-child { border-bottom: 0; }
.tp-detail-label { color: #667085; font-size: 12.5px; }
.tp-detail-value { color: var(--tp-ink); font-size: 14px; }
.tp-empty-card {
 border: 1px dashed var(--tp-line); border-radius: 10px; background: #fbfcfe;
 padding: 26px 20px; text-align: center;
}
.tp-empty-card strong { display: block; color: var(--tp-ink); font-size: 14px; margin-bottom: 6px; }
.tp-empty-card span { color: #667085; font-size: 13px; }

/* ================= Project Detail Visual System =================
   概览 / 任务 / 项目知识 / 设置 四个 tab 共用同一套 shell、容器层级与动作分级。
   这一层存在的唯一理由：让四个 tab 看起来是**同一个产品**，而不是四套独立设计。

   容器层级（三级，不再"什么内容都包一个大白盒"）：
     Level A  shell / section —— 只负责结构与留白，不加重卡片；
     Level B  primary surface —— 主要内容区块（onboarding / active task list /
              知识模块 / 设置分组 / 移入面板），一页只出现两三块；
     Level C  compact row —— task row / info row / knowledge metric / menu item，
              靠分隔线而不是边框分组。

   Spacing rhythm（全子系统统一，不再"每页一个节奏"）：
     Header → Tabs       24px
     Tabs   → Content    30px
     Section→ Section    32px（容器 margin 16 + 主垂直块 gap 16）
     Card padding        20–24px
     Compact row         12–16px
   ------------------------------------------------------------------ */

/* ---- Level B：primary surface ---- */
[class*="st-key-pd_group_"] {
 border: 1px solid var(--tp-line); border-radius: 12px;
 background: var(--tp-surface); padding: 20px 22px; margin: 0 0 16px;
}
[class*="st-key-pd_group_"] > [data-testid="stVerticalBlock"] { gap: 12px; }
/* 危险操作与其他分组同层级，但视觉上明确分开：它不是"又一个普通设置"。 */
.st-key-pd_group_danger { border-color: #f0cfca; background: #fffbfa; }
/* 设置分组里的动作是 management 动作：secondary 描边，按内容宽度，
   不允许出现"连续两个大按钮都像 primary"。 */
[class*="st-key-pd_group_"] .stButton > button {
 border-radius: 9px; font-weight: 600;
}
[class*="st-key-pd_group_"] .stButton { width: fit-content; }
/* 删除是 destructive：红色描边，与同组的管理动作分开。 */
.st-key-pd_danger_action .stButton > button {
 border-color: #f0cfca !important; background: var(--tp-surface);
 color: var(--tp-danger);
}
.st-key-pd_danger_action .stButton > button:hover {
 border-color: #e6b3ac !important; background: var(--tp-danger-soft);
 color: #912018;
}
.st-key-pd_danger_action .stButton > button:disabled {
 border-color: var(--tp-line) !important; background: var(--tp-surface-sunken);
 color: #b9c4d4;
}

/* ---- Section rhythm：Project Detail 内统一 34px（head 18 + 垂直块 gap 16）----
   此前 section head 的 22px 上边距叠加 16px gap 得到 38px，与其他区块的
   16/24px 混在一起，于是"每个 tab 像不同产品"。 */
[data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header) .tp-section-head {
 margin: 18px 0 10px;
}
/* 正文第一个 section 不再叠加 18px：Tabs → Content 就是 30px（14 + 16 gap）。
   注意 `st.container(key=…)` 的 key class 就落在 stVerticalBlock 本身上，所以这里
   是 `> stElementContainer:first-child`，中间不再有 stVerticalBlock。 */
.st-key-project_tab_content > [data-testid="stElementContainer"]:first-child .tp-section-head,
.st-key-project_tab_content > [data-testid="stLayoutWrapper"]:first-child .tp-section-head {
 margin-top: 0;
}

/* ---- Level C：compact row / item ---- */
.tp-pd-row {
 display: flex; align-items: center; justify-content: space-between;
 gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--tp-line);
}
.tp-pd-row:last-child { border-bottom: 0; }

/* ---- 分组标题（设置 / 知识模块共用）---- */
.tp-group-head {
 display: flex; align-items: baseline; justify-content: space-between;
 gap: 12px; min-width: 0;
}
.tp-group-head strong {
 color: var(--tp-ink); font-size: 15px; font-weight: 650; letter-spacing: -.01em;
}
.tp-group-head span { color: #98a2b3; font-size: 12px; }

/* ---- 项目知识：四个 compact module ---- */
[class*="st-key-pd_module_"] {
 border: 1px solid var(--tp-line); border-radius: 12px;
 background: var(--tp-surface); padding: 16px 18px; margin: 0 0 12px;
}
[class*="st-key-pd_module_"] > [data-testid="stVerticalBlock"] { gap: 10px; }
[class*="st-key-pd_module_"] [data-testid="stHorizontalBlock"] {
 align-items: flex-start; gap: 16px;
}
.tp-mod-head { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.tp-mod-title {
 color: var(--tp-ink); font-size: 15px; font-weight: 650; letter-spacing: -.01em;
}
.tp-mod-count {
 display: inline-flex; align-items: center; justify-content: center;
 height: 20px; min-width: 20px; padding: 0 7px; border-radius: 999px;
 background: var(--tp-surface-sunken); color: var(--tp-sub);
 font-size: 11.5px; font-weight: 650;
}
.tp-mod-note { margin: 4px 0 0; color: var(--tp-sub); font-size: 12.5px; line-height: 1.5; }
.tp-mod-empty { margin: 4px 0 0; color: #98a2b3; font-size: 12.5px; line-height: 1.5; }
/* 模块入口是 tertiary text action，不是又一个主按钮：透明底、主色文字、
   贴模块右边缘（同样靠 keyed container 右对齐，而不是靠拉伸按钮）。
   key 前缀刻意与 `pd_module_` 不同，否则模块自身的卡片样式会套到入口容器上。 */
[class*="st-key-pd_kmod_entry_"] {
 display: flex; flex-direction: row; justify-content: flex-end; align-items: flex-start;
}
[class*="st-key-pd_kmod_entry_"] > [data-testid="stElementContainer"],
[class*="st-key-pd_kmod_entry_"] > [data-testid="stLayoutWrapper"] {
 width: auto; flex: 0 0 auto;
}
[class*="st-key-pd_module_"] button {
 min-height: 30px; height: 30px; padding: 0 8px;
 border: 1px solid transparent !important; border-radius: 8px;
 background: transparent !important;
 color: var(--tp-primary) !important; font-size: 12.5px; font-weight: 650;
 box-shadow: none !important; white-space: nowrap;
}
[class*="st-key-pd_module_"] button:hover {
 background: var(--tp-primary-soft) !important; border-color: transparent !important;
 color: var(--tp-primary-hover) !important;
}
/* 知识页顶部：一句话 summary + 右上角低频导出（不再整页底部一个大按钮）。 */
.tp-pd-summary {
 margin: 4px 0 0; color: var(--tp-ink); font-size: 13.5px; font-weight: 600;
 letter-spacing: .01em; line-height: 1.5;
}
.tp-pd-intro {
 margin: 0 0 6px; color: var(--tp-sub); font-size: 13px; line-height: 1.6;
}
.st-key-pd_knowledge_head { margin: 0 0 16px; }
.st-key-pd_knowledge_head [data-testid="stHorizontalBlock"] {
 align-items: flex-start; gap: 16px;
}
.st-key-pd_knowledge_head .tp-section-head { margin: 0; }
/* 导出按钮贴右边缘，且是内容宽度：它是一条 tertiary 动作，不是横幅。
   右对齐靠一个显式的 keyed container（与 header 的 CTA 同一套手法），
   因为 `stColumn:last-child` 在 Streamlit 的列包装层里并不可靠。 */
/* 注意：stVerticalBlock 默认是 `flex-direction: column`，只写 justify-content
   只会把内容压到底部，不会右对齐——必须显式改成 row。 */
.st-key-pd_knowledge_export {
 display: flex; flex-direction: row; justify-content: flex-end; align-items: center;
}
.st-key-pd_knowledge_export > [data-testid="stElementContainer"],
.st-key-pd_knowledge_export > [data-testid="stLayoutWrapper"] {
 width: auto; flex: 0 0 auto;
}
.st-key-pd_knowledge_head button {
 min-height: 32px; height: 32px; padding: 0 12px;
 border: 1px solid var(--tp-line) !important; border-radius: 8px !important;
 background: var(--tp-surface) !important; color: var(--tp-sub) !important;
 font-size: 12.5px; font-weight: 600; box-shadow: none !important; white-space: nowrap;
}
.st-key-pd_knowledge_head button:hover {
 border-color: var(--tp-hairline-strong) !important; color: var(--tp-ink) !important;
 background: var(--tp-tint-hover) !important;
}

/* ---- 任务页：移入面板默认收起，与空态不抢页面主内容 ---- */
.st-key-pd_mover [data-testid="stExpander"] {
 border: 1px solid var(--tp-line) !important; border-radius: 12px !important;
 background: var(--tp-surface); overflow: hidden;
}
.st-key-pd_mover [data-testid="stExpander"] summary {
 min-height: 48px; padding: 0 16px; font-size: 13.5px; font-weight: 600;
 color: var(--tp-ink);
}
.st-key-pd_mover [data-testid="stExpander"] summary:hover { color: var(--tp-brand-ink); }
.st-key-pd_mover [data-testid="stExpanderDetails"] { padding: 4px 16px 16px; }
.st-key-pd_mover [data-testid="stExpander"] summary p { font-size: 13.5px; font-weight: 600; }
/* 移入动作是 secondary：内容宽度即可，不占满整行，也不设最小宽度。 */
.st-key-pd_mover .stButton > button { width: auto; }

/* ---- 任务页空态：compact，不再是一个巨大 dashed 空框 ---- */
.tp-pd-empty {
 display: flex; flex-direction: column; gap: 5px;
 padding: 20px 22px; border: 1px solid var(--tp-line); border-radius: 12px;
 background: var(--tp-surface);
}
.tp-pd-empty strong { color: var(--tp-ink); font-size: 14.5px; font-weight: 650; }
.tp-pd-empty span { color: var(--tp-sub); font-size: 13px; line-height: 1.6; }

/* ---- overflow menu：轻量 popover menu card，不是独立侧栏 ----
   收窄宽度、压紧 padding、用 divider 分组；菜单项是紧凑行，不是大白按钮。
   popover 的 body 可能被 portal 到 body 之外，因此两种作用域都写上。
   选择器一律用 [class*="st-key-pd_menu_..."] 前缀匹配：菜单的 key 必须带
   project_id 才唯一（同一个函数每张卡都跑一次），所以类名是
   st-key-pd_menu_body_<uuid>，写死单类名会一条都不命中。属性选择器与单类
   同为 (0,1,0) 特异性，换成前缀匹配不会改动层叠结果。 */
/* Streamlit 给 popover body 写了 `min-width: 320px`（inline 规则之外的
   `min-width` 会压过我们写的 `width`），所以宽度必须连 min/max 一起锁死，
   否则菜单永远是 320px 宽的大面板。 */
[class*="st-key-pd_menu_"] [data-testid="stPopoverBody"],
div[data-testid="stPopoverBody"]:has([class*="st-key-pd_menu_body"]) {
 width: 214px; min-width: 214px; max-width: 214px;
 padding: 6px; border-radius: 12px;
 border: 1px solid var(--tp-line); box-shadow: var(--tp-shadow-md);
}
[class*="st-key-pd_menu_body"] [data-testid="stVerticalBlock"] { gap: 2px; }
/* 菜单项：普通按钮与下载按钮共用同一套紧凑行外观——两者都必须压掉 Streamlit
   的默认描边，否则菜单里会混着"有框的按钮"和"无框的行"。 */
[class*="st-key-pd_menu_body"] button {
 min-height: 32px; height: 32px; padding: 0 10px; width: 100%;
 justify-content: flex-start; text-align: left;
 border: 1px solid transparent !important; border-radius: 8px !important;
 background: transparent !important; color: var(--tp-ink) !important;
 font-size: 13px; font-weight: 500; box-shadow: none !important;
}
[class*="st-key-pd_menu_body"] button:hover {
 background: var(--tp-tint-hover) !important;
 border-color: transparent !important; color: var(--tp-ink) !important;
}
/* 按钮内部还有一层 wrapper，它自己不是 100% 宽时文字会"看起来居中"。
   这里显式拉满并左对齐，菜单项才是稳定的左对齐行。 */
[class*="st-key-pd_menu_body"] button > div {
 width: 100%; justify-content: flex-start !important; align-items: center;
}
/* 菜单标题是一行 caption，不是可点项。 */
[class*="st-key-pd_menu_body"] [data-testid="stCaptionContainer"] { margin: 2px 0 6px; padding: 0 10px; }
[class*="st-key-pd_menu_body"] [data-testid="stCaptionContainer"] p {
 margin: 0; color: #98a2b3; font-size: 11.5px; font-weight: 650; letter-spacing: .04em;
}
/* 分组分隔线：贴边、更轻。 */
[class*="st-key-pd_menu_body"] hr {
 margin: 5px 6px; border: 0; border-top: 1px solid var(--tp-line);
}
/* destructive：删除单独一组，红色文字，不与普通项混在一起。 */
[class*="st-key-pd_menu_danger"] button { color: var(--tp-danger) !important; }
[class*="st-key-pd_menu_danger"] button:hover {
 background: var(--tp-danger-soft) !important; color: #912018 !important;
}

/* 切换项目 modal 的收紧（宽度 / 行高 / 列表高度 / 底部动作）直接改在它自己的
   规则里，见上面的 "Context project selector" 段落——这里不再重复一份，避免
   同一件事有两个来源。 */

.st-key-strategy_advanced { margin-top: 16px; }
.st-key-strategy_advanced {
 position: relative; border: 1px solid var(--tp-line); border-radius: 10px;
 background: var(--tp-surface); overflow: hidden;
}
.tp-advanced-trigger {
 display: grid; grid-template-columns: auto minmax(0,1fr) auto; align-items: center; gap: 18px;
 height: 50px; min-height: 50px; padding: 0 14px;
}
.tp-advanced-title { display: inline-flex; align-items: center; gap: 8px; color: var(--tp-ink); }
.tp-advanced-title .material-symbols-rounded {
 color: #667085; font-family: "Material Symbols Rounded" !important; font-size: 18px;
 font-weight: normal; line-height: 1; font-feature-settings: "liga";
}
.tp-advanced-title strong { font-size: 14px; font-weight: 600; }
.tp-advanced-summary {
 justify-self: end; color: #7c8799; font-size: 12px; font-weight: 500; line-height: 1.4;
 white-space: nowrap;
}
.tp-advanced-summary.is-adjusted { color: var(--tp-primary-hover); font-weight: 650; }
.st-key-strategy_advanced > [data-testid="stElementContainer"]:has(.stButton) {
 position: absolute; inset: 0 0 auto; z-index: 3; height: 50px;
}
.st-key-strategy_advanced > [data-testid="stElementContainer"]:has(.tp-advanced-trigger) {
 height: 50px;
}
.st-key-strategy_advanced .stButton, .st-key-strategy_advanced .stButton > button {
 width: 100%; height: 50px; min-height: 50px; margin: 0;
}
.st-key-strategy_advanced .stButton > button {
 padding: 0; border: 0 !important; border-radius: 0; background: transparent !important;
 color: transparent !important; box-shadow: none !important;
}
.st-key-strategy_advanced:has(.stButton > button:hover) .tp-advanced-trigger { background: #f8fafc; }
.st-key-strategy_advanced .stButton > button:focus-visible {
 outline: 3px solid var(--tp-focus-ring) !important; outline-offset: -3px;
}
.tp-strategy-state {
 padding: 0; margin: 0 0 22px;
 color: #7c8799; font-size: 12px; font-weight: 400; line-height: 1.5;
}
.tp-strategy-state strong { color: var(--tp-primary-hover); font-weight: 650; }
.st-key-advanced_body {
 gap: 0 !important; border-top: 1px solid var(--tp-line);
 padding: 20px 24px 24px;
}
/* 抵消 Streamlit 对 markdown 容器的 -16px 默认下边距，让上下文行与
   分组标题的间距按声明值精确渲染，不出现文字行重叠。 */
.st-key-advanced_body [data-testid="stMarkdownContainer"] { margin-bottom: 0; }
/* 分组标题：上方 24px 与上一组分开，下方 10px 接本组第一个设置项；
   第一组紧随「当前使用…」上下文行，不再额外加 24px。 */
.tp-advanced-group {
 margin: 24px 0 10px; padding: 0;
 color: #6f7b8d; font-size: 12px; font-weight: 600; line-height: 1.4;
 letter-spacing: 0.01em;
}
.st-key-advanced_body > [data-testid="stElementContainer"]:nth-child(2) .tp-advanced-group {
 margin-top: 0;
}
/* 设置行：单个视觉单元，文本列最宽 640px，开关固定在右侧列。 */
[class*="st-key-strategy_"][class*="_row"] {
 min-height: 62px; margin: 0; justify-content: center;
}
/* 行间细分隔线：设置行各自包在 stLayoutWrapper 里，选择器作用于
   advanced_body 的直接子容器（行包装器 / 只读行容器）。 */
.st-key-advanced_body > [data-testid="stLayoutWrapper"] + [data-testid="stLayoutWrapper"],
.st-key-advanced_body > [data-testid="stElementContainer"]:has(.tp-readonly-setting) + [data-testid="stLayoutWrapper"] {
 border-top: 1px solid #f0f2f5; padding-top: 14px;
}
[class*="st-key-strategy_"][class*="_row"] [data-testid="stHorizontalBlock"] {
 display: grid; grid-template-columns: minmax(0, 640px) minmax(48px, auto);
 justify-content: space-between; align-items: center; column-gap: 32px;
}
[class*="st-key-strategy_"][class*="_row"] [data-testid="stColumn"]:last-child {
 display: flex; align-items: center; justify-content: flex-end; min-width: 48px;
}
[class*="st-key-strategy_"][class*="_row"] [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"],
[class*="st-key-strategy_"][class*="_row"] [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"],
[class*="st-key-strategy_"][class*="_row"] [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] > [data-testid="stCheckbox"] {
 width: 100%;
}
[class*="st-key-strategy_"][class*="_row"] [data-testid="stColumn"]:last-child [data-testid="stCheckbox"] {
 display: flex; justify-content: flex-end;
}
.tp-setting-copy { padding: 0; max-width: 640px; }
.tp-setting-copy strong {
 display: block; color: #202a3a; font-size: 14px; font-weight: 600; line-height: 1.35;
}
.tp-setting-copy span {
 display: block; margin-top: 4px; color: #7a8699; font-size: 12.5px; line-height: 1.55;
}
.st-key-strategy_advanced [data-testid="stToggle"],
.st-key-output_options [data-testid="stToggle"],
.st-key-academic_output_options [data-testid="stToggle"] { margin: 0; }
[class*="st-key-strategy_"][class*="_row"] [data-testid="stToggle"] {
 display: flex; justify-content: flex-end;
}
[class*="st-key-strategy_"][class*="_row"] [data-testid="stToggle"] label {
 min-height: 44px; padding: 0;
}
.st-key-strategy_advanced [data-testid="stToggle"] label,
.st-key-output_options [data-testid="stToggle"] label,
.st-key-academic_output_options [data-testid="stToggle"] label {
 min-height: 38px; padding: 6px 0; color: var(--tp-ink) !important;
}
.st-key-strategy_advanced [data-testid="stToggle"] [role="switch"],
.st-key-output_options [data-testid="stToggle"] [role="switch"],
.st-key-academic_output_options [data-testid="stToggle"] [role="switch"] {
 width: 36px !important; min-width: 36px !important; height: 20px !important;
 background: #c6ceda !important; border-color: #c6ceda !important;
}
label:has(input[role="switch"]) > div:first-of-type {
 width: 36px !important; min-width: 36px !important; height: 20px !important;
 background: #c6ceda !important; border-color: #c6ceda !important;
}
label:has(input[role="switch"]) > div:first-of-type > div {
 width: 16px !important; height: 16px !important;
}
label[data-selected="true"]:has(input[role="switch"]) > div:first-of-type {
 background: var(--tp-primary) !important; border-color: var(--tp-primary) !important;
}
label:has(input[type="checkbox"]:not([role="switch"])) > div:first-of-type {
 background: var(--tp-surface) !important; border-color: #98a2b3 !important;
}
label[data-selected="true"]:has(input[type="checkbox"]:not([role="switch"])) > div:first-of-type {
 background: var(--tp-primary) !important; border-color: var(--tp-primary) !important;
}
.st-key-strategy_advanced [data-testid="stToggle"] label[data-selected="true"] > div:first-of-type,
.st-key-output_options [data-testid="stToggle"] label[data-selected="true"] > div:first-of-type,
.st-key-academic_output_options [data-testid="stToggle"] label[data-selected="true"] > div:first-of-type,
.st-key-output_report label[data-selected="true"] > div:first-of-type,
.st-key-output_annotate label[data-selected="true"] > div:first-of-type,
.st-key-strategy_auto_term label[data-selected="true"] > div:first-of-type,
.st-key-strategy_use_tm label[data-selected="true"] > div:first-of-type,
.st-key-strategy_review label[data-selected="true"] > div:first-of-type,
.st-key-strategy_strict_terms label[data-selected="true"] > div:first-of-type {
 background: var(--tp-primary) !important; border-color: var(--tp-primary) !important;
}
.st-key-strategy_advanced [data-testid="stToggle"] label:has(input:focus-visible) > div:first-of-type,
.st-key-output_options [data-testid="stToggle"] label:has(input:focus-visible) > div:first-of-type,
.st-key-academic_output_options [data-testid="stToggle"] label:has(input:focus-visible) > div:first-of-type,
.st-key-strategy_advanced [data-testid="stCheckbox"] label:has(input:focus-visible) > div:first-of-type,
.st-key-output_options [data-testid="stCheckbox"] label:has(input:focus-visible) > div:first-of-type,
label:has(input[role="switch"]:focus-visible) > div:first-of-type,
label:has(input[type="checkbox"]:not([role="switch"]):focus-visible) > div:first-of-type {
 box-shadow: 0 0 0 3px var(--tp-focus-ring) !important;
}
.st-key-strategy_advanced [data-testid="stToggle"] p,
.st-key-output_options [data-testid="stToggle"] p,
.st-key-academic_output_options [data-testid="stToggle"] p { color: var(--tp-ink) !important; }
.st-key-strategy_advanced [data-testid="stCheckbox"] p,
.st-key-output_options [data-testid="stCheckbox"] p { color: var(--tp-ink) !important; }
.st-key-strategy_advanced [data-testid="stCheckbox"] label > div:first-of-type,
.st-key-output_options [data-testid="stCheckbox"] label > div:first-of-type {
 background: var(--tp-surface) !important; border-color: #98a2b3 !important;
}
.st-key-strategy_advanced [data-testid="stCheckbox"] label[data-selected="true"] > div:first-of-type,
.st-key-output_options [data-testid="stCheckbox"] label[data-selected="true"] > div:first-of-type {
 background: var(--tp-primary) !important; border-color: var(--tp-primary) !important;
}
.st-key-strategy_advanced [data-testid="stCheckbox"] label[data-selected="true"] svg,
.st-key-output_options [data-testid="stCheckbox"] label[data-selected="true"] svg {
 stroke: #fff !important;
}
.st-key-output_options [data-testid="stCaptionContainer"] {
 margin: -8px 0 0; color: var(--tp-sub); font-size: 12px;
}
.st-key-delivery_builder {
 max-width: 980px; margin-top: 18px;
}
[data-testid="stMainBlockContainer"]:has(.st-key-delivery_builder) {
 padding-bottom: 112px;
}
[data-testid="stMainBlockContainer"]:has(.st-key-delivery_builder) .st-key-task_action_bar {
 max-width:980px; margin-top:28px; margin-bottom:16px;
}
.st-key-delivery_preset_selector {
 margin: 18px 0 20px; padding: 14px 16px 13px;
 border: 1px solid var(--tp-hairline-strong); border-radius: 12px;
 background: var(--tp-surface); box-shadow: var(--tp-shadow-sm);
}
.st-key-delivery_preset_selector [data-testid="stHorizontalBlock"] {
 align-items: center; gap: 18px;
}
.st-key-delivery_preset_selector [data-testid="stWidgetLabel"] label {
 color: var(--tp-ink) !important; font-size: 13px !important; font-weight: 650 !important;
}
.st-key-delivery_preset_selector [data-baseweb="select"] {
 min-height: 40px; border-color: #cfd7e3; border-radius: 8px;
}
.tp-delivery-preset-help { padding-top: 22px; }
.tp-delivery-preset-help strong { display:block; color:var(--tp-ink); font-size:13px; font-weight:650; }
.tp-delivery-preset-help span { display:block; margin-top:3px; color:var(--tp-sub); font-size:12px; line-height:1.5; }
.tp-delivery-summary {
 display:flex; align-items:baseline; flex-wrap:wrap; gap:8px 14px;
 margin-top:10px; color:var(--tp-sub); font-size:12px; line-height:1.5;
}
.tp-delivery-summary strong { color:var(--tp-brand-ink); font-size:13px; font-weight:700; }
.tp-delivery-summary span { color:var(--tp-sub); }
.tp-delivery-autosave { display:block; margin-top:2px; }
.tp-delivery-group {
 margin: 0 0 16px; padding: 0 22px 5px; border:1px solid var(--tp-line);
 border-radius:12px; background:var(--tp-surface); box-shadow:none; overflow:hidden;
}
[class*="st-key-delivery_group_"] {
 margin: 0 0 16px; padding: 0 22px 5px; border:1px solid var(--tp-line);
 border-radius:12px; background:var(--tp-surface); box-shadow:none; overflow:hidden;
}
.tp-delivery-group-head {
 display:flex; align-items:baseline; justify-content:space-between; gap:14px;
 padding:17px 0 11px;
}
.tp-delivery-group-head strong { color:var(--tp-ink); font-size:15px; font-weight:700; }
.tp-delivery-group-head span { color:var(--tp-sub); font-size:12px; }
.tp-delivery-group-head b { color:var(--tp-primary); font-size:12px; font-weight:650; white-space:nowrap; }
[class*="st-key-delivery_row_"] {
 min-height:64px; padding:10px 0; border-top:1px solid var(--tp-hairline);
}
[class*="st-key-delivery_row_01"] { border-top:0; }
[class*="st-key-delivery_row_"] [data-testid="stHorizontalBlock"] {
 display:grid; grid-template-columns:28px minmax(0,1fr) auto;
 align-items:center; column-gap:10px;
}
[class*="st-key-delivery_row_"] [data-testid="column"] {
 width:auto !important; min-width:0 !important; flex:initial !important;
}
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] {
 display:flex; align-items:center; justify-content:flex-start; margin:0;
}
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] label {
 min-height:28px; padding:0; color:transparent !important;
}
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] label > div:first-of-type {
 width:18px !important; min-width:18px !important; height:18px !important;
 border-radius:5px; background:#fff !important; border-color:#98a2b3 !important;
}
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] label[data-selected="true"] > div:first-of-type {
 background:var(--tp-primary) !important; border-color:var(--tp-primary) !important;
}
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] label[data-selected="true"] svg {
 stroke:#fff !important; width:14px; height:14px;
}
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] label:has(input:focus-visible) > div:first-of-type {
 box-shadow:0 0 0 3px var(--tp-focus-ring) !important;
}
.tp-delivery-row-copy { min-width:0; }
.tp-delivery-row-copy strong { display:inline; color:var(--tp-ink); font-size:14px; font-weight:650; line-height:1.4; }
.tp-delivery-row-copy span { display:block; margin-top:3px; color:var(--tp-sub); font-size:12.5px; line-height:1.45; }
.tp-format-badge {
 display:inline-flex; align-items:center; justify-content:center; min-height:22px;
 margin-left:8px; padding:2px 7px; border:1px solid #e0e5ec; border-radius:6px;
 background:#f7f8fa; color:#667085; font-size:10.5px; font-weight:700;
 letter-spacing:.03em; line-height:1.35; white-space:nowrap;
}
.tp-delivery-row-meta { align-self:start; padding-top:3px; min-width:72px; text-align:right; }
.tp-delivery-row-nested { margin-left:38px; min-height:57px; padding:7px 0 9px; border-top:0; }
.tp-delivery-row-nested .tp-delivery-row-copy strong { color:#344054; font-size:13px; font-weight:600; }
.tp-delivery-row-nested .tp-delivery-row-copy span { color:#7a8699; font-size:12px; }
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] label[data-disabled="true"] > div:first-of-type,
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] label:has(input:disabled) > div:first-of-type {
 background:#f2f4f7 !important; border-color:#d0d5dd !important; opacity:.8;
}
[class*="st-key-delivery_row_"] [data-testid="stCheckbox"] label:has(input:disabled) ~ * { opacity:.6; }
.st-key-delivery_research_options { margin: 2px 0 12px; padding-top: 8px; border-top:1px solid var(--tp-hairline); }
.st-key-delivery_research_options .tp-output-section-head { margin-top:8px; }
.st-key-delivery_research_options .tp-attachment { background:#fbfcfe; }
.tp-readonly-setting {
 padding: 7px 0 7px;
}
.tp-readonly-head { display: flex; align-items: center; gap: 9px; }
.tp-readonly-setting strong { color: var(--tp-ink); font-size: 14px; font-weight: 550; }
.tp-readonly-setting span { display: block; margin-top: 3px; color: var(--tp-sub); font-size: 12px; }
.tp-readonly-setting b {
 flex: 0 0 auto; padding: 2px 7px; border-radius: 999px; background: #ecfdf3;
 color: #15803d; font-size: 11px; font-weight: 650;
}
/* 高级设置面板内的只读行（基础一致性检查）与开关行使用同一套行节奏；
   Step 03 输出页的只读行保持原样式。 */
.st-key-advanced_body .tp-readonly-setting {
 min-height: 62px; padding: 0;
}
.st-key-advanced_body .tp-readonly-head { display: flex; align-items: center; gap: 8px; }
.st-key-advanced_body .tp-readonly-setting strong {
 color: #202a3a; font-size: 14px; font-weight: 600; line-height: 1.35;
}
.st-key-advanced_body .tp-readonly-setting span {
 display: block; margin-top: 4px; color: #7a8699; font-size: 12.5px; line-height: 1.55;
}
.st-key-advanced_body .tp-readonly-setting b {
 flex: 0 0 auto; padding: 2px 7px; border-radius: 999px;
 background: #eaf8f0; color: #1f8a57;
 font-size: 10.5px; font-weight: 600; line-height: 1.5;
}
.st-key-output_options { max-width: 760px; margin-top: 14px; }
.tp-output-section { margin-top: 18px; }
.tp-output-section-head { margin-bottom: 8px; }
.tp-output-section-head strong { display: block; color: var(--tp-ink); font-size: 14px; }
.tp-output-section-head span { display: block; margin-top: 3px; color: var(--tp-sub); font-size: 12px; }
.st-key-style_output { max-width: 760px; }
.st-key-style_output .stSelectbox { max-width: 340px; }
.tp-style-note {
 margin-top: 8px; padding: 12px 14px; border: 1px solid var(--tp-line);
 border-radius: 8px; background: #fbfcfe;
}
.tp-style-note strong { display: block; margin-bottom: 6px; color: var(--tp-ink); font-size: 12px; }
.tp-style-note ul { margin: 0; padding-left: 18px; }
.tp-style-note li { margin: 3px 0; color: #475467; font-size: 12px; line-height: 1.5; }
.st-key-academic_output_options {
 max-width: 760px; margin-top: 16px; padding-top: 2px; border-top: 1px solid var(--tp-line);
}
.st-key-academic_output_options .stSelectbox { max-width: 520px; }
.st-key-engine_setup_banner [data-testid="stAlert"] {
 border: 1px solid #f6c66a !important; background: #fffbeb !important;
 color: #78350f !important;
}
.st-key-engine_setup_banner [data-testid="stAlert"] p,
.st-key-engine_setup_banner [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
.st-key-engine_setup_banner [data-testid="stAlert"] [data-testid="stIconMaterial"] {
 color: #78350f !important; opacity: 1 !important; visibility: visible !important;
}
.st-key-engine_setup_banner [data-testid="stHorizontalBlock"] { align-items: center; gap: 12px; }
.st-key-engine_setup_banner .stButton > button {
 min-height: 36px; background: #fff; border-color: #f3c35c; color: #92400e;
}
.st-key-analysis_theory { max-width: 520px; margin-top: 8px; }
.tp-report-helper { margin: 0 0 4px; color: var(--tp-sub); font-size: 12px; }

/* ---------- 容器类组件 ---------- */
[data-testid="stExpander"] {
 border: 1px solid var(--tp-line) !important;
 border-radius: 10px !important; background: #fff; box-shadow: none; overflow: hidden;
}
[data-testid="stExpander"] summary { font-weight: 600; color: var(--tp-ink); }
[data-testid="stExpander"] summary:hover { color: var(--tp-primary-hover); }
[data-testid="stAlert"] { border-radius: 8px; }
[data-testid="stAlertContainer"] {
 border: 1px solid var(--tp-line) !important;
 border-radius: 8px !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
 background: #eff6ff !important; border-color: #bfdbfe !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
 background: #ecfdf3 !important; border-color: #b7e2c7 !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
 background: #fff7e6 !important; border-color: #f0cf8a !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
 background: #fff1f0 !important; border-color: #f2c3c0 !important;
}
[data-testid="stAlertContentInfo"],
[data-testid="stAlertContentInfo"] [data-testid="stMarkdownContainer"],
[data-testid="stAlertContentInfo"] p {
 color: #1e40af !important; opacity: 1 !important;
}
[data-testid="stAlertContentSuccess"],
[data-testid="stAlertContentSuccess"] [data-testid="stMarkdownContainer"],
[data-testid="stAlertContentSuccess"] p {
 color: #147a4a !important; opacity: 1 !important;
}
[data-testid="stAlertContentWarning"],
[data-testid="stAlertContentWarning"] [data-testid="stMarkdownContainer"],
[data-testid="stAlertContentWarning"] p {
 color: #8a5a00 !important; opacity: 1 !important;
}
[data-testid="stAlertContentError"],
[data-testid="stAlertContentError"] [data-testid="stMarkdownContainer"],
[data-testid="stAlertContentError"] p {
 color: #b42318 !important; opacity: 1 !important;
}
[data-testid="stAlertContentInfo"] p,
[data-testid="stAlertContentSuccess"] p,
[data-testid="stAlertContentWarning"] p,
[data-testid="stAlertContentError"] p { margin: 0; }
[data-testid="stDataFrame"] {
 border: 1px solid var(--tp-line); border-radius: 12px; overflow: hidden;
}
[data-testid="stProgress"] [role="progressbar"] > div { background: var(--tp-primary); }
[data-testid="stStatusWidget"] {
 border-radius: 14px; border-color: var(--tp-line) !important;
}
.st-key-task_action_bar .stButton button > div > span {
 display: flex; align-items: center; justify-content: center; gap: 8px;
}
.st-key-task_action_bar .stButton button [data-testid="stMarkdownContainer"] { order: 1; }
.st-key-task_action_bar .stButton button [data-testid="stIconMaterial"] { order: 2; }
.st-key-task_action_bar [class*="st-key-back_to_"] button [data-testid="stMarkdownContainer"] { order: 2; }
.st-key-task_action_bar [class*="st-key-back_to_"] button [data-testid="stIconMaterial"] { order: 1; }

/* ---------- 响应式与减少动态效果 ---------- */
@media (max-width: 1439px) {
 :root { --tp-main-gutter: 48px; }
}

@media (max-width: 1279px) {
 :root { --tp-main-gutter: 32px; }
}

@media (max-width: 767px) {
 :root { --tp-main-gutter: 14px; }
 [data-testid="stSidebar"] {
  width: var(--tp-sidebar-width); min-width: var(--tp-sidebar-width);
 }
 [data-testid="stMainBlockContainer"] { width: 100%; padding: 1rem .875rem 3rem; }
 [data-testid="stMainBlockContainer"] {
  width: calc(100% - var(--tp-sidebar-width)); max-width:none;
  margin-left:var(--tp-sidebar-width);
 }
 .tp-title h1 { font-size: 26px; }
 .tp-summary-grid { grid-template-columns: 1fr; gap: 14px; }
 .tp-confirm-card .tp-summary-grid { grid-template-columns: 1fr; }
 .tp-summary-item.is-wide { grid-column: auto; }
 .tp-confirm-stack { grid-template-columns: 1fr; }
 .tp-artifact-list, .tp-runtime-grid { grid-template-columns: 1fr; }
 .st-key-preset_cards [data-testid="stHorizontalBlock"] { flex-direction: column; }
 .tp-advanced-trigger { grid-template-columns: auto minmax(0,1fr) auto; gap: 8px; }
 [data-testid="stTabs"] [role="tablist"] { overflow-x: auto; scrollbar-width: none; }
 [data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar { display: none; }
 button[data-baseweb="tab"] { min-height: 40px; white-space: nowrap; }
 .st-key-target_language_field, .st-key-termbase_attach, .st-key-termbase_picker,
 .st-key-termbase_attached { max-width: none; }
 .st-key-provider_status { position: static; width: auto; }
 [data-testid="stMainBlockContainer"]:not(:has(.tp-workspace-shell)) [data-testid="stHorizontalBlock"] {
  display:block !important;
 }
 [data-testid="stMainBlockContainer"]:not(:has(.tp-workspace-shell)) [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  width:100% !important; max-width:none !important; min-width:0 !important; flex:none !important;
 }
 .st-key-delivery_preset_selector [data-testid="stHorizontalBlock"] {
  display:block !important;
 }
 .tp-delivery-preset-help { padding-top:10px; }
 [class*="st-key-delivery_row_"] [data-testid="stHorizontalBlock"] {
  display:grid !important; grid-template-columns:28px minmax(0,1fr) auto !important;
  align-items:center; column-gap:9px;
 }
 [class*="st-key-delivery_row_"] [data-testid="column"] {
  width:auto !important; max-width:none !important; min-width:0 !important;
  flex:none !important;
 }
 .tp-delivery-group { padding-left:14px; padding-right:14px; }
 .tp-delivery-row-nested { margin-left:28px; }
 .tp-delivery-row-meta { min-width:62px; }
 .tp-delivery-row-copy span { overflow-wrap:anywhere; }
}

@media (max-width: 767px) {
 /* 窄窗口沿用应用级布局：侧栏固定宽度并覆盖在内容之上，容器必须让出这段宽度，
    否则卡片会被侧栏压住一半。这里显式重申，因为 `:has()` 的优先级更高。 */
 [data-testid="stMainBlockContainer"]:has(.st-key-project_hub),
 [data-testid="stMainBlockContainer"]:has(.st-key-project_inbox),
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header) {
  width: calc(100% - var(--tp-sidebar-width)); max-width: none;
  margin-left: var(--tp-sidebar-width); padding: 22px 14px 40px;
 }
 .st-key-project_hub .st-key-project_header [data-testid="stHorizontalBlock"] {
  display: flex !important; flex-direction: column; align-items: stretch;
  gap: 12px;
 }
 /* 详情 header 在窄窗口堆叠：标题 → 描述 → 动作，避免 CTA 压住标题。 */
 .st-key-project_detail_header [data-testid="stHorizontalBlock"] {
  display: flex !important; flex-direction: column; align-items: stretch;
  gap: 12px;
 }
 .st-key-project_detail_actions { justify-content: flex-start; }
 .tp-project-title-row h1 { font-size: 26px; }
 .tp-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
 .tp-project-header-copy h1 { font-size: 26px; }
 .tp-inbox-title-row h1 { font-size: 24px; }
 /* 应用级窄窗口规则把所有 horizontal block 变成 block，但列宽仍是桌面的行内
    宽度，控件会被挤到几像素宽。项目页显式把列拉满，控件恢复可点面积。 */
 .st-key-project_hub [data-testid="stColumn"],
 .st-key-project_inbox [data-testid="stColumn"],
 .st-key-project_detail_header [data-testid="stColumn"] {
  width: 100% !important; max-width: none !important; flex: none !important;
 }
 /* 窄窗口 header 堆叠后，CTA 保持 compact（160 × 44）并左对齐：不拉满整行，
    也不与标题抢注意力。popover 的宽度由 Streamlit 自身收敛为 fit-content，
    因此这里只调对齐，不覆写宽度。 */
 .st-key-project_header_action { align-items: flex-start; }
 /* 应用级窄窗口规则把所有 horizontal block 变成 block（`!important`），会把
    segmented control 的两个图标压到同一格上。这里用同权重但更靠后的选择器
    把它还原成一个并排的 control，并让它的列不再被拉满。 */
 .st-key-project_hub .st-key-project_view_toggle [data-testid="stHorizontalBlock"] {
  display: inline-flex !important; width: fit-content !important;
 }
 .st-key-project_hub .st-key-project_view_toggle [data-testid="stColumn"] {
  width: auto !important; flex: 0 0 auto !important; max-width: none !important;
 }
 .st-key-project_hub .st-key-project_view_toggle { align-items: flex-start; }
 .st-key-project_toolbar [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
 .st-key-project_uncategorized { min-height: 84px; }
 .st-key-project_grid [data-testid="stHorizontalBlock"] { margin-bottom: 12px; }
 [class*="st-key-project_row_"] { min-height: 0; }
 .tp-prow { flex-wrap: wrap; gap: 6px 12px; padding-right: 34px; }
 .tp-prow-facts { align-items: flex-start; text-align: left; }
 .tp-prow-updated { width: auto; }
}

@media (min-width: 768px) and (max-width: 1040px) {
 [data-testid="stMainBlockContainer"]:has(.st-key-project_hub),
 [data-testid="stMainBlockContainer"]:has(.st-key-project_inbox),
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header) {
  padding-left: 28px; padding-right: 28px;
 }
 /* Summary cards：medium 宽度折成 2 列，不做 4 个窄条。 */
 .tp-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* ---- Project Detail：980 / 760 两个窄档 ----
   检查项（1440 / 1280 / 980 / 760）：
     - Header 右侧 `+ 新建任务` 与 `···` 始终同行（nowrap，见上面的基础规则）；
     - Tabs 不挤坏：tab 组按内容宽度左对齐，窄窗口允许横向滚动而不是换行挤压；
     - summary 折成 2 列，不做 4 个窄条；
     - 知识模块的「入口」在窄窗口下移到标题下方，不把标题挤成两行；
     - settings 分组保持单列，卡片不失衡；
     - modal / popover 宽度跟着窗口收，不溢出。 */
@media (max-width: 980px) {
 .tp-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
 .st-key-pd_knowledge_head [data-testid="stHorizontalBlock"],
 [class*="st-key-pd_module_"] [data-testid="stHorizontalBlock"] {
  flex-wrap: wrap;
 }
 .st-key-pd_knowledge_head [data-testid="stColumn"],
 [class*="st-key-pd_module_"] [data-testid="stColumn"] {
  width: 100% !important; max-width: none !important; flex: none !important;
 }
 [class*="st-key-pd_module_"] .stButton { width: 100%; }
 .st-key-project_tabbar [data-testid="stHorizontalBlock"] {
  overflow-x: auto; scrollbar-width: none;
 }
 .st-key-project_tabbar [data-testid="stHorizontalBlock"]::-webkit-scrollbar {
  display: none;
 }
}

@media (max-width: 767px) {
 /* Streamlit 在窄容器下会把 stHorizontalBlock 降级成 display:block，但列上仍是
    百分比宽度（例如 1/6 = 67px），于是右列被压成窄条——「查看全部 →」实测被截成
    「查...」。这里把 Project Detail 内部的行布局恢复成 flex，并让列按内容宽度
    分配：右列拿到它需要的宽度，标题列收缩，两个动作继续贴两边。 */
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header)
  [data-testid="stHorizontalBlock"] {
  display: flex !important; flex-direction: row !important;
  align-items: center; justify-content: space-between;
 }
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header)
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  flex: 0 1 auto !important; width: auto !important; max-width: none !important;
  min-width: 0;
 }
 /* 例外：知识页头部与知识模块在窄窗口下仍然是「标题一行 + 入口一行」，
   不回到左右两列。（选择器与上面的通用规则同级，靠顺序取胜。） */
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header)
  .st-key-pd_knowledge_head [data-testid="stHorizontalBlock"],
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header)
  [class*="st-key-pd_module_"] [data-testid="stHorizontalBlock"] {
  justify-content: flex-start;
 }
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header)
  .st-key-pd_knowledge_head [data-testid="stColumn"],
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header)
  [class*="st-key-pd_module_"] [data-testid="stColumn"] {
  width: 100% !important; flex: none !important;
 }
 /* Tabs 仍然是一行：宽度仍由内容决定（下划线只横跨 tab 组），
   必要时的横向滚动来自上面的 980 档，而不是折成四行。 */
 [data-testid="stMainBlockContainer"]:has(.st-key-project_detail_header)
  .st-key-project_tabbar [data-testid="stHorizontalBlock"] {
  justify-content: flex-start; gap: 18px !important;
 }
 /* 窄窗口下 Level B 的 padding 收到 14–16px：卡片不再吃掉半屏宽度。 */
 [class*="st-key-pd_group_"] { padding: 16px 14px; }
 [class*="st-key-pd_module_"] { padding: 14px; }
 .st-key-pd_knowledge_head [data-testid="stHorizontalBlock"] { gap: 10px; }
 .st-key-project_detail_actions { flex-wrap: nowrap; }
}

@media (prefers-reduced-motion: reduce) {
 *, *::before, *::after {
 scroll-behavior: auto !important;
 transition-duration: .01ms !important;
 animation-duration: .01ms !important;
 animation-iteration-count: 1 !important;
 }
}
"""

# Workspace-specific shell.  The setup flow keeps the existing product shell;
# once a task is open this replaces it with a focused project workspace.
_WORKSPACE_CSS = """
.stApp:has(.tp-workspace-shell) [data-testid="stSidebar"] { display: none !important; }
[data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) {
 width: min(100%, 1440px); max-width: 1440px; margin: 0 auto;
 padding: 10px 32px 44px;
}
.tp-workspace-shell { min-height: 2px; }
.st-key-workspace_exit_actions { margin-bottom:2px; }
.st-key-workspace_exit_actions [data-testid="stHorizontalBlock"] { gap:4px; align-items:center; }
.st-key-workspace_exit_actions .stButton > button {
 min-height:26px; height:26px; padding:0 8px; border-color:transparent; background:transparent;
 color:var(--tp-sub); font-size:12px; justify-content:flex-start;
}
.st-key-workspace_exit_actions .stButton > button:hover {
 border-color:var(--tp-hairline-strong); background:var(--tp-surface); color:var(--tp-ink);
}
.tp-workspace-part {
 display:inline-block; margin-right:8px; padding:1px 7px; border-radius:5px;
 background:var(--tp-surface-sunken); color:var(--tp-sub); font-size:11px;
 font-weight:700; letter-spacing:.01em; vertical-align:1.5px;
}
.tp-workspace-topbar {
 display:flex; align-items:center; justify-content:space-between; gap:16px;
 padding: 12px 16px; border:1px solid var(--tp-hairline-strong);
 border-top:3px solid var(--tp-primary); border-radius:var(--tp-radius-lg);
 background:var(--tp-surface); box-shadow:var(--tp-shadow-sm);
}
.tp-workspace-topbar h1 { margin:0; padding:0 !important; font-size:16px !important; line-height:1.25 !important; }
.tp-workspace-eyebrow { margin-bottom:0; color:var(--tp-faint); font-size:9px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; }
.tp-workspace-meta { margin-top:1px; color:var(--tp-sub); font-size:10.5px; }
.tp-workspace-status { display:flex; align-items:center; gap:8px; color:var(--tp-sub); font-size:11.5px; white-space:nowrap; }
/* 顶栏右侧：交付判断 + 最关键的进度事实，两行压到 46px 内，
   把纵向空间还给正文。 */
.tp-workspace-verdict {
 display:flex; align-items:center; gap:7px; padding:3px 9px; border-radius:999px;
 background:var(--tp-surface-sunken); color:#536176; font-size:11px; font-weight:650;
}
.tp-workspace-verdict.is-ready { background:var(--tp-success-soft); color:#147a4a; }
.tp-workspace-verdict.is-attention { background:var(--tp-warn-soft); color:var(--tp-warn); }
.tp-workspace-verdict.is-blocked { background:var(--tp-danger-soft); color:#b42318; }
.tp-workspace-verdict.is-active { background:#e8f1ff; color:#1d4ed8; }
.tp-workspace-verdict.is-neutral { background:var(--tp-surface-sunken); color:#536176; }
.tp-workspace-right { display:flex; flex-direction:column; align-items:flex-end; gap:5px; }
.tp-workspace-facts { display:flex; align-items:center; gap:10px; color:var(--tp-sub); font-size:10.5px; white-space:nowrap; }
.tp-workspace-facts b { color:var(--tp-ink); font-weight:700; font-variant-numeric:tabular-nums; }
.tp-topbar-progress { width:88px; height:4px; border-radius:2px; background:var(--tp-hairline-strong); overflow:hidden; }
.tp-topbar-progress > span { display:block; height:100%; border-radius:2px; background:var(--tp-primary); transition:width .2s ease; }
.tp-status-dot { width:9px; height:9px; border-radius:50%; background:#f59e0b; }
.tp-status-dot.is-success { background:var(--tp-success); }
.tp-status-dot.is-danger { background:var(--tp-danger); }
.tp-status-dot.is-neutral { background:#94a3b8; }
.tp-workspace-layout { margin-top:6px; }
.st-key-workspace_nav_col, .st-key-workspace_context_col, .st-key-workspace_main_col { min-width:0; }
.st-key-workspace_nav_col {
 position:sticky; top:18px; align-self:flex-start; z-index:10;
 padding-right:14px; border-right:1px solid var(--tp-hairline);
 min-height:calc(100vh - 112px);
}
.tp-workspace-nav-title { margin:0 0 6px; color:var(--tp-faint); font-size:10px; font-weight:750; letter-spacing:.06em; text-transform:uppercase; }
.tp-workspace-nav-caption { margin:0 0 10px; color:var(--tp-sub); font-size:11px; line-height:1.45; }
.st-key-workspace_nav .stButton > button {
 min-height:29px; margin:0; justify-content:flex-start; padding:0 9px;
 border-color:transparent; background:transparent; color:#5b6779; font-size:13px;
 box-shadow:none;
}
.st-key-workspace_nav .stButton > button:hover { background:var(--tp-tint-hover); border-color:transparent; color:var(--tp-ink); }
.st-key-workspace_nav .stButton > button[kind="primary"] {
 background:var(--tp-tint-active); border-color:transparent; color:var(--tp-brand-ink); font-weight:650;
}
.st-key-workspace_nav [class*="st-key-workspace_nav_item_"] {
 margin:1px 0; border-radius:8px;
}
.st-key-workspace_nav [class*="st-key-workspace_nav_item_"] [data-testid="stHorizontalBlock"] {
 align-items:center; gap:4px;
}
/* 侧栏状态：不再是独立的文字列——184px 的侧栏放不下"翻译已完成"这种标签，
   它会溢出压到相邻行上。改成"状态决定颜色"：done 保持常规文字色，attention 用红色，
   pending/stale 用琥珀色，muted 整行压暗。完整说明留在按钮的 help 里。 */
.tp-nav-state {
 display:block; min-width:0; color:var(--tp-faint); font-size:10px; font-weight:700;
 line-height:1.2; text-align:right; white-space:nowrap;
}
.tp-nav-state.is-done { color:var(--tp-success); }
.tp-nav-state.is-attention { color:#c0392b; }
.tp-nav-state.is-stale { color:var(--tp-warn); }
.tp-nav-state.is-pending { color:var(--tp-warn); }
.tp-nav-state.is-neutral { color:var(--tp-faint); }
.tp-nav-state.is-muted { color:var(--tp-faint); }
.tp-nav-state.is-empty { color:transparent; }
.tp-nav-state[title] { cursor:help; }
/* 用 `[class~=...]` 精确匹配整个 class token。不能用 `[class*="_pending"]`：
   那是个子串匹配，`st-key-workspace_nav_item_overview_neutral` 里的
   "…vie**w_ne**utral" 不含 "_pending"，但 `*=` 也会命中其它拼接出来的串，
   实测把中性的"概览"一起染上了琥珀色。token 匹配不会误伤。 */
.st-key-workspace_nav [class~="st-key-workspace_nav_item_delivery_attention"] button:not([kind="primary"]) {
 color:#a5342a !important; }
.st-key-workspace_nav [class~="st-key-workspace_nav_item_delivery_active"] button:not([kind="primary"]) {
 color:#1d4ed8 !important; }
.st-key-workspace_nav [class~="st-key-workspace_nav_item_delivery_attention"] button:not([kind="primary"]) span[data-testid="stIconMaterial"] {
 color:#c0392b !important; }
.st-key-workspace_nav [class~="st-key-workspace_nav_item_delivery_pending"] button:not([kind="primary"]),
.st-key-workspace_nav [class~="st-key-workspace_nav_item_delivery_stale"] button:not([kind="primary"]),
.st-key-workspace_nav [class~="st-key-workspace_nav_item_review_attention"] button:not([kind="primary"]),
.st-key-workspace_nav [class~="st-key-workspace_nav_item_review_pending"] button:not([kind="primary"]),
.st-key-workspace_nav [class~="st-key-workspace_nav_item_review_stale"] button:not([kind="primary"]),
.st-key-workspace_nav [class~="st-key-workspace_nav_item_terms_pending"] button:not([kind="primary"]),
.st-key-workspace_nav [class~="st-key-workspace_nav_item_cases_pending"] button:not([kind="primary"]),
.st-key-workspace_nav [class~="st-key-workspace_nav_item_report_attention"] button:not([kind="primary"]),
.st-key-workspace_nav [class~="st-key-workspace_nav_item_qa_attention"] button:not([kind="primary"]) {
 color:#8a5a00 !important; }
.st-key-workspace_nav [class~="st-key-workspace_nav_item_delivery_pending"] button:not([kind="primary"]) span[data-testid="stIconMaterial"],
.st-key-workspace_nav [class~="st-key-workspace_nav_item_delivery_stale"] button:not([kind="primary"]) span[data-testid="stIconMaterial"],
.st-key-workspace_nav [class~="st-key-workspace_nav_item_review_pending"] button:not([kind="primary"]) span[data-testid="stIconMaterial"],
.st-key-workspace_nav [class~="st-key-workspace_nav_item_review_stale"] button:not([kind="primary"]) span[data-testid="stIconMaterial"],
.st-key-workspace_nav [class~="st-key-workspace_nav_item_terms_pending"] button:not([kind="primary"]) span[data-testid="stIconMaterial"],
.st-key-workspace_nav [class~="st-key-workspace_nav_item_cases_pending"] button:not([kind="primary"]) span[data-testid="stIconMaterial"],
.st-key-workspace_nav [class~="st-key-workspace_nav_item_report_attention"] button:not([kind="primary"]) span[data-testid="stIconMaterial"],
.st-key-workspace_nav [class~="st-key-workspace_nav_item_qa_attention"] button:not([kind="primary"]) span[data-testid="stIconMaterial"] {
 color:var(--tp-warn) !important; }
/* "不适用 / 未启用"的导航项：整行退到背景里，hover 才回到正常对比度。 */
.st-key-workspace_nav [class*="st-key-workspace_nav_item_"][class*="_muted"] button:not([kind="primary"]) {
 opacity:.58 !important; }
.st-key-workspace_nav [class*="st-key-workspace_nav_item_"][class*="_muted"] button:not([kind="primary"]):hover,
.st-key-workspace_nav [class*="st-key-workspace_nav_item_"][class*="_muted"] button:not([kind="primary"]):focus-visible {
 opacity:1 !important; }
[class*="st-key-workspace_nav_item_"] .stButton button { transition:background .12s ease, color .12s ease, opacity .12s ease; }
.tp-workspace-nav-item { display:flex; align-items:center; gap:10px; }
.tp-workspace-nav-item i { width:7px; height:7px; border:1.5px solid currentColor; border-radius:50%; }
.tp-workspace-nav-item.is-active i { background:currentColor; }
.st-key-workspace_main_col { padding:0 12px; }
.tp-workspace-main h2 { margin:2px 0 5px; font-size:21px !important; }
.tp-workspace-main h3 { margin:0; font-size:15px !important; }
.tp-section-kicker { color:var(--tp-sub); font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
.tp-section-lead { margin:5px 0 18px; color:var(--tp-sub); font-size:13px; }
.tp-overview-hero { padding:22px 24px; border:1px solid #d8e5fa; border-left:4px solid var(--tp-primary); border-radius:14px; background:linear-gradient(135deg,#f8fbff,#fff); }
/* Hero 的颜色只来自 canonical tone：绿=完成/可交付，蓝=进行中，琥珀=建议，红=阻断，灰=待开始。 */
.tp-overview-hero.is-green { border-color:#b8dfcc; border-left-color:var(--tp-success); background:linear-gradient(135deg,#f3fbf7,#fff); }
.tp-overview-hero.is-blue { border-color:#b9d3f8; border-left-color:var(--tp-primary); background:linear-gradient(135deg,#f5f9ff,#fff); }
.tp-overview-hero.is-amber { border-color:#edd39d; border-left-color:#c47b00; background:linear-gradient(135deg,#fffaf0,#fff); }
.tp-overview-hero.is-red { border-color:#efc1bd; border-left-color:var(--tp-danger); background:linear-gradient(135deg,#fff7f6,#fff); }
.tp-overview-hero.is-gray { border-color:var(--tp-line); border-left-color:#94a3b8; background:linear-gradient(135deg,#f8fafc,#fff); }
.tp-overview-hero .tp-hero-dot { display:inline-block; width:9px; height:9px; margin-right:9px; border-radius:50%; background:#94a3b8; vertical-align:1.5px; }
.tp-overview-hero.is-green .tp-hero-dot { background:var(--tp-success); }
.tp-overview-hero.is-blue .tp-hero-dot { background:var(--tp-primary); }
.tp-overview-hero.is-amber .tp-hero-dot { background:#c47b00; }
.tp-overview-hero.is-red .tp-hero-dot { background:var(--tp-danger); }
.tp-overview-hero small { display:block; margin:-8px 0 0; color:var(--tp-sub); font-size:12px; }
[class*="st-key-overview_hero_actions_"] { margin:-6px 0 6px; }
/* 侧栏顶部的 canonical 状态：与顶栏、Hero 同色同语义。 */
.tp-nav-canonical { display:flex; align-items:center; gap:7px; margin:0 0 10px; padding:6px 9px;
 border:1px solid var(--tp-line); border-radius:8px; background:var(--tp-surface-sunken);
 color:#536176; font-size:12px; font-weight:700; line-height:1.3; }
.tp-nav-canonical i { flex:0 0 auto; width:8px; height:8px; border-radius:50%; background:#94a3b8; }
.tp-nav-canonical.is-success { border-color:#c8e6d5; background:#f1faf5; color:#147a4a; }
.tp-nav-canonical.is-success i { background:var(--tp-success); }
.tp-nav-canonical.is-info { border-color:#c9dcfb; background:#f2f7ff; color:#1d4ed8; }
.tp-nav-canonical.is-info i { background:var(--tp-primary); }
.tp-nav-canonical.is-warning { border-color:#edd39d; background:#fffaf0; color:#8a5a00; }
.tp-nav-canonical.is-warning i { background:#c47b00; }
.tp-nav-canonical.is-danger { border-color:#efc1bd; background:#fff7f6; color:#b42318; }
.tp-nav-canonical.is-danger i { background:var(--tp-danger); }
.tp-nav-canonical.is-neutral { color:var(--tp-faint); }
/* 辅助能力（术语治理 / 案例复核 / 合规与 QA）：移出主 pipeline 的轻量摘要。 */
.tp-capability-strip { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 26px; }
.tp-capability { display:inline-flex; align-items:center; gap:6px; padding:5px 9px;
 border:1px solid var(--tp-line); border-radius:999px; background:#fff; color:var(--tp-sub); font-size:12px; }
.tp-capability i { font-style:normal; color:#94a3b8; }
.tp-capability.is-done i { color:var(--tp-success); }
.tp-capability.is-active i { color:var(--tp-primary); }
.tp-capability.is-attention i { color:#c47b00; }
.tp-capability.is-blocked i { color:var(--tp-danger); }
.tp-capability em { font-style:normal; color:var(--tp-ink); font-weight:650; }
.tp-overview-hero strong { display:block; color:var(--tp-ink); font-size:19px; }
.tp-overview-hero p { margin:8px 0 16px; color:var(--tp-sub); font-size:13px; }
.tp-runtime-panel { margin:0 0 18px; padding:20px 22px; border:1px solid #c9dcfb; border-radius:14px; background:linear-gradient(135deg,#f8fbff,#fff); }
.tp-runtime-kicker { color:var(--tp-primary); font-size:12px; font-weight:750; letter-spacing:.04em; }
.tp-runtime-head { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-top:7px; }
.tp-runtime-head h3 { margin:0; color:var(--tp-ink); font-size:19px !important; }
.tp-runtime-head p { margin:5px 0 0; color:var(--tp-sub); font-size:13px; line-height:1.5; }
.tp-runtime-phase { display:flex; align-items:center; gap:8px; margin-top:17px; color:var(--tp-ink); font-size:14px; font-weight:700; }
.tp-runtime-phase .dot { width:9px; height:9px; border-radius:50%; background:var(--tp-primary); box-shadow:0 0 0 4px #e3efff; }
.tp-runtime-phase.is-warning .dot { background:#c47b00; box-shadow:0 0 0 4px #fff1cf; }
.tp-runtime-phase.is-danger .dot { background:var(--tp-danger); box-shadow:0 0 0 4px #ffe3e3; }
.tp-runtime-meta { display:flex; flex-wrap:wrap; gap:6px 18px; margin-top:8px; color:var(--tp-sub); font-size:12px; font-variant-numeric:tabular-nums; }
.tp-runtime-progress-head { display:flex; justify-content:space-between; gap:12px; margin-top:18px; color:var(--tp-sub); font-size:12px; }
.tp-runtime-progress-head strong { color:var(--tp-ink); font-variant-numeric:tabular-nums; }
.tp-runtime-bar { height:8px; margin-top:7px; overflow:hidden; border-radius:999px; background:#e7eef9; }
.tp-runtime-bar i { display:block; height:100%; border-radius:inherit; background:var(--tp-primary); transition:width .2s ease; }
.tp-runtime-step-title { margin-top:18px; color:var(--tp-ink); font-size:13px; font-weight:750; }
.tp-runtime-steps { margin-top:7px; padding-left:0; list-style:none; }
.tp-runtime-steps li { position:relative; padding:5px 0 5px 24px; color:var(--tp-sub); font-size:12px; }
.tp-runtime-steps li::before { content:"○"; position:absolute; left:0; color:#9aa7b8; font-size:16px; line-height:1; }
.tp-runtime-steps li.is-current { color:var(--tp-ink); font-weight:650; }
.tp-runtime-steps li.is-current::before { content:"●"; color:var(--tp-primary); }
.tp-runtime-steps li.is-done { color:var(--tp-sub); }
.tp-runtime-steps li.is-done::before { content:"✓"; color:var(--tp-success); font-weight:750; }
.tp-runtime-alert { margin-top:13px; padding:9px 11px; border-radius:8px; background:#fff5e6; color:#8a5a00; font-size:12px; line-height:1.5; }
.tp-runtime-alert.is-danger { background:#fff0f0; color:#a12222; }
.tp-runtime-event { display:flex; gap:12px; padding:6px 0; color:var(--tp-sub); font-size:12px; line-height:1.45; }
.tp-runtime-event time { flex:0 0 62px; color:var(--tp-faint); font-variant-numeric:tabular-nums; }
.tp-runtime-event span { color:var(--tp-ink); }
.tp-status-badge { display:inline-flex; align-items:center; gap:6px; padding:5px 10px; border-radius:999px; background:#fff7e6; color:#9a6700; font-size:12px; font-weight:700; }
.tp-status-badge.is-success { background:#eaf8f1; color:#147a4a; }
.tp-status-badge.is-danger { background:#fff0f0; color:#b42318; }
.tp-status-badge.is-neutral { background:#f1f4f8; color:#536176; }
.tp-status-badge.is-info { background:#e8f1ff; color:#1d4ed8; }
.tp-status-badge.is-warning { background:#fff7e6; color:#9a6700; }
.tp-card-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:18px 0 26px; }
.tp-summary-card { min-height:142px; padding:17px 17px 14px; border:1px solid var(--tp-line); border-radius:12px; background:#fff; }
.tp-summary-card strong { display:block; color:var(--tp-ink); font-size:14px; }
.tp-summary-card b { display:block; margin-top:15px; color:var(--tp-ink); font-size:23px; line-height:1; }
.tp-summary-card span { display:block; margin-top:7px; color:var(--tp-sub); font-size:12px; }
.tp-stage-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:18px 0 28px; }
.tp-stage-card { min-height:142px; padding:17px; border:1px solid var(--tp-line); border-radius:12px; background:#fff; }
.tp-stage-card strong { display:block; color:var(--tp-ink); font-size:14px; }
.tp-stage-card b { display:block; margin-top:14px; color:var(--tp-ink); font-size:21px; line-height:1; font-variant-numeric:tabular-nums; }
.tp-stage-card span { display:block; margin-top:8px; color:var(--tp-sub); font-size:12px; }
.tp-stage-card.is-active { border-color:#b9d3f8; background:#f8fbff; }
.tp-stage-card.is-done strong::before { content:"✓"; margin-right:7px; color:var(--tp-success); }
.tp-stage-card.is-active strong::before { content:"●"; margin-right:7px; color:var(--tp-primary); font-size:11px; vertical-align:1px; }
[class*="st-key-overview_stage_card_"] {
 min-height:178px; padding:0 17px 14px; border:1px solid var(--tp-line);
 border-radius:12px; background:#fff;
}
[class*="st-key-overview_stage_card_"]:has(.tp-stage-card-content.is-active) {
 border-color:#b9d3f8; background:#f8fbff;
}
[class*="st-key-overview_stage_card_"] .stButton > button { margin-top:12px; }
.tp-stage-card-content { padding-top:17px; }
.tp-stage-card-content strong { display:block; color:var(--tp-ink); font-size:14px; }
.tp-stage-card-content b { display:block; margin-top:14px; color:var(--tp-ink); font-size:21px; line-height:1; font-variant-numeric:tabular-nums; }
.tp-stage-card-content span { display:block; margin-top:8px; color:var(--tp-sub); font-size:12px; }
.tp-stage-card-content.is-done strong::before { content:"✓"; margin-right:7px; color:var(--tp-success); }
.tp-stage-card-content.is-active strong::before { content:"●"; margin-right:7px; color:var(--tp-primary); font-size:11px; vertical-align:1px; }
.tp-stage-card-content.is-muted strong::before { content:"—"; margin-right:7px; color:var(--tp-faint); }
.tp-stage-card-content.is-attention strong::before { content:"●"; margin-right:7px; color:#c47b00; font-size:11px; vertical-align:1px; }
.tp-stage-card-content.is-blocked strong::before { content:"!"; margin-right:7px; color:var(--tp-danger); }
.tp-overview-progress { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin:0 0 28px; padding:10px 0; border-top:1px solid var(--tp-line-subtle); border-bottom:1px solid var(--tp-line-subtle); }
.tp-progress-step { display:inline-flex; align-items:center; gap:6px; color:var(--tp-ink); font-size:12px; white-space:nowrap; }
.tp-progress-step i { font-style:normal; color:var(--tp-success); font-size:14px; }
.tp-progress-step.is-active i { color:var(--tp-primary); }
.tp-progress-step.is-pending i { color:#94a3b8; }
.tp-progress-step.is-skipped i { color:#94a3b8; }
.tp-progress-step.is-skipped { color:var(--tp-sub); }
.tp-progress-step.is-attention i { color:#c47b00; }
.tp-progress-step.is-blocked i { color:var(--tp-danger); }
.tp-step-connector { color:#b6c0ce; font-size:13px; }
.tp-section-label { margin:0 0 10px; color:var(--tp-ink); font-size:14px; font-weight:700; }
.tp-activity { position:relative; margin-left:5px; padding:5px 0 2px 20px; border-left:1px solid #dbe3ee; }
.tp-activity-date { margin:0 0 5px; color:var(--tp-faint); font-size:12px; font-variant-numeric:tabular-nums; }
.tp-activity-row { position:relative; display:block; padding:8px 0; color:var(--tp-ink); font-size:13px; }
.tp-activity-row::before { content:""; position:absolute; left:-25px; top:14px; width:8px; height:8px; border:2px solid #fff; border-radius:50%; background:#9bbdf0; box-shadow:0 0 0 1px #9bbdf0; }
.tp-activity-row time { display:none; }
.st-key-workspace_context_col {
 position:sticky; top:18px; align-self:flex-start; padding-left:14px;
}
.tp-info-card { padding:14px; border:1px solid var(--tp-line); border-radius:10px; background:#fff; }
.tp-info-card + .tp-info-card { margin-top:10px; }
.tp-info-card h3 { margin:0 0 10px; }
.tp-info-stat { display:flex; align-items:baseline; justify-content:space-between; gap:8px; padding:7px 0; border-bottom:1px solid var(--tp-line-subtle); }
.tp-info-stat:last-child { border-bottom:0; }
.tp-info-stat span { color:var(--tp-sub); font-size:11px; }
.tp-info-stat b { color:var(--tp-ink); font-size:13px; font-variant-numeric:tabular-nums; }
.tp-version-compare { padding:14px; border:1px solid var(--tp-line); border-radius:10px; background:#fff; }
.tp-version-compare h3 { margin:0 0 10px; color:var(--tp-ink); font-size:15px !important; }
.tp-version-row { display:flex; align-items:baseline; justify-content:space-between; gap:10px; padding:8px 0; border-bottom:1px solid var(--tp-line-subtle); }
.tp-version-row:last-of-type { border-bottom:0; }
.tp-version-row span { color:var(--tp-sub); font-size:11px; }
.tp-version-row strong { color:var(--tp-ink); font-size:12px; text-align:right; }
.tp-version-compare-status { margin-top:10px; padding:8px 9px; border-radius:7px; background:#f1f4f8; color:var(--tp-sub); font-size:11px; line-height:1.45; }
.tp-version-compare-status.is-warning { background:#fff7e6; color:#8a5a00; }
.tp-version-compare-status.is-success { background:#eaf8f1; color:#147a4a; }
.tp-version-technical { margin-top:8px; color:var(--tp-faint); font-size:10px; line-height:1.45; }
.tp-truth-banner { margin:0 0 18px; padding:14px 16px; border:1px solid #bdd5fb; border-left:4px solid var(--tp-primary); border-radius:10px; background:#f5f9ff; }
.tp-truth-banner strong { display:block; color:var(--tp-brand-ink); font-size:14px; }
.tp-truth-banner p { margin:5px 0 0; color:var(--tp-sub); font-size:12px; line-height:1.55; }
.tp-truth-banner small { display:block; margin-top:7px; color:#536176; font-size:11px; line-height:1.45; }
.tp-truth-kicker { display:block; margin-bottom:5px; color:var(--tp-primary); font-size:10px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.tp-transport-alert { margin:12px 0; padding:12px 14px; border:1px solid #efc1bd; border-left:4px solid var(--tp-danger); border-radius:9px; background:#fff7f6; color:#7f1d1d; }
.tp-transport-alert strong { display:block; font-size:12px; }
.tp-transport-alert p { margin:5px 0; color:#7f1d1d; font-size:12px; line-height:1.5; }
.tp-transport-alert span { color:#9f3d37; font-size:11px; line-height:1.45; }
.tp-dependency-panel { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin:0 0 16px; padding:14px 16px; border:1px solid #f0d5a1; border-radius:10px; background:#fffaf0; }
.tp-dependency-panel strong { color:#714c00; font-size:13px; }
.tp-dependency-panel p { margin:4px 0 0; color:#8a5a00; font-size:12px; line-height:1.45; }
.tp-dependency-panel span { align-self:center; color:#714c00; font-size:11px; font-weight:650; line-height:1.45; text-align:right; }
.tp-dependency-panel small { align-self:center; color:#8a6a24; font-size:11px; line-height:1.45; }
.tp-case-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:12px; }
.tp-case-head h3 { margin:2px 0 4px; font-size:18px !important; }
.tp-case-head p { margin:0; color:var(--tp-sub); font-size:12px; line-height:1.5; }
.tp-case-validity { flex:0 0 auto; padding:5px 8px; border-radius:999px; font-size:10px; font-weight:800; letter-spacing:.02em; white-space:nowrap; }
.tp-case-validity.is-valid { background:#eaf8f1; color:#147a4a; }
.tp-case-validity.is-stale { background:#fff7e6; color:#8a5a00; }
.tp-case-validity.is-pending { background:#fff8e8; color:#8a5a00; }
.tp-case-role-grid { display:grid; grid-template-columns:90px minmax(0,1fr); gap:5px 10px; margin:0 0 14px; padding:10px 12px; border:1px solid var(--tp-line-subtle); border-radius:8px; background:#fbfcfe; }
.tp-case-role-grid { grid-template-columns:minmax(110px,.42fr) minmax(0,1fr); }
.tp-case-role-grid span { color:var(--tp-sub); font-size:11px; white-space:nowrap; }
.tp-case-role-grid b { color:var(--tp-ink); font-size:11px; font-weight:700; }
.tp-case-text { min-height:110px; margin-bottom:12px; padding:12px; border:1px solid var(--tp-line); border-radius:9px; background:#fff; }
.tp-case-text label { display:block; margin-bottom:7px; color:var(--tp-sub); font-size:10px !important; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
.tp-case-text p { margin:0; color:var(--tp-ink); font-size:12px; line-height:1.7; white-space:pre-wrap; }
.tp-case-detail-label { margin:16px 0 8px; color:var(--tp-sub); font-size:11px; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }
.tp-case-evidence-grid { display:grid; grid-template-columns:1fr 1fr; gap:0 12px; padding:10px 12px; border:1px solid var(--tp-line); border-radius:9px; background:#fbfcfe; }
.tp-case-evidence-grid span, .tp-case-evidence-grid b { padding:6px 0; border-bottom:1px solid var(--tp-line-subtle); font-size:11px; }
.tp-case-evidence-grid span { color:var(--tp-sub); }
.tp-case-evidence-grid b { color:var(--tp-ink); text-align:right; }
.tp-qa-profile { display:flex; align-items:baseline; flex-wrap:wrap; gap:8px 16px; margin-bottom:18px; padding:14px 16px; border:1px solid #c9dcfb; border-radius:10px; background:#f8fbff; }
.tp-qa-profile strong { color:var(--tp-brand-ink); font-size:14px; }
.tp-qa-profile span { color:var(--tp-sub); font-size:12px; }
.tp-qa-profile b { margin-left:auto; color:var(--tp-ink); font-size:11px; }
.tp-qa-profile small { flex-basis:100%; color:var(--tp-faint); font-size:10px; line-height:1.4; }
.tp-qa-heading { margin:20px 0 9px; font-size:15px !important; }
.tp-qa-rule { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; margin:0 0 6px; padding:9px 12px; border:1px solid var(--tp-line); border-radius:9px; background:#fff; }
.tp-qa-rule > div { min-width:0; }
.tp-qa-rule strong { color:var(--tp-ink); font-size:12px; }
.tp-qa-rule p { margin:3px 0; color:var(--tp-sub); font-size:11px; line-height:1.4; }
.tp-qa-rule small { display:block; color:var(--tp-faint); font-size:10px; line-height:1.45; }
.tp-qa-rule > span { flex:0 0 auto; padding:4px 7px; border-radius:999px; font-size:10px; font-weight:750; white-space:nowrap; }
.tp-qa-rule.is-pass > span { background:#eaf8f1; color:#147a4a; }
.tp-qa-rule.is-fail { border-color:#efc1bd; background:#fffafa; }
.tp-qa-rule.is-fail > span { background:#fff0f0; color:#b42318; }
.tp-qa-rule.is-manual_review > span { background:#fff7e6; color:#8a5a00; }
.tp-qa-rule.is-not_checked > span { background:#f1f4f8; color:#536176; }
.tp-qa-fact { display:flex; flex-direction:column; gap:4px; padding:10px 0; }
.tp-qa-fact strong { color:var(--tp-ink); font-size:13px; }
.tp-qa-fact span { color:var(--tp-sub); font-size:11px; }
.tp-qa-status { margin-top:8px; padding:7px 8px; border-radius:8px; font-size:11px; font-weight:750; text-align:center; }
.tp-qa-status.is-pass, .tp-qa-status.is-confirmed { background:#eaf8f1; color:#147a4a; }
.tp-qa-status.is-fail { background:#fff0f0; color:#b42318; }
.tp-qa-status.is-stale { background:#fff7e6; color:#8a5a00; }
.tp-qa-status.is-not_run, .tp-qa-status.is-not_confirmed { background:#f1f4f8; color:#536176; }
/* ---- 右栏 = Agent Inspector ----
   右栏不再是第二个编辑器：它只回答"这一段现在什么状态、系统发现了什么、
   可以让我做什么"。正文编辑只发生在中央网格里。
   Inspector 自身是一个 panel surface：有区域感，但内部不再给每个事实做小方格
   （那是 dashboard）。分组靠极淡的底色块 + section divider。 */
.st-key-translation_inspector {
 padding:14px 14px 16px; color:var(--tp-ink);
 background:var(--tp-surface); border:1px solid var(--tp-hairline);
 border-radius:12px; box-shadow:var(--tp-shadow-sm);
}
.tp-translation-inspector-head {
 display:flex; align-items:center; justify-content:space-between; gap:10px;
 padding:0 0 10px; border-bottom:1px solid var(--tp-hairline);
}
.tp-translation-inspector-head h3 { margin:0; font-size:14px !important; letter-spacing:-.01em; }
.tp-translation-inspector-position { color:var(--tp-faint); font-size:11px; white-space:nowrap;
 font-variant-numeric:tabular-nums; }
.tp-inspector-section { padding:11px 0; border-bottom:1px solid var(--tp-hairline); }
.tp-inspector-section:last-child { border-bottom:0; }
.tp-inspector-section h4 {
 margin:0 0 8px; color:var(--tp-faint); font-size:10px; font-weight:750;
 letter-spacing:.07em; text-transform:uppercase;
}
.tp-inspector-status { display:flex; align-items:center; gap:7px; color:var(--tp-sub); font-size:12px; }
.tp-inspector-status strong { color:var(--tp-ink); font-weight:650; }
/* 相关术语：一个明确的组，而不是漂在右栏里的文字。
   整块给极淡 surface，条与条之间用 hairline 分隔——像工具数据，不像网页注释。 */
.tp-inspector-terms {
 background:var(--tp-canvas-soft); border:1px solid var(--tp-hairline);
 border-radius:8px; padding:2px 10px;
}
.tp-inspector-term { display:flex; justify-content:space-between; align-items:baseline;
 gap:12px; padding:7px 0; font-size:12px;
 border-bottom:1px solid var(--tp-hairline); }
.tp-inspector-term:last-child { border-bottom:0; }
.tp-inspector-term span { color:var(--tp-sub); }
.tp-inspector-term b { color:var(--tp-ink); font-weight:650; text-align:right; }
.tp-inspector-empty { color:var(--tp-faint); font-size:11.5px; }
.tp-inspector-preview { margin:0; color:var(--tp-sub); font-size:12px; line-height:1.55; }
.tp-inspector-preview + .tp-inspector-preview { margin-top:10px; }
.tp-inspector-preview strong { display:block; margin-bottom:3px; color:var(--tp-faint); font-size:11px; font-weight:650; }
/* Inspector 里没有正文编辑器（编辑只在中央网格发生），但自定义指令等输入框
   仍需要可用的默认高度。 */
.st-key-translation_inspector [data-testid="stTextArea"] textarea { min-height:120px; font-size:12.5px; line-height:1.6; }
/* 段落事实：轻量 definition list，整块一块淡 surface。
   原来是 2×3 方格，像 dashboard；但完全裸文字又让右栏显得散。
   折中：一个连续的浅底块 + 行分隔，不给每个事实单独做格子。 */
.tp-inspector-facts-list {
 display:flex; flex-direction:column;
 background:var(--tp-canvas-soft); border:1px solid var(--tp-hairline);
 border-radius:8px; padding:4px 10px;
}
.tp-inspector-fact { display:flex; align-items:baseline; gap:8px; width:100%;
 padding:5px 0; border-bottom:1px solid var(--tp-hairline); }
.tp-inspector-fact:last-child { border-bottom:0; }
.tp-inspector-fact span { flex:0 0 62px; color:var(--tp-faint); font-size:10px;
 font-weight:700; letter-spacing:.03em; text-transform:uppercase; }
.tp-inspector-fact strong { color:var(--tp-ink); font-size:12px; font-weight:650;
 overflow-wrap:anywhere; }
.tp-inspector-fact strong.is-muted { color:var(--tp-faint); font-weight:500; }
/* 段落相关的 Agent 发现：贴着 Inspector 顶部，先看问题再看操作 */
.tp-inspector-finding { margin:0 0 6px; padding:8px 10px; border-radius:8px;
 background:var(--tp-warn-soft); border-left:3px solid var(--tp-warn); }
.tp-inspector-finding.is-blocking { background:var(--tp-danger-soft); border-left-color:var(--tp-danger); }
.tp-inspector-finding.is-informational { background:var(--tp-canvas-soft); border-left-color:#98a2b3; }
.tp-inspector-finding strong { display:block; color:var(--tp-ink); font-size:11.5px; font-weight:650; line-height:1.4; }
.tp-inspector-finding p { margin:3px 0 0; color:var(--tp-sub); font-size:11px; line-height:1.5; }
.tp-inspector-finding button { margin-top:5px; }
/* Agent 建议：AI 动作产出的候选译文，明确区别于"已保存的译文" */
.tp-inspector-suggestion { margin-top:9px; padding:10px 11px; border-radius:9px;
 background:var(--tp-primary-soft); border:1px solid #d5e4fb; }
.tp-inspector-suggestion > span { color:var(--tp-primary); font-size:10px; font-weight:800;
 letter-spacing:.06em; text-transform:uppercase; }
.tp-inspector-suggestion p { margin:6px 0 0; color:var(--tp-ink); font-size:12.5px; line-height:1.6;
 white-space:pre-wrap; }
.st-key-translation_inspector [data-testid="stExpander"] { border:0; border-top:1px solid var(--tp-hairline); border-radius:0; }
.st-key-translation_inspector [data-testid="stExpander"] summary { padding:10px 0; }
.st-key-translation_inspector .stButton > button { min-height:32px; }
/* Agent 动作按钮：它们是次要操作，不该成为整页最有实体感的东西
   （上一版实心白底 + 边框，视觉重心整个跑到右栏去了）。
   改成"安静的次级按钮"：透明底 + 透明边框，hover 才浮出 surface。 */
[class*="st-key-translation_agent_actions_"] [data-testid="stHorizontalBlock"] { gap:5px; }
[class*="st-key-translation_agent_actions_"] .stButton > button {
 justify-content:flex-start; padding:0 8px; border-color:transparent;
 background:transparent; color:var(--tp-sub); font-size:12px; font-weight:550;
 box-shadow:none;
}
[class*="st-key-translation_agent_actions_"] .stButton > button:hover {
 border-color:var(--tp-hairline-strong); background:var(--tp-surface);
 color:var(--tp-brand-ink);
}
[class*="st-key-translation_agent_actions_"] .stButton > button span[data-testid="stIconMaterial"] {
 color:var(--tp-faint); }
[class*="st-key-translation_agent_actions_"] .stButton > button:hover span[data-testid="stIconMaterial"] {
 color:var(--tp-primary); }
.tp-translation-table-note { margin:8px 0 10px; color:var(--tp-faint); font-size:11px; }

/* ---- 中央 CAT 工作区 ----
   一个段落对 = 一个工作单元（行 surface），内部左右两列。
   只有一层容器：不再出现"整行卡片 → 原文卡片 → 译文卡片"的三层嵌套。
   原文是纯阅读态，译文有明确的 editable affordance。 */
.tp-cat-title { display:flex; align-items:center; flex-wrap:wrap; gap:8px 10px; margin:0 0 6px; }
.tp-cat-title h2 { margin:0; font-size:18px !important; }
.tp-cat-hint { color:var(--tp-faint); font-size:11px; }
/* 进度 = 四个维度，而不是一个"82/82 已翻译"的假完成信号 */
.tp-cat-progress-grid { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin:0 0 10px; }
.tp-cat-metric { display:inline-flex; align-items:baseline; gap:5px; padding:3px 9px;
 border-radius:999px; background:var(--tp-surface-sunken); font-size:11px; }
.tp-cat-metric span { color:var(--tp-sub); }
.tp-cat-metric b { color:var(--tp-ink); font-weight:700; font-variant-numeric:tabular-nums; }
.tp-cat-metric.is-complete b { color:var(--tp-success); }
.tp-cat-metric.is-attention b { color:var(--tp-warn); }
.tp-cat-metric.is-blocked b { color:var(--tp-danger); }
.tp-cat-metric.is-muted { opacity:.62; }
.tp-cat-progress { display:flex; align-items:center; gap:8px; margin-left:auto;
 flex:1 1 200px; min-width:160px; max-width:340px; }
.tp-cat-progress-bar { position:relative; flex:1; height:5px; border-radius:3px;
 background:var(--tp-hairline-strong); overflow:hidden; }
.tp-cat-progress-bar > span { display:block; height:100%; border-radius:3px;
 background:var(--tp-primary); }
.tp-cat-progress-text { color:var(--tp-sub); font-size:11px; font-weight:650;
 white-space:nowrap; }
/* 工具栏按钮标签绝不截断：被压成"筛…"比多占十几像素糟糕得多 */
[class*="st-key-translation_filter_menu_"] button,
[class*="st-key-translation_more_menu_"] button { white-space:nowrap; }
[class*="st-key-translation_filter_menu_"] button p,
[class*="st-key-translation_more_menu_"] button p { white-space:nowrap; }
.tp-cat-head { display:flex; gap:14px; padding:5px 0 6px; color:var(--tp-faint);
 font-size:10px; font-weight:750; letter-spacing:.07em; text-transform:uppercase;
 border-bottom:1px solid var(--tp-hairline); }
.tp-cat-head .tp-cat-num { width:74px; flex:none; }
.tp-cat-head .tp-cat-col { flex:1; }
.tp-cat-head .tp-cat-col.is-tgt { padding-left:4px; }
.tp-cat-head .tp-cat-act { width:46px; flex:none; }
/* ---- 段落工作单元：surface hierarchy ----
   要删的是"框套框"，不是工作面本身。每个段落对是一个视觉工作单元：
     工作区 surface → 段落行 surface → 可编辑译文 surface → focus/active
   靠底色 + 极淡分隔线分层，不再给原文/译文各自套卡片（只有一层，不是三层）。 */
[class*="st-key-cat_grid_"] {
 background:var(--tp-surface); border:1px solid var(--tp-hairline);
 border-radius:10px; box-shadow:var(--tp-shadow-sm); overflow:hidden;
 margin-bottom:10px;
}
[class*="st-key-cat_grid_"] [data-testid="stVerticalBlock"] { gap:0; }
[class*="st-key-cat_row_"] {
 padding:11px 12px; border-radius:0; position:relative;
 background:var(--tp-surface);
 border-bottom:1px solid var(--tp-hairline);
 transition:background .12s ease;
}
[class*="st-key-cat_row_"]:last-child { border-bottom:0; }
[class*="st-key-cat_row_"]:hover { background:var(--tp-tint-hover); }
/* Active 段落：整行淡蓝底 + 3px 蓝条。只靠段号胶囊太弱——用户需要"我正在操作
   哪一段"是整行的感知，而不是一个 18px 的方块。

   注意：`.is-active` 落在行内的标记 span 上（那是服务端渲染的，
   不需要把数据再往容器层传一遍）。所以这里必须用 `:has()` 从行容器向下看，
   不能写成 `[class*="st-key-cat_row_"].is-active`——那样永远匹配不到，
   active 会静默失效（实测就是这样：段号变了、蓝条和底色都没出现）。 */
[class*="st-key-cat_row_"]:has(> [data-testid="stElementContainer"] .is-active) {
 background:var(--tp-tint-active);
}
[class*="st-key-cat_row_"]:has(> [data-testid="stElementContainer"] .is-active)::before {
 content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
 background:var(--tp-primary);
}
[class*="st-key-cat_row_"]:has(> [data-testid="stElementContainer"] .is-active):hover {
 background:#e8f0ff;
}
[class*="st-key-cat_row_"] [data-testid="stHorizontalBlock"] { gap:14px; align-items:flex-start; }
/* 行内三列必须顶对齐。Streamlit 在 stColumn 和内容之间还夹着 stLayoutWrapper /
   stVerticalBlock 两层，它们默认 `justify-content: flex-end`：段号列只有 22px 高时
   会被推到整行底部，长原文旁边就出现"译文贴着段落末尾"的错位。
   这里把这两层显式改成顶对齐（st-key-cat_form_ 是行内表单容器，不会误伤其他面板）。 */
[class*="st-key-cat_row_"] [data-testid="stColumn"] { align-items:flex-start; }
[class*="st-key-cat_row_"] [data-testid="stColumn"] > [data-testid="stLayoutWrapper"],
[class*="st-key-cat_row_"] [data-testid="stColumn"] > [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"],
[class*="st-key-cat_form_"] { justify-content:flex-start !important; align-items:stretch; }
.tp-cat-numcell { display:flex; flex-direction:column; gap:5px; padding-top:1px; }
.tp-cat-source { color:var(--tp-ink); font-size:13px; line-height:1.72;
 white-space:pre-wrap; overflow-wrap:anywhere; }
.tp-cat-source.is-empty { color:var(--tp-faint); font-style:italic; }
.tp-cat-badges { display:flex; flex-wrap:wrap; gap:3px; }
.tp-cat-badge { padding:0 5px; border-radius:4px; background:var(--tp-surface-sunken);
 color:var(--tp-faint); font-size:9.5px; font-weight:700; line-height:15px; }
.tp-cat-badge.is-tm { background:#eef6ff; color:#1d5fb8; }
.tp-cat-badge.is-term { background:#f1f0ff; color:#5b46c4; }
.tp-cat-badge.is-issue { background:var(--tp-danger-soft); color:#b42318; }
/* 段号：默认是一个安静的序号，选中才是实心蓝。
   刻意做小（22px → 视觉权重约原来的 72%）：段号是辅助定位，不该比译文更抢眼。
   当前段落的识别主要交给 3px 蓝色指示条 + 极淡蓝底。 */
[class*="st-key-cat_num_"] .stButton button {
 min-height:18px; height:18px; padding:0 2px; font-size:10.5px; font-weight:650;
 color:#8b96a6; background:transparent; border-color:transparent; box-shadow:none;
 font-variant-numeric:tabular-nums; margin-top:2px;
}
[class*="st-key-cat_num_"] .stButton button:hover {
 background:var(--tp-surface-sunken); border-color:transparent; color:var(--tp-ink);
}
[class*="st-key-cat_num_"] .stButton button[kind="primary"] {
 background:var(--tp-primary); border-color:var(--tp-primary); color:#fff;
 font-weight:700; }
[class*="st-key-cat_num_"] .stButton button[kind="primary"]:hover {
 background:var(--tp-primary-hover); border-color:var(--tp-primary-hover); color:#fff; }
/* 行内译文编辑器：必须一眼看出"这里可以编辑"。
   目标状态不是"大白框"，而是一个有明确输入感的 surface：
     平时 = 淡灰蓝底 + 极淡描边（可编辑 affordance）
     hover = 描边加深
     focus = 白底 + 蓝色焦点环
   原文保持纯阅读态（无底色），这样左右两列的"只读 / 可写"是看得出来的。
   注意：Streamlit 把底色和边框画在 `stTextAreaRootElement` 而不是 textarea 上，
   两层都要设，否则会出现一个灰底框套一个白框。 */
[class*="st-key-cat_row_"] [data-testid="stTextArea"] { margin:0; width:100%; min-width:0; }
[class*="st-key-cat_row_"] [data-testid="stTextArea"] textarea {
 padding:7px 9px; border:0 !important; box-shadow:none !important; background:transparent !important;
 color:var(--tp-ink); font-size:13px; line-height:1.72; resize:none;
 /* 必须显式定宽：textarea 会保留首次渲染的固有宽度，列变窄后文字就横向溢出，
   看起来像"译文没对齐"。 */
 width:100% !important; min-width:0 !important; max-width:100% !important;
 /* 高度：显式约 5 行（13px × 1.72 ≈ 22.4px/行），内容更多时框内滚动。
   试过两条"自动长高"的路子，都不可靠，记在这里避免重复：
   1) `field-sizing:content` —— 在这个 Streamlit 版本的包装层里不生效
      （实测长段落 scrollHeight 375px，元素高度仍是 46px）。
   2) `height:auto + overflow:hidden` —— Streamlit 自己的 auto-resize 会覆盖它，
      把高度钉在 86px，剩下 289px 内容仍然被藏起来。
   固定高度是这里唯一稳定、可预测的做法：短段落不浪费空间，长段落有滚动条提示
   "还有内容"，而且它本身就是一种可编辑的 affordance。
   取 112px（5 行）而不是 132px（6 行）：后者会让首屏少掉一整段。 */
 height:112px !important; min-height:112px; max-height:112px;
 overflow-y:auto; overflow-x:hidden;
}
[class*="st-key-cat_row_"] [data-testid="stTextArea"] textarea::placeholder {
 color:var(--tp-faint); font-style:italic; }
[class*="st-key-cat_row_"] [data-testid="stTextAreaRootElement"] {
 width:100%; min-width:0; max-width:100%;
 background:var(--tp-tint-hover) !important;
 border:1px solid var(--tp-hairline-strong) !important;
 border-radius:8px !important; box-shadow:none !important;
 transition:background .12s ease, border-color .12s ease, box-shadow .12s ease;
}
[class*="st-key-cat_row_"] [data-testid="stTextArea"] [data-baseweb="textarea"],
[class*="st-key-cat_row_"] [data-testid="stTextArea"] [data-baseweb="base-input"] {
 border:0 !important; box-shadow:none !important; background:transparent !important;
 border-radius:0 !important;
}
[class*="st-key-cat_row_"] [data-testid="stTextAreaRootElement"]:hover {
 border-color:#c9d7ea !important; }
[class*="st-key-cat_row_"] [data-testid="stTextAreaRootElement"]:focus-within {
 background:var(--tp-surface) !important; border-color:var(--tp-primary) !important;
 box-shadow:0 0 0 3px var(--tp-focus-ring) !important;
}
/* 当前段落的译文框：底色比别的行再明显一点，配合整行 tint */
[class*="st-key-cat_row_"].is-active [data-testid="stTextAreaRootElement"] {
 background:var(--tp-surface) !important; border-color:#cddffb !important; }
[class*="st-key-cat_row_"] [data-testid="stTextArea"] label { display:none; }
/* 行内标记：只用来挂工具类/跳转锚点，不占高度、不显示内容 */
.tp-cat-rowcell { display:block; height:0; overflow:hidden; }
.tp-cat-status { display:inline-flex; align-items:center; gap:4px; color:var(--tp-faint);
 font-size:10px; font-weight:650; }
.tp-cat-status.is-dirty { color:var(--tp-warn); }
.tp-cat-status.is-issue { color:#b42318; }
.tp-cat-status.is-edited { color:var(--tp-primary); }
.tp-cat-status.is-pending { color:var(--tp-faint); }
.tp-cat-status.is-done { color:#5c8a72; }
.tp-cat-status.is-hint { color:var(--tp-faint); font-weight:500; }
/* 行内表单：无边框，保存按钮在没有改动时退成次要按钮 */
[class*="st-key-cat_row_"] [data-testid="stForm"] { border:0; padding:0; background:transparent; }
[class*="st-key-cat_row_"] [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
 gap:6px; align-items:center; }
[class*="st-key-cat_save_"] .stButton > button,
[class*="st-key-cat_save_"] [data-testid="stFormSubmitButton"] > button {
 min-height:24px; height:24px; padding:0 8px; font-size:11px; font-weight:650; }
[class*="st-key-cat_save_"] [data-testid="stFormSubmitButton"] > button[kind="secondary"] {
 background:transparent; border-color:transparent; color:var(--tp-faint); box-shadow:none; }
[class*="st-key-cat_save_"] [data-testid="stFormSubmitButton"] > button[kind="secondary"]:hover {
 background:var(--tp-surface-sunken); border-color:transparent; color:var(--tp-sub); }
.tp-cat-empty { color:var(--tp-faint); font-style:italic; font-size:12.5px; }
[class*="st-key-cat_grid_"] [data-testid="stVerticalBlock"] { gap:0; }
.tp-cat-toolbar-note { color:var(--tp-faint); font-size:11px; }
/* ---- Agent issue bar：一条 44–52px 的通知条，点"查看全部"才展开 ----
   更早的版本是大卡片 + 一排大号"定位"按钮，实测吃掉约 140px，把第一段正文推到
   屏幕中部。agent 必须随时可见，但不能抢走正文。 */
.tp-issue-bar {
 display:flex; align-items:center; gap:8px; min-height:44px; box-sizing:border-box;
 padding:0 12px; border-radius:9px; background:var(--tp-surface);
 border:1px solid var(--tp-hairline); box-shadow:var(--tp-shadow-sm);
}
.tp-issue-mark { flex:none; color:var(--tp-primary); font-size:12px; }
.tp-issue-dot { flex:none; width:6px; height:6px; border-radius:50%; background:#98a2b3; }
.tp-issue-dot.is-blocking { background:var(--tp-danger); }
.tp-issue-dot.is-actionable { background:var(--tp-warn); }
.tp-issue-bar strong {
 min-width:0; color:var(--tp-ink); font-size:12px; font-weight:650;
 white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.tp-issue-count { flex:none; color:var(--tp-faint); font-size:10.5px; white-space:nowrap; }
.tp-issue-spacer { flex:1 1 auto; }
/* ---- 问题抽屉（右栏 Issues 模式）----
   不做中央浮层：浮层会盖住正在工作的正文，而问题列表和"跳到正文处理问题"
   是同一件事的两半，盖住工作台自相矛盾。放在右栏，跳转后顺手切回段落 Inspector。 */
.tp-issues-summary {
 display:flex; flex-wrap:wrap; gap:4px 12px; margin:0 0 10px; padding:8px 10px;
 border-radius:8px; background:var(--tp-canvas-soft);
 border:1px solid var(--tp-hairline); color:var(--tp-sub); font-size:11px;
 font-variant-numeric:tabular-nums;
}
.tp-issues-summary b { color:var(--tp-ink); font-weight:750; }
.tp-issues-summary .is-blocking b { color:#b42318; }
.tp-issues-summary .is-actionable b { color:var(--tp-warn); }
.tp-issue-row { margin:10px 0 0; padding:9px 10px; border-radius:8px;
 background:var(--tp-warn-soft); border-left:3px solid var(--tp-warn); }
.tp-issue-row.is-blocking { background:var(--tp-danger-soft); border-left-color:var(--tp-danger); }
.tp-issue-row.is-informational { background:var(--tp-canvas-soft); border-left-color:#98a2b3; }
.tp-issue-row-head { display:flex; align-items:baseline; justify-content:space-between; gap:8px; }
.tp-issue-row-head strong { color:var(--tp-ink); font-size:11.5px; font-weight:650;
 line-height:1.4; }
.tp-issue-sev { flex:none; color:var(--tp-faint); font-size:9.5px; font-weight:750;
 letter-spacing:.04em; }
.tp-issue-row p { margin:3px 0 0; color:var(--tp-sub); font-size:11px; line-height:1.5; }
.tp-issue-hits { margin:7px 0 5px; color:var(--tp-faint); font-size:10.5px;
 font-variant-numeric:tabular-nums; }
/* 问题锚点：紧凑的数字按钮，不是一排大按钮 */
[class*="st-key-issue_anchor_"] .stButton button {
 min-height:24px; height:24px; padding:0 4px; font-size:10.5px; font-weight:650;
 font-variant-numeric:tabular-nums; background:var(--tp-surface);
 border-color:var(--tp-hairline-strong); color:var(--tp-sub);
}
[class*="st-key-issue_anchor_"] .stButton button:hover {
 border-color:var(--tp-border); background:var(--tp-tint-active); color:var(--tp-brand-ink); }
[class*="st-key-issues_close_"] .stButton button { min-height:28px; font-size:11.5px; }
/* "查看全部"跟 issue bar 同高，视觉上属于同一条 */
[class*="st-key-agent_all_"] button {
 min-height:44px; height:44px; font-size:11.5px; font-weight:650;
 border-color:var(--tp-hairline); background:var(--tp-surface); color:var(--tp-sub); }
[class*="st-key-agent_all_"] button:hover {
 border-color:var(--tp-border); color:var(--tp-brand-ink); background:var(--tp-tint-active); }
.tp-review-head { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin-bottom:16px; }
.tp-review-count { color:var(--tp-sub); font-size:13px; }
.tp-review-readiness {
 display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px 24px;
 margin:0 0 12px; padding:16px 18px; border:1px solid #edd39d;
 border-left:4px solid #c47b00; border-radius:12px; background:#fffaf0;
}
.tp-review-readiness.is-success { border-color:#b8dfcc; border-left-color:var(--tp-success); background:#f3fbf7; }
.tp-review-readiness.is-danger { border-color:#efc1bd; border-left-color:var(--tp-danger); background:#fff8f7; }
.tp-review-readiness.is-neutral { border-color:var(--tp-line); border-left-color:#8a94a6; background:#fbfcfe; }
.tp-review-readiness > div:first-child > span { color:var(--tp-sub); font-size:10px; font-weight:800; letter-spacing:.07em; text-transform:uppercase; }
.tp-review-readiness > div:first-child > strong { display:block; margin-top:4px; color:var(--tp-ink); font-size:19px; line-height:1.3; }
.tp-review-readiness > div:first-child > p { margin:5px 0 0; max-width:64ch; color:var(--tp-sub); font-size:12px; line-height:1.55; }
.tp-review-progress { align-self:center; text-align:right; white-space:nowrap; }
.tp-review-progress b { display:block; color:var(--tp-ink); font-size:21px; font-variant-numeric:tabular-nums; }
.tp-review-progress span { color:var(--tp-sub); font-size:10px; }
.tp-review-progress-grid { grid-column:1 / -1; display:flex; flex-wrap:wrap; gap:7px 16px; padding-top:11px; border-top:1px solid rgba(138,90,0,.16); }
.tp-review-progress-grid span { color:var(--tp-sub); font-size:11px; }
.tp-review-progress-grid b { color:var(--tp-ink); font-variant-numeric:tabular-nums; }
.tp-focus-head { display:flex; justify-content:space-between; gap:12px; margin:8px 0 14px; color:var(--tp-sub); font-size:13px; font-weight:650; }
.tp-focus-text { min-height:300px; padding:18px; border:1px solid var(--tp-line); border-radius:12px; background:#fff; }
.tp-focus-text label { display:block; margin-bottom:12px; color:var(--tp-sub); font-size:11px !important; font-weight:700; letter-spacing:.06em; text-transform:uppercase; }
.tp-focus-text p { margin:0; color:var(--tp-ink); font-size:15px; line-height:1.85; white-space:pre-wrap; }
.tp-filter-strip { display:flex; align-items:center; gap:8px; padding:9px 0 13px; border-top:1px solid var(--tp-line-subtle); border-bottom:1px solid var(--tp-line); }
.tp-filter-chip { padding:5px 10px; border:1px solid var(--tp-line); border-radius:999px; color:var(--tp-sub); font-size:12px; }
.tp-filter-chip.is-blocking { border-color:#f3c0bd; color:#b42318; background:#fff8f7; }
.tp-review-pane { min-height:530px; padding:16px; border:1px solid var(--tp-line); border-radius:12px; background:#fff; }
.tp-review-pane + .tp-review-pane { margin-left:-1px; border-radius:0 12px 12px 0; }
.tp-review-pane.is-queue { border-radius:12px 0 0 12px; background:#fbfcfe; }
.tp-review-pane.is-evidence { border-radius:0 12px 12px 0; background:#fbfcfe; }
.tp-review-queue-count { color:var(--tp-sub); font-size:13px; font-weight:500; }
.tp-review-section-label { margin:18px 0 7px; color:var(--tp-sub); font-size:12px; font-weight:700; }
.tp-review-long-text {
 padding:12px 0 16px; border-bottom:1px solid var(--tp-line-subtle);
 color:var(--tp-ink); font-size:14px; line-height:1.75; white-space:pre-wrap;
}
.tp-review-compare-label { margin:18px 0 7px; color:var(--tp-sub); font-size:11px; font-weight:800; letter-spacing:.05em; text-transform:uppercase; }
.tp-review-compare-text { min-height:160px; padding:14px 15px; border:1px solid var(--tp-line); border-radius:10px; background:#fff; color:var(--tp-ink); font-size:14px; line-height:1.75; white-space:pre-wrap; overflow-wrap:anywhere; }
.tp-review-suggestion { margin-top:14px; padding:13px 15px; border:1px solid #bfd6fa; border-left:3px solid var(--tp-primary); border-radius:9px; background:#f6f9ff; }
.tp-review-suggestion span { color:var(--tp-primary); font-size:10px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
.tp-review-suggestion p { margin:6px 0 0; color:var(--tp-ink); font-size:14px; line-height:1.7; white-space:pre-wrap; }
.tp-review-diagnostic-label { margin-top:18px; color:var(--tp-sub); font-size:11px; font-weight:750; letter-spacing:.02em; }
.tp-review-diagnostic-copy { margin:6px 0 0; color:var(--tp-ink); font-size:14px; line-height:1.7; white-space:pre-wrap; }
.tp-review-summary { padding:12px 14px; border-left:3px solid #f59e0b; border-radius:0 8px 8px 0; background:#fff9eb; color:#5f4600; }
.tp-review-span { padding:1px 3px; border-radius:3px; background:#fff0bd; box-shadow:inset 0 -1px 0 #e5b93f; }
.tp-review-location-note { margin:6px 0 0; color:var(--tp-faint); font-size:11px; line-height:1.5; }
.tp-review-legacy { margin:14px 0; padding:10px 12px; border:1px solid #d9e2ef; border-radius:8px; background:#f8fafc; color:var(--tp-sub); font-size:12px; line-height:1.55; }
.tp-review-evidence-detail { color:var(--tp-sub); font-size:12px; line-height:1.55; }
.tp-review-evidence-title { margin:0 0 14px; font-size:16px !important; }
.tp-review-evidence-row {
 display:flex; align-items:baseline; justify-content:space-between; gap:12px;
 padding:9px 0; border-bottom:1px solid var(--tp-line-subtle); font-size:12px;
}
.tp-review-evidence-row span { color:var(--tp-sub); }
.tp-review-evidence-row b { color:var(--tp-ink); text-align:right; }
.tp-review-evidence-label { margin-top:16px; color:var(--tp-sub); font-size:11px; font-weight:750; }
.tp-review-evidence-copy { margin:5px 0 0; color:var(--tp-ink); font-size:12px; line-height:1.65; white-space:pre-wrap; }
.tp-review-inspector-status { padding:12px 13px; border:1px solid #c9dcfb; border-left:3px solid var(--tp-primary); border-radius:9px; background:#f7faff; }
.tp-review-inspector-status > span { display:block; color:var(--tp-primary); font-size:10px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
.tp-review-inspector-status > strong { display:block; margin-top:4px; color:var(--tp-ink); font-size:14px; }
.tp-review-inspector-status > p { margin:5px 0 0; color:var(--tp-sub); font-size:11px; line-height:1.5; }
.tp-review-inspector-section-title { margin-top:22px; padding-top:15px; border-top:1px solid var(--tp-line-subtle); }
.tp-review-constraint { display:grid; grid-template-columns:minmax(72px,.7fr) minmax(0,1.3fr); gap:9px; padding:7px 0; border-bottom:1px solid var(--tp-line-subtle); font-size:11px; }
.tp-review-constraint span { color:var(--tp-sub); }
.tp-review-constraint strong { color:var(--tp-ink); font-weight:650; text-align:right; overflow-wrap:anywhere; }
.tp-review-history-row { display:flex; gap:9px; padding:7px 0; border-bottom:1px solid var(--tp-line-subtle); }
.tp-review-history-row time { flex:0 0 38px; color:var(--tp-faint); font-size:10px; font-variant-numeric:tabular-nums; }
.tp-review-history-row div { min-width:0; }
.tp-review-history-row strong { display:block; color:var(--tp-ink); font-size:11px; line-height:1.35; }
.tp-review-history-row span { display:block; margin-top:2px; color:var(--tp-sub); font-size:10px; line-height:1.4; overflow-wrap:anywhere; }
.st-key-workspace_main_col [class*="st-key-review_"] .stButton > button { min-height:44px; white-space:normal; }
[class*="st-key-review_primary_action_"] { margin:0 0 10px; }
[class*="st-key-review_primary_action_"] .stButton > button { min-height:38px; white-space:normal; }
[class*="st-key-review_action_bar_"] {
 position:sticky; top:8px; z-index:4; margin:0 0 14px; padding:8px 10px;
 border:1px solid #c9dcfb; border-radius:10px; background:rgba(248,251,255,.96);
 box-shadow:0 4px 14px rgba(24,55,105,.08); backdrop-filter:blur(7px);
}
[class*="st-key-review_action_bar_"] .stButton > button { min-height:40px; white-space:normal; }
.tp-queue-item { padding:11px 10px; border-bottom:1px solid var(--tp-line-subtle); }
.tp-queue-item strong { display:block; color:var(--tp-ink); font-size:13px; line-height:1.4; }
.tp-queue-item span { display:block; margin-top:4px; color:var(--tp-sub); font-size:11px; line-height:1.35; }
.tp-queue-item.is-selected { margin:0 -10px; padding-left:20px; border-left:3px solid var(--tp-primary); background:#eef5ff; }
.tp-segment-label { color:var(--tp-sub); font-size:12px; font-weight:650; }
.tp-finding-reason { margin:14px 0; padding:13px 15px; border-left:3px solid #f59e0b; border-radius:0 8px 8px 0; background:#fff9eb; color:#6c4d00; font-size:13px; line-height:1.6; }
.tp-text-card { min-height:130px; padding:14px; border:1px solid var(--tp-line); border-radius:10px; background:#fbfcfe; }
.tp-text-card label { display:block; margin-bottom:9px; color:var(--tp-sub); font-size:11px !important; font-weight:700; text-transform:uppercase; letter-spacing:.05em; }
.tp-text-card p { margin:0; color:var(--tp-ink); font-size:14px; line-height:1.7; white-space:pre-wrap; }
.tp-evidence-card { padding:13px; border:1px solid var(--tp-line); border-radius:10px; background:#fff; }
.tp-evidence-card p { margin:0; color:var(--tp-sub); font-size:12px; line-height:1.6; }
.tp-delivery-header { padding:20px 22px; border:1px solid var(--tp-line); border-radius:14px; background:#fff; }
.tp-risk-acceptance { margin:18px 0 12px; padding:16px 17px; border:1px solid #efc1bd; border-left:4px solid var(--tp-danger); border-radius:10px; background:#fff8f7; }
.tp-risk-acceptance > span { color:#b42318; font-size:10px; font-weight:800; letter-spacing:.07em; text-transform:uppercase; }
.tp-risk-acceptance h3 { margin:4px 0 0; color:#7f1d1d; font-size:18px !important; }
.tp-risk-acceptance p { margin:6px 0 0; color:#6f3130; font-size:12px; line-height:1.55; }
.tp-term-focus { margin:0 0 14px; padding:12px 14px; border:1px solid #c9dcfb; border-left:3px solid var(--tp-primary); border-radius:9px; background:#f7faff; }
.tp-term-focus span { display:block; color:var(--tp-primary); font-size:10px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
.tp-term-focus strong { display:block; margin-top:4px; color:var(--tp-ink); font-size:14px; }
.tp-term-focus p { margin:4px 0 0; color:var(--tp-sub); font-size:11px; }
.tp-report-page-head { margin-bottom:18px; }
.tp-report-page-head h2 { margin:2px 0 5px; }
.tp-report-page-lead { margin:0; color:var(--tp-sub); font-size:13px; line-height:1.6; }
.tp-report-meta-chips { display:flex; flex-wrap:wrap; gap:7px; margin-top:14px; }
.tp-report-meta-chip { display:inline-flex; align-items:center; gap:5px; padding:5px 9px; border:1px solid var(--tp-line); border-radius:999px; background:#fff; color:var(--tp-sub); font-size:11px; line-height:1.2; }
.tp-report-meta-chip strong { color:var(--tp-ink); font-weight:700; }
.tp-report-overall { margin-bottom:14px; padding:18px 20px; border:1px solid #c9dcfb; border-left:4px solid var(--tp-primary); border-radius:12px; background:#f8fbff; }
.tp-report-overall.is-danger { border-color:#f1c2bf; border-left-color:var(--tp-danger); background:#fff7f6; }
.tp-report-overall.is-warning { border-color:#edd39d; border-left-color:#c47b00; background:#fffaf0; }
.tp-report-overall.is-success { border-color:#b8dfcc; border-left-color:var(--tp-success); background:#f3fbf7; }
.tp-report-overall-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.tp-report-overall-head h3 { margin:0; color:var(--tp-ink); font-size:21px !important; }
.tp-report-overall-grid { display:grid; grid-template-columns:minmax(0,1.6fr) .8fr 1fr; gap:18px; margin-top:16px; padding-top:14px; border-top:1px solid var(--tp-line-subtle); }
.tp-report-overall-grid span { display:block; color:var(--tp-sub); font-size:11px; }
.tp-report-overall-grid strong { display:block; margin-top:5px; color:var(--tp-ink); font-size:13px; line-height:1.45; font-variant-numeric:tabular-nums; }
.tp-report-status-progress { height:6px; margin-top:14px; overflow:hidden; border-radius:999px; background:#e1ebfa; }
.tp-report-status-progress i { display:block; height:100%; border-radius:inherit; background:var(--tp-primary); }
.tp-report-overall-detail { margin:13px 0 0; color:var(--tp-sub); font-size:12px; line-height:1.55; }
.tp-delivery-header h3 { margin:0; font-size:19px !important; }
.tp-report-toolbar-kicker { margin-bottom:7px; color:var(--tp-sub); font-size:11px; font-weight:750; letter-spacing:.08em; text-transform:uppercase; }
.tp-report-outline { margin:16px 0 0; padding:14px 16px; border:1px solid var(--tp-line); border-radius:10px; background:#fbfcfe; }
.tp-report-outline-title { margin-bottom:8px; color:var(--tp-ink); font-size:12px; font-weight:750; }
.tp-report-outline a { display:block; padding:4px 0; color:var(--tp-sub); font-size:12px; line-height:1.45; text-decoration:none; }
.tp-report-outline a:hover, .tp-report-outline a:focus, .tp-report-outline a:focus-visible {
 margin:0 -7px; padding-left:7px; padding-right:7px; border-radius:5px;
 background:var(--tp-primary-soft); color:var(--tp-primary); text-decoration:none;
}
.tp-report-outline a.is-chapter { color:var(--tp-ink); font-weight:650; }
.tp-report-outline a.is-subsection { padding-left:16px; }
.tp-report-body a:target + h1, .tp-report-body a:target + h2,
.tp-report-body a:target + h3, .tp-report-body a:target + h4 {
 margin-left:-10px; padding-left:8px; border-left:2px solid var(--tp-primary);
}
.tp-report-issues { margin-top:4px; }
.tp-report-issues-head { display:flex; align-items:baseline; justify-content:space-between; gap:16px; }
.tp-report-issues-head h3 { margin:0; font-size:17px !important; }
.tp-report-issues-summary { display:flex; flex-wrap:wrap; gap:6px; color:var(--tp-sub); font-size:11px; }
.tp-report-issues-summary span { padding:3px 7px; border-radius:999px; background:#f1f4f8; }
.tp-report-issues-summary .is-blocker { background:#fff0f0; color:#b42318; }
.tp-report-issues-summary .is-warning { background:#fff7e6; color:#8a5a00; }
.tp-report-issues-summary .is-human-review { background:#edf4ff; color:var(--tp-brand-ink); }
.tp-report-issues-group { margin-top:18px; }
.tp-report-issues-group-title { display:flex; align-items:center; gap:8px; margin-bottom:2px; color:var(--tp-ink); }
.tp-report-issues-group-title h4 { margin:0; font-size:13px !important; font-weight:750; }
.tp-report-issues-group-title span { color:var(--tp-faint); font-size:11px; }
.tp-report-issue { display:block; margin:0; padding:0; border:0; background:transparent; }
.tp-report-issue-badge { display:inline-flex; padding:3px 8px; border-radius:999px; background:#f1f4f8; color:var(--tp-sub); font-size:11px; font-weight:750; }
.tp-report-issue.is-blocker .tp-report-issue-badge { background:#fff0f0; color:#b42318; }
.tp-report-issue.is-warning .tp-report-issue-badge { background:#fff7e6; color:#8a5a00; }
.tp-report-issue.is-human-review .tp-report-issue-badge { background:#edf4ff; color:var(--tp-brand-ink); }
.tp-report-issue h4 { margin:8px 0 0; color:var(--tp-ink); font-size:15px; }
.tp-report-issue p { margin:5px 0 10px; color:var(--tp-sub); font-size:13px; line-height:1.6; }
.tp-report-issue-meta { display:grid; grid-template-columns:72px minmax(0,1fr); gap:5px 10px; }
.tp-report-issue-meta span { color:var(--tp-faint); font-size:11px; }
.tp-report-issue-meta strong { color:var(--tp-ink); font-size:12px; font-weight:600; line-height:1.55; }
.tp-report-issue-next { display:inline-flex; align-items:center; min-height:32px; padding:0 8px; color:var(--tp-primary); font-size:11px; font-weight:750; white-space:nowrap; }
[class*="st-key-report_issue_row_action_"] .stButton > button { min-height:36px; white-space:nowrap; }
[class*="st-key-report_issue_row_"]:not([class*="st-key-report_issue_row_action_"]) { margin:0; padding:15px 0 15px 14px; border-bottom:1px solid var(--tp-line-subtle); border-left:3px solid #d5a12c; }
[class*="st-key-report_issue_row_"]:not([class*="st-key-report_issue_row_action_"]) .stHorizontalBlock { align-items:flex-start; }
[class*="st-key-report_issue_row_blocker_"] { border-left-color:var(--tp-danger); }
[class*="st-key-report_issue_row_human_review_"] { border-left-color:var(--tp-primary); }
.tp-report-issues-empty { margin-top:14px; padding:15px 0; color:var(--tp-sub); font-size:13px; }
[class*="st-key-report_recommended_"] { margin-top:24px; padding:17px 19px; border:1px solid #b9d3f8; border-left:4px solid var(--tp-primary); border-radius:12px; background:#f8fbff; }
[class*="st-key-report_recommended_"] .stHorizontalBlock { align-items:center; }
.tp-report-recommended-copy { min-width:0; }
.tp-report-recommended-kicker { color:var(--tp-primary); font-size:11px; font-weight:800; letter-spacing:.07em; text-transform:uppercase; }
.tp-report-recommended-copy h3 { margin:5px 0 0; color:var(--tp-ink); font-size:16px !important; }
.tp-report-recommended-copy p { margin:4px 0 0; color:var(--tp-sub); font-size:12px; line-height:1.55; }
[class*="st-key-report_recommended_"] .stButton > button { min-width:150px; }
.tp-report-focus { margin-top:24px; padding:18px 19px 20px; border:1px solid var(--tp-line); border-radius:12px; background:#fff; }
.tp-report-focus-head { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:12px; }
.tp-report-focus-head h3 { margin:0; font-size:17px !important; }
.tp-report-body { margin-top:16px; padding:30px 34px 36px; border:1px solid var(--tp-line); border-radius:12px; background:#fff; }
.tp-report-body h1, .tp-report-body h2, .tp-report-body h3, .tp-report-body h4 { color:var(--tp-ink); }
.tp-report-body h1 { margin:0 0 1.1em; font-size:25px !important; line-height:1.35 !important; }
.tp-report-body h2 { margin:1.55em 0 .55em; font-size:21px !important; line-height:1.45 !important; }
.tp-report-body h3 { margin:1.25em 0 .45em; font-size:17px !important; line-height:1.5 !important; }
.tp-report-body h4 { margin:1.15em 0 .4em; font-size:15px !important; }
.tp-report-body p, .tp-report-body li { max-width:72ch; color:#283548; font-size:15px; line-height:1.9; }
.tp-report-body p { margin:0 0 1em; }
.tp-report-body ul, .tp-report-body ol { margin:0 0 1em; padding-left:1.5em; }
.tp-report-body blockquote { max-width:72ch; margin:18px 0; padding:12px 18px; border-left:3px solid #b7cdf0; border-radius:0 8px 8px 0; background:#f7faff; color:#43536b; }
.tp-report-body blockquote p { color:#43536b; font-size:14px; line-height:1.75; }
.tp-report-body table { display:block; max-width:100%; overflow-x:auto; margin:18px 0 22px; border-collapse:collapse; }
.tp-report-body th, .tp-report-body td { min-width:110px; padding:8px 10px; border:1px solid var(--tp-line); font-size:13px; line-height:1.6; text-align:left; }
.tp-report-body th { background:#f7f9fc; color:var(--tp-ink); font-weight:700; }
.tp-report-body hr { margin:24px 0; border:0; border-top:1px solid var(--tp-line-subtle); }
.tp-report-body a { color:var(--tp-primary); }
.tp-checklist { margin:16px 0 22px; border-top:1px solid var(--tp-line-subtle); }
.tp-check-row { display:flex; gap:11px; align-items:center; padding:12px 0; border-bottom:1px solid var(--tp-line-subtle); color:var(--tp-ink); font-size:13px; }
.tp-check-row i { font-style:normal; width:20px; text-align:center; color:var(--tp-success); font-size:16px; }
.tp-check-row.is-warning i { color:#d97706; }
.tp-version-list { display:grid; gap:8px; margin-top:14px; }
.tp-version { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 14px; border:1px solid var(--tp-line); border-radius:9px; background:#fff; }
.tp-version strong { color:var(--tp-ink); font-size:13px; }
.tp-version span { color:var(--tp-sub); font-size:12px; }
.tp-asset-list { display:grid; gap:8px; margin-top:16px; }
.tp-asset-row { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:13px 14px; border:1px solid var(--tp-line); border-radius:10px; background:#fff; }
.tp-asset-copy { min-width:0; }
.tp-asset-copy strong { display:block; color:var(--tp-ink); font-size:13px; }
.tp-asset-copy span { display:block; margin-top:4px; color:var(--tp-sub); font-size:11px; }
.tp-empty { padding:34px 20px; border:1px dashed #cbd5e1; border-radius:12px; background:#fbfcfe; color:var(--tp-sub); text-align:center; }
.tp-tech-detail { color:var(--tp-sub); font-size:12px; }
.tp-readiness-card { margin:0 0 14px; padding:17px 18px 15px; border:1px solid #edd39d; border-left:4px solid #c47b00; border-radius:12px; background:#fffaf0; }
.tp-readiness-card.is-success { border-color:#b8dfcc; border-left-color:var(--tp-success); background:#f3fbf7; }
.tp-readiness-card.is-danger { border-color:#efc1bd; border-left-color:var(--tp-danger); background:#fff8f7; }
.tp-readiness-card.is-info { border-color:#b9d3f8; border-left-color:var(--tp-primary); background:#f5f9ff; }
.tp-readiness-card.is-info .tp-readiness-kicker { color:var(--tp-brand-ink); }
.tp-readiness-card.is-neutral { border-color:var(--tp-line); border-left-color:#94a3b8; background:#f8fafc; }
.tp-readiness-card.is-warning .tp-readiness-kicker { color:#8a5a00; }
.tp-readiness-card.is-success .tp-readiness-kicker { color:#147a4a; }
.tp-readiness-card.is-danger .tp-readiness-kicker { color:#b42318; }
.tp-readiness-kicker { color:#8a5a00; font-size:10px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.tp-readiness-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-top:5px; }
.tp-readiness-head h3 { margin:0; color:var(--tp-ink); font-size:22px !important; line-height:1.25; }
.tp-readiness-head p { max-width:58ch; margin:6px 0 0; color:#6f4d13; font-size:13px; line-height:1.55; }
.tp-readiness-card.is-success .tp-readiness-head p { color:#315f48; }
.tp-readiness-card.is-danger .tp-readiness-head p { color:#6f3130; }
.tp-readiness-flag { flex:0 0 auto; padding:5px 8px; border-radius:999px; background:#fff0cf; color:#8a5a00; font-size:10px; font-weight:800; white-space:nowrap; }
.tp-readiness-card.is-success .tp-readiness-flag { background:#dff4e8; color:#147a4a; }
.tp-readiness-card.is-danger .tp-readiness-flag { background:#fff0f0; color:#b42318; }
.tp-readiness-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:0 12px; margin-top:15px; padding-top:8px; border-top:1px solid #f0dfbd; }
.tp-readiness-card.is-success .tp-readiness-grid { border-top-color:#d5ebdf; }
.tp-readiness-card.is-danger .tp-readiness-grid { border-top-color:#f1d8d5; }
.tp-readiness-item { min-width:0; padding:10px 0 9px; border-bottom:1px solid #f1e5cb; }
.tp-readiness-card.is-success .tp-readiness-item { border-bottom-color:#e1f0e7; }
.tp-readiness-card.is-danger .tp-readiness-item { border-bottom-color:#f4e1df; }
.tp-readiness-item-head { display:flex; align-items:center; gap:7px; min-width:0; }
.tp-readiness-icon { display:inline-grid; flex:0 0 auto; place-items:center; width:18px; height:18px; border-radius:50%; font-size:11px; font-weight:850; line-height:1; }
.tp-readiness-item.is-pass .tp-readiness-icon { background:#dff4e8; color:#147a4a; }
.tp-readiness-item.is-warning .tp-readiness-icon { background:#fff0cf; color:#8a5a00; }
.tp-readiness-item.is-pending .tp-readiness-icon { background:#e9edf3; color:#536176; }
.tp-readiness-label { min-width:0; color:var(--tp-ink); font-size:12px; font-weight:750; line-height:1.35; }
.tp-readiness-detail { margin:5px 0 0 25px; color:var(--tp-sub); font-size:11px; line-height:1.45; }
.tp-readiness-status { margin:4px 0 0 25px; color:var(--tp-faint); font-size:10px; font-weight:750; }
.tp-readiness-item.is-pass .tp-readiness-status { color:#147a4a; }
.tp-readiness-item.is-warning .tp-readiness-status { color:#8a5a00; }
.tp-readiness-item.is-pending .tp-readiness-status { color:#536176; }
.tp-next-action-copy { min-width:0; }
.tp-next-action-kicker { color:var(--tp-primary); font-size:10px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.tp-next-action-copy strong { display:block; margin-top:4px; color:var(--tp-ink); font-size:14px; }
.tp-next-action-copy p { margin:4px 0 0; color:var(--tp-sub); font-size:12px; line-height:1.45; }
[class*="st-key-delivery_next_action_"] { margin:0 0 14px; padding:13px 15px; border:1px solid #c9dcfb; border-left:3px solid var(--tp-primary); border-radius:10px; background:#f7faff; }
[class*="st-key-delivery_next_action_"] [data-testid="stHorizontalBlock"] { align-items:center; gap:16px; }
[class*="st-key-delivery_next_action_"] .stButton > button { min-height:34px; white-space:normal; }
.tp-impact-panel { margin:0 0 14px; padding:15px 16px 13px; border:1px solid #edd39d; border-left:3px solid #c47b00; border-radius:10px; background:#fffaf0; }
.tp-impact-panel > strong { display:block; color:#714c00; font-size:14px; }
.tp-impact-panel > p { margin:4px 0 0; color:#8a5a00; font-size:12px; line-height:1.45; }
.tp-impact-summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:12px; }
.tp-impact-summary div { min-width:0; padding-top:9px; border-top:1px solid #f0dfbd; }
.tp-impact-summary span { display:block; color:#8a6a24; font-size:10px; font-weight:700; }
.tp-impact-summary strong { display:block; margin-top:4px; color:#5f4600; font-size:12px; line-height:1.4; }
.tp-impact-chain { display:grid; gap:7px; margin-top:8px; }
.tp-impact-chain-row { display:flex; align-items:baseline; gap:8px; color:var(--tp-ink); font-size:12px; line-height:1.45; }
.tp-impact-chain-row i { flex:0 0 auto; color:#c47b00; font-style:normal; font-weight:800; }
.tp-impact-chain-row strong { flex:0 0 52px; color:var(--tp-ink); font-weight:750; white-space:nowrap; }
.tp-impact-chain-row span { flex:1 1 auto; min-width:0; color:var(--tp-sub); }
.tp-technical-note { margin:0 0 14px; padding:10px 12px; border:1px solid var(--tp-line-subtle); border-radius:8px; background:#fbfcfe; }
.tp-technical-note strong { display:block; color:var(--tp-ink); font-size:12px; }
.tp-technical-note small { display:block; margin-top:4px; color:var(--tp-faint); font-size:10px; line-height:1.45; }
.tp-qa-profile { margin-bottom:12px; padding:11px 13px; }
.tp-qa-rule { border-radius:8px; }
.tp-qa-source { margin-top:6px; color:var(--tp-faint); font-size:10px; line-height:1.45; }
.tp-qa-rule .stExpander { margin-top:4px; }
.tp-qa-work-summary { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin:0 0 10px; padding:13px 14px; border:1px solid #f0d5a1; border-left:3px solid #c47b00; border-radius:9px; background:#fffaf0; }
.tp-qa-work-summary strong { color:#714c00; font-size:13px; }
.tp-qa-work-summary span { color:#8a5a00; font-size:11px; text-align:right; }
.tp-connection-summary { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:15px 0 20px; padding:13px 15px; border:1px solid var(--tp-line); border-radius:10px; background:#fbfcfe; }
.tp-connection-summary div { min-width:0; }
.tp-connection-summary span, .tp-connection-summary small { display:block; color:var(--tp-sub); font-size:11px; }
.tp-connection-summary strong { display:block; margin:3px 0; color:var(--tp-ink); font-size:13px; }
[class*="st-key-settings_connection_"] { margin:0 0 16px; }
[class*="st-key-translation_search_"] input:focus:not([aria-invalid="true"]),
[class*="st-key-translation_search_"] input:focus-visible:not([aria-invalid="true"]),
[class*="st-key-case_search_"] input:focus:not([aria-invalid="true"]),
[class*="st-key-case_search_"] input:focus-visible:not([aria-invalid="true"]) {
 border-color:#69a7f8 !important;
 box-shadow:0 0 0 3px rgba(18,103,232,.14) !important;
}
[class*="st-key-translation_search_"] [data-testid="stTextInputRootElement"]:focus-within {
 border-color:#69a7f8 !important;
 box-shadow:0 0 0 3px rgba(18,103,232,.14) !important;
}
[class*="st-key-case_search_"] [data-testid="stTextInputRootElement"]:focus-within {
 border-color:#69a7f8 !important;
 box-shadow:0 0 0 3px rgba(18,103,232,.14) !important;
}
@media (min-width: 761px) and (max-width: 1199px) {
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) {
  padding-left:24px; padding-right:24px;
 }
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) [data-testid="stHorizontalBlock"]:has(.st-key-workspace_nav_col) {
  display:grid !important; grid-template-columns:minmax(118px,.82fr) minmax(0,4fr);
  align-items:start; gap:12px;
 }
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) [data-testid="stHorizontalBlock"]:has(.st-key-workspace_nav_col) > .stColumn:has(.st-key-workspace_nav_col) { grid-row:1 / span 2; }
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) [data-testid="stHorizontalBlock"]:has(.st-key-workspace_nav_col) > .stColumn:has(.st-key-workspace_main_col) { grid-column:2; }
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) [data-testid="stHorizontalBlock"]:has(.st-key-workspace_nav_col) > .stColumn:has(.st-key-workspace_context_col) { grid-column:2; margin-top:4px; }
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) [data-testid="stHorizontalBlock"]:has(.st-key-workspace_nav_col) > .stColumn { width:auto !important; min-width:0 !important; flex:none !important; }
 .st-key-workspace_main_col { padding:0 10px; }
 .st-key-workspace_context_col { padding-left:0; }
 .st-key-workspace_nav_col { padding-right:12px; }
 .tp-review-pane { min-height:440px; }
}
@media (max-width: 900px) {
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) [data-testid="stHorizontalBlock"]:has(.st-key-workspace_nav_col) {
  display:block !important;
 }
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) [data-testid="stHorizontalBlock"]:has(.st-key-workspace_nav_col) > .stColumn {
  display:block !important; width:100% !important; max-width:none !important;
  min-width:0 !important; flex:none !important;
 }
 .st-key-workspace_nav_col { position:static; min-height:auto; padding:0 0 12px; border-right:0; border-bottom:1px solid var(--tp-line-subtle); }
 .st-key-workspace_nav .stButton > button { justify-content:flex-start; min-height:38px; white-space:nowrap; }
 .tp-workspace-nav-caption { margin-bottom:6px; }
 .st-key-workspace_nav { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:4px 8px; }
 .st-key-workspace_nav > [data-testid="stLayoutWrapper"] { min-width:0; }
 .st-key-workspace_nav [class*="st-key-workspace_nav_item_"] { margin:0; min-width:0; }
 .st-key-workspace_nav [class*="st-key-workspace_nav_item_"] [data-testid="stHorizontalBlock"] { display:block !important; }
 .st-key-workspace_nav [class*="st-key-workspace_nav_item_"] [data-testid="stHorizontalBlock"] > .stColumn {
  width:100% !important; max-width:none !important; min-width:0 !important;
 }
 .st-key-workspace_nav [class*="st-key-workspace_nav_item_"] .stButton > button {
  justify-content:center; min-height:34px; padding:0 4px; font-size:12px;
 }
 .st-key-workspace_nav [class*="st-key-workspace_nav_item_"] .tp-nav-state {
  min-width:0; text-align:center;
 }
 .st-key-workspace_main_col { padding:14px 0 0; }
 .st-key-workspace_context_col { padding:14px 0 0; margin-top:0; }
 .tp-cat-progress { margin-left:0; flex-basis:100%; min-width:0; max-width:none; }
}
@media (max-width: 1050px) {
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) { padding:22px 24px 48px; }
 .st-key-workspace_main_col { padding:0 18px; }
 .st-key-workspace_context_col { padding-left:0; margin-top:20px; }
 .st-key-translation_inspector { padding-left:0; }
 .tp-card-grid, .tp-stage-grid { grid-template-columns:1fr; }
 .tp-readiness-grid, .tp-impact-summary { grid-template-columns:repeat(2,minmax(0,1fr)); }
 .tp-dependency-panel { display:block; }
 .tp-dependency-panel span, .tp-dependency-panel small { display:block; margin-top:7px; text-align:left; }
 .tp-qa-profile b { margin-left:0; width:100%; }
 .tp-connection-summary { grid-template-columns:1fr; }
}
@media (max-width: 760px) {
 [data-testid="stMainBlockContainer"]:has(.tp-workspace-shell) { padding:16px 14px 40px; }
 .tp-workspace-topbar { display:block; }
 .tp-workspace-status { padding-top:12px; }
 .st-key-workspace_main_col { padding:14px 0 0; }
 .st-key-workspace_context_col { padding:14px 0 0; }
 .tp-readiness-grid, .tp-impact-summary { grid-template-columns:1fr; }
 .tp-readiness-head { display:block; }
 .tp-readiness-flag { display:inline-block; margin-top:10px; }
 [class*="st-key-delivery_next_action_"] [data-testid="stHorizontalBlock"] { flex-direction:column; align-items:stretch; }
 [class*="st-key-delivery_next_action_"] .stButton > button { width:100%; margin-top:12px; }
 .tp-review-pane, .tp-review-pane + .tp-review-pane { min-height:auto; margin:0; border-radius:12px; }
 .tp-review-readiness { grid-template-columns:1fr; }
 .tp-review-progress { text-align:left; }
 .tp-review-progress-grid { grid-column:auto; }
 .tp-review-compare-text { min-height:auto; }
 [class*="st-key-review_action_bar_"] [data-testid="stHorizontalBlock"] { flex-direction:row; align-items:stretch; }
 .tp-report-overall-grid { grid-template-columns:1fr; gap:10px; }
 .tp-report-issues-head { display:block; }
 .tp-report-issues-summary { margin-top:9px; }
 [class*="st-key-report_issue_row_"]:not([class*="st-key-report_issue_row_action_"]) { padding-left:11px; }
 [class*="st-key-report_issue_row_"]:not([class*="st-key-report_issue_row_action_"]) .stHorizontalBlock,
 [class*="st-key-report_recommended_"] .stHorizontalBlock { flex-direction:column; }
 [class*="st-key-report_issue_row_action_"] .stButton > button { width:100%; }
 [class*="st-key-report_recommended_"] .stButton > button { width:100%; margin-top:13px; }
 .tp-report-focus { padding:16px 14px 18px; }
 .tp-report-body { padding:20px 17px; }
 .tp-qa-work-summary { display:block; }
 .tp-qa-work-summary span { display:block; margin-top:5px; text-align:left; }
}
"""
_LANGUAGE_ASSETS_CSS = """
/* ================= Language Assets Workspace（术语与翻译记忆） =================
   目标：专业 CAT 工具的语言资产管理中心——高密度行、克制的分隔线、sticky 工具条、
   右侧 Inspector。复用既有 --tp-* token，不引入新的圆角/阴影/蓝色。 */
.la-summary { display:flex; flex-wrap:wrap; gap:8px; margin:2px 0 12px; }
.la-stat { display:inline-flex; align-items:baseline; gap:7px; padding:5px 12px;
 border:1px solid var(--tp-hairline-strong); border-radius:var(--tp-radius-sm);
 background:var(--tp-surface); box-shadow:var(--tp-shadow-sm); }
.la-stat > span { font-size:12px; color:var(--tp-sub); }
.la-stat > strong { font-size:15px; font-weight:700; color:var(--tp-ink);
 font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
.la-stat.is-warn > strong { color:var(--tp-warn); }

[class*="st-key-library_tab"] { margin-bottom:2px; }
[class*="st-key-library_tab"] button { font-size:13px; font-weight:600; }

.la-head { font-size:11px; font-weight:700; color:var(--tp-faint);
 text-transform:uppercase; letter-spacing:.06em; }
[class*="st-key-la_head_row"] { border-bottom:1px solid var(--tp-hairline-strong);
 padding-bottom:4px; margin-bottom:2px; }
.la-hint { font-size:12px; color:var(--tp-faint); }

/* 行：目标 56–76px。分隔线只在行之间，不用卡片。
   注意：Streamlit 把每个元素包进 stLayoutWrapper，所以行容器**永远是**它父节点的
   :last-child。用 `[class*="st-key-la_row_"]:last-child` 去收尾会把 72 行的分隔线
   全部清零——必须从列表容器那一层去挑真正的最后一行。 */
[class*="st-key-la_list"] { border:1px solid var(--tp-hairline-strong);
 border-radius:var(--tp-radius-md); background:var(--tp-surface);
 overflow:hidden; margin-bottom:10px; }
[class*="st-key-la_row_"] { border-bottom:1px solid var(--tp-hairline);
 padding:8px; transition:background .12s ease; }
[class*="st-key-la_list"] > [data-testid="stLayoutWrapper"]:last-child
 [class*="st-key-la_row_"] { border-bottom:0; }
[class*="st-key-la_row_"]:hover { background:var(--tp-tint-hover); }
[class*="st-key-la_row_"]:has(.la-sel-flag) { background:var(--tp-tint-active);
 box-shadow: inset 2px 0 0 var(--tp-primary); }
.la-sel-flag { display:none; }
[class*="st-key-la_row_"] [data-testid="stHorizontalBlock"] { align-items:center; }
[class*="st-key-la_row_"] [data-testid="stVerticalBlock"] { gap:0; }
/* 行内按钮统一走**后代选择器** `.stButton button`，不要用 `.stButton > button`：
   带 help= 的按钮会被再包三层（div.st-emotion-cache → span.stTooltipIcon →
   span.stTooltipHoverTarget），直接子选择器会静默失效。行内按钮全都带 help，
   用 `>` 等于一条规则都不生效（见上方「Tooltip 包装层归一化」的说明）。 */
[class*="st-key-la_row_"] .stButton button { border:0; background:transparent;
 min-height:30px; padding:3px 6px; text-align:left;
 justify-content:flex-start !important;
 font-size:13px; font-weight:600; color:var(--tp-ink); box-shadow:none; }
[class*="st-key-la_row_"] .stButton button > div { justify-content:flex-start !important; }
[class*="st-key-la_row_"] .stButton button p { font-size:13px; line-height:1.35;
 margin:0; text-align:left !important; white-space:nowrap; overflow:hidden;
 text-overflow:ellipsis; }
[class*="st-key-la_row_"] .stButton button:hover { background:var(--tp-primary-soft);
 color:var(--tp-brand-ink); }
[class*="st-key-la_row_"] .stButton button:focus-visible {
 box-shadow:0 0 0 2px var(--tp-focus-ring); }
/* 行内动作保持轻量按钮，不做巨型主按钮。 */
[class*="st-key-la_quick_"] .stButton button,
[class*="st-key-la_task_"] .stButton button,
[class*="st-key-la_reject_"] .stButton button,
[class*="st-key-la_term_edit_save"] .stButton button,
[class*="st-key-la_term_delete"] .stButton button {
 border:1px solid var(--tp-hairline-strong) !important;
 background:var(--tp-surface) !important; justify-content:center !important;
 text-align:center !important; font-weight:600; }
[class*="st-key-la_quick_"] .stButton button:hover {
 border-color:var(--tp-border) !important; background:var(--tp-primary-soft) !important; }
[class*="st-key-la_row_"] .stCheckbox { display:flex; justify-content:center; }
/* 行内「更多操作」：默认不抢视觉，hover / 展开时才显形。
   注意必须用后代选择器——Streamlit 的 popover 按钮不在 .stPopover 的直接子层。 */
[class*="st-key-la_row_"] .stPopover button { border:0; background:transparent;
 min-height:30px; padding:2px 6px; color:var(--tp-faint); box-shadow:none; }
[class*="st-key-la_row_"]:hover .stPopover button,
[class*="st-key-la_row_"] .stPopover button:hover,
[class*="st-key-la_row_"] .stPopover button:focus-visible,
[class*="st-key-la_row_"] .stPopover button[aria-expanded="true"] {
 color:var(--tp-ink); background:var(--tp-tint-hover); }

.la-meta { font-size:12px; color:var(--tp-sub); line-height:1.4; display:block;
 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.la-target { font-size:13px; font-weight:600; color:var(--tp-brand-ink);
 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.la-cell { font-size:13px; color:var(--tp-sub); white-space:nowrap;
 overflow:hidden; text-overflow:ellipsis; }
.la-num { font-size:13px; color:var(--tp-ink); font-variant-numeric:tabular-nums; }
.la-chip { display:inline-block; padding:1px 7px; border-radius:999px;
 font-size:11px; font-weight:600; line-height:1.6; white-space:nowrap;
 border:1px solid var(--tp-hairline-strong); color:var(--tp-sub);
 background:var(--tp-surface-sunken); }
.la-chip.is-ok { color:#0b6b47; background:var(--tp-success-soft); border-color:#abefc6; }
.la-chip.is-warn { color:var(--tp-warn); background:var(--tp-warn-soft); border-color:#fedf89; }
.la-chip.is-danger { color:#b42318; background:var(--tp-danger-soft); border-color:#fecdca; }
.la-chip.is-info { color:#0b4ec7; background:var(--tp-primary-soft); border-color:var(--tp-border); }

/* 工具条：sticky，滚动时筛选条件始终可见。 */
[class*="st-key-la_toolbar"] { position:sticky; top:0; z-index:6;
 background:var(--tp-canvas); padding:2px 0 8px; }

/* 批量操作条：只在有选择时出现，不做成每行重复按钮。 */
[class*="st-key-la_bulk_bar"] { background:var(--tp-primary-soft);
 border:1px solid var(--tp-border); border-radius:var(--tp-radius-sm);
 padding:6px 10px; margin:2px 0 8px; }
[class*="st-key-la_bulk_bar"] [data-testid="stHorizontalBlock"] { align-items:center; }
[class*="st-key-la_bulk_bar"] p { font-size:13px; font-weight:600;
 color:var(--tp-brand-ink); margin:0; }

/* 工具条 / 批量条 / 分页 / Inspector 内的按钮：
   全局 `.stButton > button` 是 44px 的「表单按钮」尺寸，塞进高密度区域会显得笨重
   （也违背「不要巨型按钮」）。这里按用途压到 28–34px。
   注意这些选择器一律走后代形式 `.stButton button`，理由见上方行内按钮的注释。 */
[class*="st-key-la_bulk_bar"] .stButton button,
[class*="st-key-la_select_high"] .stButton button,
[class*="st-key-la_new_term"] .stButton button,
[class*="st-key-la_retry"] .stButton button { min-height:32px; font-size:13px;
 font-weight:600; }
[class*="st-key-la_select_high"] .stButton button { font-weight:500; }
[class*="st-key-la_tm_more"] .stButton button,
[class*="st-key-la_review_more"] .stButton button,
[class*="st-key-la_pos_more_"] .stButton button {
 min-height:32px; font-size:13px; font-weight:600; color:var(--tp-sub);
 border-style:dashed; background:transparent; }
[class*="st-key-la_tm_more"] .stButton button:hover,
[class*="st-key-la_review_more"] .stButton button:hover,
[class*="st-key-la_pos_more_"] .stButton button:hover {
 color:var(--tp-brand-ink); border-style:solid; background:var(--tp-primary-soft); }
/* 「定位到工作台」是 Inspector 里的次级动作，做成紧凑文字按钮，不抢主操作。 */
[class*="st-key-la_jump_"] .stButton button { min-height:28px; font-size:12px;
 font-weight:600; color:var(--tp-brand-ink); border-color:transparent;
 background:transparent; }
[class*="st-key-la_jump_"] .stButton button:hover {
 background:var(--tp-primary-soft); border-color:var(--tp-border); }
/* 行内「更多操作」弹出菜单项：紧凑、左对齐、无边框。popover 内容可能被 portal
   到 body，所以这些规则按 key 自身匹配，不依赖是否在行容器里。 */
[class*="st-key-la_inspect_"] .stButton button,
[class*="st-key-la_edit_"] .stButton button,
[class*="st-key-la_promote_"] .stButton button,
[class*="st-key-la_term_promote_"] .stButton button {
 min-height:32px; font-size:13px; font-weight:500;
 justify-content:flex-start !important; text-align:left !important;
 border-color:transparent; background:transparent; }
/* 缺失能力用 disabled + help 说明原因，必须看得出「不可用」而不是「能点」。 */
[class*="st-key-la_promote_"] .stButton button:disabled,
[class*="st-key-la_term_promote_"] .stButton button:disabled {
 background:var(--tp-surface-sunken) !important;
 border-color:var(--tp-hairline-strong) !important; color:var(--tp-faint) !important; }

/* 右侧 Inspector：sticky；主列表宽度不随 Inspector 变化。 */
[class*="st-key-la_inspector"] { position:sticky; top:8px;
 border:1px solid var(--tp-hairline-strong); border-radius:var(--tp-radius-md);
 background:var(--tp-surface); padding:12px 14px 16px; box-shadow:var(--tp-shadow-sm); }
.la-inspector-title { font-size:15px; font-weight:700; color:var(--tp-ink);
 margin:0 0 2px; word-break:break-word; }
.la-inspector-sub { font-size:12px; color:var(--tp-sub); margin:0 0 10px; }
.la-kv { display:grid; grid-template-columns:86px minmax(0,1fr); gap:4px 10px;
 font-size:12px; margin:0 0 10px; }
.la-kv dt { color:var(--tp-faint); }
.la-kv dd { color:var(--tp-ink); margin:0; word-break:break-word; }
.la-divider { height:1px; background:var(--tp-hairline); margin:10px 0; }
.la-kicker { font-size:11px; font-weight:700; letter-spacing:.06em;
 text-transform:uppercase; color:var(--tp-faint); margin:0 0 6px; }
.la-context { font-size:12px; line-height:1.5; color:var(--tp-ink);
 background:var(--tp-surface-sunken); border-radius:var(--tp-radius-sm);
 padding:7px 9px; margin:0 0 6px; word-break:break-word; }
.la-context.is-target { background:var(--tp-primary-soft); }
.la-occ { font-size:12px; color:var(--tp-sub); line-height:1.7;
 font-variant-numeric:tabular-nums; }
.la-empty { border:1px dashed var(--tp-hairline-strong); border-radius:var(--tp-radius-md);
 background:var(--tp-surface); padding:26px 18px; text-align:center; }
.la-empty strong { display:block; font-size:14px; color:var(--tp-ink); margin-bottom:4px; }
.la-empty span { font-size:12.5px; color:var(--tp-sub); }
.la-empty.is-error { border-color:#fecdca; background:var(--tp-danger-soft); }
.la-group { font-size:12px; font-weight:700; color:var(--tp-ink); }
.la-group span { font-weight:500; color:var(--tp-faint); }

/* 窄屏：Inspector 从右侧栏改为在主列表下方整宽堆叠（drawer 的降级形态）。
   用 :has() 精确锁定「包含 Inspector 的那一个 horizontal block」，
   避免误伤 Tab 内部工具栏 / 行布局的横向 block。 */
@media (max-width: 1100px) {
 [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [class*="st-key-la_inspector"]) {
  flex-wrap:wrap; }
 [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [class*="st-key-la_inspector"]) > [data-testid="stColumn"] {
  width:100% !important; flex:1 1 100% !important; min-width:0 !important; }
 [class*="st-key-la_inspector"] { position:static; margin-top:10px; }
}
"""
_TASK_CREATION_CSS = """
/* ================= Compact task preparation surface ================= */
[data-testid="stMainBlockContainer"]:has(.st-key-task_settings_grid) {
 padding-bottom: 112px;
}
[data-testid="stMainBlockContainer"]:has(.st-key-task_settings_grid) .tp-title {
 margin-bottom: 22px;
}
.tp-task-section-heading {
 margin: 24px 0 10px; color: var(--tp-ink); font-size: 14px;
 font-weight: 700; line-height: 1.4; letter-spacing: .01em;
}
.tp-task-section-heading:first-child { margin-top: 0; }
.st-key-source_documents, .st-key-source_file_summary { margin-bottom: 0; }
.st-key-source_file_card {
 min-height: 112px; border: 1px solid var(--tp-hairline-strong);
 border-radius: var(--tp-radius-md); background: var(--tp-surface);
 box-shadow: var(--tp-shadow-sm); overflow: hidden;
}
.st-key-source_file_card .tp-source-file {
 min-height: 112px; padding: 14px 16px 48px; border: 0; border-radius: 0;
 background: transparent;
}
.st-key-source_file_card .tp-source-file-ready { top: 15px; }
.st-key-source_file_card .tp-source-ready {
 top: 15px; right: 16px; bottom: auto;
}
.st-key-source_file_card > [data-testid="stElementContainer"]:has(.st-key-source_file_actions) {
 position: absolute !important; left: auto !important; right: 12px !important;
 top: auto !important; bottom: 8px !important; width: auto !important;
 height: auto !important; z-index: 3;
}
.st-key-source_file_actions { width: auto; margin: 0; }
.st-key-source_file_actions [data-testid="stHorizontalBlock"] {
 width: auto; gap: 5px; align-items: center;
}
.st-key-source_file_actions [data-testid="stColumn"] {
 flex: 0 0 auto; width: auto !important; min-width: 0;
}
.st-key-source_file_actions .stButton { width: auto; }
.st-key-source_file_actions .stButton button {
 min-height: 27px; height: 27px; padding: 2px 8px; border: 0;
 background: transparent; color: var(--tp-sub); font-size: 12px; font-weight: 600;
 box-shadow: none;
}
.st-key-source_file_actions .stButton button:hover {
 border-color: var(--tp-border); background: var(--tp-primary-soft);
 color: var(--tp-brand-ink);
}
.st-key-source_file_actions [class*="remove_source"] .stButton button,
.st-key-source_file_actions [class*="remove_source"] button { color: var(--tp-danger); }
.st-key-source_file_actions [class*="remove_source"] .stButton button:hover,
.st-key-source_file_actions [class*="remove_source"] button:hover {
 background: var(--tp-danger-soft); color: var(--tp-danger);
}
.st-key-task_settings_grid { margin-top: 0; }
.st-key-task_settings_grid > [data-testid="stVerticalBlock"] { gap: 16px; }
.st-key-task_settings_grid [data-testid="stHorizontalBlock"] {
 align-items: stretch; gap: 16px;
}
.st-key-task_settings_grid [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
.st-key-task_settings_grid [data-testid="stHorizontalBlock"] > [data-testid="column"] {
 min-width: 0; display: flex; flex: 1 1 0;
}
.st-key-task_setting_language,
.st-key-task_setting_project,
.st-key-task_setting_glossary,
.st-key-task_setting_profile {
 width: 100%; min-height: 142px; box-sizing: border-box; padding: 15px 16px 12px;
 border: 1px solid var(--tp-hairline-strong); border-radius: var(--tp-radius-md);
 background: var(--tp-surface); box-shadow: var(--tp-shadow-sm);
}
.st-key-task_setting_language [data-testid="stWidgetLabel"],
.st-key-task_setting_project [data-testid="stWidgetLabel"] {
 margin-bottom: 6px; color: var(--tp-ink) !important; font-size: 13px !important;
 font-weight: 700 !important;
}
.st-key-task_setting_language [data-testid="stSelectbox"],
.st-key-task_setting_project [data-testid="stSelectbox"] { margin-bottom: 0; }
.st-key-task_setting_language [data-baseweb="select"] > div,
.st-key-task_setting_project [data-baseweb="select"] > div {
 min-height: 40px; background: var(--tp-canvas-soft) !important;
 border-color: var(--tp-hairline-strong) !important;
}
.st-key-task_setting_language [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
.st-key-task_setting_project [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {
 background: var(--tp-surface) !important;
}
.tp-setting-title {
 display: flex; align-items: center; gap: 7px; min-height: 19px;
 color: var(--tp-ink); font-size: 13px; font-weight: 700; line-height: 1.4;
}
.tp-setting-badge {
 margin-left: auto; padding: 2px 7px; border-radius: 999px;
 background: var(--tp-primary-soft); color: var(--tp-primary);
 font-size: 10px; font-weight: 700; line-height: 1.4;
}
.tp-setting-value { min-width: 0; margin-top: 10px; }
.tp-setting-value strong {
 display: block; overflow: hidden; color: var(--tp-brand-ink); font-size: 14px;
 line-height: 1.35; text-overflow: ellipsis; white-space: nowrap;
}
.tp-setting-value span { display: block; margin-top: 3px; color: var(--tp-sub); font-size: 11px; }
.tp-setting-status {
 display: inline-flex; align-items: center; min-height: 27px; color: var(--tp-sub);
 font-size: 12px; font-weight: 600; white-space: nowrap;
}
.tp-setting-status::before {
 content: ""; width: 6px; height: 6px; margin-right: 6px; border-radius: 50%;
 background: #98a2b3;
}
.tp-setting-status.is-ready { color: #147a4a; }
.tp-setting-status.is-ready::before { background: var(--tp-success); }
.tp-setting-status.is-running { color: var(--tp-primary); }
.tp-setting-status.is-running::before {
 background: var(--tp-primary); animation: tp-spin .8s linear infinite;
}
.tp-setting-status.is-error { color: #b42318; }
.tp-setting-status.is-error::before { background: var(--tp-danger); }
.st-key-task_setting_glossary [data-testid="stHorizontalBlock"],
.st-key-task_setting_profile [data-testid="stHorizontalBlock"] {
 align-items: center; gap: 8px;
}
.st-key-task_setting_glossary .stButton button,
.st-key-task_setting_profile .stButton button {
 min-height: 28px; height: 28px; padding: 2px 8px; font-size: 12px;
 font-weight: 600; border-color: var(--tp-hairline-strong);
}
.st-key-task_setting_glossary .stButton button:hover,
.st-key-task_setting_profile .stButton button:hover {
 border-color: var(--tp-border); background: var(--tp-primary-soft);
}
.st-key-task_setting_glossary .stCaption,
.st-key-task_setting_glossary [data-testid="stCaptionContainer"],
.st-key-task_setting_profile .stCaption,
.st-key-task_setting_profile [data-testid="stCaptionContainer"] {
 margin-top: 8px; color: var(--tp-sub) !important; font-size: 11px !important;
 line-height: 1.45; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.st-key-task_setting_profile .stToggle {
 margin: 5px 0 0; min-width: 0;
}
.st-key-task_setting_profile [data-testid="stWidgetLabel"] {
 color: var(--tp-ink) !important; font-size: 12px !important; font-weight: 650 !important;
}
.st-key-task_setting_project .stPopover { margin-top: 7px; }
.st-key-task_setting_project { gap: 8px !important; }
.st-key-task_project_helper [data-testid="stHorizontalBlock"] {
 align-items: center; gap: 8px;
}
.st-key-task_project_helper [data-testid="stCaptionContainer"] {
 margin-top: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.st-key-task_project_helper .stPopover { margin-top: 0; }
.st-key-task_setting_project .stPopover button {
 min-height: 24px; height: 24px; padding: 0 6px; border: 0;
 background: transparent; color: var(--tp-faint); font-size: 11px;
 box-shadow: none;
}
.st-key-task_setting_project .stPopover button:hover {
 background: var(--tp-primary-soft); color: var(--tp-brand-ink);
}
.st-key-task_termbase_picker { margin-top: 8px; }
.st-key-task_termbase_picker [data-testid="stFileUploaderDropzone"] {
 min-height: 72px; border-radius: var(--tp-radius-sm); box-shadow: none;
}
[data-testid="stMainBlockContainer"]:has(.st-key-task_settings_grid) [data-testid="stAlertContainer"] {
 margin-top: 8px;
}
[data-testid="stMainBlockContainer"]:has(.st-key-task_settings_grid) [data-testid="stLayoutWrapper"]:has(.st-key-task_action_bar) {
 position: static !important; z-index: auto;
}
[data-testid="stMainBlockContainer"]:has(.st-key-task_settings_grid) .st-key-task_action_bar {
 margin: 30px 0 0; padding: 12px 0; min-height: 56px;
 border-top: 1px solid var(--tp-hairline-strong);
 background: transparent;
}
[data-testid="stMainBlockContainer"]:has(.st-key-task_settings_grid) .st-key-task_action_bar [data-testid="stHorizontalBlock"] {
 align-items: center;
}
[data-testid="stMainBlockContainer"]:has(.st-key-task_settings_grid) .st-key-task_action_bar button[data-testid="stBaseButton-primary"] {
 min-width: 156px; min-height: 42px; height: 42px; border-radius: var(--tp-radius-md);
 font-size: 14px; font-weight: 700;
}
.st-key-new_task_action_in_flow .stButton button {
 min-height: 36px; height: 36px; border: 1px solid var(--tp-hairline-strong);
 background: transparent; color: var(--tp-sub); box-shadow: none; font-size: 13px;
}
.st-key-new_task_action_in_flow .stButton button:hover {
 border-color: var(--tp-border); background: var(--tp-primary-soft); color: var(--tp-brand-ink);
}
@media (max-width: 860px) {
 .st-key-task_settings_grid [data-testid="stHorizontalBlock"] { display: block !important; }
 .st-key-task_settings_grid [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
 .st-key-task_settings_grid [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  width: 100% !important; max-width: none !important; margin-bottom: 16px;
 }
 .st-key-task_settings_grid [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child,
 .st-key-task_settings_grid [data-testid="stHorizontalBlock"] > [data-testid="column"]:last-child {
  margin-bottom: 0;
 }
}
"""
st.markdown("<style>" + _CSS + _WORKSPACE_CSS + _LANGUAGE_ASSETS_CSS
            + _TASK_CREATION_CSS + "</style>",
            unsafe_allow_html=True)

# ================= 术语审核面板工具函数 =================
_EVIDENCE_LABELS = {
    "user": "用户提供", "local_termbase": "本地术语库",
    "project_override": "项目覆盖", "model_knowledge": "模型知识",
    "external": "外部来源",
}
_TERM_STATUS_LABELS = {
    "candidate": "候选",
    "provisional": "暂定",
    "locked": "已锁定",
    "rejected": "已拒绝",
}
_TERM_STATUS_VALUES = {label: value for value, label in _TERM_STATUS_LABELS.items()}
_TERM_BEHAVIOR_LABELS = {"translate": "翻译", "preserve": "保留原文"}
_TERM_BEHAVIOR_VALUES = {label: value for value, label in _TERM_BEHAVIOR_LABELS.items()}


def _evidence_label(e):
    evs = e.get("evidence") or []
    parts = []
    for ev in evs[:2]:
        label = _EVIDENCE_LABELS.get(ev.get("evidence_type"), ev.get("evidence_type"))
        note = (ev.get("note") or "").strip()
        parts.append(f"{label}：{note}" if note else label)
    return "；".join(parts)


def _conflict(e, entries):
    src = (e.get("source") or "").casefold()
    pref = e.get("preferred") or e.get("target")
    for other in entries:
        if other is e:
            continue
        if (other.get("source") or "").casefold() == src \
                and (other.get("preferred") or other.get("target")) != pref:
            return "冲突"
    return ""


def _first_context(e, paras, width=60):
    occ = e.get("occurrences") or []
    if not occ or not paras:
        return ""
    first = occ[0]
    if not (0 <= first < len(paras)):
        return ""
    text = paras[first]
    return text[:width] + ("…" if len(text) > width else "")


def _glossary_dataframe(entries, paras):
    rows = []
    for e in entries:
        rows.append({
            "选择": False,
            "id": e.get("id", ""),
            "source": e.get("source", ""),
            "proposed_target": e.get("proposed_target") or e.get("target", ""),
            "target": e.get("target", ""),
            "preferred": e.get("preferred", ""),
            "forbidden": "；".join(e.get("forbidden") or []),
            "behavior": e.get("behavior", "translate"),
            "status": e.get("status", "provisional"),
            "domain": e.get("domain", ""),
            "scope": e.get("scope", ""),
            "note": e.get("note", ""),
            "confidence": float(e.get("confidence") or 0.5),
            "出现次数": len(e.get("occurrences") or []),
            "上下文": _first_context(e, paras),
            "证据": _evidence_label(e),
            "冲突": _conflict(e, entries),
            "payload": json.dumps(e, ensure_ascii=False),
        })
    return pd.DataFrame(rows)


def _df_to_entries(df):
    entries = []
    for _, row in df.iterrows():
        base = {}
        payload = row.get("payload")
        if isinstance(payload, str) and payload.strip():
            try:
                base = json.loads(payload)
            except Exception:
                base = {}
        if not isinstance(base, dict):
            base = {}
        base = dict(base)

        def _s(key):
            v = row.get(key)
            return "" if pd.isna(v) else str(v).strip()

        base.update({
            "source": _s("source"),
            "proposed_target": _s("proposed_target"),
            "target": _s("target") or _s("proposed_target"),
            "preferred": _s("preferred") or _s("target") or _s("proposed_target"),
            "forbidden": [x.strip() for x in re.split(r"[;；]", _s("forbidden"))
                          if x.strip()],
            "behavior": _TERM_BEHAVIOR_VALUES.get(
                _s("behavior"), (_s("behavior") or "translate").lower()),
            "status": _TERM_STATUS_VALUES.get(
                _s("status"), (_s("status") or "provisional").lower()),
            "domain": _s("domain"),
            "scope": _s("scope"),
            "note": _s("note"),
        })
        try:
            base["confidence"] = float(row.get("confidence") or 0.5)
        except (TypeError, ValueError):
            base["confidence"] = 0.5
        entries.append(base)
    return entries


def _humanize_glossary_editor(df):
    """Keep persisted enum values out of the normal terminology editor."""
    displayed = df.copy()
    if "status" in displayed:
        displayed["status"] = displayed["status"].map(_TERM_STATUS_LABELS).fillna("待确认")
    if "behavior" in displayed:
        displayed["behavior"] = displayed["behavior"].map(_TERM_BEHAVIOR_LABELS).fillna("翻译")
    return displayed


def _page_title(title, sub):
    st.markdown(
        '<div class="tp-title"><div class="tp-brand-kicker">FOLIOTHREAD / WORKSPACE</div>'
        f'<h1>{title}</h1><p>{sub}</p></div>',
 unsafe_allow_html=True)


def _step_title(number, title, sub):
    st.markdown(
        f'<div class="tp-section-title">{title}</div>'
        f'<div class="tp-section-sub">{sub}</div>', unsafe_allow_html=True)


def _go_to_step(step):
    st.session_state.task_step = step


def _request_step(step):
    if step > 1 and not st.session_state.get("task_files"):
        st.session_state.step_gate_message = "请先上传原文。"
        st.session_state.task_step = 1
        return
    # Step 1 的画像是 Agent 的默认准备动作：用户点击下一步时才执行，
    # 侧栏直接点 Step 2 也必须经过同一条路径，避免绕过画像状态。
    if step == 2 and st.session_state.get("task_auto_profile", True) \
            and not _task_profile_is_ready():
        st.session_state.style_profiling_state = "running"
        st.session_state.pending_profile_step = 2
        st.session_state.pop("step_gate_message", None)
        return
    st.session_state.pop("step_gate_message", None)
    st.session_state.task_step = step


def _reset_provider_connection(preserve_models=False):
    st.session_state.provider_configured = False
    st.session_state.provider_connection_status = "unverified"
    st.session_state.reviewer_connection_status = "unverified"
    st.session_state.pop("provider_test_feedback", None)
    if not preserve_models:
        provider = st.session_state.get("provider_choice")
        if provider:
            st.session_state.pop(f"fetched_models_{provider}", None)
            st.session_state.pop(f"preferred_fetched_model_{provider}", None)
        st.session_state.pop("model_fetch_feedback", None)


def _reset_reviewer_connection():
    st.session_state.provider_configured = False
    st.session_state.reviewer_connection_status = "unverified"
    st.session_state.pop("provider_test_feedback", None)


def _open_provider_settings():
    st.session_state.app_view = "settings"


_PRESET_CONFIGS = {
    "快速": {
        "auto_term": False, "use_tm": True,
        "enable_understanding": False,
        "enable_review": False, "strict_terminology_governance": False,
        "batch_profile": "保守",
    },
    "标准": {
        "auto_term": True, "use_tm": True,
        "enable_understanding": True,
        "enable_review": False, "strict_terminology_governance": False,
        "batch_profile": "保守",
    },
    "学术增强": {
        "auto_term": True, "use_tm": True,
        "enable_understanding": True,
        "enable_review": True, "strict_terminology_governance": True,
        "batch_profile": "保守",
    },
}

# 批次策略：批次越大 → 调用次数越少 → 越快，但单次返回项数不符或截断的风险越高。
# 实测（本仓库 82 段文档）：保守 32 批，均衡 17 批，快速 13 批。
BATCH_PROFILES = {
    "保守": {"batch_size": 4, "max_batch_chars": 2400,
             "hint": "每批最多 4 段 / 2400 字符；调用次数最多，单次响应最稳"},
    "均衡": {"batch_size": 6, "max_batch_chars": 4800,
             "hint": "每批最多 6 段 / 4800 字符；调用次数约减半"},
    "快速": {"batch_size": 8, "max_batch_chars": 6400,
             "hint": "每批最多 8 段 / 6400 字符；最快，但更容易出现返回项数不符"},
}


def _batch_params(config):
    """把批次策略映射为 (batch_size, max_batch_chars)。"""
    profile = BATCH_PROFILES.get(str((config or {}).get("batch_profile") or "保守"),
                                 BATCH_PROFILES["保守"])
    return profile["batch_size"], profile["max_batch_chars"]

def _default_output_config():
    return core.default_delivery_config()


# Step 03 keeps the persisted `delivery_config` keys used by the export
# pipeline, but presents them through a smaller, user-facing preset model.
# The research-only keys are intentionally off in the ordinary delivery
# presets: they are additional products, not invisible files hidden behind a
# standard translation bundle.
_DELIVERY_OUTPUT_KEYS = (
    "enable_annotate", "enable_report", "deliver_plain_docx",
    "deliver_bilingual_docx", "deliver_pdf", "deliver_terms_xlsx",
    "deliver_tbx", "deliver_tmx", "deliver_jsonl", "deliver_evidence",
    "deliver_cases", "deliver_academic_workspace", "deliver_review_report",
)
_DELIVERY_RESEARCH_KEYS = (
    "enable_report", "deliver_evidence", "deliver_cases",
    "deliver_academic_workspace", "deliver_review_report",
)


def _delivery_config_for_outputs(*selected):
    """Return a complete export config for a UI delivery preset."""
    config = core.default_delivery_config()
    for key in _DELIVERY_OUTPUT_KEYS:
        config[key] = False
    for key in selected:
        if key in config:
            config[key] = True
    return config


_DELIVERY_PRESETS = {
    "compact": {
        "label": "精简交付",
        "description": "只保留最终译文，适合快速分享或内部查看。",
        "outputs": ("deliver_plain_docx",),
    },
    "standard": {
        "label": "标准交付",
        "description": "适合大多数正式翻译任务。",
        "outputs": ("deliver_plain_docx", "deliver_bilingual_docx",
                    "deliver_terms_xlsx"),
    },
    "complete": {
        "label": "完整交付",
        "description": "同时提供分享、审校与 CAT 工具需要的语言资产。",
        "outputs": ("deliver_plain_docx", "deliver_bilingual_docx", "deliver_pdf",
                    "deliver_terms_xlsx", "deliver_tmx", "deliver_tbx"),
    },
    "custom": {
        "label": "自定义",
        "description": "按你的交付对象和下游工具手动配置。",
        "outputs": (),
    },
}
_DELIVERY_PRESET_KEYS = tuple(_DELIVERY_PRESETS)
_DELIVERY_PRESET_CONFIGS = {
    key: _delivery_config_for_outputs(*value["outputs"])
    for key, value in _DELIVERY_PRESETS.items()
    if key != "custom"
}
_DELIVERY_WIDGET_KEYS = (
    "deliver_plain_docx", "deliver_bilingual_docx", "deliver_pdf",
    "output_annotate", "deliver_terms_xlsx", "deliver_tmx", "deliver_tbx",
    "deliver_jsonl", "output_report", "deliver_evidence", "deliver_cases",
    "deliver_academic_workspace", "deliver_review_report",
)


# These are the strategy names that currently unlock the research-product
# section. Keeping the mapping here makes the Step 02 -> Step 03 dependency
# explicit and gives future research-grade strategies one place to join.
_RESEARCH_STRATEGY_PRESETS = frozenset({"学术增强", "研究与报告", "研究级", "深度研究"})


def _research_outputs_visible(preset_label=None, strategy_config=None):
    preset_label = preset_label or st.session_state.get(
        "translation_preset", "标准")
    config = strategy_config or st.session_state.get("strategy_config") or {}
    return (preset_label in _RESEARCH_STRATEGY_PRESETS
            or bool(config.get("research_outputs_enabled")))


def _delivery_preset_label(key, *, current=None, modified=False):
    meta = _DELIVERY_PRESETS.get(key, _DELIVERY_PRESETS["standard"])
    label = meta["label"]
    if key == "standard":
        label += " · 推荐"
    if current == key and modified and key != "custom":
        label += " · 已修改"
    return label


def _delivery_preset_select_label(key):
    # Keep the selectbox option strings stable across reruns.  Streamlit uses
    # the formatted value to restore the widget; the live "已修改" state is
    # shown in the adjacent helper line instead of changing option labels.
    return _delivery_preset_label(key)


def _apply_delivery_preset(key):
    """Apply a delivery preset without changing the underlying export schema."""
    key = key if key in _DELIVERY_PRESET_KEYS else "standard"
    st.session_state.delivery_preset = key
    st.session_state.delivery_preset_modified = False
    if key == "custom":
        return
    for widget_key in _DELIVERY_WIDGET_KEYS:
        st.session_state.pop(widget_key, None)
    st.session_state.output_config = dict(_DELIVERY_PRESET_CONFIGS[key])


def _on_delivery_preset_change():
    _apply_delivery_preset(st.session_state.get("delivery_preset", "standard"))


def _delivery_output_changed(option, widget_key):
    """Persist a row checkbox and mark the originating preset as modified."""
    _set_output_option(option, widget_key)
    if st.session_state.get("delivery_preset", "standard") != "custom":
        st.session_state.delivery_preset_modified = True


def _delivery_selected_count(config, items):
    return sum(1 for item in items if bool(config.get(item["key"])))


_DELIVERY_TRANSLATION_ITEMS = (
    {
        "key": "deliver_plain_docx", "title": "纯译文", "format": "DOCX",
        "detail": "仅包含目标语言译文。",
        "file_units": (("DOCX", 1),),
    },
    {
        "key": "deliver_bilingual_docx", "title": "双语对照", "format": "DOCX",
        "detail": "原文与译文并列，适合审校。",
        "file_units": (("DOCX", 1),),
    },
    {
        "key": "enable_annotate", "title": "标记术语与翻译难点", "format": "",
        "detail": "标出生僻词、专业术语和疑难句。", "nested": True,
        "file_units": (("DOCX", 1),),
    },
    {
        "key": "deliver_pdf", "title": "纯译文", "format": "PDF",
        "detail": "适合分享、打印与最终交付。",
        "file_units": (("PDF", 1),),
    },
)
_DELIVERY_ASSET_ITEMS = (
    {
        "key": "deliver_terms_xlsx", "title": "术语表", "format": "XLSX",
        "detail": "便于人工查看、编辑和交付。",
        "file_units": (("XLSX", 1),),
    },
    {
        "key": "deliver_tmx", "title": "翻译记忆", "format": "TMX",
        "detail": "可导入 Trados、memoQ 等 CAT 工具。",
        "file_units": (("TMX", 1),),
    },
    {
        "key": "deliver_tbx", "title": "标准术语库", "format": "TBX",
        "detail": "用于术语管理与跨系统交换。",
        "file_units": (("TBX", 1),),
    },
    {
        "key": "deliver_jsonl", "title": "结构化数据", "format": "JSONL",
        "detail": "用于 AI、自动化与二次处理。",
        "file_units": (("JSONL", 1),),
    },
)
_DELIVERY_RESEARCH_ITEMS = (
    {
        "key": "enable_report", "title": "翻译实践报告", "format": "DOCX + MD",
        "detail": "基于项目数据、案例和引用证据生成。",
        "file_units": (("DOCX", 1), ("MD", 1)),
    },
    {
        "key": "deliver_evidence", "title": "翻译过程证据", "format": "JSONL",
        "detail": "保存批次翻译、审校与修订的可追溯证据。",
        "file_units": (("JSONL", 1),),
    },
    {
        "key": "deliver_cases", "title": "案例候选", "format": "JSON",
        "detail": "导出符合资格的真实修订案例。",
        "file_units": (("JSON", 1),),
    },
    {
        "key": "deliver_academic_workspace", "title": "学术写作工作区", "format": "ZIP",
        "detail": "打包论证大纲与写作素材。",
        "file_units": (("ZIP", 1),),
    },
    {
        "key": "deliver_review_report", "title": "审校报告", "format": "MD",
        "detail": "记录审校发现与处理结果。",
        "file_units": (("MD", 1),),
    },
)


def _delivery_items_for_summary(config, *, research_visible=False):
    """Return selected product rows; annotated output depends on bilingual DOCX."""
    items = []
    for item in _DELIVERY_TRANSLATION_ITEMS:
        if item["key"] == "enable_annotate":
            if config.get("deliver_bilingual_docx") and config.get(item["key"]):
                items.append(item)
        elif config.get(item["key"]):
            items.append(item)
    items.extend(item for item in _DELIVERY_ASSET_ITEMS if config.get(item["key"]))
    if research_visible:
        items.extend(item for item in _DELIVERY_RESEARCH_ITEMS
                     if config.get(item["key"]))
    return items


def _delivery_summary(config, *, research_visible=False):
    """Compute user-facing file totals and format counts from export selections."""
    counts = {}
    file_count = 0
    for item in _delivery_items_for_summary(config, research_visible=research_visible):
        for kind, amount in item.get("file_units", ()):
            counts[kind] = counts.get(kind, 0) + amount
            file_count += amount
    return {
        "file_count": file_count,
        "counts": counts,
        "items": _delivery_items_for_summary(
            config, research_visible=research_visible),
    }


def _delivery_summary_html(summary):
    count = int(summary.get("file_count", 0))
    counts = summary.get("counts") or {}
    parts = " · ".join(
        f"{escape(str(kind))} ×{int(amount)}"
        for kind, amount in counts.items())
    if not parts:
        parts = "尚未选择交付文件"
    return (
        '<div class="tp-delivery-summary">'
        f'<strong>将生成 {count} 个文件</strong>'
        f'<span>{parts}</span></div>'
    )


def _render_delivery_item(item, *, group_key, index, config, disabled=False):
    """Render one dense, labeled delivery row inside a group card."""
    option = item["key"]
    widget_key = {
        "enable_annotate": "output_annotate",
        "enable_report": "output_report",
    }.get(option, option)
    row_key = f"delivery_row_{group_key}_{index:02d}"
    if item.get("nested"):
        row_key += "_nested"
    with st.container(key=row_key):
        check_col, copy_col, meta_col = st.columns([0.06, 0.80, 0.14])
        with check_col:
            st.checkbox(
                item["title"], value=bool(config.get(option)), key=widget_key,
                on_change=_delivery_output_changed,
                args=(option, widget_key), label_visibility="collapsed",
                disabled=disabled, help=item["detail"], **_PERSIST_STATE)
        with copy_col:
            st.markdown(
                f'<div class="tp-delivery-row-copy"><strong>{escape(item["title"])}'
                f'</strong><span>{escape(item["detail"])}</span></div>',
                unsafe_allow_html=True)
        with meta_col:
            if item.get("format"):
                st.markdown(
                    f'<div class="tp-delivery-row-meta"><span class="tp-format-badge">'
                    f'{escape(item["format"])}</span></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="tp-delivery-row-meta">&nbsp;</div>',
                            unsafe_allow_html=True)


def _render_delivery_group(title, subtitle, items, config, *, group_key,
                           research_visible=False, after_rows=None):
    """Render a single vertical delivery group and its selected count."""
    count_items = [item for item in items if not item.get("nested")]
    selected = _delivery_selected_count(config, count_items)
    extra_result = None
    with st.container(key=f"delivery_group_{group_key}"):
        st.markdown(
            '<div class="tp-delivery-group-head">'
            f'<div><strong>{escape(title)}</strong><span>{escape(subtitle)}</span></div>'
            f'<b>已选 {selected}</b></div>', unsafe_allow_html=True)
        for index, item in enumerate(items, start=1):
            disabled = (item.get("key") == "enable_annotate"
                        and not config.get("deliver_bilingual_docx"))
            _render_delivery_item(
                item, group_key=group_key, index=index, config=config,
                disabled=disabled)
        if after_rows is not None:
            extra_result = after_rows()
    return extra_result


def _render_delivery_preset_selector():
    """Render the compact delivery-plan selector and its live file summary."""
    current = st.session_state.get("delivery_preset", "standard")
    if current not in _DELIVERY_PRESET_KEYS:
        current = "standard"
        st.session_state.delivery_preset = current
    modified = bool(st.session_state.get("delivery_preset_modified"))
    meta = _DELIVERY_PRESETS[current]
    with st.container(key="delivery_preset_selector"):
        selector_col, helper_col = st.columns([1.08, 1.0])
        with selector_col:
            st.selectbox(
                "交付方案", list(_DELIVERY_PRESET_KEYS),
                format_func=_delivery_preset_select_label,
                key="delivery_preset", on_change=_on_delivery_preset_change,
                **_PERSIST_STATE)
        with helper_col:
            status = " · 已修改" if modified and current != "custom" else ""
            st.markdown(
                f'<div class="tp-delivery-preset-help"><strong>'
                f'{escape(meta["label"])}{escape(status)}</strong>'
                f'<span>{escape(meta["description"])}</span></div>',
                unsafe_allow_html=True)


def _render_delivery_research_details(output_config):
    """Render report inputs only after the research product is selected."""
    if not output_config.get("enable_report"):
        return None
    st.markdown(
        '<div class="tp-output-section-head"><strong>报告设置</strong>'
        '<span>先确定分析框架，再将可追溯证据组织成报告</span></div>',
        unsafe_allow_html=True)
    theory_choice = st.selectbox("理论框架", [
        "自动推荐（建议）", "目的论 (Skopos Theory)",
        "交际翻译与语义翻译 (Newmark)", "功能对等理论 (Nida)",
        "文本类型理论 (Reiss)", "生态翻译学 (Hu Gengshen)",
        "自定义"], key="translation_theory_choice", **_PERSIST_STATE)
    st.caption("根据文本特征、案例证据与可用文献确定；仅在证据充分时使用。")
    if theory_choice == "自定义":
        custom_theory = st.text_input(
            "自定义理论框架", key="custom_translation_theory",
            placeholder="输入理论名称或分析框架")
        translation_theory = custom_theory.strip() or "自定义理论框架"
    elif theory_choice == "自动推荐（建议）":
        translation_theory = "基于文本特征、案例证据与可用文献自动推荐理论框架"
    else:
        translation_theory = theory_choice
    with st.container(key="report_template_inputs"):
        st.markdown(
            '<div class="tp-output-section-head"><strong>报告结构模板</strong>'
            '<span>先固定结构，再将证据分配到章节</span></div>',
            unsafe_allow_html=True)
        _render_report_template_input()
    with st.container(key="literature_inputs"):
        st.markdown(
            '<div class="tp-output-section-head"><strong>参考文献与理论资料</strong>'
            '<span>上传与本次研究或报告相关的专著、论文或资料</span></div>',
            unsafe_allow_html=True)
        st.caption("系统将从文献中提取可核验的理论依据，并仅在证据充分时用于实践报告。")
        _render_literature_inputs()
    return translation_theory


_PRESET_OUTPUTS = {
    # Translation presets no longer decide which files are shown in Step 03;
    # all new tasks start from the same standard delivery recommendation.
    "快速": dict(_DELIVERY_PRESET_CONFIGS["standard"]),
    "标准": dict(_DELIVERY_PRESET_CONFIGS["standard"]),
    "学术增强": dict(_DELIVERY_PRESET_CONFIGS["standard"]),
}

_PRESET_DISPLAY_NAMES = {
    "快速": "快速",
    "标准": "标准",
    "学术增强": "深度研究",
}


def _apply_preset(label):
    for key in ("strategy_auto_term", "strategy_use_tm", "strategy_review",
                "strategy_understanding", "strategy_strict_terms",
                "output_annotate", "output_report"):
        st.session_state.pop(key, None)
    st.session_state.translation_preset = label
    st.session_state.strategy_config = dict(_PRESET_CONFIGS[label])
    _apply_delivery_preset("standard")


def _strategy_is_adjusted(label, config):
    return any(config.get(key) != value
               for key, value in _PRESET_CONFIGS[label].items())


def _strategy_adjustment_count(label, config):
    """Return the number of advanced strategy values changed from the preset."""
    baseline = _PRESET_CONFIGS.get(label, {})
    return sum(config.get(key) != value for key, value in baseline.items())


def _output_is_adjusted(label, config):
    return any(config.get(key) != value
               for key, value in _PRESET_OUTPUTS[label].items())


def _toggle_advanced_strategy():
    st.session_state.strategy_advanced_open = not st.session_state.get(
        "strategy_advanced_open", False)


def _set_strategy_option(option, widget_key):
    config = dict(st.session_state.strategy_config)
    config[option] = bool(st.session_state[widget_key])
    st.session_state.strategy_config = config


def _set_output_option(option, widget_key):
    config = dict(st.session_state.output_config)
    config[option] = bool(st.session_state[widget_key])
    # Annotation is a child of the bilingual DOCX row.  Clearing the parent
    # cannot leave an invisible annotated export enabled in the pipeline.
    if option == "deliver_bilingual_docx" and not config[option]:
        config["enable_annotate"] = False
        st.session_state["output_annotate"] = False
    st.session_state.output_config = config


# ---------------- 智能风格建议（Step 01 Quick Profiling） ----------------

def _apply_style_selection(selection):
    """把选中的 Style Profile 落成 style_rules / style_template。"""
    from transpraxis.style_profile import STYLE_PROFILES, profile_to_rules
    selection = selection or {}
    rules = profile_to_rules(selection)
    custom = (selection.get("custom_rules") or "").strip()
    if custom:
        rules = rules.rstrip("。") + "。" + custom + "。"
    st.session_state.style_rules = rules
    base = selection.get("selected") or "general"
    st.session_state.style_template = STYLE_PROFILES.get(
        base, STYLE_PROFILES["general"])["name"]
    st.session_state.style_selection = selection


def _accept_style_recommendation(source="accepted"):
    rec = st.session_state.get("style_recommendation") or {}
    selection = {
        "selected": rec.get("recommended_style", "general"),
        "source": source,
        "adjustments": {},
    }
    _apply_style_selection(selection)


def _task_profile_signature():
    """Return the inputs that make a cached document profile reusable."""
    task_files = st.session_state.get("task_files") or []
    if not task_files:
        return None
    source = task_files[0]
    raw = source.get("bytes") or b""
    try:
        file_id = core.file_job_id(raw)
    except (TypeError, ValueError):
        file_id = f"{source.get('name') or ''}:{len(raw)}"
    return (str(file_id), str(st.session_state.get("target_lang") or "简体中文"))


def _task_profile_is_ready():
    """Whether Step 1 has a profile for the current file and target language."""
    profile = st.session_state.get("doc_profile")
    recommendation = st.session_state.get("style_recommendation")
    selection = st.session_state.get("style_selection")
    return bool(profile and recommendation and selection
                and st.session_state.get("task_profile_signature")
                == _task_profile_signature())


def _queue_task_profile_retry():
    st.session_state.style_profiling_state = "running"
    st.session_state.pending_profile_step = 2


def _run_quick_profile_with_progress():
    """在脚本运行内执行 Quick Profiling，用 st.status 分步显示进度。

    不放在按钮回调里：回调期间前端收不到任何更新会显得卡死/白屏。
    改为点击后置 running 状态，在本轮运行内逐步渲染状态并执行，
    完成后同一轮直接渲染结果卡片。
    """
    from transpraxis import models as _models
    from transpraxis.style_profile import _fallback_recommendation, quick_profile
    task_files = st.session_state.get("task_files") or []
    if not task_files:
        st.session_state.style_profiling_state = "idle"
        return
    source = task_files[0]
    warnings = []
    doc_profile = None
    style_rec = None
    profiling_state = "done"
    needs_api = False
    error_message = ""
    try:
        with st.status("正在生成智能画像…", expanded=True) as status:
            status.update(label="正在提取文档文本…", state="running")
            paragraphs, extract_warnings = core.extract_document_paragraphs(
                source.get("name", ""), source.get("bytes", b""))
            warnings.extend(extract_warnings)
            provider = st.session_state.get("provider_choice",
                                            next(iter(core.PROVIDERS)))
            api_key = st.session_state.get(f"api_key_{provider}", "")
            model = st.session_state.get(f"model_choice_{provider}", "")
            target_lang = st.session_state.get("target_lang", "简体中文")
            if not api_key or not model:
                status.update(label="需要配置 API Key 才能完成画像",
                              state="error")
                warnings.append("已选择 AI 模型，但 API 凭据未配置，无法自动画像")
                doc_profile = _models.default_document_profile()
                style_rec = _fallback_recommendation()
                needs_api = True
                profiling_state = "error"
            else:
                status.update(label="正在抽取首 / 中 / 尾样本并分析文体…",
                              state="running")
                doc_profile, style_rec, llm_warnings = quick_profile(
                    paragraphs, provider, api_key, model, target_lang)
                warnings.extend(llm_warnings)
                if llm_warnings:
                    error_message = llm_warnings[-1]
                    status.update(label="智能画像未完成", state="error")
                    profiling_state = "error"
                else:
                    status.update(label="智能画像已完成", state="complete")
    except Exception as exc:  # profile failure must be recoverable in the UI
        error_message = str(exc).strip() or "分析服务暂时不可用"
        warnings.append(f"无法完成自动画像：{error_message}")
        profiling_state = "error"

    st.session_state.style_profiling_state = profiling_state
    st.session_state.style_profiling_needs_api = needs_api
    st.session_state.style_profiling_error = error_message
    if doc_profile is not None:
        st.session_state.doc_profile = doc_profile
    if style_rec is not None:
        st.session_state.style_recommendation = style_rec
    st.session_state.style_profile_warnings = warnings
    if profiling_state == "done" and style_rec is not None:
        # Agentic default: the recommendation becomes the effective profile
        # without exposing an internal "accept" workflow to the user.
        _accept_style_recommendation(source="auto")
        st.session_state.task_profile_signature = _task_profile_signature()


def _render_style_adjust_panel():
    """基础风格 radio + 4 个微调滑块 + 高级规则；应用后覆盖系统建议。"""
    from transpraxis.style_profile import STYLE_PROFILES
    names = list(STYLE_PROFILES)
    current = st.session_state.get("style_selection") or {}
    rec = st.session_state.get("style_recommendation") or {}
    base_id = current.get("selected") or rec.get("recommended_style") or "general"
    if base_id not in names:
        base_id = "general"
    st.markdown(
        '<div class="tp-style-adjust-head"><strong>调整风格</strong>'
        '<span>修改后将覆盖系统建议，并记录为 user_override</span></div>',
        unsafe_allow_html=True)
    base = st.radio(
        "基础风格", names, index=names.index(base_id),
        format_func=lambda pid: STYLE_PROFILES[pid]["name"],
        key="style_adjust_base", label_visibility="collapsed",
        **_PERSIST_STATE)
    col_a, col_b = st.columns(2)
    with col_a:
        formality = st.slider("表达正式度", 0, 100, 60, key="adj_formality",
                              **_PERSIST_STATE)
        restructuring = st.slider("句法重构幅度", 0, 100, 40,
                                  key="adj_restructuring",
                                  **_PERSIST_STATE)
    with col_b:
        terminology = st.slider("术语保守程度", 0, 100, 60, key="adj_terminology",
                                **_PERSIST_STATE)
        form_preservation = st.slider("原文形式保留", 0, 100, 70,
                                      key="adj_form_preservation",
                                      **_PERSIST_STATE)
    custom_rules = st.text_area(
        "高级规则（可选）", key="style_adjust_custom",
        placeholder=f"补充风格约束，{_STYLE_RULES_PLACEHOLDER}",
        **_PERSIST_STATE)
    if st.button("应用风格", key="apply_style_adjust"):
        selection = {
            "selected": base,
            "source": "user_override",
            "adjustments": {
                "formality": formality,
                "terminology": terminology,
                "restructuring": restructuring,
                "form_preservation": form_preservation,
            },
            "custom_rules": custom_rules.strip(),
        }
        _apply_style_selection(selection)
        st.session_state.style_adjust_open = False
        st.rerun()


def _render_style_profile_section():
    """Step 01 的智能风格建议卡片：推荐 -> 接受 / 调整 / 查看分析。"""
    from transpraxis.style_profile import STYLE_PROFILES
    state = st.session_state.get("style_profiling_state", "idle")
    rec = st.session_state.get("style_recommendation")
    selection = st.session_state.get("style_selection")
    with st.container(key="style_profile_section"):
        if state == "idle":
            if not st.button("开始智能画像",
                             icon=":material/auto_awesome:",
                             key="run_quick_profile"):
                return
            st.session_state.style_profiling_state = "running"
            state = "running"
        if state == "running":
            _run_quick_profile_with_progress()
            rec = st.session_state.get("style_recommendation")
        if rec is None:
            return
        style_id = (selection or {}).get("selected") or rec.get("recommended_style") \
            or "general"
        meta = STYLE_PROFILES.get(style_id, STYLE_PROFILES["general"])
        confidence = rec.get("confidence", 0.0)
        reasons = rec.get("reasons") or []
        source_text = ""
        if selection:
            source_text = "已接受系统推荐" if selection.get("source") == "accepted" \
                else "已使用用户选择覆盖系统建议"
        st.markdown(
            f'<div class="tp-style-card{" is-selected" if selection else ""}">'
            '<div class="tp-style-card-head">'
            '<span class="material-symbols-rounded" aria-hidden="true">auto_awesome</span>'
            '<strong>智能风格建议</strong>'
            f'<b>{round(confidence * 100)}%</b></div>'
            f'<div class="tp-style-name">{meta["name"]}</div>'
            f'<div class="tp-style-summary">{meta["summary"]}</div>'
            '<div class="tp-style-reasons"><span>检测依据</span><ul>'
            + "".join(f"<li>{escape(r)}</li>" for r in reasons)
            + '</ul></div>'
            + (f'<div class="tp-style-source">{source_text}</div>'
               if source_text else "")
            + '</div>', unsafe_allow_html=True)
        for warn in st.session_state.get("style_profile_warnings", []):
            st.warning(warn)
        if st.session_state.get("style_profiling_needs_api"):
            goto_col, retry_col, adjust_col = st.columns(3)
            with goto_col:
                if st.button("前往配置 API Key", key="goto_api_settings",
                             type="primary", width="stretch"):
                    st.session_state.app_view = "settings"
                    st.rerun()
            with retry_col:
                if st.button("重试", key="retry_quick_profile",
                             width="stretch"):
                    st.session_state.style_profiling_state = "running"
                    st.rerun()
            with adjust_col:
                if st.button("调整", key="open_style_adjust_api",
                             width="stretch"):
                    st.session_state.style_adjust_open = not st.session_state.get(
                        "style_adjust_open", False)
                    st.session_state.style_analysis_open = False
                    st.rerun()
        else:
            accept_col, adjust_col, analyze_col = st.columns(3)
            with accept_col:
                if st.button("接受推荐", key="accept_style_rec",
                             width="stretch"):
                    _accept_style_recommendation()
                    st.session_state.style_adjust_open = False
                    st.session_state.style_analysis_open = False
                    st.rerun()
            with adjust_col:
                if st.button("调整", key="open_style_adjust",
                             width="stretch"):
                    st.session_state.style_adjust_open = not st.session_state.get(
                        "style_adjust_open", False)
                    st.session_state.style_analysis_open = False
                    st.rerun()
            with analyze_col:
                if st.button("查看分析", key="show_style_analysis",
                             width="stretch"):
                    st.session_state.style_analysis_open = not st.session_state.get(
                        "style_analysis_open", False)
                    st.session_state.style_adjust_open = False
                    st.rerun()
        if st.session_state.get("style_analysis_open"):
            with st.expander("文档画像分析", expanded=True):
                doc = st.session_state.get("doc_profile") or {}
                rows = [
                    ("领域", doc.get("domain") or "—"),
                    ("细分领域", doc.get("subdomain") or "—"),
                    ("文本类型", doc.get("genre") or "—"),
                    ("目标读者", doc.get("audience") or "—"),
                    ("语域", doc.get("register") or "—"),
                    ("文体约束", doc.get("style_constraints") or "—"),
                ]
                st.markdown("<br>".join(
                    f"<b>{k}</b>：{escape(str(v))}" for k, v in rows),
                    unsafe_allow_html=True)
                if rec.get("domain"):
                    st.caption("领域标签：" + " · ".join(rec.get("domain", [])))
                st.caption("样本策略：首 / 中 / 尾分布式采样，约 3000–6000 字符")
        if st.session_state.get("style_adjust_open"):
            _render_style_adjust_panel()


def _render_task_profile_setting():
    """Compact Agentic profile setting used by the new Step 1 surface."""
    state = st.session_state.get("style_profiling_state", "idle")
    ready = _task_profile_is_ready()
    with st.container(key="task_setting_profile"):
        st.markdown(
            '<div class="tp-setting-title"><span>智能画像</span>'
            '<span class="tp-setting-badge">推荐</span></div>',
            unsafe_allow_html=True)
        toggle_col, status_col = st.columns([1.08, .92], vertical_alignment="center")
        with toggle_col:
            st.toggle("自动分析", key="task_auto_profile",
                      help="进入下一步时自动分析文档；关闭后不会触发画像调用。",
                      **_PERSIST_STATE)
        with status_col:
            if state == "running":
                st.markdown('<span class="tp-setting-status is-running">正在分析…</span>',
                            unsafe_allow_html=True)
            elif ready:
                st.markdown('<span class="tp-setting-status is-ready">已开启</span>',
                            unsafe_allow_html=True)
            elif state == "error":
                st.markdown('<span class="tp-setting-status is-error">需要处理</span>',
                            unsafe_allow_html=True)
            else:
                st.markdown('<span class="tp-setting-status">待下一步分析</span>',
                            unsafe_allow_html=True)
        if ready:
            st.caption("已复用画像结果 · 进入下一步时不会重复分析")
        elif state == "error":
            st.caption("自动分析未完成。请重试，或关闭自动分析后继续。")
            retry_col, settings_col = st.columns(2)
            with retry_col:
                if st.button("重试", key="retry_task_profile",
                             icon=":material/refresh:", width="stretch"):
                    _queue_task_profile_retry()
                    st.rerun()
            with settings_col:
                if st.button("配置 API Key", key="goto_task_profile_settings",
                             width="stretch"):
                    st.session_state.app_view = "settings"
                    st.rerun()
        else:
            st.caption("自动识别领域、术语、语气与写作风格")


def _render_task_termbase_setting():
    """Compact glossary attachment setting with add / replace / remove actions."""
    term_label = str(st.session_state.get("task_glossary_name") or "未使用")
    has_term_base = term_label not in {"未使用", "未添加"}
    with st.container(key="task_setting_glossary"):
        st.markdown('<div class="tp-setting-title"><span>术语库</span></div>',
                    unsafe_allow_html=True)
        if has_term_base:
            count = st.session_state.get("task_glossary_count")
            count_text = f"{count:,} 条术语" if count is not None else "已添加"
            st.markdown(
                '<div class="tp-setting-value">'
                f'<strong>{escape(term_label)}</strong><span>{escape(count_text)}</span>'
                '</div>', unsafe_allow_html=True)
            action_col, remove_col = st.columns([1, 1])
            with action_col:
                if st.button("更换", key="replace_termbase",
                             icon=":material/swap_horiz:", width="stretch"):
                    st.session_state.show_termbase_picker = True
                    st.rerun()
            with remove_col:
                st.button("移除", key="remove_termbase",
                          icon=":material/close:", width="stretch",
                          on_click=_remove_task_termbase)
        else:
            action_col, state_col = st.columns([1, 1])
            with action_col:
                if st.button("添加", key="add_termbase",
                             icon=":material/add:", width="stretch"):
                    st.session_state.show_termbase_picker = True
                    st.rerun()
            with state_col:
                st.markdown('<span class="tp-setting-status">未使用</span>',
                            unsafe_allow_html=True)
            st.caption("可选 · 保持术语与专名一致")

        if st.session_state.get("show_termbase_picker"):
            with st.container(key="task_termbase_picker"):
                termbase_file = st.file_uploader(
                    "选择术语库文件", type=["xlsx", "csv", "tbx", "tmx"],
                    key="task_termbase_file",
                    help="支持 TBX、TMX、Excel 和 CSV。")
            if termbase_file:
                try:
                    if termbase_file.name.lower().endswith(".tmx"):
                        result = core.import_tmx(termbase_file)
                        st.session_state.task_glossary = []
                        st.session_state.task_glossary_count = result["added"]
                        st.session_state.task_glossary_name = termbase_file.name
                    else:
                        parser = core.parse_termbase if termbase_file.name.lower().endswith(".xlsx") \
                            else core.parse_termbase_csv if termbase_file.name.lower().endswith(".csv") \
                            else core.parse_termbase_tbx
                        st.session_state.task_glossary = parser(termbase_file)
                        st.session_state.task_glossary_count = len(
                            st.session_state.task_glossary)
                        st.session_state.task_glossary_name = termbase_file.name
                    st.session_state.show_termbase_picker = False
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))


def _finish_profile_before_step_two():
    """Run the queued profile and advance only after a usable result exists."""
    if st.session_state.get("style_profiling_state") != "running":
        return
    _run_quick_profile_with_progress()
    st.session_state.pop("pending_profile_step", None)
    if _task_profile_is_ready():
        st.session_state.task_step = 2
        st.rerun()


def _render_task_actions(*, back_step=None, next_step=None, next_label="下一步",
                         next_disabled=False, run=False, delivery_summary=None):
    with st.container(key="task_action_bar"):
        if back_step is None:
            status_col, next_col = st.columns([1, .22])
            back_col = None
        else:
            status_col, back_col, next_col = st.columns([2.6, .8, .8])
        has_inputs = bool(st.session_state.get("task_files"))
        save_text = "✓ 已自动保存" if has_inputs else "更改会自动保存"
        save_class = "tp-autosave is-saved" if has_inputs else "tp-autosave"
        if delivery_summary is not None:
            status_col.markdown(
                f'{_delivery_summary_html(delivery_summary)}'
                f'<span class="{save_class} tp-delivery-autosave">{save_text}</span>',
                unsafe_allow_html=True)
        else:
            status_col.markdown(f'<span class="{save_class}">{save_text}</span>',
                                unsafe_allow_html=True)
        if back_step is not None:
            back_col.button("上一步", icon=":material/arrow_back:", width="stretch",
                            on_click=_go_to_step,
                            args=(back_step,), key=f"back_to_{back_step}")
        if run:
            return next_col.button(next_label, type="primary", width="stretch",
                                   disabled=next_disabled, key="run_task")
        next_col.button(next_label, type="primary", icon=":material/arrow_forward:",
                        width="stretch", on_click=_request_step, args=(next_step,),
                        disabled=next_disabled, key=f"next_to_{next_step}")
    return False


def _remove_task_termbase():
    for key in ("task_glossary", "task_glossary_name", "task_glossary_count",
                "task_termbase_file"):
        st.session_state.pop(key, None)
    st.session_state.show_termbase_picker = False


def _remove_literature_uploads():
    for key in ("literature_uploads", "literature_upload_sources",
                "literature_upload_warnings"):
        st.session_state.pop(key, None)
    st.session_state.literature_uploader_generation = \
        st.session_state.get("literature_uploader_generation", 0) + 1


def _remove_literature_registry():
    for key in ("literature_registry_sources", "literature_registry_name",
                "literature_registry_signature", "literature_registry_warning"):
        st.session_state.pop(key, None)
    st.session_state.literature_registry_generation = \
        st.session_state.get("literature_registry_generation", 0) + 1


def _remove_report_template():
    for key in ("report_template_input", "report_template_error",
                "report_template_signature"):
        st.session_state.pop(key, None)
    st.session_state.report_template_removed = True
    st.session_state.report_template_uploader_generation = \
        st.session_state.get("report_template_uploader_generation", 0) + 1


def _render_report_template_input():
    """Capture the DOCX template separately from reference-material uploads."""
    template = st.session_state.get("report_template_input")
    if template:
        summary = _report_template.contract_summary(template.get("contract"))
        st.markdown(
            f'<div class="tp-attachment"><div><strong>{escape(str(template.get("name") or "模板.docx"))}</strong>'
            f'<span>已解析 · {summary.get("chapter_count", 0)} 个章节 · '
            f'{summary.get("subsection_count", 0)} 个小节</span></div></div>',
            unsafe_allow_html=True)
        st.button("移除报告模板", key="remove_report_template",
                  on_click=_remove_report_template, width="stretch")
        with st.expander("查看模板结构与格式契约", expanded=False):
            st.caption(
                f"模板哈希：{str(summary.get('template_hash') or '')[:16]} · "
                "模板章节、标题层级、前后置部分与 DOCX 样式将作为报告约束。")
            structure = template["contract"].get("document_structure") or {}
            for chapter in structure.get("chapters") or []:
                subs = "、".join(str(x.get("title")) for x in
                                  chapter.get("required_subsections") or [])
                st.markdown(
                    f"- **{chapter.get('section_id')} {chapter.get('title')}**"
                    f"（{chapter.get('role')}）"
                    + (f"：{subs}" if subs else ""))
            if structure.get("front_matter"):
                st.caption("前置部分：" + "、".join(
                    str(x.get("title")) for x in structure["front_matter"]))
            if structure.get("back_matter"):
                st.caption("后置部分：" + "、".join(
                    str(x.get("title")) for x in structure["back_matter"]))
        return

    uploaded = st.file_uploader(
        "报告结构模板（DOCX，可选）",
        type=["docx"],
        key=f"report_template_uploader_"
            f"{st.session_state.get('report_template_uploader_generation', 0)}",
        help="需要研究与报告专用能力时，可用模板固定章节、标题层级、前后置部分和 Word 样式。",
    )
    if uploaded:
        raw = uploaded.getvalue()
        signature = (uploaded.name, len(raw), raw[:32])
        if signature != st.session_state.get("report_template_signature"):
            try:
                contract = _report_template.parse_docx_template(uploaded.name, raw)
                st.session_state.report_template_input = {
                    "name": uploaded.name, "bytes": raw, "contract": contract,
                }
                st.session_state.report_template_error = None
                st.session_state.report_template_signature = signature
                st.session_state.report_template_removed = False
                st.rerun()
            except _report_template.TemplateParseError as exc:
                st.session_state.report_template_error = str(exc)
                st.session_state.report_template_signature = signature
    if st.session_state.get("report_template_error"):
        st.error("报告模板无法使用：" + str(st.session_state.report_template_error))


def _render_literature_inputs():
    """Show user-facing reference uploads; registry JSON stays an advanced escape hatch."""
    uploads = st.session_state.get("literature_uploads") or []
    if uploads:
        names = [escape(str(item.get("name") or "未命名资料")) for item in uploads]
        label = names[0] if len(names) == 1 else f"{names[0]} 等 {len(names)} 个文件"
        st.markdown(
            f'<div class="tp-attachment"><div><strong>{label}</strong>'
            f'<span>已添加参考资料 · 系统将在运行时解析并记录来源位置</span></div></div>',
            unsafe_allow_html=True)
        st.button("移除参考资料", key="remove_literature_uploads",
                  on_click=_remove_literature_uploads, width="stretch")
    else:
        uploaded = st.file_uploader(
            "上传参考资料",
            type=["pdf", "docx", "md", "markdown", "txt", "bib", "ris"],
            accept_multiple_files=True,
            key=f"literature_uploads_"
                f"{st.session_state.get('literature_uploader_generation', 0)}",
            help="支持 PDF、DOCX、Markdown、TXT、BibTeX / RIS（含 Zotero 导出）",
        )
        if uploaded:
            files = [{"name": item.name, "bytes": item.getvalue()} for item in uploaded]
            sources, warnings = _literature_evidence.build_sources_from_uploads(
                files, core.OUTPUT_DIR)
            st.session_state.literature_uploads = files
            st.session_state.literature_upload_sources = sources
            st.session_state.literature_upload_warnings = warnings
            st.rerun()
    for warning in st.session_state.get("literature_upload_warnings") or []:
        st.warning(warning)

    with st.expander("高级选项", expanded=False):
        st.caption("用于恢复已有工作流；普通用户无需准备 JSON。")
        registry_file = st.file_uploader(
            "导入已有文献证据注册表（.json）",
            type=["json"],
            key=f"literature_registry_"
                f"{st.session_state.get('literature_registry_generation', 0)}",
            help="仅支持已有 Literature Evidence Registry JSON",
        )
        if registry_file:
            raw = registry_file.getvalue()
            signature = (registry_file.name, len(raw))
            if signature != st.session_state.get("literature_registry_signature"):
                try:
                    loaded = json.loads(raw.decode("utf-8-sig"))
                    if isinstance(loaded, dict):
                        loaded = loaded.get("sources") or []
                    if not isinstance(loaded, list) \
                            or not all(isinstance(item, dict) for item in loaded):
                        raise ValueError("JSON 中没有可用的 sources 列表")
                    st.session_state.literature_registry_sources = loaded
                    st.session_state.literature_registry_name = registry_file.name
                    st.session_state.literature_registry_warning = None
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    st.session_state.literature_registry_warning = f"注册表无法导入：{exc}"
                st.session_state.literature_registry_signature = signature
        if st.session_state.get("literature_registry_warning"):
            st.warning(st.session_state.literature_registry_warning)
        if st.session_state.get("literature_registry_sources") is not None:
            registry_name = escape(str(
                st.session_state.get("literature_registry_name") or "已有注册表"))
            registry_count = len(st.session_state.get("literature_registry_sources") or [])
            st.caption(f"已导入 {registry_name} · {registry_count} 条来源")
            st.button("移除已有注册表", key="remove_literature_registry",
                      on_click=_remove_literature_registry, width="stretch")


def _remove_source_documents():
    st.session_state.pop("task_files", None)
    st.session_state.pop("source_parse_state", None)
    st.session_state.pop("step_gate_message", None)
    for key in ("style_profiling_state", "doc_profile", "style_recommendation",
                "style_selection", "style_profile_warnings",
                "style_adjust_open", "style_analysis_open",
                "style_profiling_needs_api", "style_profiling_error",
                "task_profile_signature", "pending_profile_step"):
        st.session_state.pop(key, None)
    st.session_state.source_uploader_generation = \
        st.session_state.get("source_uploader_generation", 0) + 1


def _source_file_html(task_files):
    total_size = sum(len(item.get("bytes") or b"") for item in task_files)
    count = len(task_files)
    raw_name = task_files[0].get("name") or "未命名文档"
    first_name = escape(raw_name)
    name = first_name if count == 1 else f"{first_name} 等 {count} 个文件"
    parse_state = st.session_state.get("source_parse_state", "uploaded")
    page_total = sum(int(item.get("pages") or 0) for item in task_files)
    suffix = Path(raw_name).suffix.lower().lstrip(".")
    file_type = {"docx": "Word", "pdf": "PDF"}.get(suffix, suffix.upper() or "文档")
    parsed_detail = f"{file_type} · {_format_size(total_size)}" \
        f'{f" · {page_total:,} 页" if page_total else ""}'
    meta = {
        "uploaded": (parsed_detail, "已上传，等待解析"),
        "parsing": (parsed_detail, "正在解析…"),
        "parsed": (parsed_detail, ""),
        "error": (parsed_detail, "解析失败"),
    }
    detail, status = meta.get(parse_state, meta["uploaded"])
    icon = "progress_activity" if parse_state == "parsing" else "description"
    icon_class = "material-symbols-rounded is-loading" if parse_state == "parsing" \
        else "material-symbols-rounded"
    ready_badge = '<span class="tp-source-ready">已就绪</span>' \
        if parse_state == "parsed" else ""
    status_html = (f' · <b class="tp-source-file-status is-{parse_state}">'
                   f'{status}</b>') if status else ""
    return (
        '<div class="tp-source-file">'
        f'<span class="{icon_class}" aria-hidden="true">{icon}</span>'
        f'<div class="tp-source-file-copy"><strong title="{escape(raw_name, quote=True)}">'
        f'{name}</strong>'
        f'<span>{detail}{status_html}</span></div>{ready_badge}</div>'
    )


def _preset_card_html(label):
    display_label = _PRESET_DISPLAY_NAMES.get(label, label)
    cards = {
        "快速": {
            "expectation": "适合快速产出可读初稿",
            "workflow": "翻译 → 基础检查",
            "metrics": (("速度", "高"), ("成本", "低"), ("审校深度", "基础")),
        },
        "标准": {
            "expectation": "适合大多数正式翻译任务",
            "workflow": "全文理解 → 术语增强 → 翻译 → 基础检查",
            "metrics": (("速度", "中"), ("成本", "中"), ("审校深度", "基础")),
        },
        "学术增强": {
            "expectation": "适合论文、报告及需要证据追踪的材料",
            "workflow": "全文理解 → 术语治理 → 翻译 → 独立审校 → 研究证据",
            "metrics": (("速度", "低"), ("成本", "高"), ("审校深度", "深度")),
        },
    }
    card = cards[label]
    badge = '<span class="tp-preset-badge">推荐</span>' if label == "标准" else ""
    icon = "radio_button_checked" if label == st.session_state.get(
        "translation_preset", "标准") else "radio_button_unchecked"
    metric_html = "".join(
        f'<span class="tp-preset-metric"><b>{escape(dimension)}</b>'
        f'<span class="tp-preset-metric-value">{escape(level)}</span></span>'
        for dimension, level in card["metrics"])
    return (
        '<div class="tp-preset-card">'
        '<div class="tp-preset-head">'
        f'<span class="material-symbols-rounded" aria-hidden="true">{icon}</span>'
        f'<strong>{display_label}</strong>{badge}</div>'
        f'<div class="tp-preset-expectation"><strong>{escape(card["expectation"])}'
        '</strong></div>'
        '<div class="tp-preset-flow-wrap">'
        '<span class="tp-preset-flow-label">包含</span>'
        f'<p class="tp-preset-flow">{escape(card["workflow"])}</p></div>'
        f'<div class="tp-preset-metrics">{metric_html}</div></div>'
    )


def _render_strategy_toggle(label, description, option, key, config):
    with st.container(key=f"{key}_row"):
        copy_col, switch_col = st.columns([9, 1], vertical_alignment="center")
        copy_col.markdown(
            f'<div class="tp-setting-copy"><strong>{label}</strong>'
            f'<span>{description}</span></div>', unsafe_allow_html=True)
        switch_col.toggle(label, value=config[option], key=key,
                          label_visibility="collapsed",
                          on_change=_set_strategy_option, args=(option, key),
                          help=description, **_PERSIST_STATE)


def _format_size(size):
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{max(1, round(size / 1024))} KB"


def _summary_html(filename, target_lang, preset_label, glossary_name,
                  strategy_config, output_config, style_template,
                  style_source="", delivery_preset=None):
    filename = escape(str(filename))
    target_lang = escape(str(target_lang))
    preset_key = str(preset_label)
    preset_label = escape(_PRESET_DISPLAY_NAMES.get(preset_key, preset_key))
    glossary_name = escape(str(glossary_name))
    workflow = []
    if strategy_config.get("enable_understanding"):
        workflow.append("全文理解")
    if strategy_config["strict_terminology_governance"]:
        workflow.append("术语治理")
    elif strategy_config["auto_term"]:
        workflow.append("术语增强")
    workflow.extend(["翻译", "基础检查"])
    if strategy_config["enable_review"]:
        workflow.append("独立审校")
    if output_config["enable_annotate"]:
        workflow.append("重点标注")
    if output_config["enable_report"]:
        workflow.extend(["研究证据", "翻译实践报告（专用）"])
    mode_label = preset_label
    if _strategy_is_adjusted(preset_key, strategy_config) \
            or _output_is_adjusted(preset_key, output_config):
        mode_label += " · 已调整"
    delivery_key = delivery_preset or st.session_state.get(
        "delivery_preset", "standard")
    delivery_label = _delivery_preset_label(
        delivery_key,
        current=delivery_key,
        modified=bool(st.session_state.get("delivery_preset_modified")),
    )
    delivery_summary = _delivery_summary(
        output_config,
        research_visible=_research_outputs_visible(preset_key, strategy_config),
    )
    artifacts = []
    if output_config.get("deliver_plain_docx"):
        artifacts.append(("description", "纯译文", "仅含译文文本", "DOCX"))
    if output_config.get("deliver_bilingual_docx"):
        artifacts.append(("description", "双语对照", "原文与译文并列，适合审校", "DOCX"))
    if output_config.get("deliver_pdf"):
        artifacts.append(("picture_as_pdf", "纯译文", "适合分享、打印与最终交付", "PDF"))
    if output_config.get("deliver_terms_xlsx"):
        artifacts.append(("table", "术语表", "自动抽取与锁定术语", "XLSX"))
    for key, name, kind in (("deliver_tbx", "标准术语库", "TBX"),
                            ("deliver_tmx", "翻译记忆", "TMX"),
                            ("deliver_jsonl", "结构化数据", "JSONL")):
        if output_config.get(key):
            artifacts.append(("code", name, "语言资产导出", kind))
    if output_config["enable_annotate"]:
        artifacts.append(("ink_highlighter", "双语对照 · 标注增强版",
                          "标出生僻词、专业术语和翻译难点句", "DOCX"))
    if output_config["enable_report"]:
        artifacts.append(("article", "翻译实践报告（专用）",
                          "基于翻译过程证据生成", "DOCX / MD"))
    if output_config.get("deliver_evidence"):
        artifacts.append(("data_object", "翻译过程证据",
                          "批次翻译、审校与修订的可追溯记录", "JSONL"))
    if output_config.get("deliver_cases"):
        artifacts.append(("fact_check", "案例候选",
                          "符合资格的真实修订案例", "JSON"))
    if output_config.get("deliver_academic_workspace"):
        artifacts.append(("folder_zip", "学术写作工作区",
                          "论证大纲与写作素材打包", "ZIP"))
    if output_config.get("deliver_review_report"):
        artifacts.append(("fact_check", "审校报告",
                          "审校发现与处理记录", "MD"))
    style_value = escape(str(
        style_template + (f"（{style_source}）" if style_source else "")))
    artifact_rows = "".join(
        '<div class="tp-artifact-row">'
        f'<span class="material-symbols-rounded" aria-hidden="true">{icon}</span>'
        f'<div><strong>{name}</strong><span>{detail}</span></div><b>{kind}</b></div>'
        for icon, name, detail, kind in artifacts)
    return (
        '<div class="tp-confirm-stack">'
        '<section class="tp-confirm-card"><div class="tp-confirm-head">'
        '<span class="material-symbols-rounded" aria-hidden="true">tune</span>'
        '<strong>任务配置</strong></div><div class="tp-summary-grid">'
        f'<div class="tp-summary-item"><span>原文</span><strong>{filename}</strong></div>'
        f'<div class="tp-summary-item"><span>目标语言</span><strong>{target_lang}</strong></div>'
        f'<div class="tp-summary-item"><span>翻译模式</span><strong>{mode_label}</strong></div>'
        f'<div class="tp-summary-item"><span>交付方案</span><strong>{escape(delivery_label)}</strong></div>'
        f'<div class="tp-summary-item"><span>译文风格</span><strong>{style_value}</strong></div>'
        f'<div class="tp-summary-item"><span>术语库</span><strong>{glossary_name}</strong></div>'
        '<div class="tp-summary-item is-wide"><span>工作流</span>'
        f'<strong>{" → ".join(workflow)}</strong></div></div></section>'
        '<section class="tp-confirm-card"><div class="tp-confirm-head">'
        '<span class="material-symbols-rounded" aria-hidden="true">inventory_2</span>'
        f'<strong>将生成 {delivery_summary["file_count"]} 个文件</strong></div>'
        '<div class="tp-artifact-list">'
        f'{artifact_rows}</div></section></div>')


def _runtime_html(provider, model, connection_status, can_start):
    provider = escape(str(provider))
    model = escape(str(model or "未配置"))
    connection = {
        "connected": ("已连接", "is-success"),
        "error": ("连接失败", "is-error"),
        "credentials_missing": ("API 凭据未配置", "is-warning"),
        "not_selected": ("尚未选择模型", "is-neutral"),
        "unverified": ("未验证", "is-neutral"),
    }.get(connection_status, ("未验证", "is-neutral"))
    if not can_start:
        readiness = ("需要配置", "is-warning")
    elif connection_status == "connected":
        readiness = ("可启动", "is-success")
    elif connection_status == "error":
        readiness = ("需检查连接", "is-error")
    else:
        readiness = ("待验证", "is-warning")
    return (
        '<section class="tp-confirm-card tp-runtime-card">'
        '<div class="tp-confirm-head"><span class="material-symbols-rounded" '
        'aria-hidden="true">memory</span><strong>运行环境</strong></div>'
        '<div class="tp-runtime-grid">'
        f'<div><span>AI 引擎</span><strong>{provider}</strong></div>'
        f'<div><span>模型</span><strong>{model}</strong></div>'
        f'<div><span>连接状态</span><strong class="tp-status {connection[1]}">'
        f'{connection[0]}</strong></div>'
        f'<div><span>启动状态</span><strong class="tp-status {readiness[1]}">'
        f'{readiness[0]}</strong></div></div></section>')


def _render_profile_editor(job_id, state, box=None):
    box = box or st
    profile = state.get("document_profile") or {}
    with box.expander("文档画像（AI 生成，可修改后保存）", expanded=False):
        c1, c2, c3 = box.columns(3)
        domain = c1.text_input("领域 domain", value=profile.get("domain") or "",
                               key=f"pf_d_{job_id}")
        subdomain = c2.text_input("细分领域 subdomain",
                                  value=profile.get("subdomain") or "",
                                  key=f"pf_sd_{job_id}")
        genre = c3.text_input("文本类型 genre", value=profile.get("genre") or "",
                              key=f"pf_g_{job_id}")
        audience = c1.text_input("读者 audience", value=profile.get("audience") or "",
                                 key=f"pf_a_{job_id}")
        register = c2.text_input("语域 register", value=profile.get("register") or "",
                                 key=f"pf_r_{job_id}")
        confidence = c3.slider("置信度", 0.0, 1.0,
                               float(profile.get("confidence") or 0.0),
                               key=f"pf_c_{job_id}")
        style_constraints = box.text_area(
            "风格约束 style_constraints",
            value=profile.get("style_constraints") or "", key=f"pf_sc_{job_id}")
        if box.button("保存文档画像", key=f"pf_save_{job_id}"):
            core.save_document_profile(job_id, {
                "domain": domain, "subdomain": subdomain, "genre": genre,
                "audience": audience, "register": register,
                "style_constraints": style_constraints, "confidence": confidence,
                "sections": profile.get("sections") or [],
            })
            st.rerun()
        secs = profile.get("sections") or []
        if secs:
            box.caption("分节：" + "；".join(
                f"{x.get('section_id')}（段落 {x.get('start_segment')}-{x.get('end_segment')}"
                f"，{x.get('topic') or x.get('domain') or '?'}）" for x in secs))
        elif not state.get("profile_done"):
            box.caption("画像未生成（AI 失败或已跳过），可在此人工填写后保存。")

def _asset_prefix(state, snapshot_current=False):
    """Only a currently matching frozen snapshot may use the final prefix."""
    return "final_" if snapshot_current and state.get("delivery_status") == "final" else "draft_"


def _render_snapshot_versions(job_id, state, location):
    snapshots = core.list_delivery_snapshots(job_id)
    if not snapshots:
        return
    filename = Path(str(state.get("filename") or "document")).stem or "document"
    with st.expander("最终交付版本", expanded=False):
        st.caption("历史版本来自已冻结文件，不会随当前工作版本变化。")
        for snapshot in reversed(snapshots):
            version = snapshot["snapshot_version"]
            approval = snapshot.get("approval") or {}
            st.markdown(f"**最终交付版本 v{version}** · 已冻结")
            st.caption(
                f"确认时间：{approval.get('timestamp') or snapshot.get('created_at') or '—'} · "
                f"交付说明：{approval.get('note') or '—'} · "
                f"资产：{len(snapshot.get('assets') or [])} 项")
            archive = core.delivery_snapshot_archive(job_id, version)
            if archive is not None:
                st.download_button(
                    f"下载最终交付版本 v{version}", archive,
                    file_name=f"final_delivery_v{version}_{filename}.zip",
                    mime="application/zip",
                    key=f"snapshot_download_{location}_{job_id}_v{version}",
                    width="stretch")


def _review_sort_key(context):
    return (
        _delivery.SEVERITY_ORDER.get(context.get("severity"), 99),
        context.get("segment_index") if context.get("segment_index") is not None else 10**9,
        context.get("finding_id") or "",
    )


def _review_phase_label(phase):
    return {
        "formal_review": "正式审校",
        "shadow_repair": "自动修订复核",
        "suggested_shadow_review": "建议译文复核",
    }.get(phase, phase or "审校记录")


def _render_finding_evidence(context):
    refs = context.get("evidence_refs") or []
    traces = context.get("review_evidence") or []
    if refs:
        st.caption("该问题引用的证据：" + "、".join(refs))
    if not traces:
        st.caption("暂无额外证据请求；以上原文与译文来自任务本地记录。")
        return
    with st.expander("审校 / 证据详情", expanded=False):
        for trace in traces[-3:]:
            status = (trace.get("completion_receipt") or {}).get("status") or "-"
            evidence_ids = "、".join(trace.get("evidence_ids") or []) or "无"
            st.caption(
                f"{_review_phase_label(trace.get('phase'))} · "
                f"结论 {trace.get('decision') or '-'} · 状态 {status} · "
                f"证据 {evidence_ids}")
            for request in (trace.get("requests") or [])[:4]:
                tool = request.get("tool") or "evidence"
                evidence_id = request.get("evidence_id") or "-"
                arguments = request.get("arguments") or {}
                st.caption(f"{evidence_id} · {tool} · {arguments}")


def _format_saved_at(value):
    if not value:
        return "尚无保存记录"
    return str(value).replace("T", " ")[:19]


def _render_recovery_panel(job_id, state):
    summary = core.recovery_summary(job_id, state)
    status = core.task_status_label(state, job_id)
    with st.container(border=True):
        st.subheader("任务状态与自动保存")
        c1, c2, c3 = st.columns(3)
        c1.metric("当前状态", status)
        batch_count = (f"{summary['completed_batch_count']}/{summary['total_batches']}"
                       if summary["total_batches"] else "—")
        c2.metric("已完成处理批次", batch_count)
        c3.metric("自动保存", "已开启")
        st.caption(f"最近保存进度：{_format_saved_at(summary['last_saved_at'])} · "
                   f"最近完成阶段：{summary['last_completed_stage']}")
        current = summary.get("current_batch")
        if current:
            st.warning(
                f"第 {current['number']} 个处理批次中断：已保存本批次 "
                f"{current['completed_segments']}/{current['segment_count']} 段。"
                f"继续时会重新执行本批次剩余内容（最多重新执行 "
                f"{current['regenerate_segments']} 段），此前已保存的批次不会重做。")
        if summary["recovered_tm_entries"]:
            st.info(f"已从上次中断中恢复 {summary['recovered_tm_entries']} 条翻译记忆同步记录。")
        if summary["can_resume"] and st.button(
                "继续处理", type="primary", key=f"resume_workspace_{job_id}",
                width="stretch"):
            st.session_state.update(
                active_job_id=job_id, app_view="workspace", workspace_mode=True)
            _resume_job(job_id, state)
            st.rerun()


def _context_status_label(status):
    return {
        "model": "模型生成",
        "deterministic_fallback": "临时摘要",
        "pending": "生成中",
        "unavailable": "不可用",
    }.get(str(status or ""), "未记录")


def _target_context_level_label(level):
    return {
        "human_accepted": "人工确认",
        "reviewed": "独立审校",
        "tm_approved": "翻译记忆",
        "generated": "自动译文（未确认）",
    }.get(level, "未标注")


def _render_context_surface(job_id, state):
    st.header("文档上下文")
    st.caption("查看系统对全文、当前内容单元和前文译文连续性的理解。")
    artifacts = core.load_context_artifacts(job_id, state)
    units = artifacts["semantic_units"]
    digests = artifacts["section_digests"]
    synopsis = artifacts["document_synopsis"]
    recovery = core.recovery_summary(job_id, state)
    pairs = state.get("pairs") or []
    current_batch = recovery.get("current_batch")
    if current_batch:
        current_index = current_batch.get("start_segment", len(pairs)) \
            + current_batch.get("completed_segments", 0)
        st.info(
            f"当前处理批次：第 {current_batch['number']} 批 · "
            f"本批已保存 {current_batch['completed_segments']}/{current_batch['segment_count']} 段。")
    else:
        current_index = len(pairs)
        if state.get("p2_done"):
            st.success("翻译批次已完成；以下显示最近使用的上下文。")
        else:
            st.caption("翻译尚未形成批次记录；以下可查看已经生成的全文理解。")
    current_index = max(0, min(current_index, len(state.get("paras") or pairs)))

    synopsis_status = _context_status_label(synopsis.get("status"))
    accepted_context = _context.select_target_context(
        pairs, current_index, limit=4)
    metric_cols = st.columns(3)
    metric_cols[0].metric("内容单元", len(units))
    metric_cols[1].metric("章节摘要", len(digests))
    metric_cols[2].metric("前文连续性", f"{len(accepted_context)} 条")

    with st.container(border=True):
        st.subheader("全文概要")
        if synopsis.get("summary"):
            st.write(synopsis["summary"])
            if synopsis.get("document_arc"):
                st.markdown(f"**全文发展/论证**：{synopsis['document_arc']}")
            for label, key in (("主题", "themes"), ("关键实体", "entities"),
                               ("关键概念", "terms"), ("翻译连续性提示", "translation_notes")):
                values = synopsis.get(key) or []
                if values:
                    st.caption(f"{label}：" + "、".join(values))
            st.caption(f"概要状态：{synopsis_status}")
        else:
            st.info(
                "当前任务没有可用的全文概要。可能是快速模式运行，或全文理解尚未完成；"
                "这不会阻止翻译继续。")

    if units:
        digest_by_unit = {str(item.get("unit_id")): item for item in digests
                          if isinstance(item, dict)}
        def unit_label(index):
            unit = units[index]
            label = unit.get("label") or f"内容单元 {index + 1}"
            return f"{label} · 第 {unit.get('start_segment', 0) + 1}-{unit.get('end_segment', 0) + 1} 段"

        default_unit = 0
        for index, unit in enumerate(units):
            if unit.get("start_segment", 0) <= current_index <= unit.get("end_segment", -1):
                default_unit = index
                break
            if unit.get("start_segment", 0) <= max(0, current_index - 1) \
                    <= unit.get("end_segment", -1):
                default_unit = index
        selected_unit = st.selectbox(
            "当前章节/内容单元", range(len(units)), index=default_unit,
            format_func=unit_label, key=f"context_unit_{job_id}")
        unit = units[selected_unit]
        digest = digest_by_unit.get(str(unit.get("unit_id")))
        with st.container(border=True):
            st.subheader("章节摘要")
            st.caption(unit_label(selected_unit))
            if digest and digest.get("summary"):
                st.write(digest["summary"])
                for label, key in (("关键实体", "key_entities"), ("关键概念", "key_terms"),
                                   ("待确认线索", "open_threads"),
                                   ("翻译提示", "translation_notes")):
                    values = digest.get(key) or []
                    if values:
                        st.caption(f"{label}：" + "、".join(values))
            else:
                st.info("该内容单元暂无章节摘要。")
    elif not synopsis.get("summary"):
        st.info("当前任务没有可展示的内容单元或章节摘要。")

    with st.container(border=True):
        st.subheader("上下文连续性")
        if accepted_context:
            st.caption("最近批次/最近译文参考的前文内容如下；标签表示译文的确认程度。")
            for item in accepted_context:
                with st.expander(
                        f"第 {item['segment_index'] + 1} 段 · "
                        f"{_target_context_level_label(item['level'])}", expanded=False):
                    st.markdown("**前文原文**")
                    st.code(item["source"] or "（无原文记录）")
                    st.markdown("**前文译文**")
                    st.code(item["target"])
        else:
            st.info("当前没有可用的前文译文连续性记录。")

        packet_log = state.get("context_packet_log") or []
        if packet_log:
            latest = packet_log[-1]
            previous_count = len(latest.get("previous_target_segments") or [])
            st.caption(
                f"最近一次处理参考了全文概要、当前章节摘要、前文原文，"
                f"以及 {previous_count} 条前文译文连续性记录。")
        else:
            st.caption("当前任务尚无已保存的批次上下文参考记录。")

    warnings = artifacts.get("warnings") or []
    if warnings:
        with st.expander("上下文生成提示", expanded=False):
            for warning in warnings:
                st.warning(warning)
    if state.get("context_packet_log"):
        with st.expander("高级诊断", expanded=False):
            st.caption("仅供排查使用；正常工作不需要查看内部记录。")
            st.json(state["context_packet_log"][-5:])


# ================= Language Assets Workspace（术语与翻译记忆）=================
# 信息架构：一个页面 = 三个一级 Tab（术语库 / 翻译记忆 / 待审核）+ 右侧 Inspector。
#
# 事实边界（不要越过；UI 不得伪造后端没有的能力）：
#   - 后端没有「全局术语库」：长期保存的跨任务知识走项目记忆（写入项目记录，
#     任务术语表仍保留其来源与冻结版本），所以「全局术语库」始终是 disabled + TODO，
#     不是假按钮；
#   - 翻译记忆条目只有 target / reviewed / updated_at：不显示来源文档、使用次数、
#     fuzzy match 百分比——后端没有这些字段；
#   - 作用域还包括项目记忆；任务侧仍支持 global / document / section:<id> /
#     segment:<id> 等历史值；
#   - 候选的「出现次数」优先用 occurrences（真实段落命中），缺失时退回
#     observed_segments 并明确标注「出现次数未知」。
#
# 交互模型：Tab 由 segmented control 承担，浏览器页面从不重新加载；Streamlit
# 没有客户端路由，因此 URL 状态用 query param（?tab=terms|tm|review）保持。
# 审核动作采用两阶段认知模型：一级「接受 / 拒绝」，接受后再选「保存到哪里」，
# 不再把两个决策揉成三个并列按钮。

# 过滤器选项一律从 language_assets 现取，不在模块层缓存：Streamlit 热重载时
# 被 import 的模块不一定重新执行，缓存住旧标签会让下拉框显示过期文案。
def _la_scope_options():
    return list(_language_assets.SCOPE_FILTERS)


def _la_confidence_options():
    return list(_language_assets.CONFIDENCE_FILTERS)


def _la_kind_options():
    return list(_language_assets.KIND_FILTERS)


_LA_PAGE_SIZE = 40
_LA_GLOBAL_TERMBASE_TODO = (
    "当前版本没有独立的全局术语库存储（后端尚未提供）。长期保存位置只有项目术语，"
    "术语会写进任务的术语表并生成新的术语版本。")
_LA_QUICK_ACCEPT_NOTE = "Quick Accept 默认保存到：项目术语库（当前唯一可用的长期保存位置）。"
_LA_TM_SOURCE_TODO = (
    "暂不可用：翻译记忆记录只有 target / reviewed / updated_at 三个字段，"
    "没有来源文档信息，因此无法按来源筛选。")
_LA_TM_LANGPAIR_TODO = (
    "暂不可用：翻译记忆没有持久化语言对字段（语言方向只存在于任务的 "
    "pipeline_config.target_lang），因此无法按语言对筛选。")


def _la_flash(message, tone="success"):
    st.session_state["library_flash"] = {"message": str(message or ""), "tone": tone}


def _la_render_flash():
    flash = st.session_state.pop("library_flash", None)
    if not isinstance(flash, dict) or not flash.get("message"):
        return
    {"error": st.error, "warning": st.warning, "info": st.info,
     "success": st.success}.get(flash.get("tone"), st.success)(flash["message"])


def _la_select(row_id):
    st.session_state["library_selected_row"] = str(row_id) if row_id else None


def _la_selected_row_id():
    value = st.session_state.get("library_selected_row")
    return str(value) if value else ""


def _la_sync_tab():
    """一级 Tab 与 URL 同步：?tab=terms|tm|review。

    URL 只在**外部改变**时优先（用户手改地址或打开分享链接）。我们自己写回去的
    值记在 `la_published_tab` 里，否则 URL 会反过来把用户在页内的切换覆盖掉。
    """
    valid = _language_assets.VALID_TABS
    try:
        requested = str(st.query_params.get("tab") or "").strip()
    except Exception:
        requested = ""
    published = str(st.session_state.get("la_published_tab") or "")
    if requested in valid and requested != published:
        st.session_state["library_tab"] = requested
    if st.session_state.get("library_tab") not in valid:
        st.session_state["library_tab"] = "terms"
    return str(st.session_state["library_tab"])


def _la_publish_query(tab):
    """把当前 Tab / 选中项写回 URL；只在变化时写。"""
    try:
        if str(st.query_params.get("view") or "") != "library":
            st.query_params["view"] = "library"
        if "project" in st.query_params:
            del st.query_params["project"]
        if str(st.query_params.get("tab") or "") != tab:
            st.query_params["tab"] = tab
        st.session_state["la_published_tab"] = tab
        selected = _la_selected_row_id()
        current = str(st.query_params.get("item") or "")
        if selected and current != selected:
            st.query_params["item"] = selected
        elif not selected and current:
            del st.query_params["item"]
    except Exception:
        pass


# ---- 多选（批量审核）----

def _la_selection():
    selection = st.session_state.get("la_selection")
    if not isinstance(selection, dict):
        selection = {}
        st.session_state["la_selection"] = selection
    return selection


def _la_generation():
    return int(st.session_state.get("la_sel_generation") or 0)


def _la_row_slug(row_id):
    """行键的 CSS 安全片段：row_id 含 "::" 与空格，不能直接进 key/class。"""
    return _la_key_fragment(row_id)


def _la_checkbox_key(row_id):
    return f"la_sel_{_la_generation()}_{_la_row_slug(row_id)}"


def _la_toggle_selection(row_id):
    selection = st.session_state.get("la_selection")
    if not isinstance(selection, dict):
        selection = {}
    if st.session_state.get(_la_checkbox_key(row_id)):
        selection[row_id] = True
    else:
        selection.pop(row_id, None)
    st.session_state["la_selection"] = selection


def _la_clear_selection():
    st.session_state["la_selection"] = {}
    st.session_state["la_sel_generation"] = _la_generation() + 1


def _la_forget_row(row_id):
    selection = st.session_state.get("la_selection")
    if isinstance(selection, dict):
        selection.pop(row_id, None)
        st.session_state["la_selection"] = selection
    if st.session_state.get("library_selected_row") == row_id:
        _la_select(None)


# ---- 决策执行 ----

def _la_jump_to_segment(job_id, index):
    """跳到该任务工作台的指定段落。

    候选的 ``occurrences`` 与 ``state["pairs"]`` 是同一套下标（已交叉验证：
    候选 first_observed_segment=4 对应 pairs[4] 的原文段落）。工作台用
    ``st.session_state["selected_segment_id"]`` 表示"当前选中的段落"，
    这里直接复用工作台自己的 ``_translation_segment_id`` 推导，保证两边一致。
    所以这是一条真实可用的深链，不是猜测出来的锚点。
    """
    state = None
    message = ""
    try:
        state = core.load_job_state(job_id)
    except Exception as exc:
        message = f"无法打开任务：{exc}"
    if not message and not state:
        message = "任务状态已不存在，无法定位。"
    pairs = (state or {}).get("pairs") or []
    if not message and (isinstance(index, bool) or not isinstance(index, int)
                        or index < 0 or index >= len(pairs)):
        # 任务被重新切分后旧下标会失效，此时宁可说清楚，也不要跳到错的段落。
        message = "该段落已不在当前任务里（任务可能被重新切分）。"
    if message:
        _la_flash(message, "error")
        st.rerun()
        return
    st.session_state["selected_segment_id"] = _translation_segment_id(
        job_id, index, pairs[index])
    # 只选中还不够：工作台要靠这个 scroll intent 把该段滚到视口中央
    # （`_render_scroll_trigger` 找 [data-segment="{index}"] 锚点）。
    # 取一次就清空，所以不能改成持久状态。
    st.session_state[_NAV_PENDING_SCROLL] = index
    _open_job(job_id, state, destination="translation")
    st.rerun()


def _la_apply_decision(row, decision):
    try:
        state, ok, message = core.review_knowledge_candidate(
            row["job_id"], row["candidate_id"], decision)
    except Exception as exc:
        return False, f"处理失败：{exc}"
    if ok and decision == "project_term":
        # `review_knowledge_candidate` 保持既有契约：先把人工确认写回任务术语表。
        # Language Assets 的「保存到项目术语库」还要走现有 Memory gate，才能真正
        # 跨任务复用；两步都成功后才向用户报告完整的项目保存结果。
        try:
            project = core.promote_job_to_project(
                row["job_id"], actor="用户", state=state)
        except Exception as exc:
            return False, f"候选已接受并写入任务术语表，但提升到项目记忆失败：{exc}"
        if project is None:
            return False, "候选已接受并写入任务术语表，但项目记忆不可用"
        message = f"{message}；已提升到项目「{project.get('name') or '未命名项目'}」"
    return bool(ok), str(message or "")


def _la_apply_bulk(rows, decision, action_label):
    done, failed = 0, []
    for row in rows:
        ok, message = _la_apply_decision(row, decision)
        if ok:
            done += 1
        else:
            failed.append(f"{row['source']}（{message}）")
    if not done and not failed:
        return "没有可处理的候选。", "warning"
    parts = []
    if done:
        parts.append(f"{action_label} {done} 条")
    if failed:
        parts.append(f"{len(failed)} 条未处理：{failed[0]}")
    tone = "success" if done and not failed else ("warning" if done else "error")
    return "；".join(parts) + "。", tone


def _la_execute_pending(candidate_rows):
    """执行上一次交互排队的审核动作（在列表与 Inspector 都渲染完之后）。

    两段式：第一次 rerun 只把目标行锁住（按钮 disabled、显示 pending），
    第二次 rerun 才真正调用后端。这样待处理状态可见，且只锁定相关行。
    """
    pending = st.session_state.get("la_pending")
    if isinstance(pending, dict):
        st.session_state["la_pending"] = None
        row = next((item for item in candidate_rows
                    if item["row_id"] == str(pending.get("row_id") or "")), None)
        if row is not None:
            ok, message = _la_apply_decision(row, str(pending.get("action") or ""))
            _la_flash(message, "success" if ok else "error")
            if ok:
                _la_forget_row(row["row_id"])
        st.rerun()
    bulk = st.session_state.get("la_pending_bulk")
    if isinstance(bulk, dict):
        st.session_state["la_pending_bulk"] = None
        wanted = {str(item) for item in bulk.get("ids") or []}
        targets = [item for item in candidate_rows if item["row_id"] in wanted]
        message, tone = _la_apply_bulk(targets, str(bulk.get("action") or ""),
                                       str(bulk.get("label") or ""))
        _la_flash(message, tone)
        _la_clear_selection()
        st.rerun()


# ---- 小部件 ----

def _la_option_value(options, label, default=""):
    for value, text in options:
        if text == label:
            return value
    return default


def _la_option_labels(options):
    return [text for _, text in options]


def _la_guard_option(key, options):
    """清掉 session_state 里已经不在 options 中的旧值。

    热重载后旧标签会残留，selectbox 会继续显示过期文案（并可能被截断），
    这里在渲染前先丢弃，保证下拉框永远和当前选项列表一致。
    """
    current = st.session_state.get(key)
    if current is not None and current not in options:
        del st.session_state[key]


def _la_status_chip(status):
    label = _language_assets.status_label(status)
    tone = {"locked": "is-ok", "provisional": "is-warn",
            "rejected": "is-danger"}.get(str(status or "").strip().casefold(), "")
    return f'<span class="la-chip {tone}">{escape(label)}</span>'


def _la_summary_html(summary):
    cells = []
    for label, value, warn in (("术语", summary["terms"], False),
                               ("翻译记忆", summary["tm"], False),
                               ("待审核", summary["review"], False),
                               ("冲突", summary["conflicts"], True)):
        tone = "la-stat is-warn" if warn and value else "la-stat"
        cells.append(f'<div class="{tone}"><span>{label}</span>'
                     f'<strong>{int(value):,}</strong></div>')
    return '<div class="la-summary">' + "".join(cells) + "</div>"


def _la_empty(title, detail, *, tone="info"):
    cls = "la-empty is-error" if tone == "error" else "la-empty"
    st.markdown(f'<div class="{cls}"><strong>{escape(title)}</strong>'
                f'<span>{escape(detail)}</span></div>', unsafe_allow_html=True)


def _la_key_fragment(text):
    return hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()[:10]


def _la_group_limit(document):
    key = f"la_group_limit_{_la_key_fragment(document)}"
    return max(_LA_PAGE_SIZE, int(st.session_state.get(key) or _LA_PAGE_SIZE))


def _la_bump_group_limit(document):
    key = f"la_group_limit_{_la_key_fragment(document)}"
    st.session_state[key] = _la_group_limit(document) + _LA_PAGE_SIZE


def _la_apply_limit():
    key = "la_review_limit"
    return max(_LA_PAGE_SIZE, int(st.session_state.get(key) or _LA_PAGE_SIZE))


# ---- 行渲染 ----

def _la_row_container(row_id, selected):
    """每行一个唯一容器；选中态用 :has(.la-sel-flag) 标记，避免 key 冲突。"""
    container = st.container(key=f"la_row_{_la_row_slug(row_id)}")
    if selected:
        container.markdown('<span class="la-sel-flag"></span>',
                           unsafe_allow_html=True)
    return container


def _la_term_row(row, *, selected):
    slug = _la_row_slug(row["row_id"])
    with _la_row_container(row["row_id"], selected):
        cols = st.columns([0.24, 0.21, 0.12, 0.10, 0.11, 0.10, 0.12],
                          vertical_alignment="center")
        if cols[0].button(f"**{row['source']}**", key=f"la_open_{slug}",
                          width="stretch", help="打开右侧 Inspector：来源、证据与出现位置"):
            _la_select(row["row_id"])
            st.rerun()
        cols[1].markdown(
            f'<div class="la-target">{escape(str(row["preferred"] or "—"))}</div>',
            unsafe_allow_html=True)
        cols[2].markdown(
            f'<div class="la-cell">{escape(str(row["domain"] or "—"))}</div>',
            unsafe_allow_html=True)
        cols[3].markdown(f'<div class="la-cell">{escape(row["scope_label"])}</div>',
                         unsafe_allow_html=True)
        cols[4].markdown(f'<div class="la-num">{int(row["usage"])}</div>',
                         unsafe_allow_html=True)
        cols[5].markdown(_la_status_chip(row["status"]), unsafe_allow_html=True)
        with cols[6].popover("⋯", key=f"la_more_{slug}"):
            if st.button("打开 Inspector", key=f"la_inspect_{slug}",
                         width="stretch"):
                _la_select(row["row_id"])
                st.rerun()
            if st.button("编辑术语", key=f"la_edit_{slug}", width="stretch"):
                _la_select(row["row_id"])
                st.session_state["la_edit_open"] = row["row_id"]
                st.rerun()
            st.button("提升为全局术语", key=f"la_promote_{slug}",
                      width="stretch", disabled=True, help=_LA_GLOBAL_TERMBASE_TODO)


def _la_tm_row(row, *, selected):
    slug = _la_row_slug(row["row_id"])
    with _la_row_container(row["row_id"], selected):
        cols = st.columns([0.42, 0.32, 0.14, 0.12], vertical_alignment="center")
        if cols[0].button(f"**{row['source']}**", key=f"la_open_{slug}",
                          width="stretch", help="打开右侧 Inspector 查看完整原文与译文"):
            _la_select(row["row_id"])
            st.rerun()
        cols[1].markdown(f'<div class="la-target">{escape(row["target"])}</div>',
                         unsafe_allow_html=True)
        cols[2].markdown('<span class="la-chip is-ok">已确认</span>',
                         unsafe_allow_html=True)
        with cols[3].popover("⋯", key=f"la_more_{slug}"):
            if st.button("打开 Inspector", key=f"la_inspect_{slug}",
                         width="stretch"):
                _la_select(row["row_id"])
                st.rerun()
            st.button("编辑", key=f"la_edit_{slug}", width="stretch",
                      disabled=True,
                      help="翻译记忆条目由审校流程写入；当前版本不提供直接编辑。")


def _la_candidate_row(row, *, selected, locked, bulk_locked):
    row_id = row["row_id"]
    slug = _la_row_slug(row_id)
    with _la_row_container(row_id, selected):
        cols = st.columns([0.05, 0.70, 0.13, 0.12], vertical_alignment="center")
        cols[0].checkbox("选择", key=_la_checkbox_key(row_id),
                         value=bool(_la_selection().get(row_id)),
                         on_change=_la_toggle_selection, args=(row_id,),
                         label_visibility="collapsed", disabled=bulk_locked)
        # 候选与它的元信息同列上下排布：一条候选两行，总高约 56–76px。
        if cols[1].button(f"**{row['source']}** → {row['target']}",
                          key=f"la_open_{slug}", disabled=locked, width="stretch",
                          help="打开右侧 Inspector：上下文与出现位置"):
            _la_select(row_id)
            st.rerun()
        chips = ""
        if row["has_conflict"]:
            chips += ' <span class="la-chip is-danger">冲突</span>'
        elif row["high_confidence"]:
            chips += ' <span class="la-chip is-ok">高置信</span>'
        meta = (f"{_language_assets.usage_text(row)} · 置信度 "
                f"{_language_assets.confidence_text(row)}")
        if locked:
            meta = "处理中…"
            chips = ""
        cols[1].markdown(f'<div class="la-meta">{escape(meta)}{chips}</div>',
                         unsafe_allow_html=True)
        if cols[2].button("接受", key=f"la_quick_{slug}", width="stretch",
                          disabled=locked or bulk_locked, help=_LA_QUICK_ACCEPT_NOTE):
            st.session_state["la_pending"] = {
                "scope": "row", "row_id": row_id, "action": "project_term"}
            st.rerun()
        with cols[3].popover("⋯", key=f"la_more_{slug}",
                             disabled=locked or bulk_locked):
            st.caption(row["document"] or "未命名文档")
            if st.button("仅此次采用", key=f"la_task_{slug}", width="stretch"):
                st.session_state["la_pending"] = {
                    "scope": "row", "row_id": row_id, "action": "task_only"}
                st.rerun()
            if st.button("拒绝", key=f"la_reject_{slug}", width="stretch"):
                st.session_state["la_pending"] = {
                    "scope": "row", "row_id": row_id, "action": "rejected"}
                st.rerun()
            if st.button("在 Inspector 中查看", key=f"la_inspect_{slug}",
                         width="stretch"):
                _la_select(row_id)
                st.rerun()


# ---- Inspector ----

def _la_inspector_hint(title, detail):
    st.markdown(f'<p class="la-kicker">Inspector</p>'
                f'<p class="la-inspector-title">{escape(title)}</p>'
                f'<p class="la-inspector-sub">{escape(detail)}</p>',
                unsafe_allow_html=True)


def _la_kv(pairs):
    rows = "".join(f"<dt>{escape(str(label))}</dt><dd>{escape(str(value))}</dd>"
                   for label, value in pairs)
    st.markdown(f'<dl class="la-kv">{rows}</dl>', unsafe_allow_html=True)


def _la_term_inspector(row):
    slug = _la_row_slug(row["row_id"])
    tasks = list(row.get("tasks") or [])
    project_names = [str(name).strip() for name in row.get("project_names") or []
                     if str(name).strip()]
    documents = row.get("documents") or []
    source_hint = (
        "项目术语 · " + (project_names[0] if len(project_names) == 1
                       else "多个项目" if project_names else
                       documents[0] if documents else "—")
    )
    _la_inspector_hint(row["source"], source_hint)
    term_meta = [
        ("推荐译法", row["preferred"] or "—"),
    ]
    proposed = str(row.get("proposed_target") or "").strip()
    if proposed and proposed.casefold() != str(row["preferred"] or "").casefold():
        term_meta.append(("可选译法", proposed))
    term_meta.extend([
        ("分类", row["domain"] or "—"),
        ("语言方向", f"→ {row['target_lang']}" if row.get("target_lang") else "—"),
        ("作用域", row["scope_label"]),
        ("状态", _language_assets.status_label(row["status"])),
        ("行为", _language_assets.behavior_label(row["behavior"])),
        ("使用次数", int(row["usage"])),
        ("来源任务", f"{len(tasks)} 个任务"),
    ])
    if project_names:
        term_meta.append(("来源项目", "、".join(project_names)))
    _la_kv(term_meta)
    if row.get("forbidden"):
        st.markdown(f'<p class="la-kicker">禁止译法</p><div class="la-context">'
                    f'{escape("、".join(row["forbidden"]))}</div>',
                    unsafe_allow_html=True)
    evidence = row.get("evidence") or []
    if evidence:
        lines = []
        for item in evidence[:3]:
            label = _EVIDENCE_LABELS.get(item.get("evidence_type"),
                                         item.get("evidence_type") or "—")
            note = str(item.get("note") or "").strip()
            lines.append(f"{label}：{note}" if note else str(label))
        st.markdown('<p class="la-kicker">来源 / 证据</p>'
                    f'<div class="la-context">{escape("；".join(lines))}</div>',
                    unsafe_allow_html=True)
    if tasks:
        lines = "".join(
            f'<div class="la-occ">{escape(str(task.get("document") or "—"))}'
            f' · {int(task.get("usage") or 0)} 次 · '
            f'{escape(_language_assets.status_label(task.get("status")))}</div>'
            for task in tasks[:6])
        st.markdown('<p class="la-kicker">出现任务</p>' + lines,
                    unsafe_allow_html=True)
    st.markdown('<div class="la-divider"></div>', unsafe_allow_html=True)

    task_ids = [str(task.get("job_id") or "") for task in tasks if task.get("job_id")]
    names = {str(task.get("job_id")): str(task.get("document") or "—") for task in tasks}
    chosen = task_ids[0] if task_ids else ""
    if len(task_ids) > 1:
        chosen = st.selectbox(
            "编辑哪个任务", task_ids, key=f"la_term_task_{slug}",
            format_func=lambda value: names.get(str(value), str(value)))
    entry_ids = {str(task.get("job_id")): str(task.get("entry_id") or "") for task in tasks}

    if not task_ids:
        st.button("编辑", key=f"la_project_edit_{slug}", width="stretch",
                  disabled=True,
                  help="项目术语由项目记忆维护流程管理；当前版本没有直接编辑项目文件的 API")
        st.caption("这条术语来自已持久化的项目记忆。当前页面可查看它，修改请从任务术语确认后再提升。")
    else:
        with st.expander("编辑", expanded=st.session_state.get("la_edit_open") == row["row_id"]):
            preferred = st.text_input("推荐译法", value=row["preferred"],
                                      key=f"la_term_pref_{slug}")
            domain = st.text_input("分类 / 领域", value=row["domain"],
                                   key=f"la_term_domain_{slug}")
            status_labels = _la_option_labels(list(_language_assets.TERM_STATUS_LABELS.items()))
            current_status = _language_assets.TERM_STATUS_LABELS.get(
                str(row["status"]).strip().casefold(), "暂定")
            status = st.selectbox(
                "状态", status_labels,
                index=status_labels.index(current_status) if current_status in status_labels else 0,
                key=f"la_term_status_{slug}")
            if st.button("保存术语", key=f"la_term_edit_save_{slug}",
                         type="primary", width="stretch", disabled=not chosen):
                _, ok, message = core.update_glossary_entry(
                    chosen, entry_ids.get(chosen, ""), preferred=preferred,
                    domain=domain,
                    status=_la_option_value(list(_language_assets.TERM_STATUS_LABELS.items()),
                                            status, "provisional"))
                _la_flash(message, "success" if ok else "error")
                if ok:
                    st.session_state["la_edit_open"] = None
                    # 行 id 由 source→preferred 决定；改了推荐译法就换到新的那一行，
                    # 否则 Inspector 会在下一次 rerun 里失去选中项。
                    _la_select("term::{}::{}".format(
                        str(row["source"]).casefold(),
                        str(preferred or "").strip().casefold()))
                st.rerun()
    if st.button("提升为全局术语", key=f"la_term_promote_{slug}",
                 width="stretch", disabled=True, help=_LA_GLOBAL_TERMBASE_TODO):
        pass
    confirm = st.checkbox("确认从术语草稿中删除该术语",
                          key=f"la_term_delete_confirm_{slug}")
    if st.button("删除", key=f"la_term_delete_{slug}", width="stretch",
                 disabled=not (chosen and confirm)):
        _, ok, message = core.delete_glossary_entry(
            chosen, entry_ids.get(chosen, ""))
        _la_flash(message, "success" if ok else "error")
        if ok:
            _la_select(None)
        st.rerun()
    st.caption("修改会生成新的术语版本，并失效受影响段落的既有审校。")


def _la_tm_inspector(row):
    _la_inspector_hint(row["source"][:80], "翻译记忆 · 精确命中复用")
    _la_kv([
        ("状态", "已确认" if row["reviewed"] else "未确认"),
        ("更新时间", str(row["updated_at"]).replace("T", " ")[:19] or "—"),
        ("原文长度", f"{row['source_chars']} 字符"),
    ])
    st.markdown('<p class="la-kicker">原文</p>'
                f'<div class="la-context">{escape(row["source"])}</div>',
                unsafe_allow_html=True)
    st.markdown('<p class="la-kicker">译文</p>'
                f'<div class="la-context is-target">{escape(row["target"])}</div>',
                unsafe_allow_html=True)
    st.caption("翻译记忆只保存原文、译文与更新时间；后端不记录来源文档、出现次数或"
               "模糊匹配相似度，因此这里不显示这些字段。")


def _la_candidate_inspector(row):
    slug = _la_row_slug(row["row_id"])
    row_id = row["row_id"]
    _la_inspector_hint(row["source"], f"{row['kind_label']} · {row['document'] or '—'}")
    _la_kv([
        ("建议译法", row["target"] or "—"),
        ("置信度", _language_assets.confidence_text(row)),
        ("出现次数", (int(row["occurrence_count"]) if row["positions_known"]
                  else "未知")),
        ("类型", row["kind_label"]),
        ("来源文档", row["document"] or "—"),
        ("首次出现", row["first_reference"] or "—"),
    ])
    if row["has_conflict"]:
        st.warning("与现有项目术语存在译名冲突：" + (row["conflict_summary"] or "—"))
    st.markdown('<p class="la-kicker">上下文</p>', unsafe_allow_html=True)
    st.markdown('<div class="la-context">'
                f'{escape(row["source_context"] or "（未找到原文段落）")}</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="la-context is-target">'
                f'{escape(row["target_context"] or "（未找到译文段落）")}</div>',
                unsafe_allow_html=True)
    entries = list(row.get("position_entries") or [])
    if entries:
        show_all = bool(st.session_state.get(f"la_pos_all_{row_id}"))
        visible = entries if show_all else entries[:6]
        st.markdown('<p class="la-kicker">出现位置</p>', unsafe_allow_html=True)
        for entry in visible:
            occ_cols = st.columns([0.48, 0.52], vertical_alignment="center")
            occ_cols[0].markdown(
                f'<div class="la-occ">{escape(entry["label"])}</div>',
                unsafe_allow_html=True)
            if occ_cols[1].button(
                    "定位到工作台", key=f"la_jump_{slug}_{entry['index']}",
                    width="stretch",
                    help="打开该任务的工作台，并选中这个段落"):
                _la_jump_to_segment(row["job_id"], entry["index"])
        if not show_all and len(entries) > len(visible):
            if st.button(f"查看全部出现位置（{len(entries)}）",
                         key=f"la_pos_more_{slug}", width="stretch"):
                st.session_state[f"la_pos_all_{row_id}"] = True
                st.rerun()
    else:
        st.caption("当前状态没有可用的段落位置记录。")

    st.markdown('<div class="la-divider"></div>', unsafe_allow_html=True)
    accept_mode = bool(st.session_state.get(f"la_accept_mode_{slug}"))
    if not accept_mode:
        st.markdown('<p class="la-kicker">决策</p>', unsafe_allow_html=True)
        action_cols = st.columns(2)
        if action_cols[0].button("接受", key=f"la_ins_accept_{slug}",
                                 type="primary", width="stretch"):
            st.session_state[f"la_accept_mode_{slug}"] = True
            st.rerun()
        if action_cols[1].button("拒绝", key=f"la_ins_reject_{slug}",
                                 width="stretch"):
            st.session_state["la_pending"] = {
                "scope": "row", "row_id": row_id, "action": "rejected"}
            st.rerun()
        return
    st.markdown('<p class="la-kicker">保存到</p>', unsafe_allow_html=True)
    save_target = st.radio(
        "保存到", ["项目术语库", "不保存，仅此次采用"],
        key=f"la_save_target_{slug}", label_visibility="collapsed")
    st.checkbox("全局术语库", value=False, disabled=True,
                key=f"la_global_todo_{slug}", help=_LA_GLOBAL_TERMBASE_TODO)
    st.caption("全局术语库暂不可用：后端尚未提供独立的全局术语库存储。")
    if save_target == "项目术语库":
        if st.button("接受并保存", key=f"la_ins_save_{slug}", type="primary",
                     width="stretch"):
            st.session_state["la_pending"] = {
                "scope": "row", "row_id": row_id, "action": "project_term"}
            st.rerun()
    else:
        if st.button("仅此次采用", key=f"la_ins_task_{slug}", type="primary",
                     width="stretch"):
            st.session_state["la_pending"] = {
                "scope": "row", "row_id": row_id, "action": "task_only"}
            st.rerun()
    if st.button("取消", key=f"la_ins_cancel_{slug}", width="stretch"):
        st.session_state[f"la_accept_mode_{slug}"] = False
        st.rerun()
    st.caption(_LA_QUICK_ACCEPT_NOTE)
    st.button("更改默认", key=f"la_quick_default_{slug}", width="stretch",
              disabled=True, help="当前版本没有其他可用的长期保存位置。")


def _la_render_inspector(tab, *, term_rows, tm_rows, candidate_rows):
    with st.container(key="la_inspector"):
        selected = _la_selected_row_id()
        if tab == "terms":
            row = next((item for item in term_rows
                        if item["row_id"] == selected), None)
            if row is None:
                _la_inspector_hint("术语详情", "点击左侧术语名称打开详情。")
                return
            _la_term_inspector(row)
        elif tab == "tm":
            row = next((item for item in tm_rows
                        if item["row_id"] == selected), None)
            if row is None:
                _la_inspector_hint("翻译记忆详情", "点击左侧原文打开详情。")
                return
            _la_tm_inspector(row)
        else:
            row = next((item for item in candidate_rows
                        if item["row_id"] == selected), None)
            if row is None:
                _la_inspector_hint("候选详情", "点击左侧候选项打开上下文与出现位置。")
                return
            _la_candidate_inspector(row)


# ---- 三个 Tab ----

def _la_terms_tab(jobs, rows):
    selected = _la_selected_row_id()
    job_choices = [(str(job.get("job_id") or ""),
                    str((job.get("state") or {}).get("filename") or "?"))
                   for job in jobs]
    with st.container(key="la_toolbar"):
        cols = st.columns([0.23, 0.13, 0.13, 0.13, 0.13, 0.25],
                          vertical_alignment="bottom")
        query = cols[0].text_input(
            "搜索术语", key="la_terms_query", placeholder="搜索术语……",
            label_visibility="collapsed")
        scope_labels = _la_option_labels(_la_scope_options())
        _la_guard_option("la_terms_scope", scope_labels)
        scope_label = cols[1].selectbox("作用域", scope_labels, key="la_terms_scope")
        domains = ["全部", *_language_assets.domain_options(rows)]
        _la_guard_option("la_terms_domain", domains)
        domain = cols[2].selectbox("分类", domains, key="la_terms_domain")
        status_options = ["全部", *_la_option_labels(
            list(_language_assets.TERM_STATUS_LABELS.items()))]
        _la_guard_option("la_terms_status", status_options)
        status_label = cols[3].selectbox("状态", status_options, key="la_terms_status")
        languages = ["全部", *_language_assets.target_language_options(rows)]
        _la_guard_option("la_terms_target_lang", languages)
        target_lang = cols[4].selectbox(
            "目标语言", languages, key="la_terms_target_lang",
            help="任务状态只持久化目标语言，未持久化源语言，因此这里不伪造完整语言对。")
        if cols[5].button("+ 新建术语", key="la_new_term", type="primary",
                          width="stretch", disabled=not job_choices,
                          help="术语保存在指定任务的术语表里并生成新的术语版本"):
            st.session_state["la_show_new_term"] = True
    if not rows:
        _la_empty("当前项目还没有术语。",
                  "在任务里完成术语抽取，或在「待审核」中接受候选后，术语会出现在这里。")
        return
    filtered = _language_assets.filter_terms(
        rows, query=query,
        scope=_la_option_value(_la_scope_options(), scope_label, "all"),
        domain="" if domain == "全部" else domain,
        status=_la_option_value(
            list(_language_assets.TERM_STATUS_LABELS.items()), status_label, ""),
        target_lang="" if target_lang == "全部" else target_lang)
    st.caption(f"显示 {len(filtered)} / {len(rows)} 条术语 · 点击术语名称打开右侧详情")
    if not filtered:
        _la_empty("没有匹配的术语。", "调整搜索词或筛选条件。")
        return
    spec = [0.26, 0.21, 0.12, 0.10, 0.11, 0.10, 0.10]
    with st.container(key="la_head_row"):
        head = st.columns(spec)
        for column, label in zip(head, ["术语", "推荐译法", "分类", "作用域",
                                        "使用次数", "状态", "操作"]):
            column.markdown(f'<div class="la-head">{label}</div>',
                            unsafe_allow_html=True)
    with st.container(key="la_list"):
        for row in filtered:
            _la_term_row(row, selected=row["row_id"] == selected)
    if st.session_state.get("la_show_new_term"):
        _la_new_term_dialog(job_choices)


def _la_tm_tab(projects, ordered_ids, labels, tm_rows, tm_project_id):
    with st.container(key="la_toolbar"):
        cols = st.columns([0.36, 0.20, 0.22], vertical_alignment="bottom")
        query = cols[0].text_input(
            "搜索原文或译文", key="la_tm_query", placeholder="搜索原文或译文……",
            label_visibility="collapsed")
        # 来源 / 语言对：后端 TM 记录只有 target / reviewed / updated_at，
        # 没有来源文档与语言对字段，因此只把 IA 位置留出来，不伪造数据。
        cols[1].selectbox("来源", ["全部来源"], key="la_tm_source", disabled=True,
                          help=_LA_TM_SOURCE_TODO)
        cols[2].selectbox("语言对", ["全部语言对"], key="la_tm_langpair",
                          disabled=True, help=_LA_TM_LANGPAIR_TODO)
        st.selectbox("查看哪个项目的记忆", ordered_ids, key="library_tm_project",
                     format_func=lambda value: labels.get(str(value), str(value)))
        st.caption("作用域：翻译记忆按项目隔离，同一原文在不同项目可以有不同译法。"
                   "来源与语言对暂不可用：TM 记录没有这两个字段。")
    counts = st.columns(max(1, min(4, len(projects))))
    for column, project in zip(counts, projects[:4]):
        column.metric(project["name"], len(core.load_tm(project["project_id"])))
    with st.expander("翻译记忆维护", expanded=False):
        st.caption("翻译记忆按项目隔离，清空只影响当前查看的项目。"
                   f"系统工作区「{core.SYSTEM_PROJECT_NAME}」沿用历史上的全局记忆。")
        confirm = st.checkbox(
            f"确认清空「{labels.get(tm_project_id, tm_project_id)}」的全部翻译记忆",
            key="library_tm_clear_confirm")
        if st.button("清空该项目的翻译记忆", disabled=not confirm,
                     key="library_tm_clear"):
            core.save_tm({}, tm_project_id)
            _la_flash("已清空该项目的翻译记忆。", "success")
            st.rerun()
    filtered = _language_assets.filter_tm(tm_rows, query=query)
    st.caption(f"显示 {len(filtered)} / {len(tm_rows)} 条已确认记忆 · "
               "点击原文打开右侧详情")
    if not tm_rows:
        _la_empty("完成并确认翻译后，翻译记忆会出现在这里。",
                  "通过独立审校的段落会自动写入所属项目的翻译记忆。")
        return
    if not filtered:
        _la_empty("没有匹配的翻译记忆。", "调整搜索词后重试。")
        return
    spec = [0.42, 0.32, 0.14, 0.12]
    with st.container(key="la_head_row"):
        head = st.columns(spec)
        for column, label in zip(head, ["原文", "译文", "状态", "操作"]):
            column.markdown(f'<div class="la-head">{label}</div>',
                            unsafe_allow_html=True)
    with st.container(key="la_list"):
        for row in filtered[:_la_apply_limit()]:
            _la_tm_row(row, selected=row["row_id"] == _la_selected_row_id())
    if len(filtered) > _la_apply_limit():
        remaining = len(filtered) - _la_apply_limit()
        if st.button(f"显示更多（还剩 {remaining} 条）", key="la_tm_more",
                     width="stretch"):
            st.session_state["la_review_limit"] = _la_apply_limit() + _LA_PAGE_SIZE
            st.rerun()


def _la_review_tab(rows):
    selection = _la_selection()
    pending = st.session_state.get("la_pending")
    locked_row = str(pending.get("row_id") or "") \
        if isinstance(pending, dict) and pending.get("scope") == "row" else ""
    bulk_locked = isinstance(st.session_state.get("la_pending_bulk"), dict)

    with st.container(key="la_toolbar"):
        top = st.columns([0.26, 0.17, 0.18, 0.19, 0.20], vertical_alignment="bottom")
        query = top[0].text_input(
            "搜索候选术语、译文或来源", key="la_review_query",
            placeholder="搜索候选术语、译文或来源……", label_visibility="collapsed")
        kind_options = _la_option_labels(_la_kind_options())
        _la_guard_option("la_review_kind", kind_options)
        kind_label = top[1].selectbox("候选类型", kind_options, key="la_review_kind")
        documents = ["全部文档", *_language_assets.document_options(rows)]
        _la_guard_option("la_review_doc", documents)
        document = top[2].selectbox("来源文档", documents, key="la_review_doc")
        confidence_options = _la_option_labels(_la_confidence_options())
        _la_guard_option("la_review_conf", confidence_options)
        confidence_label = top[3].selectbox(
            "置信度", confidence_options, key="la_review_conf",
            help=f"高置信度阈值 {_language_assets.HIGH_CONFIDENCE_THRESHOLD:.2f}")
        group_options = ["按文档分组", "平铺列表"]
        _la_guard_option("la_review_group", group_options)
        group_label = top[4].selectbox("列表", group_options, key="la_review_group")
        chip = st.pills("快速筛选", ["全部", "高置信度", "有冲突", "新术语"],
                        default="全部", key="la_review_chip",
                        label_visibility="collapsed")
    chip = chip if chip in {"全部", "高置信度", "有冲突", "新术语"} else "全部"
    kind = _la_option_value(_la_kind_options(), kind_label, "")
    if kind == "all":
        kind = ""  # 「全部」是不过滤，不是 kind 必须等于 all
    confidence = _la_option_value(_la_confidence_options(), confidence_label, "all")
    document = "" if document == "全部文档" else document

    signature = "|".join([str(query), str(kind), str(document),
                          str(confidence), str(chip)])
    if st.session_state.get("la_review_signature") != signature:
        st.session_state["la_review_signature"] = signature
        st.session_state["la_review_limit"] = _LA_PAGE_SIZE
        for key in [item for item in list(st.session_state)
                    if str(item).startswith("la_group_limit_")]:
            del st.session_state[key]

    filtered = _language_assets.filter_candidates(
        rows, query=query, kind=kind, document=document, confidence=confidence,
        only_conflicts=chip == "有冲突", only_high=chip == "高置信度",
        only_new=chip == "新术语")
    grouping = (group_label == "按文档分组"
                and not query.strip() and not kind and not document
                and confidence == "all" and chip == "全部")

    selected_rows = [item for item in rows if item["row_id"] in selection]
    high_rows = [item for item in rows if item["high_confidence"]]
    header = st.columns([0.66, 0.34], vertical_alignment="center")
    suffix = "（已筛选）" if len(filtered) != len(rows) else ""
    header[0].caption(f"待审核 {len(filtered)} 条{suffix}")
    with header[1]:
        if high_rows:
            if st.button(f"选择全部高置信度候选（{len(high_rows)}）",
                         key="la_select_high", width="stretch", disabled=bulk_locked):
                for item in high_rows:
                    selection[item["row_id"]] = True
                st.session_state["la_selection"] = selection
                st.rerun()

    if selected_rows:
        with st.container(key="la_bulk_bar"):
            bar = st.columns([0.16, 0.29, 0.18, 0.12, 0.25],
                             vertical_alignment="center")
            bar[0].markdown(f"已选择 {len(selected_rows)} 项")
            bulk_specs = (("接受并加入项目术语", "project_term", "已加入项目术语"),
                          ("仅此次采用", "task_only", "已标记仅此次采用"),
                          ("拒绝", "rejected", "已拒绝"))
            for column, (label, action, done_label) in zip(bar[1:4], bulk_specs):
                if column.button(label, key=f"la_bulk_{action}", width="stretch",
                                 disabled=bulk_locked):
                    st.session_state["la_pending_bulk"] = {
                        "action": action, "label": done_label,
                        "ids": [item["row_id"] for item in selected_rows]}
                    st.rerun()
            if bar[4].button("取消选择", key="la_bulk_clear", width="stretch",
                             disabled=bulk_locked):
                _la_clear_selection()
                st.rerun()

    if not rows:
        _la_empty("当前没有需要审核的候选内容。",
                  "Agent 在翻译过程中发现的术语候选会出现在这里，等待人工确认。")
        return
    if not filtered:
        _la_empty("没有匹配的候选。", "调整搜索词或筛选条件。")
        return

    def _render_rows(items, list_key="la_list"):
        with st.container(key=list_key):
            for item in items:
                _la_candidate_row(
                    item, selected=item["row_id"] == _la_selected_row_id(),
                    locked=item["row_id"] == locked_row, bulk_locked=bulk_locked)

    if grouping:
        for document_name, group_rows in _language_assets.group_candidates_by_document(
                filtered):
            limit = _la_group_limit(document_name)
            with st.expander(f"{document_name} · {len(group_rows)} 条", expanded=True):
                _render_rows(group_rows[:limit],
                             f"la_list_{_la_key_fragment(document_name)}")
                if len(group_rows) > limit:
                    remaining = len(group_rows) - limit
                    if st.button(f"显示更多（还剩 {remaining} 条）",
                                 key=f"la_group_more_{_la_key_fragment(document_name)}",
                                 width="stretch"):
                        _la_bump_group_limit(document_name)
                        st.rerun()
    else:
        limit = _la_apply_limit()
        _render_rows(filtered[:limit])
        if len(filtered) > limit:
            remaining = len(filtered) - limit
            if st.button(f"显示更多（还剩 {remaining} 条）", key="la_review_more",
                         width="stretch"):
                st.session_state["la_review_limit"] = limit + _LA_PAGE_SIZE
                st.rerun()


@st.dialog("新建术语")
def _la_new_term_dialog(job_choices):
    st.caption("术语保存在所选任务的术语表里，并生成新的术语版本。"
               "当前版本没有独立的全局术语库存储。")
    labels = {str(job_id): str(name) for job_id, name in job_choices}
    job_id = st.selectbox("保存到任务", list(labels),
                          format_func=lambda value: labels.get(str(value), str(value)),
                          key="la_new_term_job")
    source = st.text_input("原术语", key="la_new_term_source")
    target = st.text_input("推荐译法", key="la_new_term_target")
    domain = st.text_input("分类 / 领域（可选）", key="la_new_term_domain")
    action_cols = st.columns(2)
    if action_cols[0].button("创建术语", key="la_new_term_submit", type="primary",
                             width="stretch"):
        _, ok, message, _ = core.add_glossary_entry(job_id, source, target,
                                                    domain=domain)
        if ok:
            st.session_state["la_show_new_term"] = False
            _la_flash(message, "success")
            st.rerun()
        st.error(message)
    if action_cols[1].button("取消", key="la_new_term_cancel", width="stretch"):
        st.session_state["la_show_new_term"] = False
        st.rerun()


def _render_language_assets_workspace(saved_jobs):
    """术语与翻译记忆：语言资产管理中心（术语库 / 翻译记忆 / 待审核）。"""
    _page_title("术语与翻译记忆", "维护项目语言资产，并审核 Agent 发现的候选内容")
    _la_render_flash()
    tab = _la_sync_tab()
    try:
        jobs = list(saved_jobs if saved_jobs is not None else core.list_jobs())
        projects = core.list_active_project_options() + [
            project for project in core.list_projects() if project.get("archived_at")]
        ordered_ids = [str(project["project_id"]) for project in projects] \
            or [core.SYSTEM_PROJECT_ID]
        labels = {str(project["project_id"]): project["name"] for project in projects}
        stored = st.session_state.get("library_tm_project")
        if stored not in ordered_ids:
            # 默认看**当前项目上下文**的记忆：这里是一个查看器（不切换上下文），
            # 但它的起点应该与"我此刻在哪个项目里"一致。
            context_id = str((_current_project_context() or {}).get("project_id")
                             or "")
            st.session_state["library_tm_project"] = (
                context_id if context_id in ordered_ids else ordered_ids[0])
        tm_project_id = str(st.session_state["library_tm_project"])
        tm_rows = _language_assets.build_tm_rows(core.load_tm(tm_project_id))
        task_term_rows = _language_assets.build_term_rows(jobs)
        project_by_id = {str(project.get("project_id")): project
                         for project in projects}
        job_by_id = {str(job.get("job_id")): job for job in jobs}
        # 任务状态里可能仍然写着历史别名 `default`；展示层统一到真实项目 UUID，
        # 让项目术语的使用次数与任务来源能正确归并，也不把旧别名显示给用户。
        for row in task_term_rows:
            job = job_by_id.get(str(row.get("job_id") or "")) or {}
            row["project_id"] = core.resolved_project_id(job.get("state") or {})
            project = project_by_id.get(row["project_id"])
            row["project_name"] = str((project or {}).get("name") or "未分类")
        project_term_rows = _language_assets.build_project_term_rows(
            projects, task_rows=task_term_rows)
        term_rows = _language_assets.group_terms(
            [*task_term_rows, *project_term_rows])
        candidate_rows = _language_assets.build_candidate_rows(jobs)
    except Exception as exc:
        _la_empty("无法加载语言资产", f"{exc}", tone="error")
        if st.button("重试", key="la_retry"):
            st.rerun()
        return

    summary = {
        "terms": len(term_rows), "tm": len(tm_rows),
        "review": len(candidate_rows),
        "conflicts": sum(1 for item in candidate_rows if item["has_conflict"]),
    }
    st.markdown(_la_summary_html(summary), unsafe_allow_html=True)

    tab_labels = {
        "terms": "术语库",
        "tm": "翻译记忆",
        "review": (f"待审核 {summary['review']}" if summary["review"] else "待审核"),
    }
    options = list(_language_assets.VALID_TABS)
    chosen = st.segmented_control(
        "语言资产视图", options, format_func=lambda key: tab_labels.get(key, key),
        key="library_tab", label_visibility="collapsed", required=True)
    if chosen in options:
        tab = str(chosen)
    if st.session_state.get("library_tab_for_selection") != tab:
        st.session_state["library_tab_for_selection"] = tab
        _la_select(None)
    _la_publish_query(tab)

    main_col, inspector_col = st.columns([0.68, 0.32], gap="large")
    with main_col:
        if tab == "terms":
            _la_terms_tab(jobs, term_rows)
        elif tab == "tm":
            _la_tm_tab(projects, ordered_ids, labels, tm_rows, tm_project_id)
        else:
            _la_review_tab(candidate_rows)
    with inspector_col:
        _la_render_inspector(tab, term_rows=term_rows, tm_rows=tm_rows,
                             candidate_rows=candidate_rows)
    _la_execute_pending(candidate_rows)


def _render_delivery_review_queue(
    job_id, state, target_lang, ai_provider, ai_model, api_key, style_rules,
):
    """Render the human review queue; delivery state changes stay in core.py."""
    review_runtime = resolve_review_runtime()
    review_required = bool(state.get("translation_core_review_required"))
    findings = _delivery.review_queue_findings(state)
    contexts = sorted(
        [_delivery.finding_context(state, finding) for finding in findings],
        key=_review_sort_key)
    st.divider()
    st.subheader("人工审查队列")
    if not contexts:
        st.success("当前没有待处理发现；可以继续准备交付资产。")
        return

    counts = {severity: sum(1 for x in contexts if x["severity"] == severity)
              for severity in _delivery.SEVERITY_LABELS}
    st.caption(
        f"共 {len(contexts)} 个待审问题 · "
        f"必须处理 {counts['blocking']} · 建议检查 {counts['actionable']} · "
        f"仅供参考 {counts['informational']}。先处理必须处理项；相同审校事件的重复记录已合并，"
        "不同审校事件会分别保留。")
    metric_cols = st.columns(4)
    metric_cols[0].metric("待审", len(contexts))
    metric_cols[1].metric("必须处理", counts["blocking"])
    metric_cols[2].metric("建议检查", counts["actionable"])
    metric_cols[3].metric("仅供参考", counts["informational"])

    filter_options = ["必须处理", "全部", "建议检查", "仅供参考"]
    default_filter = "必须处理" if counts["blocking"] else "全部"
    filter_label = st.radio(
        "筛选发现", filter_options,
        index=filter_options.index(default_filter), horizontal=True,
        key=f"fd_filter_{job_id}")
    selected_severity = {
        "必须处理": "blocking", "建议检查": "actionable", "仅供参考": "informational",
    }.get(filter_label)
    visible = [x for x in contexts
               if selected_severity is None or x["severity"] == selected_severity]
    st.caption(f"当前显示 {len(visible)} 项；展开单项可查看原文、译文和审校证据。")

    selectable = [x for x in contexts if x["severity"] in ("blocking", "actionable")
                  or x["proper_noun_candidate"]]
    for ordinal, context in enumerate(visible):
        fid = context["finding_id"]
        interactive = context in selectable
        if interactive:
            st.checkbox(
                "选择此问题",
                key=f"fd_select_{job_id}_{fid}",
                help="选择后可在队列底部批量标记或重新翻译。")
        title = (
            f"第 {context['segment_number']} 段 · {context['severity_label']} · "
            f"{context['reason'][:100]}")
        if context["duplicate_count"] > 1:
            title += f" · 已合并 {context['duplicate_count']} 条重复记录"
        with st.expander(title, expanded=(ordinal == 0 and context["severity"] == "blocking")):
            st.caption(f"问题编号（调试/证据追踪）：{fid}")
            if context["detected_text"]:
                st.markdown("**检测到的文本**")
                st.code(context["detected_text"])
            source_col, target_col = st.columns(2)
            with source_col:
                st.markdown("**原文**")
                st.code(context["source"] or "（未找到对应段落）")
            with target_col:
                st.markdown("**当前译文**")
                st.code(context["target"] or "（未找到当前译文）")
            if context["initial_target"] and context["initial_target"] != context["target"]:
                st.caption("初译（当前译文之前）：")
                st.code(context["initial_target"])
            st.markdown(f"**问题说明**：{context['reason']}")
            if context["proper_noun_candidate"]:
                st.info(
                    "检测到的源语片段可能是人名、机构名或作品名。若确认这是有意保留，"
                    "可选择该问题并使用“确认保留专名”，不会强制重新翻译。")
            _render_finding_evidence(context)

    selected = [
        context for context in selectable
        if st.session_state.get(f"fd_select_{job_id}_{context['finding_id']}", False)
    ]
    selected_ids = [context["finding_id"] for context in selected]
    selected_segments = sorted({
        context["segment_index"] for context in selected
        if context["severity"] in ("blocking", "actionable")
        and isinstance(context["segment_index"], int)
    })
    preserve_ids = [
        context["finding_id"] for context in selected
        if context["proper_noun_candidate"]
    ]
    st.divider()
    st.caption(
        f"已选择 {len(selected)} 个问题 / {len(selected_segments)} 个段落。"
        "批量重新翻译按段落执行，同一段的多个问题会一起复验。")
    note = st.text_input("处理说明（可选）", key=f"fd_note_{job_id}")
    action_cols = st.columns(4)
    if action_cols[0].button(
            "标记选中为人工已处理", disabled=not selected_ids,
            key=f"fd_fix_{job_id}", width="stretch"):
        core.mark_findings_resolved(
            job_id, selected_ids, "human_fixed", note or "人工核对后确认已处理")
        st.rerun()
    if action_cols[1].button(
            "重新翻译选中段落",
            disabled=(not selected_segments or not api_key or not ai_model
                      or (review_required and not _review_runtime_ready(review_runtime))),
            key=f"fd_retranslate_{job_id}", width="stretch"):
        core.retranslate_segments(
            job_id, selected_segments, ai_provider, api_key, ai_model,
            target_lang, style_rules=style_rules,
            reviewer_provider=review_runtime["provider"],
            reviewer_api_key=review_runtime["api_key"],
            reviewer_model=review_runtime["model"],
            reviewer_base_url=review_runtime["base_url"],
            on_caption=lambda text: st.caption(text))
        st.rerun()
    if action_cols[2].button(
            "确认保留选中专名", disabled=not preserve_ids,
            key=f"fd_preserve_{job_id}", width="stretch"):
        core.mark_findings_resolved(
            job_id, preserve_ids, "preserved",
            note or "用户确认该源语片段为有意保留的专名")
        st.rerun()
    if action_cols[3].button(
            "清除选择", disabled=not selected,
            key=f"fd_clear_{job_id}", width="stretch"):
        for context in selectable:
            st.session_state.pop(f"fd_select_{job_id}_{context['finding_id']}", None)
        st.rerun()
    if selected_segments and (not api_key or not ai_model):
        st.warning("重新翻译需要先完成 AI 引擎配置；人工处理和确认保留仍可使用。")
    elif selected_segments and review_required and not _review_runtime_ready(review_runtime):
        st.warning(f"{_review_runtime_missing_message()}；人工处理和确认保留仍可使用。")


def _render_delivery_gate(job_id, state, dstatus, target_lang="", provider="", model=""):
    st.divider()
    st.subheader("最终交付")
    review_view = _review_workbench(state)
    if not review_view["readiness"]["ready"]:
        delivery_copy = review_view["delivery"]
        st.error(f"{delivery_copy['title']}：{delivery_copy['detail']}。")
        return
    blockers = _delivery.unresolved_blocking(state)
    actions = _delivery.unresolved_findings(state)
    if blockers:
        hard_gate_reasons = _workspace_hard_gate_reasons(job_id, state)
        if hard_gate_reasons:
            st.error("当前版本存在不可通过‘接受风险’跳过的交付门禁：" +
                     "、".join(hard_gate_reasons) + "。请先完成这些门禁。")
            return
        st.warning(f"仍有 {len(blockers)} 个必须处理问题；未处理或未明确接受风险前不能最终交付。")
        confirm = st.checkbox(
            "我已检查这些必须处理问题，并确认接受剩余风险",
            key=f"fd_accept_confirm_{job_id}")
        note = st.text_input("接受风险说明", key=f"fd_accept_note_{job_id}")
        if st.button(
                "接受必须处理风险并进入最终交付",
                disabled=not confirm, key=f"fd_accept_{job_id}", width="stretch"):
            _, ok, errors = core.approve_delivery(
                job_id, note or "人工确认并接受剩余 blocking 风险", accept_blocking=True,
                target_lang=target_lang, provider=provider, model=model)
            if ok:
                st.rerun()
            for error in errors:
                st.error(error)
    elif dstatus == "final":
        snapshot = core.delivery_snapshot_status(job_id, state)
        if snapshot["current"]:
            latest = snapshot["latest"]
            st.success(
                f"最终交付版本 v{latest['snapshot_version']} 已冻结；"
                "后续工作版本变更不会修改该版本。")
        else:
            st.warning(
                "当前任务虽有最终状态，但没有可用的冻结交付版本，或工作版本已有变更；"
                "请重新确认以生成新的最终交付版本。")
            note = st.text_input("交付说明（可选）", key=f"fd_reapprove_note_{job_id}")
            if st.button("重新确认并冻结最终交付", key=f"fd_reapprove_{job_id}", width="stretch"):
                _, ok, errors = core.approve_delivery(
                    job_id, note or "重新确认最终交付", target_lang=target_lang,
                    provider=provider, model=model)
                if ok:
                    st.rerun()
                for error in errors:
                    st.error(error)
        return
    else:
        if actions:
            st.info(f"还有 {len(actions)} 个建议检查/参考项；它们不阻止最终交付。")
        note = st.text_input("最终交付说明（可选）", key=f"fd_final_note_{job_id}")
        if st.button("确认进入最终交付", key=f"fd_final_{job_id}", width="stretch"):
            _, ok, errors = core.approve_delivery(
                job_id, note or "人工确认交付", target_lang=target_lang,
                provider=provider, model=model)
            if ok:
                st.rerun()
            for error in errors:
                st.error(error)


# ================= 可视化辅助（证据链流程 / 术语状态） =================
def _chain_flow(stages):
    """横向流程卡片。"""
    boxes = []
    for i, (label, value, sub, color) in enumerate(stages):
        boxes.append(
            f'<div style="flex:1 1 130px;min-width:110px;padding:8px 12px;'
            f'border:1px solid {color}44;border-left:4px solid {color};'
            f'border-radius:8px;text-align:center;background:{color}10;">'
            f'<div style="font-size:12px;color:{color};font-weight:600;">{label}</div>'
            f'<div style="font-size:20px;font-weight:700;margin-top:1px;">{value}</div>'
            + (f'<div style="font-size:11px;opacity:.75;">{sub}</div>' if sub else "")
            + "</div>")
        if i < len(stages) - 1:
            boxes.append('<div style="align-self:center;color:#94a3b8;padding:0 2px;">→</div>')
    return ('<div style="display:flex;align-items:stretch;gap:2px;flex-wrap:wrap;'
            'margin:2px 0 8px;">' + "".join(boxes) + "</div>")


def _glossary_status_chips(entries):
    counts = {}
    for entry in entries:
        status = str(entry.get("status") or "provisional")
        counts[status] = counts.get(status, 0) + 1
    conflicts = sum(1 for entry in entries if _conflict(entry, entries))
    meta = [("候选", "candidate", "#64748b"), ("建议", "provisional", "#d97706"),
            ("已锁定", "locked", "#16a34a"), ("已拒绝", "rejected", "#dc2626")]
    chips = []
    for label, status, color in meta:
        chips.append(f'<span style="display:inline-block;padding:2px 12px;margin:0 6px 4px 0;'
                     f'border-radius:999px;border:1px solid {color};color:{color};'
                     f'font-size:13px;font-weight:600;">{label} {counts.get(status, 0)}</span>')
    conflict_label = f"冲突 {conflicts}" if conflicts else "无冲突"
    chips.append(f'<span style="display:inline-block;padding:2px 12px;border-radius:999px;'
                 f'border:1px solid #94a3b8;color:#64748b;font-size:13px;">{conflict_label}</span>')
    return '<div>' + "".join(chips) + "</div>"


def _merge_edited_entries(entries, edited_rows):
    """把编辑器可见行的修改合并回完整术语表。"""
    edited_by_id = {}
    new_rows = []
    for entry in edited_rows:
        entry_id = entry.get("id")
        if entry_id:
            edited_by_id[str(entry_id)] = entry
        else:
            new_rows.append(entry)
    merged = [edited_by_id.get(str(entry.get("id")), entry) for entry in entries]
    merged.extend(new_rows)
    return merged


# ================= Task workspace =================
def _workspace_review_contexts(state):
    return _workbench_view.review_workbench_view(state)["queue_items"]


def _review_workbench(state):
    return _workbench_view.review_workbench_view(state)


def _ai_configuration_view(review_required=True):
    return _workspace_view.ai_configuration_view(
        ai_provider, ai_model, api_key,
        st.session_state.get("provider_connection_status", "unverified"),
        reviewer_mode=reviewer_mode,
        reviewer_provider=reviewer_provider,
        reviewer_model=reviewer_model,
        reviewer_api_key=reviewer_api_key,
        reviewer_connection_status=st.session_state.get(
            "reviewer_connection_status", "unverified"),
        review_required=review_required,
    )


def _workspace_projection(state, job_id="", overview=None):
    if overview is None and job_id:
        overview = _task_overview_state(job_id, state)
    delivery_state, delivery_tone = _workspace_delivery_state(
        job_id, state, overview) if job_id else (None, "neutral")
    academic = state.get("academic_state") or {}
    report_stale = any(
        _finalization._artifact_status_value(academic, name)
        in {"stale", "missing", "failed"}
        for name in ("report", "final_docx_validation", "libreoffice_render")
    )
    if job_id:
        report_stale = report_stale or core.dependency_impact_view(
            job_id, state).get("status") == "stale"
    return _workspace_view.project_workspace_state(
        state, delivery_state=delivery_state, delivery_tone=delivery_tone,
        delivery_ready=bool(overview and overview.get("delivery_ready")),
        report_stale=report_stale,
    )


def resolve_review_runtime():
    """Resolve the configured role that owns semantic review calls."""
    return _model_roles.resolve_review_runtime(
        reviewer_mode,
        {"provider": ai_provider, "model": ai_model, "api_key": api_key,
         "base_url": api_base},
        {"provider": reviewer_provider, "model": reviewer_model,
         "api_key": reviewer_api_key, "base_url": reviewer_base_url},
    )


def _review_runtime_ready(runtime):
    return bool(runtime.get("provider") and runtime.get("model")
                and runtime.get("api_key"))


def _review_runtime_missing_message():
    return ("需要先完成审校模型配置" if reviewer_mode == "separate"
            else "需要先完成 AI 引擎配置")


def _run_review_with_runtime(job_id, indexes, runtime, target_lang, style_rules):
    kwargs = {"style_rules": style_rules}
    if runtime.get("base_url"):
        kwargs["base_url"] = runtime["base_url"]
    return core.review_translation_segments(
        job_id, indexes, runtime["provider"], runtime["api_key"],
        runtime["model"], target_lang, **kwargs)


def _set_workspace_flash(message, tone="success"):
    st.session_state["workspace_flash"] = {
        "message": str(message or ""), "tone": tone,
    }


def _render_workspace_flash():
    flash = st.session_state.pop("workspace_flash", None)
    if not isinstance(flash, dict) or not flash.get("message"):
        return
    renderer = {
        "error": st.error, "warning": st.warning,
        "info": st.info, "success": st.success,
    }.get(flash.get("tone"), st.success)
    renderer(flash["message"])


def _select_review_item(item):
    st.session_state["selected_review_item_id"] = item.get("id") if item else None
    st.session_state["selected_finding_id"] = item.get("finding_id") if item else None


def _selected_review_item(view, items=None):
    candidates = items if items is not None else view.get("queue_items") or []
    selected_id = st.session_state.get("selected_review_item_id")
    if not selected_id and st.session_state.get("selected_finding_id"):
        selected_finding_id = str(st.session_state["selected_finding_id"])
        selected_id = next((item.get("id") for item in candidates
                            if item.get("finding_id") == selected_finding_id), None)
    selected = _workbench_view.select_queue_item(
        candidates, selected_id,
    )
    _select_review_item(selected)
    return selected


def _select_next_review_item(state, completed_item):
    view = _review_workbench(state)
    next_id = _workbench_view.next_queue_item_id(
        view["queue_items"], completed_item.get("id"),
        completed_item.get("segment_id"),
    )
    selected = _workbench_view.select_queue_item(view["queue_items"], next_id)
    _select_review_item(selected)
    return selected


def _workspace_status_badge(label, tone="neutral"):
    return f'<span class="tp-status-badge is-{tone}"><span class="tp-status-dot is-{tone}"></span>{escape(label)}</span>'


def _workspace_findings_counts(state):
    contexts = _workspace_review_contexts(state)
    return contexts, {
        severity: sum(1 for item in contexts if item.get("severity") == severity)
        for severity in _delivery.SEVERITY_LABELS
    }


def _workspace_compliance_view(job_id, state):
    """Return the anonymous default-profile checks for this task."""
    return core.compliance_profile_view(job_id, state)


def _workspace_structural_qa(job_id, state):
    """Expose a stale DOCX check as a distinct user-facing state."""
    qa = _finalization.normalize_final_qa(state.get("final_qa"))
    final_docx = core.load_academic_artifact(job_id, "final_docx_validation") or {}
    structural = ("PASS" if final_docx.get("status") in {"pass", "pass_with_warnings"}
                  else "FAIL" if final_docx.get("status") == "fail"
                  else qa.get("structural_qa", "NOT_RUN"))
    artifact_status = _finalization._artifact_status_value(
        state.get("academic_state") or {}, "final_docx_validation")
    if artifact_status in {"stale", "missing"}:
        return "STALE"
    if artifact_status == "failed":
        return "FAIL"
    return structural


def _task_overview_facts(job_id, state):
    """Collect the job-scoped facts the canonical overview needs.

    Read-only: every call is a `*_view`/`status`/`gate` projection that already
    tolerates a missing job directory.  This is the only place the workspace
    reads delivery/compliance/QA facts for status purposes, so the canonical
    derivation sees one consistent snapshot per rerun.
    """
    state = state if isinstance(state, dict) else {}
    snapshot = core.delivery_snapshot_status(job_id, state) if job_id else {}
    latest = snapshot.get("latest") or {}
    impact = core.dependency_impact_view(job_id, state) if job_id else {}
    compliance = _workspace_compliance_view(job_id, state) if job_id else {}
    case_gate = _finalization.case_review_gate(
        state,
        core.load_academic_artifact(job_id, "selected_cases") if job_id else None)
    runtime = core.build_job_runtime_view(job_id, state) if job_id else {}
    academic = state.get("academic_state") or {}
    return {
        "job_id": job_id,
        "runtime_status": runtime.get("runtime_status"),
        "runtime_label": runtime.get("headline_status") or "",
        "snapshot_current": bool(snapshot.get("current")),
        "snapshot_diverged": bool(snapshot.get("diverged")),
        "snapshot_version": latest.get("snapshot_version"),
        "dependency_impact_stale": impact.get("status") == "stale",
        "compliance": {"status": compliance.get("status") or "",
                       "counts": dict(compliance.get("counts") or {})},
        "case_gate": {"status": case_gate.get("status") or "",
                      "required_count": case_gate.get("required_count") or 0,
                      "blocked_count": case_gate.get("blocked_count") or 0},
        "artifact_status": {
            name: _finalization._artifact_status_value(academic, name)
            for name in ("report", "final_docx_validation", "libreoffice_render")
        },
        "structural_qa": _workspace_structural_qa(job_id, state) if job_id else None,
        "qa": _finalization.normalize_final_qa(state.get("final_qa")),
    }


def _task_overview_state(job_id, state):
    """The single canonical task-overview derivation used by the workspace.

    Header, sidebar, hero, cards and pipeline all render from this object; no
    surface may re-derive its own status.
    """
    state = state if isinstance(state, dict) else {}
    return _task_overview.derive_task_overview_state(
        state, facts=_task_overview_facts(job_id, state))


def _workspace_delivery_state(job_id, state, overview=None):
    """Human-facing delivery label, derived only from the canonical overview.

    The wording is the canonical lifecycle vocabulary: ``READY_FOR_DELIVERY_PREP``
    means "可以准备交付" (start preparing), never "可以冻结交付" / "Ready for
    delivery" — that claim belongs to ``DELIVERY_READY`` alone.
    """
    overview = overview or _task_overview_state(job_id, state)
    lifecycle = overview.get("lifecycle")
    version = overview.get("snapshot_version")
    if lifecycle == _task_overview.DELIVERED:
        return ((f"已冻结交付 v{version}" if version is not None else "已冻结交付"),
                "success")
    if overview.get("reason") == "outdated_delivery":
        return ((f"工作版本已偏离冻结交付 v{version}" if version is not None
                 else "工作版本已偏离冻结交付"), "warning")
    tone = {
        _task_overview.GREEN: "success",
        _task_overview.BLUE: "info",
        _task_overview.AMBER: "warning",
        _task_overview.RED: "danger",
        _task_overview.GRAY: "neutral",
    }.get(overview.get("tone"), "warning")
    return (overview.get("label")
            or _task_overview.LIFECYCLE_LABELS[_task_overview.DRAFT]), tone


def _workspace_hard_gate_reasons(job_id, state):
    """Return delivery gates that cannot be waived as ordinary review risk."""
    impact = core.dependency_impact_view(job_id, state) if job_id else {}
    compliance = _workspace_compliance_view(job_id, state) if job_id else {}
    compliance_counts = compliance.get("counts") or {}
    qa = _finalization.normalize_final_qa(state.get("final_qa"))
    finalization_qa_required = bool(state.get("report_enabled"))
    academic = state.get("academic_state") or {}
    report_ready = _delivery.report_ready(state)
    report_stale = _finalization._artifact_status_value(academic, "report") in {
        "stale", "missing", "failed"}
    final_export_stale = _finalization._artifact_status_value(
        academic, "final_docx_validation") in {"stale", "missing", "failed"}
    render_stale = _finalization._artifact_status_value(
        academic, "libreoffice_render") in {"stale", "missing", "failed"}
    structural = _workspace_structural_qa(job_id, state) if job_id else qa.get("structural_qa")
    case_gate = _finalization.case_review_gate(
        state, core.load_academic_artifact(job_id, "selected_cases") if job_id else None)
    translation_truth_gate_pass = (bool(state.get("p2_done")) and
                                   (state.get("delivery_validation") or {}).get("blocking") is not True)
    reasons = []
    review_view = _review_workbench(state)
    if not review_view["readiness"]["ready"] \
            and not review_view["risk_acceptance"]["available"]:
        reasons.append("翻译审校尚未完成")
    if not translation_truth_gate_pass:
        reasons.append("当前译文交付门禁")
    if impact.get("status") == "stale":
        reasons.append("受影响产物需要重建")
    if finalization_qa_required and not report_ready:
        reasons.append("报告尚未通过交付门禁")
    if finalization_qa_required and (report_stale or final_export_stale or render_stale):
        reasons.append("交付产物仍是旧版本")
    if case_gate.get("status") == "blocked":
        reasons.append("案例来源或终审条件未满足")
    if finalization_qa_required and (compliance_counts.get("fail")
                                     or compliance_counts.get("manual_review")
                                     or compliance_counts.get("not_checked")):
        reasons.append("合规门禁尚未完成")
    if finalization_qa_required and structural != "PASS":
        reasons.append("DOCX 结构检查尚未通过")
    if finalization_qa_required and qa.get("libreoffice_render") != "PASS":
        reasons.append("页面渲染尚未通过")
    if finalization_qa_required and qa.get("author_visual_review") != "CONFIRMED":
        reasons.append("作者视觉复核尚未确认")
    if finalization_qa_required and qa.get("word_final_review") != "CONFIRMED":
        reasons.append("Word 最终复核尚未确认")
    return list(dict.fromkeys(reasons))


def _workspace_impact_change_label(impact):
    indexes = impact.get("changed_segment_indexes") or []
    if len(indexes) == 1:
        try:
            return f"第 {int(indexes[0]) + 1} 段已编辑"
        except (TypeError, ValueError):
            pass
    if indexes:
        return f"{len(indexes)} 个段落已编辑"
    return "下游内容发生变化"


def _workspace_impact_reason(impact):
    reason = str(impact.get("reason") or "")
    if "CURRENT_TRANSLATION" in reason or "工作译文" in reason:
        return "工作译文发生变化，相关案例与报告产物需要更新。"
    if reason:
        return reason.replace("stale", "需要更新")
    return "相关下游内容需要更新。"


def _workspace_impact_label(item):
    labels = {
        "literature_sources": "文献来源",
        "literature_evidence": "文献证据",
        "literature_claims": "文献主张",
        "literature_support_review": "文献支持复核",
        "human_evidence": "人工证据",
        "human_evidence_needs": "人工证据需求",
        "human_evidence_questions": "人工证据问题",
        "final_contrast_portfolio": "案例对照组合",
        "legacy_inventory": "历史资料清单",
        "legacy_recovery": "历史资料恢复",
        "legacy_recovery_report": "历史资料恢复报告",
        "quality_repair_history": "质量修复记录",
        "repair_history": "修复记录",
    }
    raw_id = str(item.get("id") or "")
    raw_label = str(item.get("label") or "")
    if raw_label and raw_label != raw_id:
        return raw_label
    mapped = labels.get(raw_id) or _finalization.artifact_label(raw_id)
    return mapped if mapped != raw_id else "相关产物"


def _workspace_impact_action(item):
    action = item.get("action")
    if action:
        return _finalization.execution_action_label(action)
    return {
        "stale": "需要重建",
        "missing": "需要生成",
        "failed": "检查失败",
        "valid": "已同步",
        "reusable": "可复用",
    }.get(str(item.get("status") or ""), "需要确认")


def _render_workspace_impact_expander(impact):
    affected = impact.get("affected") or []
    reusable = impact.get("reusable") or []
    with st.expander("查看影响", expanded=False):
        st.markdown('<div class="tp-impact-chain">'
                    f'<div class="tp-impact-chain-row"><i>1</i><strong>发生变化</strong>'
                    f'<span>{escape(_workspace_impact_change_label(impact))}</span></div>'
                    f'<div class="tp-impact-chain-row"><i>2</i><strong>需要更新</strong>'
                    f'<span>{len(affected)} 项下游产物：{escape("、".join(_workspace_impact_label(item) + " · " + _workspace_impact_action(item) for item in affected) or "相关学术下游")}</span></div>'
                    f'<div class="tp-impact-chain-row"><i>3</i><strong>可以复用</strong>'
                    f'<span>{len(reusable)} 个未受影响单元/资产；案例、写作单元和支持资料保留。</span></div>'
                    '</div>', unsafe_allow_html=True)


def _workspace_case_views(job_id, state):
    selected = core.load_academic_artifact(job_id, "selected_cases") or {}
    project_evidence = core.load_academic_artifact(job_id, "evidence") or {}
    argument_plan = core.load_academic_artifact(job_id, "argument_plan") or {}
    case_analysis_plans = core.load_academic_artifact(
        job_id, "case_analysis_plans") or {}
    outline = core.load_academic_artifact(job_id, "outline") or {}
    literature = core.load_academic_artifact(job_id, "literature_sources") or {}
    cases = selected.get("cases") or []
    evidence_segments = ((project_evidence.get("project_evidence") or {}).get("segments")
                         or [])
    source_records = {str(item.get("source_id")): item
                      for item in literature.get("sources") or []
                      if isinstance(item, dict) and item.get("source_id")}
    glossary = [item for item in state.get("glossary") or []
                if isinstance(item, dict)]
    findings = [item for item in state.get("findings") or []
                if isinstance(item, dict)]
    plan_index = {
        str(item.get("case_id")): item
        for item in case_analysis_plans.get("plans") or [] if item.get("case_id")
    }
    human_by_case = {}
    for entry in state.get("human_evidence") or []:
        human_by_case.setdefault(str(entry.get("case_id")), []).append(entry)
    views = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        view = _finalization.case_review_view(case, state, job_id)
        case_id = str(view.get("case_id") or "")
        segment_index = view.get("segment_index")
        segment_id = str(view.get("segment_id") or "")
        evidence_segment = next((item for item in evidence_segments
                                 if str(item.get("segment_id") or "") == segment_id
                                 or item.get("segment_index") == segment_index), {})
        process = evidence_segment.get("process_evidence") or {}
        related_terms = list(process.get("terminology_decisions") or [])
        if not related_terms:
            haystack = f'{view.get("source_text") or ""}\n{view.get("current_text") or ""}'.casefold()
            related_terms = [item for item in glossary
                             if str(item.get("source") or "").casefold() in haystack]
        case_findings = [item for item in findings
                         if item.get("segment_index") == segment_index]
        for item in process.get("findings") or []:
            if item not in case_findings:
                case_findings.append(item)
        related_claims = []
        for claim in argument_plan.get("claims") or []:
            if (case_id in {str(item) for item in claim.get("core_case_ids") or []}
                    or case_id in {str(item) for item in claim.get("supports_cases") or []}
                    or segment_id in {str(item) for item in claim.get("project_evidence") or []}):
                related_claims.append(claim)
        literature_ids = set()
        for claim in related_claims:
            for key in ("literature_evidence", "literature_claims", "literature_sources"):
                literature_ids.update(str(item) for item in claim.get(key) or [])
        commentary = []
        for label, value in (
                ("针对问题", view.get("targeted_issue")),
                ("选择理由", view.get("selection_rationale")),
                ("差异说明", view.get("contrast_rationale")),
                ("分析理由", (view.get("synthetic_evidence") or {}).get("academic_analysis_reason")),
                ("分析种子", view.get("legacy_analysis_seed")),
                ("限制", "；".join(str(item) for item in view.get("limitations") or [])),
        ):
            if value:
                commentary.append({"label": label, "value": value})
        target_subsection = str(view.get("target_subsection") or "").strip()
        section_title = ""
        for section in outline.get("sections") or []:
            section_id = str(section.get("section_id") or "")
            if section_id == str(view.get("section_id") or "") or (
                    target_subsection and target_subsection.startswith(section_id + ".")):
                section_title = str(section.get("title") or "")
                break
        context = view.get("focus") or {}
        before = str(context.get("context_before") or "").strip()
        after = str(context.get("context_after") or "").strip()
        if not before and isinstance(segment_index, int) and segment_index > 0:
            before = str((state.get("pairs") or [])[segment_index - 1].get("target") or "")
        if not after and isinstance(segment_index, int) and segment_index + 1 < len(state.get("pairs") or []):
            after = str((state.get("pairs") or [])[segment_index + 1].get("target") or "")
        view.update({
            "case_plan": plan_index.get(case_id) or {},
            "human_evidence": human_by_case.get(case_id) or [],
            "related_terms": related_terms[:12],
            "case_findings": case_findings[:12],
            "related_claims": related_claims[:8],
            "literature_evidence": [source_records[item] for item in sorted(literature_ids)
                                     if item in source_records],
            "analytical_commentary": commentary[:8],
            "target_subsection": target_subsection,
            "section_title": section_title,
            "context_before": before,
            "context_after": after,
        })
        views.append(view)
    return views


def _workspace_activity(job_id, state):
    try:
        saved_at = _workspace_saved_label(job_id, state)
    except Exception:
        saved_at = "最近"
    rows = []
    if state.get("p3_done"):
        rows.append((saved_at, "生成实践报告"))
    if state.get("findings") is not None and state.get("p2_done"):
        rows.append((saved_at, "完成审校"))
    if state.get("auto_terms"):
        rows.append((saved_at, "完成术语抽取"))
    if state.get("p2_done"):
        rows.append((saved_at, "完成翻译"))
    elif state.get("p1_done"):
        rows.append((saved_at, "完成文档解析"))
    return rows[:4]


def _runtime_age(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    except (TypeError, ValueError):
        return None


def _runtime_clock(value):
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%H:%M:%S")
    except (TypeError, ValueError):
        return str(value)[:19]


def _runtime_duration(seconds):
    seconds = max(0, int(seconds or 0))
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes:02d}分"
    if minutes:
        return f"{minutes}分{remainder:02d}秒"
    return f"{remainder}秒"


def _render_runtime_panel(job_id, state):
    view = core.build_job_runtime_view(job_id, state)
    runtime = view["runtime"]
    status = view["status"]
    if status == "idle":
        return
    label = view["status_label"]
    tone = "danger" if status in {"failed", "interrupted"} else \
        "warning" if status in {"stalled", "cancelling", "waiting_manual"} else "neutral"
    headline, detail = view["headline"], view["detail"]
    heartbeat_age = _runtime_age(runtime.get("last_heartbeat_at"))
    tone_class = "is-warning" if tone == "warning" else "is-danger" if tone == "danger" else ""
    completed, total = view["progress_completed"], view["progress_total"]
    progress_html = ""
    if total:
        progress_pct = round(min(1.0, completed / total) * 100)
        progress_html = (
            f'<div class="tp-runtime-progress-head"><span>报告工作流</span>'
            f'<strong>{completed} / {total}</strong></div>'
            f'<div class="tp-runtime-bar" aria-label="报告工作流 {completed} / {total}">'
            f'<i style="width:{progress_pct}%"></i></div>')
    timing_html = ""
    if status in {"running", "waiting_external", "cancelling"}:
        timing_html = (
            f'<div class="tp-runtime-meta"><span>本步骤已运行 '
            f'{_runtime_duration(_runtime_age(runtime.get("operation_started_at")) or 0)}</span>'
            f'<span>最后运行信号 {_runtime_duration(heartbeat_age or 0)}前</span></div>')
    st.markdown(
        '<div class="tp-runtime-panel">'
        f'<div class="tp-runtime-kicker">{escape(view["surface_label"])}</div>'
        f'<div class="tp-runtime-phase {tone_class}"><span class="dot"></span>'
        f'<span>{escape(label)}</span></div>'
        f'<div class="tp-runtime-head"><div><h3>{escape(headline)}</h3>'
        f'<p>{escape(detail)}</p></div></div>'
        f'{timing_html}{progress_html}'
        '</div>', unsafe_allow_html=True)
    recent_events = view["user_events"]
    if recent_events:
        st.caption("最近活动")
        for event in reversed(recent_events):
            st.markdown(
                f'<div class="tp-runtime-event"><time>{escape(_runtime_clock(event.get("timestamp") or event.get("at")))}</time>'
                f'<span>{escape(event.get("message") or "")}</span></div>',
                unsafe_allow_html=True)
    action_col, detail_col = st.columns([1, 1.2], gap="small")
    with action_col:
        if status in {"resume_requested", "queued", "starting"}:
            st.button("正在恢复…", key=f"runtime_resuming_{job_id}",
                      disabled=True, width="stretch")
        elif status in {"running", "waiting_external", "cancelling"} and st.button(
                "取消任务", key=f"runtime_cancel_{job_id}", width="stretch"):
            core.request_job_cancel(job_id)
            st.rerun()
        elif status in {"interrupted", "idle_incomplete", "cancelled"}:
            if st.button("继续处理", type="primary", key=f"runtime_resume_{job_id}",
                         width="stretch"):
                _resume_job(job_id, state)
                st.rerun()
        elif status == "stalled" and core.is_job_worker_alive(job_id):
            if st.button("放弃当前运行", type="primary", key=f"runtime_abandon_{job_id}",
                         width="stretch"):
                core.request_job_cancel(job_id)
                st.rerun()
        elif status in {"failed", "stalled"}:
            if st.button("重试当前步骤", type="primary", key=f"runtime_retry_{job_id}",
                         width="stretch"):
                core.retry_job_step(job_id)
                _resume_job(job_id, core.load_job_state(job_id) or state)
                st.rerun()
    with detail_col:
        with st.expander("运行详情", expanded=False):
            st.caption(f"worker：{'运行中' if core.is_job_worker_alive(job_id) else '未连接'}")
            worker = runtime.get("worker") or {}
            st.caption(f"worker id：{worker.get('worker_id') or '—'} · "
                       f"PID：{worker.get('owner_pid') or '—'}")
            st.caption(f"lease：{worker.get('lease_expires_at') or '—'}")
            st.caption(f"runtime status：{status} · phase：{runtime.get('phase') or '—'}")
            st.caption(f"stage：{runtime.get('stage_id') or runtime.get('stage') or '—'} · "
                       f"operation：{runtime.get('operation_id') or runtime.get('operation') or '—'}")
            st.caption(f"checkpoint：{view['progress_completed']} / "
                       f"{view['progress_total'] or '—'}")
            st.caption(f"最后进展：{_runtime_clock(runtime.get('last_progress_at'))}")
            st.caption(f"最后心跳：{_runtime_clock(runtime.get('last_heartbeat_at'))}")
            if isinstance(runtime.get("error"), dict):
                error = runtime["error"]
                st.caption(f"失败类型：{error.get('type') or '—'} · "
                           f"技术日志：{error.get('technical_log') or '—'}")
            if runtime.get("last_event"):
                st.caption(f"最后事件：{runtime['last_event']}")
            st.caption("技术日志")
            for event in reversed(core.read_runtime_events(
                    job_id, 12, visibility="technical")):
                st.markdown(
                    f'<div class="tp-runtime-event"><time>{escape(_runtime_clock(event.get("timestamp") or event.get("at")))}</time>'
                    f'<span>{escape(event.get("event") or "")} · '
                    f'{escape(event.get("message") or "")}</span></div>',
                    unsafe_allow_html=True)


def _workspace_saved_label(job_id, state):
    if not job_id:
        return "最近"
    value = (core.recovery_summary(job_id, state) or {}).get("last_saved_at")
    if not value:
        return "最近"
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})[ T](\d{1,2}):(\d{2})", str(value))
    if match:
        return f"{int(match.group(2))} 月 {int(match.group(3))} 日 {int(match.group(4)):02d}:{match.group(5)}"
    return _format_saved_at(value)[:16]


def _workspace_project_title(filename):
    stem = Path(str(filename or "")).stem.strip()
    candidate = re.split(r"提取自", stem, maxsplit=1)[-1].strip()
    candidate = re.sub(r"^\d+\s*", "", candidate)
    candidate = re.sub(r"\s*\([^)]*\)\s*$", "", candidate).strip()
    candidate = re.sub(r"\s+", " ", candidate)
    if not candidate:
        return stem or "未命名项目"
    words = candidate.split(" ")
    small_words = {"a", "an", "and", "as", "at", "by", "for", "in",
                   "of", "on", "or", "the", "to", "via"}
    if len(words) > 1:
        words = [words[0]] + [word.lower() if word.lower() in small_words else word
                              for word in words[1:]]
    return " ".join(words)


def _workspace_document_title(filename):
    """从文件名里取出"用户认得出这本书"的那一段标题。

    顶栏原来同时显示 `Part 3 提取The Sensorium...` 和文件名整理出的标题，
    两者互为噪声。这里统一成"标题 + 章节"，文件名不再第二次出现。
    """
    stem = Path(str(filename or "")).stem.strip()
    candidate = re.split(r"提取自", stem, maxsplit=1)[-1].strip()
    candidate = re.sub(r"\s*\([^)]*\)\s*$", "", candidate).strip()
    candidate = re.sub(r"\s+", " ", candidate)
    return candidate or stem or "未命名项目"


def _workspace_title_parts(filename):
    """返回 (书名, 章节标签)。书名去掉 `Part N` 前缀，章节单独成行。"""
    title = _workspace_document_title(filename)
    part_match = re.search(r"\bPart\s*([A-Za-z0-9IVX]+)", title, re.IGNORECASE)
    part_label = f"Part {part_match.group(1)}" if part_match else ""
    if part_match:
        title = title[part_match.end():].strip(" -–—:·")
    title = re.sub(r"^\d+\s*", "", title).strip()
    if not title:
        title = _workspace_project_title(filename)
    return title, part_label


def _render_workspace_topbar(job_id, state, overview=None):
    filename = str(state.get("filename") or "未命名项目")
    title, part_label = _workspace_title_parts(filename)
    term_count = len(state.get("glossary") or state.get("auto_terms") or [])
    try:
        saved_at = _workspace_saved_label(job_id, state)
    except Exception:
        saved_at = "最近"
    progress = _planner.workspace_progress(state, job_id=job_id)
    translation = progress["translation"]
    issues = progress["issues"]
    # 顶栏只渲染 canonical 状态：不再自己推导"能不能交付"。
    overview = overview or _task_overview_state(job_id, state)
    verdict_tone = _task_overview.surface_token("verdict", overview["tone"])
    # 顶栏只留两件事：这是哪个文档 + 现在能不能交付。
    # 这里刻意不再放 Translation 进度条/百分比：翻译页正文上方已经有
    # Translation / Terminology / Review / Issues 四维状态，顶栏再来一条蓝色 translate
    # 进度条，等于在视觉上继续宣称"翻译完成度是主要完成指标"，和四维进度的理念打架。
    facts = [f'<b>{translation["done"]:,} / {translation["total"]:,}</b> 段',
             f'<b>{term_count:,}</b> 术语',
             f'最近保存 {escape(saved_at)}']
    if issues["count"]:
        facts.append(f'<b>{issues["count"]:,}</b> 项发现')
    facts_html = ' · '.join(facts)
    with st.container(key="workspace_exit_actions"):
        back_col, home_col, _ = st.columns([1, 0.9, 9], gap="small")
        with back_col:
            if st.button("任务列表", icon=":material/arrow_back:",
                         key=f"workspace_back_{job_id}", width="stretch"):
                st.session_state.update(app_view="history", workspace_mode=False)
                st.rerun()
        with home_col:
            if st.button("主页", icon=":material/home:",
                         key=f"workspace_home_{job_id}", width="stretch"):
                st.session_state.update(app_view="new", workspace_mode=False, task_step=1)
                st.rerun()
    title_html = escape(title)
    if part_label:
        title_html = (f'<span class="tp-workspace-part">{escape(part_label)}</span>'
                      f'{title_html}')
    st.markdown(
        '<div class="tp-workspace-shell"></div>'
        '<div class="tp-workspace-topbar">'
        f'<div><h1>{title_html}</h1>'
        f'<div class="tp-workspace-meta">{facts_html}</div></div>'
        '<div class="tp-workspace-verdict '
        f'is-{escape(verdict_tone)}" '
        f'title="{escape(overview["detail"])}">{escape(overview["label"])}</div>'
        '</div>', unsafe_allow_html=True)


def _render_workspace_nav(section, state, job_id="", overview=None):
    overview = overview or _task_overview_state(job_id, state)
    nav_tone = _task_overview.surface_token("nav", overview["tone"])
    # 侧栏顶部只挂一套 canonical 状态：和顶栏、Hero 同色同语义。
    # 状态徽标用 badge token（红=blocking），导航项用 nav token（只区分"要不要处理"）；
    # 两者都来自同一份 SURFACE_TONES 映射，不在这里各写一套颜色。
    chip_tone = _task_overview.surface_token("badge", overview["tone"])
    st.markdown('<div class="tp-workspace-nav-title">项目导航</div>'
                f'<div class="tp-nav-canonical is-{escape(chip_tone)}" '
                f'title="{escape(overview["detail"])}">'
                f'<i></i>{escape(overview["label"])}</div>',
                unsafe_allow_html=True)
    projection = _workspace_projection(state, job_id, overview=overview)
    review_view = projection["review"]
    review_nav = review_view["nav"]
    # "不适用"不是一种状态文字，而是一种视觉降级：审校未启用的任务不该在侧栏
    # 一直挂着一行字占注意力（原来的 tone 是 neutral，和"参考"混在一起）。
    if str((review_view.get("readiness") or {}).get("status") or "") == "not_required":
        review_nav = {**review_nav, "tone": "inapplicable"}
    case_views = _workspace_case_views(job_id, state) if job_id else []
    case_pending = sum(1 for item in case_views
                       if item.get("review_status") == "unreviewed"
                       or (item.get("case_origin") == _case_provenance.SYNTHETIC_BASELINE
                           and item.get("baseline_status") == "rejected"))
    compliance = _workspace_compliance_view(job_id, state) if job_id else {}
    qa = _finalization.normalize_final_qa(state.get("final_qa"))
    terms_required = bool(state.get("quality_mode") or state.get("glossary")
                          or state.get("glossary_frozen") or state.get("auto_terms"))
    terms_done = not terms_required or bool(
        state.get("glossary_frozen") or state.get("quality_bypass")
        or (state.get("auto_terms") and not state.get("quality_mode")))
    compliance_counts = compliance.get("counts") or {}
    qa_required = bool(state.get("report_enabled"))
    qa_attention_count = 0
    if qa_required:
        qa_attention_count = sum(int(compliance_counts.get(key, 0) or 0)
                                 for key in ("fail", "manual_review", "not_checked"))
        structural = _workspace_structural_qa(job_id, state) if job_id else qa.get("structural_qa")
        qa_attention_count += int(structural != "PASS")
        qa_attention_count += int(qa.get("libreoffice_render") != "PASS")
        qa_attention_count += int(qa.get("author_visual_review") != "CONFIRMED")
        qa_attention_count += int(qa.get("word_final_review") != "CONFIRMED")
    # 交付导航项只表达"交付阶段现在是否需要你动手"，颜色取自 canonical tone，
    # 不再自己算一套 delivery readiness。
    if overview["lifecycle"] in {_task_overview.DELIVERED,
                                 _task_overview.DELIVERY_READY,
                                 _task_overview.READY_FOR_DELIVERY_PREP}:
        delivery_nav = ("", nav_tone, overview["detail"])
    elif overview["lifecycle"] in {_task_overview.DRAFT, _task_overview.TRANSLATING}:
        delivery_nav = ("", nav_tone, "翻译完成后进入交付")
    elif overview["reason"] == "outdated_delivery":
        delivery_nav = ("待更新 1", nav_tone, overview["detail"])
    else:
        delivery_nav = ("待处理 1", nav_tone, overview["detail"])
    nav_meta = {
        "overview": (("", "neutral", "当前任务全貌") if section == "overview" else
                     ("", "neutral", "回到任务概览")),
        "translation": (("", "done", "翻译已完成")
                         if state.get("p2_done") and
                         projection["translated_segments"] >= projection["total_segments"]
                         else (f"{projection['translated_segments']} / {projection['total_segments']} 段",
                               "pending", "翻译尚未完成")),
        "terms": (("", "muted", "无需确认术语") if not terms_required else
                  ("", "done", "术语已冻结") if terms_done else
                  ("待确认 1", "pending", "术语仍需确认")),
        "review": ((("", "muted", "当前任务未启用独立审校")
                    if review_nav.get("tone") == "inapplicable" else
                    (review_nav["label"], review_nav["tone"], review_nav["title"]))
                   if state.get("p2_done") else ("", "muted", "翻译完成后开始审校")),
        "cases": ((f"待确认 {case_pending}", "pending", f"还有 {case_pending} 个案例未完成人工确认") if case_pending else
                  ("", "done", "案例均已完成人工确认") if case_views else
                  ("", "muted", "案例选择产物尚未生成")),
        "report": (("", "done", "研究报告稿已生成") if state.get("p3_done") else
                   ("待完成 1", "attention", "研究报告仍需完成") if state.get("report_enabled") else
                   ("", "muted", "当前任务未启用研究报告")),
        "qa": ((f"待处理 {qa_attention_count}", "attention", f"合规与最终 QA 还有 {qa_attention_count} 项需要处理")
               if qa_attention_count else
               ("", "done", "合规与最终 QA 已完成") if qa_required else
               ("", "muted", "当前任务未启用最终 QA")),
        "delivery": delivery_nav,
    }
    labels = [("overview", "概览"), ("translation", "翻译"),
              ("terms", "术语"), ("review", "审校")]
    academic = state.get("academic_state") or {}
    research_enabled = bool(state.get("report_enabled") or state.get("p3_done")
                            or case_views or academic.get("artifacts"))
    if research_enabled:
        labels.extend([("cases", "案例"), ("report", "研究报告"),
                       ("qa", "合规与 QA")])
    labels.append(("delivery", "交付"))
    # 侧栏不再用"按钮 + 状态列"的两栏结构：状态文字（例如"翻译已完成"）在 184px
    # 的侧栏里必然溢出、压到相邻行上。改成"状态决定颜色 + 图标"，标签本身保持简短。
    #
    # 这里刻意 *不用* st.button(help=...)：当前 Streamlit 版本的 help tooltip 在点击后
    # 不会消失（实测鼠标移开 5.5 秒后 stTooltipContent 仍在 DOM 里），气泡会一直盖在
    # 侧栏上。所以"不适用"这类必要语义直接写进标签，而不是塞进 tooltip。
    with st.container(key="workspace_nav"):
        for value, label in labels:
            active = value == section
            nav_status, nav_tone, nav_title = nav_meta[value]
            icon = (":material/radio_button_checked:" if active
                    else ":material/check_circle:" if nav_tone == "done"
                    else ":material/error_outline:" if nav_tone == "attention"
                    else ":material/schedule:" if nav_tone == "pending"
                    else ":material/info:")
            if nav_tone == "muted":
                # 不适用/未启用：不给图标，整行压暗（CSS 命中 _muted 后缀），
                # 语义写在标签里而不是 tooltip 里。
                icon = ":material/radio_button_checked:" if active else None
                if "不适用" not in label:
                    label = f"{label} · 不适用"
            with st.container(key=f"workspace_nav_item_{value}_{nav_tone}"):
                if st.button(label, icon=icon, key=f"workspace_nav_{value}",
                             width="stretch",
                             type="primary" if active else "secondary"):
                    st.session_state.workspace_section = value
                    st.rerun()


def _render_workspace_project_details(state):
    project = core.project_for_job(st.session_state.get("active_job_id") or "", state)
    with st.expander("项目详情", expanded=False):
        if project is not None:
            view = core.project_memory_view(project)
            st.caption(f"所属项目：{project['name']} · 项目锁定术语 "
                       f"{view['glossary_count']} 条 · 风格 {view['style_rule_count']} 条")
        else:
            st.caption(f"所属项目：{core.SYSTEM_PROJECT_NAME}"
                       "（系统工作区；本次任务不注入项目记忆）")
        st.caption(f"源文件：{state.get('filename') or '—'}")
        st.caption(f"段落：{len(state.get('paras') or []):,} · 目标语言：{state.get('target_lang') or '简体中文'}")


def _translation_pair_status(pair, state=None, index=None):
    return _translation_pair_status_label(pair, state, index)


def _translation_pair_status_label(pair, state=None, index=None):
    if state is not None and isinstance(index, int):
        projection = _workspace_projection(state)
        status = projection["segment_status"].get(index)
        if status:
            return status
    if not state or not state.get("translation_core_review_required"):
        return "已翻译" if str(pair.get("target") or "").strip() else "待翻译"
    if pair.get("human_edited"):
        return "已修改"
    if pair.get("reviewed"):
        return "已审校"
    return "待审校"


def _translation_terms_for_pair(state, pair):
    return core.translation_terms_for_pair(state, pair)


def _translation_preview(value, limit=170):
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _translation_segment_id(job_id, index, pair):
    for key in ("segment_id", "segment_uid", "seg_id"):
        if pair.get(key) is not None:
            return str(pair[key])
    # Reuse the identity already used by exported translation assets.
    return _assets.segment_id(job_id, index)


def _translation_segment_records(job_id, state):
    return [{
        "segment_id": _translation_segment_id(job_id, index, pair),
        "index": index,
        "pair": pair,
    } for index, pair in enumerate(state.get("pairs") or [])]


def _translation_selected_segment(job_id, state, visible_records=None):
    records = _translation_segment_records(job_id, state)
    by_id = {record["segment_id"]: record for record in records}
    selected_id = st.session_state.get("selected_segment_id")
    if selected_id is not None:
        selected_id = str(selected_id)
    if selected_id in by_id and (visible_records is None or
                                selected_id in {item["segment_id"] for item in visible_records}):
        st.session_state["selected_segment_id"] = selected_id
        return by_id[selected_id]
    if selected_id is None and visible_records is None:
        return None
    candidates = visible_records or records
    if not candidates:
        st.session_state["selected_segment_id"] = None
        return None
    selected = candidates[0]
    st.session_state["selected_segment_id"] = selected["segment_id"]
    return selected


def _translation_segment_findings(state, index):
    return [item for item in _review_workbench(state)["queue_items"]
            if item.get("segment_id") == index]


def _save_translation_edit(job_id, index, text):
    core.save_translation_edit(job_id, index, text)


def _restore_translation_pair(job_id, index):
    core.restore_translation_edit(job_id, index)


def _explain_translation_segment(job_id, index, state):
    if not api_key:
        return "请先配置 API Key。"
    pair = state["pairs"][index]
    terms = _translation_terms_for_pair(state, pair)
    term_text = "；".join(f"{source} → {target}" for source, target, _ in terms) or "无锁定术语"
    system = "你是严谨的翻译实践导师。用简体中文解释当前译法，聚焦语义、术语和上下文，不改写译文。"
    prompt = (f"原文：{pair.get('source', '')}\n当前译文：{pair.get('target', '')}\n"
              f"相关术语：{term_text}\n"
              "请用 2-4 句话说明当前译法的主要决策和可能的注意点。")
    try:
        return core.call_llm(ai_provider, api_key, ai_model, system, prompt, temperature=0.2)
    except Exception as exc:
        return f"解释失败：{str(exc)[:160]}"


def _pairs_of(state):
    return state.get("pairs") or []


def _segment_edit_count(state, index, pair):
    """这一段被人工改过几次。

    优先用人工动作记录（同一段多次修改都留痕）；没有记录时退化为
    `human_edited` 这个布尔事实，避免把"改过"显示成"改了 0 次"。
    """
    actions = state.get("human_actions") or []
    count = 0
    for action in actions:
        if not isinstance(action, dict):
            continue
        segments = action.get("segment_indexes") or action.get("segment_ids") or []
        if index in segments or action.get("segment_index") == index:
            count += 1
    if not count and pair.get("human_edited"):
        return 1
    return count


def _segment_term_hits(state, pair):
    """本段原文命中的项目术语数量（术语面板里的"术语匹配 n"）。"""
    return len(_translation_terms_for_pair(state, pair))


def _segment_section_label(state, index):
    """这一段属于哪个章节（Inspector 的"上下文"事实）。"""
    sections = state.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue
        start = section.get("start_segment")
        end = section.get("end_segment")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start <= index <= end:
            title = str(section.get("title") or section.get("section_id") or "").strip()
            return _translation_preview(title, 28) if title else f"§{start + 1}–{end + 1}"
    return "—"


def _segment_confidence(findings):
    """审校给出的置信度；没有独立审校时如实显示"未评审"。"""
    for item in findings:
        value = item.get("confidence")
        if isinstance(value, (int, float)):
            return ("高" if value >= 0.8 else "中" if value >= 0.55 else "低"), value
        label = str(item.get("confidence_label") or "").strip()
        if label:
            return label, None
    return "—", None


# Agent 动作：都是"给候选译文"，不是"自动改稿"。写回正文必须由人点"应用到译文"。
_AGENT_ACTIONS = (
    ("rewrite", "改写", ":material/refresh:",
     "在保持原意与信息量的前提下改写当前译文，去掉翻译腔。"),
    ("faithful", "更忠实", ":material/target:",
     "收紧当前译文，逐句对齐原文的信息与逻辑，不增不减。"),
    ("natural", "更自然", ":material/eco:",
     "让当前译文更符合目标语言的自然表达，允许调整句序。"),
    ("academic", "学术化", ":material/school:",
     "把当前译文提升为学术书面语体，术语与句式保持一致。"),
)
_AGENT_PROMPTS = {
    "rewrite": "请改写这段译文，保持信息完整，去掉翻译腔，只输出改写后的译文。",
    "faithful": "请让这段译文更忠实于原文，逐句对齐信息与逻辑，只输出修改后的译文。",
    "natural": "请让这段译文更符合简体中文的自然表达，允许调整语序，只输出修改后的译文。",
    "academic": "请把这段译文改写为学术书面语体，保持术语一致，只输出修改后的译文。",
}


def _run_agent_action(action, job_id, index, state, custom=""):
    """调用模型产出一个候选译文。返回文本，失败时返回可读的中文错误。"""
    if not api_key or not ai_model:
        return "请先完成 AI 引擎配置。"
    pair = state["pairs"][index]
    terms = _translation_terms_for_pair(state, pair)
    term_text = "；".join(f"{source} → {target}" for source, target, _ in terms) or "无锁定术语"
    neighbours = []
    if index:
        neighbours.append(f"上一段原文：{_translation_preview(_pairs_of(state)[index - 1].get('source'), 220)}")
    if index + 1 < len(_pairs_of(state)):
        neighbours.append(f"下一段原文：{_translation_preview(_pairs_of(state)[index + 1].get('source'), 220)}")
    context = "\n".join(neighbours)
    system = ("你是资深中英翻译审校。你只输出修改后的译文本身，"
              "不要解释、不要加引号、不要输出 Markdown 代码块。")
    instruction = custom.strip() or _AGENT_PROMPTS.get(action, "请改进这段译文。")
    prompt = (f"原文：\n{pair.get('source', '')}\n\n"
              f"当前译文：\n{pair.get('target', '')}\n\n"
              f"项目术语：{term_text}\n"
              f"{context}\n\n{instruction}")
    try:
        result = core.call_llm(ai_provider, api_key, ai_model, system, prompt,
                               temperature=0.3)
        return str(result or "").strip() or "模型没有返回内容，请重试。"
    except Exception as exc:
        return f"AI 动作失败：{str(exc)[:160]}"


def _render_segment_findings(pair_findings, job_id, index):
    if not pair_findings:
        return
    blocks = []
    for finding in pair_findings:
        blocks.append(
            f'<div class="tp-inspector-finding is-{escape(finding["severity"])}">'
            f'<strong>{escape(finding["title"])}</strong>'
            f'<p>{escape(finding["detail"])}</p></div>')
    st.markdown("".join(blocks), unsafe_allow_html=True)


def _render_document_agent_panel(job_id, state, overview=None):
    """没有选中段落时的 Inspector：仍然是 Agent，不是空白占位。"""
    overview = overview or _task_overview_state(job_id, state)
    findings = _planner.plan_findings(state, job_id=job_id, limit=8)
    # Inspector 也读同一份 canonical 状态：翻译页不能出现第二套交付结论。
    st.markdown(
        '<div class="tp-translation-inspector-head"><div><h3>Agent</h3>'
        f'<div class="tp-inspector-status"><strong>{escape(overview["label"])}</strong></div>'
        '</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="tp-inspector-section">'
                f'<p class="tp-inspector-preview">{escape(overview["detail"])}</p></div>',
                unsafe_allow_html=True)
    if not findings:
        st.markdown('<div class="tp-inspector-section">'
                    '<div class="tp-inspector-empty">当前没有需要处理的全文发现。</div></div>',
                    unsafe_allow_html=True)
        return
    st.markdown('<div class="tp-inspector-section"><h4>全文发现</h4>', unsafe_allow_html=True)
    for finding in findings:
        st.markdown(
            f'<div class="tp-inspector-finding is-{escape(finding["severity"])}">'
            f'<strong>{escape(finding["title"])}</strong>'
            f'<p>{escape(finding["detail"])}</p></div>', unsafe_allow_html=True)
        if finding.get("segments"):
            st.button(f"定位第 {finding['segments'][0] + 1} 段",
                      key=f"agent_goto_{job_id}_{finding['id']}",
                      width="stretch",
                      on_click=_navigate_to_segment,
                      args=(job_id, state, finding["segments"][0]))
    st.markdown('</div>', unsafe_allow_html=True)


# ---- 段落跳转：唯一入口 ----
# Agent 发现锚点、Inspector 的"定位"、问题抽屉、审校跳转都必须走这里。
# 以前每个入口各写各的（设置选中 + st.rerun() + 各自滚动），结果是
# "点 #2 → 正文变白 → 卡住"：st.pills 的选中状态在 rerun 后依然存在，
# 而 callback 里的 st.rerun() 又触发一次渲染，widget 状态反复重放形成循环。
#
# 现在的约定：
#   1. 跳转只设置状态，绝不在 callback 里 st.rerun()——Streamlit 因为 widget
#      交互本来就会 rerun；
#   2. scroll intent 消费一次就清空（`_consume_pending_scroll`），绝不留存，
#      否则之后每次 rerun 都会再跳一次；
#   3. 目标被筛选/搜索挡住时，先让筛选回到能显示它的状态（定位优先于保持筛选）。
_NAV_PENDING_SCROLL = "pending_scroll_segment_id"
_NAV_NOTICE = "_nav_notice"
_ISSUE_SEVERITY_LABELS = {"blocking": "必须处理", "actionable": "建议",
                          "informational": "参考"}
# 问题抽屉必须一次拿到**全部**发现，否则锚点会缺：planner 的 limit 是截断，
# 早先取 40 时，"每段一条术语发现"的 82 段文档里 #41 之后的段落根本没有锚点可点。
# 翻译页顶部那条 issue bar 只需要最高优先级的一条，仍然用小 limit。
_ISSUES_PANEL_LIMIT = 500


def _navigate_to_segment(job_id, state, index, *, reveal=True):
    """唯一跳转入口：选中 + 一次性滚动 +（可选）放宽筛选。

    `reveal=True`（默认，用于"从问题列表跳到正文"）：目标被筛选/搜索挡住时
    先让筛选回到能显示它的状态。
    `reveal=False`（用于上一段/下一段/网格内选段）：用户就在当前集合里移动，
    不该被改掉筛选条件。
    """
    records = _translation_segment_records(job_id, state)
    if not isinstance(index, int) or not 0 <= index < len(records):
        return False
    st.session_state["selected_segment_id"] = records[index]["segment_id"]
    st.session_state[_NAV_PENDING_SCROLL] = index
    # 跳转后恢复段落 Inspector（问题抽屉是临时视图）
    st.session_state.pop("issues_panel_open", None)
    if reveal:
        _reveal_segment(job_id, index)
    return True


def _reveal_segment(job_id, index):
    """保证目标段落处于会渲染的集合里。

    渲染集合由 status 筛选 + 关键词搜索共同决定；如果目标被挡住，
    `getElementById` 根本找不到它——那不是"滚动失败"，是目标不存在。
    这里优先保证目标可见，并把原本的搜索词暂存以便恢复。
    """
    filter_key = f"translation_filter_{job_id}"
    search_key = f"translation_search_{job_id}"
    issues_only = st.session_state.get(f"translation_filter_issue_{job_id}")
    status_filter = st.session_state.get(filter_key, "全部")
    search = str(st.session_state.get(search_key) or "")
    if status_filter != "全部":
        # 直接改写 widget state：它在本轮渲染前被清掉，所以下轮渲染会读到新值。
        st.session_state[filter_key] = "全部"
        st.session_state[_NAV_NOTICE] = f"已切换到「全部」以显示第 {index + 1} 段"
    if issues_only:
        st.session_state[f"translation_filter_issue_{job_id}"] = False
        st.session_state[_NAV_NOTICE] = f"已清除筛选以显示第 {index + 1} 段"
    if search:
        # 搜索词这里**不**恢复：恢复会让目标段落在下一次 rerun 又被藏起来，
        # 用户刚跳过去就看见它消失。"定位优先于保持筛选"——直接清空并明确告知。
        st.session_state[search_key] = ""
        st.session_state[_NAV_NOTICE] = f"已清除搜索以显示第 {index + 1} 段"


def _render_nav_notice():
    """跳转放宽了筛选条件时，明确告诉用户发生了什么。

    静默改掉用户的筛选状态比多一行提示糟糕得多。
    """
    notice = st.session_state.pop(_NAV_NOTICE, None)
    if notice:
        st.caption(f"↪ {notice}")


def _toggle_issues_panel():
    """顶部 issue bar 的「查看全部 / 返回段落」。"""
    st.session_state["issues_panel_open"] = \
        not bool(st.session_state.get("issues_panel_open"))


def _close_issues_panel():
    """问题抽屉里的「返回段落」。"""
    st.session_state.pop("issues_panel_open", None)


def _consume_pending_scroll():
    """取出并立刻清空 scroll intent。取过一次就不该再有第二次。"""
    index = st.session_state.pop(_NAV_PENDING_SCROLL, None)
    return index if isinstance(index, int) else None


def _render_scroll_trigger(index):
    if index is None:
        return
    # st.html(unsafe_allow_javascript=True) 在主文档里执行（实测可用），
    # 所以能直接查 DOM。用 requestAnimationFrame 让这一帧的 DOM 先挂完。
    #
    # 不用裸 scrollIntoView：标记 span 是 height:0 的，浏览器按它自己的盒子
    # 计算居中，实测目标行中心落在 718px、视口中心 480px——偏了 240px，
    # 而且滚完还会因为长段落上方的布局再稳定一次而继续漂。
    # 这里显式算"行中心 vs 视口中心"的差值来修正，300ms 后再纠一次。
    # 每次跳转只注入一次脚本，不存在反复滚动。
    st.html(f"""
<script>
(function () {{
  function centre() {{
    var marker = document.querySelector('[data-segment="{index}"]');
    if (!marker) return false;
    var row = marker.closest('[class*="st-key-cat_row_"]') || marker;
    var rect = row.getBoundingClientRect();
    var scroller = document.querySelector('section[data-testid="stMain"]');
    var delta = (rect.top + rect.height / 2) - window.innerHeight / 2;
    if (scroller) scroller.scrollBy({{top: delta, behavior: 'smooth'}});
    else window.scrollBy({{top: delta, behavior: 'smooth'}});
    return true;
  }}
  var tries = 0;
  function go() {{
    if (centre()) {{ window.setTimeout(centre, 300); return; }}
    if (++tries < 20) window.requestAnimationFrame(go);
  }}
  window.requestAnimationFrame(go);
}})();
</script>
""", unsafe_allow_javascript=True)


def _render_workspace_translation_context(job_id, state, overview=None):
    """右栏 = Agent Inspector。

    这里不再放第二个译文编辑器：正文只在中央网格里改。Inspector 负责回答
    "这一段现在什么状态、系统发现了什么、可以让我做什么"。
    另有 Issues 模式（问题抽屉），由顶部 issue bar 的「查看全部」切换。
    """
    review_runtime = resolve_review_runtime()
    review_required = bool(state.get("translation_core_review_required"))
    if st.session_state.get("issues_panel_open"):
        _render_issues_panel(job_id, state)
        return
    selected_segment = _translation_selected_segment(job_id, state)
    if selected_segment is None:
        _render_document_agent_panel(job_id, state, overview)
        return
    pairs = _pairs_of(state)
    index = selected_segment["index"]
    pair = selected_segment["pair"]
    selected_id = selected_segment["segment_id"]
    # 按文档顺序的 segment_id：上一段/下一段/跳转都基于它
    records_ordered = [record["segment_id"]
                       for record in _translation_segment_records(job_id, state)]
    terms = _translation_terms_for_pair(state, pair)
    findings = _translation_segment_findings(state, index)
    plan_findings = [item for item in _planner.plan_findings(state, job_id=job_id, limit=40)
                     if index in (item.get("segments") or [])]
    transport_issue = next(
        (issue for issue in (state.get("delivery_validation") or {}).get("issues") or []
         if issue.get("code") == "transport_wrapper"
         and issue.get("segment_index") == index), None)
    review_task = next((item for item in findings
                        if item.get("kind") in {"failed", "stale", "missing"}), None)
    status_label = review_task["status_label"] if review_task else \
        _translation_pair_status_label(pair, state, index)

    st.markdown(
        f'<div class="tp-translation-inspector-head"><div><h3>段落 #{index + 1}</h3></div>'
        f'<span class="tp-translation-inspector-position">{index + 1} / {len(pairs)}</span></div>',
        unsafe_allow_html=True)
    # CAT 导航：编辑流程是"看当前段 → 改 → 下一段"，所以导航就放在 Inspector 顶部。
    nav_prev, nav_next = st.columns(2, gap="small")
    # 上一段/下一段也走统一跳转：翻段时目标行会被滚到视口中央。
    # 用 `on_click` 而不是 `if button(): ... st.rerun()`：回调在 rerun **之前**执行，
    # scroll intent 因此能在渲染前就位；而 `if button()` 里再 st.rerun() 会让
    # widget 状态反复重放（这正是"点一下就一直加载"的成因）。
    nav_prev.button("← 上一段", key=f"translation_prev_{job_id}", help="上一段",
                    disabled=index == 0, width="stretch",
                    on_click=_navigate_to_segment,
                    args=(job_id, state, index - 1),
                    kwargs={"reveal": False})
    nav_next.button("下一段 →", key=f"translation_next_{job_id}", help="下一段",
                    disabled=index >= len(pairs) - 1, width="stretch",
                    on_click=_navigate_to_segment,
                    args=(job_id, state, index + 1),
                    kwargs={"reveal": False})

    edit_count = _segment_edit_count(state, index, pair)
    confidence, confidence_value = _segment_confidence(findings)
    term_hits = _segment_term_hits(state, pair)
    review_note = "不适用" if not review_required else (
        "已审校" if not findings and pair.get("reviewed") else "待审校")
    # 轻量 definition list，不再是 2×3 方格：方格看着像 dashboard，而且"AI 置信度 —"
    # "章节 —" 两个空字段白占很大面积。没有值的字段直接不渲染——不显示比显示"—"更好，
    # 空字段消失后 Agent 动作也会自然上移。
    facts = [("状态", status_label, True),
             ("人工修改", f"{edit_count} 次", edit_count > 0),
             ("术语", f"{term_hits} 条" if term_hits else "", term_hits > 0),
             ("审校", review_note, review_required),
             ("AI 置信度", confidence if confidence_value is not None else "",
              confidence_value is not None),
             ("章节", _segment_section_label(state, index), True)]
    facts = [(label, value) for label, value, show in facts
             if show and value and value != "—"]
    facts_html = "".join(
        f'<div class="tp-inspector-fact"><span>{escape(label)}</span>'
        f'<strong>{escape(value)}</strong></div>' for label, value in facts)
    st.markdown(
        '<div class="tp-inspector-section"><h4>段落事实</h4>'
        f'<div class="tp-inspector-facts-list">{facts_html}</div></div>',
        unsafe_allow_html=True)

    if plan_findings:
        st.markdown('<div class="tp-inspector-section"><h4>Agent 发现</h4>', unsafe_allow_html=True)
        _render_segment_findings(plan_findings, job_id, index)
        st.markdown('</div>', unsafe_allow_html=True)
    if findings:
        issue_label = (review_task["status_label"] if review_task else
                       f"{len(findings)} 个审校问题")
        st.markdown(f'<div class="tp-inspector-section"><div class="tp-inspector-status">'
                    f'<span>!</span><strong>{escape(issue_label)}</strong></div></div>',
                    unsafe_allow_html=True)
        if st.button("查看审校", key=f"translation_open_review_{job_id}_{selected_id}",
                     width="stretch", type="secondary"):
            _select_review_item(findings[0])
            st.session_state.workspace_section = "review"
            st.rerun()
    if transport_issue:
        st.markdown(
            '<div class="tp-transport-alert">'
            '<strong>译文结构异常</strong>'
            '<p>检测到 JSON / Markdown transport wrapper。原文仍安全保留；当前译文不能作为普通正文交付。</p>'
            '<span>修复路径：在中央网格编辑当前译文，或重新翻译当前段；修复后再运行交付检查。</span>'
            '</div>', unsafe_allow_html=True)

    # ---- AI 动作：Agent 的"手"，产出候选译文；写回正文始终由人决定 ----
    st.markdown('<div class="tp-inspector-section"><h4>Agent 动作</h4>', unsafe_allow_html=True)
    ai_ready = bool(api_key and ai_model)
    suggestion_key = f"translation_agent_suggestion_{selected_id}"
    with st.container(key=f"translation_agent_actions_{selected_id}"):
        action_cols = st.columns(2, gap="small")
        for position, (action, label, icon, help_text) in enumerate(_AGENT_ACTIONS):
            with action_cols[position % 2]:
                if st.button(label, icon=icon, help=help_text,
                             key=f"translation_agent_{action}_{selected_id}",
                             disabled=not ai_ready, width="stretch"):
                    with st.spinner(f"Agent 正在{label}…"):
                        st.session_state[suggestion_key] = {
                            "action": label,
                            "text": _run_agent_action(action, job_id, index, state),
                        }
                    st.rerun()
        if st.button("术语检查", icon=":material/rule:",
                     help="检查本段术语是否按项目术语表使用",
                     key=f"translation_agent_terms_{selected_id}",
                     disabled=not ai_ready, width="stretch"):
            with st.spinner("Agent 正在检查术语…"):
                st.session_state[suggestion_key] = {
                    "action": "术语检查",
                    "text": _run_agent_action(
                        "term_check", job_id, index, state,
                        custom=("只做术语检查：逐条说明本段是否遵守了项目术语，"
                                "以及是否有术语被漏用或误用。用简体中文回答，"
                                "不要输出改写后的译文。")),
                }
            st.rerun()
        if st.button("上下文一致性", icon=":material/hub:",
                     help="检查本段与前后段的衔接、指代与逻辑连贯",
                     key=f"translation_agent_context_{selected_id}",
                     disabled=not ai_ready, width="stretch"):
            with st.spinner("Agent 正在检查上下文…"):
                st.session_state[suggestion_key] = {
                    "action": "上下文一致性",
                    "text": _run_agent_action(
                        "context_check", job_id, index, state,
                        custom=("只做上下文一致性检查：说明本段与上一段、下一段在"
                                "指代、逻辑衔接和术语延续上是否有问题。用简体中文回答，"
                                "不要输出改写后的译文。")),
                }
            st.rerun()
        custom = st.text_input("自定义指令", key=f"translation_agent_custom_{selected_id}",
                               placeholder="例如：保留引用标注，压缩到一句…",
                               label_visibility="collapsed")
        if st.button("按指令处理", key=f"translation_agent_custom_run_{selected_id}",
                     disabled=not ai_ready or not custom.strip(), width="stretch"):
            with st.spinner("Agent 正在处理…"):
                st.session_state[suggestion_key] = {
                    "action": "自定义",
                    "text": _run_agent_action("custom", job_id, index, state,
                                              custom=custom),
                }
            st.rerun()
    if not ai_ready:
        st.caption("AI 动作需要先完成引擎配置。")
    suggestion = st.session_state.get(suggestion_key)
    if isinstance(suggestion, dict) and suggestion.get("text"):
        st.markdown(
            f'<div class="tp-inspector-suggestion"><span>Agent · {escape(suggestion["action"])}</span>'
            f'<p>{escape(suggestion["text"])}</p></div>', unsafe_allow_html=True)
        apply_col, dismiss_col = st.columns([1.4, 1], gap="small")
        if apply_col.button("应用到译文", type="primary",
                            key=f"translation_agent_apply_{selected_id}",
                            width="stretch"):
            _save_translation_edit(job_id, index, suggestion["text"])
            st.session_state.pop(suggestion_key, None)
            st.session_state.pop(f"translation_editor_{selected_id}", None)
            _set_workspace_flash(
                f"第 {index + 1} 段已应用 Agent 候选译文。"
                + ("上一次审校已过期，需要重新审校。" if review_required else ""),
                "warning" if review_required else "success")
            st.rerun()
        if dismiss_col.button("丢弃", key=f"translation_agent_discard_{selected_id}",
                              width="stretch"):
            st.session_state.pop(suggestion_key, None)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="tp-inspector-section"><h4>相关术语</h4>', unsafe_allow_html=True)
    if terms:
        rows = "".join(
            f'<div class="tp-inspector-term"><span>{escape(source)}<br/>'
            f'<small>{escape(provenance)}</small></span><b>→ {escape(target)}</b></div>'
            for source, target, provenance in terms)
        st.markdown(f'<div class="tp-inspector-terms">{rows}</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="tp-inspector-empty">本段无项目术语</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if pair.get("from_tm"):
        st.markdown('<div class="tp-inspector-section"><h4>翻译记忆</h4>'
                    '<div class="tp-inspector-status"><span>✓</span><strong>已匹配并复用</strong></div>'
                    f'<p class="tp-inspector-preview" style="margin-top:8px">源：{escape(_translation_preview(pair.get("source"), 100))}</p>'
                    f'<p class="tp-inspector-preview">译：{escape(_translation_preview(pair.get("target"), 100))}</p>'
                    '</div>', unsafe_allow_html=True)

    with st.expander("上下文", expanded=False):
        if index:
            previous = pairs[index - 1].get("source") or "—"
            st.markdown(f'<p class="tp-inspector-preview"><strong>上一段</strong>{escape(_translation_preview(previous, 180))}</p>',
                        unsafe_allow_html=True)
        if index + 1 < len(pairs):
            following = pairs[index + 1].get("source") or "—"
            st.markdown(f'<p class="tp-inspector-preview"><strong>下一段</strong>{escape(_translation_preview(following, 180))}</p>',
                        unsafe_allow_html=True)
        if not index and index + 1 >= len(pairs):
            st.caption("没有相邻段落。")

    with st.expander("当前译法依据", expanded=False):
        explanation_key = f"translation_explanation_{selected_id}"
        if st.session_state.get(explanation_key):
            st.write(st.session_state[explanation_key])
        else:
            st.caption("可让 AI 解释当前译法的语义、术语与上下文决策。")
        if st.button("解释当前译法", key=f"translation_explain_{selected_id}",
                     disabled=not api_key, width="stretch"):
            with st.spinner("正在分析当前译法…"):
                st.session_state[explanation_key] = _explain_translation_segment(job_id, index, state)
            st.rerun()
        if pair.get("human_edited"):
            if st.button("恢复原译", key=f"translation_restore_{selected_id}",
                         width="stretch"):
                _restore_translation_pair(job_id, index)
                st.session_state.pop(f"translation_editor_{selected_id}", None)
                _set_workspace_flash(
                    f"第 {index + 1} 段已恢复原译"
                    + ("；当前内容需要重新审校。" if review_required else "。"),
                    "warning" if review_required else "success")
                st.rerun()

    with st.expander("翻译设置", expanded=False):
        profile = state.get("document_profile") or {}
        st.caption(f"风格：{profile.get('register') or '正式书面语'}")
        st.caption(f"文档画像：{profile.get('domain') or '未标注领域'} · {profile.get('genre') or '未标注文本类型'}")
        st.caption("源文件：" + str(state.get("filename") or "—"))
        review_runtime_label = ("独立审校：" + (review_runtime["model"] or "已配置")
                                if review_required else "当前任务未启用独立审校")
        st.caption(review_runtime_label)


def _render_workspace_terms_context(state):
    entries = state.get("glossary") or []
    term_count = len(entries) if isinstance(entries, list) else len(state.get("auto_terms") or {})
    status = "已冻结" if state.get("glossary_frozen") else "已采用建议" if state.get("quality_bypass") else "待确认"
    st.markdown('<div class="tp-info-card"><h3>术语详情</h3>'
                f'<div class="tp-info-stat"><span>当前状态</span><b>{status}</b></div>'
                f'<div class="tp-info-stat"><span>项目术语</span><b>{term_count:,}</b></div>'
                '<p class="tp-tech-detail" style="margin-top:12px">锁定后的术语会注入后续翻译批次。</p>'
                '</div>', unsafe_allow_html=True)
    _render_workspace_project_details(state)


def _review_highlight(text, span):
    text = str(text or "")
    span = str(span or "").strip()
    if not text or not span:
        return escape(text or "—"), False
    start = text.find(span)
    if start < 0:
        return escape(text), False
    end = start + len(span)
    return (escape(text[:start]) + '<mark class="tp-review-span">'
            + escape(text[start:end]) + '</mark>' + escape(text[end:])), True


def _review_confidence_label(value):
    if value is None or value == "":
        return "未提供"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return escape(str(value))


def _render_workspace_review_context(job_id, state):
    view = _review_workbench(state)
    selected = _workbench_view.select_queue_item(
        view["queue_items"], st.session_state.get("selected_review_item_id"))
    if not selected:
        readiness = view["readiness"]
        st.markdown('<div class="tp-review-inspector-status">'
                    '<span>当前状态</span>'
                    f'<strong>{escape(readiness["label"])}</strong>'
                    f'<p>{escape(readiness["detail"])}</p></div>',
                    unsafe_allow_html=True)
        if view["risk_acceptance"]["current"]:
            st.info("当前交付包含一条有效的人工风险接受记录。")
        return

    segment_id = selected.get("segment_id")
    pair = (state.get("pairs") or [])[segment_id] \
        if isinstance(segment_id, int) and segment_id < len(state.get("pairs") or []) else {}
    st.markdown('<div class="tp-review-inspector-status">'
                '<span>当前状态</span>'
                f'<strong>{escape(selected["status_label"])}</strong>'
                f'<p>{escape(selected.get("summary") or "请检查当前审校任务。")}</p></div>',
                unsafe_allow_html=True)

    st.markdown('<h3 class="tp-review-evidence-title">为什么被标记</h3>',
                unsafe_allow_html=True)
    st.markdown(f'<p class="tp-review-evidence-copy">{escape(selected.get("explanation") or selected.get("reason") or "该旧版本记录未保存完整判断依据。")}</p>',
                unsafe_allow_html=True)
    evidence_ids = selected.get("evidence_ids") or []
    evidence_refs = selected.get("evidence_refs") or []
    st.markdown('<div class="tp-review-evidence-row"><span>证据</span>'
                f'<b>{len(set(evidence_ids + evidence_refs))} 条</b></div>',
                unsafe_allow_html=True)
    if selected.get("detected_text"):
        st.markdown('<div class="tp-review-evidence-label">检测到的片段</div>'
                    f'<p class="tp-review-evidence-copy">{escape(selected["detected_text"])}</p>',
                    unsafe_allow_html=True)

    st.markdown('<h3 class="tp-review-evidence-title tp-review-inspector-section-title">项目约束</h3>',
                unsafe_allow_html=True)
    terms = _translation_terms_for_pair(state, pair) if isinstance(pair, dict) else []
    if terms:
        for source, target, _provenance in terms[:5]:
            st.markdown(f'<div class="tp-review-constraint"><span>{escape(source)}</span>'
                        f'<strong>{escape(target)}</strong></div>', unsafe_allow_html=True)
    style_rules_view = [item for item in state.get("confirmed_style_rules") or []
                        if isinstance(item, dict) and item.get("status") == "confirmed"]
    for rule in style_rules_view[:3]:
        st.markdown(f'<div class="tp-review-constraint"><span>项目风格</span>'
                    f'<strong>{escape(str(rule.get("rule") or ""))}</strong></div>',
                    unsafe_allow_html=True)
    if not terms and not style_rules_view:
        st.caption("本段没有已确认的项目术语或风格规则。")
    if selected.get("entry_id") and st.button(
            "查看项目术语", key=f'review_open_term_{selected["id"]}', width="stretch"):
        st.session_state["selected_glossary_entry_id"] = selected["entry_id"]
        st.session_state.workspace_section = "terms"
        st.rerun()

    history = _workbench_view.review_history(state, segment_id)
    st.markdown('<h3 class="tp-review-evidence-title tp-review-inspector-section-title">历史</h3>',
                unsafe_allow_html=True)
    if history:
        for row in history:
            timestamp = str(row.get("timestamp") or "")
            clock = _runtime_clock(timestamp)[:5] if timestamp else "记录"
            st.markdown('<div class="tp-review-history-row">'
                        f'<time>{escape(clock)}</time><div><strong>{escape(row["label"])}</strong>'
                        f'<span>{escape(row.get("detail") or "")}</span></div></div>',
                        unsafe_allow_html=True)
    else:
        st.caption("暂无更早的审校记录。")

    with st.expander("查看技术详情", expanded=False):
        st.caption(f'work item：{selected.get("id") or "—"}')
        st.caption(f'finding：{selected.get("core_finding_id") or selected.get("finding_id") or "—"}')
        st.caption(f'review event：{selected.get("review_event_id") or "—"}')
        st.caption(f'identity：{selected.get("identity_stability") or "—"}')
        st.caption(f'detector：{selected.get("detector") or "—"} · '
                   f'confidence：{_review_confidence_label(selected.get("confidence"))}')
        if selected.get("technical_reason"):
            st.caption(f'原始失效原因：{selected["technical_reason"]}')
        if evidence_refs or evidence_ids:
            st.caption("证据引用：" + "、".join(dict.fromkeys(evidence_refs + evidence_ids)))
        for trace in (selected.get("review_evidence") or [])[-3:]:
            if trace.get("requests"):
                st.json(trace["requests"])


def _render_workspace_delivery_context(job_id, state):
    snapshot = core.delivery_snapshot_status(job_id, state)
    latest = snapshot.get("latest") or {}
    approval = latest.get("approval") or {}
    truth = core.translation_truth_view(job_id, state)
    working_label = f'v{truth.get("version", 0)} · 当前'
    frozen_label = (f'v{latest.get("snapshot_version")} · 已冻结交付'
                    if latest else "尚未生成")
    if snapshot.get("diverged"):
        status_label = (f'工作版本已偏离冻结交付 v{latest.get("snapshot_version")}；'
                        "原冻结版本仍可下载")
        status_tone = "warning"
    elif latest:
        status_label = f'已冻结交付 v{latest.get("snapshot_version")}'
        status_tone = "success"
    else:
        status_label = "尚未生成冻结交付"
        status_tone = "warning"
    st.markdown('<div class="tp-version-compare"><h3>版本对比</h3>'
                f'<div class="tp-version-row"><span>工作版本</span><strong>{escape(working_label)}</strong></div>'
                f'<div class="tp-version-row"><span>冻结交付</span><strong>{escape(frozen_label)}</strong></div>'
                f'<div class="tp-version-compare-status is-{status_tone}">{escape(status_label)}</div>'
                f'<div class="tp-version-technical">确认人：{escape(str(approval.get("actor") or "—"))}</div>'
                '</div>', unsafe_allow_html=True)
    if latest:
        st.caption(f"确认时间：{str(approval.get('timestamp') or latest.get('created_at') or '—')[:16]}")
    _render_workspace_project_details(state)


def _render_workspace_context(job_id, state, section, overview=None):
    if section == "translation":
        with st.container(key="translation_inspector"):
            _render_workspace_translation_context(job_id, state, overview)
    elif section == "terms":
        _render_workspace_terms_context(state)
    elif section == "review":
        _render_workspace_review_context(job_id, state)
    elif section == "cases":
        _render_workspace_cases_context(job_id, state)
    elif section == "qa":
        _render_workspace_qa_context(job_id, state)
    elif section == "delivery":
        _render_workspace_delivery_context(job_id, state)


def _academic_downstream_enabled(state, job_id=""):
    """是否存在需要随译文变化重建的学术/报告下游产物。

    `core.dependency_impact_view` 只要译文变了就把所有已知下游产物标为 stale，
    包括这个任务根本不适用的报告/QA 产物。于是纯翻译任务会被告知
    "重建 9 项下游产物"，而同一页的交付判断网格却说"学术产物同步：当前任务
    未启用 ✓"——页面自相矛盾。这里给出与网格一致的判据。
    """
    if not isinstance(state, dict):
        return False
    if state.get("report_enabled"):
        return True
    artifacts = (state.get("academic_state") or {}).get("artifacts") or {}
    return bool(artifacts)


def _render_workspace_overview(job_id, state, overview=None):
    """Task Overview: canonical state, blocking issues, next action.

    Every element on this page renders from ``overview`` — the single canonical
    derivation.  Cards and pipeline steps never re-derive their own status, and
    a workflow stage that is not enabled never gets a strong CTA.
    """
    overview = overview or _task_overview_state(job_id, state)
    projection = _workspace_projection(state, job_id, overview=overview)

    st.markdown('<h2>概览</h2>'
                '<div class="tp-section-lead">当前任务与项目进度</div>',
                unsafe_allow_html=True)
    runtime_view = core.build_job_runtime_view(job_id, state)
    if runtime_view.get("runtime_status") not in {None, "idle", "completed"}:
        _render_runtime_panel(job_id, state)

    # ---- Hero: exactly one canonical status, one fact line, ≤2 actions. ----
    translation = overview["translation"]
    review = overview["review"]
    st.markdown(
        f'<div class="tp-overview-hero is-{escape(overview["tone"])}">'
        f'<strong><i class="tp-hero-dot"></i>{escape(overview["label"])}</strong>'
        f'<p>{escape(overview["detail"])}</p>'
        + (f'<small>{escape(overview["facts_line"])}</small>'
           if overview["facts_line"] else "")
        + '</div>',
        unsafe_allow_html=True)
    actions = [overview["primary_action"]] + list(overview["secondary_actions"])
    actions = [action for action in actions if action]
    if actions:
        widths = [1.5] + [1.2] * (len(actions) - 1) + [5]
        with st.container(key=f"overview_hero_actions_{job_id}"):
            for col, action in zip(st.columns(widths, gap="small"), actions):
                with col:
                    if st.button(action["label"] + " →",
                                 key=f'overview_action_{action["kind"]}_{job_id}',
                                 type="primary" if action.get("primary") else "secondary",
                                 width="stretch"):
                        st.session_state.workspace_section = action["destination"]
                        st.rerun()

    # ---- Cards: one per enabled stage.  Disabled capabilities stay in the
    # hero's secondary summary instead of getting a card with a strong CTA. ----
    stages = {stage["id"]: stage for stage in overview["stages"]}
    cards = [{
        "id": "translation",
        "title": "翻译",
        "value": f'{translation["done"]:,} / {translation["total"]:,} 段',
        "sub": "已完成" if translation["complete"] else "处理中",
        # 卡片颜色也是 canonical tone（green/blue/...），不是 stage state。
        "tone": _task_overview.GREEN if translation["complete"]
        else _task_overview.BLUE,
        "destination": "translation",
        "action": "查看翻译" if translation["total"] else None,
    }]
    if review["enabled"]:
        cards.append({
            "id": "review",
            "title": "独立审校",
            "value": f'{review["current"]:,} / {review["expected"]:,} 段',
            "sub": stages["review"]["detail"],
            "tone": stages["review"]["tone"],
            "destination": "review",
            # 功能已启用：给出查看入口（未启用时整张卡片都不会出现）。
            "action": "查看审校",
        })
    if overview["report_enabled"]:
        report = next((item for item in overview["capabilities"]
                       if item["id"] == _task_overview.CAP_REPORT), None)
        report_generated = bool(overview["report_ready"]
                                and not overview["report_stale"])
        report_content = bool(
            report_generated or state.get("p3_done") or state.get("p3_md")
            or _finalization._artifact_status_value(
                state.get("academic_state") or {}, "report")
            not in {"not_available", ""})
        cards.append({
            "id": "report",
            "title": "研究报告",
            "value": "已生成" if report_generated else
            "需要更新" if overview["report_stale"] else "尚未生成",
            "sub": report["detail"] if report else "",
            "tone": report["tone"] if report else _task_overview.GRAY,
            "destination": "report",
            # 只有功能真正启用且存在内容时才提供"查看报告"。
            "action": "查看报告" if report_content else None,
        })
    delivery_action = overview["primary_action"]
    cards.append({
        "id": "delivery",
        "title": "交付",
        "value": overview["label"],
        "sub": overview["detail"],
        "tone": overview["tone"],
        "destination": "delivery",
        # 交付 CTA 只在 canonical 状态允许交付准备时出现；blocking 时
        # primary 已经是"查看问题"，这里不能再出现交付动作。
        "action": delivery_action["label"]
        if delivery_action.get("kind") in {"prepare_delivery", "open_delivery"} else None,
    })
    for col, card in zip(st.columns(len(cards), gap="small"), cards):
        with col:
            with st.container(key=f'overview_stage_card_{card["id"]}'):
                token = _task_overview.surface_token("card", card["tone"])
                st.markdown(
                    f'<div class="tp-stage-card-content {token}">'
                    f'<strong>{escape(card["title"])}</strong>'
                    f'<b>{escape(card["value"])}</b>'
                    f'<span>{escape(card["sub"])}</span></div>',
                    unsafe_allow_html=True)
                if card["action"]:
                    if st.button(card["action"] + " →",
                                 key=f'overview_go_{card["id"]}_{job_id}',
                                 width="stretch", type="secondary"):
                        st.session_state.workspace_section = card["destination"]
                        st.rerun()

    # ---- Pipeline: the mandatory lifecycle only.  Terminology extraction and
    # the research report are auxiliary capabilities (see the strip below), and
    # an optional stage that is off renders as skipped — never as completed. ----
    rows = []
    for stage in overview["stages"]:
        token = ("is-skipped" if stage["state"] == _task_overview.SKIPPED
                 else _task_overview.surface_token("step", stage["tone"]))
        if rows:
            rows.append('<span class="tp-step-connector">→</span>')
        rows.append(f'<span class="tp-progress-step {token}" '
                    f'title="{escape(stage["detail"])}">'
                    f'<i>{stage["glyph"]}</i>{escape(stage["label"])}</span>')
    st.markdown('<div class="tp-section-label">项目进度</div>'
                '<div class="tp-overview-progress">' + "".join(rows) + '</div>',
                unsafe_allow_html=True)

    auxiliary = [item for item in overview["capabilities"]
                 if item["enabled"] and item["id"] != _task_overview.CAP_REPORT]
    if auxiliary:
        chips = "".join(
            f'<span class="tp-capability {_task_overview.surface_token("card", item["tone"])}">'
            f'<i>{_task_overview.STAGE_GLYPHS[item["state"]]}</i>'
            f'{escape(item["label"])}<em>{escape(item["detail"])}</em></span>'
            for item in auxiliary)
        st.markdown('<div class="tp-section-label">辅助能力</div>'
                    f'<div class="tp-capability-strip">{chips}</div>',
                    unsafe_allow_html=True)

    if not runtime_view.get("user_events"):
        st.markdown('<div class="tp-section-label">最近活动</div><div class="tp-activity">',
                    unsafe_allow_html=True)
        activities = _workspace_activity(job_id, state)
        if activities:
            st.markdown(f'<div class="tp-activity-date">{escape(activities[0][0])}</div>',
                        unsafe_allow_html=True)
            for _, text_value in activities[:3]:
                st.markdown(f'<div class="tp-activity-row">{escape(text_value)}</div>',
                            unsafe_allow_html=True)
        else:
            st.markdown('<div class="tp-activity-row">暂无活动记录</div>',
                        unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    _render_workspace_project_details(state)


# 一次最多渲染多少行。实测 300 行约 0.11s 脚本时间 / 650ms 首屏，400 行仍很轻；
# 超出部分靠搜索与筛选收敛，避免把整本书一次性塞进 DOM。
CAT_GRID_ROWS = 400
# 编辑框的保存基线：`translation_editor_{segment_id}` 里的值 != 基线 => 有未保存改动。
# 用基线而不是 `st.session_state` 里有没有 key，是因为 typeahead 的 widget 状态在
# 交互后就会写进 session_state，直接拿它判断会把"没改过"误报成"改过"。
_CAT_BASELINE_PREFIX = "cat_baseline_"


def _cat_status_tone(status):
    """把段落状态映射成左侧指示条，替代"状态"整列。"""
    return {
        "已审校": "is-reviewed",
        "已修改": "is-edited",
        "待审校": "is-pending",
        "待翻译": "is-pending",
    }.get(str(status or ""), "")


def _cat_metric(label, value, tone="", title=""):
    return (f'<span class="tp-cat-metric {tone}" title="{escape(title)}">'
            f'<span>{escape(label)}</span><b>{escape(str(value))}</b></span>')


def _render_translation_progress(state, job_id, projection, truth, change_note):
    """进度 = Translation / Terminology / Review / Issues。

    单一"82/82 已翻译"会被读成"完成了"，而右上角的交付判断又说没满足条件。
    这里让四个维度各自说话，完成度不再是翻译一个数字。
    """
    progress = _planner.workspace_progress(state, job_id=job_id)
    translation = progress["translation"]
    terminology = progress["terminology"]
    review = progress["review"]
    issues = progress["issues"]
    total = translation["total"]
    percent = (translation["done"] / total * 100) if total else 0.0
    metrics = [
        _cat_metric("翻译", f'{translation["done"]:,} / {total:,}',
                    "is-complete" if translation["complete"] else "",
                    "当前译文覆盖的段落数"),
    ]
    if terminology["applicable"]:
        # 说清是哪个指标：这是"确认（锁定/冻结）了几个术语"，不是"术语覆盖率"，
        # 否则用户会把它和 Inspector 里当前段命中的术语数当成同一件事。
        metrics.append(_cat_metric("术语已确认", terminology["label"],
                                   "is-complete" if terminology["complete"] else "is-attention",
                                   "已锁定/冻结的项目术语"))
    else:
        metrics.append(_cat_metric("术语已确认", "不适用", "is-muted", "当前任务未启用项目术语"))
    if review["applicable"]:
        metrics.append(_cat_metric("审校", review["label"],
                                   "is-complete" if review["complete"] else "is-attention",
                                   "当前译文已有最新审校结果的段落"))
    else:
        metrics.append(_cat_metric("审校", "不适用", "is-muted", "当前任务未启用独立审校"))
    issue_tone = ("is-blocked" if issues["blocking"] else
                  "is-attention" if issues["count"] else "is-complete")
    metrics.append(_cat_metric("发现", f'{issues["count"]:,}', issue_tone,
                               "Agent 在全文里发现的需要处理的问题"))
    detail_parts = [change_note,
                    f"当前译文 v{truth['version']} · {truth['segment_count']:,} 段 · 交付与审校的唯一来源",
                    (f"审校：{projection['review_coverage']:,} 段已有最新结果，"
                     f"{projection['missing_review_segments'] + projection['stale_segments'] + projection['failed_segments']:,} 段待处理")
                    if projection["review_required"] else "当前任务未启用独立审校",
                    f"TM 复用 {state.get('tm_used_count', 0):,}"]
    st.markdown(
        '<div class="tp-cat-title"><h2>翻译</h2>'
        '<span class="tp-cat-hint">点段号选中，直接在右列改译文</span>'
        f'<div class="tp-cat-progress" title="{escape(" · ".join(detail_parts))}">'
        f'<div class="tp-cat-progress-bar"><span style="width:{percent:.1f}%"></span></div>'
        f'<span class="tp-cat-progress-text">{translation["label"]}</span>'
        '</div></div>'
        f'<div class="tp-cat-progress-grid">{"".join(metrics)}</div>',
        unsafe_allow_html=True)


def _render_agent_findings_strip(job_id, state):
    """文档级 Agent 观察，压成一条 44–52px 的 issue bar。

    Agent 的辨识度靠"系统主动说出它发现了什么"，但这份主动性不该吃掉首屏：
    更早的版本用大卡片铺 5 条发现 + 一排大号"定位"按钮，实测吃掉约 140px，
    把第一段正文推到屏幕中部。现在是一条 44px 的 bar：

        ✦ "aerial view" 在 4 处译法不一致 · 8 项发现 · [查看全部]

    「查看全部」把**右栏 Inspector** 切到 Issues 模式，不再弹中央浮层：
    浮层会盖住正在工作的正文，而问题列表和"跳到正文处理问题"是同一件事的两半，
    把它盖在工作台上自相矛盾。Agent 随时可见，但不抢正文。
    """
    findings = _planner.plan_findings(state, job_id=job_id, limit=12)
    progress = _planner.workspace_progress(state, job_id=job_id)
    issues = progress["issues"]
    if not findings:
        return
    lead = findings[0]
    issues_open = bool(st.session_state.get("issues_panel_open"))
    bar_col, action_col = st.columns([5.2, 1], gap="small")
    with bar_col:
        st.markdown(
            '<div class="tp-issue-bar">'
            '<span class="tp-issue-mark">✦</span>'
            f'<span class="tp-issue-dot is-{escape(lead["severity"])}"></span>'
            f'<strong>{escape(lead["title"])}</strong>'
            f'<span class="tp-issue-count">{issues["count"]:,} 项发现</span>'
            '<span class="tp-issue-spacer"></span>'
            '</div>', unsafe_allow_html=True)
    with action_col:
        label = "返回段落" if issues_open else "查看全部"
        # 切视图同样走 on_click：按钮点击本身已经触发一次渲染，脚本里不需要
        # 也不应该再 st.rerun()。这里没有 scroll intent，所以点开抽屉不会跳走。
        st.button(label, key=f"agent_all_{job_id}", use_container_width=True,
                  on_click=_toggle_issues_panel)


def _render_issues_panel(job_id, state):
    """右栏的问题抽屉：发现 → 定位 → 回到该段 Inspector。

    每条问题保留 #N 锚点。点锚点走唯一的 `_navigate_to_segment`：
    关闭抽屉 + 选中该段 + 一次性滚动 + 目标被挡住时先放宽筛选。
    """
    findings = _planner.plan_findings(state, job_id=job_id, limit=_ISSUES_PANEL_LIMIT)
    progress = _planner.workspace_progress(state, job_id=job_id)
    issues = progress["issues"]
    head_col, close_col = st.columns([3.2, 1], gap="small")
    with head_col:
        st.markdown('<div class="tp-translation-inspector-head"><div>'
                    '<h3>问题</h3></div></div>', unsafe_allow_html=True)
    with close_col:
        st.button("返回段落", key=f"issues_close_{job_id}",
                  use_container_width=True, on_click=_close_issues_panel)
    st.markdown(
        f'<div class="tp-issues-summary">'
        f'<span class="is-blocking"><b>{issues["blocking"]}</b> 必须处理</span>'
        f'<span class="is-actionable"><b>{issues["actionable"]}</b> 建议检查</span>'
        f'<span><b>{issues["informational"]}</b> 参考</span></div>',
        unsafe_allow_html=True)
    if not findings:
        st.markdown('<div class="tp-inspector-empty">当前没有需要处理的全文发现。</div>',
                    unsafe_allow_html=True)
        return
    for finding in findings:
        st.markdown(
            f'<div class="tp-issue-row is-{escape(finding["severity"])}">'
            f'<div class="tp-issue-row-head"><strong>{escape(finding["title"])}</strong>'
            f'<span class="tp-issue-sev">{escape(_ISSUE_SEVERITY_LABELS.get(finding["severity"], finding["severity"]))}</span>'
            '</div>'
            f'<p>{escape(finding["detail"])}</p></div>', unsafe_allow_html=True)
        segments = finding.get("segments") or []
        if not segments:
            continue
        st.markdown(f'<div class="tp-issue-hits">命中 '
                    + " ".join(f"#{index + 1}" for index in segments[:10])
                    + '</div>', unsafe_allow_html=True)
        # 锚点用按钮而不是 pills：pills 的选中状态会留在 widget state 里，
        # rerun 后再次返回同一个值——正是上一版"点一次跳转、之后反复重放"的成因。
        # 按钮是一次性事件，天然没有这个问题。
        anchor_cols = st.columns(min(len(segments), 6), gap="small")
        for position, segment in enumerate(segments[:6]):
            with anchor_cols[position]:
                st.button(f"#{segment + 1}",
                          key=f"issue_anchor_{job_id}_{finding['id']}_{segment}",
                          use_container_width=True,
                          on_click=_navigate_to_segment,
                          args=(job_id, state, segment))


def _blocking_segments(state, job_id):
    """存在"必须处理"级问题的段落集合。

    只有 blocking 才配上行内标记。actionable 级（例如"这段译文偏短，可能漏译"）
    是建议，不是异常——把 actionable 也标成"需处理"，82 段文档里会出现 26 个红字，
    等于把建议喊成了错误。
    """
    return {index for finding in _planner.plan_findings(state, job_id=job_id, limit=200)
            if finding.get("severity") == "blocking"
            for index in (finding.get("segments") or [])}


def _row_status_anomaly(pair, index, blocking_segments, is_dirty, review_required):
    """段落行里唯一值得常驻的状态文字：异常。

    "已翻译"是正常状态，不该每一行都宣布一次——20 段同屏就变成 20 个重复标签，
    正文也不再像连续文档。正常状态交给右侧 Inspector 的"段落事实"。
    没有异常时返回 None，整行不渲染状态区。
    """
    if is_dirty:
        return ("is-dirty", "● 未保存")
    if index in blocking_segments:
        return ("is-issue", "需处理")
    if pair.get("human_edited"):
        return ("is-edited", "已修改")
    if review_required and str(pair.get("target") or "").strip() \
            and not pair.get("reviewed"):
        return ("is-pending", "待审校")
    return None


def _render_translation_row(job_id, state, index, pair, segment_id,
                           selected_index, blocking_segments):
    """一行 = 段号 + 原文 + 可编辑译文。

    译文编辑器就在中央这一列里——右栏不再有第二个编辑器，用户不需要猜
    "到底该在哪里改"。行内表单只在提交时才触发 rerun（`enter_to_submit=False`），
    所以打字本身不会让整页重跑。

    `segment_id` 由调用方传入：每行都去重算一遍全部 segment_id 是 O(n²)，
    400 行的窗口上这是白白的开销。
    """
    pair = pair if isinstance(pair, dict) else {}
    status = _translation_pair_status_label(pair, state, index)
    cell_class = f"tp-cat-rowcell {_cat_status_tone(status)}".strip()
    is_active = index == selected_index
    source_text = str(pair.get("source") or "").strip()
    target_text = str(pair.get("target") or "")
    editor_key = f"translation_editor_{segment_id}"
    baseline_key = f"{_CAT_BASELINE_PREFIX}{editor_key}"
    if editor_key not in st.session_state:
        # 只有在用户还没动过这个框时才同步基线，避免把正在输入的内容当成已保存。
        st.session_state[baseline_key] = target_text
    baseline = st.session_state.get(baseline_key, target_text)
    current = st.session_state.get(editor_key, target_text)
    is_dirty = str(current) != str(baseline)
    row_class = f"{cell_class}{' is-active' if is_active else ''}".strip()
    anomaly = _row_status_anomaly(pair, index, blocking_segments, is_dirty,
                                  bool(state.get("translation_core_review_required")))
    # 只有"必须处理"值得在原文下面留一枚徽标；TM/术语/人工修改都属于 Inspector 的职责，
    # 每一行都挂一遍会让正文看起来像报表。
    issue_badge = ('<div class="tp-cat-badges">'
                   '<span class="tp-cat-badge is-issue">必须处理</span></div>'
                   if index in blocking_segments else "")

    with st.container(key=f"cat_row_{job_id}_{index}"):
        # data-segment 是跳转锚点：`_render_scroll_trigger` 在目标渲染完成后
        # 用它把这一行滚到视口中央。属性挂在行容器上，所以哪怕行内没有译文框
        # （空段落）也能定位。
        st.markdown(f'<span class="{row_class}" data-segment="{index}"></span>',
                    unsafe_allow_html=True)
        number_col, source_col, target_col = st.columns(
            [0.42, 3.56, 3.62], gap="medium")
        with number_col:
            with st.container(key=f"cat_num_{job_id}_{index}"):
                st.button(str(index + 1), key=f"cat_sel_{job_id}_{index}",
                          help=f"第 {index + 1} 段 · {status}"
                               + ("（当前段落）" if is_active else ""),
                          type="primary" if is_active else "secondary",
                          width="stretch",
                          # 点段号也在当前渲染集合里，不需要放宽筛选
                          on_click=_navigate_to_segment,
                          args=(job_id, state, index),
                          kwargs={"reveal": False})
        source_col.markdown(
            f'<div class="tp-cat-source{" is-empty" if not source_text else ""}">'
            f'{escape(source_text) or "（空段落）"}</div>{issue_badge}',
            unsafe_allow_html=True)
        with target_col:
            with st.form(key=f"cat_form_{job_id}_{index}", enter_to_submit=False,
                         border=False):
                with st.container(key=f"cat_editor_{job_id}_{index}"):
                    st.text_area("译文", value=current, key=editor_key,
                                 height=48, label_visibility="collapsed",
                                 placeholder="尚未翻译——在这里写译文")
                # 正常状态下完全不渲染保存操作：只在内容变化后浮现"未保存 + 保存"。
                # ⌘/Ctrl+Enter 也能提交（表单默认行为），所以编辑时手不必离开键盘。
                if is_dirty:
                    foot_col, save_col = st.columns([1.6, 0.9], gap="small")
                    label, text = anomaly or ("is-dirty", "● 未保存")
                    foot_col.markdown(
                        f'<span class="tp-cat-status {label}">{escape(text)}</span>'
                        '<span class="tp-cat-status is-hint">⌘/Ctrl+Enter 保存</span>',
                        unsafe_allow_html=True)
                    with save_col:
                        with st.container(key=f"cat_save_{job_id}_{index}"):
                            submitted = st.form_submit_button(
                                "保存", type="primary",
                                key=f"cat_save_btn_{job_id}_{index}",
                                width="stretch")
                elif anomaly is not None:
                    label, text = anomaly
                    st.markdown(
                        f'<span class="tp-cat-status {label}">{escape(text)}</span>',
                        unsafe_allow_html=True)
                    submitted = False
                else:
                    submitted = False
            if submitted:
                updated = st.session_state.get(editor_key, "")
                if str(updated) != str(baseline):
                    _save_translation_edit(job_id, index, updated)
                    st.session_state.pop(editor_key, None)
                    st.session_state.pop(baseline_key, None)
                    _set_workspace_flash(
                        f"第 {index + 1} 段译文已修改"
                        + ("；上一次审校已过期，需要重新审校。"
                           if state.get("translation_core_review_required") else "。"),
                        "warning" if state.get("translation_core_review_required") else "success")
                    st.rerun()


def _render_workspace_translation(job_id, state, overview=None):
    pairs = state.get("pairs") or []
    projection = _workspace_projection(state)
    truth = core.translation_truth_view(job_id, state)
    last_change = truth.get("last_change") or {}
    changed_indexes = last_change.get("segment_indexes") or []
    raw_change_reason = str(last_change.get("reason") or "")
    change_reason = ("当前译文已更新，相关下游需要重新检查"
                     if "CURRENT_TRANSLATION" in raw_change_reason
                     else raw_change_reason or "工作版本已更新")
    valid_changed_indexes = [x for x in changed_indexes
                             if isinstance(x, int) and 0 <= x < len(pairs)]
    change_note = (f"最近变更：第 {', '.join(str(int(x) + 1) for x in valid_changed_indexes)} 段 · "
                   f"{change_reason}"
                   if valid_changed_indexes else "尚未记录当前译文变更")
    if not pairs:
        runtime = core.build_job_runtime_view(job_id, state)
        runtime_status = runtime.get("runtime_status") or runtime.get("status")
        if runtime_status in {"failed", "interrupted", "stalled"}:
            st.error("翻译未完成；上次运行没有生成当前译文。")
            st.caption("已保留任务进度，修复 AI 配置后可以重试翻译。")
            if st.button("前往 AI 设置", key=f"translation_open_settings_{job_id}", width="stretch"):
                st.session_state.app_view = "settings"
                st.session_state.workspace_mode = False
                st.rerun()
            if runtime_status != "failed":
                st.caption("也可以回到概览继续处理任务。")
        else:
            st.markdown('<div class="tp-empty">翻译尚未开始。</div>', unsafe_allow_html=True)
        return
    _render_translation_progress(state, job_id, projection, truth, change_note)

    # 筛选/更多两列不能再压：1536px 宽下"筛选 ▾"也会被截成"筛…"（实测），
    # 宁可给这两列多十几像素，也不要出现这种一眼像 bug 的截断。
    toolbar_search, toolbar_primary, toolbar_filter, toolbar_more = st.columns(
        [3.05, 2.2, 1.08, 0.98], gap="small")
    with toolbar_search:
        search = st.text_input("搜索段落", key=f"translation_search_{job_id}",
                               placeholder="搜索原文或译文，或输入段落号…",
                               label_visibility="collapsed")
    with toolbar_primary:
        filter_label = st.segmented_control(
            "一级筛选", ["全部", "待审", "已审校"], default="全部",
            key=f"translation_filter_{job_id}", label_visibility="collapsed",
            width="stretch") or "全部"
    with toolbar_filter:
        # 三角形改成更窄的 ▾，并配一条 nowrap 规则，避免标签被省略号截断
        with st.popover("筛选 ▾", use_container_width=True,
                        key=f"translation_filter_menu_{job_id}"):
            filter_terms = st.checkbox("含项目术语", key=f"translation_filter_terms_{job_id}")
            filter_edited = st.checkbox("已修改", key=f"translation_filter_edited_{job_id}")
            issue_only = st.checkbox("有审校问题", key=f"translation_filter_issue_{job_id}")
            filter_tm = st.checkbox("使用翻译记忆", key=f"translation_filter_tm_{job_id}")
    with toolbar_more:
        with st.popover("更多 ▾", use_container_width=True,
                        key=f"translation_more_menu_{job_id}"):
            mode = st.radio("显示模式", ["列表模式", "聚焦模式"],
                            key=f"translation_mode_{job_id}")

    issue_indexes = {item.get("segment_index") for item in _workspace_review_contexts(state)
                     if item.get("segment_index") is not None}
    # 行内标记只看"必须处理"级问题（actionable 是建议，不是异常）
    blocking_segments = _blocking_segments(state, job_id)
    visible_indexes = core.translation_visible_indexes(
        state, search=search, status_filter=filter_label,
        filter_terms=filter_terms, filter_edited=filter_edited,
        filter_issues=issue_only, filter_tm=filter_tm,
        issue_indexes=issue_indexes)
    if filter_label == "待审":
        visible_indexes = [index for index in visible_indexes
                           if projection["segment_status"].get(index) != "已审校"]
    elif filter_label == "已审校":
        visible_indexes = [index for index in visible_indexes
                           if projection["segment_status"].get(index) == "已审校"]
    records = _translation_segment_records(job_id, state)
    visible_records = [records[index] for index in visible_indexes]
    # Agent 发现条与 scroll intent 必须在**任何 early return 之前**渲染。
    # 早先它们放在"没有符合筛选条件的段落"之后，于是筛选/搜索命中 0 段时
    # issue bar 也一起消失——而那恰恰是用户最需要它的时候（"有问题但当前筛选
    # 看不到"正是要点「查看全部」去定位的场景）。
    _render_agent_findings_strip(job_id, state)
    # scroll intent 只消费一次，且必须在正文渲染之前取出：网格/聚焦模式两个分支
    # 都要用到它。清空发生在取出的一瞬间，所以不存在"之后每次 rerun 又跳一次"的残留。
    pending_scroll = _consume_pending_scroll()
    _render_nav_notice()
    if not visible_indexes:
        st.session_state["selected_segment_id"] = None
        st.markdown('<div class="tp-empty">没有符合当前筛选条件的段落。</div>', unsafe_allow_html=True)
        return

    selected_segment = _translation_selected_segment(job_id, state, visible_records)
    selected_index = selected_segment["index"]
    if mode == "聚焦模式":
        pair = selected_segment["pair"]
        st.markdown(f'<div class="tp-focus-head"><span>第 {selected_index + 1} 段</span>'
                    f'<span>{escape(_translation_pair_status_label(pair, state, selected_index))} · {selected_index + 1} / {len(pairs)}</span></div>',
                    unsafe_allow_html=True)
        source_col, target_col = st.columns(2)
        with source_col:
            st.markdown(f'<div class="tp-focus-text"><label>原文</label><p>{escape(pair.get("source") or "—")}</p></div>',
                        unsafe_allow_html=True)
        with target_col:
            st.markdown(f'<div class="tp-focus-text"><label>译文（在右栏编辑）</label><p>{escape(pair.get("target") or "—")}</p></div>',
                        unsafe_allow_html=True)
        prev_col, next_col = st.columns(2)
        if prev_col.button("← 上一段", key=f"translation_focus_prev_{job_id}", disabled=selected_index == visible_indexes[0], width="stretch"):
            current = visible_indexes.index(selected_index)
            next_index = visible_indexes[max(0, current - 1)]
            st.session_state["selected_segment_id"] = records[next_index]["segment_id"]
            st.rerun()
        if next_col.button("下一段 →", key=f"translation_focus_next_{job_id}", disabled=selected_index == visible_indexes[-1], width="stretch"):
            current = visible_indexes.index(selected_index)
            next_index = visible_indexes[min(len(visible_indexes) - 1, current + 1)]
            st.session_state["selected_segment_id"] = records[next_index]["segment_id"]
            st.rerun()
        _render_scroll_trigger(pending_scroll)
        return

    # ---- CAT 段落网格 ----
    # 译文就在原文右边直接编辑：中间这一列既是阅读区也是编辑区，右栏不再是第二个
    # 编辑器。行与行之间靠留白和 hover 分层，不加外框/内框/卡片三层边界。
    position = (visible_indexes.index(selected_index)
                if selected_index in visible_indexes else 0)
    start = max(0, min(position - CAT_GRID_ROWS // 2,
                       len(visible_indexes) - CAT_GRID_ROWS))
    window_indexes = visible_indexes[start:start + CAT_GRID_ROWS]
    st.markdown('<div class="tp-cat-head">'
                '<span class="tp-cat-num">段</span>'
                '<span class="tp-cat-col">原文</span>'
                '<span class="tp-cat-col is-tgt">译文 · 可直接编辑</span></div>',
                unsafe_allow_html=True)
    if len(window_indexes) < len(visible_indexes):
        st.caption(f"显示第 {start + 1}–{start + len(window_indexes)} 段"
                   f"（筛选后共 {len(visible_indexes)} 段）；搜索或切换筛选可查看其余段落。")
    with st.container(key=f"cat_grid_{job_id}"):
        for index in window_indexes:
            _render_translation_row(job_id, state, index, pairs[index],
                                    records[index]["segment_id"],
                                    selected_index, blocking_segments)
    # 跳转收尾：在目标行渲染完成之后注入一次性滚动。放在网格之后是关键——
    # 目标 DOM 必须已经存在，否则 querySelector 找不到它。
    _render_scroll_trigger(pending_scroll)


def _render_workspace_terms(job_id, state):
    entries = state.get("glossary") or []
    if not isinstance(entries, list):
        entries = []
    if not entries and isinstance(state.get("auto_terms"), dict):
        entries = [{"id": f"auto-{i}", "source": source,
                    "target": value if isinstance(value, str) else "",
                    "preferred": value if isinstance(value, str) else "",
                    "status": "provisional"}
                   for i, (source, value) in enumerate(state["auto_terms"].items())]
    st.markdown('<div class="tp-section-kicker">语言资产</div><h2>术语</h2>'
                '<div class="tp-section-lead">术语是项目记忆的一部分；锁定后会随翻译批次注入。</div>',
                unsafe_allow_html=True)
    frozen = state.get("glossary_frozen")
    bypassed = state.get("quality_bypass")
    if frozen:
        st.success(f"术语已冻结 · v{frozen.get('version')}")
    elif bypassed:
        st.info("本任务跳过了人工冻结，当前使用暂定术语。")
    elif not state.get("p2_done") and state.get("quality_mode"):
        st.warning("术语尚未冻结；完成人工确认后才能继续翻译。")
        _render_profile_editor(job_id, state)
    if frozen and state.get("p2_done"):
        st.info("当前术语版本已用于翻译；修改锁定术语后，相关译文或审校结果可能需要重新确认。")
    if not entries:
        st.markdown('<div class="tp-empty">暂无项目术语。</div>', unsafe_allow_html=True)
        return
    selected_entry_id = str(st.session_state.get("selected_glossary_entry_id") or "")
    selected_entry = next((entry for entry in entries
                           if str(entry.get("id") or "") == selected_entry_id), None)
    if selected_entry:
        st.markdown('<div class="tp-term-focus"><span>来自审校工作台</span>'
                    f'<strong>{escape(str(selected_entry.get("source") or "—"))} → '
                    f'{escape(str(selected_entry.get("preferred") or selected_entry.get("target") or "—"))}</strong>'
                    '<p>这是当前审校发现关联的既有项目术语。</p></div>',
                    unsafe_allow_html=True)
    if not state.get("p2_done") and state.get("quality_mode") and state.get("glossary") is not None:
        df = _glossary_dataframe(entries, state.get("paras") or [])
        visible = ["选择", "source", "proposed_target", "preferred", "status", "domain", "note", "id", "payload"]
        edited = st.data_editor(
            _humanize_glossary_editor(df[[key for key in visible if key in df.columns]]),
            key=f"workspace_glossary_editor_{job_id}", num_rows="dynamic",
            hide_index=True, width="stretch",
            column_config={
                "选择": st.column_config.CheckboxColumn("选择"),
                "id": st.column_config.TextColumn("ID", disabled=True),
                "source": st.column_config.TextColumn("源术语", required=True),
                "proposed_target": st.column_config.TextColumn("建议译名"),
                "preferred": st.column_config.TextColumn("首选译名"),
                "status": st.column_config.SelectboxColumn(
                    "状态", options=list(_TERM_STATUS_LABELS.values())),
                "domain": st.column_config.TextColumn("领域"),
                "note": st.column_config.TextColumn("备注"),
                "payload": st.column_config.TextColumn("payload", disabled=True),
            })
        chosen = edited[edited["选择"].fillna(False)] if "选择" in edited.columns else edited.iloc[0:0]
        ids = [str(item) for item in chosen.get("id", []).tolist() if str(item)]
        a, b, c = st.columns(3)
        if a.button("保存草稿", key=f"workspace_terms_save_{job_id}", width="stretch"):
            core.save_glossary_draft(job_id, _merge_edited_entries(entries, _df_to_entries(edited)))
            st.rerun()
        if b.button("锁定选中", key=f"workspace_terms_lock_{job_id}", disabled=not ids, width="stretch"):
            core.set_glossary_entry_status(job_id, ids, "locked")
            st.rerun()
        if c.button("冻结并继续翻译", type="primary", key=f"workspace_terms_freeze_{job_id}", width="stretch"):
            core.freeze_glossary(job_id, entries=_merge_edited_entries(entries, _df_to_entries(edited)), frozen_by="用户")
            st.session_state.pending_continue_job = job_id
            st.rerun()
    else:
        rows = [{"源术语": e.get("source", ""), "首选译名": e.get("preferred") or e.get("target", ""),
                 "状态": _TERM_STATUS_LABELS.get(str(e.get("status") or "provisional"), "待确认"),
                 "出现次数": len(e.get("occurrences") or [])}
                for e in entries]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=430)
    _render_project_promotion(job_id, state, entries)


def _render_project_promotion(job_id, state, entries):
    """Memory gate：把本任务已确认的术语与风格提升到项目记忆（人工动作）。

    这是"跨任务复用"真正发生的地方：只有提升过的内容才会被同项目的后续任务
    注入。因此这里必须说明清楚"会提升什么"，而不是给一个语义模糊的按钮。
    """
    project = core.project_for_job(job_id, state)
    if project is None:
        # 任务不属于任何项目：不静默落到默认项目，而是说明"复用需要一个容器"，
        # 并指向项目页。提升本身仍是人工动作，不会自动发生。
        with st.container(border=True):
            st.markdown('<div class="tp-field-head"><strong>项目记忆</strong>'
                        f'<span>本任务在系统工作区「{core.SYSTEM_PROJECT_NAME}」</span>'
                        '</div>', unsafe_allow_html=True)
            st.caption("系统工作区可以正常积累与提升记忆，但它的记忆面向所有未分类"
                       "任务。需要按项目隔离术语与风格时，在项目页创建项目，"
                       "再把本任务移入即可。")
            if st.button("前往项目页", key=f"promote_goto_projects_{job_id}",
                         width="stretch"):
                _open_project_list()
                st.rerun()
        return
    locked = [e for e in (entries or []) if str(e.get("status") or "") == "locked"]
    styles = [r for r in (state.get("confirmed_style_rules") or [])
              if str((r or {}).get("status") or "").lower() in
              {"approved", "confirmed", "locked"}]
    decisions = [a for a in (state.get("human_actions") or [])
                 if isinstance(a, dict)
                 and str(a.get("record_type") or "") == "human_decision"]
    injectable = bool(locked or styles)

    with st.container(border=True):
        st.markdown(f'<div class="tp-field-head"><strong>项目记忆</strong>'
                    f'<span>{escape(str(project["name"]))}</span></div>',
                    unsafe_allow_html=True)
        injected = state.get("project_memory") or {}
        if injected.get("project_id"):
            st.caption(f"本任务已注入项目记忆：锁定术语 "
                       f"{len(injected.get('injected_entry_ids') or [])} 条 · "
                       f"项目术语版本 v{injected.get('glossary_version') or '—'}")
        st.caption(f"可提升：锁定术语 {len(locked)} 条 · 已确认风格 {len(styles)} 条 · "
                   f"人工决定 {len(decisions)} 条")
        st.caption("只有提升后的内容才会被同项目的后续任务注入；候选术语与未审校译文不会进入项目记忆。")
        if st.button("提升到项目记忆", key=f"promote_project_{job_id}",
                     disabled=not injectable, width="stretch"):
            try:
                updated = core.promote_job_to_project(job_id, actor="用户", state=state)
            except ValueError as exc:
                st.error(f"提升失败：{exc}")
            else:
                if updated is None:
                    st.error("提升失败：任务状态不可用。")
                else:
                    view = core.project_memory_view(updated)
                    st.success(f"已提升到「{updated['name']}」：锁定术语 "
                               f"{view['glossary_count']} 条 · 风格 {view['style_rule_count']} 条 · "
                               f"人工决定 {view['human_decision_count']} 条")
                    st.rerun()
        if not injectable:
            st.caption("先锁定术语或确认风格规则，才有内容可提升。")


def _render_review_item_actions(
        job_id, state, selected, items, review_required, review_ready,
        review_runtime, translator_ready):
    """Keep the common human decisions beside the selected finding."""
    segment_id = selected.get("segment_id")
    suggested_target = selected.get("suggested_target") or ""
    with st.container(key=f"review_action_bar_{selected['id']}"):
        if selected["kind"] in {"failed", "stale", "missing"}:
            action_label = {"failed": "重试审校此段", "stale": "重新审校此段",
                            "missing": "审校此段"}[selected["kind"]]
            review_col, edit_col = st.columns([1.35, 1], gap="small")
            if review_col.button(action_label, type="primary", disabled=not review_ready,
                                 key=f'review_task_run_{selected["id"]}', width="stretch"):
                with st.spinner(f"正在审校第 {segment_id + 1} 段…"):
                    _run_review_with_runtime(
                        job_id, [segment_id], review_runtime, target_lang,
                        style_rules)
                refreshed = core.load_job_state(job_id) or state
                _select_next_review_item(refreshed, selected)
                segment_items = [item for item in _review_workbench(refreshed)["queue_items"]
                                 if item.get("segment_id") == segment_id]
                tone = "warning" if any(item.get("kind") == "failed"
                                        for item in segment_items) else "success"
                message = (f"第 {segment_id + 1} 段审校仍未完成，请重试。"
                           if tone == "warning" else
                           f"第 {segment_id + 1} 段已完成重新审校。")
                _set_workspace_flash(message, tone)
                st.rerun()
            if edit_col.button("修改译文", key=f'review_task_edit_{selected["id"]}',
                               width="stretch"):
                pair = (state.get("pairs") or [])[segment_id]
                st.session_state["selected_segment_id"] = _translation_segment_id(
                    job_id, segment_id, pair)
                st.session_state.workspace_section = "translation"
                st.rerun()
            if not review_ready:
                st.caption(f"{_review_runtime_missing_message()}；仍可先修改译文，或前往 AI 设置。")
            return True, ""

        note_key = f"workspace_review_note_{selected['id']}"
        with st.expander("处理说明（可选）", expanded=False):
            st.text_input("说明", key=note_key, label_visibility="collapsed",
                          placeholder="添加本次决定的说明…")
        note = st.session_state.get(note_key, "")
        action_disabled = not selected.get("decidable")
        decision_capable = (not selected.get("core_finding")
                            or selected.get("requires_human_confirmation"))
        primary_label = ("应用建议并复审" if suggested_target and review_required else
                         "应用建议" if suggested_target else
                         "确认已解决" if decision_capable else "查看下一项")
        primary_disabled = action_disabled or bool(
            suggested_target and review_required and not review_ready)
        primary_col, edit_col, preserve_col = st.columns([1.55, 1, 1.2], gap="small")
        if primary_col.button(primary_label, type="primary", disabled=primary_disabled,
                              key=f'review_resolve_{selected["id"]}', width="stretch"):
            if not suggested_target and not decision_capable:
                next_id = _workbench_view.next_queue_item_id(
                    items, selected["id"], selected.get("segment_id"))
                _select_review_item(_workbench_view.select_queue_item(items, next_id))
                _set_workspace_flash("此建议已查看；它不会阻止交付。", "info")
                st.rerun()
            if review_required and selected.get("core_finding") and selected.get(
                    "requires_human_confirmation"):
                core.decide_translation_review_finding(
                    job_id, selected["core_finding_id"],
                    "request_revision" if suggested_target else "accept_resolution",
                    "user", actor_type="human",
                    note=note or ("应用建议译文并重新审校" if suggested_target
                                  else "人工核对后确认问题已解决"))
            if suggested_target and isinstance(segment_id, int):
                core.save_translation_edit(job_id, segment_id, suggested_target,
                                           actor="reviewer")
                if not review_required or not selected.get("core_finding"):
                    core.mark_findings_resolved(
                        job_id, [selected["finding_id"]], "human_fixed",
                        note or "应用建议译文")
                if review_required:
                    _run_review_with_runtime(
                        job_id, [segment_id], review_runtime, target_lang,
                        style_rules)
                message = ""
            elif decision_capable:
                if not review_required or not selected.get("core_finding"):
                    core.mark_findings_resolved(
                        job_id, [selected["finding_id"]], "human_fixed",
                        note or "人工核对后确认问题已解决")
                message = "已确认问题解决。该决定已记录。"
            refreshed = core.load_job_state(job_id) or state
            if suggested_target and review_required:
                segment_items = [item for item in _review_workbench(refreshed)["queue_items"]
                                 if item.get("segment_id") == segment_id]
                if any(item.get("kind") == "failed" for item in segment_items):
                    message = (f"建议译文已应用，但第 {segment_id + 1} 段审校未完成，"
                               "请重试。")
                elif segment_items:
                    message = (f"建议译文已应用并重新审校；第 {segment_id + 1} 段仍有"
                               f" {len(segment_items)} 项当前任务。")
                else:
                    message = f"建议译文已应用，第 {segment_id + 1} 段已完成重新审校。"
            elif suggested_target:
                message = "建议译文已应用。"
            _select_next_review_item(refreshed, selected)
            _set_workspace_flash(message, "warning" if "未完成" in message else "success")
            st.rerun()
        if edit_col.button("修改译文", key=f'review_edit_{selected["id"]}',
                           disabled=not isinstance(segment_id, int), width="stretch"):
            pair = (state.get("pairs") or [])[segment_id]
            st.session_state["selected_segment_id"] = _translation_segment_id(
                job_id, segment_id, pair)
            st.session_state.workspace_section = "translation"
            st.rerun()
        if preserve_col.button("保留当前译文",
                               disabled=action_disabled or not decision_capable,
                               key=f'review_preserve_{selected["id"]}', width="stretch"):
            if review_required and selected.get("core_finding") and selected.get(
                    "requires_human_confirmation"):
                core.decide_translation_review_finding(
                    job_id, selected["core_finding_id"], "dismiss", "user",
                    actor_type="human", note=note or "人工确认保留当前译文")
            else:
                core.mark_findings_resolved(
                    job_id, [selected["finding_id"]], "preserved",
                    note or "人工确认保留当前译文")
            refreshed = core.load_job_state(job_id) or state
            _select_next_review_item(refreshed, selected)
            _set_workspace_flash("已保留当前译文。该决定已记录。")
            st.rerun()
        if action_disabled:
            st.warning("此发现来自临时定位，无法安全记录人工决定；请先修改或重新审校该段。")
        elif not decision_capable:
            st.caption("该建议不需要人工决定，也不会阻止交付；可修改译文、应用建议或查看下一项。")
        elif suggested_target and review_required and not review_ready:
            st.caption(f"{_review_runtime_missing_message()}；也可以先修改译文或保留当前译文。")

        retranslate_label = "重新翻译并复审" if review_required else "重新翻译"
        retranslate_disabled = (not translator_ready or action_disabled
                                or (review_required and not review_ready)
                                or not isinstance(segment_id, int))
        if st.button(retranslate_label, disabled=retranslate_disabled,
                     key=f'review_retranslate_{selected["id"]}', width="stretch"):
            if review_required and selected.get("core_finding") and selected.get(
                    "requires_human_confirmation"):
                core.decide_translation_review_finding(
                    job_id, selected["core_finding_id"], "request_revision", "user",
                    actor_type="human", note=note or "请求重新翻译并复审")
            spinner_label = (f"正在重新翻译并审校第 {segment_id + 1} 段…"
                             if review_required else
                             f"正在重新翻译第 {segment_id + 1} 段…")
            with st.spinner(spinner_label):
                core.retranslate_segments(
                    job_id, [segment_id], ai_provider, api_key, ai_model,
                    target_lang, style_rules=style_rules,
                    reviewer_provider=review_runtime["provider"],
                    reviewer_api_key=review_runtime["api_key"],
                    reviewer_model=review_runtime["model"],
                    reviewer_base_url=review_runtime["base_url"],
                    on_caption=lambda text: st.caption(text))
            refreshed = core.load_job_state(job_id) or state
            _select_next_review_item(refreshed, selected)
            segment_items = [item for item in _review_workbench(refreshed)["queue_items"]
                             if item.get("segment_id") == segment_id]
            if not review_required:
                _set_workspace_flash("重新翻译完成。")
            elif any(item.get("kind") == "failed" for item in segment_items):
                _set_workspace_flash("重新翻译完成，但重新审校未完成，请重试。", "warning")
            else:
                _set_workspace_flash("重新翻译完成，已完成重新审校。")
            st.rerun()
    return False, note


def _render_workspace_review(job_id, state):
    view = _review_workbench(state)
    readiness = view["readiness"]
    progress = view["progress"]
    items = view["queue_items"]
    primary = view["primary_action"]
    review_runtime = resolve_review_runtime()
    review_required = bool(state.get("translation_core_review_required"))
    review_ready = _review_runtime_ready(review_runtime)
    translator_ready = bool(api_key and ai_model)
    review_progress_value = (f"{progress['current']} / {progress['total']}"
                             if review_required else "不适用")
    review_progress_label = ("段已有最新审校结果"
                             if review_required else "当前任务未启用独立审校")
    st.markdown('<div class="tp-review-head"><div><div class="tp-section-kicker">人工工作区</div>'
                '<h2>审校工作台</h2></div>'
                f'<div class="tp-review-count">{len(items):,} 项当前任务</div></div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="tp-review-readiness is-{readiness["tone"]}">'
        '<div><span>当前状态</span>'
        f'<strong>{escape(readiness["label"])}</strong>'
        f'<p>{escape(readiness["detail"])}</p></div>'
        f'<div class="tp-review-progress"><b>{review_progress_value}</b>'
        f'<span>{review_progress_label}</span></div>'
        '<div class="tp-review-progress-grid">'
        f'<span><b>{progress["blocking"]}</b> 必须处理</span>'
        f'<span><b>{progress["actionable"]}</b> 建议检查</span>'
        f'<span><b>{progress["stale"]}</b> 需要重新审校</span>'
        f'<span><b>{progress["failed"]}</b> 审校未完成</span>'
        f'<span><b>{progress["missing"]}</b> 尚未审校</span>'
        '</div></div>', unsafe_allow_html=True)
    if not review_required:
        if not items:
            st.info("当前任务未启用独立审校，此页不适用。当前译文可直接进入交付。")
            if st.button("前往交付", type="primary", key=f"review_not_required_delivery_{job_id}", width="stretch"):
                st.session_state.workspace_section = "delivery"
                st.rerun()
            return
        st.info("当前任务未启用独立审校；以下是基础检查发现，仅需人工处理，不会触发独立审校。")
    primary_disabled = primary["kind"] == "review_segments" and not review_ready
    if primary["kind"] != "handle_finding":
        with st.container(key=f"review_primary_action_{job_id}"):
            if st.button(primary["label"], type="primary", disabled=primary_disabled,
                         key=f"review_primary_{job_id}_{primary['kind']}"):
                if primary["kind"] == "review_segments":
                    with st.spinner("正在审校所选段落…"):
                        _run_review_with_runtime(
                            job_id, primary["segment_ids"], review_runtime, target_lang,
                            style_rules)
                    refreshed = core.load_job_state(job_id) or state
                    selected = _workbench_view.select_queue_item(
                        _review_workbench(refreshed)["queue_items"])
                    _select_review_item(selected)
                    _set_workspace_flash("审校已完成；工作台已更新为当前结果。")
                else:
                    st.session_state.workspace_section = "delivery"
                st.rerun()
        if primary_disabled:
            st.warning(f"{_review_runtime_missing_message()}，无法运行审校。")
            if st.button("前往 AI 设置", key=f"review_open_settings_{job_id}", width="stretch"):
                st.session_state.app_view = "settings"
                st.session_state.workspace_mode = False
                st.rerun()

    if not items:
        _select_review_item(None)
        st.markdown('<div class="tp-empty">当前没有待处理审校任务。</div>',
                    unsafe_allow_html=True)
        return

    filter_names = [
        ("pending", "待处理"), ("rereview", "需复审"),
        ("suggested", "建议"), ("reference", "参考"), ("all", "全部"),
    ]
    filter_options = [f"{label} {view['filter_counts'][name]}"
                      for name, label in filter_names]
    label_to_filter = {option: name for option, (name, _label)
                       in zip(filter_options, filter_names)}
    default_filter = ("rereview" if view["filter_counts"]["rereview"] else
                      "pending" if view["filter_counts"]["pending"] else
                      "suggested" if view["filter_counts"]["suggested"] else
                      "reference" if view["filter_counts"]["reference"] else "all")
    default_label = next(option for option, name in label_to_filter.items()
                         if name == default_filter)
    filter_key = f"workspace_review_filter_chips_{job_id}"
    if st.session_state.get(filter_key) not in filter_options:
        st.session_state[filter_key] = default_label
    filter_value = st.segmented_control(
        "筛选审校任务", filter_options, key=filter_key,
        label_visibility="collapsed", width="stretch") or default_label
    visible = _workbench_view.filter_queue_items(items, label_to_filter[filter_value])
    if not visible:
        _select_review_item(None)
        st.info("当前筛选下没有审校任务。")
        return
    selected = _selected_review_item(view, visible)
    action_terminal, note = _render_review_item_actions(
        job_id, state, selected, items, review_required, review_ready,
        review_runtime, translator_ready)
    if action_terminal:
        return

    queue_col, editor_col = st.columns([0.78, 2.72], gap="medium")
    with queue_col:
        st.markdown(f'<h3>工作队列 <span class="tp-review-queue-count">{len(visible)}</span></h3>',
                    unsafe_allow_html=True)
        st.caption("失败与过期任务优先，其次是当前必须处理的问题。")
        queue_labels, label_to_id = [], {}
        for item in visible:
            detail = (item.get("summary") or "请检查当前任务")[:54]
            if item.get("kind") == "finding":
                detail = f'{item["status_label"]} · {detail}'
            base = f'{item["title"]}\n{detail}'
            label = base
            occurrence = 1
            while label in label_to_id:
                occurrence += 1
                label = f"{base} · 位置 {occurrence}"
            queue_labels.append(label)
            label_to_id[label] = item["id"]
        queue_key = f"workspace_review_queue_{job_id}"
        selected_label = next(label for label, item_id in label_to_id.items()
                              if item_id == selected["id"])
        if st.session_state.get(queue_key) not in label_to_id:
            st.session_state[queue_key] = selected_label
        selected_label = st.radio(
            "审校队列", queue_labels, key=queue_key,
            label_visibility="collapsed")
        selected = next(item for item in visible
                        if item["id"] == label_to_id[selected_label])
        _select_review_item(selected)

    with editor_col:
        st.markdown(f'<div class="tp-segment-label">第 {selected["segment_number"]} 段 · '
                    f'{escape(selected["status_label"])} · '
                    f'{escape(selected.get("category_label") or "审校任务")}</div>',
                    unsafe_allow_html=True)
        if selected["kind"] == "stale":
            st.warning("此段译文已在上次审校后修改；旧结果已保留为历史，但不再适用于当前译文。")
        elif selected["kind"] == "failed":
            st.error("上次独立审校未完成。当前译文尚未获得有效审校结果。")
        elif selected["kind"] == "missing":
            st.info("此段尚未完成独立审校。")
        summary = selected.get("summary") or "请检查当前审校任务"
        st.markdown('<div class="tp-review-diagnostic-label">问题是什么</div>'
                    f'<div class="tp-review-diagnostic-copy tp-review-summary">{escape(summary)}</div>',
                    unsafe_allow_html=True)
        if selected.get("legacy_diagnostic"):
            st.markdown('<div class="tp-review-legacy">旧版本审校记录：仅保留基础问题信息，'
                        '请结合原文和当前译文人工判断。</div>', unsafe_allow_html=True)
        source_markup, source_found = _review_highlight(
            selected.get("source"), selected.get("source_span"))
        target_markup, target_found = _review_highlight(
            selected.get("target"), selected.get("target_span"))
        source_col, target_col = st.columns(2, gap="medium")
        with source_col:
            st.markdown('<div class="tp-review-compare-label">原文</div>'
                        f'<div class="tp-review-compare-text">{source_markup}</div>',
                        unsafe_allow_html=True)
            if selected.get("source_span") and not source_found:
                st.caption("记录的原文片段无法在当前段落中可靠定位。")
        with target_col:
            st.markdown('<div class="tp-review-compare-label">当前译文</div>'
                        f'<div class="tp-review-compare-text">{target_markup}</div>',
                        unsafe_allow_html=True)
            if selected.get("target_span") and not target_found:
                st.caption("记录的译文片段无法在当前译文中可靠定位。")
        suggested_target = selected.get("suggested_target") or ""
        if suggested_target:
            st.markdown('<div class="tp-review-suggestion"><span>系统建议</span>'
                        f'<p>{escape(suggested_target)}</p></div>', unsafe_allow_html=True)
        st.markdown('<div class="tp-review-diagnostic-label">为什么被标记</div>'
                    f'<p class="tp-review-diagnostic-copy">{escape(selected.get("explanation") or selected.get("reason") or "该旧记录未保存完整判断依据。")}</p>',
                    unsafe_allow_html=True)
        st.markdown('<div class="tp-review-diagnostic-label">建议怎么处理</div>'
                    f'<p class="tp-review-diagnostic-copy">{escape(selected.get("recommendation") or "核对原文和当前译文后，选择下方安全动作。")}</p>',
                    unsafe_allow_html=True)

        if selected.get("category") == "style":
            with st.expander("保存为项目风格规则", expanded=False):
                style_key = f'review_style_rule_{selected["id"]}'
                if style_key not in st.session_state:
                    st.session_state[style_key] = selected.get("recommendation") or ""
                st.text_area("规则", key=style_key,
                             help="只有点击确认保存后，规则才会成为项目知识。")
                if st.button("确认保存", key=f'review_style_confirm_{selected["id"]}',
                             width="stretch"):
                    core.confirm_translation_style_rule(
                        job_id, st.session_state.get(style_key, ""), "user",
                        actor_type="human", note=note,
                        source_finding_id=selected.get("core_finding_id") or "")
                    _set_workspace_flash("项目风格规则已由你确认保存。")
                    st.rerun()


def _case_origin_label(case):
    return _case_provenance.display_contract(case).get("origin_label") or "未分类案例"


def _case_review_status_label(status):
    value = str(status or "")
    return {"unreviewed": "待人工确认", "approved": "已批准纳入", "rejected": "已排除"}.get(
        value, "需人工确认" if value else "待人工确认")


def _case_state_label(value):
    return {
        "pass": "已通过", "fail": "未通过", "manual_review": "待人工复核",
        "not_checked": "未检查", "not_applicable": "不适用",
        "not_available": "尚未生成", "unreviewed": "未处理",
        "approved": "已确认", "rejected": "已拒绝", "modified": "已修改",
        "other": "其他",
    }.get(str(value or ""), "需确认" if value else "—")


def _case_identity_label(case):
    raw = str(case.get("case_id") or "")
    if raw.startswith("seg-"):
        index = case.get("segment_index")
        return f"第 {int(index) + 1} 段" if isinstance(index, int) else "真实修订案例"
    if raw.startswith(("LSC-", "SC-")):
        index = case.get("segment_index")
        return f"第 {int(index) + 1} 段" if isinstance(index, int) else "案例"
    return "案例" if raw else "未命名案例"


def _case_review_is_stale(case, state):
    case_id = str(case.get("case_id") or "")
    if bool(case.get("content_stale")):
        return True
    academic = state.get("academic_state") or {}
    artifact = (academic.get("artifacts") or {}).get(f"case:{case_id}") or {}
    if artifact.get("status") == "stale":
        return True
    impact = state.get("dependency_impact") or {}
    if case_id in {str(value) for value in impact.get("affected_case_ids") or []}:
        return True
    return False


def _case_validity_label(case, state):
    if _case_review_is_stale(case, state):
        return "需要重新检查", "stale"
    if case.get("review_status") == "rejected" or case.get("baseline_status") == "rejected":
        return "已排除", "stale"
    if case.get("review_status") == "unreviewed":
        return "待人工确认", "pending"
    return "可复用", "valid"


def _render_workspace_cases(job_id, state):
    selected = core.load_academic_artifact(job_id, "selected_cases") or {}
    views = _workspace_case_views(job_id, state)
    st.markdown('<div class="tp-section-kicker">案例与人工确认</div><h2>案例终审</h2>'
                '<div class="tp-section-lead">逐例确认案例是否可纳入学术分析；批准不会把合成对照变成历史初译。</div>',
                unsafe_allow_html=True)
    truth = core.translation_truth_view(job_id, state)
    st.markdown(
        '<div class="tp-truth-banner">'
        '<div><span class="tp-truth-kicker">案例引用依据</span>'
        '<strong>案例引用以当前译文为准</strong>'
        f'<p>所有案例的“当前译文”都来自工作译文 v{truth["version"]}；修改当前译文后，受影响的案例会提示重新确认。</p>'
        '</div></div>', unsafe_allow_html=True)
    if not views:
        st.markdown('<div class="tp-empty">尚未生成案例选择产物。</div>', unsafe_allow_html=True)
        return
    filter_origin, filter_status, filter_search = st.columns([1, 1, 1.6], gap="small")
    with filter_origin:
        origin_filter = st.selectbox(
            "案例来源", ["全部", "真实修订", "合成对照", "翻译决策"],
            key=f"case_origin_filter_{job_id}", label_visibility="collapsed")
    with filter_status:
        status_filter = st.selectbox(
            "审校状态", ["全部", "待人工确认", "已批准纳入", "已排除"],
            key=f"case_status_filter_{job_id}", label_visibility="collapsed")
    with filter_search:
        case_search = st.text_input(
            "搜索案例", key=f"case_search_{job_id}",
            placeholder="搜索段落、原文或译文…", label_visibility="collapsed")
    needle = str(case_search or "").strip().casefold()
    filtered = [item for item in views
                if (origin_filter == "全部" or _case_origin_label(item) == origin_filter)
                and (status_filter == "全部" or
                     _case_review_status_label(item.get("review_status")) == status_filter)
                and (not needle or needle in " ".join(
                    str(value or "") for value in (
                        _case_identity_label(item), _case_origin_label(item),
                        _case_review_status_label(item.get("review_status")),
                        item.get("source_text"), item.get("current_text"),
                        item.get("target_subsection"), item.get("section_title"),
                    )).casefold())]
    if not filtered:
        st.info("当前筛选下没有案例。")
        return
    ids = [str(item.get("case_id")) for item in filtered]
    selected_id = str(st.session_state.get(f"selected_case_id_{job_id}") or "")
    if selected_id not in ids:
        selected_id = ids[0]
        st.session_state[f"selected_case_id_{job_id}"] = selected_id
    queue_col, detail_col = st.columns([1.35, 2.3], gap="medium")
    with queue_col:
        st.markdown(f'<h3>案例队列 <span class="tp-review-queue-count">{len(filtered)}</span></h3>',
                    unsafe_allow_html=True)
        labels = []
        label_ids = {}
        for index, item in enumerate(filtered, start=1):
            label = (f'{_case_identity_label(item)} · {_case_origin_label(item)} · '
                     f'{_case_review_status_label(item.get("review_status"))}')
            if label in label_ids:
                label = f'{label} · 第 {index} 项'
            labels.append(label)
            label_ids[label] = str(item.get("case_id"))
        queue_key = f"case_queue_{job_id}"
        current_label = next(label for label in labels if label_ids[label] == selected_id)
        if st.session_state.get(queue_key) not in labels:
            st.session_state[queue_key] = current_label
        chosen_label = st.selectbox(
            "案例队列", labels, key=queue_key, label_visibility="collapsed",
            help="选择一个案例查看证据并记录人工终审。")
        selected_id = label_ids[chosen_label]
        st.session_state[f"selected_case_id_{job_id}"] = selected_id
        approved = sum(item.get("review_status") == "approved" for item in views)
        excluded = sum(item.get("review_status") == "rejected" for item in views)
        st.caption(f"显示 {len(filtered)} / 总计 {len(views)} · 总计状态：已批准 {approved} · 已排除 {excluded} · 待人工确认 {len(views) - approved - excluded}")
    item = next(item for item in filtered if str(item.get("case_id")) == selected_id)
    display = _case_provenance.display_contract(item)
    lifecycle = item.get("artifact_status") or "not_available"
    with detail_col:
        validity_label, tone = _case_validity_label(item, state)
        stale = tone == "stale"
        status = _case_review_status_label(item.get("review_status"))
        st.markdown(
            f'<div class="tp-case-head"><div><div class="tp-section-kicker">当前选中 · {escape(_case_identity_label(item))}</div>'
            f'<h3>{escape(display["origin_label"])} · {escape(status)}</h3>'
            f'<p>{escape(display["origin_description"])}</p></div>'
            f'<span class="tp-case-validity is-{tone}">{validity_label}</span></div>',
            unsafe_allow_html=True)
        has_initial = bool(item.get("initial_text"))
        initial_role_label = (
            "模拟初译" if item.get("case_origin") == _case_provenance.SYNTHETIC_BASELINE
            else "历史初译" if has_initial else "无真实初译（不伪造对照）")
        role_rows = ['<span>原文</span><b>原文段落</b>']
        if item.get("case_origin") == _case_provenance.SYNTHETIC_BASELINE or has_initial:
            role_rows.append(
                f'<span>{escape(initial_role_label)}</span><b>{escape(initial_role_label)}</b>')
        role_rows.append('<span>当前译文</span><b>当前译文</b>')
        st.markdown('<div class="tp-case-role-grid">' + "".join(role_rows) + '</div>',
                    unsafe_allow_html=True)
        text_col_a, text_col_b = st.columns(2)
        with text_col_a:
            st.markdown(f'<div class="tp-case-text"><label>原文</label><p>{escape(item.get("source_text") or "—")}</p></div>', unsafe_allow_html=True)
            if item.get("initial_text"):
                st.markdown(f'<div class="tp-case-text"><label>{escape(display.get("initial_label") or "初始文本")}</label><p>{escape(item.get("initial_text"))}</p></div>', unsafe_allow_html=True)
        with text_col_b:
            st.markdown(f'<div class="tp-case-text"><label>当前译文</label><p>{escape(item.get("current_text") or "—")}</p></div>', unsafe_allow_html=True)
            context = " ".join(str(item.get(key) or "") for key in ("context_before", "context_after")).strip()
            if context:
                st.markdown(f'<div class="tp-case-text"><label>必要上下文</label><p>{escape(context)}</p></div>', unsafe_allow_html=True)
        st.markdown('<div class="tp-case-detail-label">分析与证据</div>', unsafe_allow_html=True)
        evidence = item.get("synthetic_evidence") or {}
        analysis = item.get("analysis_fields") or {}
        evidence_rows = [
            ("基线合理性", _case_state_label(evidence.get("baseline_plausibility"))),
            ("实质差异", _case_state_label(evidence.get("material_difference"))),
            ("修复正确性", _case_state_label(evidence.get("repair_correctness"))),
            ("分析价值", _case_state_label(evidence.get("academic_analysis_value"))),
            ("基线状态", ({"modified": "已修改", "rejected": "已拒绝",
                           "approved": "已确认", "unreviewed": "未处理"}.get(
                               item.get("baseline_status"), "不适用")
                       if item.get("case_origin") == _case_provenance.SYNTHETIC_BASELINE
                       else "不适用")),
            ("分析状态", "已保存" if analysis else "未提供"),
        ]
        case_plan = item.get("case_plan") or {}
        if case_plan:
            evidence_rows.extend([
                ("问题类型", _case_state_label((case_plan.get("problem") or {}).get("type"))),
                ("决策理由", "已保存" if case_plan.get("decision_rationale") else "未提供"),
                ("理论映射", "已保存" if case_plan.get("theory_mapping") else "未提供"),
            ])
        st.markdown('<div class="tp-case-evidence-grid">' + "".join(
            f'<span>{escape(label)}</span><b>{escape(str(value))}</b>'
            for label, value in evidence_rows) + '</div>', unsafe_allow_html=True)
        segment_index = item.get("segment_index")
        finding_count = len(item.get("case_findings") or [])
        target_section = item.get("target_subsection") or item.get("section_id") or "—"
        section_suffix = f' · {item.get("section_title")}' if item.get("section_title") else ""
        st.caption(f'关联位置：第 {int(segment_index) + 1 if isinstance(segment_index, int) else "—"} 段 · '
                   f'目标报告位置 {target_section}{section_suffix} · 相关审校发现 {finding_count} 条')
        if item.get("segment_current_text") and item.get("current_text") != item.get("segment_current_text"):
            st.caption("当前译文已按案例片段定位；完整段落真值仍以翻译工作区中的当前译文为准。")
        with st.expander("查看依赖与技术依据", expanded=False):
            st.caption(f'依赖状态：{"需要重建" if stale else "可复用"} · '
                       f'内部生命周期：{lifecycle} · 技术标识：{item.get("segment_id") or "—"}')
        with st.expander("查看关联证据", expanded=True):
            commentary = item.get("analytical_commentary") or []
            if commentary:
                st.markdown("**分析评论**")
                for entry in commentary:
                    st.markdown(f'**{escape(str(entry.get("label") or "说明"))}**：{escape(str(entry.get("value") or "—"))}')
            else:
                st.caption("尚未保存可展示的案例分析评论。")
            terms = item.get("related_terms") or []
            if terms:
                st.markdown("**相关术语**")
                for term in terms:
                    source = term.get("source") or term.get("term") or "—"
                    target = term.get("target") or term.get("preferred") or term.get("proposed_target") or "—"
                    st.markdown(f'- {escape(str(source))} → {escape(str(target))}')
            else:
                st.caption("未登记与本案例直接绑定的术语记录。")
            if item.get("case_findings"):
                st.markdown("**相关审校发现**")
                for finding in item.get("case_findings") or []:
                    severity = {"blocking": "必须处理", "actionable": "建议",
                                "informational": "参考"}.get(
                                    str(finding.get("severity") or ""), "审校发现")
                    st.markdown(f'- {escape(severity)} · {escape(str(finding.get("reason") or "审校发现"))}')
            else:
                st.caption("当前段落没有已登记的 finding。")
            if item.get("literature_evidence"):
                st.markdown("**文献证据**")
                for source in item.get("literature_evidence") or []:
                    st.markdown(f'- {escape(str(source.get("title") or source.get("source_id") or "—"))}')
            else:
                st.caption("未登记案例专属文献证据；当前分析边界仍以项目证据为准。")
            human_entries = item.get("human_evidence") or []
            if human_entries:
                st.markdown("**作者补充证据**")
                for entry in human_entries:
                    st.markdown(f'- {escape(str(entry.get("question_type") or "说明"))}: '
                                f'{escape(str(entry.get("answer") or "—"))}')
            else:
                st.caption("没有已确认的作者事后解释。")
        if item.get("review_note"):
            st.caption(f'人工确认说明：{item["review_note"]}')
        if item.get("reviewed_at"):
            st.caption(f'人工确认记录：{item.get("reviewed_at")} · {item.get("review_actor") or "user"}')
        if stale:
            st.warning("当前译文或输入已变化，此案例需要重新检查；旧批准不能直接交付。")
        action_a, action_b, action_c, action_d = st.columns(4)
        if action_a.button("批准纳入" if item.get("review_status") != "approved" else "保持批准",
                          type="primary", key=f"case_approve_{job_id}_{selected_id}",
                          disabled=item.get("review_status") == "approved" and not stale,
                          width="stretch"):
            core.review_academic_case(job_id, selected_id, "approved", actor="user")
            st.rerun()
        exclude_key = f"case_exclude_note_{job_id}_{selected_id}"
        with action_b:
            with st.popover("排除案例", use_container_width=True):
                note = st.text_area("排除原因", key=exclude_key, height=90,
                                    placeholder="说明为什么不纳入本次分析…")
                if st.button("确认排除", key=f"case_exclude_go_{job_id}_{selected_id}",
                             type="primary", width="stretch"):
                    if not note.strip():
                        st.warning("请填写排除原因。")
                    else:
                        core.review_academic_case(job_id, selected_id, "rejected", note, actor="user")
                        st.rerun()
        with action_c:
            if st.button("修改当前译文", key=f"case_edit_target_{job_id}_{selected_id}", width="stretch"):
                if segment_index is not None:
                    pair = (state.get("pairs") or [])[int(segment_index)]
                    st.session_state["selected_segment_id"] = _translation_segment_id(
                        job_id, int(segment_index), pair)
                st.session_state.workspace_section = "translation"
                st.rerun()
        with action_d:
            if st.button("从合格池替换", key=f"case_replace_{job_id}_{selected_id}",
                         disabled=item.get("review_status") != "rejected", width="stretch"):
                _state, ok, result = core.replace_rejected_case(
                    job_id, selected_id, actor="user")
                if not ok:
                    st.error(result[0] if isinstance(result, list) and result else str(result))
                else:
                    st.rerun()
        if item.get("case_origin") == _case_provenance.SYNTHETIC_BASELINE:
            st.markdown('<div class="tp-case-detail-label">模拟初译（分析对照，不是历史初译）</div>', unsafe_allow_html=True)
            baseline_key = f"case_baseline_{job_id}_{selected_id}"
            if baseline_key not in st.session_state:
                st.session_state[baseline_key] = item.get("initial_text") or ""
            baseline = st.text_area("模拟初译", key=baseline_key, height=110,
                                    label_visibility="collapsed")
            base_a, base_b = st.columns(2)
            if base_a.button("保存修改模拟初译", key=f"case_baseline_save_{job_id}_{selected_id}", width="stretch"):
                _state, ok, message = core.update_synthetic_baseline(
                    job_id, selected_id, baseline, status="modified", actor="user")
                if not ok:
                    st.error(message)
                else:
                    st.rerun()
            if base_b.button("拒绝模拟初译", key=f"case_baseline_reject_{job_id}_{selected_id}", width="stretch"):
                core.update_synthetic_baseline(job_id, selected_id, baseline,
                                               status="rejected", actor="user")
                st.rerun()


def _render_workspace_cases_context(job_id, state):
    views = _workspace_case_views(job_id, state)
    pending = sum(item.get("review_status") == "unreviewed" for item in views)
    synthetic = sum(item.get("case_origin") == _case_provenance.SYNTHETIC_BASELINE for item in views)
    real = sum(item.get("case_origin") == _case_provenance.REAL_REVISION for item in views)
    st.markdown('<div class="tp-info-card"><h3>案例状态</h3>'
                f'<div class="tp-info-stat"><span>案例总数</span><b>{len(views)}</b></div>'
                f'<div class="tp-info-stat"><span>真实修订</span><b>{real}</b></div>'
                f'<div class="tp-info-stat"><span>合成对照</span><b>{synthetic}</b></div>'
                f'<div class="tp-info-stat"><span>尚未审校</span><b>{pending}</b></div>'
                '</div>', unsafe_allow_html=True)
    impact = core.dependency_impact_view(job_id, state)
    if impact.get("status") == "stale":
        st.markdown('<div class="tp-info-card"><h3>最近依赖变化</h3>'
                    f'<p class="tp-inspector-preview">{escape(_workspace_impact_reason(impact))}</p>'
                    f'<p class="tp-inspector-preview">{len(impact.get("affected") or [])} 项下游内容需要更新 · '
                    f'{len(impact.get("reusable") or [])} 个未受影响单元/资产可复用</p></div>',
                    unsafe_allow_html=True)


def _render_workspace_qa(job_id, state):
    """Compliance, independent QA facts, and the explicit finalization gate."""
    st.markdown('<div class="tp-section-kicker">交付检查</div><h2>合规与最终 QA</h2>'
                '<div class="tp-section-lead">每一项检查都独立决定一件事；结构检查和页面渲染通过，也不等于作者与 Word 最终复核已确认。</div>',
                unsafe_allow_html=True)
    compliance = _workspace_compliance_view(job_id, state)
    profile_id = str(state.get("compliance_profile_id") or
                     _compliance.DEFAULT_PROFILE_ID)
    profile = _compliance.compliance_profile(profile_id)
    counts = compliance.get("counts") or {}
    qa = _finalization.normalize_final_qa(state.get("final_qa"))
    structural = _workspace_structural_qa(job_id, state)
    render_status = qa.get("libreoffice_render")
    failed_count = int(counts.get("fail", 0) or 0) + int(structural == "FAIL") + int(render_status == "FAIL")
    manual_count = int(counts.get("manual_review", 0) or 0)
    manual_count += int(qa.get("author_visual_review") != "CONFIRMED")
    manual_count += int(qa.get("word_final_review") != "CONFIRMED")
    not_run_count = int(counts.get("not_checked", 0) or 0)
    not_run_count += int(structural in {"NOT_RUN", "STALE"})
    not_run_count += int(render_status in {None, "NOT_RUN", "STALE"})
    attention_count = failed_count + manual_count + not_run_count
    source_mapping_label = {
        "reference_template_mapped": "已登记匿名参考模板",
    }.get(profile.get("authority_mapping_status"), "院校特殊要求需人工确认")
    st.markdown(
        '<div class="tp-qa-profile"><strong>研究与报告（专用能力）</strong>'
        f'<span>{escape(str(profile.get("display_name") or "默认 MTI 实践报告规范"))} · {escape(source_mapping_label)}</span>'
        f'<b>通过 {counts.get("pass", 0)} · 失败 {counts.get("fail", 0)} · 人工复核 {counts.get("manual_review", 0)} · 未检查 {counts.get("not_checked", 0)}</b>'
        '</div>', unsafe_allow_html=True)
    if attention_count:
        summary_parts = []
        if failed_count:
            summary_parts.append(f"{failed_count} 项自动检查失败")
        if manual_count:
            summary_parts.append(f"{manual_count} 项需要人工复核")
        if not_run_count:
            summary_parts.append(f"{not_run_count} 项尚未运行")
        with st.container(key=f"qa_work_summary_{job_id}"):
            st.markdown(
                '<div class="tp-qa-work-summary"><strong>还有 '
                f'{attention_count} 项需要处理</strong><span>{" · ".join(summary_parts)}</span></div>',
                unsafe_allow_html=True)
            if st.button("处理阻塞项", type="primary", key=f"qa_focus_{job_id}", width="stretch"):
                st.session_state[f"qa_focus_rules_{job_id}"] = True
                st.rerun()
    with st.expander("查看规则集技术依据", expanded=False):
        st.markdown(
            f'**规则集内部标识**：`{escape(str(profile.get("profile_id") or "—"))}`')
        mapping_status = profile.get("authority_mapping_status")
        mapping_label = {
            "reference_template_mapped": "已登记匿名参考模板",
        }.get(mapping_status, "院校特殊要求需人工确认")
        st.caption(f'参考映射状态：{mapping_label}')
        for source in profile.get("sources") or profile.get("source_documents") or []:
            st.caption(f'参考来源记录：{source.get("document") or source.get("title") or source.get("file") or "—"} · '
                       f'{source.get("note") or source.get("authority") or ""}')
        for source in profile.get("implementation_sources") or []:
            st.caption(f'项目实现依据（非规范来源）：{source.get("document") or source.get("file") or "—"}')
    st.markdown('<h3 class="tp-qa-heading">合规检查清单</h3>', unsafe_allow_html=True)
    focus_rules = bool(st.session_state.get(f"qa_focus_rules_{job_id}"))
    for index, rule in enumerate(compliance.get("rules") or []):
        status = str(rule.get("status") or "not_checked")
        label = {"pass": "通过", "fail": "失败", "manual_review": "手动复核",
                 "not_applicable": "不适用", "not_checked": "未检查"}.get(status, status)
        rule_label = (rule.get("description") or rule.get("label") or
                      rule.get("rule_id") or rule.get("id") or "合规规则")
        source = rule.get("source") or {}
        applicability = rule.get("scope") or rule.get("applicability") or "—"
        check_level = rule.get("check_type") or rule.get("check_level") or "—"
        check_level_label = {"deterministic": "自动检查", "manual": "人工检查",
                             "project_constraint": "项目约束"}.get(str(check_level), str(check_level))
        authority = rule.get("authority_level") or ""
        authority_label = {"project": "项目约束",
                           "reference_template": "默认参考模板",
                           "custom_profile": "用户自定义院校规则"}.get(
                               str(authority), "未映射的自定义规则" if not (
                                   rule.get("source_available") or
                                   rule.get("reliable_source_mapping") or
                                   source.get("available"))
                               else str(source.get("authority") or "—"))
        source_document = rule.get("source_document") or source.get("file")
        has_rule_source = (
            rule.get("source_kind") in {"reference_template", "custom_profile"} and
            rule.get("authority_level") != "project" and
            (rule.get("source_available") or
             rule.get("reliable_source_mapping") or source.get("available")))
        rule_source = (source_document if has_rule_source else
                       "院校特殊要求需根据实际模板确认")
        with st.container(key=f"qa_rule_{job_id}_{index}"):
            st.markdown(
                f'<div class="tp-qa-rule is-{status}"><div><strong>{escape(str(rule_label))}</strong>'
                f'<p>{escape(str(rule.get("message") or ""))}</p>'
                f'</div><span>{escape(label)}</span></div>', unsafe_allow_html=True)
            with st.expander("查看来源与技术细节", expanded=focus_rules and status in {"fail", "manual_review", "not_checked"}):
                st.caption(f'规则来源：{rule_source} · 页码/条款：{rule.get("page_or_clause") or source.get("page") or "待提供"}')
                source_url = rule.get("source_url") or source.get("url") or ""
                if source_url and has_rule_source:
                    st.markdown(f'来源链接：[打开来源]({source_url})')
                st.caption(f'适用范围：{applicability} · 检查方式：{check_level_label} · 规则层级：{authority_label}')
                implementation_source = rule.get("implementation_source")
                implementation_clause = rule.get("implementation_clause") or rule.get("source_clause")
                if implementation_source:
                    st.caption(f'项目实现依据（非规范来源）：{implementation_source} · {implementation_clause or "—"}')
                st.caption(f'内部状态：{status} · 规则标识：{rule.get("rule_id") or rule.get("id") or "—"}')
    if structural in {"PASS", "FAIL", "NOT_RUN"} and structural != qa.get("structural_qa"):
        qa["structural_qa"] = structural
        state["final_qa"] = qa
        core.save_job_state(job_id, state)
    st.markdown('<h3 class="tp-qa-heading">独立最终质量事实</h3>', unsafe_allow_html=True)
    qa_rows = [
        ("structural_qa", "DOCX 结构检查", structural, "文档结构、段落与确定性规则"),
        ("libreoffice_render", "LibreOffice 页面渲染", qa.get("libreoffice_render"), "DOCX 转 PDF 页面预检"),
        ("author_visual_review", "作者视觉复核", qa.get("author_visual_review"), "作者检查关键页面与版式"),
        ("word_final_review", "Word 最终复核", qa.get("word_final_review"), "Word 更新字段并确认最终页面"),
    ]
    for field, label, status, proof in qa_rows:
        with st.container(key=f"qa_fact_{job_id}_{field}"):
            left, right = st.columns([3.1, 1.1], gap="small")
            with left:
                st.markdown(f'<div class="tp-qa-fact"><strong>{escape(label)}</strong><span>{escape(proof)}</span></div>', unsafe_allow_html=True)
            with right:
                status_class = "stale" if status == "STALE" else str(status).lower()
                status_label = "需要重建" if status == "STALE" else _finalization.final_qa_label(
                    str(field), str(status))
                st.markdown(f'<div class="tp-qa-status is-{status_class}">{escape(status_label)}</div>', unsafe_allow_html=True)
            if field == "libreoffice_render":
                if st.button("运行 LibreOffice 页面预检", key=f"qa_run_lo_{job_id}",
                             disabled=not bool(state.get("p2_done")), width="stretch"):
                    try:
                        core.run_libreoffice_render_qa(job_id)
                        st.rerun()
                    except RuntimeError as exc:
                        st.error(str(exc))
            elif field in {"author_visual_review", "word_final_review"}:
                button_label = "确认已完成" if status != "CONFIRMED" else "撤销确认"
                next_status = "CONFIRMED" if status != "CONFIRMED" else "NOT_CONFIRMED"
                if st.button(button_label, key=f"qa_confirm_{job_id}_{field}", width="stretch"):
                    core.record_final_qa(job_id, field, next_status,
                                        "人工在最终 QA 工作区记录", actor="user")
                    st.rerun()
    if qa.get("libreoffice_render") == "PASS":
        st.caption(f'渲染记录：{qa.get("page_count") or "—"} 页 · 当前 DOCX 已渲染并保存 PDF 页面预检结果。')
        render_record = core.load_academic_artifact(job_id, "libreoffice_render") or {}
        from transpraxis import rendered_qa as _rendered_qa
        st.markdown("#### 关键页面定位（作者需在 Word 中复核）")
        st.dataframe(pd.DataFrame(_rendered_qa.key_page_references(render_record)),
                     hide_index=True, width="stretch")
    st.warning("只有以上四项独立质量事实和合规门禁都分别满足要求，才能把版本标为最终确认。")


def _render_workspace_qa_context(job_id, state):
    qa = _finalization.normalize_final_qa(state.get("final_qa"))
    compliance = _workspace_compliance_view(job_id, state)
    snapshot = core.delivery_snapshot_status(job_id, state)
    structural = _workspace_structural_qa(job_id, state)
    render_status = _finalization._artifact_status_value(
        state.get("academic_state") or {}, "libreoffice_render")
    structural_label = {"PASS": "已通过", "FAIL": "失败", "STALE": "需要重建",
                         "NOT_RUN": "尚未运行"}.get(structural, "尚未运行")
    render_label = ("需要重建" if render_status in {"stale", "missing"} else
                    "失败" if render_status == "failed" or qa.get("libreoffice_render") == "FAIL" else
                    "已通过" if qa.get("libreoffice_render") == "PASS" else "尚未运行")
    author_label = "已确认" if qa.get("author_visual_review") == "CONFIRMED" else "尚未确认"
    word_label = "已确认" if qa.get("word_final_review") == "CONFIRMED" else "尚未确认"
    delivery_label, _ = _workspace_delivery_state(job_id, state)
    st.markdown('<div class="tp-info-card"><h3>交付门禁</h3>'
                f'<div class="tp-info-stat"><span>合规失败</span><b>{(compliance.get("counts") or {}).get("fail", 0)}</b></div>'
                f'<div class="tp-info-stat"><span>DOCX 结构</span><b>{structural_label}</b></div>'
                f'<div class="tp-info-stat"><span>页面渲染</span><b>{render_label}</b></div>'
                f'<div class="tp-info-stat"><span>作者 / Word</span><b>{author_label} / {word_label}</b></div>'
                f'<div class="tp-info-stat"><span>交付判断</span><b>{delivery_label}</b></div>'
                f'<div class="tp-info-stat"><span>最近冻结</span><b>{"v" + str((snapshot.get("latest") or {}).get("snapshot_version")) if snapshot.get("latest") else "尚未生成"}</b></div>'
                '</div>', unsafe_allow_html=True)


_REPORT_CASE_ISSUES = {
    "case_count_status_mismatch", "insufficient_core_revision_cases",
    "invalid_selected_case", "non_revision_case_used_as_revision_analysis",
    "synthetic_pipeline_unavailable", "synthetic_only_without_eligible_cases",
    "ineligible_synthetic_case_selected", "synthetic_case_provenance_mismatch",
    "duplicate_selected_case_presentation",
    "case_presentation_count_mismatch",
    "case_minimum_not_met", "case_coverage_below_recommended",
    "duplicate_canonical_case", "missing_focus_span",
    "focus_span_outside_canonical", "focus_excerpt_excessively_long",
    "full_segment_rendered_as_case", "case_node_focus_mismatch",
    "case_numbering_not_continuous", "case_hierarchy_missing",
    "case_distribution_severely_unbalanced",
    "research_question_case_coverage_insufficient",
    "case_presentation_contract_violation",
}
_REPORT_SECTION_ISSUES = {
    "missing_required_section", "section_too_short", "missing_planned_claim",
    "missing_research_question_link", "missing_selected_case",
    "missing_planned_literature_claim", "missing_planned_literature_evidence",
    "section_literature_outside_plan", "section_literature_claim_outside_plan",
    "section_literature_evidence_outside_plan", "section_literature_source_outside_plan",
}
_REPORT_STATISTIC_ISSUES = {
    "unknown_project_statistic", "wrong_project_statistic",
    "unresolved_statistic_token", "unmarked_project_statistic",
}
_REPORT_TEMPLATE_ISSUES = {
    "template_chapter_count_mismatch", "template_missing_chapter",
    "template_chapter_order_mismatch", "template_chapter_title_mismatch",
    "template_missing_subsection", "template_subsection_level_mismatch",
    "template_subsection_order_mismatch", "template_extra_subsection",
    "template_extra_chapter", "template_hash_mismatch", "template_matter_mismatch",
    "template_case_role_missing", "template_case_role_mismatch",
    "template_case_mapping_mismatch", "template_case_minimum_not_met",
    "template_front_matter_content_missing", "template_internal_id_visible",
    "template_unresolved_marker", "template_duplicate_rendering",
    "template_duplicate_heading",
}


def _report_artifacts(job_id):
    return {
        name: core.load_academic_artifact(job_id, name)
        for name in (
            "evidence", "argument_plan", "selected_cases", "outline", "report", "validation", "review",
            "literature_sources", "literature_evidence", "literature_claims",
            "literature_support_review", "academic_quality",
            "human_evidence_questions",
            "final_docx_validation",
        )
    }


def _report_quality_label(status):
    return {
        "pass": "已验证", "pass_with_warnings": "已验证 · 有警告",
        "review_required": "需要复核", "fail": "需要复核",
        "literature_required": "需要补充文献",
        "failed": "生成失败", "not_started": "未生成",
        "stale": "需要更新（按影响范围）", "in_progress": "生成中",
    }.get(status, "—")


def _report_validation_label(status):
    return {
        "pass": "通过", "pass_with_warnings": "通过 · 有警告",
        "fail": "需要复核", "review_required": "需要复核",
        "not_configured": "未配置模板",
    }.get(status, "未生成")


def _report_literature_status(artifacts):
    sources = (artifacts.get("literature_sources") or {}).get("sources") or []
    evidence = (artifacts.get("literature_evidence") or {}).get("items") or []
    claims = (artifacts.get("literature_claims") or {}).get("items") or []
    if not sources:
        return "尚未建立"
    if not evidence or not claims:
        return "待补证据"
    if any(item.get("evidence_grounded_status") in {"needs_review", "review_required"}
           for item in claims):
        return "需要复核"
    return "已登记"


def _report_updated_label(job_id, state, academic):
    value = academic.get("updated_at") or \
        (core.recovery_summary(job_id, state) or {}).get("last_saved_at")
    return _format_saved_at(value) if value else "最近"


def _report_docx_bytes(state, frozen_assets=None):
    """Use the persisted template renderer for Report and Delivery surfaces."""
    job_id = st.session_state.get("active_job_id")
    if not job_id:
        return None
    return core.report_docx_bytes(job_id, state, frozen_assets=frozen_assets)


def _report_heading_title(value):
    value = re.sub(r"\s+#+\s*$", "", str(value or "")).strip()
    return value


def _report_heading_key(value):
    value = _report_heading_title(value).casefold()
    value = re.sub(r"^\d+(?:\.\d+)*[.、．]?\s*", "", value)
    return re.sub(r"\s+", "", value)


def _report_headings(report):
    headings = []
    for line_index, line in enumerate(str(report or "").splitlines()):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        title = _report_heading_title(match.group(2))
        if not title:
            continue
        headings.append({
            "line_index": line_index,
            "level": len(match.group(1)),
            "title": title,
            "anchor": f"report-heading-{len(headings) + 1}",
        })
    return headings


def _report_markdown_with_anchors(report, headings):
    lines = str(report or "").splitlines()
    for item in reversed(headings):
        lines.insert(item["line_index"],
                     f'<a id="{escape(item["anchor"])}"></a>')
    return "\n".join(lines)


def _clean_report_for_display(report_md):
    """Hide provenance and collapse adjacent duplicate headings in the reader."""
    text = str(report_md or "")
    text = re.sub(r"\\?<!--.*?-->\\?", "", text, flags=re.DOTALL)
    text = re.sub(r"\\?\{\{TERM:[^}]+\}\}\\?", "", text)
    text = re.sub(r"\b(?:(?:seg|claim|rq|lit-claim|lit-evidence|human-ev)-"
                  r"[A-Za-z0-9_.:-]+|(?:AQ|AV|AR|LR)-\d+)\b",
                  "对应证据", text)
    # These two shapes are reachable in ordinary legacy/generated reports:
    # the analysis label can leak a quote marker, and a bold numbered
    # subsection can be glued to the preceding paragraph.  Repair only those
    # exact forms; ordinary blockquotes and bold prose remain untouched.
    text = re.sub(
        r"((?:\*{0,2}分析\*{0,2})\s*[：:]\s*)>\s*[。．]\s*",
        r"\1", text)
    text = re.sub(
        r"(?P<lead>[。！？])\s*(?P<title>\d+(?:\.\d+)+\s+[^。\n*]{2,100})"
        r"\*{2}\s*[。！？]",
        r"\g<lead>\n\n### \g<title>\n\n", text)
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            title = _report_heading_title(match.group(2))
            # The toolbar is the single report-title source.
            if not any(value.strip() for value in cleaned) and \
                    title.casefold().startswith("翻译实践报告"):
                continue
            previous = next((value for value in reversed(cleaned) if value.strip()), "")
            previous_match = re.match(r"^#{1,6}\s+(.+?)\s*$", previous)
            if previous_match and _report_heading_key(previous_match.group(1)) == \
                    _report_heading_key(title):
                continue
        cleaned.append(line.rstrip())
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _report_template.anonymize_sensitive_institutions(text.strip())


def _report_issue_category(issue):
    issue_type = str(issue.get("type") or "")
    if issue_type in _REPORT_CASE_ISSUES:
        return "案例不足"
    if issue_type in _REPORT_STATISTIC_ISSUES:
        return "统计验证失败"
    if issue_type in _REPORT_TEMPLATE_ISSUES:
        return "模板合规"
    if "citation" in issue_type or issue_type in {
            "unregistered_formal_citation", "uncitable_literature_source"}:
        return "引用需要确认"
    if "literature" in issue_type or "grounding" in issue_type:
        return "文献证据缺失"
    if issue_type in _REPORT_SECTION_ISSUES or issue.get("section_id"):
        return "章节需要重新生成"
    if "human" in issue_type:
        return "需要人工补充"
    return "需要人工补充"


def _report_issue_detail(category, issue):
    if category == "案例不足":
        return "项目中可追溯、符合资格的案例数量或案例选择状态需要确认。"
    if category == "文献证据缺失":
        return "文献来源、逐字证据与论点之间的支持链路尚未完整。"
    if category == "引用需要确认":
        return "存在需要核对的引用来源或作者—年份信息。"
    if category == "统计验证失败":
        return "报告中的项目统计与证据库不一致，或统计来源未能解析。"
    if category == "模板合规":
        return "报告与上传模板的章节、标题、层级或角色不一致。"
    if category == "章节需要重新生成":
        section_id = issue.get("section_id")
        return f"第 {section_id} 节存在结构或论证问题，建议定点重新生成。" \
            if section_id else "报告章节存在结构或论证问题，建议重新生成。"
    if "human" in str(issue.get("type") or ""):
        return "有需要作者确认或补充的项目过程信息。"
    return "报告质量结果仍需人工核对后再作为最终学术结论使用。"


def _report_issue_groups(artifacts, academic):
    groups = {}

    def add(category, detail, section_id=None):
        group = groups.setdefault(category, {"category": category, "details": [],
                                             "sections": set()})
        if detail and detail not in group["details"]:
            group["details"].append(detail)
        if section_id:
            group["sections"].add(str(section_id))

    selected = artifacts.get("selected_cases") or {}
    policy = selected.get("authentic_selection_status") or \
        (selected.get("case_count_policy") or {}).get("status")
    if policy == "insufficient_revision_cases":
        add("案例不足", "符合资格的真实修订案例少于当前研究要求。")

    validation = artifacts.get("validation") or {}
    review = artifacts.get("review") or {}
    literature_review = artifacts.get("literature_support_review") or {}
    quality = artifacts.get("academic_quality") or {}
    final_docx_validation = artifacts.get("final_docx_validation") or {}
    for issue in list(validation.get("issues") or []) \
            + list(review.get("issues") or []) \
            + list(literature_review.get("issues") or []) \
            + list(quality.get("findings") or []) \
            + list(final_docx_validation.get("issues") or []):
        category = _report_issue_category(issue)
        add(category, _report_issue_detail(category, issue), issue.get("section_id"))

    # A legacy/fixture report without a structured report artifact has no
    # literature contract to enforce.  Once the academic pipeline has emitted
    # the report artifact, its explicit literature status is authoritative.
    report_artifact = artifacts.get("report") or {}
    if report_artifact and not (artifacts.get("literature_sources") or {}).get("sources"):
        add("文献证据缺失", "正文结构与案例已完成，但学术文献支持尚未建立。")

    if _academic_validator.citation_validation_status(
            validation, artifacts.get("literature_sources"),
            artifacts.get("literature_evidence"), artifacts.get("literature_claims")) \
            == "evidence_missing" and \
            (artifacts.get("literature_sources") or {}).get("sources"):
        add("文献证据缺失", "已登记文献来源，但逐字证据或文献主张尚未完整。")

    dimensions = academic.get("quality_dimensions") or {}
    if dimensions.get("literature_grounding") in {"review_required", "fail"}:
        add("文献证据缺失", "文献证据的可核验性仍需处理。")
    if dimensions.get("citation_validation") in {"review_required", "fail"}:
        add("引用需要确认", "引用完整性检查未通过。")
    if dimensions.get("statistics_validation") in {"review_required", "fail"}:
        add("统计验证失败", "统计一致性检查未通过。")
    human_status = academic.get("human_evidence_status") or {}
    if human_status.get("unanswered") or human_status.get("critical_questions"):
        add("需要人工补充", "仍有未回答的人类证据问题。")
    if (academic.get("quality_status") or academic.get("status")) in {
            "review_required", "fail", "failed"} and not groups:
        add("需要人工补充", "报告质量状态仍要求人工复核。")

    ordered = []
    for category in ("模板合规", "案例不足", "文献证据缺失", "引用需要确认",
                     "统计验证失败", "章节需要重新生成", "需要人工补充"):
        if category not in groups:
            continue
        group = groups[category]
        sections = sorted(group["sections"], key=str)
        if category == "模板合规":
            action = "处理模板问题"
        elif category == "案例不足":
            action = "处理案例"
        elif category == "文献证据缺失":
            action = "处理文献证据"
        elif category == "引用需要确认":
            action = "检查引用"
        elif category == "统计验证失败":
            action = "检查统计"
        elif category == "章节需要重新生成":
            action = "重新生成章节"
        else:
            action = "回答人工问题"
        group["action"] = action
        group["target"] = "detail"
        ordered.append(group)
    return ordered


def _report_issue_level(category):
    if category == "需要人工补充":
        return "human_review"
    if category in {"章节需要重新生成", "引用需要确认"}:
        return "warning"
    return "blocker"


def _report_issue_impact(group):
    category = group["category"]
    sections = sorted(group.get("sections") or [], key=str)
    if group.get("target") == "review":
        return (f"涉及 {len(sections)} 个段落，完成处理后才能继续最终交付。"
                if sections else "翻译审校队列仍有未关闭发现。")
    if category == "案例不足":
        return "案例分析未满足数量或可追溯性要求，报告不能最终交付。"
    if category == "统计验证失败":
        return "项目统计与证据不一致，最终稿不能通过验证。"
    if category == "模板合规":
        return "章节或版式未满足模板约束，DOCX 交付可能被阻止。"
    if category == "文献证据缺失":
        return "论点缺少可核验支持，报告不能作为最终学术成果交付。"
    if category == "引用需要确认":
        return "引用信息仍需核对，可能影响稿件可信度。"
    if category == "章节需要重新生成":
        location = "、".join(f"第 {value} 节" for value in sections)
        return f"{location or '部分章节'}的结构或证据需要修正。"
    return "仍有内容依赖作者判断或项目经历补充。"


def _report_issue_recommendation(category):
    return {
        "模板合规": "查看验证结果，按模板约束修正报告。",
        "案例不足": "查看案例选择结果，补足合格案例。",
        "文献证据缺失": "检查来源与证据链，补齐文献支持。",
        "引用需要确认": "核对引用来源和作者—年份信息。",
        "统计验证失败": "查看不一致项，重新验证项目统计。",
        "章节需要重新生成": "定位受影响章节，仅重新生成问题部分。",
        "需要人工补充": "回答待补充问题，再继续生成受影响内容。",
    }[category]


def _report_review_issue_groups(state):
    """Bring translation delivery findings into the report Issues view."""
    groups = {}
    for context in _workspace_review_contexts(state):
        if context.get("severity") not in {"blocking", "actionable"}:
            continue
        category = context.get("category_label") or "翻译审校"
        severity = "blocker" if context.get("severity") == "blocking" else "warning"
        group = groups.setdefault(category, {
            "category": category,
            "details": [],
            "sections": set(),
            "severity": severity,
            "level": severity,
            "action": "处理审校",
            "target": "review",
            "finding_ids": [],
        })
        if severity == "blocker":
            group["severity"] = group["level"] = "blocker"
        reason = context.get("summary") or context.get("reason") or "存在待处理的翻译审校发现。"
        if reason not in group["details"]:
            group["details"].append(reason)
        if context.get("segment_number") not in {None, "?"}:
            group["sections"].add(f"段落 {context['segment_number']}")
        finding_id = context.get("finding_id")
        if finding_id and finding_id not in group["finding_ids"]:
            group["finding_ids"].append(finding_id)
    for group in groups.values():
        sections = sorted(group["sections"], key=str)
        group["impact"] = (f"涉及 {len(sections)} 个段落，完成处理后才能继续最终交付。"
                            if sections else "翻译审校队列仍有未关闭发现。")
        group["recommendation"] = "打开审校工作区，逐项处理并保留处理记录。"
    return list(groups.values())


def _report_page_view(job_id, state, artifacts=None):
    """Compose the report page's single status and decision hierarchy."""
    artifacts = artifacts or _report_artifacts(job_id)
    # 报告页的交付措辞直接取 canonical 状态，一次推导、两处引用。
    canonical_label = _task_overview_state(job_id, state)["label"]
    academic = state.get("academic_state") or {}
    runtime_view = core.build_job_runtime_view(job_id, state)
    runtime_status = runtime_view.get("runtime_status") or runtime_view.get("status")
    quality = academic.get("quality_status") or academic.get("status") or "not_started"
    final_qa = _finalization.normalize_final_qa(state.get("final_qa"))
    academic_records = academic.get("artifacts") or {}
    strict_finalization = bool(state.get("report_enabled")) and any(
        name in academic_records for name in (
            "report", "compliance", "final_docx_validation",
            "libreoffice_render", "report_qa"))
    final_review_pending = strict_finalization and (
        final_qa.get("author_visual_review") != "CONFIRMED" or
        final_qa.get("word_final_review") != "CONFIRMED")
    validation = artifacts.get("validation") or {}
    groups = _report_issue_groups(artifacts, academic) + _report_review_issue_groups(state)
    if runtime_status == "waiting_manual" and not any(
            group.get("severity") == "human_review" for group in groups):
        groups.append({
            "category": "运行需要人工确认",
            "details": ["当前阶段已暂停，等待人工输入后才能继续。"],
            "sections": set(),
            "severity": "human_review",
            "level": "human_review",
            "action": "查看运行详情",
            "target": "runtime",
            "impact": "报告生成流程尚未完成。",
            "recommendation": "查看运行详情，确认需要补充的输入。",
        })
    for group in groups:
        group.setdefault("severity", _report_issue_level(group["category"]))
        group["level"] = group["severity"]
        group["impact"] = _report_issue_impact(group)
        group.setdefault("recommendation", _report_issue_recommendation(group["category"])
                         if group["category"] in {
                             "模板合规", "案例不足", "文献证据缺失", "引用需要确认",
                             "统计验证失败", "章节需要重新生成", "需要人工补充",
                         } else "打开审校工作区，逐项处理并保留处理记录。")
    active_statuses = {"resume_requested", "queued", "starting", "running",
                       "waiting_external", "cancelling"}
    blocking = [group for group in groups if group["severity"] == "blocker"]
    if runtime_status in active_statuses:
        overall = "running"
    elif runtime_status == "waiting_manual":
        overall = "review_required"
    elif runtime_status in {"failed", "interrupted", "stalled"} or quality == "failed":
        overall = "failed"
    elif runtime_status in {"cancelled", "idle_incomplete"} and not state.get("p3_done"):
        overall = "blocked"
    elif blocking or quality == "fail" or validation.get("status") == "fail":
        overall = "blocked"
    elif groups or quality in {"review_required", "pass_with_warnings"}:
        overall = "review_required"
    elif state.get("p3_done") and quality == "pass" and validation.get("status") == "pass":
        overall = "ready_for_delivery"
    elif state.get("p3_md"):
        overall = "draft_preview"
    else:
        overall = "blocked"
    report_preview_available = bool(state.get("p3_md") or artifacts.get("report"))
    status_meta = {
        "running": ("正在运行", "查看运行详情", "运行详情", "neutral"),
        "failed": ("运行失败", "查看运行详情", "运行详情", "danger"),
        "blocked": ("可预览 · 尚不可交付" if report_preview_available else "尚不可交付",
                    "处理阻塞问题", "问题与修复", "danger"),
        "review_required": ("可预览 · 等待复核" if report_preview_available else "等待复核",
                            "查看待复核项", "问题与修复", "warning"),
        # 报告页不另造交付词汇：这里显示的就是 canonical 状态。
        "ready_for_delivery": (canonical_label,
                                "完成最终确认" if final_review_pending else "进入交付",
                                None, "warning" if final_review_pending else "success"),
        "draft_preview": ("可预览 · 尚不可交付", "查看当前稿件", "当前稿件", "neutral"),
    }
    label, cta, target_tab, tone = status_meta[overall]
    severity_order = {"blocker": 0, "warning": 1, "human_review": 2}
    groups.sort(key=lambda group: (severity_order.get(group.get("severity"), 9),
                                   group.get("category", "")))
    recommended_issue = next((group for group in groups
                              if group.get("severity") == "blocker"), None)
    if recommended_issue is None:
        recommended_issue = next((group for group in groups
                                  if group.get("severity") in {"warning", "human_review"}), None)
    if recommended_issue and overall in {"blocked", "review_required"}:
        cta = recommended_issue["action"]
        target_tab = "问题与修复"
    if overall in {"failed", "running"}:
        target_tab = "运行详情"
    if overall == "blocked" and not groups:
        cta = "查看运行详情"
        target_tab = "运行详情"
    if overall == "blocked":
        if blocking:
            gate_note = f"仍有 {len(blocking)} 个报告阻塞项；下一步：{cta}。"
        elif validation.get("status") == "fail":
            gate_note = "当前问题列表没有报告阻塞项，但验证结果仍未通过；下一步：查看报告验证结果。"
        elif quality in {"fail", "failed"}:
            gate_note = "当前问题列表没有报告阻塞项，但报告质量检查未通过；下一步：查看质量检查结果。"
        else:
            gate_note = "报告门禁尚未完成；下一步：查看运行详情并完成报告流程。"
    elif overall == "review_required" and not groups:
        gate_note = "报告仍需人工复核；下一步：查看运行详情并记录复核结果。"
    elif overall == "ready_for_delivery" and final_review_pending:
        gate_note = "报告技术检查已完成，但作者视觉复核和 Word 最终复核仍未确认；下一步：进入交付检查。"
    else:
        gate_note = ""
    return {
        "overall": overall, "overall_label": label, "tone": tone,
        "primary_cta": cta, "target_tab": target_tab,
        "runtime": runtime_view, "quality": quality,
        "validation": validation, "groups": groups, "blocking": blocking,
        "recommended_issue": recommended_issue,
        "preview_only": overall != "ready_for_delivery" or final_review_pending,
        "delivery_label": canonical_label
        if overall == "ready_for_delivery" else
        "可预览 · 尚不可交付" if report_preview_available else "尚不可交付",
        "final_review_pending": final_review_pending,
        "gate_note": gate_note,
    }


def _select_report_tab(job_id, label):
    st.session_state[f"report_tabs_{job_id}"] = label


def _report_issues_for_category(category, artifacts):
    issues = []
    for artifact_name, field in (("validation", "issues"), ("review", "issues"),
                                 ("literature_support_review", "issues"),
                                 ("academic_quality", "findings")):
        for issue in (artifacts.get(artifact_name) or {}).get(field) or []:
            if _report_issue_category(issue) == category:
                issues.append(issue)
    return issues


def _queue_report_repair(job_id, state, category, sections):
    if category == "模板合规":
        scope = "writer"
    elif category == "案例不足":
        scope = "planning"
    elif category == "文献证据缺失":
        scope = "all"
    elif category in {"引用需要确认", "统计验证失败"}:
        scope = "validation"
    elif category == "章节需要重新生成" and sections:
        for section_id in sections:
            core.invalidate_academic_report(job_id, "section", section_id)
        scope = None
    else:
        scope = "case_analysis" if category == "需要人工补充" else "writer"
    if scope:
        core.invalidate_academic_report(job_id, scope)
    _resume_job(job_id, core.load_job_state(job_id) or state)


def _render_report_issue_detail(job_id, state, groups, artifacts):
    category = st.session_state.get(f"report_review_focus_{job_id}")
    group = next((item for item in groups if item["category"] == category), None)
    if not group:
        return

    with st.container(key=f"report_issue_detail_{job_id}"):
        back_col, _ = st.columns([1.2, 4], gap="small")
        with back_col:
            if st.button("← 返回当前问题", key=f"report_issue_back_{job_id}",
                         type="secondary", width="stretch"):
                st.session_state.pop(f"report_review_focus_{job_id}", None)
                st.rerun()
        st.markdown(
            f'<div class="tp-report-focus"><div class="tp-report-focus-head">'
            f'<h3>{escape(group["action"])}</h3>'
            f'<span class="tp-report-issue-badge">{escape(group["category"])}</span>'
            '</div>', unsafe_allow_html=True)
        if group.get("target") == "review":
            st.info("这类问题属于翻译审校队列；打开审校工作区后可查看原文、译文和证据，并留下处理记录。")
            if st.button("打开审校工作区", type="primary",
                         key=f"report_open_review_{job_id}", width="stretch"):
                _open_report_issue(job_id, group)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            return
        if category == "案例不足":
            selected = artifacts.get("selected_cases") or {}
            cases = selected.get("cases") or []
            st.caption(
                f"选择状态：{selected.get('authentic_selection_status') or '未记录'} · "
                f"当前案例 {len(cases)} 个")
            if cases:
                rows = [{
                    "案例": item.get("case_id") or "—",
                    "类型": _case_provenance.display_contract(item)["origin_label"],
                    "类型说明": _case_provenance.display_contract(item)[
                        "origin_description"],
                    "来源段": item.get("segment_id") or item.get("source_segment_id") or "—",
                    "聚焦问题": (item.get("focus") or {}).get("issue") or "—",
                    "难点": item.get("difficulty_group") or "—",
                    "策略": item.get("strategy_group") or "—",
                } for item in cases]
                with st.expander(f"查看 {len(cases)} 个已选案例", expanded=False):
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            else:
                st.info("当前没有符合报告要求的案例。重新规划会再次扫描现有翻译修订记录。")
            _render_case_portfolio(selected, artifacts.get("validation") or {})
        elif category == "文献证据缺失":
            sources = (artifacts.get("literature_sources") or {}).get("sources") or []
            evidence = (artifacts.get("literature_evidence") or {}).get("items") or []
            claims = (artifacts.get("literature_claims") or {}).get("items") or []
            st.caption(f"已登记来源 {len(sources)} · 可核验证据 {len(evidence)} · 文献主张 {len(claims)}")
            for source in sources:
                st.markdown(f"- {escape(str(source.get('title') or source.get('source_id') or '未命名来源'))}")
            if not sources:
                st.info("当前没有已登记的参考资料；请先在新建任务的报告设置中添加文献，再重新生成。")
        elif category == "需要人工补充":
            questions = [
                question for question in
                (artifacts.get("human_evidence_questions") or {}).get("questions") or []
                if question.get("status") == "open"
            ]
            if not questions:
                st.success("当前没有尚未回答的人类证据问题，可以继续生成受影响章节。")
            for question in questions:
                question_id = question.get("question_id")
                context = question.get("context") or {}
                st.markdown(f"**{escape(str(question.get('question') or '请补充项目过程信息'))}**")
                if context.get("source"):
                    st.caption(f"原文：{str(context['source'])[:180]}")
                answer_key = f"report_human_answer_{job_id}_{question_id}"
                answer = st.text_area(
                    "你的回答", key=answer_key, height=90,
                    placeholder="如无法回忆，可填写“不记得/没有相关记录”。")
                if st.button("提交回答", key=f"report_human_submit_{job_id}_{question_id}"):
                    if not answer.strip():
                        st.warning("请填写回答；无法回忆时可直接填写“不记得”。")
                    else:
                        core.record_human_evidence(job_id, question_id, answer)
                        st.session_state.pop(answer_key, None)
                        st.rerun()
        elif category == "章节需要重新生成":
            sections = group.get("sections") or []
            st.info("将只重新生成问题章节：" + "、".join(f"第 {value} 节" for value in sections))
        else:
            issues = _report_issues_for_category(category, artifacts)
            if not issues:
                st.info("已定位该复核项；重新执行对应检查后会刷新这里的结果。")
            for issue in issues:
                reason = issue.get("reason") or issue.get("message") or \
                    _report_issue_detail(category, issue)
                st.markdown(f"- {escape(str(reason))}")

        sections = sorted(group.get("sections") or [], key=str)
        action_labels = {
            "模板合规": "按模板重新生成",
            "案例不足": "重新选择案例并继续生成",
            "文献证据缺失": "重建文献证据并继续生成",
            "引用需要确认": "重新验证引用并继续生成",
            "统计验证失败": "重新验证统计并继续生成",
            "章节需要重新生成": "重新生成问题章节",
            "需要人工补充": "用已提交回答继续生成",
        }
        open_questions = category == "需要人工补充" and any(
            question.get("status") == "open" for question in
            (artifacts.get("human_evidence_questions") or {}).get("questions") or [])
        disabled = not api_key or open_questions
        if st.button(action_labels[category], type="secondary",
                     key=f"report_issue_repair_{job_id}_{category}",
                     disabled=disabled, width="stretch"):
            _queue_report_repair(job_id, state, category, sections)
            st.rerun()
        if not api_key:
            st.caption("继续生成需要先在“设置”中配置当前模型的 API Key。")
        elif open_questions:
            st.caption("请先提交上方所有待回答问题；无法回忆时可以如实说明。")
        st.markdown('</div>', unsafe_allow_html=True)


def _render_case_portfolio(selected_cases, validation):
    portfolio = (selected_cases or {}).get("case_portfolio") or {}
    cases = list(portfolio.get("cases") or [])
    if not cases:
        return
    case_validation = (validation or {}).get("case_validation") or {}
    st.markdown("### Case Portfolio")
    pool = int(portfolio.get("candidate_pool_count") or 0)
    selected_count = int(portfolio.get("selected_case_count") or len(cases))
    validated = case_validation.get("provenance_safe_case_count")
    cols = st.columns(3)
    cols[0].metric("总候选数", pool)
    cols[1].metric("最终选中", selected_count)
    cols[2].metric("已验证", "—" if validated is None else int(validated))
    distribution = (selected_cases or {}).get("difficulty_distribution") or {}
    if distribution:
        st.caption(" · ".join(f"{label} {count}" for label, count in distribution.items()))
    st.caption("真实修订：项目保存的历史初译与当前译文；合成对照：模拟初译仅用于分析，不是历史初译。")
    rows = []
    for item in cases:
        focus = item.get("focus") or {}
        source = (focus.get("source_span") or {}).get("text") or ""
        display = _case_provenance.display_contract(item)
        rows.append({
            "case_id": item.get("case_id") or "—",
            "类型": display["origin_label"],
            "类型说明": display["origin_description"],
            "focus": source,
            "难点": item.get("difficulty_group") or "—",
            "策略": item.get("strategy_group") or "—",
            "RQ": "、".join(item.get("research_question_ids") or []),
            "provenance": item.get("provenance_confidence") or "—",
        })
    with st.expander(f"查看 {selected_count} 个聚焦案例", expanded=False):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _open_report_issue(job_id, group):
    if group.get("target") == "review":
        st.session_state.workspace_section = "review"
        finding_ids = group.get("finding_ids") or []
        if finding_ids:
            st.session_state.selected_finding_id = finding_ids[0]
        return
    if group.get("target") == "runtime":
        _select_report_tab(job_id, "运行详情")
        return
    st.session_state[f"report_review_focus_{job_id}"] = group["category"]


def _render_report_status_card(job_id, view):
    runtime = view["runtime"]
    progress = (f'{runtime["progress_completed"]} / {runtime["progress_total"]}'
                if runtime["progress_total"] else "—")
    signal = runtime.get("runtime", {}).get("last_heartbeat_at") or runtime.get("last_activity_at")
    current_step = runtime.get("current_operation") or runtime.get("headline") or "等待下一步"
    detail = runtime.get("detail") or "当前没有新的运行说明。"
    if view.get("gate_note") and view["gate_note"] not in detail:
        detail = f"{detail} {view['gate_note']}"
    progress_html = ""
    if runtime.get("progress_total"):
        progress_pct = round(min(1.0, runtime["progress_completed"] /
                                 runtime["progress_total"]) * 100)
        progress_html = (f'<div class="tp-report-status-progress" aria-label="报告生成步骤 {escape(progress)}">'
                          f'<i style="width:{progress_pct}%"></i></div>')
    st.markdown(
        f'<div class="tp-report-overall is-{view["tone"]}">'
        '<div class="tp-report-overall-head"><div>'
        '<div class="tp-report-toolbar-kicker">报告状态</div>'
        f'<h3>{escape(view["overall_label"])}</h3></div>'
        f'{_workspace_status_badge(view["overall_label"], view["tone"])}</div>'
        '<div class="tp-report-overall-grid">'
        f'<div><span>当前阶段</span><strong>{escape(current_step)}</strong></div>'
        f'<div><span>生成步骤</span><strong>{escape(progress)}</strong></div>'
        f'<div><span>最近运行信号</span><strong>{escape(_runtime_clock(signal))}</strong></div>'
        f'</div>{progress_html}<p class="tp-report-overall-detail">{escape(detail)}</p>'
        '</div>', unsafe_allow_html=True)
    if view["overall"] == "running":
        with st.popover("更多操作", use_container_width=False):
            if st.button("取消任务", type="secondary", width="stretch",
                         key=f"report_cancel_{job_id}"):
                core.request_job_cancel(job_id)
                st.rerun()


def _render_report_issue_workbench(job_id, state, view, artifacts):
    groups = view["groups"]
    counts = {
        severity: sum(1 for group in groups if group.get("severity") == severity)
        for severity in ("blocker", "warning", "human_review")
    }
    st.markdown(
        '<section class="tp-report-issues" aria-labelledby="report-issues-heading">'
        '<div class="tp-report-issues-head"><h3 id="report-issues-heading">当前问题</h3>'
        '<div class="tp-report-issues-summary">'
        f'<span class="is-blocker">阻塞项 {counts["blocker"]}</span>'
        f'<span class="is-warning">建议项 {counts["warning"]}</span>'
        f'<span class="is-human-review">人工判断 {counts["human_review"]}</span>'
        '</div></div></section>', unsafe_allow_html=True)
    focused_category = st.session_state.get(f"report_review_focus_{job_id}")
    if focused_category and any(
            group.get("category") == focused_category for group in groups):
        _render_report_issue_detail(job_id, state, groups, artifacts)
        return
    if not groups:
        st.markdown('<div class="tp-report-issues-empty">当前没有待处理的问题。</div>',
                    unsafe_allow_html=True)
        if view.get("gate_note"):
            st.warning(view["gate_note"])
        return
    if view["overall"] == "running":
        st.info("系统仍在运行。问题列表是最近一次检查结果，请等待当前步骤完成后再执行修复。")
    level_meta = {
        "blocker": ("阻塞项", "阻止交付"),
        "warning": ("建议项", "建议检查"),
        "human_review": ("人工判断", "需要人工判断"),
    }
    recommended = view.get("recommended_issue")
    for severity in ("blocker", "warning", "human_review"):
        level_groups = [group for group in groups if group.get("severity") == severity]
        if not level_groups:
            continue
        heading, note = level_meta[severity]
        st.markdown(
            f'<div class="tp-report-issues-group"><div class="tp-report-issues-group-title">'
            f'<h4>{heading}</h4><span>{note} · {len(level_groups)}</span></div></div>',
            unsafe_allow_html=True)
        for index, group in enumerate(level_groups):
            details = " ".join(group.get("details") or [])
            is_recommended = (group is recommended
                              and view["overall"] in {"blocked", "review_required"})
            recommended_marker = (
                '<span class="tp-report-issue-next">推荐下一步</span>'
                if is_recommended else "")
            with st.container(key=f"report_issue_row_{job_id}_{severity}_{index}"):
                issue_col, action_col = st.columns([4.8, 1.2], gap="small")
                with issue_col:
                    st.markdown(
                        f'<div class="tp-report-issue is-{severity}">'
                        f'<div class="tp-report-issue-badge">{heading}</div>'
                        f'<h4>{escape(group["category"])}</h4>'
                        f'<p>{escape(details)}</p>'
                        '<div class="tp-report-issue-meta">'
                        f'<span>影响范围</span><strong>{escape(group["impact"])}</strong>'
                        f'<span>下一步</span><strong>{escape(group["recommendation"])}</strong>'
                        '</div></div>', unsafe_allow_html=True)
                with action_col:
                    if is_recommended:
                        st.markdown(recommended_marker, unsafe_allow_html=True)
                    else:
                        with st.container(key=f"report_issue_row_action_{job_id}_{severity}_{index}"):
                            if st.button(group["action"], type="secondary", width="stretch",
                                         disabled=view["overall"] == "running",
                                         key=f"report_issue_button_{job_id}_{severity}_{index}"):
                                _open_report_issue(job_id, group)
                                st.rerun()
    _render_report_issue_detail(job_id, state, groups, artifacts)


def _render_report_recommended_action(job_id, view):
    issue = view.get("recommended_issue")
    if view["overall"] == "ready_for_delivery":
        title = "完成作者与 Word 最终复核" if view.get("final_review_pending") \
            else "进入交付并冻结最终版本"
        description = ("报告技术检查已完成，但两项人工终审仍需分别确认。"
                       if view.get("final_review_pending") else
                       "报告已通过当前验证，下一步是确认并生成不可变的最终交付版本。")
    elif view["overall"] in {"running", "failed"}:
        title = view["primary_cta"]
        description = ("查看当前阶段和运行日志，完成后再继续交付。"
                       if view["overall"] == "running"
                       else "查看失败原因并重试当前步骤，报告工作区会保留已完成产物。")
    elif issue:
        title = issue["action"]
        description = issue.get("recommendation") or "处理后会重新计算报告的交付状态。"
    else:
        title = view["primary_cta"]
        description = "查看运行详情，确认报告生成流程的下一步。"
    with st.container(key=f"report_recommended_{job_id}"):
        action_col, button_col = st.columns([3.2, 1], gap="small")
        with action_col:
            st.markdown(
                '<div class="tp-report-recommended-copy">'
                '<div class="tp-report-recommended-kicker">推荐下一步</div>'
                f'<h3>{escape(title)}</h3><p>{escape(description)}</p></div>',
                unsafe_allow_html=True)
        with button_col:
            if st.button(title, type="primary", width="stretch",
                         key=f"report_primary_{job_id}_{view['overall']}"):
                if issue and view["overall"] in {"blocked", "review_required"}:
                    _open_report_issue(job_id, issue)
                    if issue.get("target") in {"review", "runtime"}:
                        st.rerun()
                    _select_report_tab(job_id, "问题与修复")
                elif view["target_tab"] == "运行详情":
                    _select_report_tab(job_id, "运行详情")
                elif view["target_tab"] == "当前稿件":
                    _select_report_tab(job_id, "当前稿件")
                else:
                    st.session_state.workspace_section = "delivery"
                st.rerun()


def _render_report_draft(job_id, state, view, artifacts, report, headings):
    if not report:
        st.markdown('<div class="tp-empty">报告尚未生成。</div>', unsafe_allow_html=True)
        return
    template = core.load_report_template(job_id)
    template_summary = (template or {}).get("summary") or {}
    template_compliance = (view["validation"].get("template_compliance") or {}).get(
        "status", "not_configured")
    st.markdown("### 当前工作稿")
    if view["preview_only"]:
        st.warning("当前稿件仅供预览，尚不能用于最终交付。")
    else:
        st.success("当前稿件已通过验证，可以进入最终交付。")
    if not (artifacts.get("literature_sources") or {}).get("sources"):
        st.warning("正文结构与案例已完成，但学术文献支持尚未建立。")
    if template:
        st.caption(f"模板：{template_summary.get('filename') or '—'} · "
                   f"{template_summary.get('chapter_count', 0)} 章 / "
                   f"{template_summary.get('subsection_count', 0)} 节 · "
                   f"合规 {_report_validation_label(template_compliance)}")
    else:
        st.caption("未配置报告模板；当前 DOCX 使用通用排版。")
    st.caption("阅读模式 · 技术标记已隐藏")
    with st.container(key=f"report_actions_{job_id}"):
        action_a, action_b = st.columns([1.45, 1.2], gap="small")
        docx_data = _report_docx_bytes(state)
        filename = Path(str(state.get("filename") or "report")).stem or "report"
        draft_label = ("导出模板化 DOCX" if template else
                       "导出当前草稿 DOCX" if view["preview_only"] else "导出 DOCX")
        with action_a:
            if docx_data is None:
                blockers = "、".join(group["category"] for group in view["blocking"][:2])
                st.error(f"DOCX 暂不可导出：请先处理“问题与修复”中的{blockers or '阻塞项'}。")
            else:
                st.download_button(
                    draft_label, docx_data,
                    file_name=f"{filename}_翻译实践报告_草稿.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"report_docx_{job_id}", width="stretch")
        with action_b:
            st.download_button(
                "导出 Markdown", report.encode("utf-8"),
                file_name=f"{filename}_翻译实践报告_草稿.md", mime="text/markdown",
                key=f"report_markdown_{job_id}", width="stretch")
    if headings:
        outline_links = []
        for item in headings:
            css = "is-chapter" if item["level"] <= 2 else "is-subsection"
            outline_links.append(
                f'<a class="{css}" href="#{escape(item["anchor"])}">'
                f'{escape(item["title"])}</a>')
        st.markdown('<nav class="tp-report-outline" aria-label="报告目录">'
                    '<div class="tp-report-outline-title">报告目录</div>'
                    + "".join(outline_links) + '</nav>', unsafe_allow_html=True)
    st.markdown('<article class="tp-report-body">', unsafe_allow_html=True)
    st.markdown(_report_markdown_with_anchors(report, headings), unsafe_allow_html=True)
    st.markdown('</article>', unsafe_allow_html=True)


def _render_report_runtime_details(job_id, view, artifacts):
    runtime = view["runtime"]
    runtime_status = runtime.get("runtime_status") or runtime.get("status")
    if runtime_status in {"interrupted", "idle_incomplete", "cancelled"}:
        st.info("这次运行没有完成；已保存的报告产物仍然保留，可以从当前检查点继续。")
        if st.button("继续处理", type="primary", key=f"report_runtime_resume_{job_id}",
                     width="stretch"):
            _resume_job(job_id, core.load_job_state(job_id) or {})
            st.rerun()
    elif runtime_status in {"failed", "stalled"}:
        st.error("报告运行未完成。查看下方阶段和技术详情后，可以重试当前步骤。")
        if st.button("重试当前步骤", type="primary", key=f"report_runtime_retry_{job_id}",
                     width="stretch"):
            core.retry_job_step(job_id)
            _resume_job(job_id, core.load_job_state(job_id) or {})
            st.rerun()
    st.markdown("### 最近活动")
    events = runtime["user_events"]
    if events:
        for event in reversed(events):
            st.markdown(
                f'<div class="tp-runtime-event"><time>{escape(_runtime_clock(event.get("timestamp") or event.get("at")))}</time>'
                f'<span>{escape(event.get("message") or "")}</span></div>',
                unsafe_allow_html=True)
    else:
        st.caption("暂无运行活动。")
    st.markdown("### 运行阶段")
    completed, total = runtime["progress_completed"], runtime["progress_total"]
    if total:
        progress_pct = round(min(1.0, completed / total) * 100)
        st.markdown(
            f'<div class="tp-runtime-progress-head"><span>{escape(runtime["headline"])}</span>'
            f'<strong>{completed} / {total}</strong></div>'
            f'<div class="tp-runtime-bar"><i style="width:{progress_pct}%"></i></div>',
            unsafe_allow_html=True)
    else:
        st.caption(runtime["detail"] or "尚无可用的阶段进度。")
    with st.expander("技术详情与调试信息", expanded=False):
        raw = runtime["runtime"]
        worker = raw.get("worker") or {}
        st.caption(f"runtime status：{runtime['status']} · phase：{raw.get('phase') or '—'}")
        st.caption(f"worker id：{worker.get('worker_id') or '—'} · PID：{worker.get('owner_pid') or '—'}")
        st.caption(f"最后进展：{_runtime_clock(raw.get('last_progress_at'))} · "
                   f"最后心跳：{_runtime_clock(raw.get('last_heartbeat_at'))}")
        for label, artifact_name in (("验证产物", "validation"),
                                     ("语义复核", "review"),
                                     ("质量评估", "academic_quality"),
                                     ("最终 DOCX 验证", "final_docx_validation")):
            artifact = artifacts.get(artifact_name)
            if artifact:
                with st.expander(label, expanded=False):
                    st.json(artifact)
        technical_events = core.read_runtime_events(job_id, 12, visibility="technical")
        if technical_events:
            st.caption("技术日志")
            for event in reversed(technical_events):
                st.markdown(
                    f'<div class="tp-runtime-event"><time>{escape(_runtime_clock(event.get("timestamp") or event.get("at")))}</time>'
                    f'<span>{escape(event.get("event") or "")} · '
                    f'{escape(event.get("message") or "")}</span></div>',
                    unsafe_allow_html=True)


def _render_workspace_report(job_id, state):
    artifacts = _report_artifacts(job_id)
    view = _report_page_view(job_id, state, artifacts)
    report = _clean_report_for_display(state.get("p3_md"))
    headings = _report_headings(report)
    outline = artifacts.get("outline") or {}
    selected_cases = artifacts.get("selected_cases") or {}
    template = core.load_report_template(job_id)
    template_summary = (template or {}).get("summary") or {}
    compliance = (view["validation"].get("template_compliance") or {}).get(
        "status", "not_configured")
    chapter_count = template_summary.get("chapter_count") or sum(
        item["level"] == 2 for item in headings) or len(outline.get("sections") or [])
    subsection_count = template_summary.get("subsection_count") or sum(
        item["level"] > 2 for item in headings)
    if not report:
        chapter_count = subsection_count = 0
    case_portfolio = selected_cases.get("case_portfolio") or {}
    case_count = (len(selected_cases.get("cases") or [])
                  or int(case_portfolio.get("selected_case_count")
                         or len(case_portfolio.get("cases") or [])))
    issue_counts = {
        severity: sum(1 for group in view["groups"] if group.get("severity") == severity)
        for severity in ("blocker", "warning", "human_review")
    }
    chips = [
        ("章节", f"{chapter_count} 章 / {subsection_count} 节"),
        ("案例", f"{case_count} 个"),
        ("验证", _report_validation_label(view["validation"].get("status"))),
        ("阻塞项", str(issue_counts["blocker"])),
        ("交付", view["delivery_label"]),
    ]
    if template:
        chips.insert(2, ("模板", _report_validation_label(compliance)))
    chip_html = "".join(
        f'<span class="tp-report-meta-chip">{escape(label)} <strong>{escape(value)}</strong></span>'
        for label, value in chips)
    st.markdown(
        '<div class="tp-report-page-head"><div class="tp-section-kicker">研究与报告 · 专用能力</div>'
        '<h2>报告</h2>'
        '<p class="tp-report-page-lead">先判断报告状态，再处理真正阻止交付的问题。</p>'
        f'<div class="tp-report-meta-chips">{chip_html}</div></div>',
        unsafe_allow_html=True)
    truth = core.translation_truth_view(job_id, state)
    st.markdown(
        '<div class="tp-truth-banner"><div><span class="tp-truth-kicker">报告输入依据</span>'
        '<strong>当前译文 — 报告证据的唯一来源</strong>'
        f'<p>报告中的译文证据来自工作译文 v{truth["version"]}；译文变更会使受影响的案例、写作单元和报告稿进入“需要更新”。</p>'
        '</div></div>', unsafe_allow_html=True)
    _render_report_status_card(job_id, view)
    impact = core.dependency_impact_view(job_id, state)
    if impact.get("status") == "stale":
        affected = impact.get("affected") or []
        reusable = impact.get("reusable") or []
        st.markdown(
            '<div class="tp-impact-panel"><strong>报告需要更新</strong>'
            f'<p>{escape(_workspace_impact_reason(impact))}</p>'
            '<div class="tp-impact-summary">'
            f'<div><span>发生了什么</span><strong>{escape(_workspace_impact_change_label(impact))}</strong></div>'
            f'<div><span>现在需要更新</span><strong>{len(affected)} 个下游产物</strong></div>'
            f'<div><span>仍可复用</span><strong>{len(reusable)} 个未受影响单元/资产</strong></div>'
            '</div></div>',
            unsafe_allow_html=True)
        _render_workspace_impact_expander(impact)
        if st.button("按影响范围继续重建", type="secondary",
                     key=f"report_targeted_rebuild_{job_id}",
                     disabled=not api_key, width="stretch"):
            _resume_job(job_id, state)
            st.rerun()
        if not api_key:
            st.caption("定点重建需要先在“设置”中配置当前模型 API Key；上方范围说明仍可用于人工核对。")
    tabs = st.tabs(["问题与修复", "当前稿件", "运行详情"],
                   default="问题与修复", key=f"report_tabs_{job_id}")
    with tabs[0]:
        _render_report_issue_workbench(job_id, state, view, artifacts)
        if not st.session_state.get(f"report_review_focus_{job_id}"):
            _render_report_recommended_action(job_id, view)
    with tabs[1]:
        _render_report_draft(job_id, state, view, artifacts, report, headings)
    with tabs[2]:
        _render_report_runtime_details(job_id, view, artifacts)


def _render_workspace_delivery(job_id, state, overview=None):
    overview = overview or _task_overview_state(job_id, state)
    blockers = _delivery.unresolved_blocking(state)
    review_view = _review_workbench(state)
    review_readiness = review_view["readiness"]
    snapshot = core.delivery_snapshot_status(job_id, state)
    latest = snapshot.get("latest")
    report_ready = _delivery.report_ready(state)
    impact = core.dependency_impact_view(job_id, state)
    compliance = _workspace_compliance_view(job_id, state)
    compliance_counts = compliance.get("counts") or {}
    qa = _finalization.normalize_final_qa(state.get("final_qa"))
    finalization_qa_required = bool(state.get("report_enabled"))
    final_docx = core.load_academic_artifact(job_id, "final_docx_validation") or {}
    academic = state.get("academic_state") or {}
    report_workflow_enabled = bool(
        finalization_qa_required or state.get("p3_done") or academic.get("artifacts"))
    final_export_status = _finalization._artifact_status_value(
        academic, "final_docx_validation")
    render_status = _finalization._artifact_status_value(
        academic, "libreoffice_render")
    report_status = _finalization._artifact_status_value(academic, "report")
    final_export_stale = final_export_status in {"stale", "missing", "failed"}
    render_stale = render_status in {"stale", "missing", "failed"}
    report_stale = report_status in {"stale", "missing", "failed"}
    structural = _workspace_structural_qa(job_id, state)
    qa_ready = (not finalization_qa_required or
                not report_stale and not final_export_stale and not render_stale and
                compliance.get("status") == "pass" and
                structural == "PASS" and
                qa.get("libreoffice_render") == "PASS" and
                qa.get("author_visual_review") == "CONFIRMED" and
                qa.get("word_final_review") == "CONFIRMED")
    case_views = _workspace_case_views(job_id, state)
    case_gate = _finalization.case_review_gate(
        state, core.load_academic_artifact(job_id, "selected_cases"))
    case_pending = case_gate.get("blocked_count", 0)
    case_stale = sum(1 for item in case_views if _case_review_is_stale(item, state))
    render_label = ("需要重建" if render_status == "stale" else
                    "失败" if render_status == "failed" else
                    "尚未运行" if render_status in {"missing", "not_available"} else
                    "已通过" if qa.get("libreoffice_render") == "PASS" else "尚未运行")
    render_detail = ("上一份页面预检通过；当前译文变化后需要重新运行" if render_status == "stale" else
                     "页面预检失败，需要查看失败原因" if render_status == "failed" else
                     "尚未生成页面预检结果" if render_status in {"missing", "not_available"} else
                     f"{qa.get('page_count') or '—'} 页 PDF 页面预检" if qa.get("libreoffice_render") == "PASS" else
                     "需要重新运行页面预检")
    translation_truth_gate_pass = (bool(state.get("p2_done")) and
                                   (state.get("delivery_validation") or {}).get("blocking") is not True)
    translation_gate_pass = (translation_truth_gate_pass and review_readiness["ready"]
                             and not blockers)
    report_draft_exists = bool(state.get("p3_md") or
                               core.load_academic_artifact(job_id, "report"))
    affected_count = len(impact.get("affected") or [])
    reusable_count = len(impact.get("reusable") or [])
    review_gate = _workspace_view.delivery_review_gate_copy(
        bool(review_readiness.get("required")), translation_gate_pass,
        review_view["delivery"]["detail"])
    review_gate_status = review_gate["status"]
    review_gate_detail = review_gate["detail"]
    readiness = [
        # 翻译本身是最前置的门禁：此前网格里没有这一项，于是"翻译未完成"的任务
        # 在交付页只看到"独立审校：不适用"，看不到真正的阻塞原因。
        ("翻译完成", "已完成" if translation_truth_gate_pass else "未完成",
         "全部段落已完成翻译，且交付门禁未发现阻断项"
         if translation_truth_gate_pass else
         f"{len(state.get('pairs') or [])} / {len(state.get('paras') or [])} 段已翻译；"
         "完成剩余段落并确认交付门禁后才能冻结交付",
         "pass" if translation_truth_gate_pass else "warning"),
        ("独立审校", review_gate_status, review_gate_detail,
         "pass" if not review_readiness.get("required") or translation_gate_pass else "warning"),
        ("学术产物同步", "当前任务未启用" if not report_workflow_enabled else
         "需要更新" if (impact.get("status") == "stale" or
                                          report_stale or final_export_stale) else
         "已同步" if report_ready else "报告未完成",
         "当前任务没有独立研究报告要求" if not report_workflow_enabled else
         f"{affected_count} 项下游产物待重建" if impact.get("status") == "stale" else
         "报告或 DOCX 产物需要重新检查" if report_stale or final_export_stale else
         "报告与当前译文一致" if report_ready else
         "报告稿可预览，但尚未达到可交付状态" if report_draft_exists else
         "报告稿尚未生成",
         "warning" if report_workflow_enabled and (
             impact.get("status") == "stale" or report_stale or
             final_export_stale or not report_ready) else "pass"),
        ("案例复核", "当前任务未启用" if not report_workflow_enabled and not case_views else
         "需要重建" if case_stale else "待人工确认" if case_pending else
         "已确认" if case_views else "待生成",
         "当前任务没有独立案例终审要求" if not report_workflow_enabled and not case_views else
         f"{case_stale} 个案例受译文变化影响" if case_stale else
         f"{case_pending} 个案例尚未完成终审" if case_pending else
         "案例均已完成终审" if case_views else "尚未生成案例选择产物",
         "warning" if (report_workflow_enabled or case_views) and (
             case_stale or case_pending or not case_views) else "pass"),
        ("合规检查", "当前任务未启用" if not finalization_qa_required else
         f"{compliance_counts.get('fail', 0)} 项失败" if compliance_counts.get("fail") else
         "需人工复核" if compliance_counts.get("manual_review") else "已通过",
         "当前任务没有独立报告与最终 QA 要求" if not finalization_qa_required else
         (f"{compliance_counts.get('manual_review', 0)} 项需要人工复核 · "
          f"{compliance_counts.get('not_checked', 0)} 项未检查")
         if compliance_counts.get("manual_review") or compliance_counts.get("not_checked") else
         "所有适用规则已通过" if compliance.get("status") == "pass" else "仍有规则需要确认",
         "warning" if finalization_qa_required and (
             compliance_counts.get("fail") or compliance_counts.get("manual_review")) else "pass"),
        ("DOCX 结构检查", "当前任务未启用" if not finalization_qa_required else
         "已通过" if structural == "PASS" else
         "失败" if structural == "FAIL" else "需要重建" if structural == "STALE" else "尚未运行",
         "当前任务没有独立报告结构检查要求" if not finalization_qa_required else
         "文档结构检查已保存" if structural == "PASS" else
         "上一份检查已通过；当前译文变化后需要重新检查" if structural == "STALE" else
         "需要先完成结构检查" if structural == "NOT_RUN" else "结构检查发现问题",
         "pass" if not finalization_qa_required or structural == "PASS" else "warning"),
        ("LibreOffice 页面渲染",
         "当前任务未启用" if not finalization_qa_required else render_label,
         "当前任务没有独立页面预检要求" if not finalization_qa_required else render_detail,
         "warning" if finalization_qa_required and (
             render_status in {"stale", "missing", "failed", "not_available"} or
             qa.get("libreoffice_render") != "PASS") else "pass"),
        ("作者视觉复核", "当前任务未启用" if not finalization_qa_required else
         "已确认" if qa.get("author_visual_review") == "CONFIRMED" else "尚未确认",
         "当前任务没有独立作者视觉复核要求" if not finalization_qa_required else
         "作者已确认关键页面" if qa.get("author_visual_review") == "CONFIRMED" else
         "需要作者检查关键页面与版式",
         "pass" if not finalization_qa_required or
         qa.get("author_visual_review") == "CONFIRMED" else "warning"),
        ("Word 最终复核", "当前任务未启用" if not finalization_qa_required else
         "已确认" if qa.get("word_final_review") == "CONFIRMED" else "尚未确认",
         "当前任务没有独立 Word 最终复核要求" if not finalization_qa_required else
         "Word 最终页面已确认" if qa.get("word_final_review") == "CONFIRMED" else
         "需要在 Word 更新字段并确认最终页面",
         "pass" if not finalization_qa_required or
         qa.get("word_final_review") == "CONFIRMED" else "warning"),
        ("冻结交付", f"已冻结交付 v{latest.get('snapshot_version')}"
         if snapshot.get("current") and latest else
         f"工作版本已偏离冻结交付 v{latest.get('snapshot_version')}"
         if snapshot.get("diverged") and latest else "尚未生成",
         f"冻结交付 v{latest.get('snapshot_version')} 可下载" if snapshot.get("current") and latest else
         f"v{latest.get('snapshot_version')} 保持不变；完成更新后可冻结新版本 v{int(latest.get('snapshot_version')) + 1}"
         if snapshot.get("diverged") and latest else
         "所有前置事实满足后再生成不可变版本",
         "pass" if snapshot.get("current") else "warning"),
    ]
    hard_gate_reasons = _workspace_hard_gate_reasons(job_id, state)
    delivery_state_label, delivery_state_tone = _workspace_delivery_state(
        job_id, state, overview)
    if snapshot.get("current"):
        readiness_title = delivery_state_label
        readiness_summary = "当前冻结交付仍是可下载的不可变版本。"
    elif snapshot.get("diverged"):
        readiness_title = delivery_state_label
        readiness_summary = (f"冻结交付 v{latest.get('snapshot_version')} 保持不变；"
                             f"当前工作版本需要完成检查后，才能冻结为新版本 v{int(latest.get('snapshot_version')) + 1}。"
                             if latest else "当前工作版本与最近冻结交付不一致，需要重新检查后再冻结。")
    elif overview["lifecycle"] == _task_overview.DELIVERY_READY:
        readiness_title = delivery_state_label
        readiness_summary = "最终交付资产已生成并通过检查，可以生成冻结交付。"
    elif overview["lifecycle"] == _task_overview.READY_FOR_DELIVERY_PREP:
        readiness_title = delivery_state_label
        readiness_summary = "当前译文满足条件，可以开始准备最终交付。"
    else:
        readiness_title = delivery_state_label
        summary_parts = []
        if not review_readiness["ready"]:
            summary_parts.append(review_view["delivery"]["detail"])
        elif translation_gate_pass:
            summary_parts.append("当前译文已通过交付门禁")
        # 与网格、下一步保持一致：只有确实存在学术下游时才算"报告产物待重建"。
        # 此前这里没有这个判据，纯翻译任务会同时出现"学术产物同步：当前任务未启用"
        # 与"但受影响的报告产物仍需重建"两句互相矛盾的话。
        if impact.get("status") == "stale" and _academic_downstream_enabled(state, job_id):
            summary_parts.append("但受影响的报告产物仍需重建")
        if finalization_qa_required and compliance_counts.get("fail"):
            summary_parts.append(f"{compliance_counts['fail']} 项合规检查失败")
        if finalization_qa_required and compliance_counts.get("manual_review"):
            summary_parts.append(f"{compliance_counts['manual_review']} 项需要人工复核")
        if finalization_qa_required and compliance_counts.get("not_checked"):
            summary_parts.append(f"{compliance_counts['not_checked']} 项尚未检查")
        if finalization_qa_required and structural == "STALE":
            summary_parts.append("DOCX 结构检查需要重建")
        if finalization_qa_required and render_stale:
            summary_parts.append("LibreOffice 页面预检需要重建")
        if finalization_qa_required and qa.get("author_visual_review") != "CONFIRMED" and qa.get("word_final_review") != "CONFIRMED":
            summary_parts.append("作者视觉复核和 Word 最终复核尚未确认")
        elif finalization_qa_required and qa.get("author_visual_review") != "CONFIRMED":
            summary_parts.append("作者视觉复核尚未确认")
        elif finalization_qa_required and qa.get("word_final_review") != "CONFIRMED":
            summary_parts.append("Word 最终复核尚未确认")
        if case_pending and (report_workflow_enabled or case_views) \
                and "案例" not in "".join(summary_parts):
            summary_parts.append(f"另有 {case_pending} 个案例待人工确认")
        readiness_summary = (f"{delivery_state_label}；" + "；".join(summary_parts) + "。"
                             if summary_parts else f"{delivery_state_label}；请查看各项准备状态。")
    st.markdown('<div class="tp-section-kicker">工作流最后一步</div><h2>最终交付</h2>'
                '<div class="tp-section-lead">先判断是否安全，再处理阻塞项；确认后才会生成不可变版本。</div>',
                unsafe_allow_html=True)
    flag_label = delivery_state_label
    st.markdown(
        f'<div class="tp-readiness-card is-{delivery_state_tone}"><div class="tp-readiness-kicker">交付判断</div>'
        f'<div class="tp-readiness-head"><div><h3>{escape(readiness_title)}</h3>'
        f'<p>{escape(readiness_summary)}</p></div><span class="tp-readiness-flag">{flag_label}</span></div>'
        '<div class="tp-readiness-grid">' + "".join(
            f'<div class="tp-readiness-item is-{tone}"><div class="tp-readiness-item-head">'
            f'<span class="tp-readiness-icon">{"✓" if tone == "pass" else "!"}</span>'
            f'<span class="tp-readiness-label">{escape(label)}</span></div>'
            f'<div class="tp-readiness-detail">{escape(detail)}</div>'
            f'<div class="tp-readiness-status">{escape(status)}</div></div>'
            for label, status, detail, tone in readiness) + '</div></div>',
        unsafe_allow_html=True)
    if not translation_truth_gate_pass:
        next_title = "翻译尚未完成"
        next_detail = (f"{len(state.get('pairs') or [])} / "
                       f"{len(state.get('paras') or [])} 段已翻译；"
                       "完成剩余段落并确认交付门禁后，才能生成冻结交付。")
        next_button = "回到翻译"
        next_target = "translate"
    elif not review_readiness["ready"] and not review_view["risk_acceptance"]["available"]:
        next_title = review_view["delivery"]["detail"]
        next_detail = "先回到审校工作台完成当前译文的审校，再继续准备交付。"
        next_button = review_view["primary_action"]["label"]
        next_target = "review"
    elif blockers and review_view["risk_acceptance"]["available"]:
        next_title = f"处理 {len(blockers)} 个必须处理的问题"
        next_detail = "优先解决问题；只有在理解剩余风险后，才可在下方选择仍要交付。"
        next_button = "返回审校工作台"
        next_target = "review"
    elif impact.get("status") == "stale" and _academic_downstream_enabled(state, job_id):
        next_title = "更新受影响的报告产物"
        next_detail = (f"先按影响范围重建 {affected_count} 项下游产物；"
                       f"{reusable_count} 个未受影响单元/资产仍可复用。")
        next_button = "按影响范围继续重建"
        next_target = "rebuild"
    elif finalization_qa_required and (
            compliance_counts.get("fail") or compliance_counts.get("manual_review")):
        next_title = "处理合规与人工复核"
        next_detail = "先在合规与 QA 中处理失败规则，再记录需要人工确认的项目。"
        next_button = "打开合规与 QA"
        next_target = "qa"
    elif not report_ready and state.get("report_enabled"):
        next_title = "完成报告"
        next_detail = "当前报告还不能作为最终学术产物交付。"
        next_button = "打开报告"
        next_target = "report"
    elif finalization_qa_required and (qa.get("author_visual_review") != "CONFIRMED" or qa.get("word_final_review") != "CONFIRMED"):
        next_title = "完成最终人工复核"
        next_detail = "作者视觉复核和 Word 最终复核都必须分别记录。"
        next_button = "打开合规与 QA"
        next_target = "qa"
    elif snapshot.get("diverged") and latest:
        next_title = f"冻结为新版本 v{int(latest.get('snapshot_version')) + 1}"
        next_detail = (f"当前工作版本已偏离 v{latest.get('snapshot_version')}；"
                       "冻结会追加新版本，不会覆盖已有交付。")
        next_button = "回到冻结操作"
        next_target = "freeze"
    else:
        next_title = "生成冻结交付"
        next_detail = "前置检查已完成，确认后会生成不可变交付快照。"
        next_button = "回到冻结操作"
        next_target = "freeze"
    with st.container(key=f"delivery_next_action_{job_id}"):
        action_copy, action_button = st.columns([3.2, 1.15], gap="medium")
        with action_copy:
            st.markdown(f'<div class="tp-next-action-copy"><div class="tp-next-action-kicker">下一步</div>'
                        f'<strong>{escape(next_title)}</strong>'
                        f'<p>{escape(next_detail)}</p></div>', unsafe_allow_html=True)
        with action_button:
            if next_target == "rebuild":
                if st.button(next_button, type="primary", key=f"delivery_targeted_rebuild_{job_id}",
                             disabled=not api_key, width="stretch"):
                    _resume_job(job_id, state)
                    st.rerun()
            elif next_target == "qa":
                if st.button(next_button, type="primary", key=f"delivery_open_qa_{job_id}", width="stretch"):
                    st.session_state.workspace_section = "qa"
                    st.rerun()
            elif next_target == "report":
                if st.button(next_button, type="primary", key=f"delivery_open_report_{job_id}", width="stretch"):
                    st.session_state.workspace_section = "report"
                    st.rerun()
            elif next_target == "translate":
                if st.button(next_button, type="primary",
                             key=f"delivery_open_translation_{job_id}",
                             width="stretch"):
                    st.session_state.workspace_section = "translation"
                    st.rerun()
            elif next_target == "review":
                if st.button(next_button, type="primary",
                             key=f"delivery_open_review_{job_id}", width="stretch"):
                    st.session_state.workspace_section = "review"
                    st.rerun()
            else:
                st.caption("请使用下方冻结操作。")
    if next_target == "rebuild" and not api_key:
        st.caption("定点重建需要先在“设置”中配置当前模型 API Key；影响范围仍可用于人工核对。")
    with st.expander("查看技术依据", expanded=False):
        truth = core.translation_truth_view(job_id, state)
        st.caption(f'CURRENT_TRANSLATION · 当前工作译文 v{truth["version"]} · {truth["segment_count"]:,} 段')
        st.caption("交付文件和学术下游都以当前译文为输入；冻结交付另存为不可变快照。")
    if impact.get("status") == "stale":
        st.markdown(
            '<div class="tp-impact-panel"><strong>最近变更的影响</strong>'
            f'<p>{escape(_workspace_impact_reason(impact))}</p>'
            '<div class="tp-impact-summary">'
            f'<div><span>发生了什么</span><strong>{escape(_workspace_impact_change_label(impact))}</strong></div>'
            f'<div><span>现在需要更新</span><strong>{affected_count} 个下游产物</strong></div>'
            f'<div><span>仍可复用</span><strong>{reusable_count} 个未受影响单元/资产</strong></div>'
            '</div></div>', unsafe_allow_html=True)
        _render_workspace_impact_expander(impact)
    freeze_action = (f"冻结为新版本 v{int(latest.get('snapshot_version')) + 1}"
                     if latest else "确认并冻结最终版本")
    if blockers and hard_gate_reasons:
        st.error(f"还有 {len(blockers)} 个审校阻塞项；以下门禁不能通过“接受风险”跳过："
                 f"{'、'.join(dict.fromkeys(hard_gate_reasons))}。请先完成这些门禁。")
    elif blockers and review_view["risk_acceptance"]["available"]:
        st.markdown('<div class="tp-risk-acceptance"><span>高风险最终动作</span>'
                    '<h3>仍要交付</h3>'
                    f'<p>当前仍有 {len(blockers)} 个必须处理的问题。继续交付不会删除这些问题；'
                    '系统会保存本次风险接受记录。</p></div>', unsafe_allow_html=True)
        note = st.text_area(
            "处理说明", key=f"workspace_delivery_note_{job_id}",
            placeholder="说明为什么在这些问题仍然存在时决定继续交付…")
        accept = st.checkbox(
            "我确认理解这些问题仍然存在，并决定继续交付",
            key=f"workspace_delivery_accept_{job_id}")
        if st.button("确认风险并继续交付", type="primary",
                     disabled=(not accept or not report_ready or not qa_ready
                                or not translation_truth_gate_pass),
                     key=f"workspace_delivery_accept_go_{job_id}", width="stretch"):
            _, ok, errors = core.approve_delivery(job_id, note or "人工确认并接受剩余风险",
                                                   accept_blocking=True, target_lang=target_lang,
                                                   provider=ai_provider, model=ai_model)
            if ok:
                _set_workspace_flash("风险接受记录已保存，并已生成冻结交付。")
                st.rerun()
            for error in errors:
                st.error(error)
    elif not snapshot.get("current"):
        note = st.text_input("交付说明（可选）", key=f"workspace_delivery_final_note_{job_id}", placeholder="例如：已完成人工审校…")
        # `next_target == "freeze"` 是"所有交付门禁都已通过"的既有单一判据
        # （翻译完成 / 审校就绪 / 无阻塞 / 报告与 QA 就绪）。这里复用它，而不是
        # 再维护第三份门禁判断——此前只检查报告与 QA，导致翻译未完成或审校
        # 未就绪的任务也显示可点击的冻结按钮，点了必然失败。
        if st.button(freeze_action, type="primary",
                     disabled=next_target != "freeze",
                     key=f"workspace_delivery_final_{job_id}", width="stretch"):
            _, ok, errors = core.approve_delivery(job_id, note or "人工确认最终交付",
                                                   target_lang=target_lang, provider=ai_provider,
                                                   model=ai_model)
            if ok:
                st.rerun()
            for error in errors:
                st.error(error)
    else:
        st.success(f"最终交付版本 v{latest.get('snapshot_version')} 已冻结；后续工作版本变更不会修改它。")

    st.markdown('<div class="tp-section-label" style="margin-top:24px">版本历史</div>', unsafe_allow_html=True)
    snapshots = core.list_delivery_snapshots(job_id)
    if snapshots:
        st.markdown('<div class="tp-version-list">', unsafe_allow_html=True)
        filename = Path(str(state.get("filename") or "document")).stem or "document"
        for item in reversed(snapshots):
            approval = item.get("approval") or {}
            st.markdown(f'<div class="tp-version"><strong>v{item.get("snapshot_version")} · 已冻结</strong>'
                        f'<span>{escape(str(approval.get("timestamp") or item.get("created_at") or "—"))[:19]}</span></div>',
                        unsafe_allow_html=True)
            archive = core.delivery_snapshot_archive(job_id, item.get("snapshot_version"))
            if archive:
                st.download_button(f"下载最终交付版本 v{item.get('snapshot_version')}", archive,
                                   file_name=f"final_delivery_v{item.get('snapshot_version')}_{filename}.zip",
                                   mime="application/zip", key=f"workspace_snapshot_{job_id}_{item.get('snapshot_version')}",
                                   width="stretch")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.caption("尚无冻结版本；确认后将从 v1 开始记录。")

    if not state.get("p2_done"):
        st.markdown('<div class="tp-empty">翻译完成后，交付文件会显示在这里。</div>', unsafe_allow_html=True)
        return
    frozen_assets = core.delivery_snapshot_assets(job_id, latest.get("snapshot_version")) \
        if snapshot.get("current") and latest else {}
    try:
        assets = frozen_assets or core.build_delivery_assets(job_id, state)
    except RuntimeError as exc:
        st.error(str(exc))
        for issue in (state.get("delivery_validation") or {}).get("issues") or []:
            st.warning(
                f"第 {int(issue.get('segment_index', -1)) + 1 if isinstance(issue.get('segment_index'), int) else '?'} 段："
                f"{issue.get('message', '译文未通过交付检查')}"
            )
        st.caption("当前工作稿已保留；修复问题后才能生成 DOCX、JSONL、TMX 和最终快照。")
        return
    labels = {
        "translation.docx": "纯译文", "bilingual.docx": "双语对照",
        "translation.pdf": "纯译文", "annotated_bilingual.docx": "双语对照 · 标注增强版",
        "terms.xlsx": "术语表", "terms.tbx": "标准术语库",
        "memory.tmx": "翻译记忆", "bilingual.jsonl": "结构化数据",
        "segment_evidence.jsonl": "翻译过程证据",
        "selected_cases.json": "案例候选",
        "academic_workspace.zip": "学术写作工作区",
        "review_report.md": "审校报告", "report.docx": "实践报告 DOCX",
        "report.md": "实践报告 Markdown",
        "delivery_manifest.json": "Delivery Manifest",
        "stage1_cleaned.docx": "清洗后原文", "auto_terms.xlsx": "自动术语表",
        "stage2_bilingual.docx": "双语对照", "stage3_report.docx": "实践报告",
    }
    mime_by_suffix = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf", ".tbx": "application/xml",
        ".tmx": "application/xml", ".json": "application/json",
        ".jsonl": "application/x-jsonlines", ".md": "text/markdown",
        ".zip": "application/zip",
    }
    st.markdown('<div class="tp-section-label" style="margin-top:24px">交付文件</div><div class="tp-asset-list">', unsafe_allow_html=True)
    for index, (key, data) in enumerate(assets.items()):
        label = labels.get(key, key)
        mime = mime_by_suffix.get(Path(key).suffix.lower(), "application/octet-stream")
        description = f"{key} · {_format_size(len(data))}"
        asset_col, action_col = st.columns([3, 1])
        with asset_col:
            st.markdown(f'<div class="tp-asset-row"><div class="tp-asset-copy"><strong>{escape(label)}</strong><span>{escape(description)}</span></div></div>', unsafe_allow_html=True)
        with action_col:
            if data is not None:
                st.download_button("下载" if key != "delivery_manifest.json" else "下载 manifest", data,
                                   file_name=key, mime=mime, key=f"workspace_asset_{job_id}_{index}", width="stretch")
            if key == "delivery_manifest.json" and data:
                with st.expander("查看 manifest", expanded=False):
                    try:
                        st.json(json.loads(data.decode("utf-8")))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        st.caption("manifest 当前不可预览。")
    st.markdown('</div>', unsafe_allow_html=True)


def _render_workspace_shell(job_id, state):
    if not state:
        _render_workspace_topbar(job_id or "", {"filename": "当前任务", "paras": [], "pairs": []})
        st.markdown('<div class="tp-empty">还没有打开的任务。请从历史任务或新建任务进入。</div>', unsafe_allow_html=True)
        return
    # 单一派生入口：本页所有表面（顶栏 / 侧栏 / Hero / pipeline）共用这一份状态。
    overview = _task_overview_state(job_id, state)
    _render_workspace_topbar(job_id, state, overview)
    _render_workspace_flash()
    section = st.session_state.get("workspace_section", "overview")
    if section not in {"overview", "translation", "terms", "review", "cases", "report", "qa", "delivery"}:
        section = "overview"
        st.session_state.workspace_section = section
    if section == "overview":
        nav_col, main_col = st.columns([0.82, 4.63], gap="small")
        with nav_col:
            with st.container(key="workspace_nav_col"):
                _render_workspace_nav(section, state, job_id, overview)
        with main_col:
            with st.container(key="workspace_main_col"):
                _render_workspace_overview(job_id, state, overview)
        return

    if section == "report":
        nav_col, main_col = st.columns([0.82, 4.63], gap="small")
        with nav_col:
            with st.container(key="workspace_nav_col"):
                _render_workspace_nav(section, state, job_id, overview)
        with main_col:
            with st.container(key="workspace_main_col"):
                _render_workspace_report(job_id, state)
        return

    # Translation needs the widest center surface; the inspector stays a
    # compact, segment-driven utility column rather than a second dashboard.
    if section == "translation":
        # 把宽度让给正文，但要留够导航标签的宽度：低于 0.7 时中文标签会被截成一个字。
        # 右栏是 Inspector 而不是编辑器，1.32 足够放"段落事实"两列网格和 AI 动作。
        shell_ratios = [0.96, 3.92, 1.32]
    elif section == "review":
        shell_ratios = [0.78, 4.05, 1.28]
    else:
        shell_ratios = [0.82, 3.05, 1.58]
    nav_col, main_col, context_col = st.columns(shell_ratios, gap="small")
    with nav_col:
        with st.container(key="workspace_nav_col"):
            _render_workspace_nav(section, state, job_id, overview)
    with main_col:
        with st.container(key="workspace_main_col"):
            if section == "translation":
                _render_workspace_translation(job_id, state, overview)
            elif section == "terms":
                _render_workspace_terms(job_id, state)
            elif section == "review":
                _render_workspace_review(job_id, state)
            elif section == "cases":
                _render_workspace_cases(job_id, state)
            elif section == "report":
                _render_workspace_report(job_id, state)
            elif section == "qa":
                _render_workspace_qa(job_id, state)
            else:
                _render_workspace_delivery(job_id, state, overview)
    with context_col:
        with st.container(key="workspace_context_col"):
            _render_workspace_context(job_id, state, section, overview)


@st.fragment(run_every="3s")
def _render_live_workspace(job_id):
    """Poll the durable state without blocking the Streamlit render thread."""
    _render_workspace_shell(job_id, core.load_job_state(job_id) if job_id else None)

# ================= Product shell / state =================
providers = sorted(core.PROVIDERS, key=str.casefold)
default_provider = "DeepSeek" if "DeepSeek" in providers else providers[0]
ai_provider = st.session_state.get("provider_choice", default_provider)
if ai_provider not in core.PROVIDERS:
    ai_provider = default_provider
provider_cfg = core.PROVIDERS[ai_provider]
model_opts = sorted(provider_cfg.get("models") or [], key=str.casefold)
default_model = provider_cfg.get("default_model")
if default_model not in model_opts:
    default_model = model_opts[0] if model_opts else ""
ai_model = st.session_state.get(f"model_choice_{ai_provider}", default_model)
if model_opts and ai_model not in model_opts:
    ai_model = default_model
    st.session_state[f"model_choice_{ai_provider}"] = default_model
api_key = st.session_state.get(f"api_key_{ai_provider}", "")
api_base = st.session_state.get("custom_base_url", "") \
    if provider_cfg.get("custom_base_url") else None
reviewer_mode = st.session_state.get("reviewer_mode", "same")
reviewer_provider = st.session_state.get("reviewer_provider_choice", ai_provider)
if reviewer_provider not in core.PROVIDERS:
    reviewer_provider = ai_provider
reviewer_model = st.session_state.get("reviewer_model", "")
reviewer_api_key = st.session_state.get("reviewer_api_key", "")
reviewer_base_url = st.session_state.get("reviewer_base_url", "")
saved_jobs = core.list_jobs()


# ================= 统一反馈（toast / flash）=================
# 所有 Project 操作的结果都走这里：回调里只入队，渲染层在**稳定位置**取一次并
# 用 `st.toast` 提示。这样即使操作后紧跟 `st.rerun()`（或弹出 modal 导致一次
# 额外 rerun），反馈也不会像 inline st.success 那样丢失或重复。
_TOAST_ICONS = {"success": ":material/check_circle:", "error": ":material/error:",
                "warning": ":material/warning:", "info": ":material/info:"}


def _push_flash(message, tone="success"):
    """入队一条待提示消息。跨 rerun 存活（存在 session_state 里）。"""
    text = str(message or "").strip()
    if not text:
        return
    queue = list(st.session_state.get("app_flash") or [])
    queue.append({"message": text, "tone": str(tone or "success")})
    st.session_state["app_flash"] = queue[-5:]


def _render_flashes():
    """取一次队列并渲染 toast。只消费一次，不会在 rerun 后重复出现。

    渲染过的消息追加到 `app_flash_log`：`st.toast` 是短期浮层，无法被回归测试
    观察到，因此把"确实提示过什么"留一份可断言的记录（界面不渲染它）。
    """
    queue = list(st.session_state.pop("app_flash", []) or [])
    for item in queue:
        message = str(item.get("message") or "")
        log = list(st.session_state.get("app_flash_log") or [])
        log.append({"message": message, "tone": item.get("tone") or "success"})
        st.session_state["app_flash_log"] = log[-20:]
        try:
            st.toast(message, icon=_TOAST_ICONS.get(
                item.get("tone") or "success", _TOAST_ICONS["success"]))
        except Exception:
            # 老版本 Streamlit 没有 st.toast：退化成一次性提示条，语义不变。
            {"error": st.error, "warning": st.warning,
             "info": st.info}.get(item.get("tone") or "success",
                                  st.success)(message)


# ================= Project 弹窗（新建 / 重命名 / 编辑 / 归档 / 删除）=================
# 交互模型：破坏性或需要输入的 Project 生命周期操作都在 modal 里完成，避免
# inline 表单把列表页撑成表单页。每个 modal 由「谁打开」的 session_state 键驱动。
#
# 关键约束：`st.dialog` 的内容是一个 fragment，点击其中的按钮只会**重跑该
# fragment**，主脚本里"渲染一次就清掉标记"的写法会让弹窗在这一次重跑里消失，
# 连带丢掉按钮刚写下的效果（实测：切换项目时 active_project_id 根本没被写入）。
# 因此标记**只在动作成功后清掉**（`_close_project_modals` / `_close_project_switcher`），
# 不在渲染时消费。

PROJECT_MODAL_KEYS = ("project_modal", "project_modal_target", "task_move_job_id")
_HAS_ST_DIALOG = hasattr(st, "dialog")


def _open_project_modal(kind, project_id=""):
    st.session_state["project_modal"] = str(kind or "")
    st.session_state["project_modal_target"] = str(project_id or "")


def _close_project_modals():
    for key in PROJECT_MODAL_KEYS:
        st.session_state.pop(key, None)


def _consume_project_modal(*kinds):
    """当前打开的是哪个 modal（没有打开时返回空串）。

    刻意**不**在这里清除标记：dialog 内的按钮点击只重跑 fragment，清掉标记会让
    弹窗在重跑时消失（见本节说明）。
    """
    kind = str(st.session_state.get("project_modal") or "")
    return kind if kind in kinds else ""


def _modal_container(title, *, width="small"):
    """modal 渲染器；Streamlit 版本没有 st.dialog 时退化成 inline 卡片。

    退化路径只影响外观，不影响语义：用户仍然能完成同一批操作，且不会因为
    版本差异丢掉功能。
    """
    if _HAS_ST_DIALOG:
        return st.dialog(title, width=width)
    def _inline(func):
        def _wrapper():
            with st.container(border=True, key=f"project_modal_{title}"):
                st.markdown(f'<div class="tp-field-head"><strong>{escape(title)}'
                            '</strong></div>', unsafe_allow_html=True)
                func()
        return _wrapper
    return _inline


def _project_modal_record():
    """modal 当前作用的项目记录（不存在时返回 None，调用方负责报错）。"""
    project_id = str(st.session_state.get("project_modal_target") or "")
    if not project_id:
        return None
    if core.is_system_project_id(project_id):
        return core.system_project_view()
    return core.load_project(project_id)


def _reload_project_state():
    """任何 Project 操作成功后刷新与项目相关的派生状态。

    侧栏「项目上下文」、项目列表、新建任务页的上下文都从磁盘派生，因此这里只做
    一件事：让缓存/失效的导航状态与磁盘一致。**不做 rerun**，由调用方决定。
    """
    active = str(st.session_state.get("active_project_id") or "")
    if active and core.load_project(active) is None \
            and not core.is_system_project_id(active):
        st.session_state.pop("active_project_id", None)
    chosen = str(st.session_state.get("task_project_id") or "")
    if chosen and core.load_project(chosen) is None \
            and not core.is_system_project_id(chosen):
        st.session_state["task_project_id"] = None
        st.session_state.pop("task_project_choice", None)


def _refresh_projects_after():
    """任何 Project 操作成功后的统一收尾：刷新派生导航状态并提示成功。

    侧栏「项目上下文」、项目列表、新建任务页的上下文都从磁盘派生，因此这里只做
    一件事：让失效的导航状态与磁盘一致，并把"操作成功"变成一次 toast。
    """
    _reload_project_state()


# ================= 统一导航入口（项目 / 任务 / 历史卡片）=================
# 历史卡片的标题点击、卡片空白点击、右侧 CTA、侧栏「项目上下文」，全部走这里。
# 之前每个入口各写一份 session_state 赋值，三套逻辑很容易漂移——这里收敛成一份。
#
# `destination` 用人类可读的名字（overview/translation/review/report/delivery），
# 不是一个已经映射好的 section，因为 CTA 的语义是"去哪里做事"，而不是"打开哪一页"。
_JOB_DESTINATIONS = {
    "overview": "overview",
    "translation": "translation",
    "terms": "terms",
    "review": "review",
    "report": "report",
    "qa": "qa",
    "delivery": "delivery",
}

# Project 详情的一级 tab（顺序即信息架构）。`active_project_tab` 是导航状态，
# 与 `workspace_section` 对称：项目与任务各有各的层级，互不覆盖。
PROJECT_TABS = (("overview", "概览"), ("tasks", "任务"),
                ("knowledge", "项目知识"), ("settings", "设置"))
PROJECT_TAB_LABELS = dict(PROJECT_TABS)


def _remember_project_visit(project_id):
    """Keep a short-lived session list for switcher recency ordering."""
    canonical = core._project.canonical_project_id(project_id)
    recent = [str(item) for item in
              (st.session_state.get("project_switcher_recent") or [])]
    recent = [item for item in recent if item != canonical]
    recent.insert(0, canonical)
    st.session_state["project_switcher_recent"] = recent[:8]


def _route_params(**mapping):
    """把导航状态镜像到 URL query params（`/projects/<uuid>` 的可分享等价物）。

    Streamlit 的脚本式路由没有真实 path segment，因此用 `project=<uuid>` 表达
    "当前打开的是哪个项目"。它只镜像**稳定 ID**，不镜像显示名称——名称是标签，
    改名不应该改变任何链接。

    空值必须**删除**该参数，而不是写成 `?project=None`：后者会让 URL 看起来像
    "打开了一个叫 None 的项目"。
    """
    for key, value in mapping.items():
        text = str(value or "").strip()
        try:
            if text:
                st.query_params[key] = text
            elif key in st.query_params:
                del st.query_params[key]
        except Exception:  # 老版本 / 非浏览器上下文：路由镜像不是关键路径
            pass


def _open_job(job_id, state, destination="overview"):
    """唯一入口：打开一个任务，并落到指定阶段。

    只设置导航状态；滚动/恢复等副作用由调用方按需追加（例如 `resume=True`
    时再调 `_resume_job`）。不做 `st.rerun()`，让调用方的按钮/回调自然触发渲染。

    **只设置 task 侧状态**（`active_job_id`）。任务所属项目由任务 state 里的
    `project_id` 决定，不允许写进 `active_project_id`——那会把「打开任务」变成
    「打开项目」，让两个实体在导航状态里混成一个。Project 详情有自己的
    入口（`_open_project`）。
    """
    section = _JOB_DESTINATIONS.get(str(destination or "overview"), "overview")
    st.session_state.update(active_job_id=job_id,
                            app_view="workspace",
                            workspace_mode=True,
                            workspace_section=section)
    _route_params(project=None, view=None)
    return section


def _open_project(project_id, tab="overview"):
    """唯一入口：打开项目详情（`/projects/:projectId`）。

    与 `_open_job` 对称：Project 侧只写 `active_project_id` + `active_project_tab`，
    不写 `active_job_id`。当前任务保持打开（侧栏「当前任务」仍然可用），
    因为项目与任务互不替代。

    **路由标识永远是不可变 UUID**：`project_id` 可以是历史别名（`default`），
    这里先归一再写入导航状态与 URL，因此旧链接也能正确落到「未分类」。
    """
    canonical = _apply_project_context(project_id)
    st.session_state["active_project_tab"] = tab if tab in PROJECT_TAB_LABELS \
        else "overview"
    st.session_state.update(app_view="projects", workspace_mode=False,
                            projects_route="detail")
    _close_project_modals()
    _route_params(project=canonical, view=None)
    return canonical


def _projects_route():
    """`app_view == "projects"` 下正在看哪一层：`detail`（某个项目）或 `list`（项目中心）。

    **路由与上下文必须分开**。以前两者都由 `active_project_id` 兼任——进列表页就得把
    上下文清空，于是侧栏 selector 从「项目 A」翻成「未选择项目」，用户读到的是"我的
    上下文没了"，而实际上他只是去看了一眼项目列表。项目中心是**纯导航**：它不该
    修改当前 Project Context（需求 B）。

    没有显式标记时沿用旧推断（有 `active_project_id` 就是详情），这样归档 / 新建项目
    等直接写 `app_view` 的旧路径行为不变。
    """
    route = str(st.session_state.get("projects_route") or "")
    if route in ("list", "detail"):
        return route
    return "detail" if str(st.session_state.get("active_project_id") or "") else "list"


def _open_project_list():
    """进入项目列表（Project manager），不是开始翻译，也不是某个项目。

    **纯导航**：只改路由（`projects_route="list"`），不碰当前 Project Context——
    `active_project_id` 保留，侧栏 selector 因此在管理页上仍然显示"我在哪个项目里
    工作"。这同时满足需求 B 的两条：不修改上下文、且项目中心保持 active state。
    它还会收起任何展开着的切换面板，否则侧栏展开的下拉会跟着漂到管理页上。
    """
    st.session_state.update(app_view="projects", workspace_mode=False,
                            projects_route="list")
    st.session_state["active_project_tab"] = "overview"
    _close_project_modals()
    _close_all_project_switchers()
    _route_params(project=None, view="projects")


def _restore_route_from_params():
    """页面刷新后按 URL 恢复项目或语言资产工作区。"""
    try:
        project_id = str(st.query_params.get("project") or "").strip()
        requested_view = str(st.query_params.get("view") or "").strip().casefold()
        requested_tab = str(st.query_params.get("tab") or "").strip()
    except Exception:
        return
    if project_id:
        if st.session_state.get("active_project_id"):
            return
        record = core.load_project(project_id)
        if record is None and core.is_system_project_id(project_id):
            record = core.system_project_view()
        if record is None:
            # 项目已被删除：清掉失效路由，回项目列表并如实说明。
            _route_params(project=None, view="projects")
            _push_flash(f"链接指向的项目已不存在（{project_id}），已回到项目列表。",
                        tone="warning")
            return
        st.session_state["active_project_id"] = record["project_id"]
        st.session_state.update(app_view="projects", workspace_mode=False,
                                projects_route="detail")
        return

    # 项目中心（`view=projects`）是一个可分享的页面入口：它**不**携带项目上下文，
    # 所以恢复的是"列表路由"，上下文交由用户本次会话重新建立。已经打开了某个项目
    # 的时候不覆盖（页面重连不该把详情页踢回列表）。
    if requested_view == "projects" and not st.session_state.get("active_project_id"):
        st.session_state.update(app_view="projects", workspace_mode=False,
                                projects_route="list")
        st.session_state["active_project_tab"] = "overview"
        return

    # 语言资产工作区是一个真正可分享的页面入口。只接受已知 Tab，避免一个
    # 任意的 `?tab=` 参数把普通新建任务页误切走；`view=library` 可单独打开
    # 默认术语库，`view=library&tab=review` 打开指定 Tab。
    if requested_view == "library" or requested_tab in _language_assets.VALID_TABS:
        st.session_state.update(app_view="library", workspace_mode=False)
        if requested_tab in _language_assets.VALID_TABS:
            st.session_state["library_tab"] = requested_tab


def _open_job_cta(job_id, state, cta):
    """按卡片 CTA 进入对应流程。

    CTA 点击**不经过 Overview**：用户点"继续审校"就是要去审校页。只有
    "查看进度 / 继续处理 / 打开项目"这三个语义本来就是"先看看整体"的才落 Overview。
    """
    cta = cta or {}
    _open_job(job_id, state, cta.get("destination") or "overview")
    if cta.get("resume"):
        _resume_job(job_id, state)
    st.rerun()


def _job_display_title(job):
    """侧栏与卡片共用的主标题解析：文档元数据优先，不拿完整文件名当标题。"""
    state = job.get("state") or {}
    return _history_view.document_title(state)


def _project_display_title(project):
    return str((project or {}).get("name") or "").strip()


def _history_card_html(view):
    """Translation Task 卡片视觉：标题 / 身份 / 状态 / 进度 / 问题数 / 最近更新。

    四行结构（回归测试守住，密度目标 105–120px）：

      1. display title
      2. author · source type · target language · domain
      3. status chip · segment progress · issue count（+ 所属项目）
      4. 最近更新                                       contextual CTA →

    第 4 行右侧的空位留给 contextual CTA：它由 `_render_history_page` 作为卡片
    内部的一个**真实按钮**渲染，本函数只画出留白。完整源文件名不作为主标题，
    只作为 hover 提示保留，避免丢信息。
    """
    chip = view["chip"]
    title = escape(view["title"])
    part = (f'<span class="tp-hcard-part">{escape(view["part_label"])}</span>'
            if view.get("part_label") else "")
    identity = escape(view["identity"]) if view.get("identity") else ""
    project = escape(view["project_name"]) if view.get("project_name") else ""
    issues = int(view.get("issue_count") or 0)
    issue_text = f"问题 {issues}" if issues else "无待处理问题"
    return (
        f'<div class="tp-hcard" title="{escape(view["filename"])}">'
        f'<h3 class="tp-hcard-title">{part}{title}</h3>'
        f'<div class="tp-hcard-sub">{identity}</div>'
        '<div class="tp-hcard-meta">'
        f'<span class="tp-hcard-chip is-{escape(chip["tone"])}">'
        f'{escape(chip["label"])}</span>'
        f'<span class="tp-hcard-progress">{escape(view["progress"])}</span>'
        f'<span class="tp-hcard-issues{" is-flagged" if issues else ""}">'
        f'{escape(issue_text)}</span>'
        + (f'<span class="tp-hcard-project">项目 {project}</span>' if project else "")
        + '</div>'
        '<div class="tp-hcard-foot">'
        f'<span class="tp-hcard-updated">最近更新 {escape(view["updated_label"])}</span>'
        '</div></div>')


def _render_history_page(jobs):
    """Translation Task 列表：每张卡片是一次具体的文档翻译执行。

    对象语义（回归测试守住）：这里列的是 **Tasks**，不是 Projects。Task 属于某个
    Project 只是它的属性，因此页面叫「历史任务」、卡片动作叫「打开任务」；Project
    有自己的入口（侧栏「项目」）。

    交互约定：
      - 整张卡片可点 → Task Overview（铺满卡片的透明 button）；
      - contextual CTA 在**卡片内部**，是真实按钮，z-index 高于点击层；
        两者是兄弟节点，一次点击只触发一个导航，不冒泡到 Overview；
      - 顶部 search 是主控件（约 55%），status / sort 是紧凑 select，三者不等宽；
      - 浅 surface + hairline + low shadow，不做重卡片。
    """
    views = []
    for job in jobs:
        state = job.get("state") or {}
        runtime_view = core.build_job_runtime_view(job["job_id"], state)
        runtime_status = (runtime_view.get("runtime_status")
                          or runtime_view.get("status") or "")
        delivery_label, _tone = _workspace_delivery_state(job["job_id"], state)
        snapshot = core.delivery_snapshot_status(job["job_id"], state)
        recovery = core.recovery_summary(job["job_id"], state)
        project = core.project_for_job(job["job_id"], state) or {}
        views.append(_history_view.history_card_view(
            state, job_id=job["job_id"], runtime_status=runtime_status,
            delivery_label=delivery_label,
            delivery_current=bool(snapshot.get("current")),
            saved_at=str(recovery.get("last_saved_at") or ""),
            project_name=_project_display_title(project),
        ))

    # search 是主控件；status / sort 只做紧凑筛选，三者不等宽。
    head_left, head_mid, head_right = st.columns([5.5, 2.3, 2.2], gap="small")
    query = head_left.text_input(
        "搜索历史任务", key="history_search", label_visibility="collapsed",
        placeholder="搜索任务名称、文件、作者或领域…")
    status_filter = head_mid.selectbox(
        "状态筛选", ["全部", "需要处理", "建议检查", "进行中", "已完成"],
        key="history_status", label_visibility="collapsed")
    order = head_right.selectbox(
        "排序", ["最近更新", "任务名称", "状态"],
        key="history_order", label_visibility="collapsed")

    visible = [view for view in views
               if _history_view.card_matches(view, query=query,
                                             status=status_filter)]
    visible.sort(key=lambda item: _history_view.sort_key(item, order),
                 reverse=(order == "最近更新"))
    if not visible:
        st.markdown('<div class="tp-empty">没有符合条件的历史任务。</div>',
                    unsafe_allow_html=True)
        return

    for view in visible:
        job_id = view["job_id"]
        state = next(job["state"] for job in jobs if job["job_id"] == job_id)
        with st.container(key=f"history_item_{job_id}"):
            # 卡片本体 + 两个导航入口。定位容器只包住卡片，恢复提示在外面，
            # 否则绝对定位的 CTA 会锚到提示下方。
            with st.container(key=f"history_cardframe_{job_id}"):
                st.markdown(_history_card_html(view), unsafe_allow_html=True)
                # 点击层：铺满整张卡片的透明按钮 → Task Overview。
                if st.button("打开任务", key=f"history_card_{job_id}",
                             width="stretch"):
                    _open_job(job_id, state, "overview")
                    st.rerun()
                # contextual CTA：卡片内部的真实按钮。它与点击层是**兄弟节点**且
                # z-index 更高，所以点击 CTA 不会触发整卡导航（无冒泡可穿透）。
                if st.button(view["cta"]["label"], key=f"history_cta_{job_id}",
                             width="stretch",
                             type="primary" if view["cta"]["label"] in
                             {"继续处理", "继续审校", "继续翻译"} else "secondary"):
                    _open_job_cta(job_id, state, view["cta"])
            recovery = core.recovery_summary(job_id, state)
            if view["counts"]["translated"] < view["counts"]["total"] or \
                    view["chip"]["kind"] in {"interrupted", "running"}:
                st.caption(f"最近更新 {_format_saved_at(recovery['last_saved_at'])}"
                           " · 自动保存已开启")
                if recovery.get("current_batch"):
                    current = recovery["current_batch"]
                    st.warning(
                        f"处理中断：当前批次已保存 "
                        f"{current['completed_segments']}/{current['segment_count']} 段；"
                        "继续后只处理未完成内容。")
            _render_snapshot_versions(job_id, state, "history")


def _relative_project_updated_at(value, *, now=None):
    """Return the short relative timestamp used by project scan cards."""
    if not value:
        return "刚刚更新"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "最近更新"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    seconds = max(0, int((reference - parsed).total_seconds()))
    if seconds < 60:
        return "刚刚更新"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时前"
    days = hours // 24
    if days < 2:
        return "昨天更新"
    return f"{days} 天前更新"


# ---- 项目卡：先回答"这个项目现在在做什么" ----
# 卡片的信息优先级固定（回归测试守住）：
#   1. 项目名称   2. 任务分布   3. 最近工作   4. 知识资产摘要   5. 最近更新时间
#
# 「0 术语 · 0 规则 · 0 决定 · 0 记忆」这类数据库式统计**不再出现**在卡上：
# 没有数据的行留空，由 markup 隐藏，而不是渲染一排 0。

#: 任务分布的分桶顺序即展示顺序；只渲染计数非零的桶。
_PROJECT_TASK_BUCKETS = (
    ("active", "进行中"),
    ("attention", "待处理"),
    ("pending", "待开始"),
    ("done", "已完成"),
)
# 项目卡上的工作分布**不是**任务详情的权威状态：它只用 runtime 状态与段落完成度
# 做一次聚合。逐任务派生 `_task_overview_state`（含交付 / 合规 / QA 投影）成本高，
# 而任务自己的页面已经由 canonical overview 渲染，那里才是权威。
_PROJECT_RUNTIME_ACTIVE = frozenset({
    "running", "resume_requested", "queued", "starting", "waiting_external",
    "cancelling", "waiting_manual"})
_PROJECT_RUNTIME_ATTENTION = frozenset({
    "interrupted", "failed", "stalled", "cancelled"})

#: 状态筛选：默认「活动中」，归档项目从首屏移出但可一键找回。
_PROJECT_STATUS_OPTIONS = ("全部", "活动中", "已归档")
#: 排序是显式动词，不是一个含糊的"最近更新"下拉。
_PROJECT_ORDER_OPTIONS = ("最近更新", "最早更新", "名称 A-Z", "任务最多")
_PROJECT_VIEW_MODES = ("grid", "list")


def _project_translation_progress(state):
    """(已译, 总段数)。与 planner 的 translation 维度同规则：pairs 优先，否则 paras。

    纯 state 投影，不读盘、不派生状态，因此可以在项目列表上对每个任务调用。
    """
    state = state if isinstance(state, dict) else {}
    pairs = state.get("pairs") or []
    paras = state.get("paras") or []
    rows = pairs if pairs else paras
    total = len(rows)
    done = sum(1 for row in rows
               if isinstance(row, dict) and str(row.get("target") or "").strip())
    return done, total


def _project_job_bucket(job):
    """任务在项目卡上的工作分布桶。

    「已完成」必须与任务详情的 canonical lifecycle 同义（只有**已冻结交付**才算
    完成）：译文全部翻完但还没交付是"进行中 / 待交付"，不是"已完成"。否则同一个
    项目在卡片上写"2 已完成"、进详情却是"3 进行中"，两处说法互相打架。
    """
    state = job.get("state") or {}
    runtime = core.build_job_runtime_view(job["job_id"], state)
    status = str(runtime.get("runtime_status") or runtime.get("status") or "")
    if status in _PROJECT_RUNTIME_ATTENTION:
        return "attention"
    if status in _PROJECT_RUNTIME_ACTIVE:
        return "active"
    if str(state.get("delivery_status") or "") == "final":
        return "done"
    done, _total = _project_translation_progress(state)
    return "active" if done or state.get("p2_done") else "pending"


def _project_job_activity(job):
    """项目卡的「最近工作」：最近任务的标题 / 状态 / 段落进度。

    状态词来自 canonical 交付状态（`_workspace_delivery_state`），百分比来自段落
    完成度。两者都是既有真实数据；没有进度数据时不显示百分比，也不编造。
    """
    state = job.get("state") or {}
    job_id = job["job_id"]
    done, total = _project_translation_progress(state)
    percent = round(done * 100 / total) if total else 0
    label, _tone = _workspace_delivery_state(job_id, state)
    return {
        "job_id": job_id,
        "title": _job_display_title(job),
        "status": label,
        # 只有"部分完成"才显示百分比：0% / 100% 是噪音，状态词已经说清楚了。
        "progress": f"{percent}%" if total and 0 < percent < 100 else "",
    }


def _project_knowledge_summary(view):
    """知识资产压成一行：术语 / 规则 /（决定）/ 记忆。全为 0 时返回空串。"""
    parts = []
    for count, label in (
            (int(view.get("glossary_count") or 0), "术语"),
            (int(view.get("style_rule_count") or 0), "规则"),
            (int(view.get("human_decision_count") or 0), "决定"),
            (int(view.get("translation_memory_count") or 0), "记忆")):
        if count:
            parts.append(f"{label} {count}")
    return " · ".join(parts)


def _project_card_view(view, project):
    """把项目摘要投影成一张紧凑项目卡需要的全部字段。

    返回的字符串字段为空即表示"这条没有真实数据"，由 markup 决定隐藏。
    """
    jobs = list(view.get("jobs") or [])
    buckets = {key: 0 for key, _label in _PROJECT_TASK_BUCKETS}
    for job in jobs:
        buckets[_project_job_bucket(job)] += 1
    breakdown = " · ".join(
        f"{buckets[key]} {label}" for key, label in _PROJECT_TASK_BUCKETS
        if buckets[key])
    latest = _recent_jobs(jobs, 1)
    return {
        "project_id": view["project_id"],
        "name": str(view.get("name") or "—"),
        "description": str(project.get("description") or "").strip(),
        "archived": bool(view.get("status") == "archived"),
        "job_count": len(jobs),
        "breakdown": breakdown,
        "activity": _project_job_activity(latest[0]) if latest else None,
        "knowledge": _project_knowledge_summary(view),
        "updated": _relative_project_updated_at(view.get("updated_at")),
        "updated_exact": _format_saved_at(view.get("updated_at")),
    }


def _project_card_markup(card):
    """Project Hub 的项目卡：身份 / 状态 / 行动三个区。

    卡片刻意**不**回答"这个项目的全部事实"，只回答三个问题：

        1. 这是哪个项目？           → head：图标 + 名称 +（已归档 chip）
        2. 它现在是什么状态？       → body：任务摘要（主）+ 描述 / 最近工作（次）
        3. 我下一步能做什么？       → foot：ghost CTA + 知识摘要 + 最近更新

    因此这里有三条硬约束（回归测试守住）：

      - 空项目**不**写成一句长说明，而是一行短提示 `可开始积累术语与翻译记忆`，
        它占据的正是"有任务时最近工作"那一行，让两种状态的卡片节奏一致；
      - 全 0 的统计不上卡（`0 术语 · 0 规则` 一律省略，不写成一行 0）；
      - 更新时间是卡上**最弱**的元素（11.5px / 最低对比度），且永远不和 CTA 争行。
    """
    name = escape(str(card.get("name") or "—"))
    status_chip = ('<span class="tp-chip is-archived">已归档</span>'
                   if card.get("archived") else "")
    description = str(card.get("description") or "").strip()
    desc_html = (f'<div class="tp-pcard-desc" title="{escape(description)}">'
                 f'{escape(description)}</div>' if description else "")

    job_count = int(card.get("job_count") or 0)
    activity = card.get("activity") or None
    is_empty = not job_count and not card.get("archived")
    if job_count:
        work_html = (
            '<div class="tp-pcard-work">'
            f'<span class="tp-pcard-tasks"><strong>{job_count}</strong> 个任务</span>'
            + (f'<span class="tp-pcard-breakdown">{escape(card["breakdown"])}</span>'
               if card.get("breakdown") else "")
            + '</div>')
    else:
        work_html = ('<div class="tp-pcard-work is-quiet">'
                     '<span class="tp-pcard-tasks">尚无任务</span></div>')

    recent_html = ""
    if activity is not None:
        meta = " · ".join(part for part in (activity["status"],
                                            activity["progress"]) if part)
        recent_html = (
            '<div class="tp-pcard-recent">'
            '<span class="tp-pcard-recent-label">最近</span>'
            f'<em title="{escape(activity["title"])}">'
            f'{escape(activity["title"])}</em>'
            f'<span class="tp-pcard-recent-meta">{escape(meta)}</span>'
            '</div>')
    elif is_empty:
        # 一行短提示，取代原来的长句式说明：它只说明"这一步能拿到什么"。
        recent_html = ('<div class="tp-pcard-hint">'
                       '可开始积累术语与翻译记忆</div>')

    knowledge = str(card.get("knowledge") or "")
    # CTA 槽位永远渲染：空项目挂 `+ 创建任务`、有任务的项目挂 `查看项目`，
    # 两者都是绝对定位的真实按钮（z-index 高于整卡点击层），这里只负责留位置，
    # 让"知识摘要 + 最近更新"永远不和它抢同一行。
    cta_slot = '<span class="tp-pcard-cta-slot" aria-hidden="true"></span>'
    return (
        '<div class="tp-pcard' + (' is-empty' if is_empty else '') + '">'
        '<div class="tp-pcard-head">'
        '<span class="tp-project-icon" aria-hidden="true">'
        '<span class="material-symbols-rounded">folder</span></span>'
        f'<strong title="{name}">{name}</strong>{status_chip}'
        '</div>'
        '<div class="tp-pcard-body">'
        f'{work_html}'
        f'{desc_html}'
        f'{recent_html}'
        '</div>'
        '<div class="tp-pcard-foot">'
        f'{cta_slot}'
        '<span class="tp-pcard-meta">'
        f'<span class="tp-pcard-knowledge">{escape(knowledge)}</span>'
        f'<span class="tp-pcard-updated" title="{escape(card["updated_exact"])}">'
        f'{escape(card["updated"])}</span>'
        '</span>'
        '</div>'
        '</div>')


def _project_row_markup(card):
    """List View 的一行：同一份卡数据，横向排布，适合项目很多时扫读。"""
    name = escape(str(card.get("name") or "—"))
    status_chip = ('<span class="tp-chip is-archived">已归档</span>'
                   if card.get("archived") else "")
    activity = card.get("activity") or None
    if activity is not None:
        meta = " · ".join(part for part in (activity["status"],
                                            activity["progress"]) if part)
        recent = (f'<span class="tp-prow-recent-label">最近</span>'
                  f'<em title="{escape(activity["title"])}">'
                  f'{escape(activity["title"])}</em>'
                  f'<span class="tp-prow-recent-meta">{escape(meta)}</span>')
    else:
        recent = '<span class="tp-prow-recent-label">尚无任务</span>'
    job_count = int(card.get("job_count") or 0)
    if job_count:
        tasks = (f'<strong>{job_count}</strong> 个任务'
                 + (f' · {escape(card["breakdown"])}' if card.get("breakdown")
                    else ""))
    else:
        # 「尚无任务」已经出现在 recent 槽位，这里不再重复一次。
        tasks = ""
    knowledge = str(card.get("knowledge") or "")
    return (
        '<div class="tp-prow">'
        '<div class="tp-prow-main">'
        '<span class="tp-project-icon" aria-hidden="true">'
        '<span class="material-symbols-rounded">folder</span></span>'
        '<div class="tp-prow-copy">'
        f'<div class="tp-prow-title"><strong title="{name}">{name}</strong>'
        f'{status_chip}</div>'
        f'<div class="tp-prow-recent">{recent}</div>'
        '</div></div>'
        '<div class="tp-prow-facts">'
        f'<span class="tp-prow-tasks">{tasks}</span>'
        f'<span class="tp-prow-knowledge">{escape(knowledge)}</span>'
        '</div>'
        f'<span class="tp-prow-updated" title="{escape(card["updated_exact"])}">'
        f'{escape(card["updated"])}</span>'
        '</div>')


def _project_matches(view, query):
    """项目搜索：名称 / 描述 / 项目 ID 都可命中（ID 可粘贴，便于核对）。"""
    text = str(query or "").strip().casefold()
    if not text:
        return True
    haystack = " ".join(str(view.get(key) or "") for key in
                        ("name", "description", "project_id")).casefold()
    return text in haystack


def _sort_project_views(views, order):
    """排序键必须与 `_PROJECT_ORDER_OPTIONS` 一一对应。"""
    if order == "名称 A-Z":
        return sorted(views, key=lambda item: str(item.get("name") or "").casefold())
    if order == "任务最多":
        return sorted(views, key=lambda item: int(item.get("job_count") or 0),
                      reverse=True)
    if order == "最早更新":
        return sorted(views, key=lambda item: str(item.get("updated_at") or ""))
    return sorted(views, key=lambda item: str(item.get("updated_at") or ""),
                  reverse=True)


def _load_project_views():
    """项目页的唯一数据入口：一次扫盘 → 分区 → 逐项派生摘要。"""
    sections = core.project_sections()
    views, records = [], {}
    for bucket in ("system", "active", "archived"):
        for project in sections[bucket]:
            summary = core.project_summary(project)
            views.append(summary)
            records[summary["project_id"]] = project
    return sections, views, records


def _knowledge_module(*, key, title, count, note, empty_hint, entry_label,
                      opened_label, body):
    """一个知识模块：count + 一句说明 + 当前状态 / empty hint + 入口。

    它是 Level B 的 compact section，不是一个塞满长说明的白盒子：标题与 count 同行，
    下面最多一句说明；详情默认收起，点入口才展开。四个模块共用这一份实现，所以
    「锁定术语 / 风格规则 / 人工决定 / 已审核记忆」不会各自漂移成四种版式。
    """
    open_key = f"pd_knowledge_open_{key}"
    opened = bool(st.session_state.get(open_key))
    with st.container(key=f"pd_module_{key}"):
        head_left, head_right = st.columns([5, 2], gap="medium")
        with head_left:
            st.markdown(
                '<div class="tp-mod-head">'
                f'<span class="tp-mod-title">{escape(title)}</span>'
                f'<span class="tp-mod-count">{int(count or 0)}</span>'
                '</div>'
                f'<p class="{"tp-mod-note" if count else "tp-mod-empty"}">'
                f'{escape(note if count else empty_hint)}</p>',
                unsafe_allow_html=True)
        with head_right, st.container(key=f"pd_kmod_entry_{key}"):
            if st.button(opened_label if opened else entry_label,
                         key=f"pd_knowledge_toggle_{key}"):
                st.session_state[open_key] = not opened
                st.rerun()
        if opened:
            body()


def _knowledge_glossary_body(project):
    """锁定术语：术语版本 + 术语表（真实数据，未确认的候选不在其中）。"""
    version = (project.get("glossary_versions") or [])
    if version:
        latest = version[-1]
        st.caption(f"术语版本 v{latest['version']} · "
                   f"hash {str(latest.get('glossary_hash') or '')[:12]}… · "
                   f"冻结于 {_format_saved_at(latest.get('frozen_at'))}")
    else:
        st.caption("项目尚无术语版本。翻译完成后在任务里确认术语，再提升到项目知识。")
    rows = [{"源术语": entry.get("source", ""),
             "首选译名": entry.get("preferred") or entry.get("target", ""),
             "保留": "是" if entry.get("behavior") == "preserve" else "",
             "禁止译名": "、".join(entry.get("forbidden") or []),
             "范围": entry.get("scope", "")}
            for entry in project.get("glossary") or []]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 height=min(420, 40 + 35 * len(rows)))


def _knowledge_rules_body(project):
    """风格规则：已确认的规则列表 + 提升记录（只读审计）。"""
    for rule in project.get("style_rules") or []:
        st.markdown(f"- {escape(str(rule.get('rule') or rule.get('text') or ''))}")
    _knowledge_promotion_body(project)


def _knowledge_decisions_body(project):
    """人工决定：只读审计流水，按时间倒序取最近 20 条。"""
    for record in (project.get("human_decisions") or [])[-20:]:
        st.caption(
            f"{escape(str(record.get('decided_at') or record.get('timestamp') or ''))} · "
            f"{escape(str(record.get('decision') or record.get('action') or ''))} · "
            f"{escape(str(record.get('actor') or ''))}")


def _knowledge_promotion_body(project):
    """提升记录：某次提升往各类知识里加了什么（真实数据，不 mock 具体条目）。"""
    log = project.get("promotion_log") or []
    if not log:
        return
    with st.expander(f"提升记录（{len(log)} 次）", expanded=False):
        for entry in log[-20:]:
            added = entry.get("added") or {}
            detail = "、".join(f"{key} +{value}" for key, value in added.items()
                              if value)
            st.caption(f"{escape(str(entry.get('at') or ''))} · "
                       f"来自任务 {escape(str(entry.get('source_job_id') or '—'))} · "
                       f"{escape(detail or '无新增')}")


def _knowledge_memory_body(project, core_view):
    """已审核记忆：本项目已审校记忆的复用说明（+ 从系统工作区并入的显式动作）。

    翻译记忆按项目隔离：新建项目从空白记忆开始。把「未分类」的既有积累带过来是
    一个显式动作，而不是静默共享——只在"本项目为空且未分类有内容"时提供。
    """
    is_system = core.is_system_project(project)
    if core_view["translation_memory_count"]:
        st.caption("这些译文通过了独立审校门槛，会在本项目的后续任务中被复用。")
        return
    system_tm_count = len(core.load_tm(core.SYSTEM_PROJECT_ID))
    if not is_system and system_tm_count:
        st.caption(f"系统工作区「{core.SYSTEM_PROJECT_NAME}」里有 {system_tm_count} "
                   "条已审校记忆。翻译记忆按项目隔离，新项目不会自动共享它们。")
        if st.button("把「未分类」的已审校记忆并入本项目",
                     key=f"project_adopt_tm_{project['project_id']}",
                     width="content"):
            try:
                added = core.copy_system_tm_to_project(project["project_id"])
            except ValueError as exc:
                _push_flash(f"并入失败：{exc}", tone="error")
            else:
                _push_flash(f"已并入 {added} 条已审校记忆。" if added
                            else "没有可并入的新条目。",
                            tone="success" if added else "info")
            st.rerun()
        return
    st.caption("本项目还没有已审校记忆；通过独立审校的段落会自动入库到本项目。")


def _render_project_conflicts(project):
    """待决冲突：导入时发现的"本地与导入不一致"，由人逐条决定。

    这些不是报告里的临时信息，而是持久待决项——因此关掉页面再回来仍然在。
    默认做法是保留本地（导入永不静默覆盖），采纳导入版本是一个明确动作。
    """
    conflicts = core.list_project_conflicts(project["project_id"])
    if not conflicts:
        return
    with st.container(border=True):
        st.markdown(f'<div class="tp-field-head"><strong>待处理的导入冲突'
                    f'</strong><span>{len(conflicts)} 条</span></div>',
                    unsafe_allow_html=True)
        st.caption("导入不会静默覆盖本地：这些译名与导入版本不一致，需要你决定保留哪一个。"
                   "决定会记入项目提升记录。")
        for conflict in conflicts:
            kind_label = "术语" if conflict["kind"] == "glossary" else "已审校译文"
            source = escape(str(conflict["source"])[:60])
            st.markdown(
                f'<div class="tp-history-copy"><strong>{source}</strong>'
                f'<span>{kind_label} · 来自「{escape(str(conflict.get("imported_from") or "导入文件"))}」</span>'
                f'<span>本地：{escape(str(conflict["local"])[:40])}'
                f'　|　导入：{escape(str(conflict["incoming"])[:40])}</span></div>',
                unsafe_allow_html=True)
            take, keep = st.columns(2)
            if take.button("采纳导入版本", width="stretch",
                           key=f"conflict_take_{conflict['conflict_id']}"):
                core.resolve_project_conflict(project["project_id"],
                                              conflict["conflict_id"],
                                              adopt_incoming=True, actor="用户")
                st.rerun()
            if keep.button("保留本地版本", width="stretch",
                           key=f"conflict_keep_{conflict['conflict_id']}"):
                core.resolve_project_conflict(project["project_id"],
                                              conflict["conflict_id"],
                                              adopt_incoming=False, actor="用户")
                st.rerun()
        all_keep, all_take = st.columns(2)
        if all_keep.button("全部保留本地", width="stretch",
                           key=f"conflict_all_keep_{project['project_id']}"):
            core.resolve_all_project_conflicts(project["project_id"],
                                               adopt_incoming=False, actor="用户")
            st.rerun()
        if all_take.button("全部采纳导入", width="stretch",
                           key=f"conflict_all_take_{project['project_id']}",
                           help="把本地译名替换为导入版本；此动作不可撤销。"):
            core.resolve_all_project_conflicts(project["project_id"],
                                               adopt_incoming=True, actor="用户")
            st.rerun()


def _render_project_job_mover(project):
    """批量把任务移入本项目：**secondary collapsible panel，默认收起**。

    它是二级功能，不是页面主内容。此前它常驻展开，与任务空态并列铺在同一页上，
    页面同时出现两个"主要内容块"、两个"没有任务"的表达。现在收进一个默认折叠的
    panel：需要的人展开它，不需要的人看到的是一个安静的入口行。

    改归属会改变任务今后使用哪一套项目记忆（术语、风格、翻译记忆）。它**不会**
    改动已有译文，也不会自动迁移术语——那些要通过 Memory gate 显式提升。
    """
    others = [job for job in core.list_jobs()
              if core.resolved_project_id(job["state"]) != project["project_id"]]
    with st.container(key="pd_mover"):
        # 显式 key：折叠状态是面板自身的状态，可被测试与外部状态直接驱动。
        with st.expander("把任务移入本项目", expanded=False,
                         key=f"project_move_panel_{project['project_id']}"):
            if not others:
                st.caption("没有其它项目下的任务可以移入。")
                return
            st.caption("移动只改变归属，不会修改已有译文；术语与记忆不会自动迁移，"
                       "需要通过项目记忆提升显式确认。")
            labels = {job["job_id"]: f'{job["state"].get("filename") or "?"}'
                                     f'（{core.project_name_for_id(core.resolved_project_id(job["state"]))}）'
                      for job in others}
            chosen = st.multiselect(
                "选择要移入的任务", list(labels), format_func=lambda key: labels[key],
                key=f"project_move_pick_{project['project_id']}")
            move_tm = st.checkbox(
                "同时把它们的已审校译文并入本项目记忆（只增不改）",
                key=f"project_move_tm_{project['project_id']}")
            st.caption("正在运行的任务不能改归属：它已经读取了原项目的记忆。")
            if st.button("移入本项目", key=f"project_move_go_{project['project_id']}",
                         disabled=not chosen, width="content"):
                result = core.assign_jobs_to_project(
                    chosen, project["project_id"], move_translations=move_tm)
                if result["moved"]:
                    st.success(f"已移入 {len(result['moved'])} 个任务；"
                               f"并入已审校记忆 {result['tm_added']} 条。")
                for item in result["skipped"]:
                    st.warning(
                        f"{labels.get(item['job_id'], item['job_id'])}：{item['reason']}")
                if result["moved"]:
                    st.rerun()


# ================= Project 管理页与项目详情 =================
# 信息架构（回归测试守住）：
#
#   /projects                 管理页：系统工作区 + 活动项目 + 搜索 + 已归档入口 + 新建
#   /projects/:project_id     详情：概览 / 任务 / 项目记忆 / 设置
#
# 项目卡片整体可点进入详情；右侧 overflow menu 提供打开项目、重命名、编辑、
# 归档、删除。系统工作区「未分类」在同一页但**不可**重命名 / 归档 / 删除。


def _project_overflow_menu(project, *, archived):
    """卡片右侧 overflow menu：只承担 **secondary actions**。

    popover 与整卡点击层是兄弟节点且 z-index 更高，因此点菜单不会触发"打开项目"。
    「打开项目」不在菜单里——整卡已经是主入口，菜单里再放一次只会让人以为卡片
    本身不可点。删除是 destructive，必须走二次确认的弹窗。
    """
    project_id = project["project_id"]
    with st.container(key=f"project_menu_{project_id}"):
        with st.popover("⋯", help="更多项目操作"):
            # 与 Project Detail 的 ⋯ 共用同一套轻量 menu card 视觉（同一个 Menu 组件）。
            # key 必须带 project_id：这个函数每张卡都调一次，写死常量会在第二个项目
            # 上直接抛 StreamlitDuplicateElementKey。视觉共用靠 CSS 的
            # [class*="st-key-pd_menu_body"] 前缀匹配，不靠共享同一个 key。
            with st.container(key=f"pd_menu_body_{project_id}"):
                st.caption(str(project["name"]))
                if st.button("重命名", key=f"pm_rename_{project_id}",
                             icon=":material/edit:", width="stretch"):
                    _open_project_modal("rename", project_id)
                    st.rerun()
                if st.button("编辑名称与描述", key=f"pm_edit_{project_id}",
                             icon=":material/description:", width="stretch"):
                    _open_project_modal("edit", project_id)
                    st.rerun()
                if archived:
                    if st.button("恢复为活动项目", key=f"pm_restore_{project_id}",
                                 icon=":material/unarchive:", width="stretch"):
                        _open_project_modal("restore", project_id)
                        st.rerun()
                else:
                    if st.button("归档", key=f"pm_archive_{project_id}",
                                 icon=":material/archive:", width="stretch"):
                        _open_project_modal("archive", project_id)
                        st.rerun()
                st.download_button(
                    "导出项目", data=core.export_project_memory(project_id),
                    file_name=f"foliothread-project-{project_id}.json",
                    mime="application/json", key=f"pm_export_{project_id}",
                    icon=":material/download:", width="stretch",
                    help="导出术语、风格、人工决定审计与本项目的已审校记忆；"
                         "不含任务状态、源文档或任何凭据。")
                st.divider()
                with st.container(key=f"pd_menu_danger_{project_id}"):
                    if st.button("删除", key=f"pm_delete_{project_id}",
                                 icon=":material/delete:", width="stretch"):
                        _open_project_modal("delete", project_id)
                        st.rerun()


def _project_card(view, project, *, archived=False):
    """一张项目卡：整卡可点 + 右侧 overflow menu + 底部左侧**一个** ghost CTA。

    点击卡片主体的**任意位置**都进入项目概览页；不需要用户去找「打开」按钮。
    底部的 ghost CTA 是同一个槽位的两种动词，由状态决定：

        尚未有任何任务  →  `+ 创建任务`：进入新建任务流程，并**自动带上本项目**
        已经有任务      →  `查看项目`  ：进入项目概览页

    两者都必须是**真实按钮**，并且是整卡点击层的**兄弟节点**（z-index 更高），
    否则点它们会被整卡导航吞掉。
    """
    project_id = project["project_id"]
    card = _project_card_view(view, project)
    with st.container(key=f"project_row_{project_id}"):
        st.markdown(_project_card_markup(card), unsafe_allow_html=True)
        # 整卡可点：HTML 负责视觉，透明覆盖按钮负责点击与键盘。
        if st.button("打开项目", key=f"project_open_{project_id}", width="stretch"):
            _open_project(project_id)
            st.rerun()
        if not archived:
            if not card.get("job_count"):
                with st.container(key=f"project_empty_cta_{project_id}"):
                    if st.button("创建任务", key=f"project_card_create_{project_id}",
                                 icon=":material/add:", width="content",
                                 help="在「%s」下创建第一个翻译任务" % card["name"]):
                        _begin_new_task(project_id)
                        st.rerun()
            else:
                with st.container(key=f"project_view_cta_{project_id}"):
                    if st.button("查看项目", key=f"project_card_view_{project_id}",
                                 icon=":material/arrow_forward:", width="content",
                                 help="打开「%s」的项目详情" % card["name"]):
                        _open_project(project_id)
                        st.rerun()
        _project_overflow_menu(project, archived=archived)


def _project_list_row(view, project, *, archived=False):
    """List View 的一行：与卡片同一份数据、同一套动作。"""
    project_id = project["project_id"]
    card = _project_card_view(view, project)
    with st.container(key=f"project_row_{project_id}"):
        st.markdown(_project_row_markup(card), unsafe_allow_html=True)
        if st.button("打开项目", key=f"project_open_{project_id}", width="stretch"):
            _open_project(project_id)
            st.rerun()
        _project_overflow_menu(project, archived=archived)


def _uncategorized_strip(view, project):
    """系统工作区「未分类」的轻量系统入口（72–88px）。

    它不是项目：没有项目卡的面积、没有 overflow menu、没有知识资产统计。
    它只回答"有多少任务还没有归属"，整条可点进入未分类任务列表。

    count 只出现**一次**（在标题行右侧，与「查看 →」同一行）；副标题只说明这是什么，
    不再重复数字。
    """
    project_id = project["project_id"]
    job_count = int(view.get("job_count") or 0)
    count_html = (f'<span class="tp-uncat-count">{job_count} 个</span>'
                  if job_count else "")
    meta = ("尚未归入任何项目的任务" if job_count
            else "暂时没有未归入项目的任务")
    with st.container(key="project_system_zone"):
        st.markdown(
            '<div class="tp-section-head is-inline">'
            '<strong>系统任务区</strong>'
            '<span class="tp-section-note">系统工作区 · 不属于任何项目</span>'
            '</div>', unsafe_allow_html=True)
        with st.container(key="project_uncategorized"):
            st.markdown(
                '<div class="tp-uncat">'
                '<span class="tp-uncat-icon" aria-hidden="true">'
                '<span class="material-symbols-rounded">inbox</span></span>'
                '<div class="tp-uncat-copy">'
                '<div class="tp-uncat-head">'
                '<span class="tp-uncat-title">未分类任务'
                '<span class="tp-uncat-tag">Inbox</span></span>'
                '<span class="tp-uncat-right">'
                f'{count_html}'
                '<span class="tp-uncat-action">查看 →</span>'
                '</span></div>'
                f'<div class="tp-uncat-meta">{escape(meta)}</div>'
                '</div>'
                '</div>', unsafe_allow_html=True)
            if st.button("查看未分类任务", key=f"project_open_{project_id}",
                         width="stretch"):
                _open_project(project_id)
                st.rerun()


def _empty_projects_state():
    """一个项目都没有时的首屏：说明项目能集中管理什么，并给出两个真实入口。"""
    st.markdown(
        '<div class="tp-empty-card tp-hub-empty">'
        '<strong>还没有项目</strong>'
        '<span>项目可以集中管理：任务、术语、翻译规则和项目记忆。'
        '项目不是必须先建——没有归属的任务会留在「未分类任务」里。</span>'
        '</div>', unsafe_allow_html=True)
    # 两个入口按内容宽度排布，不各占一半：空状态的主次关系必须看得出来。
    create_col, import_col, _spacer = st.columns([1.15, 1.15, 2.4])
    if create_col.button("创建第一个项目", key="project_empty_create",
                         type="primary", icon=":material/add:", width="stretch"):
        _clear_project_form()
        _open_project_modal("new")
        st.rerun()
    if import_col.button("导入已有项目", key="project_empty_import",
                         width="stretch", icon=":material/upload:"):
        _open_project_modal("import")
        st.rerun()


def _render_project_detail(project):
    """`/projects/:projectId`：真实项目的 Project Command Center。

    一级 IA：概览 / 任务 / 项目知识 / 设置。

    关键约束（回归测试守住）：
      - header 只回答"这是什么项目、现在什么状态、下一步做什么"，**不出现**
        UUID / Project ID / 类型 / 创建时间 / 更新时间——那些是设置里的高级信息；
      - `jobs` / 派生摘要**只加载一次**，向下传给各 tab，避免同一份 project data
        被 summary / recent / task count 各读一遍。
    """
    project_id = project["project_id"]
    archived = bool(project.get("archived_at"))
    jobs = core.list_project_jobs(project_id)
    # 单一数据源：memory view 一次 + 已经加载的 jobs，不再触发第二次 list_project_jobs。
    summary = _project_detail_summary(project, jobs)

    _render_project_detail_header(project, summary, archived=archived)

    # 一级 tab：导航状态 `active_project_tab`（与任务工作区的 section 对称）。
    # Tabs 是 **compact left-aligned** 的四个入口：宽度由内容决定、间距 28px
    # （CSS 负责），不四等分页面宽度。只有「任务」带 count——四等分宽度 + 每个
    # 都挂数字会让 tab 组本身变重，而"有多少工作"只有任务这一个 tab 在回答。
    tab_key = str(st.session_state.get("active_project_tab") or "overview")
    if tab_key not in PROJECT_TAB_LABELS:
        tab_key = "overview"
    task_count = int(summary["job_count"] or 0)
    with st.container(key="project_tabbar"):
        columns = st.columns(len(PROJECT_TABS))
        for column, (key, label) in zip(columns, PROJECT_TABS):
            suffix = f" {task_count}" if key == "tasks" and task_count else ""
            if column.button(f"{label}{suffix}", key=f"project_tab_{key}",
                             type="primary" if key == tab_key else "secondary"):
                st.session_state["active_project_tab"] = key
                st.rerun()

    # 正文包在一个显式容器里：Tabs → Content 的间距由 tabbar 自己负责（14 + 16
    # gap = 30px），正文第一个 section 不再叠加自己的 18px 上边距——否则实测会变成
    # 48px，"每个 tab 像不同产品"就是这么来的。
    with st.container(key="project_tab_content"):
        if tab_key == "overview":
            _render_project_overview_tab(project, jobs, summary)
        elif tab_key == "tasks":
            _render_project_tasks_tab(project, jobs)
        elif tab_key == "knowledge":
            _render_project_knowledge_tab(project)
        else:
            _render_project_settings_tab(project, jobs, summary)


def _project_detail_summary(project, jobs):
    """项目详情的派生数据：memory view + 已加载的 jobs（不重复扫盘）。

    `core.project_summary` 会再调用一次 `list_project_jobs`；详情页已经拿到了
    jobs，因此这里直接复用，避免 summary / recent / count 各读一遍。
    """
    view = core.project_memory_view(project)
    view["job_count"] = len(jobs)
    view["jobs"] = jobs
    return view


def _render_project_detail_header(project, summary, *, archived):
    """Header：返回 + 名称 + 状态 + 描述 + 主 CTA + secondary ⋯ 菜单。

    结构固定为两层，且**动作与身份同一行**：

        ← 返回项目
        测试1  [活动中]                        + 新建任务   ···
        项目描述（如果存在）

    约束（回归测试守住）：
      - Project Name 是主标题，状态是跟在它后面的 compact badge；
      - `+ 新建任务` 与 `···` 同属 `project_detail_actions`（flex + nowrap），
        overflow 不允许单独掉到下一行；
      - 描述为空时整行省略，不写「暂无描述」；
      - UUID / Project ID / 类型 / 创建·更新时间属于设置，这里一律不出现。
    """
    project_id = project["project_id"]
    with st.container(key="project_detail_header"):
        if st.button("← 返回项目", key="project_back_to_list"):
            _open_project_list()
            st.rerun()
        title_col, actions_col = st.columns([5, 2], gap="large")
        with title_col:
            status = ("已归档" if archived else
                      ("系统中" if core.is_system_project(project) else "活动中"))
            status_modifier = "archived" if archived else "active"
            description = str(project.get("description") or "").strip()
            # 描述为空时直接省略，不写「暂无描述」。
            desc_html = (f'<p>{escape(description)}</p>' if description else "")
            st.markdown(
                '<div class="tp-project-header-copy">'
                '<div class="tp-project-title-row">'
                f'<h1>{escape(str(project["name"]))}</h1>'
                f'<span class="tp-project-badge is-{status_modifier}">'
                f'{escape(status)}</span>'
                '</div>'
                f'{desc_html}</div>', unsafe_allow_html=True)
        with actions_col:
            with st.container(key="project_detail_actions"):
                if archived:
                    # 归档项目不允许无提示地新建任务：主 CTA 变成恢复。
                    if st.button("恢复项目", key=f"detail_restore_{project_id}",
                                 type="primary", icon=":material/unarchive:"):
                        _open_project_modal("restore", project_id)
                        st.rerun()
                else:
                    if st.button("新建任务", key=f"detail_new_task_{project_id}",
                                 type="primary", icon=":material/add:",
                                 help="在「%s」下创建翻译任务" % project["name"]):
                        _begin_new_task(project_id)
                        st.rerun()
                _project_detail_overflow_menu(project, archived=archived)
        if archived:
            # 归档说明留在 header 内部：Header 与 Tabs 之间不插任何东西，
            # 两者始终是一个整体。
            st.warning("这个项目已归档：它不在活动项目列表与新建任务的项目选择里，"
                       "但项目知识、翻译任务与归属全部保留，可随时恢复。")


def _project_detail_overflow_menu(project, *, archived):
    """Header 的 ⋯：编辑项目 / 导出项目 / 归档（或恢复）/ 删除。

    它是一个**轻量 popover menu card**（收窄宽度、压紧 padding、用 divider 分组），
    不是一个独立侧面板；菜单项是紧凑行而不是一个个大白按钮。低频管理动作收在这里，
    不与「新建任务」竞争注意力。删除是 destructive，单独一组并用红色文字区分。

    结构：项目操作 → 编辑 / 导出 / 归档（恢复）→ ──── → 删除项目。
    """
    project_id = project["project_id"]
    with st.container(key="project_detail_menu"):
        with st.popover("⋯", help="项目操作"):
            with st.container(key=f"pd_menu_body_{project_id}"):
                st.caption("项目操作")
                if st.button("编辑项目", key=f"detail_menu_edit_{project_id}",
                             icon=":material/edit:", width="stretch"):
                    _open_project_modal("edit", project_id)
                    st.rerun()
                st.download_button(
                    "导出项目", data=core.export_project_memory(project_id),
                    file_name=f"foliothread-project-{project_id}.json",
                    mime="application/json", key=f"detail_menu_export_{project_id}",
                    icon=":material/download:", width="stretch",
                    help="导出术语、风格、人工决定审计与本项目的已审校记忆；"
                         "不含任务状态、源文档或任何凭据。")
                if archived:
                    if st.button("恢复项目", key=f"detail_menu_restore_{project_id}",
                                 icon=":material/unarchive:", width="stretch"):
                        _open_project_modal("restore", project_id)
                        st.rerun()
                else:
                    if st.button("归档项目", key=f"detail_menu_archive_{project_id}",
                                 icon=":material/archive:", width="stretch"):
                        _open_project_modal("archive", project_id)
                        st.rerun()
                st.divider()
                # destructive 单独一组：删除不与其他管理动作混排。
                with st.container(key=f"pd_menu_danger_{project_id}"):
                    if st.button("删除项目", key=f"detail_menu_delete_{project_id}",
                                 icon=":material/delete:", width="stretch"):
                        _open_project_modal("delete", project_id)
                        st.rerun()


# Summary card：label / 主值 / 一句话说明。**只在 ACTIVE PROJECT 渲染**——
# 空项目根本不渲染这四张卡，所以这里没有"空值文案"分支：0 就是 0，
# 用一句短注说明它是什么，而不是把"还没有任务"这种长句子填进数字卡里。
def _summary_card(label, count, note):
    return (f'<div class="tp-stat"><div class="tp-stat-label">'
            f'{escape(label)}</div>'
            f'<div class="tp-stat-value">{int(count or 0)}</div>'
            f'<div class="tp-stat-note">{escape(note)}</div></div>')


def _render_project_overview_tab(project, jobs, summary):
    """概览有两种**明确分开**的 UI 状态，绝不共用同一套 dashboard：

      - EMPTY PROJECT（`jobs` 为空）：一个 onboarding surface ——
        "项目已经建好了 → 下一步创建任务"；
      - ACTIVE PROJECT（存在 task）：command center，信息顺序固定为
        工作概览 → 进行中的任务 → 最近任务 → 项目知识摘要。

    "空 / 非空"只用**真实数据**判断：`core.list_project_jobs()` 的长度。
    不从 summary 文案或"计数是不是 0"之类的 UI 推断出发。

    这里**不再**渲染「基本信息」表：UUID / 类型 / 创建·更新时间属于设置。
    """
    project_id = project["project_id"]

    # ---- EMPTY PROJECT ----
    # 没有 task 时不渲染 任务/术语/规则/记忆 四张 summary card：它们只会重复
    # 表达"空"。也不渲染第二块「项目知识尚未建立」——onboarding 文案已经说过
    # 创建任务后会积累知识。整页只有一个 surface。
    if not jobs:
        _render_project_onboarding(project,
                                   archived=bool(project.get("archived_at")))
        return

    # ---- ACTIVE PROJECT ----
    rows = [_task_row_view(job) for job in jobs]
    active_rows = [row for row in rows if row["active"]]
    active_rows.sort(key=lambda row: row["stamp"], reverse=True)
    done_count = len(rows) - len(active_rows)
    breakdown = " · ".join(part for part in (
        f"{len(active_rows)} 进行中" if active_rows else "",
        f"{done_count} 已完成" if done_count else "") if part) or "全部已交付"

    # ---- 1. 工作概览 ----
    # 四张卡只在 ACTIVE PROJECT 出现，且是**紧凑**的：数值 + 一句轻量说明。
    # 说明永远短（"已确认" / "尚未建立"），不把长句子塞进数字卡。
    st.markdown('<div class="tp-section-head is-inline"><strong>工作概览</strong>'
                '</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="tp-stat-grid">'
        + _summary_card("任务", len(rows), breakdown)
        + _summary_card("术语", summary["glossary_count"],
                        "已确认" if summary["glossary_count"] else "尚未建立")
        + _summary_card("规则", summary["style_rule_count"],
                        "已确认" if summary["style_rule_count"] else "尚未设置")
        + _summary_card("记忆", summary["translation_memory_count"],
                        "已审核" if summary["translation_memory_count"] else "尚无")
        + '</div>', unsafe_allow_html=True)

    # ---- 2. 进行中的任务 ----
    # 有才渲染。没有进行中的任务时**整节不渲染**：直接给「最近任务」，
    # 而不是补一个"没有进行中的任务"的大空框。
    if active_rows:
        st.markdown(
            '<div class="tp-section-head is-inline"><strong>进行中的任务</strong>'
            f'<span class="tp-count-badge">{len(active_rows)}</span></div>',
            unsafe_allow_html=True)
        with st.container(key="project_overview_active"):
            _render_task_rows(active_rows[:4], row_prefix="projrow_active",
                              card_key_prefix="project_job_open")

    # ---- 3. 最近任务（最多 5 条）----
    recent = sorted(rows, key=lambda row: row["stamp"], reverse=True)
    head_left, head_right = st.columns([5, 1])
    head_left.markdown(
        '<div class="tp-section-head is-inline"><strong>最近任务</strong>'
        f'<span>共 {len(jobs)} 个 · 显示最近 {min(len(rows), 5)} 个</span></div>',
        unsafe_allow_html=True)
    if head_right.button("查看全部 →", key=f"overview_all_tasks_{project_id}",
                         width="stretch"):
        st.session_state["active_project_tab"] = "tasks"
        st.rerun()
    with st.container(key="project_overview_recent"):
        _render_task_rows(recent[:5], row_prefix="projrow_recent",
                          card_key_prefix="project_recent_open")

    # ---- 4. 项目知识摘要（一级 tab 才有完整知识页）----
    _render_project_knowledge_summary(project, summary)


def _render_project_onboarding(project, *, archived=False):
    """EMPTY PROJECT 的**唯一** surface：项目已经建好了 → 下一步创建任务。

    它取代了此前"任务空状态 + 创建按钮 + 项目知识空状态 + 查看知识按钮"的多段
    空页面：整页只有一个 onboarding block、一个 medium 的「创建第一个任务」、
    一个次要入口「设置项目知识 →」。

    归档项目不提供新建任务入口：它的下一步是恢复，不是创建。
    """
    project_id = project["project_id"]
    if archived:
        st.markdown(
            '<div class="tp-onboarding-copy">'
            '<h2>这个项目已归档</h2>'
            '<p>归档项目不参与新建任务。恢复项目后即可继续创建翻译任务，'
            '项目知识会完整保留。</p></div>', unsafe_allow_html=True)
        return
    with st.container(key="project_onboarding"):
        st.markdown(
            '<div class="tp-onboarding-copy">'
            '<h2>开始使用这个项目</h2>'
            '<p>这个项目已经准备好了。<br>创建第一个翻译任务后，FolioThread 会'
            '逐步积累术语、规则、项目决定与审核记忆。</p></div>',
            unsafe_allow_html=True)
        # 与 Header 的「+ 新建任务」是**完全相同的 action**（`_begin_new_task`），
        # 只是视觉上是 medium 按钮——不做第二个巨大的 Primary CTA。
        if st.button("创建第一个任务",
                     key=f"project_onboarding_create_{project_id}",
                     type="primary", icon=":material/add:"):
            _begin_new_task(project_id)
            st.rerun()
        # 次要操作：把用户送去真正能积累知识的地方（复用同一个 tab 导航状态）。
        if st.button("设置项目知识 →",
                     key=f"project_onboarding_knowledge_{project_id}"):
            st.session_state["active_project_tab"] = "knowledge"
            st.rerun()


def _render_project_knowledge_summary(project, summary):
    """Overview 的紧凑项目知识区块：四类知识计数 + 一个入口。

    一级 tab 已经有完整的「项目知识」，因此这里**只做摘要**，绝不复制一个完整
    知识页。知识全为空时也只给一行 compact row（不是第二个巨大 dashed 空框）。
    没有 recent knowledge event 数据时**只展示数量**，不 mock 事件。
    """
    project_id = project["project_id"]
    counts = " · ".join(part for part in (
        f"术语 {int(summary['glossary_count'])}" if summary["glossary_count"] else "",
        f"规则 {int(summary['style_rule_count'])}" if summary["style_rule_count"] else "",
        f"决定 {int(summary['human_decision_count'])}"
        if summary["human_decision_count"] else "",
        f"记忆 {int(summary['translation_memory_count'])}"
        if summary["translation_memory_count"] else "") if part)
    st.markdown('<div class="tp-section-head is-inline"><strong>项目知识</strong>'
                '</div>', unsafe_allow_html=True)
    if not counts:
        st.markdown(
            '<div class="tp-knowledge-empty-row">'
            '<strong>项目知识尚未形成</strong>'
            '<span>随着任务确认逐步积累：锁定术语、确认风格规则、人工决定与'
            '已审校记忆。</span></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="tp-knowledge-line">{escape(counts)}</div>',
                    unsafe_allow_html=True)
        events = _project_knowledge_events(project, limit=3)
        if events:
            st.markdown(
                '<div class="tp-knowledge-events">'
                + "".join(f'<div class="tp-knowledge-event">{escape(item)}</div>'
                          for item in events)
                + '</div>', unsafe_allow_html=True)
    if st.button("查看项目知识 →", key=f"overview_knowledge_{project_id}"):
        st.session_state["active_project_tab"] = "knowledge"
        st.rerun()


def _project_knowledge_events(project, *, limit=3):
    """最近的知识提升事件（真实数据，来自项目提升记录）。

    `promotion_log` 只记录"某次提升往各类知识里加了什么"，因此这里如实描述为
    「新增术语 +N」，**不**编造具体术语条目。
    """
    labels = (("glossary", "术语"), ("style_rules", "规则"),
              ("human_decisions", "决定"), ("translation_memory", "记忆"))
    events = []
    for entry in reversed(list(project.get("promotion_log") or [])):
        added = entry.get("added") or {}
        detail = " · ".join(f"新增{name} +{int(added[key])}"
                            for key, name in labels if added.get(key))
        if not detail:
            continue
        at = _format_saved_at(entry.get("at"))
        events.append(f"{detail}（{at}）")
        if len(events) >= limit:
            break
    return events


def _recent_jobs(jobs, limit):
    def _stamp(job):
        state = job["state"] or {}
        return str(state.get("updated_at") or state.get("created_at") or "")
    return sorted(jobs, key=_stamp, reverse=True)[:limit]


def _render_project_tasks_tab(project, jobs):
    """任务：当前项目的完整任务列表。

    结构固定为「标题 → toolbar → 内容」：
      1. 标题 + count（section head）；
      2. 共享 toolbar（搜索 / 状态 / 排序）；
      3. 内容：有任务给 task list；无任务给**一个** compact empty state。

    「把任务移入本项目」是 secondary 功能，渲染成一个**默认收起**的 collapsible
    panel。此前它和空态同时铺在页面上，等于让一个二级操作与主内容抢位置。
    """
    project_id = project["project_id"]
    st.markdown('<div class="tp-section-head is-inline"><strong>任务</strong>'
                f'<span class="tp-count-badge">{len(jobs)}</span></div>',
                unsafe_allow_html=True)
    query, status_filter, order = _render_task_list_toolbar(
        key_prefix=f"project_task_{project_id}")

    rows = [_task_row_view(job) for job in jobs]
    visible = _filter_task_rows(rows, query=query,
                                status_filter=status_filter, order=order)

    if not jobs:
        # 整页唯一的主 empty state：compact，不再是一个巨大 dashed 空框。
        st.markdown(
            '<div class="tp-pd-empty">'
            '<strong>这个项目还没有翻译任务</strong>'
            '<span>新建任务时选择本项目即可归入，也可以从其他项目移入任务。</span>'
            '</div>', unsafe_allow_html=True)
    elif not visible:
        st.markdown('<div class="tp-empty">没有符合条件的任务。</div>',
                    unsafe_allow_html=True)
    else:
        st.caption(f"共 {len(jobs)} 个任务，当前显示 {len(visible)} 个。"
                   "这里只列出属于本项目的任务。")
        with st.container(key="project_task_list"):
            _render_task_rows(visible, row_prefix="projrow_task",
                              card_key_prefix="project_task_open")
    _render_project_job_mover(project)


# ================= 共享 Task Row（Inbox / Overview / Tasks 同一份投影）=================
# Project Overview、Project Tasks、未分类 Inbox 都列同一种东西：一次翻译任务。
# 它们**必须**共用同一份 view model 与 markup——否则三套几乎一样的列表会各自漂移
# （旧版就同时存在"大按钮行"和"紧凑行"两种）。这里只投影展示数据，不重新派生
# 任何状态：状态词仍然来自 canonical `_task_overview_state`。
_TASK_STATUS_OPTIONS = ("全部", "进行中", "需要处理", "可交付", "已完成")
_TASK_ORDER_OPTIONS = ("最近更新", "最早更新", "名称")
#: 未交付的生命周期都算"进行中"（可以正式交付也算：它还没被冻结）。
_TASK_DONE_LIFECYCLES = frozenset({_task_overview.DELIVERED})


def _task_bucket(lifecycle):
    """把 canonical lifecycle 收敛成列表上的几个工作桶。

    这里**不重新发明状态**：`lifecycle` 来自 `_task_overview_state`，与任务工作区、
    历史页用的是同一套权威状态；本函数只做"一眼扫读"的聚合映射。
    """
    if lifecycle == _task_overview.DELIVERED:
        return "已完成"
    if lifecycle == _task_overview.DELIVERY_READY:
        return "可交付"
    if lifecycle == _task_overview.NEEDS_ATTENTION:
        return "需要处理"
    return "进行中"


def _task_row_view(job):
    """一条任务行的展示投影（标题 / 状态 / 段落 / 文件类型 / 进度 / 时间）。"""
    state = job.get("state") or {}
    job_id = job["job_id"]
    overview = _task_overview_state(job_id, state)
    label, tone = _workspace_delivery_state(job_id, state, overview=overview)
    done, total = _project_translation_progress(state)
    total = total or _history_view.segment_count(state)
    percent = round(done * 100 / total) if total and 0 < done < total else 0
    stamp = str(state.get("updated_at") or state.get("created_at") or "")
    lifecycle = overview.get("lifecycle") or _task_overview.DRAFT
    return {
        "job_id": job_id,
        "title": _job_display_title(job),
        "filename": str(state.get("filename") or ""),
        "status": label,
        "tone": tone,
        "lifecycle": lifecycle,
        "bucket": _task_bucket(lifecycle),
        "active": lifecycle not in _TASK_DONE_LIFECYCLES,
        "total": total,
        "done": done,
        "kind": _history_view.document_kind(state),
        "percent": percent,
        "stamp": stamp,
        "updated": _history_view.format_age(stamp) or "—",
    }


def _task_row_markup(row):
    """紧凑 Task Row：标题一行、状态 · 段落 · 文件类型一行，右侧相对时间 + 箭头。

    不放大号「打开任务」按钮——整行 hover + click 就是打开动作。
    """
    meta_parts = [row["status"]]
    if row["percent"]:
        meta_parts.append(f'{row["percent"]}%')
    if row["total"]:
        meta_parts.append(f'{row["total"]} 段')
    if row["kind"]:
        meta_parts.append(row["kind"])
    return (
        f'<div class="tp-taskrow" title="{escape(row["filename"])}">'
        '<div class="tp-taskrow-head">'
        f'<div class="tp-taskrow-title">{escape(row["title"])}</div>'
        '</div>'
        '<div class="tp-taskrow-foot">'
        f'<span class="tp-taskrow-meta is-{escape(row["tone"])}">'
        f'{escape(" · ".join(meta_parts))}</span>'
        f'<span class="tp-taskrow-time">{escape(row["updated"])}</span>'
        '<span class="tp-taskrow-arrow" aria-hidden="true">→</span>'
        '</div></div>')


def _open_task(job_id):
    """打开任务（共享入口）：任务不存在时如实说明，不抛异常。"""
    state = core.load_job_state(job_id)
    if state is None:
        _push_flash("任务已不存在。", tone="warning")
    else:
        _open_job(job_id, state, "overview")
    st.rerun()


def _render_task_rows(rows, *, row_prefix, card_key_prefix, menu=None):
    """共享的 Task Row 渲染：markup + 覆盖整行的点击层（+ 可选的次级菜单）。

    `row_prefix` / `card_key_prefix` 让不同页面各自持有独立控件 key，但视觉、状态、
    进度与点击语义完全一致。
    """
    for row in rows:
        job_id = row["job_id"]
        with st.container(key=f"{row_prefix}_{job_id}"):
            st.markdown(_task_row_markup(row), unsafe_allow_html=True)
            if st.button("打开任务", key=f"{card_key_prefix}_{job_id}",
                         width="stretch"):
                _open_task(job_id)
            if menu is not None:
                menu(job_id, row["title"])


def _render_task_list_toolbar(*, key_prefix, options_status=_TASK_STATUS_OPTIONS,
                              options_order=_TASK_ORDER_OPTIONS):
    """共享的任务列表 toolbar：搜索 / 状态 / 排序（返回归一后的三个值）。

    不引入任何新的后端查询：调用方用已经加载的 jobs 过滤即可。
    """
    status_key = f"{key_prefix}_status"
    order_key = f"{key_prefix}_order"
    if st.session_state.get(status_key) not in options_status:
        st.session_state.pop(status_key, None)
    if st.session_state.get(order_key) not in options_order:
        st.session_state.pop(order_key, None)
    search_col, status_col, order_col = st.columns([5, 2, 2], gap="small")
    query = search_col.text_input(
        "搜索任务", key=f"{key_prefix}_search", label_visibility="collapsed",
        placeholder="搜索任务...", icon=":material/search:")
    status_filter = status_col.selectbox(
        "状态", options_status, key=status_key, label_visibility="collapsed")
    order = order_col.selectbox(
        "排序", options_order, key=order_key, label_visibility="collapsed")
    return query, status_filter, order


def _filter_task_rows(rows, *, query, status_filter, order):
    """共享的任务过滤 / 排序（纯内存，用的是已加载数据）。"""
    needle = str(query or "").strip().casefold()
    visible = [
        row for row in rows
        if (not needle or needle in row["title"].casefold()
            or needle in row["filename"].casefold())
        and (status_filter == "全部" or row["bucket"] == status_filter)
    ]
    if order == "名称":
        visible.sort(key=lambda row: row["title"].casefold())
    elif order == "最早更新":
        visible.sort(key=lambda row: row["stamp"])
    else:
        visible.sort(key=lambda row: row["stamp"], reverse=True)
    return visible


def _uncat_task_overflow_menu(job_id, title):
    """未分类行的 ⋯：打开任务 / 移入项目。整行点击已经能打开，菜单里也保留一份入口
    便于键盘与可发现性；「移入项目」复用既有的 `core.assign_jobs_to_project`。"""
    with st.container(key=f"inbox_menu_{job_id}"):
        with st.popover("⋯", help="任务操作"):
            st.caption(str(title)[:40] or "未分类任务")
            if st.button("打开任务", key=f"inbox_open_{job_id}",
                         icon=":material/arrow_forward:", width="stretch"):
                _open_task(job_id)
            if st.button("移入项目", key=f"inbox_move_{job_id}",
                         icon=":material/drive_file_move:", width="stretch"):
                _open_task_move_modal(job_id)
                st.rerun()


def _render_uncategorized_tasks_workspace(project):
    """「未分类任务」专属页面：Task Inbox，不是项目概览。

    结构与真实 Project Detail 完全无关：header 只给「未分类任务 + 数量 + 一句说明」，
    一个轻量 toolbar，然后是紧凑的任务行列表。不暴露 UUID / 项目 ID / 记忆 / 设置。
    """
    jobs = core.list_project_jobs(project["project_id"])
    with st.container(key="project_inbox"):
        # ---- Header ----
        with st.container(key="inbox_header"):
            # 文案是「返回项目中心」而不是「返回项目」：这个动作是 **navigation**，
            # 不是 Project Context mutation —— 它只改 `projects_route`，`active_project_id`
            # 原样保留。详见 docs/sidebar-context-vs-center.md（需求 B）。
            if st.button("← 返回项目中心", key="inbox_back_to_hub"):
                _open_project_list()
                st.rerun()
            st.markdown(
                '<div class="tp-project-header-copy">'
                '<div class="tp-inbox-title-row">'
                '<h1>未分类任务</h1>'
                f'<span class="tp-count-badge">{len(jobs)}</span>'
                '</div>'
                '<p>尚未归入任何项目的翻译任务。你可以打开任务、移入已有项目，'
                '或创建新项目。</p></div>', unsafe_allow_html=True)

        # ---- Toolbar（与 Project Tasks 共用同一套 toolbar / 过滤）----
        query, status_filter, order = _render_task_list_toolbar(
            key_prefix="uncat_task")

        rows = [_task_row_view(job) for job in jobs]
        visible = _filter_task_rows(rows, query=query,
                                    status_filter=status_filter, order=order)

        # ---- List ----
        st.markdown('<div class="tp-section-head is-inline">'
                    f'<strong>任务</strong>'
                    f'<span class="tp-count-badge">{len(jobs)}</span>'
                    '</div>', unsafe_allow_html=True)

        if not jobs:
            st.markdown(
                '<div class="tp-empty-card tp-hub-empty">'
                '<strong>还没有未分类任务</strong>'
                '<span>新建任务时选择「未分类」，任务就会出现在这里；'
                '也可以把已有任务移入某个项目。</span></div>',
                unsafe_allow_html=True)
        elif not visible:
            st.markdown('<div class="tp-empty tp-project-hub-empty">'
                        '没有符合条件的任务。</div>', unsafe_allow_html=True)
        else:
            with st.container(key="inbox_list"):
                _render_task_rows(visible, row_prefix="inbox_row",
                                  card_key_prefix="inbox_card",
                                  menu=_uncat_task_overflow_menu)


def _open_task_move_modal(job_id):
    st.session_state["project_modal"] = "move_task"
    st.session_state["task_move_job_id"] = str(job_id or "")


def _project_move_task_modal():
    """把一条未分类任务移入已有项目。复用 `core.assign_jobs_to_project`。"""
    def _body():
        job_id = str(st.session_state.get("task_move_job_id") or "")
        state = core.load_job_state(job_id)
        if state is None:
            _close_project_modals()
            _push_flash("任务已不存在，操作已取消。", tone="warning")
            st.rerun()
            return
        title = _job_display_title({"job_id": job_id, "state": state})
        st.markdown('<div class="tp-history-copy">'
                    f'<strong>{escape(title)}</strong>'
                    '<span>把任务从「未分类任务」移入所选项目。'
                    '移动只改变归属，不会修改已有译文。</span></div>',
                    unsafe_allow_html=True)
        options = core.list_active_project_options()
        labels = {p["project_id"]: p["name"] for p in options
                  if not core.is_system_project(p)}
        if not labels:
            st.info("还没有可移入的项目。先去新建一个项目，再回来移入。")
            if st.button("取消", key="project_form_cancel", width="stretch"):
                _close_project_modals()
                st.rerun()
            return
        chosen = st.selectbox(
            "目标项目", list(labels), key="task_move_target_project",
            format_func=lambda pid: labels[pid])
        confirm_col, cancel_col = st.columns([2, 1])
        if confirm_col.button("移入项目", key="task_move_confirm",
                              type="primary", width="stretch"):
            result = core.assign_jobs_to_project([job_id], chosen)
            _close_project_modals()
            st.session_state.pop("task_move_target_project", None)
            if result["moved"]:
                _push_flash(f'已把「{title}」移入「{labels[chosen]}」。')
            elif result["skipped"]:
                reason = result["skipped"][0].get("reason") if result["skipped"] else ""
                _push_flash(f'无法移入：{reason or "任务正在运行或状态不允许"}。',
                            tone="warning")
            else:
                _push_flash("没有发生移动。", tone="info")
            st.rerun()
        if cancel_col.button("取消", key="project_form_cancel", width="stretch"):
            _close_project_modals()
            st.session_state.pop("task_move_target_project", None)
            st.rerun()
    _modal_container("移入项目")(_body)()


def _render_project_knowledge_tab(project):
    """项目知识：术语 / 规则 / 决定 / 记忆 —— 四个 compact module。

    这一页此前像一篇说明文档：一整段长说明 + 四个 metric + 一整张表 + 页面底部一个
    全宽导出按钮，读起来像"关于项目知识的文档"而不是一个工作页面。现在它是一个
    结构化的页面：

        项目知识                                        [ 导出 JSON ]
        术语 1 · 规则 1 · 决定 0 · 记忆 0
        （知识全空时才给一段短总说明）

        锁定术语    1    已人工锁定的译名会注入后续翻译上下文。   [查看术语表 →]
        风格规则    1    已确认的风格与翻译规则。                 [查看规则 →]
        人工决定    0    人对术语与译文的决定记录。               [查看审计 →]
        已审核记忆  0    通过审校门槛、可被复用的译文。           [查看记忆 →]

    每个模块是 compact section（count + 一句说明 + 状态 / empty hint + 入口），
    详情默认收起。低频的整项目导出收进右上角的小按钮，不再用页面底部一个全宽
    大按钮承载。

    数据来源与业务能力**未改**：仍然读 `core.project_memory_view` / 项目记录，
    `core.export_project_memory` 也仍然是同一次导出。
    """
    project_id = project["project_id"]
    summary = core.project_memory_view(project)
    glossary_count = int(summary["glossary_count"])
    rule_count = int(summary["style_rule_count"])
    decision_count = int(summary["human_decision_count"])
    memory_count = int(summary["translation_memory_count"])
    chips = " · ".join((
        f"术语 {glossary_count}", f"规则 {rule_count}",
        f"决定 {decision_count}", f"记忆 {memory_count}"))

    with st.container(key="pd_knowledge_head"):
        # 列宽 [4, 2]：右侧要放得下「导出项目记忆（JSON）」这个内容宽度的小按钮，
        # 它不再靠"页面底部全宽"来获得空间。
        head_left, head_right = st.columns([4, 2], gap="medium")
        with head_left:
            st.markdown(
                '<div class="tp-section-head is-inline"><strong>项目知识</strong>'
                '</div>'
                f'<p class="tp-pd-summary">{escape(chips)}</p>',
                unsafe_allow_html=True)
        with head_right, st.container(key="pd_knowledge_export"):
            # 低频导出：右上角的内容宽度小按钮，不再用页面底部一个全宽大按钮承载。
            st.download_button(
                "导出项目记忆（JSON）",
                data=core.export_project_memory(project_id),
                file_name=f"foliothread-project-{project_id}.json",
                mime="application/json", key=f"project_export_{project_id}",
                width="content",
                help="导出术语、风格、人工决定审计与本项目的已审校记忆；"
                     "不含任务状态、源文档或任何凭据。")

    # 空状态时允许一段**短**总说明（分层：一句定义 + 一句来源），不重复四次。
    if not any((glossary_count, rule_count, decision_count, memory_count)):
        st.markdown(
            '<p class="tp-pd-intro">项目知识只收录人工确认后的内容：'
            '锁定术语、已确认规则、人工决定与已审核记忆。'
            '它们由任务里的确认动作逐步提升上来，模型生成的候选不会进入这里。</p>',
            unsafe_allow_html=True)

    _knowledge_module(
        key="glossary", title="锁定术语", count=glossary_count,
        note="已人工锁定的译名会注入后续翻译上下文。",
        empty_hint="还没有锁定术语：在任务里锁定译名后提升到本项目。",
        entry_label="查看术语表 →", opened_label="收起术语表",
        body=lambda: _knowledge_glossary_body(project))
    _knowledge_module(
        key="rules", title="风格规则", count=rule_count,
        note="已确认的风格与翻译规则，随任务一起注入。",
        empty_hint="还没有确认的风格规则：在任务里确认规则后提升到本项目。",
        entry_label="查看规则 →", opened_label="收起规则",
        body=lambda: _knowledge_rules_body(project))
    _knowledge_module(
        key="decisions", title="人工决定", count=decision_count,
        note="人对术语与译文的决定记录，可追溯。",
        empty_hint="还没有人工决定记录：确认术语或译文后会留下审计记录。",
        entry_label="查看审计 →", opened_label="收起审计",
        body=lambda: _knowledge_decisions_body(project))
    _knowledge_module(
        key="memory", title="已审核记忆", count=memory_count,
        note="通过审校门槛、可在本项目复用的译文。",
        empty_hint="本项目还没有已审校记忆：通过独立审校的段落会自动入库。",
        entry_label="查看记忆 →", opened_label="收起记忆",
        body=lambda: _knowledge_memory_body(project, summary))

    # 待处理的导入冲突是**待决动作**，不是知识条目：有才渲染，放在模块之后。
    _render_project_conflicts(project)


def _render_project_settings_tab(project, jobs, summary=None):
    """设置：项目资料 / 状态 / 高级信息 / 危险操作 —— 四个明确分区。

    原 Overview 的「基本信息」表（项目 ID / 类型 / 创建时间 / 更新时间）迁移到
    这里——UUID 可以存在于设置，但不应出现在普通概览里。

    这一版做两件事，都是"去掉重复"而不是"加功能"：

      - **动作去重**：此前「编辑名称与描述」与「重命名」并排成两个大按钮，两者
        高度重叠。现在只剩一个动作「编辑项目资料」，名称与描述在同一个编辑流程里
        改；「重命名」这个入口在设置页不再出现（它本来就只是编辑流程的子集）。
      - **分组归位**：归档此前单独占一张卡，但它和「状态」说的是同一件事。
        现在并入「状态」；设置页因此从五段收敛成四段。

    动作分级：Header 的「+ 新建任务」是页面级 Primary；设置里的动作全部是
    management 动作，一律 secondary / tertiary，危险动作单独一组。
    """
    project_id = project["project_id"]
    is_system = core.is_system_project(project)
    archived = bool(project.get("archived_at"))
    summary = summary if summary is not None else _project_detail_summary(project, jobs)

    if is_system:
        with st.container(key="pd_group_system"):
            st.markdown('<div class="tp-group-head"><strong>系统工作区</strong>'
                        '<span>不可重命名 / 归档 / 删除</span></div>',
                        unsafe_allow_html=True)
            st.caption(
                f"「{core.SYSTEM_PROJECT_NAME}」承载所有没有归属的翻译任务（包括"
                "迁移前创建的任务）。它拥有真实持久化 ID 与独立的项目知识空间，"
                "因此可以正常积累术语与已审校记忆；但重命名、归档或删除会让这些"
                "任务失去容器，所以这些操作一律不提供。")
            st.markdown(
                '<div class="tp-pd-row"><span class="tp-detail-label">项目 ID</span>'
                f'<span class="tp-detail-value"><code>{escape(project_id)}</code>'
                '</span></div>'
                '<div class="tp-pd-row"><span class="tp-detail-label">当前任务</span>'
                f'<span class="tp-detail-value">{len(jobs)} 个</span></div>',
                unsafe_allow_html=True)
            if st.button("前往「任务」标签", key=f"settings_tasks_{project_id}",
                         width="content"):
                st.session_state["active_project_tab"] = "tasks"
                st.rerun()
        return

    # ---- 1. 项目资料（名称 + 描述 + 唯一的编辑入口）----
    description = str(project.get("description") or "").strip()
    with st.container(key="pd_group_profile"):
        st.markdown('<div class="tp-group-head"><strong>项目资料</strong>'
                    '<span>名称与描述</span></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="tp-pd-row"><span class="tp-detail-label">项目名称</span>'
            f'<span class="tp-detail-value">{escape(str(project["name"]))}</span></div>'
            '<div class="tp-pd-row"><span class="tp-detail-label">项目描述</span>'
            f'<span class="tp-detail-value">'
            + (escape(description) if description
               else '<span class="tp-detail-muted">添加项目描述</span>')
            + '</span></div>', unsafe_allow_html=True)
        # 一个动作：名称与描述在同一个编辑流程里改。不再并排第二个「重命名」。
        if st.button("编辑项目资料", key=f"settings_edit_{project_id}",
                     icon=":material/edit:", width="content"):
            _open_project_modal("edit", project_id)
            st.rerun()

    # ---- 2. 状态（活动 / 归档 + 归档或恢复，收在同一组）----
    with st.container(key="pd_group_status"):
        st.markdown('<div class="tp-group-head"><strong>状态</strong>'
                    '<span>可恢复 · 不删除任何东西</span></div>',
                    unsafe_allow_html=True)
        status_label = "已归档" if archived else "活动中"
        status_note = (f"归档于 {_format_saved_at(project.get('archived_at'))}"
                       if archived else "正常参与新建任务的项目选择")
        st.markdown(
            '<div class="tp-pd-row"><span class="tp-detail-label">项目状态</span>'
            f'<span class="tp-detail-value">{escape(status_label)}'
            f'<span class="tp-detail-muted"> · {escape(status_note)}</span>'
            '</span></div>', unsafe_allow_html=True)
        if archived:
            st.caption("归档不影响项目知识、翻译任务与归属，只是不再出现在活动项目"
                       "列表与新建任务的选择里。")
            if st.button("恢复为活动项目", key=f"settings_restore_{project_id}",
                         icon=":material/unarchive:", width="content"):
                _open_project_modal("restore", project_id)
                st.rerun()
        else:
            st.caption("归档后项目从活动列表移出，不再出现在新建任务的选择里；"
                       "项目知识、任务与归属全部保留，可随时恢复。")
            if st.button("归档项目", key=f"settings_archive_{project_id}",
                         icon=":material/archive:", width="content"):
                _open_project_modal("archive", project_id)
                st.rerun()

    # ---- 3. 高级信息（身份与时间戳：只在设置里出现）----
    with st.container(key="pd_group_advanced"):
        st.markdown('<div class="tp-group-head"><strong>高级信息</strong>'
                    '<span>身份与时间戳</span></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="tp-pd-row"><span class="tp-detail-label">Project ID</span>'
            f'<span class="tp-detail-value"><code>{escape(project_id)}</code></span>'
            '</div>'
            '<div class="tp-pd-row"><span class="tp-detail-label">UUID</span>'
            '<span class="tp-detail-value">不可变标识'
            '<span class="tp-detail-muted"> · 重命名不会改变它</span></span></div>'
            '<div class="tp-pd-row"><span class="tp-detail-label">创建时间</span>'
            f'<span class="tp-detail-value">'
            f'{escape(_format_saved_at(project.get("created_at")))}</span></div>'
            '<div class="tp-pd-row"><span class="tp-detail-label">最近更新</span>'
            f'<span class="tp-detail-value">'
            f'{escape(_format_saved_at(project.get("updated_at")))}</span></div>',
            unsafe_allow_html=True)
        st.caption("任务归属、路由与项目知识都以 Project ID 为准；重命名只改显示名称。")

    # ---- 4. 危险操作（单独一组，视觉上明确分开）----
    with st.container(key="pd_group_danger"):
        st.markdown('<div class="tp-group-head"><strong>危险操作</strong>'
                    '<span>永久删除 · 不可撤销</span></div>',
                    unsafe_allow_html=True)
        if jobs:
            st.warning(f"这个项目下还有 {len(jobs)} 个翻译任务。"
                       "删除项目需要先移动或删除这些任务——"
                       "否则任务的归属会指向一个不存在的项目。")
            if st.button("前往「任务」标签处理", key=f"settings_goto_tasks_{project_id}",
                         width="content"):
                st.session_state["active_project_tab"] = "tasks"
                st.rerun()
        else:
            st.caption("这个项目没有任务，可以删除。删除前会自动写一份可恢复备份"
                       "（含项目知识与已审校记忆），但删除本身不可撤销。")
        with st.container(key="pd_danger_action"):
            if st.button("删除项目", key=f"settings_delete_{project_id}",
                         icon=":material/delete:", width="content",
                         disabled=bool(jobs)):
                _open_project_modal("delete", project_id)
                st.rerun()


def _render_projects_surface():
    """`/projects` 与 `/projects/:projectId` 的唯一入口。

    IA 约定（回归测试守住）：

      - 首屏是**项目 hub**：page header +「新建项目」menu + 统一 toolbar
        （搜索 / 状态 / 排序 / Grid-List）+ 未分类任务轻量入口 +「我的项目」；
      - 项目卡片整体可点进入 `/projects/:projectId`，右侧 overflow menu 只提供
        secondary actions（重命名 / 编辑 / 归档 / 导出 / 删除）；
      - 真实项目详情四个一级 tab：概览 / 任务 / 项目知识 / 设置；
      - **系统工作区「未分类」不是项目**：它的路由落点不是 Project Detail，而是
        专门的 Task Inbox（`_render_uncategorized_tasks_workspace`）；
      - 归档项目从默认活动列表移出，统一从状态筛选进入并可恢复；
      - 新建与导入都是 modal，不在首屏展开表单。
    """
    active_project_id = str(st.session_state.get("active_project_id") or "")
    # 路由说"在看某个项目"但上下文已经空了（项目刚被删除 / 冷启动）：归一到列表，
    # 否则 `projects_route` 会停在 `detail` 上，管理页的 active state 就丢了。
    if _projects_route() == "detail" and not active_project_id:
        st.session_state["projects_route"] = "list"
    if active_project_id and _projects_route() == "detail":
        project = core.load_project(active_project_id)
        if project is None and core.is_system_project_id(active_project_id):
            project = core.system_project_view()
        if project is None:
            # 项目在别处被删除：清掉失效导航状态，如实说明并回到列表。
            st.session_state.pop("active_project_id", None)
            st.session_state["projects_route"] = "list"
            _route_params(project=None, view="projects")
            _push_flash(f"项目 {active_project_id} 已不存在，已回到项目列表。",
                        tone="warning")
        else:
            # 系统工作区「未分类」不是项目：它走专门的 Task Inbox，
            # 而不是 generic Project Detail（后者会把它重新渲染成一个正式项目）。
            if core.is_system_project(project):
                _render_uncategorized_tasks_workspace(project)
            else:
                _render_project_detail(project)
            return

    _render_project_list()


def _project_view_mode():
    """Grid / List 视图状态（显式落进 session_state，默认 Grid：项目少时它扫读最快）。"""
    mode = str(st.session_state.get("project_view_mode") or "")
    if mode not in _PROJECT_VIEW_MODES:
        mode = "grid"
        st.session_state["project_view_mode"] = mode
    return mode


def _normalize_project_toolbar_state():
    """会话里可能残留上一版选项（例如旧的「活动项目」）：先归一再建控件。"""
    if st.session_state.get("project_status_filter") not in _PROJECT_STATUS_OPTIONS:
        st.session_state.pop("project_status_filter", None)
    if st.session_state.get("project_order") not in _PROJECT_ORDER_OPTIONS:
        st.session_state.pop("project_order", None)


def _render_project_toolbar():
    """统一 Project Toolbar。返回 (query, status_filter, order)。

    它是**一个**工具栏，不是三个散落的表单控件：search 是主控件，状态与排序是
    紧凑的具名下拉，视图切换是同一行右侧的图标按钮。
    """
    _normalize_project_toolbar_state()
    with st.container(key="project_toolbar"):
        search_col, status_col, order_col, view_col = st.columns(
            [5.0, 1.8, 2.0, 1.3], gap="small")
        query = search_col.text_input(
            "搜索项目", key="project_search", label_visibility="collapsed",
            placeholder="搜索项目...", icon=":material/search:")
        status_filter = status_col.selectbox(
            "状态", _PROJECT_STATUS_OPTIONS, key="project_status_filter",
            index=_PROJECT_STATUS_OPTIONS.index("活动中"),
            label_visibility="collapsed")
        order = order_col.selectbox(
            "排序", _PROJECT_ORDER_OPTIONS, key="project_order",
            label_visibility="collapsed")
        with view_col.container(key="project_view_toggle"):
            grid_col, list_col = st.columns(2, gap="small")
            mode = _project_view_mode()
            if grid_col.button("▦", key="project_view_grid", help="网格视图",
                               type="primary" if mode == "grid" else "secondary",
                               width="stretch"):
                st.session_state["project_view_mode"] = "grid"
                st.rerun()
            if list_col.button("☰", key="project_view_list", help="列表视图",
                               type="primary" if mode == "list" else "secondary",
                               width="stretch"):
                st.session_state["project_view_mode"] = "list"
                st.rerun()
    return query, status_filter, order


def _render_project_cards(visible, records, *, mode):
    """Grid 是 2 列（宽屏才考虑 3 列）；List 是单列紧凑行。两者共用同一份卡数据。"""
    if mode == "list":
        with st.container(key="project_list"):
            for view in visible:
                _project_list_row(
                    view, records[view["project_id"]],
                    archived=(view.get("status") == "archived"))
        return
    with st.container(key="project_grid"):
        for start in range(0, len(visible), 2):
            row = visible[start:start + 2]
            columns = st.columns(2, gap="medium")
            for column, view in zip(columns, row):
                with column:
                    _project_card(
                        view, records[view["project_id"]],
                        archived=(view.get("status") == "archived"))


def _render_project_list():
    """项目 hub 首屏：page header / toolbar / 未分类入口 / 我的项目。"""
    sections, views, records = _load_project_views()
    system_views = [v for v in views if v.get("is_system")]
    active_views = [v for v in views
                    if not v.get("is_system") and v.get("status") != "archived"]
    archived_views = [v for v in views if v.get("status") == "archived"]
    if system_views:
        system_view = system_views[0]
        system_project = records[system_view["project_id"]]
    else:  # pragma: no cover - 磁盘上还没有记录时的只读视图
        system_project = core.system_project_view()
        system_view = core.project_summary(system_project)
    uncategorized_count = int(system_view.get("job_count") or 0)

    with st.container(key="project_hub"):
        # ---- Page header：标题与「新建项目」属于同一个 page container ----
        with st.container(key="project_header"):
            head_left, head_right = st.columns([5, 2], gap="large")
            head_left.markdown(
                '<div class="tp-project-header-copy"><h1>项目</h1>'
                '<p>管理翻译任务、项目知识与语言资产</p></div>',
                unsafe_allow_html=True)
            with head_right.container(key="project_header_action"):
                # Compact CTA：它是 page header 的动作，不是整页最重的元素。
                with st.popover("新建项目", type="primary",
                                icon=":material/add:", width="content"):
                    if st.button("新建空白项目", key="project_new_blank",
                                 icon=":material/create_new_folder:",
                                 width="stretch"):
                        _clear_project_form()
                        _open_project_modal("new")
                        st.rerun()
                    if st.button("导入项目", key="project_new_import",
                                 icon=":material/upload_file:",
                                 width="stretch",
                                 help="从 FolioThread 项目备份（JSON）导入"):
                        _open_project_modal("import")
                        st.rerun()

        # ---- Unified toolbar ----
        query, status_filter, order = _render_project_toolbar()

        if status_filter == "已归档":
            candidate_views = archived_views
        elif status_filter == "全部":
            candidate_views = active_views + archived_views
        else:
            candidate_views = active_views
        visible = _sort_project_views(
            [v for v in candidate_views if _project_matches(v, query)], order)

        # ---- 系统任务区：未分类任务不是项目，只是没有归属的任务收纳区 ----
        # 它必须和「我的项目」在**结构上**分开（各自一个 section），只在视觉上
        # 靠虚线 / sunken 面降级是不够的：区块标题才说明"这里不是你的项目列表"。
        _uncategorized_strip(system_view, system_project)

        # ---- My projects ----
        filter_note = ""
        if str(query or "").strip():
            filter_note = f"匹配 {len(visible)} 个"
        elif status_filter == "已归档":
            filter_note = f"{len(archived_views)} 个已归档"
        elif status_filter == "全部":
            filter_note = f"共 {len(active_views) + len(archived_views)} 个"
        # badge 与当前筛选一致：筛"已归档"时它必须说归档的数量，否则读者会以为
        # 列表和数字对不上。
        section_count = {"已归档": len(archived_views),
                         "全部": len(active_views) + len(archived_views)}.get(
                             status_filter, len(active_views))
        with st.container(key="project_section"):
            st.markdown(
                '<div class="tp-section-head is-inline"><strong>我的项目</strong>'
                f'<span class="tp-count-badge">{section_count}</span>'
                + (f'<span class="tp-section-note">{escape(filter_note)}</span>'
                   if filter_note else "")
                + '</div>', unsafe_allow_html=True)
            if not active_views and not archived_views:
                _empty_projects_state()
            elif not visible:
                hint = ("没有符合条件的项目。"
                        if active_views or archived_views else "")
                if not active_views and archived_views \
                        and status_filter == "活动中":
                    hint = ("没有活动项目。已归档的项目可以从上方「状态」"
                            "筛选里查看并恢复。")
                st.markdown(f'<div class="tp-empty tp-project-hub-empty">'
                            f'{hint}</div>', unsafe_allow_html=True)
            else:
                _render_project_cards(visible, records,
                                      mode=_project_view_mode())


# ================= Project 生命周期弹窗 =================
# 一次只渲染一个 modal，由 `_open_project_modal(kind, project_id)` 打开。


def _render_project_modal():
    """按当前 modal 类型渲染对应弹窗；没有打开的 modal 时什么都不做。"""
    kind = _consume_project_modal("new", "import", "rename", "edit", "archive",
                                  "restore", "delete", "move_task")
    if not kind:
        return
    if kind == "move_task":
        _project_move_task_modal()
        return
    target = _project_modal_record() if kind not in ("new", "import") else None
    if kind not in ("new", "import") and (target is None or not str(
            st.session_state.get("project_modal_target") or "").strip()):
        # 项目在弹窗打开后被删除：如实说明并关闭，而不是抛异常。
        _close_project_modals()
        _push_flash("这个项目已不存在，操作已取消。", tone="warning")
        return
    if kind == "new":
        _project_new_modal()
    elif kind == "import":
        _project_import_modal()
    elif kind == "rename":
        _project_rename_modal(target)
    elif kind == "edit":
        _project_edit_modal(target)
    elif kind == "archive":
        _project_archive_modal(target, archived=True)
    elif kind == "restore":
        _project_archive_modal(target, archived=False)
    else:
        _project_delete_modal(target)


def _project_new_modal():
    """新建项目：第一版至少支持 name 与 description。"""
    def _body():
        st.caption("项目是任务、术语、风格规则、人工决定与已审校记忆的长期容器。"
                   "新建项目不会创建任何翻译任务。")
        name = st.text_input("项目名称", key="project_form_name",
                             placeholder=_PROJECT_NAME_PLACEHOLDER)
        description = st.text_area(
            "项目描述（可选）", key="project_form_description", height=90,
            placeholder="一句话说明这个项目覆盖什么文档、面向什么读者。")
        create_col, cancel_col = st.columns([2, 1])
        if create_col.button("新建项目", key="project_form_create",
                             type="primary", width="stretch"):
            try:
                if error := _reserved_project_name_error(name):
                    raise ValueError(error)
                created = core.create_project(name, description=description)
            except ValueError as exc:
                # 校验失败时**不** rerun：在 dialog 里 rerun 会关掉弹窗并丢掉
                # 用户已经填好的内容，错误提示也来不及显示。
                st.session_state["project_form_error"] = str(exc)
            else:
                _clear_project_form()
                _close_project_modals()
                _apply_project_context(created["project_id"])
                if _in_new_task_flow():
                    # 在「新建任务」流程里建项目：它成为上下文，但用户留在流程里。
                    _push_flash(f"已新建项目「{created['name']}」，"
                                "已作为本次任务的上下文。")
                else:
                    _push_flash(f"已新建项目「{created['name']}」，已进入项目详情。")
                    st.session_state.update(app_view="projects",
                                            workspace_mode=False,
                                            projects_route="detail")
                    st.session_state["active_project_tab"] = "overview"
                st.rerun()
        if cancel_col.button("取消", key="project_form_cancel", width="stretch"):
            _clear_project_form()
            _close_project_modals()
            st.rerun()
        _render_project_form_error()
    _modal_container("新建项目")(_body)()


def _project_import_modal():
    """导入项目：与新建项目平级的 modal，而不是页面底部的展开表单。

    保留既有全部业务能力：JSON 文件、名称覆盖、描述、只增不改的冲突记录。
    """
    def _body():
        _render_project_importer(key_prefix="project_import_modal",
                                 heading="")
    _modal_container("导入项目", width="large")(_body)()


def _project_rename_modal(project):
    """重命名：**只改 display name，不改 project_id**，所有引用不受影响。"""
    def _body():
        st.caption("重命名只改变显示名称。项目 ID 是不可变 UUID，任务归属、路由与"
                   "项目记忆都不受影响。")
        name = st.text_input("新的项目名称", key="project_form_name",
                             value=str(project["name"]))
        save_col, cancel_col = st.columns([2, 1])
        if save_col.button("保存名称", key="project_form_save", type="primary",
                           width="stretch"):
            try:
                updated = core.rename_project(project["project_id"], name)
            except ValueError as exc:
                st.session_state["project_form_error"] = str(exc)
            else:
                _clear_project_form()
                _close_project_modals()
                _refresh_projects_after()
                _push_flash(f"已重命名为「{updated['name']}」；项目 ID 未变。")
                st.rerun()
        if cancel_col.button("取消", key="project_form_cancel", width="stretch"):
            _clear_project_form()
            _close_project_modals()
            st.rerun()
        _render_project_form_error()
    _modal_container("重命名项目")(_body)()


def _project_edit_modal(project):
    """编辑：名称 + 描述。与重命名共用同一层校验，不重复实现。"""
    def _body():
        name = st.text_input("项目名称", key="project_form_name",
                             value=str(project["name"]))
        description = st.text_area("项目描述", key="project_form_description",
                                   value=str(project.get("description") or ""),
                                   height=110)
        save_col, cancel_col = st.columns([2, 1])
        if save_col.button("保存", key="project_form_save", type="primary",
                           width="stretch"):
            try:
                updated = core.update_project(project["project_id"], name=name,
                                              description=description)
            except ValueError as exc:
                st.session_state["project_form_error"] = str(exc)
            else:
                _clear_project_form()
                _close_project_modals()
                _refresh_projects_after()
                _push_flash(f"已保存项目「{updated['name']}」的基本信息。")
                st.rerun()
        if cancel_col.button("取消", key="project_form_cancel", width="stretch"):
            _clear_project_form()
            _close_project_modals()
            st.rerun()
        _render_project_form_error()
    _modal_container("编辑项目")(_body)()


def _project_archive_modal(project, *, archived):
    """归档（可恢复）/ 恢复。都不删除任务，也不删除项目记忆。"""
    verb = "归档" if archived else "恢复"
    def _body():
        if archived:
            st.markdown(
                f'<div class="tp-history-copy"><strong>{escape(project["name"])}'
                '</strong><span>归档后：从活动项目列表移出，不再出现在新建任务的'
                '项目选择里。</span><span>不会被删除：项目记忆、术语、风格规则与'
                '任务归属全部保留，随时可以恢复。</span></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="tp-history-copy"><strong>{escape(project["name"])}'
                '</strong><span>恢复后：重新出现在活动项目列表与新建任务的项目'
                '选择里。</span></div>',
                unsafe_allow_html=True)
        confirm_col, cancel_col = st.columns([2, 1])
        if confirm_col.button(f"确认{verb}", key="project_form_confirm",
                              type="primary", width="stretch"):
            try:
                core.archive_project(project["project_id"], archived)
            except ValueError as exc:
                _close_project_modals()
                _push_flash(f"{verb}失败：{exc}", tone="error")
                st.rerun()
            else:
                _close_project_modals()
                _refresh_projects_after()
                if archived and str(st.session_state.get("active_project_id")) \
                        == project["project_id"]:
                    st.session_state["active_project_tab"] = "settings"
                _push_flash(f"已{verb}项目「{project['name']}」。"
                            + ("项目记忆与任务归属都保留，可随时恢复。"
                               if archived else ""))
                st.rerun()
        if cancel_col.button("取消", key="project_form_cancel", width="stretch"):
            _close_project_modals()
            st.rerun()
    _modal_container(f"{verb}项目")(_body)()


def _project_delete_modal(project):
    """永久删除：仍含任务时**拒绝**并指引先移动/删除任务；无任务时二次确认。"""
    def _body():
        jobs = core.list_project_jobs(project["project_id"])
        st.markdown(
            f'<div class="tp-history-copy"><strong>{escape(project["name"])}'
            '</strong><span>项目 ID：'
            f'{escape(project["project_id"])}</span>'
            f'<span>翻译任务 {len(jobs)} 个 · 锁定术语 '
            f'{len(project.get("glossary") or [])} 条 · 已审校记忆 '
            f'{len(core.load_tm(project["project_id"]))} 条</span></div>',
            unsafe_allow_html=True)
        if jobs:
            st.error(f"这个项目下还有 {len(jobs)} 个翻译任务，不能删除。"
                     "请先把这些任务移到其它项目，或删除任务，然后再删除项目。")
            if st.button("前往「任务」标签处理", key="project_form_goto_tasks",
                         width="stretch"):
                _close_project_modals()
                st.session_state["active_project_tab"] = "tasks"
                st.rerun()
            if st.button("取消", key="project_form_cancel", width="stretch"):
                _close_project_modals()
                st.rerun()
            return
        st.warning("删除是永久操作：项目记忆、术语、风格规则与该项目已审校记忆都会"
                   "从工作区移除。删除前会自动写一份可恢复备份。")
        typed = st.text_input(
            f"输入项目名称「{project['name']}」以确认",
            key="project_form_confirm_name", placeholder=project["name"])
        confirm_col, cancel_col = st.columns([2, 1])
        if confirm_col.button("永久删除", key="project_form_confirm",
                              type="primary",
                              disabled=str(typed or "").strip() != project["name"],
                              width="stretch"):
            try:
                result = core.delete_project(project["project_id"],
                                             confirm_name=typed)
            except ValueError as exc:
                st.session_state["project_form_error"] = str(exc)
            else:
                _clear_project_form()
                _close_project_modals()
                if str(st.session_state.get("active_project_id")) \
                        == project["project_id"]:
                    st.session_state.pop("active_project_id", None)
                    _route_params(project=None, view="projects")
                _refresh_projects_after()
                _push_flash(f"已永久删除项目「{result['name']}」；"
                            f"备份保存在 {result['backup'].name}。")
                st.rerun()
        if cancel_col.button("取消", key="project_form_cancel", width="stretch"):
            _clear_project_form()
            _close_project_modals()
            st.rerun()
    _modal_container("删除项目（永久）")(_body)()


def _render_project_form_error():
    """渲染弹窗内的校验错误。

    必须放在按钮**之后**：dialog 重跑时 body 先执行、按钮回调随后触发，因此
    "先渲染再处理"会让校验失败晚一轮才可见。
    """
    if error := st.session_state.get("project_form_error"):
        st.error(error)


def _clear_project_form():
    for key in ("project_form_name", "project_form_description",
                "project_form_error", "project_form_confirm_name"):
        st.session_state.pop(key, None)


# ================= 新建任务的项目上下文（只读）=================
# 语义：Workspace ▸ Project ▸ Task ▸ Run。Project 是可复用的长期容器，Task 是
# 一次执行，任务的归属就是**当前 Project Context**。
#
# Project Context 只有一个来源：侧栏的 switcher。因此新建任务页不自己维护一个
# 并列的项目下拉框——两个并列的选择器迟早会给出互相矛盾的答案（侧栏说 A、
# 任务说 B）。这里只**显示**上下文，改归属只有一条路：打开那一个 switcher。
#
# 没有上下文的任务属于系统工作区「未分类任务」：它是真实容器，有记忆命名空间，
# 只是不注入任何项目上下文。

# 项目名不能占用系统工作区的显示名，否则列表里的「未分类」会同时指两个东西。
_RESERVED_PROJECT_NAMES = ("未分类", "未分类任务")


def _reserved_project_name_error(name):
    cleaned = str(name or "").strip()
    if cleaned in _RESERVED_PROJECT_NAMES:
        return (f"项目名称不能是「{'」或「'.join(_RESERVED_PROJECT_NAMES)}」"
                "——那是系统工作区的保留名。")
    return ""


def _render_project_importer(*, key_prefix="project_import", heading="导入项目"):
    """导入项目备份（只增不改）。

    advanced / migration 动作，不是项目页首屏内容：入口在「新建项目」菜单里，
    界面是一个独立 modal。`key_prefix` 让同一页面上可能出现的多个入口各自持有
    独立控件，不会撞 key。业务能力（JSON / 名称覆盖 / 描述 / 冲突记录）不变。
    """
    if heading:
        st.markdown(f'<div class="tp-field-head"><strong>{heading}</strong>'
                    '<span>从项目备份导入 · 只增不改，冲突不会被静默覆盖</span>'
                    '</div>', unsafe_allow_html=True)
    upload = st.file_uploader(
        "拖入 FolioThread 项目文件（.json）", type=["json"],
        key=f"{key_prefix}_file",
        help="由「导出项目」生成的 JSON。拖入或点击选择文件；"
             "同名项目会被并入，而不是新建重复项目。")
    rename = st.text_input(
        "项目名称（可选）", key=f"{key_prefix}_name",
        placeholder="留空则自动使用文件中的项目名称")
    description = st.text_input(
        "项目描述（可选）", key=f"{key_prefix}_description",
        placeholder="一句话说明这个项目的范围")
    if upload is None:
        st.caption("导入只增不改：与本地不一致的译名会被记录成待处理冲突，"
                   "而不是静默覆盖。")
        return
    if st.button("导入", key=f"{key_prefix}_go", width="stretch", type="primary"):
        try:
            project, report = core.import_project_memory(
                upload.getvalue(), name=str(rename or "").strip() or None,
                description=str(description or "").strip())
        except (ValueError, OSError) as exc:
            _push_flash(f"导入失败：{exc}", tone="error")
            st.error(f"导入失败：{exc}")
            return
        summary = (f"已导入到「{project['name']}」：术语 +{report['glossary_added']} · "
                   f"风格 +{report['style_added']} · "
                   f"人工决定 +{report['decisions_added']} · "
                   f"已审校记忆 +{report.get('tm_added', 0)}")
        _close_project_modals()
        _refresh_projects_after()
        _push_flash(summary)
        if report["glossary_conflicts"]:
            with st.expander(f"术语冲突 {len(report['glossary_conflicts'])} 条"
                             f"（保留本地译名）", expanded=False):
                for item in report["glossary_conflicts"]:
                    st.caption(f"{item['source']}：本地「{item['local']}」"
                               f" vs 导入「{item['incoming']}」")
        if report.get("tm_conflicts_count"):
            st.caption(f"有 {report['tm_conflicts_count']} 条已审校记忆与本地不同，"
                       "已保留本地译法。")
        _open_project(project["project_id"])
        st.rerun()


def _render_task_project_context():
    """新建任务里的「项目上下文」：**只读**地显示当前上下文。

    它不是一个 Project Selector：归属只有一个来源（侧栏「项目」分组里的上下文
    selector），这里只回答"这个任务会落在哪个项目里"，并把改归属的入口指回那一个
    selector。

    两种状态是**同一个 context block**，不是两张卡：

        已选项目：项目名 +「继承项目术语、翻译记忆和规则」+ [更改]
        未选项目：未分类任务（Inbox）+「任务将保存到系统工作区…」+ [选择项目]

    关键约束（回归测试守住）：未分类态**不得**使用 Project 的语法——没有卡片阴影、
    没有"项目"这个称谓、没有 overflow menu，且英文 `Inbox` 只能作为状态行右侧的
    低对比小标签出现，不能变成主视觉标题。
    """
    context = _project_context()
    with st.container(key="task_project_context"):
        st.markdown('<div class="tp-context-head">项目上下文</div>',
                    unsafe_allow_html=True)
        if context["selected"]:
            st.markdown(
                '<div class="tp-project-context is-selected">'
                '<span class="material-symbols-rounded" aria-hidden="true">'
                'folder_open</span>'
                '<div class="tp-context-copy">'
                '<div class="tp-context-status">'
                f'<strong>{escape(context["name"])}</strong></div>'
                '<span class="tp-project-context-note">'
                '继承项目术语、翻译记忆和规则</span></div></div>',
                unsafe_allow_html=True)
            if st.button("更改", key="task_project_change",
                         icon=":material/swap_horiz:", width="content",
                         help="打开侧栏「项目」分组里的同一个上下文选择器"):
                _toggle_project_switcher("task")
                st.rerun()
            if _project_switcher_is_open("task"):
                _render_project_switcher_body("task")
        else:
            st.markdown(
                '<div class="tp-project-context is-empty">'
                '<span class="material-symbols-rounded" aria-hidden="true">'
                'inbox</span>'
                '<div class="tp-context-copy">'
                '<div class="tp-context-status">'
                '<strong>未分类任务</strong>'
                '<span class="tp-context-tag">Inbox</span></div>'
                '<span class="tp-project-context-note">'
                '任务将保存到系统工作区，不继承项目术语、翻译记忆与规则'
                '</span></div></div>',
                unsafe_allow_html=True)
            if st.button("选择项目", key="task_project_pick",
                         icon=":material/folder_open:", width="content",
                         help="在侧栏「项目」分组里为本次任务选择上下文"):
                _toggle_project_switcher("task")
                st.rerun()
            if _project_switcher_is_open("task"):
                _render_project_switcher_body("task")


def _current_project_context():
    """侧栏上下文的**原始**来源（可能是系统工作区），按优先级：

    1. **正在做的任务**（`workspace_mode`）：任务所属的项目——层级里 Task 在
       Project 之下，打开一个任务就等于进入它所属的项目；
    2. **正在看的项目**（`active_project_id`，即停在 `/projects/:projectId`），
       以及新建任务流程里记住的上下文；
    3. 否则是系统工作区「未分类」。

    这是 context switcher，不是 project manager：它只回答"我现在在哪个项目里
    工作"。顺序刻意让"当前任务"压过"上次看过的项目"——否则侧栏会说项目 A，
    而屏幕上做的事属于项目 B。
    """
    if st.session_state.get("workspace_mode"):
        active_job_id = str(st.session_state.get("active_job_id") or "")
        if active_job_id:
            state = core.load_job_state(active_job_id)
            if state is not None:
                project = core.project_for_job(active_job_id, state)
                if project is not None:
                    return project
    viewing = str(st.session_state.get("active_project_id") or "")
    if viewing:
        project = core.load_project(viewing)
        if project is None and core.is_system_project_id(viewing):
            project = core.system_project_view()
        if project is not None:
            return project
    active_job_id = str(st.session_state.get("active_job_id") or "")
    if active_job_id:
        state = core.load_job_state(active_job_id)
        if state is not None:
            project = core.project_for_job(active_job_id, state)
            if project is not None:
                return project
    return core.system_project_view()


def _project_context():
    """Project Context 的**唯一读口**：全应用都从这里取，不各自拼一份。

    返回 `{project, project_id, name, selected, is_system}`：
    `selected=False` 表示当前没有进入任何真实项目（= 系统工作区「未分类」）。
    """
    project = _current_project_context() or core.system_project_view()
    is_system = core.is_system_project(project)
    return {
        "project": project,
        "project_id": str(project.get("project_id") or core.SYSTEM_PROJECT_ID),
        "name": (core.SYSTEM_PROJECT_NAME if is_system
                 else str(project.get("name") or "未命名项目")),
        "selected": not is_system,
        "is_system": is_system,
    }


def _apply_project_context(project_id):
    """Project Context 的**唯一写入口**：侧栏 switcher / 打开项目 / 新建项目共用。

    一次写入同时落两处：`active_project_id`（导航与侧栏）与 `task_project_id`
    （新建任务的归属）。二者必须是同一个值——它们是同一件事的两种读法，分开写
    迟早会变成"侧栏 A、任务 B"。
    """
    canonical = core._project.canonical_project_id(project_id)
    _remember_project_visit(canonical)
    st.session_state["active_project_id"] = canonical
    st.session_state["task_project_id"] = canonical
    st.session_state.pop("task_project_choice", None)
    _route_params(project=canonical, view=None)
    return canonical


def _sync_task_project_context():
    """让 Task 归属成为 Project Context 的**投影**，而不是第二份状态。

    每次运行都对齐一次：上下文换了，新建任务的归属就跟着换，不存在"侧栏已经
    切到 B、任务还挂在 A"的中间态。
    """
    context = _project_context()
    if st.session_state.get("task_project_id") != context["project_id"]:
        st.session_state["task_project_id"] = context["project_id"]
    if st.session_state.get("task_project_context_id") != context["project_id"]:
        st.session_state["task_project_context_id"] = context["project_id"]
        st.session_state.pop("task_project_choice", None)
    return context


def _in_new_task_flow():
    """是否停在「新建任务」流程里（决定 switcher 切换后要不要留在原地）。"""
    return (str(st.session_state.get("app_view") or "") == "new"
            and not st.session_state.get("workspace_mode"))


def _sidebar_current_project():
    """侧栏「项目上下文」里那个**真实项目**，没有时返回 None。

    「未分类」是任务收纳区，不是项目：它不出现在这里，否则会持续强化
    "未分类 = 项目"这个错误概念。未分类任务有自己的轻量入口（项目中心）。
    """
    project = _current_project_context()
    if project is None or core.is_system_project(project):
        return None
    return project


def _sidebar_active_job():
    """侧栏「当前任务」的来源：任务必须**真实存在**。

    `active_job_id` 是会话状态；任务被删除之后它仍然会留在状态里，进而让侧栏
    显示一个已经不存在、点开还会报错的入口。因此这里以磁盘为准。
    """
    job_id = str(st.session_state.get("active_job_id") or "")
    if not job_id:
        return ""
    return job_id if core.load_job_state(job_id) is not None else ""


def _begin_new_task(project_id=""):
    """Open Step 1 with the current workspace project as its default context.

    `project_id` 显式传入时优先（Project Detail 的「+ 新建任务」走这条），保证
    从项目里创建任务时**所属项目已经选定**，用户不必在创建流程里再选一次。
    归档项目不是合法的任务归属：回落到系统工作区并如实说明。
    """
    target = str(project_id or "").strip()
    if not target:
        target = str((_sidebar_current_project() or {}).get("project_id") or "")
    if target and core.is_system_project_id(target):
        target = ""
    if target:
        record = core.load_project(target)
        if record is None:
            target = ""
        elif record.get("archived_at"):
            _push_flash(f"「{record['name']}」已归档，新任务不会归入它；"
                        "请先恢复项目。", tone="warning")
            target = ""
    # 归档 / 已删除的上下文不能留着当归属：显式落回系统工作区，而不是让侧栏
    # 继续显示一个本次任务用不上的项目。
    _apply_project_context(target or core.SYSTEM_PROJECT_ID)
    st.session_state.update(app_view="new", workspace_mode=False, task_step=1)
    st.session_state.pop("task_project_choice", None)


def _sidebar_project_switcher(context):
    """侧栏「项目」分组里的上下文控件：**state / switch action**，不是导航。

    它只回答"我此刻在哪个项目里工作"。点击打开一个**轻量 Popover**（搜索 +
    项目列表 + 新建项目），选中后立刻收起并更新全局 Project Context。

    Project Management（查看 / 新建 / 重命名 / 归档 / 删除）属于同组的
    「项目中心」导航项，**不在**这个 Popover 里——所以这里没有「管理所有项目」。
    这正是本轮修正的交互语义：state action 与 navigation 相邻但严格分离。

    不管有没有选中项目，它都是**同一个 compact 控件**：选中时显示项目名，
    未选中时显示「未选择项目」。绝不把「未分类」渲染成一个项目。
    """
    label = context["name"] if context["selected"] else "未选择项目"
    display = _project_display_title({"name": label}) or "未选择项目"
    if len(display) > 14:
        display = display[:13] + "…"
    with st.container(key="current_project"):
        if not context["selected"]:
            # 空的语义标记（不渲染任何文字）：CSS 用它把 selector 切成中性态，
            # 没有项目时不该看起来像已经选中了一个。
            st.markdown('<span class="tp-nav-empty" aria-hidden="true"></span>',
                        unsafe_allow_html=True)
        if _project_switcher_is_open("sidebar"):
            # 同一个套路：展开态也是**空的语义标记**，CSS 用它把触发器切成"已按下"，
            # 这样开与合共用一套控件样式，不会突然换一种按钮语言。
            st.markdown('<span class="tp-nav-open" aria-hidden="true"></span>',
                        unsafe_allow_html=True)
        if st.button(f"{display}  ▾",
                     key=_PROJECT_SWITCHER_ANCHORS["sidebar"]["trigger"],
                     icon=":material/folder_open:" if context["selected"]
                     else ":material/swap_horiz:",
                     width="stretch", type="secondary",
                     help="切换项目上下文" if context["selected"]
                     else "选择要进入的项目"):
            _toggle_project_switcher("sidebar")
            st.rerun()
        # 面板**只在展开时渲染**：列表数据一次约 0.4 s，常驻渲染会把它加到每一次
        # 重跑上。收起时不渲染，空闲成本为零——这才是 quick switcher。
        if _project_switcher_is_open("sidebar"):
            _render_project_switcher_body("sidebar")
        viewing = str(st.session_state.get("active_project_id") or "")
        # `is_system_project_id("")` 为真（空值收敛到系统项目），所以这里必须
        # 先确认"确实打开了一个项目"，再判断它是不是系统工作区。而且这条
        # "正在查看未分类任务"提示只属于**项目详情**路由：上下文会被带进项目中心，
        # 只看 `app_view == "projects"` 会让管理页也挂上这句不该出现的话。
        if viewing and core.is_system_project_id(viewing) \
                and str(st.session_state.get("app_view") or "") == "projects" \
                and _projects_route() == "detail":
            st.markdown('<p class="tp-nav-note">正在查看未分类任务</p>',
                        unsafe_allow_html=True)


# ---- Project Switcher：**唯一**一份上下文切换 UI ----
# 交互模型（本轮修正）：上下文 selector 展开的是**轻量下拉面板**，不是大型 Modal。
# 两个锚点共用同一份列表实现，所以不存在"两套并行的 project switching UX"：
#
#   sidebar：侧栏「项目」分组的 selector（主入口，state action）
#   task   ：新建任务第 1 步「项目上下文」块的 [更改] / [选择项目]（就近入口）
#
# 为什么不用 `st.popover` 而用一个受控的会话标记：①`st.popover` 的开合由前端
# 驱动，服务端既读不到也关不掉——"选中后立即关闭"与"点项目中心不得弹 switcher"
# 这两条会变成不可测也不可靠的约定；②Popover 的内容默认**常驻渲染**（惰性要靠
# `.open`，而 `.open` 只在 `on_change="rerun"` 下才存在），面板数据一次约 0.4 s，
# 常驻等于给每次重跑都加上这笔开销。用会话标记驱动，展开才渲染、关闭是确定性的。
#
# 容器 key 都含 `switcher_*` 片段，CSS 用 `[class*="switcher_..."]` 同时命中两处；
# 每处锚点又有自己的整套 widget key，同一页面里两处同时展开不会撞 key。
#
# 业务边界：switcher 只做 context switching + 搜索 + 进入 create-project flow。
# 管理动作（查看全部 / 重命名 / 归档 / 删除）属于侧栏「项目中心」，不在这里。
_PROJECT_SWITCHER_ANCHORS = {
    "sidebar": {"trigger": "current_project_selector",
                "open": "sidebar_project_switcher_open",
                "panel": "project_switcher_panel",
                "search": "project_switcher_search",
                "query": "project_switcher_query",
                "list": "project_switcher_list",
                "row": "switcher_pick_",
                "footer": "project_switcher_footer",
                "new": "switcher_new_project"},
    "task": {"trigger": "task_project_switcher_trigger",
             "open": "task_project_switcher_open",
             "panel": "task_project_switcher_panel",
             "search": "task_project_switcher_search",
             "query": "task_project_switcher_query",
             "list": "task_project_switcher_list",
             "row": "task_switcher_pick_",
             "footer": "task_project_switcher_footer",
             "new": "task_switcher_new_project"},
}


def _project_switcher_is_open(anchor="sidebar"):
    """某个锚点的切换面板是否展开。纯 UI chrome，不参与任何 Project 状态推导。"""
    return bool(st.session_state.get(_PROJECT_SWITCHER_ANCHORS[anchor]["open"]))


def _close_project_switcher(anchor="sidebar"):
    """收起某个锚点的切换面板。

    "选中后立刻关闭"是硬要求：面板不会因为内部按钮重跑而自动消失（脚本式 UI 里
    它就是一段普通内容），所以每次选中都显式关一次。
    """
    st.session_state[_PROJECT_SWITCHER_ANCHORS[anchor]["open"]] = False


def _close_all_project_switchers():
    """收起全部切换面板（导航离开当前语境时调用）。"""
    for anchor in _PROJECT_SWITCHER_ANCHORS:
        _close_project_switcher(anchor)


def _toggle_project_switcher(anchor="sidebar"):
    """展开 / 收起**同一个**切换面板，同一时刻只留一个。

    两处锚点展开的是同一份列表：同时开着会被读成两套系统（本轮要消除的正是这个
    观感），所以打开一处就收起另一处。
    """
    key = _PROJECT_SWITCHER_ANCHORS[anchor]["open"]
    opening = not bool(st.session_state.get(key))
    if opening:
        _close_all_project_switchers()
    st.session_state[key] = opening


def _ordered_project_switcher_options(options, current_project_id):
    """Prioritize the current project and recent session visits."""
    by_id = {str(item.get("project_id") or ""): item for item in options}
    ordered_ids = []
    current_id = str(current_project_id or "")
    if current_id in by_id:
        ordered_ids.append(current_id)
    for project_id in st.session_state.get("project_switcher_recent") or []:
        project_id = str(project_id or "")
        if project_id in by_id and project_id not in ordered_ids:
            ordered_ids.append(project_id)
    ordered_ids.extend(project_id for project_id in by_id
                       if project_id not in ordered_ids)
    return [by_id[project_id] for project_id in ordered_ids]


def _switch_project_context(project):
    """Apply a context selection and finish with one success toast."""
    project_id = str(project["project_id"])
    project_name = str(project.get("name") or "未分类")
    # 在「新建任务」流程里只换上下文：不把用户从创建流程拽到项目详情页。
    # 其余任何页面里，切换上下文 = 进入该项目（导航语义不变）。
    in_flow = _in_new_task_flow()
    # 选中即收起：面板不会因为内部按钮重跑而自动消失（见 `_close_project_switcher`）。
    # 两处锚点都收：上下文已经变了，留着另一个展开会显示过期的"当前"行。
    _close_all_project_switchers()
    if in_flow:
        _apply_project_context(project_id)
        _push_flash(f"已切换到「{project_name}」")
        st.rerun()
        return
    _push_flash(f"已切换到「{project_name}」")
    _open_project(project_id)
    st.rerun()


def _render_project_switcher_body(anchor="sidebar"):
    """项目切换列表正文。**唯一一份实现**，两个锚点共用。

    只做三件事：切换当前 Project Context、搜索、进入 create-project flow。
    管理动作（查看全部 / 重命名 / 归档 / 删除）不在这里——那是「项目中心」的职责，
    所以这里**没有**「管理所有项目」：同一个页面里出现两个指向管理页的入口，
    正是本轮要消除的重复。

    「当前」标记以**原始上下文**为准（可能落在系统工作区），因此用
    `_current_project_context()` 而不是只认真实项目的 `_sidebar_current_project()`。
    """
    ids = _PROJECT_SWITCHER_ANCHORS[anchor]
    context_id = str((_current_project_context() or {}).get("project_id") or "")
    options = _ordered_project_switcher_options(
        core.list_active_project_options(), context_id)
    with st.container(key=ids["panel"]):
        st.caption("新任务将默认加入所选项目，已有任务不会移动。")

        search_query = ""
        if len(options) > 4:
            with st.container(key=ids["search"]):
                search_query = st.text_input(
                    "搜索项目", key=ids["query"],
                    placeholder="搜索项目名称", label_visibility="collapsed",
                    icon=":material/search:") or ""
        normalized_query = str(search_query).strip().casefold()
        filtered = [
            item for item in options
            if not normalized_query
            or normalized_query in str(item.get("name") or "").casefold()
            or normalized_query in str(item.get("description") or "").casefold()
        ]

        with st.container(key=ids["list"]):
            for project in filtered:
                pid = str(project["project_id"])
                is_system = core.is_system_project(project)
                is_current = pid == context_id
                view = core.project_summary(project)
                project_name = ("未分类任务" if is_system
                                else str(project.get("name") or "未命名项目"))
                safe_name = re.sub(
                    r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", project_name)
                status = []
                if is_current:
                    status.append("✓ 当前")
                if is_system:
                    status.append("系统工作区")
                status_label = " ".join(f"`{item}`" for item in status)
                detail = (f"{view['job_count']} 个未归入项目的任务"
                          if is_system else f"{view['job_count']} 个任务")
                row_label = (
                    f"**{safe_name}**  "
                    f"{status_label}  \n{detail}"
                    if status_label else
                    f"**{safe_name}**  \n{detail}")
                if st.button(
                        row_label, key=f"{ids['row']}{pid}",
                        width="stretch", icon=(
                            ":material/inbox:" if is_system
                            else ":material/folder:"),
                        type="primary" if is_current else "secondary"):
                    _switch_project_context(project)
        if not filtered:
            st.caption("没有匹配的项目。")

        st.divider()
        with st.container(key=ids["footer"]):
            # 单个低频动作：新建项目。管理入口**不**在这里重复一份。
            if st.button("新建项目", key=ids["new"],
                         width="stretch", icon=":material/add:"):
                _close_project_switcher(anchor)
                _open_project_modal("new")
                st.rerun()


def _sidebar_task_steps():
    """当前任务步骤（只在任务创建流程里出现，收在「当前任务」下）。"""
    with st.container(key="task_steps"):
        current_step = st.session_state.task_step
        for number, label in ((1, "文档与画像"), (2, "翻译策略"),
                              (3, "交付内容"), (4, "确认运行")):
            status = "done" if number < current_step else "current" if number == current_step else "pending"
            icon = ":material/check_circle:" if status == "done" \
                else ":material/radio_button_checked:" if status == "current" \
                else ":material/radio_button_unchecked:"
            if st.button(f"{number:02d}  {label}", icon=icon,
                         key=f"task_step_{status}_{number}", width="stretch",
                         type="primary" if status == "current" else "secondary"):
                _request_step(number)
                st.rerun()


# ---- URL 路由恢复（必须在读取 app_view 之前）----
# 刷新页面时 URL 里可能有 `project=<uuid>`：先把它恢复成导航状态，再让下面的
# 分派逻辑读到正确的 `app_view`。只在启动时做一次（`_route_restored` 标记避免
# 每次 rerun 都覆盖用户当前的导航状态）。
if not st.session_state.get("_route_restored"):
    st.session_state["_route_restored"] = True
    _restore_route_from_params()

app_view = st.session_state.get("app_view", "new")
workspace_mode = st.session_state.get("workspace_mode", False)

with st.sidebar:
    st.markdown(
            '<div class="tp-brand" aria-label="FolioThread 智能体翻译工作台">'
            f'<img class="tp-brand-logo" src="{_BRAND_LOGO_URI}" '
            'alt="FolioThread Agentic Translation Workspace"></div>',
            unsafe_allow_html=True)
    new_task_in_flow = app_view == "new" and not workspace_mode
    # Project Detail 的页面级 Primary CTA 是 Header 的「+ 新建任务」：侧栏这一颗
    # 必须退成 secondary，避免两个同级主操作互相竞争。动作仍然是同一个
    # （`_begin_new_task()` 会带上当前项目上下文）。未分类 Task Inbox 没有页面级 CTA，
    # 因此那里保持 primary。
    # 只有**项目详情**才有页面级 Primary CTA。判据是路由而不是"有没有上下文"：
    # 上下文现在会跟着用户进到项目中心（`_open_project_list` 不再清它），拿
    # `sidebar_project_id` 当依据会让管理页也以为自己在项目详情里。
    sidebar_project_id = str(st.session_state.get("active_project_id") or "")
    on_project_detail = (app_view == "projects" and _projects_route() == "detail")
    new_task_in_project = (on_project_detail and bool(sidebar_project_id)
                           and not core.is_system_project_id(sidebar_project_id))
    new_task_subdued = new_task_in_flow or new_task_in_project
    new_task_action_key = ("new_task_action_in_flow" if new_task_in_flow else
                           "new_task_action_in_project" if new_task_in_project else
                           "new_task_action")
    with st.container(key=new_task_action_key):
        if st.button("新建任务", icon=":material/add:", width="stretch",
                     type="secondary" if new_task_subdued else "primary"):
            _begin_new_task()
            st.rerun()
    # ---- 「项目」分组：上下文（我在哪个项目里工作）+ 管理入口（我拥有哪些项目）----
    # 两者同属 Project，因此收进**同一个分组**：同一个标题、上下相邻、中间不插
    # 分隔线。拆成"顶部上下文 + 底部项目中心"会被读成两套系统，这正是本轮要消除
    # 的割裂感。主次仍然明确：selector 是全局唯一上下文来源，「项目中心」只是它
    # 的次级入口（见 CSS `st-key-project_center_entry`）。
    with st.container(key="project_nav_group"):
        st.markdown('<div class="tp-nav-label">项目</div>', unsafe_allow_html=True)
        # 每次运行都对齐一次：Task 归属是上下文的投影，不存在两份互相矛盾的选择。
        _sidebar_context = _sync_task_project_context()
        _sidebar_project_switcher(_sidebar_context)
        # Project Management：**纯导航**——只进入管理页（列表），不切换上下文，
        # 也绝不打开 switcher。它和 selector 相邻但不同级：扁平行、透明底，
        # 不升格成第二颗主按钮。
        # "当前页"标记只在**列表路由**上出现（`projects_route == "list"`），不再拿
        # `active_project_id` 当判据——上下文现在会被带进管理页，用旧判据会让标记
        # 在管理页上消失（需求 B：位于 Project Center 时要保持 active state）。
        _project_center_current = (app_view == "projects" and not workspace_mode
                                  and _projects_route() == "list")
        with st.container(key="project_center_entry"):
            if _project_center_current:
                st.markdown('<span class="tp-nav-current" aria-hidden="true"></span>',
                            unsafe_allow_html=True)
            if st.button("项目中心", icon=":material/folder_managed:",
                         width="stretch", key="project_center_entry_button",
                         help="查看所有项目、新建 / 重命名 / 归档 / 删除；"
                              "不切换当前项目上下文"):
                _open_project_list()
                st.rerun()
    # ---- 当前任务（任务创建流程的步骤收在这里，不与项目混在一栏）----
    _sidebar_active_job = _sidebar_active_job()
    if app_view == "new" and not workspace_mode:
        st.markdown('<div class="tp-nav-divider"></div>'
                    '<div class="tp-nav-label">当前任务</div>', unsafe_allow_html=True)
        _sidebar_task_steps()
    elif _sidebar_active_job and app_view == "workspace":
        _sidebar_state = core.load_job_state(_sidebar_active_job) or {}
        _sidebar_job_label = (_history_view.document_title(_sidebar_state)
                              or _sidebar_active_job)[:16]
        st.markdown('<div class="tp-nav-divider"></div>'
                    '<div class="tp-nav-label">当前任务</div>', unsafe_allow_html=True)
        if st.button(_sidebar_job_label, icon=":material/description:",
                     key=f"sidebar_job_{_sidebar_active_job}", width="stretch",
                     type="primary" if workspace_mode else "secondary",
                     help="回到当前任务工作区"):
            _open_job(_sidebar_active_job, _sidebar_state, "overview")
            st.rerun()
    # ---- 工作区区：跨项目的资料与全局设置 ----
    # 这是 **global navigation**，不是 Project 的一部分：所以「项目中心」不在这一
    # 组里——否则它会被读成"和历史任务 / 术语与翻译记忆同类的第三个资料库"，
    # 而它其实是 Project 分组的次级入口。
    st.markdown('<div class="tp-nav-label">工作区</div>', unsafe_allow_html=True)
    with st.container(key="library_nav"):
        if st.button("历史任务", icon=":material/history:", width="stretch",
                     type="primary" if app_view == "history" else "secondary"):
            st.session_state.app_view = "history"
            st.rerun()
        if st.button("术语与翻译记忆", icon=":material/menu_book:", width="stretch",
                     type="primary" if app_view == "library" else "secondary"):
            st.session_state.app_view = "library"
            st.rerun()
        if st.button("设置", icon=":material/settings:", width="stretch",
                     type="primary" if app_view == "settings" else "secondary"):
            st.session_state.app_view = "settings"
            st.rerun()
    with st.container(key="provider_status"):
        provider_col, manage_col = st.columns([3, 1])
        ai_view = _ai_configuration_view()
        connection_status = st.session_state.get("provider_connection_status", "unverified")
        # Keep the legacy class for existing CSS/tests while exposing the
        # more useful configuration state in the visible copy.
        provider_col.markdown(f'<div class="tp-provider is-{connection_status} is-{ai_view["state"]}">'
                              '<strong>AI引擎</strong></div>',
                              unsafe_allow_html=True)
        if manage_col.button("管理", key="manage_provider"):
            st.session_state.app_view = "settings"
            st.rerun()
        st.markdown('<div class="tp-engine-detail">'
                    f'<span>{escape(str(ai_model or "尚未选择模型"))}</span>'
                    f'<span>{escape(ai_view["label"])}</span></div>',
                    unsafe_allow_html=True)

# ---- 跨页面的 Project 弹窗 ----
# 这里只剩**管理类**弹窗（新建 / 导入 / 重命名 / 编辑 / 归档 / 删除 / 移入任务）。
# 「切换项目」不再是弹窗：它是侧栏 selector（以及正文上下文块）上的轻量 Popover，
# 在各自的锚点里就地渲染，因此这里没有任何 switcher 的分支。
_render_project_modal()

# Pipeline defaults; preset is a template and strategy_config is the effective configuration.
preset_label = st.session_state.get("translation_preset", "标准")
if preset_label not in _PRESET_CONFIGS:
    preset_label = "标准"
if "strategy_config" not in st.session_state:
    st.session_state.strategy_config = dict(_PRESET_CONFIGS[preset_label])
if "delivery_preset" not in st.session_state:
    st.session_state.delivery_preset = "standard"
if "delivery_preset_modified" not in st.session_state:
    st.session_state.delivery_preset_modified = False
if "output_config" not in st.session_state:
    st.session_state.output_config = dict(_DELIVERY_PRESET_CONFIGS["standard"])
strategy_config = st.session_state.strategy_config
output_config = st.session_state.output_config
# A normal/quick strategy never exposes research products in Step 03.  Clear
# stale UI-only state so a hidden option cannot accidentally reach a new run;
# persisted/resumed jobs still take their saved pipeline configuration in
# `_pipeline_kwargs` below.
if not _research_outputs_visible(preset_label, strategy_config):
    output_config["enable_report"] = False
    for _research_key in _DELIVERY_RESEARCH_KEYS[1:]:
        output_config[_research_key] = False
auto_term = strategy_config["auto_term"]
use_tm = strategy_config["use_tm"]
enable_review = strategy_config["enable_review"]
strict_terminology_governance = strategy_config["strict_terminology_governance"]
enable_annotate = output_config["enable_annotate"]
enable_report = output_config["enable_report"]
target_lang = st.session_state.get("target_lang", "简体中文")
user_glossary = st.session_state.get("task_glossary", [])
uploaded_files = []
run_clicked = False
resume_choice = None
job_choices = [f"{j['state'].get('filename', '?')} {core.progress_label(j['state'])}"
               for j in saved_jobs]
style_rules = st.session_state.get(
    "style_rules", "保持学术书面语；专有名词、作者姓名、机构名、引用标注、URL 等保留原文；标点遵循目标语言规范。")
annotation_colors = st.session_state.get("annotation_colors", {
    "rare": "C00000", "domain": "BF8F00", "hard": "008080"})
theory_choice = st.session_state.get("translation_theory_choice", "自动推荐（建议）")
if theory_choice == "自定义":
    translation_theory = st.session_state.get("custom_translation_theory", "").strip() \
        or "自定义理论框架"
elif theory_choice in ("自动推荐", "自动推荐（建议）"):
    translation_theory = "基于文本特征、案例证据与可用文献自动推荐理论框架"
else:
    translation_theory = theory_choice
_uploaded_literature = st.session_state.get("literature_upload_sources") or []
_registry_literature = st.session_state.get("literature_registry_sources")
if _registry_literature is None:
    _registry_literature = st.session_state.get("literature_sources") or []
literature_sources = [*_uploaded_literature, *_registry_literature] or None
research_settings = st.session_state.get("research_settings", {
    "target_words": 4200, "body_language": "zh-CN",
    "case_selection_policy": "mixed", "report_stage": "final_report",
    "analysis_dimensions": ["文本特征", "术语管理", "翻译策略", "译后编辑与质量控制"],
})
research_settings = dict(research_settings)
template_input = st.session_state.get("report_template_input")
if template_input:
    research_settings["report_template_contract"] = template_input.get("contract")
elif st.session_state.get("report_template_removed"):
    research_settings.pop("report_template_contract", None)


def _pipeline_kwargs(state=None):
    """Build the current UI configuration for a new or resumed worker."""
    state = state if isinstance(state, dict) else {}
    saved = state.get("pipeline_config") or {}
    academic_state = state.get("academic_state") or {}
    persisted = bool(saved or state.get("p1_done") or state.get("p2_done")
                     or academic_state.get("artifacts"))
    resume_report = saved.get("enable_report") if saved else \
        state.get("report_enabled", enable_report) if persisted else enable_report
    if state and (academic_state.get("artifacts") or academic_state.get(
            "current_stage") not in {None, "", "not_started"}):
        resume_report = True
    resume_annotate = saved.get("enable_annotate") if "enable_annotate" in saved \
        else state.get("enable_annotate", enable_annotate) if persisted else enable_annotate
    delivery = state.get("delivery_config") or output_config
    delivery = core.normalize_delivery_config(
        delivery, enable_report=resume_report, enable_annotate=resume_annotate)
    understanding_default = strategy_config.get("enable_understanding", True)
    if persisted and "enable_understanding" not in saved:
        understanding_default = bool(
            state.get("profile_done") or state.get("understanding_done")
            or state.get("quality_mode"))
    return {
        "provider": ai_provider,
        "api_key": api_key,
        "model": ai_model,
        "target_lang": saved.get("target_lang") or state.get("target_lang") or target_lang,
        "auto_term": saved.get("auto_term", auto_term),
        "enable_report": bool(resume_report),
        "translation_theory": saved.get("translation_theory") or
        state.get("theory") or translation_theory,
        "user_glossary": state.get("glossary") or user_glossary,
        "style_rules": saved.get("style_rules", style_rules),
        "enable_review": saved.get("enable_review", enable_review),
        "enable_annotate": bool(resume_annotate),
        "use_tm": saved.get("use_tm", use_tm),
        "enable_understanding": saved.get(
            "enable_understanding", understanding_default),
        "batch_size": _batch_params(saved or strategy_config)[0],
        "max_batch_chars": _batch_params(saved or strategy_config)[1],
        "translator_base_url": api_base,
        "strict_terminology_governance": saved.get(
            "strict_terminology_governance", state.get(
                "quality_mode", strict_terminology_governance)),
        **({
            "reviewer_provider": reviewer_provider,
            "reviewer_model": reviewer_model,
            "reviewer_api_key": reviewer_api_key,
            "reviewer_base_url": reviewer_base_url,
        } if reviewer_mode == "separate" else {}),
        "research_settings": state.get("research_settings") or research_settings,
        "literature_sources": state.get("literature_sources") or literature_sources,
        "delivery_config": delivery,
    }


def _resume_job(job_id, state):
    return core.resume_job(
        job_id, state.get("filename") or "当前任务",
        _pipeline_kwargs(state), base_url=api_base)

# ================= Main views =================
setup_placeholder = st.empty()
with setup_placeholder.container():
    if app_view == "settings":
        _page_title("AI 引擎", "配置一次，所有新任务自动使用当前连接")
        if not core.is_onboarded():
            st.caption("首次使用：选择服务商 → 填写 API 密钥与模型 → 保存配置 → 点击「测试连接」通过后即可开始翻译。")
        pc1, pc2 = st.columns(2)
        ai_provider = pc1.selectbox("服务商", providers,
                                    index=providers.index(ai_provider), key="provider_choice",
                                    on_change=_reset_provider_connection,
                                    **_PERSIST_STATE)
        provider_cfg = core.PROVIDERS[ai_provider]
        model_opts = sorted(provider_cfg.get("models") or [], key=str.casefold)
        fetched_models = sorted(
            set(st.session_state.get(f"fetched_models_{ai_provider}") or []),
            key=str.casefold)
        if model_opts:
            default_model = provider_cfg.get("default_model")
            if default_model not in model_opts:
                default_model = model_opts[0]
            model_key = f"model_choice_{ai_provider}"
            if st.session_state.get(model_key, default_model) not in model_opts:
                st.session_state[model_key] = default_model
            ai_model = pc2.selectbox("模型", model_opts,
                                     index=model_opts.index(st.session_state.get(
                                         model_key, default_model)),
                                     key=model_key,
                                     on_change=_reset_provider_connection,
                                     **_PERSIST_STATE)
        elif fetched_models:
            model_key = f"fetched_model_choice_{ai_provider}"
            preferred_key = f"preferred_fetched_model_{ai_provider}"
            current_model = st.session_state.get(
                model_key, st.session_state.get(
                    preferred_key, st.session_state.get(f"model_choice_{ai_provider}")))
            if current_model not in fetched_models:
                current_model = fetched_models[0]
            ai_model = pc2.selectbox(
                "模型", fetched_models,
                index=fetched_models.index(current_model), key=model_key,
                on_change=_reset_provider_connection, args=(True,),
                **_PERSIST_STATE)
            st.session_state[f"model_choice_{ai_provider}"] = ai_model
        else:
            ai_model = pc2.text_input("模型", key=f"model_choice_{ai_provider}",
                                     placeholder=provider_cfg.get("model_hint") or "model-name",
                                     on_change=_reset_provider_connection,
                                     **_PERSIST_STATE)
        api_key = st.text_input("API 密钥", type="password", key=f"api_key_{ai_provider}",
                                on_change=_reset_provider_connection,
                                **_PERSIST_STATE)
        if provider_cfg.get("custom_base_url"):
            api_base = st.text_input("API 地址", key="custom_base_url",
                                     placeholder="https://your-relay.example.com/v1",
                                     on_change=_reset_provider_connection,
                                     **_PERSIST_STATE)
        else:
            api_base = None
        st.markdown("### 独立审校模型")
        st.caption("可选：不单独配置时，审校会使用翻译模型。")
        reviewer_mode = st.radio(
            "审校模型",
            ["same", "separate"],
            index=0 if st.session_state.get("reviewer_mode", "same") == "same" else 1,
            format_func=lambda value: "与翻译模型相同" if value == "same" else "单独配置",
            key="reviewer_mode",
            horizontal=True,
            on_change=_reset_reviewer_connection,
            **_PERSIST_STATE,
        )
        if reviewer_mode == "separate":
            reviewer_provider = st.selectbox(
                "审校服务商", providers,
                index=providers.index(st.session_state.get(
                    "reviewer_provider_choice", ai_provider))
                if st.session_state.get("reviewer_provider_choice", ai_provider) in providers
                else providers.index(ai_provider),
                key="reviewer_provider_choice",
                on_change=_reset_reviewer_connection,
                **_PERSIST_STATE,
            )
            reviewer_provider_cfg = core.PROVIDERS[reviewer_provider]
            reviewer_model_opts = sorted(
                reviewer_provider_cfg.get("models") or [], key=str.casefold)
            if reviewer_model_opts:
                reviewer_default = reviewer_provider_cfg.get("default_model")
                if reviewer_default not in reviewer_model_opts:
                    reviewer_default = reviewer_model_opts[0]
                reviewer_current = st.session_state.get(
                    "reviewer_model", reviewer_default)
                if reviewer_current not in reviewer_model_opts:
                    reviewer_current = reviewer_default
                    st.session_state.reviewer_model = reviewer_current
                reviewer_model = st.selectbox(
                    "审校模型", reviewer_model_opts,
                    index=reviewer_model_opts.index(reviewer_current),
                    key="reviewer_model", on_change=_reset_reviewer_connection,
                    **_PERSIST_STATE)
            else:
                reviewer_model = st.text_input(
                    "审校模型", key="reviewer_model",
                    placeholder=reviewer_provider_cfg.get("model_hint") or "例如 gpt-4.1-mini",
                    on_change=_reset_reviewer_connection,
                    **_PERSIST_STATE,
                )
            reviewer_api_key = st.text_input(
                "审校 API 密钥", type="password", key="reviewer_api_key",
                on_change=_reset_reviewer_connection,
                **_PERSIST_STATE,
            )
            reviewer_base_url = st.text_input(
                "审校 API 地址（可选）", key="reviewer_base_url",
                placeholder="留空使用服务商默认地址",
                on_change=_reset_reviewer_connection,
                **_PERSIST_STATE,
            )
        else:
            reviewer_provider = ai_provider
            reviewer_model = ""
            reviewer_api_key = ""
            reviewer_base_url = ""
        ai_view = _ai_configuration_view()
        reviewer_view = ai_view["reviewer"]
        reviewer_label = ("使用翻译模型" if reviewer_mode == "same"
                          else reviewer_view["label"])
        st.markdown(
            '<div class="tp-connection-summary">'
            f'<div><span>翻译模型</span><strong>{escape(ai_view["label"])}</strong>'
            f'<small>{escape(str(ai_provider))} · {escape(str(ai_model or "尚未选择模型"))}</small></div>'
            f'<div><span>独立审校</span><strong>{escape(reviewer_label)}</strong>'
            f'<small>{escape("与翻译模型共用连接" if reviewer_mode == "same" else reviewer_view["label"])}</small></div>'
            '</div>', unsafe_allow_html=True)
        can_fetch_models = provider_cfg.get("kind") in ("openai", "openai_compat") \
            and (provider_cfg.get("custom_base_url") or not model_opts)
        if can_fetch_models:
            fetch_base = api_base or provider_cfg.get("base_url")
            if st.button("获取可用模型", width="stretch",
                         disabled=not (api_key and fetch_base),
                         help="从 OpenAI 兼容接口的 /models 目录读取可用模型"):
                with st.spinner("正在获取模型目录…"):
                    ok, fetched, msg = core.fetch_provider_models(
                        ai_provider, api_key, base_url=fetch_base)
                if ok:
                    st.session_state[f"fetched_models_{ai_provider}"] = fetched
                    selected = st.session_state.get(f"model_choice_{ai_provider}")
                    if selected not in fetched:
                        selected = fetched[0]
                    st.session_state[f"preferred_fetched_model_{ai_provider}"] = selected
                else:
                    st.session_state.pop(f"fetched_models_{ai_provider}", None)
                st.session_state.model_fetch_feedback = (ok, msg)
                st.rerun()
            if feedback := st.session_state.get("model_fetch_feedback"):
                ok, msg = feedback
                (st.success if ok else st.error)(msg)
        display_base = api_base or provider_cfg.get("base_url") or "由服务商管理"
        st.caption(f"接口地址：{display_base}")
        save_ready = bool(api_key and ai_model) and (
            reviewer_mode == "same"
            or bool(reviewer_provider and reviewer_model and reviewer_api_key)
        )
        save_btn, test_btn = st.columns(2)
        with save_btn:
            if st.button("保存配置", width="stretch",
                         disabled=not save_ready,
                         help="把服务商、模型与 API 密钥写入本地，重启应用后仍会保留"):
                core.save_provider_config(
                    ai_provider, ai_model, api_key, api_base,
                    reviewer=(
                        {"provider": reviewer_provider, "model": reviewer_model,
                         "api_key": reviewer_api_key, "base_url": reviewer_base_url}
                        if reviewer_mode == "separate" else None
                    ),
                )
                st.toast("AI 引擎配置已保存，重启应用后仍会保留")
        with test_btn:
            if st.button("测试连接", type="primary", width="stretch",
                         disabled=not save_ready):
                with st.spinner("正在验证连接…"):
                    ok, msg = core.test_provider(ai_provider, api_key,
                                                 ai_model, base_url=api_base)
                    reviewer_ok, reviewer_msg = True, ""
                    if ok and reviewer_mode == "separate":
                        reviewer_ok, reviewer_msg = core.test_provider(
                            reviewer_provider, reviewer_api_key, reviewer_model,
                            base_url=reviewer_base_url or None)
                if ok:
                    core.mark_onboarded()
                st.session_state.provider_configured = ok and reviewer_ok
                st.session_state.provider_connection_status = \
                    "connected" if ok else "error"
                st.session_state.reviewer_connection_status = (
                    "connected" if reviewer_ok else "error")
                if ok and not reviewer_ok:
                    msg = f"翻译连接正常；审校连接失败：{reviewer_msg}"
                st.session_state.provider_test_feedback = (ok and reviewer_ok, msg)
                st.rerun()
        if feedback := st.session_state.get("provider_test_feedback"):
            ok, msg = feedback
            (st.success if ok else st.error)(msg)

    elif app_view == "new" and not workspace_mode:
        _page_title("新建翻译任务", "准备输入材料与翻译上下文")
        step = st.session_state.task_step
        if not core.is_onboarded() \
                and not st.session_state.get("onboarding_dismissed") \
                and not api_key:
            with st.container(key="onboarding_guide"):
                guide_col, action_col = st.columns([3, 1])
                guide_col.markdown(
                    '<div class="tp-onboard-card">'
                    '<div class="tp-style-card-head">'
                    '<span class="material-symbols-rounded" aria-hidden="true">rocket_launch</span>'
                    '<strong>首次使用 FolioThread</strong></div>'
                    '<p>配置 AI 引擎后即可开始翻译。三步完成：</p>'
                    '<ol><li>选择服务商（DeepSeek / OpenAI / Gemini / 中转站…）</li>'
                    '<li>填写 API 密钥并选择模型</li>'
                    '<li>点击「测试连接」验证通过</li></ol></div>',
                    unsafe_allow_html=True)
                with action_col:
                    if st.button("前往设置", key="goto_settings_onboard",
                                 type="primary", width="stretch"):
                        st.session_state.app_view = "settings"
                        st.rerun()
                    if st.button("暂不配置", key="dismiss_onboarding",
                                 width="stretch"):
                        st.session_state.onboarding_dismissed = True
                        st.rerun()

        if step == 1:
            if gate_message := st.session_state.pop("step_gate_message", None):
                st.warning(gate_message, icon=":material/info:")
            # 画像只在用户真正继续时运行；这样首屏保持安静，也不会把内部
            # workflow 暴露成一个需要手动启动的 CTA。
            if st.session_state.get("pending_profile_step") == 2 \
                    and st.session_state.get("style_profiling_state") == "running":
                _finish_profile_before_step_two()

            st.markdown('<div class="tp-task-section-heading">输入文件</div>',
                        unsafe_allow_html=True)
            task_files = st.session_state.get("task_files") or []
            if task_files:
                first_job = core.load_job_state(core.file_job_id(task_files[0]["bytes"]))
                if first_job and first_job.get("p1_done"):
                    st.session_state.source_parse_state = "parsed"
                    if first_job.get("source_page_count"):
                        task_files[0]["pages"] = first_job["source_page_count"]
                with st.container(key="source_file_summary"):
                    with st.container(key="source_file_card"):
                        st.markdown(_source_file_html(task_files), unsafe_allow_html=True)
                        with st.container(key="source_file_actions"):
                            replace_col, remove_col = st.columns(2)
                            with replace_col:
                                st.button("更换文件", icon=":material/swap_horiz:",
                                          key="replace_source",
                                          on_click=_remove_source_documents,
                                          help="选择另一份 PDF 或 DOCX")
                            with remove_col:
                                st.button("删除", icon=":material/delete_outline:",
                                          key="remove_source",
                                          on_click=_remove_source_documents,
                                          help="移除当前输入文件")
            else:
                with st.container(key="source_documents"):
                    st.markdown('<div class="tp-upload-copy">'
                                '<span class="material-symbols-rounded" aria-hidden="true">upload_file</span>'
                                '<span>拖入文件或点击选择</span>'
                                '<small>支持 PDF、DOCX · 单文件最大 200 MB</small></div>',
                                unsafe_allow_html=True)
                    uploaded_files = st.file_uploader("原文", type=["pdf", "docx"],
                                                      accept_multiple_files=True,
                                                      key=f"source_documents_"
                                                          f"{st.session_state.get('source_uploader_generation', 0)}",
                                                      label_visibility="collapsed",
                                                      help="支持 PDF 和 DOCX，可一次添加多个文件")
                if uploaded_files:
                    st.session_state.task_files = [
                        {"name": f.name, "bytes": f.getvalue()} for f in uploaded_files
                    ]
                    st.session_state.source_parse_state = "uploaded"
                    st.rerun()

            st.markdown('<div class="tp-task-section-heading">基础设置</div>',
                        unsafe_allow_html=True)
            with st.container(key="task_settings_grid"):
                language_col, project_col = st.columns(2, gap="medium")
                with language_col:
                    with st.container(key="task_setting_language"):
                        st.selectbox(
                            "目标语言", ["简体中文", "繁体中文", "English", "日本語", "한국어",
                            "Deutsch", "Français", "Español", "Русский", "Português",
                                         "Italiano", "العربية"], key="target_lang",
                            **_PERSIST_STATE)
                with project_col:
                    with st.container(key="task_setting_project"):
                        _render_task_project_context()

                glossary_col, profile_col = st.columns(2, gap="medium")
                with glossary_col:
                    _render_task_termbase_setting()
                with profile_col:
                    _render_task_profile_setting()
            # Keep the current custom relay available to quick profiling, which
            # can run before the rest of the page reaches the pipeline setup.
            core.set_llm_base_url(api_base if provider_cfg.get("custom_base_url") else None)
            _render_task_actions(
                next_step=2,
                next_disabled=(not st.session_state.get("task_files")
                               or st.session_state.get("style_profiling_state")
                               == "running"))

        elif step == 2:
            _step_title(2, "翻译策略", "选择适合本次任务的工作流；需要时可调整高级设置")
            with st.container(key="preset_cards"):
                preset_columns = st.columns(3)
                for column, label in zip(preset_columns, _PRESET_CONFIGS):
                    state = "selected" if label == preset_label else "idle"
                    with column.container(key=f"preset_card_{label}_{state}"):
                        st.markdown(_preset_card_html(label), unsafe_allow_html=True)
                        display_label = _PRESET_DISPLAY_NAMES.get(label, label)
                        if st.button(f"选择{display_label}预设", key=f"choose_preset_{label}"):
                            _apply_preset(label)
                            st.toast(f"已恢复“{display_label}”预设")
                            st.rerun()
            strategy_config = st.session_state.strategy_config
            adjusted = _strategy_is_adjusted(preset_label, strategy_config)
            adjustment_count = _strategy_adjustment_count(preset_label, strategy_config)
            with st.container(key="strategy_advanced"):
                advanced_open = st.session_state.get("strategy_advanced_open", False)
                display_preset_label = _PRESET_DISPLAY_NAMES.get(preset_label, preset_label)
                state_text = f'<strong>{display_preset_label} · 已调整 {adjustment_count} 项</strong>' if adjusted \
                    else f'当前使用「{display_preset_label}」默认配置'
                summary_class = "tp-advanced-summary is-adjusted" if adjusted \
                    else "tp-advanced-summary"
                summary_text = (
                    f"{display_preset_label} · 已调整 {adjustment_count} 项 · "
                    f"已自定义 {adjustment_count} 项"
                    if adjusted else "默认配置")
                trigger_icon = "expand_less" if advanced_open else "chevron_right"
                st.markdown(
                    '<div class="tp-advanced-trigger">'
                    '<span class="tp-advanced-title">'
                    f'<span class="material-symbols-rounded" aria-hidden="true">'
                    f'{trigger_icon}</span><strong>高级设置 · 可选</strong></span>'
                    f'<span class="{summary_class}">{summary_text}</span></div>',
                    unsafe_allow_html=True)
                st.button("切换高级设置", key="toggle_strategy_advanced",
                          on_click=_toggle_advanced_strategy, width="stretch")
                if advanced_open:
                    with st.container(key="advanced_body"):
                        st.markdown(f'<div class="tp-strategy-state">{state_text}</div>',
                                    unsafe_allow_html=True)
                        st.markdown('<div class="tp-advanced-group">翻译辅助</div>',
                                    unsafe_allow_html=True)
                        _render_strategy_toggle(
                            "自动术语抽取", "从全文识别候选术语并用于翻译",
                            "auto_term", "strategy_auto_term", strategy_config)
                        _render_strategy_toggle(
                            "全文文档理解", "建立文档画像、语义单元、章节摘要和全文概要",
                            "enable_understanding", "strategy_understanding", strategy_config)
                        _render_strategy_toggle(
                            "复用翻译记忆", "精确复用已审校通过的历史译文",
                            "use_tm", "strategy_use_tm", strategy_config)
                        st.markdown('<div class="tp-advanced-group">质量控制</div>',
                                    unsafe_allow_html=True)
                        st.markdown(
                            '<div class="tp-readonly-setting">'
                            '<div class="tp-readonly-head">'
                            '<strong>基础一致性检查</strong><b>始终开启</b></div>'
                            '<span>自动检查漏译、保留项、源语残留和锁定术语</span>'
                            '</div>', unsafe_allow_html=True)
                        _render_strategy_toggle(
                            "独立审校", "使用独立模型阶段复核语义与术语，并保存审校证据",
                            "enable_review", "strategy_review", strategy_config)
                        st.markdown('<div class="tp-advanced-group">术语治理</div>',
                                    unsafe_allow_html=True)
                        _render_strategy_toggle(
                            "审核并冻结候选术语", "翻译前建立文档画像，并审核自动提取的候选术语",
                            "strict_terminology_governance", "strategy_strict_terms",
                            strategy_config)
                        st.markdown('<div class="tp-advanced-group">速度</div>',
                                    unsafe_allow_html=True)
                        _batch_labels = list(BATCH_PROFILES)
                        _current_batch = str(strategy_config.get("batch_profile") or "保守")
                        _picked_batch = st.selectbox(
                            "批次策略", _batch_labels,
                            index=_batch_labels.index(_current_batch)
                            if _current_batch in _batch_labels else 0,
                            key="strategy_batch_profile",
                            help="批次越大，模型调用次数越少、整体越快；"
                                 "但单次返回项数不符或截断的风险也越高。",
                            **_PERSIST_STATE)
                        if _picked_batch != _current_batch:
                            strategy_config["batch_profile"] = _picked_batch
                            st.session_state.strategy_config = strategy_config
                        st.caption(BATCH_PROFILES[_picked_batch]["hint"]
                                   + "。大文档建议先用「均衡」跑一章确认质量。")
            _render_task_actions(back_step=1, next_step=3)

        elif step == 3:
            _step_title(3, "交付内容", "选择要生成的文件与附加成果")
            with st.container(key="delivery_builder"):
                _render_delivery_preset_selector()
            output_config = st.session_state.output_config
            research_visible = _research_outputs_visible(preset_label, strategy_config)
            if not output_config.get("deliver_bilingual_docx"):
                output_config["enable_annotate"] = False
                st.session_state["output_annotate"] = False
            _render_delivery_group(
                "译文文件", "最终译文与审校用文档",
                _DELIVERY_TRANSLATION_ITEMS, output_config,
                group_key="translation")
            _render_delivery_group(
                "语言资产", "术语、翻译记忆与结构化数据",
                _DELIVERY_ASSET_ITEMS, output_config,
                group_key="assets")
            if research_visible:
                selected_theory = _render_delivery_group(
                    "研究产物", "仅对研究级翻译策略开放",
                    _DELIVERY_RESEARCH_ITEMS, output_config,
                    group_key="research",
                    after_rows=lambda: _render_delivery_research_details(output_config))
                if selected_theory:
                    translation_theory = selected_theory
            enable_annotate = bool(output_config.get("enable_annotate"))
            enable_report = bool(output_config.get("enable_report"))
            delivery_summary = _delivery_summary(
                output_config, research_visible=research_visible)
            _render_task_actions(
                back_step=2, next_step=4, delivery_summary=delivery_summary)

        else:
            _step_title(4, "确认运行", "核对任务、输出内容与运行环境")
            task_files = st.session_state.get("task_files") or []
            filename_summary = task_files[0]["name"] if len(task_files) == 1 \
                else f"{len(task_files)} 个文档"
            glossary_name = st.session_state.get("task_glossary_name", "未添加")
            style_template = st.session_state.get("style_template", "学术书面语")
            style_source = ""
            style_sel = st.session_state.get("style_selection")
            if style_sel:
                style_source = "接受系统推荐" if style_sel.get("source") == "accepted" \
                    else "用户调整"
            connection_status = st.session_state.get(
                "provider_connection_status", "unverified")
            task_review_required = bool(strategy_config.get("enable_review"))
            ai_view = _ai_configuration_view(task_review_required)
            can_start = bool(task_files and _workspace_view.task_ai_ready(ai_view)) and not bool(
                st.session_state.get("report_template_error"))
            if st.session_state.get("report_template_error"):
                st.warning("请移除或重新上传可解析的报告模板后再开始任务。")
            st.markdown(_summary_html(filename_summary, target_lang, preset_label,
                                      glossary_name, strategy_config, output_config,
                                      style_template, style_source),
                        unsafe_allow_html=True)
            st.markdown(_runtime_html(ai_provider, ai_model, ai_view["state"],
                                      can_start), unsafe_allow_html=True)
            if ai_view["state"] == "credentials_missing":
                with st.container(key="engine_setup_banner"):
                    message_col, action_col = st.columns([4, 1])
                    message_col.warning(
                        "已选择 AI 模型，但 API 凭据未配置。开始任务前，请先完成凭据设置。",
                        icon=":material/warning:")
                    action_col.button("前往设置", key="open_engine_settings",
                                      on_click=_open_provider_settings,
                                      width="stretch")
            elif ai_view["state"] == "error":
                with st.container(key="engine_connection_banner"):
                    message_col, action_col = st.columns([4, 1])
                    message_col.error(
                        "最近一次连接测试未通过。请检查服务商、模型或 API 地址后再开始任务。",
                        icon=":material/error:")
                    action_col.button("检查设置", key="open_engine_settings_error",
                                      on_click=_open_provider_settings,
                                      width="stretch")
            elif ai_view["state"] != "connected":
                with st.container(key="engine_connection_banner"):
                    message_col, action_col = st.columns([4, 1])
                    message_col.warning(
                        "模型已配置，但连接尚未验证。建议先测试连接，确认可用后再开始任务。",
                        icon=":material/warning:")
                    action_col.button("测试连接", key="open_engine_settings_unverified",
                                      on_click=_open_provider_settings,
                                      width="stretch")
            run_clicked = _render_task_actions(
                back_step=3, next_label="开始任务", run=True,
                next_disabled=not can_start)

    elif app_view == "workspace":
        pass
    elif app_view == "history":
        _page_title("历史任务", "")
    elif app_view == "library":
        pass

# `setup_placeholder` 保留的是上一次脚本运行写入的子树。切换到 workspace、
# history、projects 或 library 时该分支不会再次写入内容，如果不显式清空，
# 用户会看到旧的「新建翻译任务」仍浮在新页面上方。
if not (app_view == "settings" or (app_view == "new" and not workspace_mode)):
    setup_placeholder.empty()

core.set_llm_base_url(api_base if provider_cfg.get("custom_base_url") else None)

if app_view == "settings":
    _render_flashes()
    st.stop()
if app_view == "projects":
    # Project 管理页：/projects（列表）与 /projects/:projectId（详情）。
    _render_projects_surface()
    _render_flashes()
    st.stop()
if app_view == "library":
    # 术语与翻译记忆：语言资产管理中心（术语库 / 翻译记忆 / 待审核）。
    _render_flashes()
    _render_language_assets_workspace(saved_jobs)
    st.stop()
if app_view == "history":
    _render_flashes()
    if not saved_jobs:
        st.info("暂无历史任务。新建任务后，这里会列出可以继续的翻译任务。")
    else:
        _render_history_page(saved_jobs)
    st.stop()
if app_view == "new" and not workspace_mode and not run_clicked:
    # 这一步也会被"带着上下文进入新建流程"用到（例如从已归档项目点新建任务），
    # 因此必须把队列里的提示真正渲染出来——否则用户看不到"为什么没归入那个项目"。
    _render_flashes()
    st.stop()

# ================= 核心处理流（后台 worker，UI 轮询 runtime 状态）=================
pending_job = st.session_state.pop("pending_continue_job", None)

tasks = []
seen = set()
if run_clicked:
    task_inputs = st.session_state.get("task_files") or []
    has_resume = bool(saved_jobs and resume_choice and resume_choice != "— 不继续 —")
    if not task_inputs and not has_resume:
        st.error("请先上传待翻译文档，或在「上传与开始」卡片中选择要继续的本地任务。")
    else:
        st.session_state.update(workspace_mode=True, app_view="workspace")
        for f in task_inputs:
            file_bytes = f["bytes"]
            job_id = core.file_job_id(file_bytes)
            if job_id in seen:
                continue
            seen.add(job_id)
            tasks.append({"job_id": job_id, "filename": f["name"],
                          "file_bytes": file_bytes})
        if has_resume:
            job = saved_jobs[job_choices.index(resume_choice)]
            if job["job_id"] not in seen:
                tasks.append({"job_id": job["job_id"],
                              "filename": job["state"].get("filename", "?"),
                              "file_bytes": None})
                st.session_state.active_job_id = job["job_id"]
elif pending_job:
    job = next((j for j in (saved_jobs or []) if j["job_id"] == pending_job), None)
    if job:
        tasks.append({"job_id": job["job_id"],
                      "filename": job["state"].get("filename", "?"),
                      "file_bytes": None})
        st.session_state.active_job_id = job["job_id"]

if tasks:
    started_jobs = []
    for task in tasks:
        job_id, filename, file_bytes = task["job_id"], task["filename"], task["file_bytes"]
        if st.session_state.get("report_template_removed"):
            core.clear_report_template(job_id)
            st.session_state.doc_states.pop(job_id, None)
        if template_input:
            core.save_report_template(
                job_id, template_input.get("name") or "template.docx",
                template_input.get("bytes") or b"")
        state = st.session_state.doc_states.get(job_id) or core.load_job_state(job_id) \
            or core.new_job_state(filename)
        # 归属项目必须在 worker 启动前落盘：worker 是独立进程，会从磁盘读取
        # project_id 来决定注入哪一套项目记忆。已开始的任务不改归属。
        # 「未分类」写入显式 null（而不是某个"默认项目"）：未分类任务由系统工作区
        # 承载（`resolved_project_id` 负责归一），显式 null 让"用户没有选择长期
        # 归属"这一事实在 state 里保持可见。
        if "task_project_id" in st.session_state and not state.get("glossary") \
                and not state.get("p2_done"):
            chosen_project = str(st.session_state.get("task_project_id") or "")
            state["project_id"] = None if not chosen_project \
                or core.is_system_project_id(chosen_project) else chosen_project
        st.session_state.doc_states[job_id] = state
        core.save_job_state(job_id, state)

        # Report dependencies (research settings, literature, writer version) are
        # checked inside the backend before its early return.  Only skip here
        # when academic writing is explicitly disabled.
        if state["p1_done"] and state["p2_done"] and not enable_report \
                and (not enable_annotate or state.get("annotations_done")):
            started_jobs.append(job_id)
            continue

        try:
            # Step 01 的 Quick Profiling 产物：落盘为版本化 artifact，
            # 并把文档画像注入任务状态，让管线跳过重复画像。
            style_selection = st.session_state.get("style_selection")
            doc_profile = st.session_state.get("doc_profile")
            if style_selection:
                core.write_profile_artifacts(job_id, doc_profile, style_selection)
                if doc_profile and doc_profile.get("domain"):
                    job_state = core.load_job_state(job_id) or {}
                    if not job_state.get("profile_done"):
                        job_state["document_profile"] = doc_profile
                        job_state["profile_done"] = True
                        core.save_job_state(job_id, job_state)
            if task["file_bytes"] is not None:
                st.session_state.source_parse_state = "parsing"
            if file_bytes is None:
                started = core.resume_job(
                    job_id, filename, _pipeline_kwargs(state), base_url=api_base)
            else:
                started = core.start_job_worker(
                    job_id, filename, file_bytes, _pipeline_kwargs(state), base_url=api_base)
            if started or core.is_job_worker_alive(job_id):
                started_jobs.append(job_id)
                st.session_state.active_job_id = job_id
        except Exception as exc:  # setup failures remain visible in the UI
            st.error(f"无法启动 {filename}：{exc}")
    if started_jobs:
        st.session_state.update(
            active_job_id=started_jobs[0], app_view="workspace", workspace_mode=True,
            workspace_section="overview")
        st.rerun()

# ================= 术语准备与审核面板（刷新/重启后自动恢复）=================
saved_jobs_after = core.list_jobs()
active = st.session_state.get("active_job_id")
if active is None and saved_jobs_after:
    for job in saved_jobs_after:
        s = job["state"]
        if s.get("p1_done") and not s.get("p2_done") and s.get("quality_mode") \
                and s.get("glossary") is not None:
            active = job["job_id"]
            break
st.session_state.active_job_id = active

if active and not (app_view == "workspace" and st.session_state.get("active_job_id")):
    astate = core.load_job_state(active)
    if astate and astate.get("p1_done") and not astate.get("p2_done") \
            and astate.get("quality_mode") and astate.get("glossary") is not None \
            and astate.get("stage") not in ("TRANSLATING", "TRANSLATED", "ACADEMIC_WRITING", "REPORT_GENERATED", "REVIEW_REQUIRED"):
        box = st.container(border=True)
        box.subheader(f"术语准备与审核：{astate.get('filename', '?')}")
        _render_profile_editor(active, astate, box)

        entries = astate.get("glossary") or []
        frozen = astate.get("glossary_frozen")
        bypassed = astate.get("quality_bypass")
        if frozen:
            box.success(f"术语表已冻结：版本 v{frozen.get('version')} "
                        f"冻结时间 {frozen.get('frozen_at', '')}")
            with box.expander("高级诊断", expanded=False):
                st.caption(f"术语版本内容指纹：{frozen.get('glossary_hash', '')}")
        elif bypassed:
            box.info("已选择跳过人工冻结：术语以 provisional 建议注入翻译。")
        else:
            box.warning("术语尚未冻结：仍有候选术语待人工审核，「开始翻译」不可执行。"
                       "请完成审核后冻结，或选择跳过冻结。")

        box.markdown(_glossary_status_chips(entries), unsafe_allow_html=True)
        fc1, fc2, fc3 = box.columns([2, 1, 1])
        filter_status = fc1.selectbox(
            "状态筛选", ["全部", *(_TERM_STATUS_LABELS.values())],
            key=f"gfilter_status_{active}")
        only_conflicts = fc2.checkbox("只看冲突项", key=f"gfilter_conflict_{active}")
        filter_text = fc3.text_input("搜索源术语", key=f"gfilter_text_{active}")

        df = _glossary_dataframe(entries, astate.get("paras") or [])
        view_mask = pd.Series(True, index=df.index)
        if filter_status != "全部":
            view_mask &= df["status"].eq(_TERM_STATUS_VALUES[filter_status])
        if only_conflicts:
            view_mask &= df["冲突"].eq("冲突")
        if filter_text.strip():
            view_mask &= df["source"].str.contains(filter_text.strip(), case=False, na=False)
        df_view = df[view_mask]
        if not view_mask.all():
            box.caption(f"已按条件筛选：显示 {len(df_view)} / {len(df)} 条术语。")

        edited = box.data_editor(
            _humanize_glossary_editor(df_view),
            key=f"glossary_editor_{active}",
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "选择": st.column_config.CheckboxColumn("选择", default=False),
                "id": st.column_config.TextColumn("ID", disabled=True),
                "source": st.column_config.TextColumn("源术语", required=True),
                "proposed_target": st.column_config.TextColumn("建议译名"),
                "target": st.column_config.TextColumn("目标译名"),
                "preferred": st.column_config.TextColumn("首选译名"),
                "forbidden": st.column_config.TextColumn("禁止译名（;分隔）"),
                "behavior": st.column_config.SelectboxColumn(
                    "行为", options=list(_TERM_BEHAVIOR_LABELS.values())),
                "status": st.column_config.SelectboxColumn(
                    "状态", options=list(_TERM_STATUS_LABELS.values())),
                "domain": st.column_config.TextColumn("领域"),
                "scope": st.column_config.TextColumn("范围"),
                "note": st.column_config.TextColumn("备注"),
                "confidence": st.column_config.NumberColumn(
                    "置信度", min_value=0.0, max_value=1.0, step=0.05),
                "出现次数": st.column_config.NumberColumn("出现次数", disabled=True),
                "上下文": st.column_config.TextColumn("部分上下文", disabled=True),
                "证据": st.column_config.TextColumn("证据", disabled=True),
                "冲突": st.column_config.TextColumn("冲突", disabled=True),
                "payload": st.column_config.TextColumn("payload", disabled=True),
            },
        )

        selected = edited[edited["选择"].fillna(False)] if "选择" in edited.columns \
            else edited.iloc[0:0]
        sel_ids = [str(x) for x in selected["id"].tolist() if str(x)]

        c1, c2, c3 = box.columns(3)
        if c1.button("保存草稿", key=f"gs_{active}", width="stretch"):
            core.save_glossary_draft(
                active, _merge_edited_entries(entries, _df_to_entries(edited)))
            st.rerun()
        if c2.button("锁定选中术语", disabled=not sel_ids, key=f"gl_{active}",
                          width="stretch"):
            core.set_glossary_entry_status(active, sel_ids, "locked")
            st.rerun()
        if c3.button("拒绝选中术语", disabled=not sel_ids, key=f"gr_{active}",
                          width="stretch"):
            core.set_glossary_entry_status(active, sel_ids, "rejected")
            st.rerun()

        c4, c5, c6 = box.columns(3)
        if c4.button("冻结术语表并继续翻译", key=f"gf_{active}",
                          width="stretch"):
            core.freeze_glossary(
                active, entries=_merge_edited_entries(entries, _df_to_entries(edited)),
                frozen_by="用户")
            st.session_state["pending_continue_job"] = active
            st.rerun()
        if c5.button("跳过冻结并翻译", key=f"gb_{active}",
                          width="stretch"):
            core.save_glossary_draft(
                active, _merge_edited_entries(entries, _df_to_entries(edited)))
            core.bypass_freeze(active)
            st.session_state["pending_continue_job"] = active
            st.rerun()
        if c6.button("开始翻译", disabled=not (frozen or bypassed),
                     key=f"gt_{active}", width="stretch"):
            st.session_state["pending_continue_job"] = active
            st.rerun()
        if frozen and not bypassed:
            if box.button("返回修改（解除冻结）", key=f"gu_{active}",
                          width="stretch"):
                core.unfreeze_glossary(active)
                st.rerun()
        if not frozen and not bypassed:
            box.caption("翻译未开始：请先「冻结术语表并继续翻译」，"
                       "或选择跳过冻结（快速模式）。")

# ================= 任务工作区（唯一工作区表面）=================
# 所有可达视图都在上面提前 st.stop()，工作区统一走这里的 compact shell。
# 旧的「资产与交付 / 文档上下文 / 研究报告（专用）」渲染面已按蓝图 §9 删除：
# 它会把工作区里每一个任务的资产面板、审校队列和报告渲染到同一页，是纯粹的
# 回归风险。回归防线见 tests/ui_console_test.py。
if app_view == "workspace":
    live_status = core.get_job_runtime_status(active).get("status") if active else None
    if live_status in {"resume_requested", "queued", "starting", "running",
                       "waiting_external", "cancelling"}:
        _render_live_workspace(active)
    else:
        _render_workspace_shell(active, core.load_job_state(active) if active else None)
    _render_flashes()
    st.stop()
