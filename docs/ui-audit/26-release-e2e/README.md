# 26 · 发布前新任务端到端验收

日期：2026-09-21
对象：`tests/release_e2e_acceptance_test.py`
环境：隔离的 pytest `tmp_path`，确定性 provider 替身

这份验收记录验证的是任务状态、段落身份、交付资产和恢复行为是否贯通，
不是对真实模型译文质量的判断。流程从一份含页码噪声的 DOCX 开始，故意让第一轮
翻译中断，然后重新打开任务继续：

1. DOCX 导入并保留可排除的页码行；
2. 翻译中断后从阶段一 checkpoint 恢复；
3. 排除页码、拆分一段、再合并；
4. 人工修改一段并执行独立审校；
5. 生成纯译文、双语文档、排除清单和交付 manifest；
6. 冻结 `v1` 交付快照。

```text
$ venv/bin/python -m pytest tests/release_e2e_acceptance_test.py -q
1 passed
```

交付包中的 `excluded_segments.md` / `excluded_segments.json` 证明被排除的源文没有
静默消失；`delivery_status=final` 和 `latest_delivery_snapshot_version=1` 证明最后
一步确实走过人工交付冻结。真实 provider、浏览器视觉、无障碍和原 DOCX 格式保真
仍由各自的验收项负责。
