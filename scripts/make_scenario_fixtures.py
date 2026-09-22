"""生成 Folith 三个端到端验收场景的源文档（内容确定性、可重复）。

蓝图 `docs/foliothread-agentic-native-blueprint.md` §8 把发布进度定义为三个
端到端场景，而不是模块数量：

| 场景 | 必须证明 |
| --- | --- |
| 20 页 DOCX | 导入、术语准备、翻译、审校、双语交付可完成 |
| 100 页 PDF | 中断恢复、章节上下文、受影响范围重建可用 |
| 术语密集文档 | 术语确认、TM 复用、独立审校和交付清单可信 |

本脚本把这三个场景的**源文档**变成可重复生成的产物，从而让
`tests/scenario_gate_test.py` 能在离线、无 provider 的情况下运行验收。
仓库不提交二进制 fixture：文档每次由本脚本按固定内容重建。

**确定性边界**：生成过程不使用随机数，产出的**文本内容**逐段一致
（manifest 中每个场景的 `content_sha256` 是内容指纹，可用于验证未漂移）。
但**容器字节不保证一致**：DOCX 的 zip 条目带写入时间戳，PDF 内部有文档
ID 与交叉引用偏移。因此不要用文件 sha256 判断 fixture 是否漂移，
请使用 `content_sha256`。

用法：

    python scripts/make_scenario_fixtures.py --out tmp/scenarios
    python scripts/make_scenario_fixtures.py --out tmp/scenarios --only pdf

生成物：

    scenario-20p.docx            20 页级结构化 DOCX（标题层级 + 正文 + 引用/URL）
    scenario-100p.pdf            100 页 PDF（重复页眉、页码页脚、跨行连字符）
    scenario-terms.docx          术语密集 DOCX
    scenario-terms.glossary.json 与术语密集文档配套的锁定术语表
    fixtures-manifest.json       每个场景的预期结构，供验收断言读取
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:  # PyMuPDF ≥1.24 同时提供新旧两个模块名
    import pymupdf as fitz
except ImportError:  # pragma: no cover - 兼容旧版 PyMuPDF
    import fitz

from docx import Document
from docx.shared import Pt


def content_sha256(lines: list[str]) -> str:
    """内容指纹：只覆盖文本内容，不含容器字节（zip 时间戳 / PDF ID）。"""
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# ================= 确定性语料 =================

# 每个场景的正文由固定句子池按固定顺序组合，不使用随机数：
# 文本内容在任何机器、任何时间都一致（容器字节不保证，见模块 docstring）。
_TOPICS = (
    ("生态恢复与演替", "Ecological restoration and succession"),
    ("土壤碳循环", "Soil carbon cycling"),
    ("林冠结构与光竞争", "Canopy structure and light competition"),
    ("菌根网络与养分转运", "Mycorrhizal networks and nutrient transfer"),
    ("干扰机制与恢复力", "Disturbance regimes and resilience"),
    ("流域尺度水文响应", "Catchment-scale hydrological response"),
)

_SENTENCES = (
    "Recent work on {topic} has shifted from describing static states to "
    "modelling the transitions between them.",
    "Field measurements were collected across {plots} plots during three "
    "consecutive growing seasons.",
    "The observed response was non-linear, which complicates the use of a "
    "single recovery rate.",
    "Earlier studies reported a comparable pattern, although their sampling "
    "design did not isolate the same mechanism.",
    "We therefore treat {topic} as a coupled process rather than a sequence "
    "of independent stages.",
    "We recorded the canopy structure and the understorey composition "
    "separately at each visit.",
    "Where the disturbance regime changed, the trajectories diverged within "
    "two seasons.",
    "These results are consistent with the hypothesis that legacy effects "
    "persist longer than the perturbation itself.",
    "Quantifying that lag requires either longer records or a stronger "
    "assumption about the underlying process.",
)

# 确定性检查会命中的保留项：URL、引用标注、占位符、DOI、邮箱。
# 全部落在 `core.PRESERVE_RE`（core.py:655）覆盖范围内，因此翻译后必须原样回填。
_RESERVED_TOKENS = (
    "See https://example.com/folio/thread for the full protocol.",
    "The framework follows the earlier treatment [12] and its corrigendum [13].",
    "Model output was written to {{artifact_path}} before aggregation.",
    "The dataset is archived under doi 10.1234/folio.2026.001 for inspection.",
    "Correspondence should be addressed to field-team@example.com directly.",
)

_TERM_SENTENCES = (
    "The {term} determines how quickly the system returns to its prior state.",
    "We measured {term} at each site and compared it with the regional mean.",
    "A change in {term} can mask a simultaneous change in the other "
    "components.",
    "Independent estimates of {term} were within the reported uncertainty.",
    "The {term} should not be conflated with the short-term response.",
)

# 术语密集场景的锁定术语（source -> 首选译名 / 禁止译名）
_LOCKED_TERMS = (
    ("ecological succession", "生态演替", ("生态继承",)),
    ("canopy closure", "林冠郁闭", ("冠层关闭",)),
    ("mycorrhizal network", "菌根网络", ("菌根网路",)),
    ("soil respiration", "土壤呼吸", ("土壤呼吸作用率",)),
    ("disturbance regime", "干扰机制", ("扰动政权",)),
)

# 保留专名：用于术语密集场景的 `preserve` 行为（该词不在 PRESERVE_RE 内，
# 因此会按"源语残留"被确定性检查记录为 actionable —— 这是预期行为，由
# tests/scenario_gate_test.py 显式断言，而不是让它在其它场景里变成噪声）。
_PRESERVE_SENTENCE = (
    "The instrument, a LiCOR-7500 analyser, was calibrated before each campaign."
)


# ================= 文本装配 =================


def _body_paragraphs(count: int, *, topic_offset: int = 0) -> list[str]:
    """按固定顺序生成 count 段正文，段落长度在 40–90 词之间。"""
    paragraphs: list[str] = []
    index = 0
    while len(paragraphs) < count:
        title, english = _TOPICS[(index + topic_offset) % len(_TOPICS)]
        sentences = []
        for offset in range(4):
            template = _SENTENCES[(index * 4 + offset) % len(_SENTENCES)]
            sentences.append(template.format(
                topic=english, plots=18 + (index * 7 + offset * 3) % 60))
        if index % 5 == 4:
            # 独立轮转：index % 5 == 4 是固定余数，用 index // 5 才不会退化成同一个 token。
            sentences.append(_RESERVED_TOKENS[(index // 5) % len(_RESERVED_TOKENS)])
        paragraphs.append(" ".join(sentences))
        index += 1
    return paragraphs


def _headings(count: int, *, topic_offset: int = 0) -> list[tuple[str, str]]:
    """生成 (中文标题, 英文标题) 序列，供标题层级与章节划分使用。"""
    return [
        _TOPICS[(index + topic_offset) % len(_TOPICS)] for index in range(count)
    ]


def _section_paragraphs(paragraphs: list[str], section_count: int) -> list[list[str]]:
    """把段落均分到若干个章节，保持顺序。"""
    sections: list[list[str]] = [[] for _ in range(section_count)]
    for index, paragraph in enumerate(paragraphs):
        sections[index % section_count].append(paragraph)
    return sections


# ================= 场景一：20 页 DOCX =================


def build_docx_scenario(
    path: Path, *, sections: int = 8, paragraphs: int = 175,
) -> dict:
    """生成结构化 DOCX：8 个二级标题章节、175 段正文。

    175 段 × 约 63 词 ≈ 11,000 词，在 A4 / 11pt 下约 20 页，与蓝图场景一致。
    """
    headings = _headings(sections)
    body = _body_paragraphs(paragraphs)
    grouped = _section_paragraphs(body, sections)

    document = Document()
    document.add_heading("长文档验收场景：生态恢复的过程与机制", level=0)
    document.add_paragraph(
        "本文件由 scripts/make_scenario_fixtures.py 确定性生成，"
        "用于 Folith 的端到端验收，不包含任何真实研究数据。"
    )
    for index, (title_cn, title_en) in enumerate(headings):
        document.add_heading(f"{index + 1}. {title_cn} / {title_en}", level=1)
        for paragraph in grouped[index]:
            document.add_paragraph(paragraph)
    for section in document.sections:
        for run in section.footer.paragraphs[0].runs or []:
            run.font.size = Pt(9)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))

    words = sum(len(item.split()) for item in body)
    return {
        "kind": "docx",
        "content_sha256": content_sha256(
            [f"{index + 1}. {title_cn} / {title_en}"
             for index, (title_cn, title_en) in enumerate(headings)] + body),
        "path": path.name,
        "sections": sections,
        "paragraphs": paragraphs,
        "words": words,
        "approx_pages": round(words / 550, 1),
        "reserved_tokens": list(_RESERVED_TOKENS),
        "preserve_sentence": _PRESERVE_SENTENCE,
    }


# ================= 场景二：100 页 PDF =================

_RUNNING_HEADER = "Folith Scenario Fixture — Ecological Restoration"
_PDF_BODY_X0 = 72.0          # 正文左边界
_PDF_INDENT = 14.0           # 首行缩进：运行时的段落边界判据
_PDF_LINE_WIDTH = 92         # 每行最大字符数
_PDF_LINE_HEIGHT = 12.5
_PDF_PARAGRAPH_GAP = 6.0


def _wrap_line(text: str, width: int = _PDF_LINE_WIDTH) -> list[str]:
    """按单词边界折行；行尾不切断单词（与真实排版一致）。"""
    lines: list[str] = []
    current = ""
    for word in text.split():
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def build_pdf_scenario(
    path: Path, *, pages: int = 100, paragraphs_per_page: int = 6,
) -> dict:
    """生成 100 页 PDF，带重复页眉、页码页脚和一处跨行连字符。

    版面刻意采用真实排版惯例，使运行时能恢复段落边界：

    - 每段首行缩进 `_PDF_INDENT`：`reconstruct_paragraph_records` 据此判定
      新段落开始（`pdf_ingestion.py:397`）；
    - 行在单词边界折行，因此跨行拼接应当插入空格而不是粘连；
    - 固定位置注入一处 `can-` / `opy` 断词，验证 `_join_text`
      （`pdf_ingestion.py:312`）的去连字符还原；
    - 重复页眉与页码页脚用于验证 `classify_blocks` 的版面噪声剔除。
    """
    paragraphs = _body_paragraphs(pages * paragraphs_per_page)
    hyphen_target = 5 * paragraphs_per_page  # 第 6 页首段，位置可预测

    document = fitz.open()
    cursor = 0
    for page_index in range(pages):
        page = document.new_page(width=595, height=842)  # A4
        page.insert_text((_PDF_BODY_X0, 60), _RUNNING_HEADER, fontsize=8)
        page.insert_text((540, 812), str(page_index + 1), fontsize=8)

        y = 92.0
        for _ in range(paragraphs_per_page):
            if cursor >= len(paragraphs):
                break
            lines = _wrap_line(paragraphs[cursor])
            if cursor == hyphen_target:
                lines = _inject_hyphenation(lines, "canopy")
            for line_index, line in enumerate(lines):
                x = _PDF_BODY_X0 + (_PDF_INDENT if line_index == 0 else 0.0)
                page.insert_text((x, y), line, fontsize=9.5)
                y += _PDF_LINE_HEIGHT
            y += _PDF_PARAGRAPH_GAP
            cursor += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    document.close()

    words = sum(len(item.split()) for item in paragraphs)
    return {
        "kind": "pdf",
        "content_sha256": content_sha256(
            [p.replace("canopy", "can-\nopy", 1) if index == hyphen_target else p
             for index, p in enumerate(paragraphs)]),
        "path": path.name,
        "pages": pages,
        "paragraphs": len(paragraphs),
        "words": words,
        "running_header": _RUNNING_HEADER,
        "hyphenation": {
            "page": hyphen_target // paragraphs_per_page + 1,
            "word": "canopy",
            "joined": "canopy",
        },
    }


def _inject_hyphenation(lines: list[str], word: str) -> list[str]:
    """把包含 `word` 的行拆成 `…can-` / `opy…` 两行，验证去连字符还原。"""
    for index, line in enumerate(lines):
        if word in line.lower():
            position = line.lower().index(word)
            head = line[:position] + word[:3] + "-"   # "can-"
            tail = line[position + 3:]                # "opy …"
            return lines[:index] + [head.rstrip(), tail.lstrip()] + lines[index + 1:]
    return lines


# ================= 场景三：术语密集 DOCX =================


def build_terminology_scenario(
    docx_path: Path, glossary_path: Path, *, paragraphs: int = 90,
) -> dict:
    """生成术语密集 DOCX + 配套锁定术语表。

    每个术语反复出现在多个段落中，用于验证术语注入范围、TM 复用和
    独立审校的术语一致性发现。
    """
    document = Document()
    document.add_heading("术语密集验收场景", level=0)
    document.add_paragraph(
        "本文件由脚本确定性生成，术语密度远高于普通长文档。"
    )

    produced: list[str] = []
    for index in range(paragraphs):
        term, target, forbidden = _LOCKED_TERMS[index % len(_LOCKED_TERMS)]
        template = _TERM_SENTENCES[(index // len(_LOCKED_TERMS)) % len(_TERM_SENTENCES)]
        sentence = template.format(term=term)
        # 前两轮重复同一术语，制造跨段落一致性压力。
        repeat = f" The same {term} was re-measured in the following season."
        paragraph = f"{sentence}{repeat}"
        if index % 23 == 22:
            paragraph = f"{paragraph} {_RESERVED_TOKENS[(index // 23) % len(_RESERVED_TOKENS)]}"
        if index % 29 == 28:
            paragraph = f"{paragraph} {_PRESERVE_SENTENCE}"
        produced.append(paragraph)
        document.add_paragraph(paragraph)

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(docx_path))

    entries = [
        {
            "source": term,
            "target": target,
            "preferred": target,
            "forbidden": list(forbidden),
            "behavior": "translate",
            "status": "locked",
            "domain": "ecology",
            "scope": "document",
            "note": "验收场景锁定术语",
        }
        for term, target, forbidden in _LOCKED_TERMS
    ]
    entries.append({
        "source": "LiCOR-7500 analyser",
        "target": "LiCOR-7500 analyser",
        "preferred": "LiCOR-7500 analyser",
        "forbidden": [],
        "behavior": "preserve",
        "status": "locked",
        "domain": "instrument",
        "scope": "document",
        "note": "仪表专名，保留原文",
    })
    glossary_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    term_hits = sum(paragraph.count(term) for term, _, _ in _LOCKED_TERMS
                    for paragraph in produced)
    words = sum(len(item.split()) for item in produced)
    return {
        "kind": "terms",
        "content_sha256": content_sha256(produced),
        "path": docx_path.name,
        "glossary": glossary_path.name,
        "paragraphs": len(produced),
        "words": words,
        "approx_pages": round(words / 550, 1),
        "terms": [term for term, _, _ in _LOCKED_TERMS],
        "locked_entries": len(entries),
        "term_occurrences": term_hits,
        "preserve_sentence": _PRESERVE_SENTENCE,
        "reserved_tokens": list(_RESERVED_TOKENS),
    }


# ================= 入口 =================


def build_all(out_dir: Path, *, only: set[str] | None = None) -> dict:
    """生成选中场景，返回 manifest（含每个场景的预期结构）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    scenarios: dict[str, dict] = {}

    if only is None or "docx" in only:
        scenarios["docx_20p"] = build_docx_scenario(out_dir / "scenario-20p.docx")
    if only is None or "pdf" in only:
        scenarios["pdf_100p"] = build_pdf_scenario(out_dir / "scenario-100p.pdf")
    if only is None or "terms" in only:
        scenarios["terms_dense"] = build_terminology_scenario(
            out_dir / "scenario-terms.docx", out_dir / "scenario-terms.glossary.json")

    manifest = {
        "generator": "scripts/make_scenario_fixtures.py",
        "blueprint": "docs/foliothread-agentic-native-blueprint.md#8",
        "deterministic": True,
        "scenarios": scenarios,
    }
    (out_dir / "fixtures-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("tmp/scenarios"),
                        help="输出目录（默认 tmp/scenarios）")
    parser.add_argument("--only", choices=["docx", "pdf", "terms"], action="append",
                        help="只生成指定场景，可重复；默认全部")
    args = parser.parse_args(argv)

    manifest = build_all(args.out, only=set(args.only) if args.only else None)
    for name, info in manifest["scenarios"].items():
        size = (args.out / info["path"]).stat().st_size
        pages = info.get("pages") or info.get("approx_pages") or "-"
        print(f"  {name:12s} {info['path']:26s} "
              f"{info['paragraphs']:5d} 段  ~{pages} 页  {size / 1024:.0f} KB")
    print(f"manifest -> {args.out / 'fixtures-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
