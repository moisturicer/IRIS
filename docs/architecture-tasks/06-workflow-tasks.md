# 06 — Workflow Tasks

Five tasks. The workflow is the best-designed part of IRIS; these tasks consolidate it rather than rebuild it.

**Context:** `reviews/services.py` (407 lines) is a genuine domain service with guarded transitions, a documented routing model, and a clearance-smart resubmission rule that is real domain insight. It owns 11 of the 18 places `pipeline_status` is written. The other seven live in views, guarded by hand-written HTTP 400s or nothing.

---

# WF-01 · One transition table for the record lifecycle

## Objective
Give the record lifecycle a single module owning every legal transition, replacing 18 assignment sites across four modules.

## Problem
The system's routing rule is written three times, seven transitions are unguarded, and there is no enumeration of legal edges — so nobody can answer "what can happen to this record next?" without reading three files.

## Current State

| Site | Transitions | Guard |
|---|---|---|
| `reviews/services.py` | 11 | `InvalidPipelineTransition` ✓ |
| `records/views.py:76` | 1 (`→ draft` on create) | n/a |
| `records/views.py:135-138` (`submit`) | 2 | hand-written 400 |
| `records/views.py:208` (`complete`) | 1 | hand-written 400 |
| `records/views.py:254` (`perform_destroy`) | 1 | **none** |
| `records/views.py:334` (`import_excel`) | 1 → `published` | **none** |
| `records/views.py:690-693` (delete decline) | 1 | none; re-derives the type rule |
| `records/services.py:33` (`soft_delete_record`) | 1 | none |

The rule *"Proposal → `adviser_review`, everything else → `rdco_intake`"* appears at `reviews/services.py:150-152`, `records/views.py:135-138`, and inverted at `records/views.py:690-693` (`"approved" if rt == "Proposal" else "published"`).

**SRS Module 5 is still marked draft**, so this *will* change — currently in three places.

**Relates to Jira `IR-41`** ("[Backend] State Transition API & Validation Matrix"), which asks to build a `WorkflowEngineService` validating that "an Adviser cannot approve a KTTO stage." Much of that exists in `reviews/services.py`; the task should be rewritten to consolidate rather than build from scratch. See `12-jira-ready-tasks.md`.

## Proposed State
`records/lifecycle.py` holding a declarative table `(from_status, event, actor_role) → to_status` and one entry point `apply(record, event, actor)` that wraps the write in `transaction.atomic()`. Views name events, never statuses.

## Scope
- The transition table and `apply()`
- Migrate all 18 assignment sites
- `can_transition(record, event, actor)` predicate for UI affordances
- Excel import becomes a declared `legacy_import` event (see `WF-04`)

## Out of Scope
Changing workflow *semantics*. The role→stage authorization rule (`WF-02`).

## Technical Approach
A plain dict keyed by `(from_status, event)`. **Deletion test passes:** removing the module scatters ~30 rules back across 18 sites in four modules — complexity concentrates rather than moves.

Rejected alternatives: `django-fsm` (unmaintained upstream; ~30 rows do not need a library); moving everything into `reviews/services.py` (records-owned edges like create, delete and import do not belong in the `reviews` app).

## Dependencies
`BE-05` (enums) first. **`TEST-01` first** — this touches the core write path and must not be attempted without an import-smoke test and preferably transition tests.

## Risks
**Medium — the highest-risk refactor in this backlog.** It touches every write path for the central domain object. Sequence it after tests exist, not before.

## Security Impact
Positive: the Excel import's unguarded jump to `published` becomes a declared, auditable edge rather than an invisible bypass.

## Performance Impact
Neutral.

## Deployment Impact
None.

## Framework Impact
None — plain Python.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] `records/lifecycle.py` enumerates every legal `(from, event, role) → to` edge.
- [ ] `grep -rn "pipeline_status = " backend/apps/` returns matches only in `lifecycle.py`.
- [ ] An illegal transition raises `InvalidPipelineTransition` and leaves the record unchanged.
- [ ] A parametrised test covers every legal edge and a representative sample of illegal ones, with no HTTP.
- [ ] The type-routing rule (`Proposal → adviser_review`) exists in exactly one place.
- [ ] All existing workflow behaviour is unchanged (regression suite green).

## Definition of Done
Merged; table-driven tests in CI; `IR-41` rewritten and linked; SRS Module 5 traceability recorded.

## Complexity
L

## Suggested Jira Type
Story

## Suggested Priority
High

## Suggested Labels
`backend`, `workflow`, `architecture`, `refactor`, `fr-m5-01`, `mvp-recommended`

---

# WF-02 · One policy answers "who may review what, when"

## Objective
Collapse two independent encodings of the role→stage mapping into one consulted by both the queue and the authorization check.

## Problem
The mapping is written twice, in two modules, in two shapes, with no shared source — so a record can appear in a reviewer's pending queue and then be refused when they act on it.

## Current State

`reviews/views.py:61-67` builds the **pending queue**:

