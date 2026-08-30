# Translation Core Phase 2 runtime closure

Phase 2 closes FolioThread's first production Translation Core loop without
replacing the long-document translation product or its persistence model:

```text
translation -> deterministic QA -> self-contained review packet
  -> independent semantic review -> ReviewFinding -> HumanDecision
  -> confirmed knowledge promotion -> freshness propagation -> delivery gate
```

Translation execution, Provider routing, checkpoints and recovery, PDF/DOCX
handling, academic reporting, MTI workflow, exports, and delivery snapshots remain
FolioThread-specific. Translation Core supplies domain-neutral contracts and
adapters around the existing runtime.

## Authoritative state

There is no second database or parallel truth:

- canonical terminology remains FolioThread `GlossaryEntry` state, including
  candidate/provisional/locked/rejected, translate/preserve, evidence, frozen
  versions, and glossary hashes;
- translation memory remains the existing reviewed pair/TM store;
- review findings remain in `state["findings"]`;
- review events remain in `state["review_evidence"]`;
- human decisions and promotion audit records remain in
  `state["human_actions"]`;
- confirmed style rules are an additive state field read by Project Memory.

The adapters normalize these records to Translation Core contracts in place.
Existing v0.4 state receives additive defaults and retains legacy human-action
inference when `actor_type` is absent. New Translation Core decisions always
require an explicit human actor type.

## Review finding and decision lifecycle

Review findings have stable logical identity separate from input freshness.
Identity uses code/category, subject, optional glossary entry, and a stable
location/occurrence key. A unique source span is adapted to a source offset. A
duplicate with no stable locator may receive a provisional ordinal for display and
collision avoidance, but HumanDecision rejects that provisional identity.

The decision vocabulary maps directly to lifecycle state:

| HumanDecision | Finding status | Delivery effect |
| --- | --- | --- |
| `accept_resolution` | `resolved` | closes the current blocking finding |
| `dismiss` | `dismissed` | closes the current blocking finding with audit |
| `request_revision` | `open` | continues to block until revision and re-review |

A decision is accepted only for an open, human-confirmation finding with a nonempty
stable ID, an explicit human actor, and an exact current input fingerprint. A model
cannot approve its own output. Old decisions are preserved and may be superseded;
they are never overwritten.

## Freshness and supersession

The final consumed-input fingerprint represents the reviewer's complete input:
source, target, canonical glossary hash, scoped confirmed knowledge, bounded review
context, deterministic checks, and the evidence envelopes actually consumed. In
packet mode, legacy prompt arguments are not appended outside the packet, and the
external target-language argument must match packet context before the reviewer is
called.

Changing review-relevant translation truth marks dependent review events,
findings, decisions, and reviewed/TM trust stale. Triggers include source or target
edits, relevant context/profile changes, canonical glossary changes, confirmed
style changes, deterministic checks, and evidence/version changes. Stale records
retain their prior status, reason, time, and superseding review event. A new current
review supersedes only the segments it covers, so unrelated segments remain current
and historical stale records do not permanently block delivery.

Audit history is carried separately from confirmed Project Memory knowledge and is
not a review fingerprint dependency. Recording a decision therefore cannot make
that same decision stale. When an explicit promotion originates from a current
finding, the source segment is likewise excluded from the promotion's immediate
invalidation; other dependent reviews still become stale.

## Confirmed Project Memory

Only explicit human confirmation promotes durable knowledge:

- terminology promotion creates or updates the canonical locked GlossaryEntry and
  freezes the canonical glossary;
- reviewed, current translation pairs feed the existing translation-memory truth;
- confirmed style rules are stored with actor, time, source finding, and decision
  provenance.

Model observations and provisional glossary hints remain candidates or advisory
review context. They can affect a fingerprinted review input, but cannot silently
become durable knowledge.

## Delivery readiness

For jobs that require Translation Core review, readiness distinguishes `not_run`,
`missing`, `failed`, `stale`, and `current`. Only `current` passes. Every expected
segment must have a successful current review event, and every current blocking
finding must have a matching current human decision. Both backend approval and the
workbench delivery surface use this readiness result; accepting legacy review risk
cannot bypass it.

Legacy jobs whose additive `translation_core_review_required` flag is false retain
their existing delivery behavior. Existing target invariants, academic/report
gates, final snapshots, and accepted-risk audit behavior remain in force alongside
the Translation Core gate.

## Compatibility, rollback, and non-goals

The change is additive. The legacy reviewer path still works when no Translation
Core packet is supplied. Runtime adoption can be rolled back by stopping packet and
review-event registration; no state migration or database reversal is required.

Phase 2 adds no agent loop, workflow engine, second state store, broad retrieval
layer, translation-execution rewrite, checkpoint replacement, delivery replacement,
or academic/MTI redesign.

## Phase 3 follow-ups

Future work can deepen canonical glossary decisions, reviewed TM retrieval and
promotion, more selective dependency scopes, and richer delivery reporting. Any
new detector that can emit multiple findings at the same logical subject must
provide a stable location or occurrence key before those findings can receive a
HumanDecision.
