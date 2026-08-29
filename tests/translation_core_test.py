"""Focused contracts for the additive Translation Core foundation."""
from __future__ import annotations

from copy import deepcopy

import pytest

from transpraxis import models
from transpraxis.translation_core import (
    build_review_packet,
    fingerprint,
    mark_stale,
    normalize_finding,
    project_memory_from_state,
    record_human_decision,
    review_input_fingerprint,
)


def _entry(source: str, target: str, status: str = "locked", **extra):
    return {
        "source": source,
        "target": target,
        "preferred": target,
        "behavior": "translate",
        "status": status,
        "scope": "document",
        **extra,
    }


def _state():
    entries = [
        _entry("continuity", "连续性", evidence=[{
            "evidence_type": "user", "source_name": "terminologist",
            "note": "confirmed", "quote": "continuity", "url": "",
        }]),
        _entry("candidate", "候选", status="candidate"),
        _entry("rejected", "拒绝", status="rejected"),
    ]
    return {
        "pairs": [
            {"source": "Continuity matters.", "target": "连续性很重要。",
             "reviewed": True, "target_provenance": "reviewed"},
            {"source": "Candidate text.", "target": "候选文本。", "reviewed": False},
            {"source": "Old continuity.", "target": "旧连续性。", "reviewed": True,
             "stale_due_to_glossary": True},
        ],
        "glossary": entries,
        "glossary_frozen": {
            "entries": entries,
            "glossary_hash": models.glossary_hash(entries),
        },
        "knowledge_candidates": [{"source": "model term", "status": "emergent_candidate"}],
        "human_actions": [
            {"action": "knowledge_project_term", "actor": "alice", "finding_id": "k-1"},
            {"action": "self_approval", "actor": "review-model", "actor_type": "model"},
        ],
    }


def test_project_memory_contains_only_confirmed_existing_truth():
    state = _state()
    memory = project_memory_from_state(
        state,
        translation_memory={
            "TM confirmed": {"target": "已确认", "reviewed": True},
            "TM generated": {"target": "未确认", "reviewed": False},
        },
        confirmed_style_rules=[
            "Use formal register.",
            {"rule": "Prefer active voice.", "status": "confirmed"},
            {"rule": "Model suggestion.", "status": "candidate"},
        ],
    )

    assert memory["glossary_hash"] == models.glossary_hash(state["glossary"])
    assert [item["glossary_entry_id"] for item in memory["terminology_refs"]] == [
        models.normalize_glossary_entry(state["glossary"][0])["id"]
    ]
    assert {(item["source"], item["target"]) for item in memory["translation_memory"]} == {
        ("Continuity matters.", "连续性很重要。"), ("TM confirmed", "已确认")
    }
    assert [item["rule"] for item in memory["style_rules"]] == [
        "Use formal register.", "Prefer active voice."
    ]
    assert memory["human_decisions"] == [state["human_actions"][0]]
    assert "knowledge_candidates" not in memory


def test_review_finding_identity_ignores_mutable_explanation_text():
    input_hash = fingerprint({"review": 1})
    base = {
        "category": "semantic_accuracy", "code": "omission", "severity": "actionable",
        "status": "open", "segment_id": 4, "source_span": "the result",
        "target_span": "结果", "evidence_refs": ["E1", "E1", "E2"],
        "requires_human_confirmation": True,
    }
    first = normalize_finding({**base, "summary": "First wording"},
                              input_fingerprint=input_hash)
    second = normalize_finding({**base, "summary": "Reworded"},
                               input_fingerprint=input_hash)

    assert first["finding_id"] == second["finding_id"]
    assert first["evidence_refs"] == ["E1", "E2"]
    assert first["severity"] == "actionable" and first["status"] == "open"
    with pytest.raises(ValueError, match="severity"):
        normalize_finding({**base, "severity": "urgent"}, input_fingerprint=input_hash)


