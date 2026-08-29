"""Auditable human decisions for review findings."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Tuple, TypedDict

from .. import models
from .evidence import freshness
from .findings import ReviewFinding


DECISIONS = {"approved", "rejected", "request_changes", "dismissed"}


class HumanDecision(TypedDict, total=False):
    decision_id: str
    finding_id: str
    decision: str
    actor: str
    actor_type: str
    note: str
    decided_at: str
    input_fingerprint: str
    status: str


def record_human_decision(
    finding: Mapping[str, Any],
    decision: str,
    actor: str,
    *,
    actor_type: str,
    note: str = "",
    decided_at: str | None = None,
    current_fingerprint: str | None = None,
) -> Tuple[ReviewFinding, HumanDecision]:
    """Resolve one current, open, human-required finding with a human actor."""
    decision = str(decision or "").strip().lower()
    actor = str(actor or "").strip()
    if actor_type != "human" or not actor:
        raise ValueError("only an identified human may record a human decision")
    if decision not in DECISIONS:
        raise ValueError(f"invalid human decision: {decision!r}")
    if finding.get("status") != "open" or not finding.get("requires_human_confirmation"):
        raise ValueError("human decisions require an open finding that requests confirmation")
    input_fingerprint = str(finding.get("input_fingerprint") or "")
    if not input_fingerprint:
        raise ValueError("finding has no review input fingerprint")
    if current_fingerprint is not None and freshness(finding, current_fingerprint) != "current":
        raise ValueError("cannot decide a stale finding")
    timestamp = decided_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    finding_id = str(finding.get("finding_id") or "")
    decision_id = models.stable_id(
        finding_id, input_fingerprint, actor, decision, timestamp, prefix="d",
    )
    record: HumanDecision = {
        "decision_id": decision_id,
        "finding_id": finding_id,
        "decision": decision,
        "actor": actor,
        "actor_type": "human",
        "note": str(note or "").strip(),
        "decided_at": timestamp,
        "input_fingerprint": input_fingerprint,
        "status": "current",
    }
    updated: ReviewFinding = dict(finding)  # type: ignore[assignment]
    updated["status"] = "dismissed" if decision == "dismissed" else "resolved"
    updated["resolution_decision_id"] = decision_id  # type: ignore[typeddict-unknown-key]
    return updated, record
