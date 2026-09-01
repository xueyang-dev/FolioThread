# FolioThread UI audit pack

Baseline commit: `b21ddfbbd1120774251e634cbaa7f8397ada0bdb` (`main`, PR #4)

Capture date: 2026-09-01 · Python 3.11.3 · Streamlit 1.62.0

App under test: the real `app.py` Streamlit application, run locally with deterministic fixtures. Phase 3.5 closure changes are recorded in [`docs/phase3-5-ux-closure.md`](../phase3-5-ux-closure.md).

Primary desktop viewport: 1440 × 780, the closest stable viewport available in the in-app browser to the requested 1440 × 1000.

Responsive viewports: 980 × 780 and 760 × 780. Screenshots are viewport captures; lower-page captures are used only where the action or evidence is below the fold.

## Master checklist

| Section | Coverage | Desktop | 980px | 760px |
|---|---:|:---:|:---:|:---:|
| Shell | 1 | ✓ | — | — |
| New task | 9 | ✓ | — | — |
| Settings | 3 | ✓ | ✓ | ✓ |
| History | 1 | ✓ | — | — |
| Library | 1 | ✓ | — | — |
| Workspace overview | 4 | ✓ | — | — |
| Workspace translation | 7 | ✓ | ✓ | ✓ |
| Workspace terms | 1 | ✓ | — | — |
| Workspace review | 9 | ✓ | ✓ | ✓ |
| Workspace cases | 2 | ✓ | — | — |
| Workspace report | 2 | ✓ | — | — |
| Workspace QA | 4 | ✓ | — | — |
| Workspace delivery | 7 | ✓ | ✓ | ✓ |
| Responsive subset | 12 | — | ✓ | ✓ |
| **Total** | **63** | **51** | **6** | **6** |

## Screenshot index

Every entry records the observed state, what is visible, the primary action, and the review focus. “Fixture” names are local-only IDs from `scripts/ui_audit_fixtures.py`.

### 00 · Shell

| Screenshot | State | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [001-shell-start.png](00-shell/001-shell-start.png) | Fresh app shell | Empty new-task shell, navigation, active DeepSeek connection | Start a new task | Orientation and shell hierarchy |

### 01 · New task

| Screenshot | State | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [010-new-task-step-1-document-loaded.png](01-new-task/010-new-task-step-1-document-loaded.png) | PDF loaded | Source file, target language, termbase entry point, style profiling | Configure document inputs | File confirmation and next-step affordance |
| [011-new-task-step-1-style-profile-fallback.png](01-new-task/011-new-task-step-1-style-profile-fallback.png) | AI unavailable | Manual style-selection fallback after smart profiling | Choose a style manually | Error recovery and footer overlap |
| [012-new-task-step-2-standard-strategy.png](01-new-task/012-new-task-step-2-standard-strategy.png) | Standard strategy | Translation strategy cards and selected default | Choose a strategy | Choice clarity and explanatory copy |
| [013-new-task-step-2-advanced-strategy.png](01-new-task/013-new-task-step-2-advanced-strategy.png) | Advanced strategy | Advanced strategy section opened | Review advanced controls | Progressive disclosure |
| [014-new-task-step-2-advanced-controls.png](01-new-task/014-new-task-step-2-advanced-controls.png) | Advanced controls | Lower advanced toggles and explanatory content | Adjust workflow options | Control grouping and scroll continuity |
| [015-new-task-step-3-delivery-content.png](01-new-task/015-new-task-step-3-delivery-content.png) | Delivery outputs | Output-format selection and standard deliverables | Select outputs | Deliverable comprehension |
| [016-new-task-step-3-research-report-enabled.png](01-new-task/016-new-task-step-3-research-report-enabled.png) | Research report enabled | Report workflow and theory controls | Enable report generation | Dependency disclosure |
| [017-new-task-step-3-research-inputs.png](01-new-task/017-new-task-step-3-research-inputs.png) | Research inputs | Template/reference upload areas below the fold | Add research inputs | Lower-page discoverability |
| [018-new-task-step-4-confirmation-unverified.png](01-new-task/018-new-task-step-4-confirmation-unverified.png) | Run confirmation | Configuration summary with unverified AI connection | Confirm or return to settings | Readiness and disabled-action explanation |

### 02 · Settings

| Screenshot | State | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [020-settings-default-same-reviewer.png](02-settings/020-settings-default-same-reviewer.png) | Default connection | DeepSeek provider/model, empty API key, reviewer follows translator | Configure the shared connection | Form hierarchy and disabled actions |
| [021-settings-separate-reviewer.png](02-settings/021-settings-separate-reviewer.png) | Separate reviewer | Separate reviewer option exposed with a deterministic dummy translator key | Configure reviewer role | Conditional form reveal |
| [022-settings-separate-reviewer-actions-clean.png](02-settings/022-settings-separate-reviewer-actions-clean.png) | Separate reviewer details | Reviewer model/key/endpoint and save/test actions | Save or test reviewer connection | Long-form completion and action reachability |

### 03 · History

| Screenshot | State | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [030-history-populated-audit-jobs.png](03-history/030-history-populated-audit-jobs.png) | 18 deterministic jobs | Populated history cards with business-stage labels and open/continue actions | Reopen a job | Scanability and status consistency |

### 04 · Library

| Screenshot | State | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [040-library-empty-memory-and-term-version.png](04-library/040-library-empty-memory-and-term-version.png) | No globally approved memory | Empty approved-memory state and collapsed project-term versions | Inspect or add reusable assets | Empty-state guidance |

### 10 · Workspace overview

| Screenshot | State / fixture | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [100-overview-translation-in-progress.png](10-workspace-overview/100-overview-translation-in-progress.png) | `ui-audit-in-progress` | Running translation, activity feed, progress, cancel action | Monitor or cancel | Progress feedback and recovery |
| [101-overview-review-required.png](10-workspace-overview/101-overview-review-required.png) | `ui-audit-blocking-suggested` | Review-required overview with blocking count and next step | Open review | Gate visibility |
| [102-overview-clean-ready.png](10-workspace-overview/102-overview-clean-ready.png) | `ui-audit-clean` | Completed translation and current review, ready for delivery | Open delivery | Completion summary |
| [103-overview-research-enabled.png](10-workspace-overview/103-overview-research-enabled.png) | `ui-audit-report-available` | Research-enabled job with report workflow in navigation | Open report | Academic workflow discoverability |

### 11 · Workspace translation

| Screenshot | State / fixture | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [200-translation-stale-edit-state.png](11-workspace-translation/200-translation-stale-edit-state.png) | `ui-audit-stale` | Current translation with a stale/review-history distinction | Inspect changed segment | Provenance and freshness |
| [201-translation-legacy-no-review.png](11-workspace-translation/201-translation-legacy-no-review.png) | `ui-audit-legacy` | Legacy job without independent review requirement | Edit or continue | Backward-compatible workflow copy |
| [202-translation-terminology-context.png](11-workspace-translation/202-translation-terminology-context.png) | `ui-audit-term` | Translation table with locked-term context | Inspect term context | Terminology visibility |
| [203-translation-multiple-findings.png](11-workspace-translation/203-translation-multiple-findings.png) | `ui-audit-multiple` | Multiple segment rows and findings context | Select a segment | Dense table scanning |
| [204-translation-review-finding.png](11-workspace-translation/204-translation-review-finding.png) | `ui-audit-blocking-suggested` | Current translation associated with review blocker | Save an edit or open review | Edit-to-review relationship |
| [205-translation-clean-segments.png](11-workspace-translation/205-translation-clean-segments.png) | `ui-audit-clean` | Reviewed translation rows and disabled retranslation without AI config | Review or edit a row | Trust signals and action state |
| [206-translation-in-progress.png](11-workspace-translation/206-translation-in-progress.png) | `ui-audit-in-progress` | Partially translated rows and interrupted workflow | Resume translation | Partial-state comprehension |

### 12 · Workspace terms

| Screenshot | State / fixture | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [250-terms-project-glossary.png](12-workspace-terms/250-terms-project-glossary.png) | `ui-audit-term` | Frozen project glossary v1 and one locked term | Inspect terminology | Lock state and table affordances |

### 13 · Workspace review

| Screenshot | State / fixture | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [300-review-clean-empty.png](13-workspace-review/300-review-clean-empty.png) | `ui-audit-clean` | Current translation fully reviewed with empty work queue | Proceed to delivery | Clear completion state |
| [301-review-blocking-suggested.png](13-workspace-review/301-review-blocking-suggested.png) | `ui-audit-blocking-suggested` | Blocking semantic finding with suggested target and highlighted spans | Apply suggestion, edit, or retain | Decision support |
| [302-review-blocking-no-suggestion.png](13-workspace-review/302-review-blocking-no-suggestion.png) | `ui-audit-blocking-no-suggestion` | Blocking completeness finding without suggested target | Confirm, edit, or retain | Safe fallback when no suggestion exists |
| [303-review-stale-task.png](13-workspace-review/303-review-stale-task.png) | `ui-audit-stale` | Re-review queue with stale current-translation warning | Re-review the changed segment | Freshness explanation |
| [304-review-failed-task.png](13-workspace-review/304-review-failed-task.png) | `ui-audit-failed` | Failed independent review state and retry affordance | Retry review | Failure recovery |
| [305-review-missing-task.png](13-workspace-review/305-review-missing-task.png) | `ui-audit-missing` | Unreviewed segments with pending queue | Start review | Empty-history onboarding |
| [306-review-multiple-findings.png](13-workspace-review/306-review-multiple-findings.png) | `ui-audit-multiple` | Blocking and suggested findings in one queue | Filter or resolve | Severity/filter model |
| [307-review-style-finding.png](13-workspace-review/307-review-style-finding.png) | `ui-audit-style` | Style finding with project-rule context | Save as style rule | Rule reuse affordance |
| [308-review-terminology-finding.png](13-workspace-review/308-review-terminology-finding.png) | `ui-audit-term` | Terminology finding tied to project glossary | View project term | Cross-workspace context |

### 14 · Workspace cases

| Screenshot | State / fixture | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [400-cases-review-queue.png](14-workspace-cases/400-cases-review-queue.png) | `ui-audit-report-available` | Authentic and synthetic case entries with one pending review | Approve or exclude a case | Provenance and review status |
| [401-cases-stale-downstream.png](14-workspace-cases/401-cases-stale-downstream.png) | `ui-audit-report-stale` | Case list under downstream stale conditions | Inspect affected case | Impact visibility |

### 15 · Workspace report

| Screenshot | State / fixture | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [500-report-available.png](15-workspace-report/500-report-available.png) | `ui-audit-report-available` | Report status, current-translation source, cases, and blocker summary | Review report issues | Report readiness |
| [501-report-stale-downstream.png](15-workspace-report/501-report-stale-downstream.png) | `ui-audit-report-stale` | Stale report warning with affected/reusable downstream counts | Rebuild affected outputs | Dependency explanation |

### 16 · Workspace QA

| Screenshot | State / fixture | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [550-qa-unfinished.png](16-workspace-qa/550-qa-unfinished.png) | `ui-audit-qa-unfinished` | Compliance failures and unconfirmed final-QA facts | Open rule details or record QA | Gate transparency |
| [551-qa-passing-facts.png](16-workspace-qa/551-qa-passing-facts.png) | `ui-audit-qa-passing` | DOCX/render/author/Word facts marked passed while other report gates remain | Inspect remaining blockers | Independent-fact separation |
| [552-qa-failed.png](16-workspace-qa/552-qa-failed.png) | `ui-audit-qa-failed` | Failed structural validation state | Inspect failed rule | Failure communication |
| [553-qa-stale.png](16-workspace-qa/553-qa-stale.png) | `ui-audit-qa-stale` | Stale QA artifact state after downstream change | Re-run or inspect source | Staleness lifecycle |

### 17 · Workspace delivery

| Screenshot | State / fixture | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [600-delivery-clean-ready.png](17-workspace-delivery/600-delivery-clean-ready.png) | `ui-audit-clean` | Review gate passed; report/QA not required; freeze action available | Freeze delivery | Final gate clarity |
| [601-delivery-blocked-review.png](17-workspace-delivery/601-delivery-blocked-review.png) | `ui-audit-blocking-suggested` | Delivery blocked by a review finding | Return to review | Blocker propagation |
| [602-delivery-risk-acceptance.png](17-workspace-delivery/602-delivery-risk-acceptance.png) | `ui-audit-blocking-no-suggestion` | Blocking delivery state and review-only next action | Understand or resolve risk | Risk boundary |
| [603-delivery-stale-review.png](17-workspace-delivery/603-delivery-stale-review.png) | `ui-audit-stale` | Delivery blocked by stale current-translation review | Re-review | Stale gate copy |
| [604-delivery-stale-report.png](17-workspace-delivery/604-delivery-stale-report.png) | `ui-audit-report-stale` | Delivery blocked by stale report downstream | Rebuild affected output | Impact-to-delivery link |
| [605-delivery-legacy-no-review.png](17-workspace-delivery/605-delivery-legacy-no-review.png) | `ui-audit-legacy` | Legacy no-review job with delivery-ready state | Freeze legacy delivery | Legacy path continuity |
| [606-delivery-frozen-v1.png](17-workspace-delivery/606-delivery-frozen-v1.png) | `ui-audit-clean` after freeze | Immutable v1 history, download, and current-version confirmation | Download frozen version | Irreversibility and version history |

### 20 · Responsive subset

| Screenshot | Viewport / state | What shown | Primary action | Review focus |
|---|---|---|---|---|
| [700-responsive-980-overview-review-required.png](20-responsive/700-responsive-980-overview-review-required.png) | 980px · blocker overview | Compressed workspace shell and delivery blocker | Open review | Tablet-width hierarchy |
| [701-responsive-980-translation.png](20-responsive/701-responsive-980-translation.png) | 980px · clean translation | Translation table and inspector | Inspect a segment | Table/inspector fit |
| [702-responsive-980-review-blocker.png](20-responsive/702-responsive-980-review-blocker.png) | 980px · blocker review | Review queue and inspector | Handle finding | Queue density |
| [703-responsive-980-review-stale.png](20-responsive/703-responsive-980-review-stale.png) | 980px · stale review | Stale warning, filters, and history | Re-review | Freshness at tablet width |
| [704-responsive-980-delivery-frozen.png](20-responsive/704-responsive-980-delivery-frozen.png) | 980px · frozen delivery | Frozen v1 delivery history and downloads | Download version | Long-page delivery layout |
| [705-responsive-980-settings.png](20-responsive/705-responsive-980-settings.png) | 980px · settings | Two-column settings form at tablet width | Configure connection | Form fit |
| [710-responsive-760-overview-review-required.png](20-responsive/710-responsive-760-overview-review-required.png) | 760px · blocker delivery | Narrow delivery layout with persistent navigation | Return to review | Narrow-width readability |
| [711-responsive-760-translation.png](20-responsive/711-responsive-760-translation.png) | 760px · clean translation | Translation table and inspector in narrow viewport | Inspect a segment | Horizontal compression |
| [712-responsive-760-review-blocker.png](20-responsive/712-responsive-760-review-blocker.png) | 760px · blocker review | Review queue, finding, and inspector | Handle finding | Narrow queue density |
| [713-responsive-760-review-stale.png](20-responsive/713-responsive-760-review-stale.png) | 760px · stale review | Stale warning and history | Re-review | Narrow stale-state copy |
| [714-responsive-760-delivery-frozen.png](20-responsive/714-responsive-760-delivery-frozen.png) | 760px · frozen delivery | Frozen v1 history and downloads | Download version | Narrow long-page layout |
| [715-responsive-760-settings.png](20-responsive/715-responsive-760-settings.png) | 760px · settings | Settings form under narrow viewport | Configure reviewer | Overflow and field reachability |

## Fixture matrix

The helper creates 18 local jobs and one synthetic PDF source. Fixture IDs map to the visible filenames above:

`ui-audit-new-untranslated`, `ui-audit-in-progress`, `ui-audit-clean`, `ui-audit-blocking-suggested`, `ui-audit-blocking-no-suggestion`, `ui-audit-stale`, `ui-audit-failed`, `ui-audit-missing`, `ui-audit-multiple`, `ui-audit-style`, `ui-audit-term`, `ui-audit-legacy`, `ui-audit-report-available`, `ui-audit-report-stale`, `ui-audit-qa-unfinished`, `ui-audit-qa-passing`, `ui-audit-qa-failed`, and `ui-audit-qa-stale`.

The fixtures are deterministic, local-only, and use dummy provider/model values. The original `outputs/` directory was restored after capture; no real provider credentials or source documents are included in this pack.

## Observed UI issues

The original pack recorded the following evidence-backed issues. Phase 3.5 closes both in the live app; the original PNGs remain as before-state evidence.

| ID | Evidence | Observation | Impact |
|---|---|---|---|
| UI-001 | [011-new-task-step-1-style-profile-fallback.png](01-new-task/011-new-task-step-1-style-profile-fallback.png) | Before-state: the manual style-profile fallback card was partially hidden behind the fixed bottom action bar. | Closed by keeping the action bar in document flow with separation from the fallback content. |
| UI-002 | [715-responsive-760-settings.png](20-responsive/715-responsive-760-settings.png) | Before-state: the Settings form retained a wide two-column layout at 760px and was cropped beneath the persistent sidebar. | Closed by stacking setup forms and offsetting the narrow main surface beside the sidebar. |

### Phase 3.5 live closure captures

These supplemental captures were taken from the updated real Streamlit app after the fixture run:

| Screenshot | Viewport / state | Closure evidence |
|---|---|---|
| [800-live-new-task-1440.png](18-phase3-5-live/800-live-new-task-1440.png) | 1440px · fresh task | Desktop shell and primary input hierarchy |
| [801-live-delivery-stale-1440.png](18-phase3-5-live/801-live-delivery-stale-1440.png) | 1440px · stale report delivery | Explicit impact scope and rebuild action |
| [802-live-report-stale-980.png](18-phase3-5-live/802-live-report-stale-980.png) | 980px · stale report | Readable compact nav/main layout |
| [803-live-review-stale-760.png](18-phase3-5-live/803-live-review-stale-760.png) | 760px · review workspace | Stacked narrow navigation with no vertical labels |
| [804-live-settings-760.png](18-phase3-5-live/804-live-settings-760.png) | 760px · AI settings | Provider and reviewer fields fully reachable beside sidebar |

The history cards also show runtime completion labels alongside business-stage labels. This pack treats the business-stage text as the state evidence and keeps that distinction visible; it is not logged as a product defect because these jobs are locally synthesized for audit coverage.

## Evidence limits

This is a screenshot-first product audit. It covers visible hierarchy, copy, states, actions, and responsive composition using the real Streamlit app. It does not establish keyboard-only behavior, screen-reader semantics, full color-contrast conformance, browser zoom behavior, or production performance. Those require a separate accessibility/performance pass.

## Final verification

- [x] Baseline `main` commit recorded above; Phase 3.5 work is on the feature branch.
- [x] `python3 -m pytest -q` passed: 427 tests.
- [x] All 63 accepted PNGs are viewport screenshots with descriptive three-digit filenames.
- [x] Desktop and required 980px/760px responsive subset captured.
- [x] README links and fixture names are relative to this directory.
- [x] Original `outputs/` data restored after capture.
- [x] Updated application behavior, projection tests, fixtures, and architecture notes are recorded on the Phase 3.5 branch.
