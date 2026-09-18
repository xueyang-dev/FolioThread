# 全量回归报告 — Project Center / Inbox 信息架构改造

运行时间：2026-09-17 22:14 起，总耗时 106m48s（GMT+3）  
分支：`feat/phase3-5-ux-closure`  
命令：`venv/bin/python scripts/run_regression.py --tsv …`（逐文件串行；内部对 pytest 风格调
`python -m pytest <file>`，对脚本式调 `python <file>`）

## 统计口径

`tests/` 里混了**两类**测试，统计时必须分开报，否则会得出"63 个文件"这种错误结论
（`app_boot_test.py` 会被同时算进 pytest 与 smoke 两边）：

| 类别 | 数量 | 跑法 | 结果 |
| --- | --- | --- | --- |
| 测试文件总数 | **62** | — | — |
| ├ pytest 风格 | **61** | `venv/bin/python -m pytest <file> -q --no-header -p no:cacheprovider` | **874 passed / 0 failed / 0 skipped / 0 xfailed** |
| └ 脚本式 smoke | **1** | `venv/bin/python tests/app_boot_test.py` | passed（`AppTest 启动测试通过 ✅`） |
| 有效失败 | **0** | — | — |

`tests/app_boot_test.py` 是**脚本式**测试（`def main()` + `if __name__ == "__main__"`），
没有 `def test_*`，pytest 跑它退出码为 5（"未收集到任何测试"）—— 那是**预期**，不是失败，
也不该被改写成 pytest 风格：它提供的是"整个应用能否起来"的**单点**信号，拆成一堆用例反而丢掉它。

## Runner 如何区分这两类

`scripts/run_regression.py` 按**文件内容**分类，不写死文件名：

```
正则 ^(def test_|class Test)      → pytest-style → python -m pytest <file> -q --no-header -p no:cacheprovider
'__name__ == "__main__"'          → script-style → python <file>
两者都没有                         → 仍按 pytest-style（收集为空会以退出码 5 暴露出来，不被静默跳过）
```

重新生成本报告：

```bash
venv/bin/python scripts/run_regression.py --tsv docs/ui-audit/19-project-center-inbox/regression-summary.tsv
```

## 结论

| 指标 | 值 |
| --- | --- |
| pytest 用例 | **874 passed / 0 failed / 0 skipped / 0 xfailed** |
| 有效失败文件 | **0** |
| 总耗时 | 106m48s（逐文件独立进程，串行） |

## 为什么逐文件跑

本项目 Streamlit `AppTest` 单文件内会构建完整应用树，多文件串在一个 pytest 进程里会撞内存峰值
被 SIGTERM 137 杀掉 —— 那样得到的"失败"是假阳性。逐文件独立进程天然规避，且单文件失败不污染
后续结果。

## 环境陷阱：固定名 basetemp 会让"第二次跑"整片报错

受限环境（WorkBuddy 的 `sitecustomize` shim）把 Python 的文件操作代理给宿主，并把
`mkdir(exist_ok=True)` 的 `EEXIST` 抛成**致命错误**。pytest 的 basetemp 恰好是固定名
`$TMPDIR/pytest-of-<user>`：它一旦存在，后续每个 pytest 进程都会在 setup 阶段整片报错
（退出码 1 且**没有** "N passed" 汇总行）。典型症状是同一批测试"第一次跑全绿、第二次 26 个
文件报错"—— 与代码无关。

实测证据（修复前）：

```
$ TMPDIR=<全新目录> pytest tests/style_profile_test.py -q      # 6 passed
$ TMPDIR=<同一目录> pytest tests/style_profile_test.py -q      # 5 passed, 1 error
E  PermissionError: EEXIST: file already exists, mkdir '.../folio-regression-tmp/pytest-of-unknown'
```

`scripts/run_regression.py` 因此**为每个测试文件分配一个全新的私有临时目录**，并把 `TMPDIR` 与
`--basetemp` 都指到它 —— basetemp 永不撞已存在路径，调用方也不需要自己设 `TMPDIR`。

同一个 shim 还会让 AppTest 类测试明显变慢（本次全量 106m48s，而首次报告时是 5m44s；纯逻辑测试的
pytest **内部**耗时不变，可据此区分"环境慢"与"代码回归"）。

## 本次 cleanup 直接触及的面（全部通过）

| 文件 | 类别 | 耗时 | 结果 |
| --- | --- | --- | --- |
| `inbox_project_density_test.py` | pytest | 358s | 20 passed |
| `project_task_navigation_test.py` | pytest | 1537s | 85 passed |
| `project_context_hierarchy_test.py` | pytest | 345s | 18 passed |
| `project_memory_test.py` | pytest | 307s | 45 passed |
| `project_lifecycle_test.py` | pytest | 16s | 18 passed |
| `project_detail_visual_system_test.py` | pytest | 523s | 28 passed |
| `project_overview_structure_test.py` | pytest | 347s | 18 passed |
| `task_overview_ui_test.py` | pytest | 218s | 12 passed |
| `ui_console_test.py` | pytest | 386s | 10 passed |
| `phase35_workspace_view_test.py` | pytest | 5s | 8 passed |
| `app_boot_test.py` | script | 37s | exit=0 |

清理本身只删除**从未被 markup 生成**的 key 的样式、以及已被同权重后置规则整条覆盖的声明，
不触及任何存活的选择器；另加 `test_project_row_rule_holds_only_the_overlay_anchor`
锁住清理后唯一承重的 `position: relative`（它是整卡点击层的定位锚点）。

## 全量逐文件结果

