#!/usr/bin/env python3
"""在隔离的 OUTPUT_DIR 里跑一份工作台，供浏览器交互实测使用。

为什么需要它：真实 `outputs/` 里是用户的任务与交付快照，浏览器实测会往里写测试任务
（编辑译文会真的落盘）。所以先把 `core.OUTPUT_DIR` 指到一个临时目录、写入一个已知
夹具任务，再以 `__main__` 方式执行 `app.py`。

用法（端口随便挑一个没占用的）：

    streamlit run docs/ui-audit/25-save-flow/serve_fixture.py \\
        --server.port 8505 --server.address 127.0.0.1

脚本会在 stdout 打印 `FIXTURE_JOB_ID` 与 `FIXTURE_OUTPUT_DIR`，与 `audit.js` 里的
默认值一致，因此通常不需要额外传参。

**关键陷阱**：Streamlit 每次 rerun 都会重跑这个入口脚本。如果在这里用模块级
`tempfile.mkdtemp()`，那么**每一次交互都会换一个新的 OUTPUT_DIR**——夹具看起来被
"重置"了，保存写入的是一个刚创建的空目录，于是"保存成功但刷新后内容不见"。
所以临时目录必须按**进程**创建一次（`st.cache_resource`），夹具也只在状态文件
不存在时播种一次。
"""
import runpy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import core  # noqa: E402
import streamlit as st  # noqa: E402

JOB_ID = "saveflowbrowser01"
SEGMENTS = 6


@st.cache_resource
def _isolated_output_dir():
    """每个 Streamlit 进程一个私有临时目录（跨 rerun 复用）。"""
    path = Path(tempfile.mkdtemp(prefix="folio-save-flow-"))
    path.mkdir(parents=True, exist_ok=True)
    return path


OUTPUT_DIR = _isolated_output_dir()
core.OUTPUT_DIR = OUTPUT_DIR


def _fixture_state():
    state = core.new_job_state("browser-save-flow.pdf")
    pairs = []
    for index in range(SEGMENTS):
        pairs.append({
            "source": f"Source segment {index + 1} for the browser save-flow audit.",
            "target": f"待审译文 {index + 1}",
            "initial_target": f"待审译文 {index + 1}",
            # 前两段已审校：用来验证"切筛选不丢稿"（筛掉未审校的段落）。
            "reviewed": index in {0, 1},
            "from_tm": False,
            "glossary_entry_ids": [],
        })
    state.update(
        p1_done=True,
        p2_done=True,
        paras=[pair["source"] for pair in pairs],
        pairs=pairs,
        review_stats={"reviewed_segments": 2},
        delivery_status="draft",
    )
    return state


if not (OUTPUT_DIR / JOB_ID / "state.json").is_file():
    core.save_source(JOB_ID, b"browser save-flow audit fixture")
    core.save_job_state(JOB_ID, _fixture_state())

# 只在**新会话**第一次跑时落到工作台的这个任务上（app.py 只在 key 缺失时填默认值，
# 所以必须自己判一次，否则每次 rerun 都会把用户切走的页面拉回来）。
if not st.session_state.get("_save_flow_audit_booted"):
    st.session_state["_save_flow_audit_booted"] = True
    st.session_state["active_job_id"] = JOB_ID
    st.session_state["app_view"] = "workspace"
    st.session_state["workspace_mode"] = True
    st.session_state["workspace_section"] = "translation"

print(f"FIXTURE_JOB_ID {JOB_ID}", flush=True)
print(f"FIXTURE_OUTPUT_DIR {OUTPUT_DIR}", flush=True)

# 再把目录写到一个**固定位置**，让 audit.js / runtime_edit_audit.js 能自动拿到它。
# 为什么不能靠 `ls -dt $TMPDIR/folio-save-flow-*` 猜：同一台机器上留着历次运行的目录，
# 而本次进程的目录要到**第一个会话连上**才被创建（`st.cache_resource` 在脚本首次执行
# 时才跑），所以"最新的那个"既可能不是本次的、也可能还不存在。固定位置没有这个歧义。
_HANDOFF = ROOT / ".audit" / "fixture-output-dir.txt"
_HANDOFF.parent.mkdir(parents=True, exist_ok=True)
_HANDOFF.write_text(str(OUTPUT_DIR), encoding="utf-8")

runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
