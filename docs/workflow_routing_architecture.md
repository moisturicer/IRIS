# Workflow routing — current code, settled model, and the path between them

> **Read with [ADR-032](adr/032-adviser-first-review-and-office-reviewer-pools.md) (Proposed 2026-09-26),
> which reopened the workflow at the project lead's instruction.** Everything below about the
> **intake** party, Intake & Triage queues and UI, the Proposal "complete" act, and RDCO as a
> mandatory decider for Thesis/Project is **superseded**. The code mapping, migration shape,
> tracker derivation and test seams still hold. ADR-032 §14 lists how each unbuilt IR-255 slice
> changes. The phrase "does not reopen it" below was true when written.

**Status: the implementation companion to two Accepted ADRs.** The decisions are in
[ADR-021](adr/021-reviewer-directed-routing.md) and
[ADR-022](adr/022-explicit-document-requests.md). The workflow was settled on 2026-09-15 by the
project lead, and this document does not reopen it.

This document covers what the code does today, exactly where it differs from the settled model,
and how to get from one to the other in slices that can each be tested. Every claim about
current behaviour is cited to a file and line, read from the working tree.

Tracked on [IR-254](https://citiris.atlassian.net/browse/IR-254) (design) and
[IR-255](https://citiris.atlassian.net/browse/IR-255) (implementation).

**Contents:** §1 settled model · §2 current state · §3 conflicts · §4 code mapping · §5 data
model · §6 state mapping · §7 migration plan · §8 tracker · §9 frontend · §10 test migration ·
§11 what is preserved · §12 Jira breakdown · §13 terminology · §14 considerations outside the
workflow.

---

## 1. The settled model

IRIS routes research through reviewers who decide where it goes next. It is not a fixed office
pipeline. Every record carries:

- concurrent **assignments** across six parties;
- a **routing history**;
- **document requests**;
- **resubmission requests**;
- a **clearance ledger**;
- a **review history**.

| | Proposal | Thesis / Research | Project |
|---|---|---|---|
| Path | Submitter → Adviser → [specialists if needed] → **Adviser or RDCO completes** | Submitter → Intake & Triage → [specialists if needed] → **RDCO final review → decision** | same as Thesis |
| Enters at | `adviser` | `intake` | `intake` |
| Decides | assigned Adviser **or** RDCO | RDCO | RDCO |
| RDCO mandatory? | **No** | Yes | Yes |
| In Discover | Never | when `published` | when `published` |

**Parties:** `intake` · `adviser` · `itso` · `ierc` · `ktto` · `rdco`.

`intake` and `rdco` are different parties even though RDCO staff fill both. Staff see the label
"Intake & Triage"; students see "Intake".

**Withdrawn rule.** The project lead withdrew the statement *"a Proposal MUST be capable of
reaching RDCO for a final institutional decision"*. Two statements depended on it and are
withdrawn too: the instruction that a Proposal "still proceeds to RDCO", and the defect "Proposal
approval ending without a real RDCO final institutional decision". Nothing below relies on any of
the three.

---

## 2. What the code does today

`backend/apps/records/lifecycle.py` (IR-136) defines:

- `STAGES` — five nodes;
- `TRANSITIONS` — about 30 edges keyed by `(from_status, event)`.

`Record.pipeline_status` holds a single value. Four resolvers compute where a record goes next;
no reviewer chooses:

| Resolver | Line | What it computes |
|---|---|---|
| `_resolve_first_status` / `first_status_for` | `:691`, `:737` | Proposal → `adviser_review`; anything else → `rdco_intake` |
| `_resolve_enter_clearance_stage` | `:505` | Which `RecordClearance` rows to create, from three booleans the student set |
| `_clearance_entry_for` | `:532` | Whether the record goes to `itso_review`, `parallel_review` or `rdco_review`, given its office set |
| `_resolve_after_clearance` | `:553` | ITSO-then-IERC ordering; once every office has cleared, the record goes to `rdco_review` |

**Already correct, so not rebuilt:**

- **A record is not forced through every office.** `_clearance_entry_for([])` returns
  `rdco_review` (`:550`).
- **IERC and KTTO already clear concurrently**, gated by `_all_clearances_done` (`:729`).
- **A decline by one office preserves the other offices' clearances** (`:606`). This is the
  thesis contribution.

---

## 3. Conflicts with the settled model

Each item is a defect relative to the settled MVP.

### 3.1 The defects listed in the settling instruction

| # | Defect | Evidence |
|---|---|---|
| 1 | `rdco_intake` is used as an RDCO identity, and intake can reject | `core/enums.py:57` labels it "RDCO Intake **Review**"; `:89` makes it a `ReviewStage`; `lifecycle.py:285` defines `(RDCO_INTAKE, REJECT) → rejected`; `notifications/services.py` shows "RDCO (intake review)"; `EvaluationPage.tsx:53` |
| 2 | A Thesis/Research record cannot reach ITSO | `lifecycle.py:519`: `if type_name == PROJECT and record.requested_itso`. ADR-018 states this is intended |
| 3 | *Withdrawn* — see §1. What remains is a real gap: the **Adviser cannot complete a Proposal and RDCO cannot decide one** | `lifecycle.py:495` stops a Proposal at `approved`; `/complete/` requires RDCO (`records/views.py:345`, `get_permissions` at `:121`) |
| 4 | Fixed `itso_review` / `parallel_review` stages are the routing model | `lifecycle.py:242–249`. KTTO belongs to both groups, which is why `_stage_reviewed_by` (`:655`) exists |
| 5 | Only one assignee can be represented | `pipeline_status` is a single value. `reviews/views.py:63–68` builds the review queue from role → status mappings |
| 6 | The frontend works out who owns a record by itself | `PaperViewPage.tsx:44–48` (`canReview` switch), `workspaceStages.ts:36–66`, `:106–118` (`currentStage`, `currentOfficeLabel`) |
| 7 | A document request is only free text | No mechanism exists. ADR-018 §Status records this |
| 8 | Resubmission loses or wrongly resets history | `lifecycle.py:651` deletes **every** `RecordClearance` after a sequential decline. `Record` stores only `resubmission_count` and `last_resubmitted_at`, so earlier resubmissions cannot be recovered |

### 3.2 Additional conflicts found while mapping the code

| | Conflict | Evidence | Smallest change |
|---|---|---|---|
| A | **Specialist offices can terminally reject a record** | `reviews/services.py:submit_clearance` maps `rejected` → `WorkflowEvent.REJECT` → `lifecycle.py:316`, `:328`. `EvaluationPage.tsx:39–45` offers Reject to every reviewer | Offices record a negative finding and route onward (ADR-021 §7) |
| B | **A single `declined` value cannot represent concurrent resubmission requests** | `PipelineStatus.DECLINED`; `resubmit_record` reads only the *last* decline `Review` | `ResubmissionRequest` rows; `declined` stops being stored (ADR-021 §4) |
| C | **The resubmit guard accepts only an upload**, but the settled model allows revising metadata only | `reviews/services.py:resubmit_record` requires a `RecordUpload` newer than the last decline | Accept an upload **or** an owner edit to metadata (ADR-021 §11) |
| D | **A second, broken resubmission entry point** | `records/views.py:submit` accepts `DECLINED` and says it "also handles resubmission", but no `(declined, submit)` edge exists, so `apply()` raises | Remove that branch. `/reviews/resubmit/` remains the only entry point |
| E | **Discover lists Proposals, and Ask IRIS cites them** | Only Proposals reach `approved` and `completed`; both are in `PUBLICLY_VISIBLE_STATUSES` (`core/enums.py:72`), which feeds `visible_to()` (`records/models.py:118`), the list view (`records/views.py:94`) and `ai/services/retrieval.py:109` | Narrow the tuple to `(PUBLISHED,)` (ADR-021 §13) |
| F | **Deletion depends on visibility** | `perform_destroy` (`records/views.py:148`) and the `REQUEST_DELETE` edges (`lifecycle.py:375`) branch on `PUBLICLY_VISIBLE_STATUSES` | Add `DELETE_REVIEW_STATUSES`. Without it, E would let owners soft-delete approved Proposals |
| G | **A dead branch would become live if routing were added as extra edges** | `_resolve_after_adviser_review` ends `else PUBLISHED`; an Adviser holding a Thesis would publish it | Delete the resolver; do not extend the table |
| H | **The frontend's stage type is incomplete** | `types/reviews.ts:3` omits `"ierc"` | Fix in IR-259 |

**No conflict found makes the settled design technically impossible.**

---

## 4. Current code → new model, symbol by symbol

### 4.1 Backend

| Current | Becomes | Slice |
|---|---|---|
| `core/enums.py` `PipelineStatus` | `IN_REVIEW` added; `ADVISER_REVIEW`, `RDCO_INTAKE`, `ITSO_REVIEW`, `PARALLEL_REVIEW`, `RDCO_REVIEW`, `DECLINED` removed | IR-256 adds `IN_REVIEW` beside the old values; IR-260 removes them |
| `ReviewStage.RDCO_INTAKE = "rdco_intake"` | `ReviewStage.INTAKE = "intake"`; `Party = ReviewStage` alias | IR-256 adds `INTAKE` beside `RDCO_INTAKE`, plus the alias and `ASSIGNABLE_PARTIES` (the six parties without `rdco_intake`); IR-260 renames the stored rows and removes `RDCO_INTAKE` |
| `ReviewDecision` | `NEGATIVE_FINDING` added; `DECLINED` relabelled "Resubmission requested" (stored value unchanged) | IR-256 |
| `ClearanceStatus` | `NOT_CLEARED` added; `REJECTED` kept for history, no new writes | IR-256 adds `NOT_CLEARED` (and widens the column); IR-260 stops writing `REJECTED` |
| `PUBLICLY_VISIBLE_STATUSES` | `(PUBLISHED,)` | IR-264 |
| — | `DELETE_REVIEW_STATUSES = (PUBLISHED, APPROVED, COMPLETED)` | IR-264 |
| `lifecycle.STAGES` | `PARTIES` (labels, clears-or-gates, allowed route targets) | IR-260 |
| `lifecycle.TRANSITIONS` (~30 edges) | Record-level edges only: submit, decide, complete, delete, restore | IR-260 |
| `_resolve_first_status`, `first_status_for` | `ENTRY_PARTY[record_type]` | IR-260 |
| `_resolve_enter_clearance_stage`, `_clearance_entry_for`, `_resolve_after_clearance`, `_stage_reviewed_by`, `_resolve_after_adviser_review` | **Deleted** | IR-260 |
| `_all_clearances_done` | `hand_back_to_decider()` (ADR-021 §10) | IR-260 |
| `_resolve_after_resubmission` | `resolve_resubmission()` over `ResubmissionRequest`; the delete at `:651` is removed | IR-260 |
| `resubmission_policy()`, `ResubmissionPolicy` | **Unchanged** | — |
| `reviews/services.py` `approve_record`, `decline_record`, `reject_record`, `submit_clearance` | `clear()`, `record_finding()`, `request_resubmission()`, `decide()`, `complete_proposal()` — each checks the party and holding, and writes `Review` against the assignment | IR-260 |
| `_can_review`, `_can_submit_clearance` | `holds_open_assignment()` + `can_decide(record, user, acting_as)` in `core/permissions.py` | IR-260 |
| `ROLE_TO_OFFICE` | `ROLE_TO_PARTIES` (`RDCO` → `{intake, rdco}`) | IR-260 |
| `resubmit_record` | Resolves open `ResubmissionRequest`s; relaxed guard; nothing deleted | IR-260 |
| — | `route()` | IR-260 |
| `reviews/views.py:47 pending` | Queue from active assignments for the viewer's parties; RDCO gets an intake queue and a final-review queue | IR-260 |
| `reviews/views.py:113 submit` | Replaced by action endpoints (clear / finding / resubmission / decide) | IR-260 |
| `reviews/views.py:168 resubmit` | Same endpoint, new service | IR-260 |
| `reviews/views.py:215 declined` | Records with an open `ResubmissionRequest` | IR-260 |
| `records/views.py:163 submit` | Opens the entry assignment and writes a `RoutingEvent` from the submitter; `DECLINED` branch removed | IR-257 (shadow) / IR-260 |
| `records/views.py:345 complete` | Assigned Adviser **or** RDCO | IR-260 |
| `records/views.py:148 perform_destroy` | Branches on `DELETE_REVIEW_STATUSES` | IR-264 |
| `records/views_dashboard.py:13, 33, 36` | Counts by `workflow_state` / `PUBLICLY_VISIBLE_STATUSES` | IR-260 / IR-264 |
| `records/serializers.py:100, 109` (`clearances[]`, `resubmission{}`) | **Kept.** `workflow_state`, `current_holders`, `can_act` added | IR-258 |
| `reviews/serializers.py:9 queue_rows` | Keyed on assignment instead of status; `peer_summary` kept | IR-260 |
| `reviews/clearance_state.py` | **Kept.** `declining_office` generalises to `requesting_parties` | IR-260 |
| `notifications/services.py` `notify_record_reviewed` (`:111`), `notify_clearance_result` (`:253`), `notify_resubmit` (`:378`), `notify_proposal_completed` (`:486`) | Plumbing kept; recipients come from assignments; labels come from party labels; new routed / document-requested / decided notices | IR-260, IR-262 |
| `records/management/commands/seed_demo.py` | Seeds every new `workflow_state` | IR-260 |

### 4.2 Frontend

| Current | Becomes | Slice |
|---|---|---|
| `lib/constants.ts:44–50`, `lib/utils.ts:17–23`, `components/shared/StatusBadge.tsx` | Stored statuses plus `workflow_state`; labels come from the API | IR-259 |
| `lib/workspaceStages.ts` `currentStage`, `currentOfficeLabel`, `needsAuthorAction` | Read `workflow_state` and `current_holders`; `needsAuthorAction` = open resubmission **or** document request | IR-259 / IR-263 |
| `features/records/paper-view/ClearanceTrack.tsx` (105 lines) | `ReviewRoutingTracker`; the `preserved` badge is kept verbatim. **Done in IR-258**, whose card asks for the panel on the paper view; the reviewer-page placement stays IR-259's | IR-258 |
| `features/review/PeerClearanceStrip.tsx` (59 lines) | Reads the tracker; still shows no peer comments | IR-259 |
| `PaperViewPage.tsx:44–48 canReview` | The server's `can_act` | IR-259 |
| `features/review/EvaluationPage.tsx` (359 lines) | Rebuilt around `acting_as`: six actions plus decision controls per ADR-021 §7 | IR-261 |
| `features/review/ReviewQueuePage.tsx` (200 lines) | Queue from assignments; RDCO sees two tabs | IR-261 |
| `api/reviews.ts:14 submit` | `route`, `clear`, `finding`, `requestResubmission`, `decide` | IR-261 |
| `api/records.ts` complete call | Available to the assigned Adviser | IR-261 |
| `types/reviews.ts:3` | `Party` type with all six values | IR-259 |
| `DocumentsPage.tsx:436`, `PaperViewPage.tsx:342` resubmit | Same call; the error is shown prominently (IR-233 candidate 1) | IR-233 / IR-259 |
| — | `RerouteDialog`, `RequestDocumentDialog`, `ActionRequiredPanel` | IR-261, IR-263 |

---

## 5. Data model

```
RecordAssignment
├── record       FK Record, related_name="assignments"
├── party        CharField(choices=Party)
├── state        active | completed | withdrawn
├── opened_by    FK User, null        (null = opened by submission or the system)
├── opened_at    DateTime
├── closed_by    FK User, null
├── closed_at    DateTime, null
└── reason       TextField            ("backfilled from review history (IR-257)" on backfilled rows)
    UniqueConstraint(record, party, condition=state="active")

RoutingEvent
├── record, actor (FK User), from_party (null = submitter), to_party
├── reason, group_id (UUID), created_at
    Index(record, created_at)

ResubmissionRequest
├── record, party, assignment (FK, null), review (FK Review)
├── requested_by, reason
├── state        open | resubmitted | withdrawn
├── created_at, resolved_by (null), resolved_at (null)
    Index(record, state)

DocumentRequest, DocumentRequestItem           — ADR-022 §1

Review            + assignment FK (null)
RecordClearance   status widened from 10 to 20 characters for `not_cleared` (IR-256); otherwise unchanged
Record            pipeline_status narrowed; resubmission_count / last_resubmitted_at kept
                  (IR-139's `preserved` rule reads last_resubmitted_at)
```

**The vocabulary values land in step 1, not at the cutover.** `in_review`, `intake`,
`negative_finding` and `not_cleared` are added in IR-256 beside the values they will replace,
which is what the expand step is for and what IR-256's card asks for; the old values stay until
IR-260 removes them. **Adding a value to an enum is not inert**: `ReviewWriteSerializer`
validated `status` against every `ReviewDecision` value, so `negative_finding` became postable to
`/reviews/submit/` the moment it existed, and was recorded as a decline. IR-256 pins that
serializer to the three decisions the endpoint implements (`SUBMITTABLE_DECISIONS`), and IR-260
replaces it. Anything else that iterates a workflow enum — `lifecycle.py`'s soft-delete edges,
IR-140's matrix, DRF's OPTIONS metadata — takes the new values silently, which is safe only
because nothing stores them yet.

**Deliberate constraints:**

- **An assignment has no outcome field.** Outcomes live in `Review` and `RecordClearance`.
  Duplicating them on the assignment would create a second source of truth.
- **No column stores `workflow_state`**, and a test enforces that.
- **None of the three tables is ever deleted from by a workflow action.**

`Party` is `ReviewStage`, so `Office ⊆ Party` still holds (`test_enum_vocabulary.py`).

---

## 6. State mapping — current status to new rows

This table drives the IR-257 backfill and the IR-260 contract migration. Party names map from
`Review.stage` as follows: `adviser`→`adviser`, `rdco_intake`→`intake`, `rdco`→`rdco`,
`itso`/`ierc`/`ktto` unchanged.

| Current `pipeline_status` | New `pipeline_status` | Active assignments | Completed assignments | Open requests |
|---|---|---|---|---|
| `draft` | `draft` | — | — | — |
| `adviser_review` | `in_review` | `adviser` | — | — |
| `rdco_intake` | `in_review` | `intake` | — | — |
| `itso_review` | `in_review` | every office with a `pending` clearance | `intake`; every office with a `cleared` clearance | — |
| `parallel_review` | `in_review` | every office with a `pending` clearance | `intake`; every office with a `cleared` clearance | — |
| `rdco_review` | `in_review` | `rdco` | `intake` and every cleared office | — |
| `declined` | `in_review` | the declining party (from the last decline `Review.stage`), plus every office with a `pending` clearance | `intake` (if the record passed it) and every cleared office | one `ResubmissionRequest(party = declining party, review = that Review)` |
| `approved` · `completed` · `published` · `rejected` · `pending_delete` | unchanged | — | one per distinct `Review.stage`, dated from those reviews | — |

**No `RoutingEvent` is backfilled.** The old model never recorded who sent a record where, and
this migration does not invent it. The tracker says *"Routing history recorded from
<migration date>"*.

**One visible behaviour change for records already declined at migration time.** Under the old
code, a sequential decline at `rdco_review` would have deleted every clearance on resubmission.
After migration those clearances are preserved. This is intended (ADR-021 §11); note it in the
IR-260 PR.

---

## 7. Migration plan

The plan follows expand → migrate → contract. Each step is its own PR, keeps the suite green,
and can be deployed.

| Step | Slice | Schema | Behaviour | Verification |
|---|---|---|---|---|
| 0 | IR-233 | none | none | Regression test is committed as `xfail(strict=True)` and its failure is recorded |
| 1 | IR-256 | **additive**: 3 tables, 1 nullable FK, the new vocabulary values beside the old ones, and `RecordClearance.status` widened to 20 for `not_cleared` | none | Constraint tests; migration run against a copy of a seeded database; record-detail and review-queue snapshots identical before and after |
| 2 | IR-257 | data only (backfill) | services **also** write the new tables (dual-write) | IR-140's matrix acts as oracle: shadow rows equal the §6 mapping in every cell; per-status counts before and after |
| 3 | IR-258 + IR-259 | none | the frontend reads `workflow_state` and the tracker; no screen reads stage values | grep gate; Vitest + axe |
| 4 | IR-260 | **contract** (below) | assignments become authoritative | New suite green; IR-233 flips to passing |
| 5 | IR-261 | none | the new reviewer actions are exposed | Vitest + axe |
| 6 | IR-262 + IR-263 | additive (ADR-022) | document requests | as listed on each card |
| — | IR-264 | none | visibility narrowed | Authorization tests, including retrieval |

### 7.1 The contract migration (step 4)

**Before running it:**

1. `pg_dump` the `postgres_data` database. The backup is the rollback.
2. Run the migration against a copy of a seeded database. Record per-status counts before and
   after in the PR.

**Forward, in one migration, in this order:**

1. **Consistency gate.** For every in-flight record, check that its assignment rows match §6
   given its current status and clearances. If any record fails, **raise and list its id**. The
   migration must not guess.
2. `Review.stage`: `rdco_intake` → `intake`.
3. `declined` records: confirm an open `ResubmissionRequest` exists, which the gate already did.
4. `pipeline_status` ∈ {five stage values, `declined`} → `in_review`.
5. `AlterField` choices on `pipeline_status` and `Review.stage`.

**Reverse:** irreversible. Once the new model has written anything — concurrent assignments
across parties, Adviser + ITSO holding together, several open resubmission requests — the old
single-value model cannot represent it, and any automatic reverse would lose data silently.
Rollback means restoring the step-0 backup. The migration's `reverse_code` raises with that
instruction.

**Release rule:** merge IR-261 straight after IR-260, with no pilot deployment in between.
Step 3 already moved the frontend's *reads* onto the new model. Only the reviewer *actions*
change at step 4, and IR-261 supplies them, so no throwaway compatibility layer is needed.

---

## 8. The Review & Routing Tracker

### 8.1 Payload

**Document-request fields are authorised separately from the rest of the tracker** (ADR-022
§Amendment 5, 2026-09-24). A viewer who may read the Record gets every field below. The
document-request fields are the exception:
- the per-party `awaiting_document` flag, which names the party that asked;
- `document_requests`: the requests, messages, items and their history.

These go only to **workflow participants**: owners and submitters, and anyone who can staff a
party that holds, held or acted on an assignment on the Record, or that took part in the
request. A role alone never qualifies, and neither does being able to read a published Record.

For anyone else, both fields are `null`, meaning "not disclosed". `[]` would wrongly say the
Record has no requests. The generic `workflow_state` still reads `awaiting_document` while a
request is open.

Implementation: IR-349. Until it lands, the shipped tracker returns both fields to every reader
of the Record.

**As a workflow participant sees it:**

```
GET /api/v1/records/<id>/tracker/
{
  "workflow_state": "in_review",
  "record_type": "Thesis / Research",
  "current_holders": [{"party": "ierc", "label": "IERC", "opened_at": "…", "opened_by": "…"}],
  "parties": [
    {"party": "intake", "label": "Intake & Triage", "state": "completed", "outcome": "cleared", "at": "…"},
    {"party": "itso",   "label": "ITSO",            "state": "completed", "outcome": "cleared", "preserved": true},
    {"party": "ierc",   "label": "IERC",            "state": "active",    "awaiting_document": true},
    {"party": "ktto",   "label": "KTTO",            "state": "not_requested"},
    {"party": "adviser","label": "Adviser",         "state": "not_requested"},
    {"party": "rdco",   "label": "RDCO Final",      "state": "awaiting"}
  ],
  "routing_history":      [{"group_id": "…", "from": "intake", "to": ["itso","ierc"], "actor": "…", "reason": "…", "at": "…"}],
  "routing_recorded_from": "2026-09-…",
  "reviews":              [ … Review rows, newest last … ],
  "resubmissions":        [ … ResubmissionRequest rows … ],
  "document_requests":    [ … ADR-022 … ],
  "clearances":           [ … IR-139 payload, unchanged … ]
}
```

**As a non-participant sees the same Record**, such as a public reader or an uninvolved office:
the same payload, except for the document-request fields.

```
  "workflow_state": "awaiting_document",          ← generic state: still shown
  "parties": [
    …
    {"party": "ierc", "label": "IERC", "state": "active", "awaiting_document": null},
    …                                              ← every row's flag is null
  ],
  "document_requests": null                        ← not disclosed; never []
```

### 8.2 What the tracker must answer, and where each answer comes from

| Question | Derived from |
|---|---|
| Current active reviewers or offices | `RecordAssignment.state = active` |
| Completed reviews | `state = completed`, with the party's latest `Review` as the outcome |
| Active reviews | `state = active` and the party has at least one `Review` |
| Requested but not yet started | `state = active` and the party has no `Review` |
| Offices never requested | Parties with no assignment row at all (see RDCO rule below) |
| Document requests and their status | `DocumentRequest` + items. **Workflow participants only** (ADR-022 §Amendment 5; IR-349). `null` for anyone else |
| Routing history | `RoutingEvent`, grouped by `group_id` |
| Review history | `Review` |
| Resubmission history | `ResubmissionRequest` |

**RDCO's row:**

- **Thesis/Research and Project:** never `not_requested`. It shows `awaiting` until RDCO has an
  assignment.
- **Proposal:** `not_requested` unless RDCO has actually been routed to.

**`workflow_state`** is computed in one function, first match wins:

1. `awaiting_resubmission`
2. `awaiting_document`
3. `submitted`
4. `final_review`
5. `in_review`

The definitions are in ADR-021 §4. `submitted` must come before `final_review`; otherwise a new
Proposal would show as `final_review`, because its entry party is also a deciding party.

**Access:** `Record.objects.visible_to(user)`. A refusal is a 404, identical to a missing record.

---

## 9. Frontend workflow and UI

### 9.1 Tracker (IR-259)

The tracker is a persistent panel on the paper view and on the reviewer page. It has two parts.

**Party list** — six rows with a glyph:

| Glyph | Meaning |
|---|---|
| ✓ | completed |
| ● | active |
| ◐ | awaiting document |
| ○ | not requested / awaiting |

Each row shows the date, and the finding is shown when the viewer is entitled to see it. The
`preserved` badge carries over unchanged from `ClearanceTrack`.

**Routing history** — one line per `group_id`, in the form `Intake → ITSO + IERC`, with the
actor and reason on expansion. Below it, the resubmission and document-request lists.

Everything renders from the server payload; nothing is computed on the client.

### 9.2 Reviewer page (IR-261)

A header names **the party you are acting as**. An RDCO user holding both `intake` and `rdco`
switches between them explicitly.

The actions shown come from `can_act`:

| Action | Behaviour |
|---|---|
| **Clear** | Optional note |
| **Record finding** | Positive or negative, with a mandatory comment |
| **Reroute** | Checkbox list of the parties the graph permits; a mandatory reason; Adviser disabled with an explanation when the record has no adviser |
| **Request document** | IR-263 |
| **Request resubmission** | Mandatory reason |
| **Decide** | Thesis/Project: publish / complete / reject, RDCO only. Proposal: approve / reject, assigned Adviser or RDCO. Disabled with the reason while a resubmission is open |
| **Mark completed** | Approved Proposal, assigned Adviser or RDCO |

**No Reject control is shown to Intake, to specialist offices, or to an Adviser on a Thesis or
Project.**

**Queues:** RDCO sees *Intake & Triage* and *Final Review*. Offices see their active assignments.
Advisers see Proposals they hold plus any Thesis/Project they were routed to.

### 9.3 Submitter (IR-259, IR-263)

The student-facing label is *Intake*. An **Action required** panel lists each open resubmission
request and document request: who asked, why, and an upload or edit control. Resubmission
refusals are shown in the panel, not as a small red line (IR-233 candidate 1).

---

## 10. Test migration plan

**Principle:** no test is edited to make it pass (CLAUDE.md). A test that describes the old model
is retired deliberately, in the same PR that makes it obsolete, and the PR says why.

### 10.1 Existing backend tests

| File | Lines | What happens | When |
|---|---|---|---|
| `reviews/test_workflow_matrix.py` (IR-140, 77 tests / 172 subtests) | 1109 | **Used as the oracle for the backfill**, then **retired** | IR-257 → IR-260 |
| `reviews/test_workflow_characterisation.py` (IR-197, 30 tests) | 720 | **Retired** | IR-260 |
| `records/test_lifecycle.py` (25 tests) | 462 | **Rewritten** for `PARTIES`, the narrowed `TRANSITIONS` and the settings override (ADR-005 seam kept) | IR-260 |
| `records/tests.py` | 519 | **Partly.** `:72`, `:423`, `:447` assert `rdco_intake`; visibility cases change | IR-260, IR-264 |
| `reviews/test_resubmission_policy.py` (9 tests) | 303 | **Partly.** Both ADR-004 arms survive; re-entry is asserted on assignments; multi-request cases added | IR-260 |
| `apps/tests/test_authorization_matrix.py` | 266 | **Partly.** `:241` iterates the two RDCO stages; visibility cases | IR-260, IR-264 |
| `reviews/test_clearance_payload.py` (12 tests) | 226 | **Kept.** `preserved` is unchanged | — |
| `reviews/tests.py` | 150 | **Rewritten** (service-level pipeline assertions) | IR-260 |
| `reviews/test_clearance_state.py` (13 tests, pure) | 107 | **Kept**; `declining_office` → `requesting_parties` | IR-260 |
| `apps/tests/test_enum_vocabulary.py` | — | **Changed deliberately.** IR-256 extends `GOVERNED_ENUMS` with `AssignmentState`, so the new tables' states cannot be hand-written as literals (`ResubmissionRequestState` stays out: its `resubmitted` is also a queue-row response key). Its `:8` docstring names the `rdco_intake` rename; `:299` asserts `len(PUBLICLY_VISIBLE_STATUSES) == 3` | IR-256, then IR-260, IR-264 |

### 10.2 IR-233 — keeping the failure visible

1. **Slice 0:** add `apps/reviews/test_resubmission_regression.py`. It is **not** in any suite
   that gets retired. This departs from IR-233's original acceptance criteria; the amendment is
   posted on the card.
2. **Written against the API and behaviour, not stage names.** Call `POST /reviews/resubmit/`,
   read the detail endpoint, and assert:
   - the response is a success;
   - the record is no longer `declined`;
   - the declining office's clearance is `pending`;
   - the peer offices are `cleared` with `preserved: true`.
3. **Marked `@pytest.mark.xfail(strict=True, reason="IR-233")`.** CI stays green while the bug
   exists, and an unexpected pass fails the build, so the fix cannot go unnoticed either.
4. **IR-260 removes the marker.** Every PR from slice 1 onward states that the test is still
   xfail.

### 10.3 New backend suites

Each is written first and seen failing:

- `reviews/test_party_graph.py` — legal and illegal routes; adviser target requires
  `record.adviser`.
- `reviews/test_assignments.py` — concurrency; at most one active assignment per party; hand-back
  rules per record type.
- `reviews/test_authority.py` — the full matrix from ADR-021 §7, including that intake and offices
  cannot reject, and that an Adviser decides and completes a Proposal with **no RDCO assignment**.
- `reviews/test_resubmission_requests.py` — concurrent requests; clearing blocked while open;
  upload-or-metadata guard; nothing deleted; both ADR-004 arms.
- `records/test_tracker.py` — every question in §8.2, each `workflow_state` precedence rule,
  RDCO row per type, 404-not-403 for four viewer kinds.
- `documents/test_document_requests.py` — ADR-022; nothing resets.
- `records/test_proposal_visibility.py` — IR-264, including retrieval.

### 10.4 Frontend

- `EvaluationPage.test.tsx` is rewritten with the page.
- New tests: `ReviewRoutingTracker.test.tsx`, `RerouteDialog.test.tsx`,
  `RequestDocumentDialog.test.tsx`, `ActionRequiredPanel.test.tsx`.
- All queries go through the accessible tree. axe must be clean for serious and critical issues.
  Contrast is checked by hand.

### 10.5 Evidence

- Each PR records the command it ran and the result, in the backend container.
- Never two suite runs at once (see the backend test harness note).
- `docs/testing/TRACEABILITY.md` FR-M5-01 is rewritten in IR-260; NFR-S4 in IR-264.

---

## 11. What is preserved

- `RecordClearance`, `clearance_state.py` (`is_preserved`, `clearance_payload`,
  `resubmission_payload`, `peer_summary`), and the `preserved` badge.
- `ResubmissionPolicy` and ADR-004's two arms.
- `Record.objects.visible_to()` — its structure is unchanged; only the public tuple narrows.
  IR-153's 404-not-403 rule stands.
- The whole documents app: `UploadSlot`, `RecordUpload`, versioning,
  `authorize_record_documents()`.
- Extraction and Docling, chunking, embeddings and RAG. Retrieval code is untouched; its corpus
  narrows through the shared predicate.
- Notification plumbing, `apps/audit`, accounts, roles, opportunities, settings.
- Publication, Discover, search (`search_vector`).

---

## 12. Jira breakdown

Story [IR-255](https://citiris.atlassian.net/browse/IR-255), under IR-53.

| Order | Key | Slice | Depends on | Estimate |
|---|---|---|---|---|
| 0 | [IR-233](https://citiris.atlassian.net/browse/IR-233) | Reproduce; strict-xfail regression | PR #81 merged | 0.5–1 d |
| 1 | [IR-256](https://citiris.atlassian.net/browse/IR-256) | Additive models | IR-233 | 1 d |
| 2 | [IR-257](https://citiris.atlassian.net/browse/IR-257) | Dual-write + backfill | IR-256 | 2 d |
| 3 | [IR-258](https://citiris.atlassian.net/browse/IR-258) | Tracker endpoint + `workflow_state` | IR-257 | 1.5 d |
| 4 | [IR-259](https://citiris.atlassian.net/browse/IR-259) | Frontend reads the new model | IR-258 | 2 d |
| 5 | [IR-260](https://citiris.atlassian.net/browse/IR-260) | **Backend cutover** | IR-233, IR-257–259 | 5–6 d |
| 6 | [IR-261](https://citiris.atlassian.net/browse/IR-261) | Reviewer actions UI | IR-260 (released together) | 2–3 d |
| 7 | [IR-262](https://citiris.atlassian.net/browse/IR-262) | Document requests — backend | IR-256 | 1.5 d |
| 8 | [IR-263](https://citiris.atlassian.net/browse/IR-263) | Document requests — frontend | IR-259, IR-262 | 1.5 d |
| — | [IR-264](https://citiris.atlassian.net/browse/IR-264) | Discover excludes Proposals | none | 0.5–1 d |

**Existing cards linked rather than duplicated:**

- IR-216 and IR-144 — workflow audit events, fed by `RoutingEvent`, `ResubmissionRequest` and
  `DocumentRequest`.
- IR-224 — end-to-end demonstration; an AC restatement is posted on the card.

---

## 13. Terminology

**Settled.**

| | |
|---|---|
| Identifier | `intake` |
| Staff label | "Intake & Triage" |
| Student label | "Intake" |

**Rejected alternatives:**

| Candidate | Why rejected |
|---|---|
| `rdco_intake` / "RDCO Intake Review" | Implies RDCO has already reviewed the work substantively — the reading the settled model rejects |
| "Institutional Intake" | *Institutional* carries RDCO's decision authority; using it for triage blurs the two |
| "Intake" for staff | Drops the "work out what is required" half, which is what makes routing out of intake forward movement |
| "Pre-Review", "Screening" | One implies a review has happened; the other implies filtering records out |

Different labels for staff and students cost nothing: ADR-002 §4 already treats labels as
configuration.

---

## 14. Considerations outside the workflow

Recorded here so they are not lost. **None of them reopens the workflow.**

- **Research positioning.** Reviewer-directed routing sits closer to CMMN than to BPMN. See
  ADR-021 §Research considerations. This is the team's research decision.
- **ADR-004 variance.** Participants now choose the route. ADR-011's protocol should be reviewed
  before data collection.
- **Semester budget.** Roughly 17–20 dev-days across IR-255. Deciding what it displaces is a
  project-management call.
