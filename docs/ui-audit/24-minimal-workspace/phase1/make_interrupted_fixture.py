#!/usr/bin/env python3
"""为 24-minimal-workspace 的第一阶段视觉验证补一个**真正中断**的任务。

为什么需要它：`scripts/ui_audit_fixtures.py` 只产出两种运行状态
（`completed` / `idle_incomplete`），所以"运行区在中断态长什么样"一直没有
截图证据——上一轮 `audit.js` 打开 `audit-translation-in-progress` 时，
命中的其实是 `ui-audit-in-progress`（它的 runtime_state.json 已被后来的
真实运行覆盖成 `completed`），于是"运行区取证"拍到的是一张空图。

本脚本只写 `outputs/ui-audit-interrupted/`，**不触碰**全局翻译记忆
（`ui_audit_fixtures.py` 会替换 `outputs/translation_memory.json`，这里刻意
不走那条路），也不调用任何付费模型。

用法：
    venv/bin/python docs/ui-audit/24-minimal-workspace/phase1/make_interrupted_fixture.py
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import core                                                    # noqa: E402
import ui_audit_fixtures as fx                                 # noqa: E402

JOB_ID = "ui-audit-interrupted"
FILENAME = "audit-interrupted-run.docx"


def build():
    # 业务状态：4 段里只有 2 段有译文 → 「业务未完成」，运行区才有话可说。
    state = fx._base(JOB_ID, FILENAME, 4, review_required=False)
    state.update({
        "p2_done": False,
        "pairs": fx._pairs(JOB_ID, 2),
        "stage": "TRANSLATING",
        "filename": FILENAME,
    })
    # 运行状态：worker 已退出、进度停在 2/4。`interrupted` 不在
    # `RUNTIME_ACTIVE_STATUSES` 里，`get_job_runtime_status` 不会再改写它，
    # 因此这里写的值就是界面会读到的值。
    runtime = {
        "status": "interrupted",
        "phase": "interrupted",
        "phase_label": "双语翻译与术语严格注入…（批次 2/4）",
        "started_at": fx.FIXED_AT,
        "operation_started_at": fx.FIXED_AT,
        # 心跳故意停在很旧的时间：真实中断就是"有启动、没有后续心跳"。
        "last_heartbeat_at": "2026-09-01T08:16:00+03:00",
        "last_progress_at": "2026-09-01T08:17:00+03:00",
        "completed_units": 2,
        "total_units": 4,
        "overall_progress": 0.5,
        "operation": "translating",
        "operation_id": "translating",
        "operation_label": "双语翻译与术语严格注入…（批次 2/4）",
        "stage": "TRANSLATING",
        "stage_id": "TRANSLATING",
        "last_event": "上次运行的进程已退出（应用被关闭或中断），翻译线程随之终止；"
                      "中断时正在：双语翻译与术语严格注入…（批次 2/4）；"
                      "已完成 2/4 段，可从断点继续",
        "worker": {"owner_pid": None, "worker_id": None,
                   "lease_expires_at": None},
        "error": None,
        "cancel_requested": False,
    }
    fx._save(JOB_ID, state, runtime=runtime)
    return core.build_job_runtime_view(JOB_ID, core.load_job_state(JOB_ID))


def main():
    fx.OUTPUT = fx.OUTPUT          # 只写 outputs/，不落任何其它目录
    view = build()
    print(json.dumps({
        "job_id": JOB_ID,
        "runtime_status": view.get("runtime_status"),
        "status_label": view.get("status_label"),
        "progress": view.get("progress"),
        "available_actions": view.get("available_actions"),
        "primary_action": view.get("primary_action"),
        "detail": view.get("detail"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
