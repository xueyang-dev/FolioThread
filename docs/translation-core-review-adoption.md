# Translation Core review adoption (Phase 2B)

Phase 2B is a narrow runtime vertical slice: FolioThread's existing long-document
translation review now crosses the Translation Core boundary without redesigning
translation execution or persistence.

The production sequence is:

```text
existing translation and deterministic QA
  -> Translation Core review packet
  -> existing independent semantic reviewer
  -> Translation Core ReviewFinding
  -> existing repair and persistence behavior
```

## Adopted review paths

The same packet and finding contracts serve all three real semantic-review paths:

1. Formal batch review after deterministic repair has completed.
2. Blind review of a deterministic-repair shadow candidate before promotion.
3. Blind re-review of a reviewer-suggested target after deterministic rechecking.

Blind packets contain the candidate target only. They do not expose the formal or
initial target, generation or repair rationale, audit history, or prior reviewer
decisions. The existing bounded evidence allow-list and Provider execution remain
authoritative.

## Ephemeral current-batch projection

Review occurs before the current batch is committed to `state["pairs"]`. The
FolioThread adapter therefore copies the committed pair list and overlays copied
current-batch pairs at their explicit document-global segment IDs. Packet
construction reads this temporary projection only; it does not mutate the caller's
state or batch and does not save a checkpoint. The same projection works after a
resume, when earlier batches are already committed.

## Review-scoped Project Memory

The runtime packet carries only review-relevant confirmed knowledge:

- canonical locked terminology references relevant to the reviewed sources;
- the canonical full glossary hash;
- confirmed style knowledge when a future caller has an explicit confirmed source.

Phase 2B deliberately supplies no translation-memory entries. FolioThread has no
review-time TM retrieval layer yet, and hashing the continually growing project TM
would make unrelated earlier reviews stale. Audit history is also absent from both
the reviewer-visible packet and the freshness fingerprint. Current runtime style
text remains bounded factual review context rather than being promoted to confirmed
Project Memory.

## Review context and dynamic evidence

The packet fingerprints bounded factual context already available to the runtime:
document and section profiles, document synopsis and section digest, neighboring
source text, accepted or reviewed previous target context, next-source context, and
current style constraints. The target language and the exact advisory terminology
text—including provisional hints—also live in this fingerprinted review context.
With a Translation Core packet, the packet view is the reviewer's sole data input;
legacy `glossary_text` and `style_rules` arguments are not appended beside it. It
does not reuse an opaque generation prompt.

The initial packet contains no dynamically requested evidence. If the reviewer uses
the existing evidence-request round, the adapter recomputes the final consumed-input
fingerprint from the actual bounded evidence envelopes. Returned findings use that
final fingerprint, and the trace plus completion receipt record it. With no evidence
request, the initial and final fingerprints are identical.

## Finding and trace compatibility

Semantic findings are normalized through `translation_core.normalize_finding()`.
Translation Core identity and freshness fields are authoritative, while legacy
runtime fields such as `reason`, `suggested_target`, diagnostic spans, evidence
references, `segment_index`, `type="review"`, and `review_event_id` remain available
to existing repair, persistence, reports, and UI readers.

Identity uses code/category, global subject ID, optional glossary entry ID, and an
explicit logical location or occurrence key. Mutable source/target span prose is not
part of identity. When the reviewer emits duplicate logical findings without a key,
the adapter assigns deterministic per-response occurrence ordinals so IDs do not
collide. Blocking semantic findings request human confirmation; this phase adds no
HumanDecision UI or action path.

Review traces add packet schema, initial and final consumed fingerprints, and the
translation-truth fingerprint. The full packet is not persisted.

## Compatibility and rollback

`review_translation_batch_with_evidence()` still accepts calls without a Translation
Core packet. That path retains its prior prompt, result shape, evidence protocol, and
failure behavior. Runtime adoption is therefore additive and can be rolled back by
stopping packet construction/passing without changing persisted state or migrating
existing v0.4 jobs.

## Explicit non-goals

Phase 2B does not change translation generation, Provider routing, checkpoints or
resume, delivery/release gates, academic reporting, MTI workflow, translation-memory
promotion, Workbench UI, HumanDecision integration, state migration, or persisted
schema requirements. It adds no database, agent loop, workflow engine, retrieval
subsystem, or persistence layer.

Before HumanDecision runtime adoption, duplicate detectors must provide stable
`location_key` or `occurrence_key` values. The current deterministic response-order
fallback prevents collisions but is not a durable decision identity if a model
reorders otherwise identical findings.
