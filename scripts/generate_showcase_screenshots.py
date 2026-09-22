#!/usr/bin/env python3
"""Generate high-resolution, privacy-clean showcase screenshots of Folith for documentation."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "tmp" / "showcase_outputs"
ASSETS = ROOT / "docs" / "assets"
PORT = 8588

os.environ["FOLITH_OUTPUT_DIR"] = str(OUTPUT)
sys.path.insert(0, str(ROOT))

import core
from transpraxis import translation_core


def setup_showcase_fixtures():
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / ".onboarded").touch()

    # Create a clean project
    project = core.create_project("技术专著本地化", description="面向大模型与开源体系的专业翻译工作区")
    project_id = project["project_id"]

    pairs = [
        {
            "segment_id": "seg-001",
            "source": "The translation workspace preserves source context, terminology rules, and human review history.",
            "target": "翻译工作区完整保留原文上下文、术语规范与人工审校历史。",
            "initial_target": "初译：翻译工作区保留上下文和历史。",
            "reviewed": True,
            "review_status": "reviewed_clean",
            "target_provenance": "reviewed",
        },
        {
            "segment_id": "seg-002",
            "source": "Terminology decisions remain visible and editable throughout the entire localization lifecycle.",
            "target": "术语决策在整个本地化生命周期中对人工审校者保持清晰可见且可随时编辑。",
            "initial_target": "初译：术语决策在整个周期可见。",
            "reviewed": True,
            "review_status": "reviewed_clean",
            "target_provenance": "reviewed",
        },
        {
            "segment_id": "seg-003",
            "source": "Downstream delivery artifacts are verified against structured quality gates before final export.",
            "target": "在最终导出前，下游交付资产将由结构化质量门禁进行全面验证。",
            "initial_target": "初译：交付文件在导出前会验证质量门禁。",
            "reviewed": True,
            "review_status": "reviewed_clean",
            "target_provenance": "reviewed",
        },
        {
            "segment_id": "seg-004",
            "source": "Interrupted long-document translation tasks can seamlessly resume from the last saved breakpoint.",
            "target": "长文档翻译任务中断后，可随时从最近的保存断点无缝恢复继续执行。",
            "initial_target": "初译：中断的任务可以从断点恢复。",
            "reviewed": False,
            "review_status": "not_reviewed",
            "target_provenance": "generated",
        },
    ]

    glossary = [
        {
            "id": "term-01",
            "source": "translation workspace",
            "target": "翻译工作区",
            "preferred": "翻译工作区",
            "status": "locked",
            "domain": "本地化技术",
            "scope": "项目",
            "occurrences": [0],
            "note": "规范产品实体命名",
        },
        {
            "id": "term-02",
            "source": "quality gate",
            "target": "质量门禁",
            "preferred": "质量门禁",
            "status": "locked",
            "domain": "软件工程",
            "scope": "项目",
            "occurrences": [2],
            "note": "保持交付工程概念统一",
        },
        {
            "id": "term-03",
            "source": "localization lifecycle",
            "target": "本地化生命周期",
            "preferred": "本地化生命周期",
            "status": "locked",
            "domain": "本地化流程",
            "scope": "项目",
            "occurrences": [1],
            "note": "标准行业术语",
        },
    ]

    state = core.new_job_state("Agentic Translation Workspace Architecture.docx")
    state.update({
        "p1_done": True,
        "p2_done": True,
        "p3_done": False,
        "report_enabled": False,
        "target_lang": "简体中文",
        "project_id": project_id,
        "paras": [p["source"] for p in pairs],
        "pairs": pairs,
        "glossary": glossary,
        "glossary_frozen": {"version": 1, "entries": glossary, "frozen_at": "2026-09-22T10:00:00+08:00"},
        "document_profile": {
            "display_name": "Agentic Translation Architecture Guide",
            "domain": "计算机科学与人工智能",
            "subdomain": "大语言模型与本地化工程",
            "genre": "技术白皮书",
            "audience": "专业本地化工程师与译审专家",
            "register": "正式书面语",
            "style_constraints": "保持专业术语一致性，句式清晰严谨，保留专有名词与技术边界",
        },
        "profile_done": True,
        "translation_core_review_required": True,
        "review_evidence": [],
        "findings": [],
        "human_actions": [],
        "review_stats": {
            "reviewed_segments": 3,
            "batches_reviewed": 1,
            "blocking": 1,
            "actionable": 0,
            "informational": 0,
            "review_failed": 0,
        },
        "has_blocking": True,
        "translation_truth": {
            "authority": "CURRENT_TRANSLATION",
            "version": 1,
            "last_changed_at": "2026-09-22T10:00:00+08:00",
            "last_change": None,
        },
        "provider": "DeepSeek",
        "model": "deepseek-v4-flash",
        "stage": "TRANSLATED",
        "style_rules": "正式技术书面语",
        "delivery_config": core.default_delivery_config(),
    })

    # Add a realistic review finding on segment 4
    fp = translation_core.fingerprint({"segment": 3, "target": pairs[3]["target"]})
    raw_finding = {
        "type": "review",
        "category": "terminology",
        "severity": "blocking",
        "status": "open",
        "segment_id": 3,
        "segment_index": 3,
        "location_key": "term:long-document",
        "entry_id": "term-01",
        "requires_human_confirmation": True,
        "summary": "建议核对长文档断点恢复机制在中文表述中的术语准确性",
        "source_span": "saved breakpoint",
        "target_span": "保存断点",
        "explanation": "技术白皮书中应统一对应 breakpoint 为「检查点」或「断点」，建议与项目术语表保持同步。",
        "recommendation": "可采纳建议译文或保留人工决议，以消除交付风险。",
        "suggested_target": "长文档翻译任务中断后，可随时从最近的保存检查点无缝恢复继续执行。",
        "detector": "Folith Agent Reviewer",
        "confidence": 0.94,
        "review_event_id": "rev-showcase-01",
        "reason": "术语一致性核验",
    }
    normalized = translation_core.normalize_finding(raw_finding, input_fingerprint=fp)
    normalized.update({
        "type": "review",
        "segment_index": 3,
        "review_event_id": "rev-showcase-01",
        "created_at": "2026-09-22T10:00:00+08:00",
    })
    state["findings"].append(normalized)

    core.save_job_state("showcase-job", state)
    core.save_source("showcase-job", b"Folith Architecture Guide Mock Source")
    core.update_runtime_state("showcase-job",
                              status="completed",
                              phase="completed",
                              phase_label="已完成",
                              started_at="2026-09-22T10:00:00+08:00",
                              last_heartbeat_at="2026-09-22T10:00:00+08:00",
                              last_progress_at="2026-09-22T10:00:00+08:00",
                              last_event="showcase")

    print("[OK] Showcase fixtures created in", OUTPUT)


def wait_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def run_screenshot(url: str, out_path: Path, section: str = ""):
    cmd = [
        str(ROOT / "venv" / "bin" / "python"),
        str(ROOT / "scripts" / "ui_screenshot.py"),
        "--url", url,
        "--out", str(out_path),
        "--section", section,
        "--wait-ms", "3500",
    ]
    env = {
        **os.environ,
        "FOLIO_PLAYWRIGHT_CORE": str(Path("~/.hermes/hermes-agent/node_modules/playwright-core").expanduser()),
        "FOLIO_CHROME": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "DEVICE_SCALE_FACTOR": "2",
    }
    subprocess.run(cmd, env=env, check=True)


def main():
    setup_showcase_fixtures()
    ASSETS.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "FOLITH_OUTPUT_DIR": str(OUTPUT)}
    server_cmd = [
        str(ROOT / "venv" / "bin" / "python"),
        "-m", "streamlit", "run", str(ROOT / "app.py"),
        "--server.headless", "true",
        "--server.port", str(PORT),
        "--server.address", "127.0.0.1",
        "--theme.primaryColor", "#004cfd",
        "--theme.textColor", "#131c2e",
        "--browser.gatherUsageStats", "false",
    ]

    print(f"Starting Streamlit server on port {PORT} with showcase fixtures...")
    proc = subprocess.Popen(server_cmd, env=env)
    try:
        url = f"http://127.0.0.1:{PORT}"
        if not wait_port(PORT, timeout=40):
            print("Streamlit failed to become ready in time.")
            return 1
        print("Streamlit ready! Capturing screenshots...")

        # 1. Workbench Preview
        wb_path = ASSETS / "workbench-preview.png"
        run_screenshot(url, wb_path, "翻译")

        # 2. Overview Preview
        ov_path = ASSETS / "overview-preview.png"
        run_screenshot(url, ov_path, "概览")

        # 3. Review Preview
        rev_path = ASSETS / "review-preview.png"
        run_screenshot(url, rev_path, "审校")

        # 4. Terms Preview
        terms_path = ASSETS / "assets-preview.png"
        run_screenshot(url, terms_path, "术语")

        # Also replace the leaked audit images in docs/ui-audit/24-minimal-workspace
        audit_dir = ROOT / "docs" / "ui-audit" / "24-minimal-workspace"
        if audit_dir.exists():
            shutil.copyfile(wb_path, audit_dir / "03-workbench-current.png")
            shutil.copyfile(ov_path, audit_dir / "04-overview-current.png")
            shutil.copyfile(terms_path, audit_dir / "05-terms-workbench.png")
            shutil.copyfile(rev_path, audit_dir / "13-review-blocker-workbench.png")
            print("[OK] Replaced legacy leaked audit images in 24-minimal-workspace")

        print("All showcase screenshots successfully generated!")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