```python
role_to_statuses = {
    "Adviser": ["adviser_review"],
    "RDCO":    ["rdco_intake", "rdco_review"],
    "ITSO":    ["itso_review"],
    "IERC":    ["parallel_review"],
    "KTTO":    ["itso_review", "parallel_review"],
}
```

`reviews/services.py:76-93` **authorizes the decision**:

```python
if role_name == "Adviser":
    return status == "adviser_review" and record.adviser_id == user.pk
if role_name == "RDCO":
    return status in ("rdco_intake", "rdco_review")
```

The adviser case already differs: the queue filters `records.filter(adviser=request.user)` separately at `:78`, while the service checks `record.adviser_id == user.pk` inline.

## Proposed State
A `ReviewPolicy` exposing `stages_for(role)` and `can_act(user, record)`, consumed by the queue, the service and `WF-01`'s lifecycle module.

## Scope
- Extract `_can_review` and `_can_submit_clearance` into a policy object
- Derive the pending queue from the policy rather than a parallel dict
- Remove the `is_django_staff` bypass (with `SEC-05`)

## Out of Scope
DRF permission classes for HTTP-level checks (`BE-03`/`SEC-03` cover those).

## Technical Approach
A plain class or module of pure functions. `BE-05`'s `ClearanceOffice` enum carries the role↔office mapping, removing a third encoding.

## Dependencies
`BE-05`, `SEC-05` (`ARCH-04` decision).

## Risks
Low, provided the current behaviour is captured in tests first.

## Security Impact
Positive: one place to audit the question NFR-S4 asks.

## Performance Impact
Neutral.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] One module answers both "which records are pending for this user" and "may this user act on this record".
- [ ] A record appearing in a reviewer's pending queue is always actionable by that reviewer (property test over the six roles).
- [ ] A record absent from the queue is always refused (403/400).
- [ ] The role→stage mapping exists in exactly one place.
- [ ] Policy tests run without HTTP.

## Definition of Done
Merged; policy tests in CI; queue and authorization proven consistent.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`backend`, `workflow`, `rbac`, `refactor`, `nfr-s4`

---

# WF-03 · Audit every review and clearance decision

## Objective
Record the workflow decisions that matter in the audit log, as FR-M8-02 and NFR-S5 require.

## Problem
The audit log records logins, views, uploads, downloads, PIN events, role changes and session revocations — but **not a single approval**.

## Current State
`AuditEvent.EVENT_TYPE_CHOICES` (`audit/models.py:29-44`) lists 14 types; none covers approve, decline, reject or clear. `grep -rn "create_audit_event" backend/apps/reviews/` returns two matches, both `PIN_GENERATED`/`PIN_VERIFIED`.

`Review` and `RecordClearance` rows record decisions, which is most of the value — but they are domain records, not an audit trail: `resubmit_record` (`reviews/services.py:381`) **deletes all clearance rows** on a sequential-decline resubmission, they carry no IP or user-agent, and they are not queryable through the audit endpoint an auditor would use.

`ACCESS` is also overloaded — `records/views.py:223` logs a tag edit as `ACCESS`.

**Relates to Jira `IR-42`** ("[Security] Workflow Transition Logging"), which is consistent with this and should be linked rather than duplicated.

## Proposed State
`REVIEW_DECISION`, `CLEARANCE_DECISION` and `TAG_CHANGE` event types, emitted from the service layer inside the transition's transaction.

## Scope
- Add the three event types
- Emit from `approve_record`, `decline_record`, `reject_record`, `submit_clearance`, `resubmit_record`
- Record stage, decision, resulting status and comment presence in `metadata`
- Give tag edits their own type

## Out of Scope
Immutability (`SEC-07`). Retention automation (`DEP-04`).

## Technical Approach
Emit inside `WF-05`'s `transaction.atomic()` so the audit event cannot diverge from the decision it records.

## Dependencies
`WF-05` (transaction). Pairs with `SEC-07`.

## Risks
Low.

## Security Impact
High for compliance: the approval chain becomes auditable independently of mutable domain rows.

## Performance Impact
One insert per transition; negligible.

## Deployment Impact
None (JSONB metadata absorbs the new fields).

## Framework Impact
None.

## MVP Classification
**MVP Required** — a thesis-scope compliance property, not a nice-to-have

## Acceptance Criteria
- [ ] Every approve/decline/reject/clear writes exactly one audit event.
- [ ] The event records stage, decision and resulting pipeline status.
- [ ] Audit events survive a resubmission that deletes clearance rows.
- [ ] Tag edits emit `TAG_CHANGE`, not `ACCESS`.
- [ ] Filtering the audit log by `REVIEW_DECISION` returns the full approval history for a record.
- [ ] A rolled-back transition writes **no** audit event.

## Definition of Done
Merged; tests asserting one event per transition and none on rollback; `IR-42` linked.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`backend`, `workflow`, `audit`, `compliance`, `fr-m8-02`, `mvp-required`

---

# WF-04 · Make the Excel import a declared transition

## Objective
Turn the import's jump to `published` from an invisible bypass into an explicit, restricted, audited capability.

