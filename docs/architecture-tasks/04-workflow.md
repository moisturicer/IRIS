# 04 — Workflow

**Thesis-critical.** These six tasks build, protect and measure the contribution in [ADR-003](../adr/003-clearance-aware-resubmission.md). If capacity slips, cut from `06-rag.md` and `03-frontend.md` before touching `W-01`, `W-02`, `W-03` or `W-04`.

---

# W-01 · Declarative transition table

## Objective
One module owning every legal workflow transition, replacing 18 assignment sites across four modules — and making routing configurable per institution.

## Problem
The system's routing rule is written three times, seven transitions are unguarded, and there is no enumeration of legal edges. Nobody can answer "what can happen to this record next?" without reading three files — including the thesis author, at defence.

## Evidence

| Site | Transitions | Guard |
|---|---|---|
| `reviews/services.py` | 11 | `InvalidPipelineTransition` ✓ |
| `records/views.py:76` (create) | 1 | n/a |
| `records/views.py:135-138` (`submit`) | 2 | hand-written 400 |
| `records/views.py:208` (`complete`) | 1 | hand-written 400 |
| `records/views.py:254` (`perform_destroy`) | 1 | **none** |
| `records/views.py:334` (`import_excel`) | 1 → `published` | **none** |
| `records/views.py:690-693` (delete decline) | 1 | none; re-derives the type rule |
| `records/services.py:33` | 1 | none |

*"Proposal → `adviser_review`, else `rdco_intake`"* appears at `reviews/services.py:150-152`, `records/views.py:135-138`, and inverted at `:690-693`. SRS Module 5 is marked draft, so it will change again.

## Current State
Workflow logic is branches across four modules; offices and routing are hardcoded to CIT-U.

## Proposed State
`records/lifecycle.py` — a declarative table keyed `(from_status, event, actor_role) → to_status`, with `apply(record, event, actor)` wrapping each transition in `transaction.atomic()`. Views name events, never status strings.

## Scope
The table and `apply()`; migrate all 18 sites; a `can_transition(record, event, actor)` predicate for UI affordances; the Excel importer becomes a `legacy_import` event (`W-06`).

## Out of Scope
Changing workflow *semantics*. The role→stage authorization rule (`W-05`). A general BPMN engine — explicitly not that ([ADR-002](../adr/002-workflow-transition-table.md)).

## Technical Approach
A plain dict. **Deletion test passes:** removing the module scatters ~30 rules back across 18 sites in four modules.

## Dependencies
`F-02` (enums). **`T-01` first** — this touches the core write path and must not be attempted without an import-smoke test; characterisation tests before the refactor are strongly preferred (`T-03`).

## Risks
**Medium — the highest-risk refactor in the plan.** It touches every write path for the central domain object. Sequence it after tests, not before. Scope creep into a general workflow engine is the second risk: ~30 rows, no timers, no sub-processes, no conditional expressions.

## Security Impact
Positive. The unguarded transitions at `records/views.py:254` and `:334` become guarded edges. `transaction.atomic()` closes the partial-application defect (`W-03`).

## Performance Impact
Neutral.

## SaaS Impact
**The core enabler.** Offices, stages and routing become data; institutional onboarding becomes configuration rather than a fork ([ADR-005](../adr/005-instance-per-tenant.md)).

## Research/Thesis Impact
**This is where the contribution lives.** The table is what the paper describes and what `W-02` varies. It also upgrades the claim from "CIT-U's workflow, implemented" to "a configurable routing model, instantiated for CIT-U."

## MVP Classification
MVP REQUIRED — thesis-critical, protected

## Priority
P1 — Weeks 4–7

## Complexity
M (~3 dev-days)

## Acceptance Criteria
- [ ] `records/lifecycle.py` enumerates every legal `(from, event, role) → to` edge.
- [ ] `grep -rn "pipeline_status = " backend/apps/` matches only `lifecycle.py`.
- [ ] An illegal transition raises `InvalidPipelineTransition` and leaves the record unchanged.
- [ ] The type-routing rule exists in exactly one place.
- [ ] All three record types traverse `draft` → terminal state correctly.
- [ ] Existing workflow behaviour is unchanged (regression suite green).

## Testing Requirements
`T-03` — parametrised test over every legal edge and representative illegal ones, with no HTTP.

## Documentation Requirements
The table rendered as a state diagram in the SDD (`F-03`). It is the figure the paper uses.

## Definition of Done
Merged; `T-03` green in CI; Jira `IR-41` rewritten to reference consolidation rather than rebuilding.

---

# W-02 · Restart-all resubmission policy

