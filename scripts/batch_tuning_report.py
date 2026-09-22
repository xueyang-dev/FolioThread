#!/usr/bin/env python3
"""批次大小调优报告：先离线算批次结构，再用真实 provider 做**有界**实测。

背景：长文档的耗时主要来自"批次数 × 每次调用延迟"。批次由
`BATCH_SIZE` 与 `TRANSLATION_MAX_BATCH_CHARS` 决定，而这两个值此前是写死的。
本脚本回答两个问题：

1. **离线**（不花钱）：给定文档与候选配置，各会产生多少批、单段批有几个。
2. **实测**（`--live K`）：对每种配置实际调用 K 个批次，测每次调用延迟、返回项数
   是否匹配、以及按时延投影的总耗时。

**这个脚本不测翻译质量。** 它只测"批次变大后是否更慢/更容易出错"。质量要用
`eval/` 的盲评流程评估。

用法：

    # 只看批次结构（免费）
    python scripts/batch_tuning_report.py --state outputs/<job_id>/state.json

    # 加做真实调用（默认每种配置 4 个批次，注意会产生 API 费用）
    python scripts/batch_tuning_report.py --state outputs/<job_id>/state.json --live 4
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core  # noqa: E402

CANDIDATES = ((4, 2400), (6, 4800), (8, 6400))


def load_provider_config() -> dict:
    """读取本机已保存的 provider 配置（`outputs/provider_config.json`）。"""
    path = core.OUTPUT_DIR / "provider_config.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def batch_structure(paragraphs, units, batch_size, max_chars):
    batches = core.make_batches(paragraphs, batch_size=batch_size,
                                max_chars=max_chars, semantic_units=units)
    sizes = [len(batch) for batch in batches]
    return {
        "batch_size": batch_size,
        "max_chars": max_chars,
        "batches": batches,
        "batch_count": len(batches),
        "mean_segments": sum(sizes) / len(sizes) if sizes else 0.0,
        "max_segments": max(sizes) if sizes else 0,
        "single_segment_batches": sum(1 for size in sizes if size == 1),
        "total_chars": sum(len(p) for p in paragraphs),
    }


def glossary_text_from_state(state) -> str:
    """用任务自己的术语表拼出与生产接近的固定前缀。

    生产提示词里有一段固定长度的前缀（术语表 + 风格规则 + 上下文包）。只测裸批次
    会低估大批次的好处——因为固定前缀的边际成本与批次大小无关。这里带上真实术语表，
    让 A/B 更接近实际。
    """
    entries = state.get("glossary_frozen", {}).get("entries")         if isinstance(state.get("glossary_frozen"), dict) else None
    entries = entries or state.get("glossary") or []
    lines = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # 生产提示词里注入的是"非拒绝"的条目（locked 优先，provisional 作为
        # 建议性提示也会带上），因此这里排除 rejected 而不是只留 locked。
        if str(entry.get("status") or "") == "rejected":
            continue
        source = str(entry.get("source") or "").strip()
        target = str(entry.get("preferred") or entry.get("target") or "").strip()
        if source and target:
            lines.append(f"{source} -> {target}")
    return "\n".join(lines)


def live_probe(structure, provider_cfg, sample_batches, glossary_text="",
               style_rules=""):
    """对前 sample_batches 个批次做真实调用，返回时延与协议正确性。"""
    provider = str(provider_cfg.get("provider") or "")
    model = str(provider_cfg.get("model") or "")
    api_key = str(provider_cfg.get("api_key") or "")
    base_url = str(provider_cfg.get("base_url") or "")
    if not (provider and model and api_key):
        raise SystemExit("[错误] 缺少 provider/model/api_key，无法实测。")

    core.set_llm_base_url(base_url or None)
    latencies, failures = [], 0
    try:
        for batch in structure["batches"][:sample_batches]:
            started = time.monotonic()
            try:
                targets = core.translate_batch(
                    batch, [], [], glossary_text, style_rules, "简体中文",
                    provider, api_key, model)
                ok = len(targets) == len(batch) and all(
                    str(t or "").strip() for t in targets)
            except Exception as exc:  # 协议错误/超时都算失败
                ok, targets = False, []
                print(f"    ! 批次失败：{type(exc).__name__}: {str(exc)[:120]}")
            elapsed = time.monotonic() - started
            latencies.append(elapsed)
            failures += 0 if ok else 1
            print(f"    - {len(batch)} 段：{elapsed:5.1f}s "
                  f"{'OK' if ok else '失败'}")
    finally:
        core.set_llm_base_url(None)

    mean = statistics.mean(latencies) if latencies else 0.0
    return {
        "samples": len(latencies),
        "failures": failures,
        "mean_seconds": mean,
        "median_seconds": statistics.median(latencies) if latencies else 0.0,
        "projected_total_seconds": mean * structure["batch_count"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", type=Path,
                        help="任务 state.json（含 paras 与 semantic_units）")
    parser.add_argument("--no-glossary", action="store_true",
                        help="实测时不带任务术语表（默认带上，贴近生产提示词）")
    parser.add_argument("--live", type=int, default=0, metavar="K",
                        help="每种配置实测 K 个批次（会产生真实 API 调用）")
    parser.add_argument("--candidates", default="",
                        help="自定义候选，形如 4x2400,6x4800")
    args = parser.parse_args(argv)

    if args.candidates:
        candidates = tuple(
            (int(item.split("x")[0]), int(item.split("x")[1]))
            for item in args.candidates.split(",") if item.strip())
    else:
        candidates = CANDIDATES

    if args.state:
        state = json.loads(args.state.read_text(encoding="utf-8"))
        paragraphs = state.get("paras") or []
        units = state.get("semantic_units") or state.get("section_digests") or None
        label = args.state.parent.name
    else:
        parser.error("需要 --state 指向任务 state.json（用它取真实段落）")

    if not paragraphs:
        parser.error("该任务没有段落（paras 为空）")

    lengths = sorted(len(p) for p in paragraphs)
    print(f"文档：{label} · {len(paragraphs)} 段 · {sum(lengths):,} 字符 · "
          f"段落中位 {lengths[len(lengths)//2]} / 最长 {max(lengths)}")
    print(f"语义单元：{len(units) if units else 0} 个（批次不跨单元）\n")

    structures = [batch_structure(paragraphs, units, bs, mc)
                  for bs, mc in candidates]
    baseline = structures[0]
    print(f"{'batch':>6} {'max_chars':>10} {'批次数':>7} {'平均段/批':>9} "
          f"{'单段批':>7} {'相对':>7}")
    for item in structures:
        delta = (item["batch_count"] / baseline["batch_count"] - 1) * 100
        marker = "（基准）" if item is baseline else f"{delta:+.0f}%"
        print(f"{item['batch_size']:>6} {item['max_chars']:>10} "
              f"{item['batch_count']:>7} {item['mean_segments']:>9.2f} "
              f"{item['single_segment_batches']:>7} {marker:>7}")

    if not args.live:
        print("\n（未做真实调用；加 --live K 可实测每种配置 K 个批次的时延与协议正确性）")
        return 0

    provider_cfg = load_provider_config()
    print(f"\n实测：provider={provider_cfg.get('provider')} "
          f"model={provider_cfg.get('model')}，每种配置 {args.live} 个批次"
          f"（共约 {args.live * len(structures)} 次真实调用）\n")
    print(f"{'batch':>6} {'max_chars':>10} {'样本':>5} {'失败':>5} "
          f"{'中位时延':>9} {'投影总耗时':>11}")
    glossary_text = "" if args.no_glossary else glossary_text_from_state(state)
    if glossary_text:
        print(f"实测提示词带任务术语表（{glossary_text.count(chr(10)) + 1} 条），"
              "贴近生产提示词\n")
    for structure in structures:
        print(f"  {structure['batch_size']}x{structure['max_chars']}:")
        probe = live_probe(structure, provider_cfg, args.live,
                           glossary_text=glossary_text,
                           style_rules=str(state.get("style_rules") or ""))
        print(f"{structure['batch_size']:>6} {structure['max_chars']:>10} "
              f"{probe['samples']:>5} {probe['failures']:>5} "
              f"{probe['median_seconds']:>8.1f}s "
              f"{probe['projected_total_seconds'] / 60:>10.1f}m")
    print("\n注意：投影 = 批次中位时延 × 批次数，不含审校/知识反馈/恢复等开销；"
          "本脚本不评估翻译质量。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