## Problem
`import_excel` writes `pipeline_status="published"` directly, bypassing adviser approval, RDCO intake, IERC ethics, ITSO technical and KTTO IP review. The docstring says this is intentional — but a bare assignment is indistinguishable from an oversight.

## Current State
`records/views.py:274-356`. 82 lines of per-row model writes inside a per-row `except Exception`, ending in:

```python
record = Record.objects.create(..., pipeline_status="published")
```

Permission is `IsStaff` — which per `SEC-05` means all four office roles, including ITSO and IERC. No audit event is emitted. The docstring reads: *"Legacy imports bypass the review pipeline — staff is the implicit reviewer."*

Bulk import is FR-M2-04, so the capability is legitimate; the way it is expressed is not.

## Proposed State
Import routes through `WF-01`'s `apply(record, "legacy_import", actor)`, restricted to RDCO, emitting an audit event per record.

## Scope
- Add a `legacy_import` edge to the transition table
- Restrict the endpoint to RDCO (or per an explicit decision)
- Emit an audit event per imported record
- Extract the import body into `records/importing.py` so it is testable without HTTP

## Out of Scope
Changing the spreadsheet format or parser (`parse_excel_import` is fine).

## Technical Approach
`import_rows(rows, actor) -> ImportResult`. The view becomes ~8 lines. Consider importing to a distinct status (e.g. `archived`) rather than `published` if imported records should not claim to have been reviewed — worth a decision.

## Dependencies
`WF-01`. Overlaps the service-extraction half of the review's `BE-5`.

## Risks
Low. Restricting to RDCO may remove access someone is using — confirm.

## Security Impact
Closes an unaudited path to publication available to four roles.

## Performance Impact
Neutral. Per-row `except Exception` swallowing should also log (`BE-07`).

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] Imported records are created via the lifecycle module, not a direct assignment.
- [ ] The import endpoint is restricted to RDCO (or the decided role) — others receive 403.
- [ ] Each imported record produces an audit event naming the importer.
- [ ] `import_rows` is unit-testable with a list of dicts and no HTTP request.
- [ ] Per-row failures are logged, not silently swallowed, and reported in the response log.

## Definition of Done
Merged; unit tests for the import service; audit events verified; the status decision recorded.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`backend`, `workflow`, `import`, `security`, `fr-m2-04`

---

# WF-05 · Wrap workflow transitions in transactions

## Objective
Prevent partially-applied transitions, one of which can advance a record past an office that never cleared it.

## Problem
Every transition performs 2–4 writes with no transaction boundary, and notifications fire before commit.

## Current State
`grep -rn "atomic" backend/apps/` returns exactly one match — `accounts/views.py:23`, in registration. **None in `reviews/` or `records/`.**

`approve_record` at `rdco_intake` performs, in order: create `Review` → `get_or_create` two `RecordClearance` rows → save `Record.pipeline_status` → `notify_record_reviewed`.

Failure modes:
- Fail after the `Review`: a review row records an approval that did not advance the record. The reviewer sees their decision recorded; the owner sees the record stuck.
- **Fail after one clearance row:** one office has a pending row, the other does not. `_all_clearances_done` then returns `True` prematurely once that single office clears — **the record advances to `rdco_review` having been cleared by one office instead of two.** This is a correctness failure with a security character: it defeats the parallel-review requirement.
- A decline that later rolls back still emails the owner, because `notify_*` runs before commit.

Related to **NFR-R3** (data integrity under concurrency).

## Proposed State
Each of the five transition functions wrapped in `transaction.atomic()`; notifications dispatched via `transaction.on_commit`.

## Scope
- `transaction.atomic()` around `approve_record`, `decline_record`, `reject_record`, `submit_clearance`, `resubmit_record`
- Move every `notify_*` call to `transaction.on_commit(...)`
- Same for the `WF-03` audit events (inside the transaction)

## Out of Scope
`ATOMIC_REQUESTS = True` globally — rejected: it would hold a transaction open across email dispatch and file I/O on every request.

## Technical Approach
Decorate or wrap; `on_commit` for side effects. Naturally absorbed into `WF-01` if that lands first.

## Dependencies
None. Complements `WF-01` and `WF-03`.

## Risks
Low. Verify `on_commit` fires in tests — it does not run under `TestCase` unless `captureOnCommitCallbacks` is used.

## Security Impact
Prevents a record advancing without all required clearances.

## Performance Impact
Negligible; slightly longer transactions.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] Forcing an exception after the `Review` insert leaves `pipeline_status` unchanged and no `Review` row persisted.
- [ ] Forcing an exception between the two `RecordClearance` inserts leaves neither row.
- [ ] A rolled-back transition sends **no** notification and writes **no** audit event.
- [ ] All five transition functions are covered by such a test.
- [ ] Concurrent clearance submissions for two offices produce exactly two rows (`NFR-R3`).

## Definition of Done
Merged; rollback tests in CI using `captureOnCommitCallbacks`; `NFR-R3` evidence recorded for `VAL-15`.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
High

## Suggested Labels
`backend`, `workflow`, `data-integrity`, `nfr-r3`, `mvp-required`