## Objective
Make resubmission policy configurable so the contribution can be evaluated by controlled comparison rather than asserted.

## Problem
Preserved-clearance counting cannot produce a negative result — given which office declined, the count is deterministically computable. Without an alternative policy to compare against, the central claim is arithmetic, not evidence.

## Evidence
`reviews/services.py:378-395` — the clearance-office decline branch resets one office's `RecordClearance` and routes to that office's stage. The sequential-decline branch already deletes all clearances. The policy switch belongs on the first branch only; the insertion point is small and precise.

## Current State
Clearance-aware behaviour is hardcoded. No comparison is possible.

## Proposed State
Two policies in the `W-01` table:
- `CLEARANCE_AWARE` (production default) — reset only the declining office
- `RESTART_ALL` — reset every clearance row to `pending`, route to the first clearance stage for the record type

Policy is instance-level configuration, not an in-app setting.

## Scope
The policy enum; the alternate row set; configuration binding; tests covering both.

## Out of Scope
A UI for switching policy — it is deployment configuration ([ADR-004](../adr/004-restart-all-comparison-mode.md)).

## Technical Approach
A configuration value read at startup. **`RESTART_ALL` must never be enabled on the customer's production instance** — it would reset live clearance state. The evaluation runs on a separate instance, which instance-per-tenant makes free.

## Dependencies
`W-01`.

## Risks
**Operational, and must be controlled:** enabling the flag on a live instance corrupts customer workflows. Mitigation: instance-level only, production default `CLEARANCE_AWARE`, evaluation on a dedicated instance.

## Security Impact
Low, with one control: the policy must not be reachable through a staff-facing endpoint.

## Performance Impact
None.

## SaaS Impact
Positive — resubmission policy joins offices and routing as institution-configurable. A real product capability that emerged from the research design.

## Research/Thesis Impact
**Defining.** This is what makes [ADR-003](../adr/003-clearance-aware-resubmission.md)'s claim testable. Either result is a valid finding.

## MVP Classification
MVP REQUIRED — thesis-critical, protected

## Priority
P1 — Weeks 4–7

## Complexity
XS (~0.5 dev-days)

## Acceptance Criteria
- [ ] Under `CLEARANCE_AWARE`, an IERC decline then resubmit resets **only** IERC; KTTO's `cleared` status persists.
- [ ] Under `RESTART_ALL`, the same sequence resets **every** clearance to `pending`.
- [ ] The policy is read from instance configuration, not per-request.
- [ ] Production default is `CLEARANCE_AWARE`.
- [ ] No API endpoint can change the policy.

## Testing Requirements
`T-03` covers both policies over the same scenario set.

## Documentation Requirements
Recorded in the SDD as an institutional configuration option; the evaluation protocol in `V-04`.

## Definition of Done
Merged; both policies tested; the evaluation instance provisioned separately.

---

# W-03 · Transaction boundaries on transitions

## Objective
Prevent partially-applied transitions, one of which can advance a record past an office that never cleared it.

## Problem
Every transition performs 2–4 writes with no transaction boundary, and notifications fire before commit.

## Evidence
`grep -rn "atomic" backend/apps/` returns exactly one match — `accounts/views.py:23`, in registration. **None in `reviews/` or `records/`.**

`approve_record` at `rdco_intake` performs: create `Review` → `get_or_create` two `RecordClearance` rows → save `Record.pipeline_status` → `notify_record_reviewed`.

**The dangerous failure:** if it fails after the first clearance row, one office has a pending row and the other does not. `_all_clearances_done` then returns `True` once that single office clears — **the record advances to `rdco_review` having been cleared by one office instead of two.** That defeats the parallel-review requirement, which is the contribution.

## Current State
No transaction boundaries. A decline that rolls back still emails the owner.

## Proposed State
All five transition functions wrapped in `transaction.atomic()`; notifications and audit events dispatched via `transaction.on_commit`.

## Scope
`approve_record`, `decline_record`, `reject_record`, `submit_clearance`, `resubmit_record`; move `notify_*` to `on_commit`; `W-04`'s audit events inside the transaction.

## Out of Scope
`ATOMIC_REQUESTS = True` globally — rejected; it would hold a transaction open across email dispatch and file I/O on every request.

## Technical Approach
Naturally absorbed into `W-01` if that lands first.

## Dependencies
None; complements `W-01` and `W-04`.

## Risks
Low. `on_commit` does not fire under `TestCase` without `captureOnCommitCallbacks` — tests must use it.

## Security Impact
Prevents a record advancing without all required clearances — a correctness failure with a security character.

## Performance Impact
Negligible.

## SaaS Impact
None.

