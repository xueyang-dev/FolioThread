"""Self-contained independent-review packet construction."""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .. import models, terminology
from .evidence import fingerprint, review_input_fingerprint
from .memory import project_memory_from_state


def _bounded(value: Any, char_limit: int) -> Any:
    if isinstance(value, str):
        return value[:char_limit]
    if isinstance(value, list):
        result, used = [], 0
        for item in value:
            bounded = _bounded(item, max(0, char_limit - used))
            size = len(json.dumps(bounded, ensure_ascii=False, default=str))
            if used + size > char_limit:
                break
            result.append(bounded)
            used += size
        return result
    if isinstance(value, Mapping):
        result, used = {}, 0
        for key in sorted(value, key=str):
            bounded = _bounded(value[key], max(0, char_limit - used))
            size = len(str(key)) + len(json.dumps(bounded, ensure_ascii=False, default=str))
            if used + size > char_limit:
                break
            result[str(key)] = bounded
            used += size
        return result
    return value


def _translation_truth(
    state: Mapping[str, Any], segment_ids: Sequence[int] | None,
) -> List[Dict[str, Any]]:
    pairs = state.get("pairs") or []
    selected = list(segment_ids) if segment_ids is not None else list(range(len(pairs)))
    truth = []
    for index in selected:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(pairs):
            raise ValueError(f"unknown translation segment: {index!r}")
        pair = pairs[index]
        truth.append({
            "segment_id": pair.get("segment_id", index),
            "source": str(pair.get("source") or ""),
            "target": str(pair.get("target") or ""),
            "reviewed": bool(pair.get("reviewed")),
            "target_provenance": pair.get("target_provenance"),
        })
    return truth


def _relevant_glossary(
    entries: Iterable[models.GlossaryEntry], truth: Sequence[Mapping[str, Any]],
) -> List[models.GlossaryEntry]:
    segment_ids = {item["segment_id"] for item in truth}
    sources = [str(item["source"]) for item in truth]
    return [entry for entry in entries if
            segment_ids.intersection(entry.get("occurrences") or [])
            or any(terminology.term_matches(entry["source"], source) for source in sources)]


def build_review_packet(
    state: Mapping[str, Any],
    *,
    segment_ids: Sequence[int] | None = None,
    deterministic_checks: Any = None,
    context: Any = None,
    evidence: Any = None,
    translation_memory: Any = None,
    confirmed_style_rules: Iterable[Any] = (),
    project_memory: Mapping[str, Any] | None = None,
    context_char_limit: int = 12_000,
    evidence_char_limit: int = 16_000,
) -> Dict[str, Any]:
    """Build an independent packet; generation rationale is never accepted."""
    truth = _translation_truth(state, segment_ids)
    frozen = state.get("glossary_frozen") or {}
    entries = models.normalize_glossary(
        frozen.get("entries") or state.get("glossary") or []
    )
    glossary_hash = models.glossary_hash(entries)
    bounded_context = _bounded(context or {}, max(0, context_char_limit))
    bounded_evidence = _bounded(evidence or [], max(0, evidence_char_limit))
    bounded_checks = _bounded(deterministic_checks or [], max(0, evidence_char_limit))
    memory = deepcopy(dict(project_memory)) if project_memory is not None else \
        project_memory_from_state(
            state,
            translation_memory=translation_memory,
            confirmed_style_rules=confirmed_style_rules,
        )
    if not isinstance(memory.get("knowledge"), Mapping):
        raise ValueError("review packet Project Memory requires confirmed knowledge")
    input_fingerprint = review_input_fingerprint(
        source=[item["source"] for item in truth],
        target=[item["target"] for item in truth],
        glossary_hash=glossary_hash,
        confirmed_knowledge=memory["knowledge"],
        context=bounded_context,
        deterministic_checks=bounded_checks,
        evidence=bounded_evidence,
    )
    packet = {
        "schema_version": "translation-core-review-packet-v1",
        "review_mode": "independent",
        "instruction": (
            "Review only the supplied translation truth and evidence. "
            "Do not infer or reuse generation rationale."
        ),
        "translation_truth": truth,
        "translation_truth_fingerprint": fingerprint({"segments": truth}),
        "glossary": {
            "glossary_hash": glossary_hash,
            "entries": _relevant_glossary(entries, truth),
        },
        "project_memory": memory,
        "deterministic_checks": bounded_checks,
        "context": bounded_context,
        "evidence": bounded_evidence,
        "input_fingerprint": input_fingerprint,
    }
    return packet
