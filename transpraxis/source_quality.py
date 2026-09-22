"""Deterministic source-admission checks for OCR output.

The PDF cleaner is allowed to repair text, but it must not turn an isolated
OCR fragment into a translation request.  This module is deliberately a
conservative quarantine gate: it never deletes source text and it never tries
to guess a replacement.  It only identifies short, structurally suspicious
items so the translation stage can keep them as source text and require a
human source check.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from .textual import has_textual_content


VERSION = 1

_WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019\u2013\u2014-][A-Za-z]+)?")
_TERMINAL_RE = re.compile(r"[.!?\u2026:;,\)\]\}\u00bb\u201d\u2019\"']+$")
_SPACED_DASH_RE = re.compile(
    r"\b[A-Za-z]{1,4}\s+[-\u2013\u2014]\s+[A-Za-z]{1,4}\b"
)
_IDENTIFIER_RE = re.compile(
    r"^(?:@\S+|(?:https?://|www\.)\S+|\S+@\S+|[A-Za-z0-9.-]+\.\w{2,})$",
    re.IGNORECASE,
)


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def _reasons(text: str) -> List[str]:
    value = _normalise(text)
    if not value or not has_textual_content(value):
        return []
    # Handles page numbers/isolated OCR numerals without treating numbers in a
    # normal sentence as suspicious.
    if re.fullmatch(r"\d{1,4}", value):
        return ["孤立数字行，疑似页码或批注"]
    # Social handles, URLs and domains are legitimate short front/back-matter
    # items and should not be sent through this fragment gate.
    if _IDENTIFIER_RE.fullmatch(value):
        return []
    words = _WORD_RE.findall(value)
    if not words or len(value) > 36 or _TERMINAL_RE.search(value):
        return []
    reasons: List[str] = []
    if value[:1].islower() and len(words) <= 4:
        reasons.append("小写且未闭合的短片段")
    if len(words) == 1 and len(value) <= 12 and value.islower():
        reasons.append("孤立短词")
    # OCR often turns handwriting or a damaged line into a fake hyphenated
    # phrase.  This is a strong signal when the whole item is short.
    if _SPACED_DASH_RE.search(value):
        reasons.append("短片段含异常空格连字符")
    return reasons


def audit_source_segments(paragraphs: Sequence[str]) -> Dict[str, Any]:
    """Return a JSON-safe source-admission report.

    The report is intentionally independent of a language dictionary.  It is
    used as a safety gate for arbitrary source languages, so a token is never
    rejected merely because it is unfamiliar.  A flagged item remains in the
    source list and must be handled explicitly by the translation stage.
    """
    values = [_normalise(item) for item in (paragraphs or [])]
    candidates: List[Dict[str, Any]] = []
    for index, text in enumerate(values):
        reasons = _reasons(text)
        if reasons:
            candidates.append({
                "segment_index": index,
                "text": text,
                "reasons": reasons,
                "severity": "blocking",
            })

    # Adjacent suspicious items are stronger evidence of a broken layout or
    # OCR layer than a single short heading.  Keep the fact in the report so
    # the UI/review log can explain why the gate fired.
    clusters: List[List[int]] = []
    current: List[int] = []
    for item in candidates:
        index = int(item["segment_index"])
        if current and index != current[-1] + 1:
            clusters.append(current)
            current = []
        current.append(index)
    if current:
        clusters.append(current)
    cluster_by_index = {
        index: cluster for cluster in clusters for index in cluster
    }
    for item in candidates:
        cluster = cluster_by_index.get(int(item["segment_index"]), [])
        item["adjacent_flagged_segments"] = len(cluster)
        if len(cluster) >= 2 and "相邻可疑片段" not in item["reasons"]:
            item["reasons"].append("与相邻可疑片段形成连续异常")

    return {
        "version": VERSION,
        "status": "blocked" if candidates else "passed",
        "checked_count": len(values),
        "flagged_count": len(candidates),
        "flags": candidates,
        "clusters": clusters,
    }


__all__ = ["VERSION", "audit_source_segments"]