## Research/Thesis Impact
Protects the integrity of the clearance state the evaluation measures. Corrupted clearance rows would silently invalidate `V-05` data.

## MVP Classification
MVP REQUIRED — thesis-critical

## Priority
P1

## Complexity
S

## Acceptance Criteria
- [ ] An exception after the `Review` insert leaves `pipeline_status` unchanged and no `Review` row persisted.
- [ ] An exception between the two `RecordClearance` inserts leaves neither row.
- [ ] A rolled-back transition sends no notification and writes no audit event.
- [ ] Concurrent clearance submissions by two offices produce exactly two rows (NFR-R3).

## Testing Requirements
Rollback tests using `captureOnCommitCallbacks`; concurrency test feeding `V-13`.

## Documentation Requirements
Transaction boundaries noted in the SDD.

## Definition of Done
Merged; rollback tests in CI.

---

# W-04 · Audit review decisions and instrument time-on-task

## Objective
Record the workflow decisions that matter, and capture the measurements the thesis evaluation depends on.

## Problem
Two gaps. The audit log records logins, views, uploads and downloads — but **not a single approval**. And the evaluation needs per-office review durations that nothing currently captures.

## Evidence
`AuditEvent.EVENT_TYPE_CHOICES` (`audit/models.py:29-44`) lists 14 types; none covers approve, decline, reject or clear. `grep -rn "create_audit_event" backend/apps/reviews/` returns two matches, both PIN events.

`Review` and `RecordClearance` rows record decisions but are **not an audit trail**: `resubmit_record` (`reviews/services.py:381`) deletes all clearance rows on a sequential-decline resubmission, and they carry no timing beyond `created_at`.

`ACCESS` is overloaded — `records/views.py:223` logs a tag edit as `ACCESS`.

## Current State
The approval chain is unauditable and unmeasurable.

## Proposed State
`REVIEW_DECISION`, `CLEARANCE_DECISION` and `TAG_CHANGE` event types, emitted from the service layer inside `W-03`'s transaction, recording stage, decision, resulting status — plus **queue-entry and decision timestamps per office**, so time-on-task is derivable.

## Scope
Three event types; emission from all five transition functions; per-office queue-entry timestamp; a `preserved_clearances` count on each resubmission event; tag edits given their own type.

## Out of Scope
Audit immutability (`S-07`). An analytics dashboard (deferred).

## Technical Approach
Extend `AuditEvent.metadata` (JSONB) rather than adding columns. Time-on-task = decision timestamp − queue-entry timestamp per office. Preserved-clearance count computed and stored at resubmission time so it survives the clearance-row deletion.

## Dependencies
`W-01`, `W-03`. **Must exist before Week 11** — there is no second chance to collect pilot data.

## Risks
**Highest research risk in the plan if late.** Instrumentation added after the pilot begins yields no data. Treat the Week 10 deadline as hard.

## Security Impact
Satisfies part of FR-M8-02 and NFR-S5. Evaluation timing data includes participant identity — handle under RA 10173 and anonymise in the paper.

## Performance Impact
One insert per transition; negligible.

## SaaS Impact
Per-stage turnaround becomes a product analytics capability in Phase 2.

## Research/Thesis Impact
**Defining.** This produces every quantitative metric in [ADR-011](../adr/011-evaluation-framework.md): task success, time-on-task, offices re-reviewed, preserved clearances, per-stage and total turnaround.

## MVP Classification
MVP REQUIRED — thesis-critical, protected

## Priority
P1 — must complete by end of Week 10

## Complexity
M (~2 dev-days)

## Acceptance Criteria
- [ ] Every approve/decline/reject/clear writes exactly one audit event.
- [ ] Each records stage, decision and resulting status.
- [ ] Each office's queue-entry and decision timestamps are captured, so time-on-task is computable per office per record.
- [ ] Each resubmission event records offices reset and offices preserved, and the count survives clearance-row deletion.
- [ ] Tag edits emit `TAG_CHANGE`, not `ACCESS`.
- [ ] A rolled-back transition writes no audit event.
- [ ] Filtering by `REVIEW_DECISION` returns a record's full approval history.

## Testing Requirements
One-event-per-transition test; a test asserting preserved-clearance counts survive resubmission; export verified against a seeded scenario.

## Documentation Requirements
Metric definitions in the evaluation protocol (`V-02`) and the SDD.

## Definition of Done
Merged; instrumentation verified end-to-end on a seeded workflow; a sample export reviewed against `V-02`'s metric definitions before Week 11.

---

# W-05 · One `ReviewPolicy` for role→stage authorization

