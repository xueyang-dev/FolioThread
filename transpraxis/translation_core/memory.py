"""Project Memory views with confirmed knowledge and separate audit history."""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, TypedDict

from .. import models


CONFIRMED_STYLE_STATUSES = {"approved", "confirmed", "locked"}


class ConfirmedKnowledge(TypedDict, total=False):
    glossary_hash: str
    terminology_refs: List[Dict[str, Any]]
    translation_memory: List[Dict[str, Any]]
    style_rules: List[Dict[str, Any]]


class AuditHistory(TypedDict, total=False):
    human_decisions: List[Dict[str, Any]]


class ProjectMemory(TypedDict, total=False):
    schema_version: str
    knowledge: ConfirmedKnowledge
    audit_history: AuditHistory


def _glossary(state: Mapping[str, Any]) -> tuple[List[models.GlossaryEntry], str]:
    frozen = state.get("glossary_frozen") or {}
    entries = models.normalize_glossary(
        frozen.get("entries") or state.get("glossary") or []
    )
    return entries, models.glossary_hash(entries)


def _translation_memory(
    state: Mapping[str, Any], translation_memory: Any,
) -> List[Dict[str, Any]]:
    records = []
    if isinstance(translation_memory, Mapping):
        records.extend({"source": source, **dict(value)}
                       for source, value in translation_memory.items()
                       if isinstance(value, Mapping))
    elif isinstance(translation_memory, list):
        records.extend(dict(value) for value in translation_memory
                       if isinstance(value, Mapping))
    for index, pair in enumerate(state.get("pairs") or []):
        if isinstance(pair, Mapping) and pair.get("reviewed") \
                and not pair.get("stale_due_to_glossary"):
            records.append({
                "source": pair.get("source"), "target": pair.get("target"),
                "reviewed": True, "segment_id": pair.get("segment_id", index),
                "provenance": "foliothread_state",
            })
    confirmed = {}
    for record in records:
        source = str(record.get("source") or "").strip()
        target = str(record.get("target") or "").strip()
        if source and target and record.get("reviewed"):
            value = dict(record)
            value["source"], value["target"] = source, target
            confirmed[(source, target)] = value
    return sorted(confirmed.values(), key=lambda item: (item["source"], item["target"]))


def _style_rules(values: Iterable[Any]) -> List[Dict[str, Any]]:
    rules = []
    for value in values or []:
        if isinstance(value, str):
            rule = {"rule": value.strip(), "status": "confirmed"}
        elif isinstance(value, Mapping):
            rule = dict(value)
        else:
            continue
        text = str(rule.get("rule") or rule.get("text") or "").strip()
        status = str(rule.get("status") or "").strip().lower()
        if text and status in CONFIRMED_STYLE_STATUSES:
            rule["rule"], rule["status"] = text, status
            rules.append(rule)
    return _unique(rules)


def _unique(values: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result, seen = [], set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def project_memory_from_state(
    state: Mapping[str, Any],
    *,
    translation_memory: Any = None,
    confirmed_style_rules: Iterable[Any] = (),
) -> ProjectMemory:
    """Adapt current state without promoting candidates or adding persistence."""
    entries, glossary_hash = _glossary(state)
    terminology_refs = [{
        "glossary_entry_id": entry["id"],
        "glossary_hash": glossary_hash,
        "status": entry["status"],
        "behavior": entry["behavior"],
    } for entry in entries if entry["status"] == "locked"]
    human_decisions = [
        dict(action) for action in state.get("human_actions") or []
        if isinstance(action, Mapping)
        and str(action.get("actor_type") or "human").lower() == "human"
        and str(action.get("actor") or "").strip()
    ]
    return {
        "schema_version": "translation-core-project-memory-v1",
        "knowledge": {
            "glossary_hash": glossary_hash,
            "terminology_refs": terminology_refs,
            "translation_memory": _translation_memory(state, translation_memory),
            "style_rules": _style_rules(confirmed_style_rules),
        },
        "audit_history": {"human_decisions": _unique(human_decisions)},
    }