| 退出码 | 文件 | 类别 | 耗时 | 用例 |
| --- | --- | --- | --- | --- |
| 0 | `academic_writer_outline_test.py` | pytest | 4s | 2 passed |
| 0 | `agent_inspector_ui_test.py` | pytest | 95s | 6 passed |
| 0 | `app_boot_test.py` | script | 37s | exit=0 |
| 0 | `brand_assets_test.py` | pytest | 7s | 10 passed |
| 0 | `case_portfolio_test.py` | pytest | 6s | 23 passed |
| 0 | `case_provenance_test.py` | pytest | 8s | 4 passed |
| 0 | `context_knowledge_ui_test.py` | pytest | 61s | 4 passed |
| 0 | `delivery_builder_ui_test.py` | pytest | 110s | 4 passed |
| 0 | `delivery_review_test.py` | pytest | 37s | 1 passed |
| 0 | `delivery_snapshot_test.py` | pytest | 86s | 10 passed |
| 0 | `finalization_workspace_test.py` | pytest | 38s | 6 passed |
| 0 | `gui_launcher_test.py` | pytest | 5s | 5 passed |
| 0 | `history_library_test.py` | pytest | 93s | 32 passed |
| 0 | `inbox_project_density_test.py` | pytest | 358s | 20 passed |
| 0 | `language_assets_workspace_test.py` | pytest | 443s | 39 passed |
| 0 | `legacy_case_recovery_test.py` | pytest | 5s | 11 passed |
| 0 | `legacy_literature_recovery_test.py` | pytest | 5s | 3 passed |
| 0 | `literature_upload_test.py` | pytest | 5s | 2 passed |
| 0 | `mti_finalization_fixture_test.py` | pytest | 5s | 1 passed |
| 0 | `phase35_task_policy_ui_test.py` | pytest | 66s | 2 passed |
| 0 | `phase35_workspace_view_test.py` | pytest | 5s | 8 passed |
| 0 | `phase3_review_runtime_compat_test.py` | pytest | 8s | 5 passed |
| 0 | `phase3_workbench_ui_test.py` | pytest | 254s | 13 passed |
| 0 | `phase3_workbench_view_test.py` | pytest | 5s | 13 passed |
| 0 | `project_context_hierarchy_test.py` | pytest | 345s | 18 passed |
| 0 | `project_detail_visual_system_test.py` | pytest | 523s | 28 passed |
| 0 | `project_lifecycle_test.py` | pytest | 16s | 18 passed |
| 0 | `project_memory_test.py` | pytest | 307s | 45 passed |
| 0 | `project_overview_structure_test.py` | pytest | 347s | 18 passed |
| 0 | `project_task_navigation_test.py` | pytest | 1537s | 85 passed |
| 0 | `provider_exchange_modes_test.py` | pytest | 10s | 8 passed |
| 0 | `recovery_ui_test.py` | pytest | 31s | 1 passed |
| 0 | `red_team_acceptance_test.py` | pytest | 41s | 18 passed |
| 0 | `report_template_test.py` | pytest | 14s | 30 passed |
| 0 | `report_workspace_test.py` | pytest | 220s | 11 passed |
| 0 | `revision_case_eligibility_test.py` | pytest | 5s | 11 passed |
| 0 | `runtime_eval_test.py` | pytest | 9s | 1 passed |
| 0 | `runtime_quality_regression_test.py` | pytest | 9s | 11 passed |
| 0 | `runtime_resume_ui_test.py` | pytest | 45s | 2 passed |
| 0 | `runtime_state_test.py` | pytest | 19s | 14 passed |
| 0 | `runtime_status_test.py` | pytest | 10s | 1 passed |
| 0 | `scenario_gate_test.py` | pytest | 84s | 12 passed |
| 0 | `segment_navigation_test.py` | pytest | 235s | 11 passed |
| 0 | `semantic_repair_test.py` | pytest | 5s | 7 passed |
| 0 | `smoke_test.py` | pytest | 22s | 28 passed |
| 0 | `stage2_dependency_test.py` | pytest | 9s | 8 passed |
| 0 | `stage3_case_review_test.py` | pytest | 11s | 7 passed |
| 0 | `stage4_compliance_test.py` | pytest | 8s | 25 passed |
| 0 | `stage5_rendered_qa_test.py` | pytest | 11s | 7 passed |
| 0 | `stage6_anonymous_mti_regression_test.py` | pytest | 11s | 10 passed |
| 0 | `style_profile_test.py` | pytest | 8s | 6 passed |
| 0 | `synthetic_cases_test.py` | pytest | 9s | 22 passed |
| 0 | `task_overview_state_test.py` | pytest | 5s | 35 passed |
| 0 | `task_overview_ui_test.py` | pytest | 218s | 12 passed |
| 0 | `terminology_governance_test.py` | pytest | 36s | 32 passed |
| 0 | `translation_core_phase2_test.py` | pytest | 9s | 10 passed |
| 0 | `translation_core_test.py` | pytest | 5s | 25 passed |
| 0 | `translation_planner_test.py` | pytest | 5s | 32 passed |
| 0 | `translation_runtime_test.py` | pytest | 12s | 27 passed |
| 0 | `translation_workbench_test.py` | pytest | 11s | 3 passed |
| 0 | `translation_workbench_ui_test.py` | pytest | 41s | 1 passed |
| 0 | `ui_console_test.py` | pytest | 386s | 10 passed |

共 **62** 行 = 62 个测试文件。退出码列中 script-style 行是 `python <file>` 的退出码，
pytest-style 行是 pytest 的退出码；两者均为 0。