def test_only_a_human_can_decide_an_open_human_required_finding():
    current = fingerprint({"target": "v1"})
    finding = normalize_finding({
        "category": "meaning", "code": "ambiguous", "severity": "actionable",
        "status": "open", "segment_id": 1, "requires_human_confirmation": True,
    }, input_fingerprint=current)
    updated, decision = record_human_decision(
        finding, "approved", "alice", actor_type="human",
        note="Checked against the source.", decided_at="2026-08-29T12:00:00+00:00",
        current_fingerprint=current,
    )

    assert updated["status"] == "resolved"
    assert decision["finding_id"] == finding["finding_id"]
    assert decision["actor_type"] == "human" and decision["status"] == "current"
    with pytest.raises(ValueError, match="human"):
        record_human_decision(finding, "approved", "review-model", actor_type="model")
    with pytest.raises(ValueError, match="open finding"):
        record_human_decision(
            {**finding, "requires_human_confirmation": False},
            "approved", "alice", actor_type="human",
        )
    with pytest.raises(ValueError, match="stale"):
        record_human_decision(
            finding, "approved", "alice", actor_type="human",
            current_fingerprint=fingerprint({"target": "v2"}),
        )


def test_review_freshness_changes_for_every_dependency_and_preserves_records():
    dependencies = {
        "source": ["source"], "target": ["target"], "glossary_hash": "g1",
        "project_memory": {"style_rules": []}, "context": {"before": "x"},
        "deterministic_checks": [{"code": "ok"}], "evidence": [{"id": "E1"}],
    }
    original = review_input_fingerprint(**dependencies)
    for key, replacement in {
        "source": ["changed"], "target": ["changed"], "glossary_hash": "g2",
        "project_memory": {"style_rules": ["changed"]},
        "context": {"before": "changed"},
        "deterministic_checks": [{"code": "changed"}],
        "evidence": [{"id": "E2"}],
    }.items():
        changed = dict(dependencies)
        changed[key] = replacement
        assert review_input_fingerprint(**changed) != original

    old = {"finding_id": "f-1", "status": "resolved", "input_fingerprint": original}
    stale = mark_stale(
        [old], fingerprint({"new": "inputs"}), "translation changed",
        stale_at="2026-08-29T12:01:00+00:00",
    )
    assert stale == [{
        **old, "status_before_stale": "resolved", "status": "stale",
        "stale_reason": "translation changed", "stale_at": "2026-08-29T12:01:00+00:00",
    }]
    assert old["status"] == "resolved"


def test_review_packet_is_bounded_independent_and_v04_compatible():
    state = _state()
    before = deepcopy(state)
    packet = build_review_packet(
        state,
        segment_ids=[0],
        deterministic_checks=[{"code": "terminology", "status": "pass"}],
        context={"previous": "x" * 100},
        evidence=[{"evidence_id": "E1", "quote": "y" * 100}],
        confirmed_style_rules=["Use formal register."],
        context_char_limit=40,
        evidence_char_limit=60,
    )

    assert state == before
    assert packet["review_mode"] == "independent"
    assert "generation_context" not in packet and "generation_rationale" not in packet
    assert packet["translation_truth"][0]["source"] == "Continuity matters."
    assert [entry["source"] for entry in packet["glossary"]["entries"]] == ["continuity"]
    assert packet["glossary"]["glossary_hash"] == models.glossary_hash(state["glossary"])
    assert len(str(packet["context"])) < 100
    assert len(str(packet["evidence"])) < 120
    assert packet["project_memory"]["terminology_refs"]

    changed = deepcopy(state)
    changed["pairs"][0]["target"] = "改变。"
    assert build_review_packet(changed, segment_ids=[0])["input_fingerprint"] != \
        build_review_packet(state, segment_ids=[0])["input_fingerprint"]

    legacy = {"pairs": [{"source": "A", "target": "甲"}], "glossary": []}
    assert build_review_packet(legacy)["translation_truth"][0]["source"] == "A"
