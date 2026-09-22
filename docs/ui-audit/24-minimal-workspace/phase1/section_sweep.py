"""一次性扫描：所有 workspace_section 在新工具栏下都能渲染。"""
from pathlib import Path
import sys, tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
import core

SECTIONS = ["translation", "terms", "review", "cases", "report", "qa", "delivery"]
JOBS = ["ui-audit-clean", "ui-audit-report-available", "ui-audit-new-untranslated",
        "ui-audit-stale", "ui-audit-multiple"]

tmp = Path(tempfile.mkdtemp())
core.OUTPUT_DIR = ROOT / "outputs"      # 只读真实 fixture
bad = []
for job in JOBS:
    state = core.load_job_state(job)
    if state is None:
        print("skip (no state)", job); continue
    for section in SECTIONS:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
        at.run()
        at.session_state["active_job_id"] = job
        at.session_state["app_view"] = "workspace"
        at.session_state["workspace_mode"] = True
        at.session_state["workspace_section"] = section
        at.run()
        if at.exception:
            bad.append((job, section, str(at.exception)[:200]))
            print("EXC", job, section, str(at.exception)[:160])
        else:
            page = "\n".join(str(i.value) for i in at.markdown)
            details = [e.label for e in at.expander]
            print(f"ok  {job:<28} {section:<12} details={('任务详情' in details)} toolbar_head={'tp-workspace-toolbar-head' in page}")
print("\nBAD:", bad if bad else "none")