## Objective
Collapse two independent encodings of "who reviews what, when" into one consulted by both the queue and the authorization check.

## Problem
The mapping is written twice, in two shapes, with no shared source — so a record can appear in a reviewer's queue and then be refused when they act on it.

## Evidence
`reviews/views.py:61-67` builds the pending queue from a `role_to_statuses` dict. `reviews/services.py:76-93` authorizes decisions with inline conditionals. The adviser case already differs: the queue filters `records.filter(adviser=request.user)` at `:78` while the service checks `record.adviser_id == user.pk`.

## Current State
Two encodings that can silently disagree.

## Proposed State
A `ReviewPolicy` exposing `stages_for(role)` and `can_act(user, record)`, consumed by the queue, the service and `W-01`.

## Scope
Extract `_can_review` and `_can_submit_clearance`; derive the queue from the policy; remove the `is_django_staff` bypass (with `S-05`).

## Out of Scope
DRF permission classes for HTTP-level checks (`S-03`).

## Technical Approach
Pure functions. `F-02`'s `ClearanceOffice` enum carries the role↔office mapping, removing a third encoding.

## Dependencies
`F-02`, `S-05`.

## Risks
Low, provided current behaviour is captured in tests first.

## Security Impact
Positive — one place to audit the question NFR-S4 asks.

## Performance Impact
Neutral.

## SaaS Impact
Role→stage mapping becomes institution-configurable alongside the transition table.

## Research/Thesis Impact
Supports `V-06` reviewer-routing validation; queue/authorization disagreement would produce noise in that data.

## MVP Classification
MVP RECOMMENDED

## Priority
P2

## Complexity
M

## Acceptance Criteria
- [ ] One module answers both "which records are pending for this user" and "may this user act on this record".
- [ ] Every record in a reviewer's queue is actionable by that reviewer (property test over six roles).
- [ ] Every record absent from the queue is refused.
- [ ] The role→stage mapping exists in exactly one place.

## Testing Requirements
Policy tests without HTTP; property test linking queue and authorization.

## Documentation Requirements
The mapping documented in the SDD.

## Definition of Done
Merged; queue and authorization proven consistent in CI.

---

# W-06 · Excel import as a declared transition

## Objective
Turn the import's jump to `published` from an invisible bypass into an explicit, restricted, audited capability.

## Problem
`import_excel` writes `pipeline_status="published"` directly, bypassing adviser approval, RDCO intake, IERC ethics, ITSO technical and KTTO IP review. The docstring says this is intentional, but a bare assignment is indistinguishable from an oversight.

## Evidence
`records/views.py:274-356` — 82 lines of per-row model writes inside a per-row `except Exception`, ending in `Record.objects.create(..., pipeline_status="published")`. Permission is `IsStaff`, which under the current `is_django_staff` bypass means all four office roles. No audit event.

## Current State
An unaudited path to publication available to four roles.

## Proposed State
Import routes through `apply(record, "legacy_import", actor)`, restricted to RDCO, emitting an audit event per record.

## Scope
A `legacy_import` edge; role restriction; per-record audit event; extract the body into `records/importing.py` so it is testable without HTTP.

## Out of Scope
The spreadsheet parser (`parse_excel_import` is fine). The styled template download — deferred.

## Technical Approach
`import_rows(rows, actor) -> ImportResult`; the view becomes ~8 lines. Consider importing to a distinct status rather than `published` if imported records should not claim to have been reviewed — a decision for `F-03`.

## Dependencies
`W-01`.

## Risks
Low. Restricting to RDCO may remove access someone uses — confirm.

## Security Impact
Closes an unaudited publication path.

## Performance Impact
Neutral. Per-row `except Exception` should also log (`B-06`).

## SaaS Impact
Bulk import is a plausible onboarding capability for a new institution — worth keeping, correctly gated.

## Research/Thesis Impact
Imported records must be excluded from workflow metrics, or they distort turnaround figures. `W-04`'s events make that filterable.

## MVP Classification
POST-MVP — bulk import is not in the pilot workflow

## Priority
P3

## Complexity
M

## Acceptance Criteria
- [ ] Imported records are created via the lifecycle module, not a direct assignment.
- [ ] The endpoint is restricted to RDCO; others receive 403.
- [ ] Each imported record produces an audit event naming the importer.
- [ ] `import_rows` is unit-testable with a list of dicts and no HTTP.
- [ ] Per-row failures are logged and reported, not silently swallowed.

## Testing Requirements
Unit tests for the import service; an authorization test.

## Documentation Requirements
The bypass documented as a deliberate, audited capability in the SDD.

## Definition of Done
Merged; tests green; the status decision recorded in `F-03`.
