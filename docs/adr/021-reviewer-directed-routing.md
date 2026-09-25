# ADR-021: Intake, specialist review, and reviewer-directed routing

## Status

> **Partially superseded by [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md)**
> (Proposed 2026-09-26). The intake party (§1–§2), the Proposal rule "Adviser or RDCO decides and
> completes" (§3), RDCO as a mandatory gate for Thesis/Research and Project (§3, §10), and
> party-only assignment are replaced. The assignment, routing, resubmission and tracker machinery
> (§4, §6, §8, §11, §12, §14) is kept. The body below is left as decided, per this project's
> supersede-don't-edit rule.

**Accepted** — 2026-09-15 · **corrected 2026-09-16, §8 (schema compatibility: the
`RecordClearance.status` column width).** The workflow was settled as a business decision by
**Lee Jasmin Adolfo** (project lead). This ADR records that decision and the design that implements it. It
takes effect when [PR #81](https://github.com/moisturicer/IRIS/pull/81) merges. Tracked on
[IR-254](https://citiris.atlassian.net/browse/IR-254); implementation is
[IR-255](https://citiris.atlassian.net/browse/IR-255).

**Partially supersedes [ADR-018](018-conditional-parallel-office-routing.md)**, including its
rule that ITSO is Project-only. **Amends [ADR-002](002-workflow-transition-table.md).**

The code inspection this rests on — the exact current-to-new mapping, the migration plan, the
test migration plan and the Jira breakdown — is
[`docs/workflow_routing_architecture.md`](../workflow_routing_architecture.md). This ADR holds
the decisions; that document shows how the code gets there.

### How this decision was reached, in brief

This ADR went through three drafts on the same day.

1. **The first draft** introduced assignments and routing. It kept intake as part of a single
   `rdco` party, which preserved the reading the project lead objected to: RDCO reviewing a
   paper substantively and then handing it *down* to a specialist office.
2. **The second draft** separated intake from RDCO. It left the Proposal decision authority
   and the stored-versus-derived lifecycle question open.
3. **This version** records how both were settled.

One statement from the settling instruction was **withdrawn by the project lead** before this
version was written: *"A Proposal MUST be capable of reaching RDCO for a final institutional
decision."* Two things depended on it and are withdrawn with it:

- the instruction that a Proposal "still proceeds to RDCO for final institutional decision";
- the listed defect "Proposal approval ending without a real RDCO final institutional decision".

The settled Proposal rule is **"Adviser or RDCO completes"** (§3). RDCO is *not* a mandatory
gate for a Proposal.

## Context

### The reading being corrected

Written as `Submitter → RDCO Intake → ITSO/IERC/KTTO → RDCO`, the old workflow reads backwards.
The institution's senior office appears to review the work, pass it down to a smaller office,
and then take it back.

The settled model has three separate acts:

| | What it is | Who |
|---|---|---|
| **Intake & Triage** | *Administrative.* The submission has arrived; work out which reviews, documents or corrections are needed before a decision can be made. | RDCO staff, working administratively |
| **Specialist review** | *Substantive, narrow.* Ethics, protectability, commercial viability — only the ones this work actually raises. | ITSO / IERC / KTTO, and the Adviser |
| **Decision** | *Substantive, whole-record.* | RDCO for Thesis/Research and Project; the Adviser or RDCO for a Proposal |

When triage sends a record to a specialist office, the record moves *forward*. Intake and the
final decision being done by the same people is a staffing arrangement. It is not a workflow
state.

### Where the code contradicts the settled model

[`workflow_routing_architecture.md` §3](../workflow_routing_architecture.md#3-conflicts-with-the-settled-model)
lists every conflict with its file and line. The ones that shape the decisions below:

- **Intake is a substantive review that can reject.** `core/enums.py:57` labels it "RDCO
  Intake **Review**". It writes a `Review` row with a decision, and `lifecycle.py:285` gives it
  an edge straight to `rejected`.
- **Triage cannot do triage.** The set of offices is read from three booleans the *student* set
  (`lifecycle.py:505`). Intake has no way to request a document and no way to route.
- **Thesis/Research cannot reach ITSO** (`lifecycle.py:519`).
- **Specialist offices can terminally reject** (`reviews/services.py:submit_clearance`,
  `EvaluationPage.tsx:39`).
- **The Adviser cannot complete a Proposal, and RDCO cannot decide one.** A Proposal stops at
  `approved` (`lifecycle.py:495`), and `/complete/` is RDCO-only (`records/views.py:345`).
- **`pipeline_status` is one field.** It cannot represent two offices reviewing at once, or two
  offices each waiting on a resubmission.
- **Discover lists Proposals.** `approved` and `completed` are statuses only a Proposal can
  reach, and both are in `PUBLICLY_VISIBLE_STATUSES` (`core/enums.py:72`), which Ask IRIS
  retrieval also reads.

Two things the code already gets right, and which this ADR does not rebuild:

- a record that requests no specialist office already goes straight from intake to RDCO final
  (`lifecycle.py:550`);
- IERC and KTTO already review genuinely concurrently.

## Decision

**A record's position is a set of open assignments plus a routing history, over six parties.
`intake` and `rdco` are separate parties. Any party holding an open assignment may route the
record to one or more other parties, with a reason. Entry is fixed by record type. Decision
authority is fixed by record type.**

### 1. Parties — intake is its own party

```
Party = intake | adviser | itso | ierc | ktto | rdco
```

**No new enum is needed.** `core.enums.ReviewStage` already holds exactly these six values;
the only difference is that one of them is called `rdco_intake`. Renaming that one value
(§2) turns `ReviewStage` into the party vocabulary. `Party` is added as an alias for
readability.

`intake` and `rdco` are **two parties staffed by the same role**, `RoleName.RDCO`. The mapping
from role to parties is configuration. An RDCO user acting on a record states which party they
are acting as (`acting_as`). The server checks that their role can staff that party *and* that
the party holds an active assignment on the record.

**What Intake & Triage may do:** check completeness; identify missing information; decide which
specialist reviews are needed; route to one or more parties; request documents; request
resubmission; record an initial assessment or clearance.

**What Intake & Triage may not do:** make the final decision, reject the record, or publish it.

### 2. Terminology

**Identifier `intake`. Staff see "Intake & Triage". Students see "Intake".**

The identifier must drop `rdco`. `rdco_intake` is a *stored* value, not just a label, and as
long as the stored name ties intake to RDCO, every reader will rebuild the wrong picture of the
workflow. "Institutional Intake" was rejected: *institutional* is the word that carries RDCO's
authority in "institutional decision", so using it for triage blurs the very distinction this
ADR draws. The full comparison is in
[`workflow_routing_architecture.md` §13](../workflow_routing_architecture.md#13-terminology).

Showing different labels to staff and students costs nothing. ADR-002's amendment §4 already
treats labels as configuration.

**The rename is a deliberate data migration, never a find-and-replace.**
`apps/tests/test_enum_vocabulary.py:8` exists to catch exactly this rename. Let it fail, read
it, and update it together with the migration.

### 3. Workflow and decision authority by record type

| | Proposal | Thesis / Research | Project |
|---|---|---|---|
| **Enters at** | `adviser` | `intake` | `intake` |
| **Specialist review** | if needed | if needed | if needed |
| **Decides** | assigned **Adviser or RDCO**: approve → `approved`, or reject → `rejected` | **RDCO**: publish → `published`, complete → `completed`, or reject → `rejected` | same as Thesis |
| **Completes** | assigned **Adviser or RDCO**: `approved` → `completed` | — (a decision is terminal) | — |
| **RDCO a mandatory gate?** | **No** | Yes | Yes |
| **In Discover?** | **No** | when `published` | when `published` |

**A Proposal can be decided and completed without any RDCO assignment ever existing.** An
Adviser may still route a Proposal to RDCO. When RDCO holds a Proposal, RDCO's authority is the
same as the Adviser's.

**How "Adviser or RDCO completes" maps onto the existing states.** The repository already
separates `approved` ("proposal approved, research ongoing" — My Workspace's *Research Ongoing*)
from `completed` ("research finished"), and `/complete/` already moves a record from one to the
other. The smallest faithful implementation keeps both states and widens both acts: *deciding*
a Proposal and *completing* it each become available to the assigned Adviser or RDCO. Before,
deciding was Adviser-only and completing was RDCO-only.

**Thesis/Research and Project reach RDCO.** When every non-RDCO assignment has closed, IRIS
opens an RDCO assignment (§10). RDCO then decides whether the output is **published**
(institutional visibility, Discover) or **completed** (retained, not listed).

### 4. Lifecycle state: store facts, derive everything else

`Record.pipeline_status` keeps **only durable facts about the record**. Anything that can be
worked out from assignments, requests or reviews is **derived** and never stored. Otherwise two
places hold the same answer and can drift apart. The code already shows that failure:
`_stage_reviewed_by` (`lifecycle.py:655`) exists only because `pipeline_status` and
`RecordClearance` each hold half of the answer to "where is KTTO?".

| Stored in `pipeline_status` | Meaning |
|---|---|
| `draft` | not yet submitted |
| `in_review` | in the workflow |
| `approved` | Proposal approved; research ongoing |
| `completed` | closed and retained, not published |
| `published` | approved for institutional visibility |
| `rejected` | terminally refused |
| `pending_delete` | awaiting a delete decision |

**Retired as stored values:** `adviser_review`, `rdco_intake`, `itso_review`,
`parallel_review`, `rdco_review` — and **`declined`**.

`declined` is retired because it breaks the rule above once several parties hold a record at
the same time. ITSO and IERC can both be reviewing and can both ask for a resubmission. One
scalar cannot record *who* is waiting for a resubmission or *how many* requests are open. That
fact now lives in `ResubmissionRequest` rows (§8), and `awaiting_resubmission` is derived from
them.

**`workflow_state`** is exposed to the frontend and never stored. Terminal states pass through
as-is. For an `in_review` record, the first rule that matches wins:

1. `awaiting_resubmission` — at least one open `ResubmissionRequest`
2. `awaiting_document` — at least one open `DocumentRequest` (ADR-022)
3. `submitted` — the only active assignment belongs to the entry party, and that party has not
   yet recorded a review or a routing event
4. `final_review` — every active assignment belongs to a party that can decide this record type
5. `in_review` — anything else

`submitted` comes before `final_review` on purpose. A Proposal enters at the Adviser, who is
also a deciding party. With the order reversed, a Proposal nobody has opened would show as
being in final review.

`pipeline_status` is **narrowed, not deleted**. `Record.objects.visible_to()` and
`PUBLICLY_VISIBLE_STATUSES` still read it.

### 5. Specialist review is conditional, and ITSO is open to every record type

No record goes through an office just because the office exists. Triage decides which
specialists are needed, based on the work itself. Any holder who later spots a need adds
another.

**ADR-018's Project-only rule for ITSO is reversed.** A thesis that produces patentable work can
now reach ITSO. ADR-018's requested-office booleans stay on the record, but their role changes:
they are a **suggestion to triage**, not the route.

### 6. Initial routing and dynamic rerouting use one mechanism

There is one action:

```python
route(record, actor, acting_as, targets, reason)
```

**Initial routing** is triage's first use of it. **Dynamic rerouting** is any later use by any
holder. The difference matters to someone reading the tracker, and `RoutingEvent` records it:
the first event whose `from_party` is `intake` is the initial routing. It is still one
mechanism. Building two would be the start of the hardcoded state machine this decision
rejects.

`route()`:

- Refuses unless `acting_as` holds an active assignment and the actor may staff `acting_as`.
- Refuses any target the party graph (§9) does not permit from `acting_as`.
- Refuses `adviser` as a target when `record.adviser` is empty. Access is granted through that
  foreign key (`visible_to()`, `_can_review`), so there would be nobody to assign.
- Opens a `RecordAssignment` for each target that has no active one, and writes one
  `RoutingEvent` per target. All events from one call share a `group_id`, so "Intake → ITSO +
  IERC" appears as a single movement.
- Opens a `RecordClearance` for a clearing-office target if none exists. **An existing
  `cleared` row is never reset by routing.** Sending a record back to an office that already
  cleared it means "please look again". Whether that cancels the earlier clearance is for that
  office to say in its next `Review`.
- Does not close the actor's own assignment.
- Runs inside `transaction.atomic()`.

### 7. Actions and authority

| Action | Intake | Adviser | ITSO / IERC / KTTO | RDCO |
|---|---|---|---|---|
| Clear / record assessment | ✓ | ✓ | ✓ | ✓ |
| Record negative finding or recommendation | ✓ | ✓ | ✓ | ✓ |
| Reroute (multi-select) | ✓ | ✓ | ✓ | ✓ |
| Request document (ADR-022) | ✓ | ✓ | ✓ | ✓ |
| Request resubmission | ✓ | ✓ | ✓ | ✓ |
| **Decide** a Proposal (approve / reject) | ✗ | ✓ *assigned* | ✗ | ✓ |
| **Complete** an approved Proposal | ✗ | ✓ *assigned* | ✗ | ✓ |
| **Decide** a Thesis/Research or Project (publish / complete / reject) | ✗ | ✗ | ✗ | ✓ |

**A specialist office never ends a record.** Today it can: `submit_clearance` maps `rejected`
straight to `PipelineStatus.REJECTED`. That changes. An office with an objection records a
negative finding, which is kept as a `Review` and on its `RecordClearance`, and routes the
record onward. The finding is shown to whoever decides.

**An Adviser on a Thesis/Research or Project** is one consulted party among several. They
recommend; they do not decide.

**Authorization stays out of the transition table.** The table says which routes are *legal*.
`core.permissions` decides *who* may take them. The reason: "the assigned adviser" and "holds
an active assignment" are conditions on a particular record, and a table keyed on roles cannot
express them.

### 8. Data model

```
NEW  RecordAssignment    record, party, state, opened_by, opened_at,
                         closed_by, closed_at, reason
                         state ∈ active | completed | withdrawn
                         at most one active row per (record, party)

NEW  RoutingEvent        record, actor, from_party, to_party, reason, group_id, created_at

NEW  ResubmissionRequest record, party, assignment, review, requested_by, reason,
                         state, created_at, resolved_by, resolved_at
                         state ∈ open | resubmitted | withdrawn

NEW  DocumentRequest + DocumentRequestItem                       — ADR-022

EXT  Review              + assignment (FK, nullable)
EXT  RecordClearance     status column widened 10 -> 20 chars; no row, value or
                         behaviour changed
```

**An assignment has no outcome field.** Its state only says whether the party is still acting.
*What* the party concluded is recorded in `Review` and `RecordClearance`. Storing the outcome on
the assignment as well would create exactly the duplicate this ADR removes.

**Correction, 2026-09-16 (IR-256): `RecordClearance` is not quite unchanged.** This section
listed it as `KEEP ... unchanged` while also giving `ClearanceStatus` a value that does not fit
its column. The two could not both hold, and the column is the half that gives way:
`reviews/0007` widens `status` from `varchar(10)` to `varchar(20)`. **This is a schema
compatibility correction, not a workflow redesign** — no row is rewritten, no stored value
changes, no clearance behaves differently, and the widening is the whole of it. Everything this
ADR decides about clearances, above all that a peer's `cleared` row survives another party's
resubmission request, is untouched. `ALTER COLUMN ... TYPE varchar(20)` is a catalogue-only
change in PostgreSQL: it neither rewrites the table nor takes a long lock.

**`RecordAssignment` and `RecordClearance` stay separate.** An assignment answers *"who needs to
act now?"*. A clearance answers *"what clearance has already been obtained?"*. Clearance-aware
resubmission depends on the second surviving events that end the first. Put both in one row and
a preserved clearance can no longer be represented.

**Vocabulary changes:**

- `ReviewStage.RDCO_INTAKE` → `INTAKE`.
- `ReviewDecision` gains `NEGATIVE_FINDING`. `DECLINED` keeps its stored value, relabelled
  *"Resubmission requested"*.
- `ClearanceStatus` gains `NOT_CLEARED`. `REJECTED` is kept for historical rows; nothing new
  writes it. **`RecordClearance.status` is `varchar(10)`, and `not_cleared` is eleven
  characters, so the column widens to 20** — see the correction below.
- `PipelineStatus` gains `IN_REVIEW` and loses six values (§4).
- `PUBLICLY_VISIBLE_STATUSES` narrows to `(PUBLISHED,)` (§13).
- A new `DELETE_REVIEW_STATUSES` holds `(PUBLISHED, APPROVED, COMPLETED)`.

### 9. `lifecycle.py` evolves; it is not extended

- **`STAGES` is replaced by `PARTIES`.** For each party: its labels, whether it clears or gates,
  and which parties it may route to. It stays overridable in settings, as ADR-002 decided.
- **`TRANSITIONS` shrinks to record-level edges:** submit, decide, complete, the delete edges,
  and restore.
- **`ENTRY_PARTY` and `DECIDING_PARTIES`** are declared per record type.
- **`_resolve_after_clearance`, `_resolve_enter_clearance_stage`, `_clearance_entry_for`,
  `_stage_reviewed_by` and `_resolve_after_adviser_review` are deleted.** They work out a
  status from a set of offices; with assignments, the set of offices *is* the answer.

**Why not simply add edges such as `intake → itso`, `itso → ierc`, `ierc → rdco`?**
`_resolve_after_adviser_review` ends in `else PipelineStatus.PUBLISHED`. That branch is
unreachable today, because a Thesis never enters `adviser_review`. Add an edge that lets an
Adviser hold a Thesis, and an Adviser approving it would **publish it without RDCO**. The
existing statuses carry assumptions about which record types can reach them. Extending the
table turns each of those assumptions into a live defect.

### 10. Handing a record back to its decider

When the last active assignment that does not belong to a deciding party closes:

- **Thesis/Research and Project:** if RDCO has no active assignment, IRIS opens one and notifies
  RDCO.
- **Proposal:** if neither the Adviser nor RDCO has an active assignment, IRIS reopens the
  Adviser's. RDCO is never opened on a Proposal automatically.

This is a hand-back, not a status change: `pipeline_status` stays `in_review`. The old pipeline
*advanced* records from stage to stage; this model *hands them back* to whoever decides.

### 11. Resubmission

**Requesting a resubmission** does four things:

1. writes a `Review` with decision `declined` ("resubmission requested");
2. opens a `ResubmissionRequest` for the requesting party;
3. for a clearing office, sets its `RecordClearance` to `declined`;
4. leaves every assignment exactly as it is.

**While any resubmission request is open,** reviewers can still route, request documents, record
findings and add further resubmission requests. They **cannot** clear, decide or complete,
because there is no point signing off a version the submitter is about to change.

**Resubmitting** requires that the submitter changed something since the earliest open request:
**a new upload or an edit to the record's metadata**. Today's guard accepts only an upload, so a
revision that changes only metadata is refused. On resubmission:

- every open `ResubmissionRequest` is resolved as `resubmitted`, which is also the resubmission
  history the tracker shows;
- under `CLEARANCE_AWARE` (the default), **only the requesting parties' clearances** reset to
  `pending`, and every other `cleared` row is preserved;
- under `RESTART_ALL` (ADR-004's comparison arm), every clearance resets;
- the requesting parties' assignments are still active, so review continues where it paused;
- **nothing is deleted.** Today's sequential-decline branch, which deletes every
  `RecordClearance` (`lifecycle.py:651`), goes away.

ADR-003's rule still holds, in a more general form: *only the parties that asked for changes
lose their clearance.* The two ADR-004 arms still differ in exactly one statement, which is
IR-137's acceptance criterion.

There is **one** resubmission entry point, `POST /reviews/resubmit/`. The comment in
`records/views.py:submit` saying it "also handles resubmission" describes a path with no
declared edge, and it is removed.

### 12. A decision closes the record's open work

A decision — or completing a Proposal — marks every other active assignment `withdrawn` and
every open `DocumentRequest` `withdrawn`, with the decision as the reason. The history is kept.
**A decision is refused while any resubmission request is open.**

### 13. Discover and visibility

`PUBLICLY_VISIBLE_STATUSES = (PUBLISHED,)`. Before this change it also contained `approved` and
`completed`, and only a Proposal can reach those two statuses.

The **single visibility predicate** changes, not only the Discover list. Per CLAUDE.md,
visibility is one predicate used everywhere, so Discover, record detail, dashboards and Ask
IRIS retrieval move together. A filter that only hid Proposals from Discover would add a second
predicate: an unrelated user could still open a Proposal by its id, and Ask IRIS could still
cite it.

Owners, the assigned adviser and office staff keep access through `visible_to()`'s other
clauses.

**Deletion is decoupled from visibility.** `perform_destroy` (`records/views.py:148`) and the
`REQUEST_DELETE` edges (`lifecycle.py:375`) currently branch on `PUBLICLY_VISIBLE_STATUSES`.
Narrowing that tuple alone would let an owner soft-delete an approved or completed Proposal
without review. They branch on `DELETE_REVIEW_STATUSES` instead, so deletion behaves exactly as
it does today.

### 14. Review & Routing Tracker

`GET /api/v1/records/<id>/tracker/` answers every question the tracker must answer. It derives
all of them from persisted rows, with no frontend-only state: current active parties; completed,
active, requested-but-incomplete and not-requested parties; document requests and their status;
routing history; review history; resubmission history. The field-by-field mapping is in
[`workflow_routing_architecture.md` §8](../workflow_routing_architecture.md#8-the-review--routing-tracker).

RDCO's row depends on record type. On a Thesis/Research or Project it is never "not
requested", because RDCO always decides; it shows *awaiting* until RDCO is assigned. On a
Proposal it is "not requested" unless RDCO was actually routed to.

The endpoint uses `Record.objects.visible_to(user)`. A user without access gets a 404, the same
response as for a record that does not exist (IR-153).

## What this changes in the accepted record

- **ADR-018 — partially superseded.** The ITSO-is-Project-only rule is reversed. The
  requested-office booleans become a suggestion to triage. Its unbuilt "RDCO amend UI" is no
  longer needed, because amending the office set is rerouting. The `request_document` gap it
  recorded is closed by ADR-022.
- **ADR-002 — amended.** Its key `(from_status, event, actor_role) → to_status` no longer
  describes movement between parties. The table keeps the record's own lifecycle and gains a
  party graph. It can no longer claim that *all* routing is a table lookup, and that is recorded
  here rather than presented as an improvement.
- **ADR-003 — mechanism kept, generalised** from "the one declining office" to "every party with
  an open resubmission request". The route table in its §Context is now historical.
- **ADR-004 — both arms kept**, still differing in one statement.
- **ADR-009 — one predicate added**, `holds_open_assignment`.
- **IR-153's visibility predicate — narrowed** (§13).

## Alternatives Considered

The workflow itself is a settled business decision and is not reargued here. These are the
*implementation* alternatives that were considered.

**Rename `rdco_intake` and change nothing else.** Rejected. Intake would still be unable to
request documents or route — the whole job the settled model gives it. A correct label on a step
that cannot do its named job is worse than a wrong one, because it stops anyone looking.

**Add routing as edges in the existing table.** Rejected, for the dead-branch reason in §9.

**Keep a single `rdco` party that covers both intake and final decision.** Rejected. This was the
first draft's mistake: the tracker could not show "✓ Intake / ○ RDCO awaiting".

**Keep `declined` as a stored status next to `ResubmissionRequest`.** Rejected. Once several
parties hold a record, two parties can each have an open resubmission request, and one column
cannot represent that.

**Hide Proposals from Discover only, and leave `visible_to()` unchanged.** Rejected. It creates a
second visibility predicate, which CLAUDE.md forbids, and Ask IRIS could still cite a record that
Discover hides.

**Adopt a case-management engine (CMMN — Flowable, Camunda's case module).** Rejected for the
reasons ADR-002 rejected BPM engines. See §Research considerations.

## Decision Rationale

This model removes more than it adds. Five pieces of machinery exist only because one status
field is being asked to describe a set of offices: `_stage_reviewed_by`, `_clearance_entry_for`,
the ITSO special case in `_resolve_after_clearance`, `_resolve_after_adviser_review`, and the
split between `itso_review` and `parallel_review`. All five are deleted, and nothing replaces
them.

The new structures pass the deletion test. Remove `RecordAssignment`, `RoutingEvent` or
`ResubmissionRequest`, and the questions they answer — who holds this record, who sent it there
and why, who is waiting on a resubmission — cannot be answered from anything else. Today, "who
asked IERC to look at this?" cannot be recovered at all.

Separating `intake` from `rdco` costs one identifier. It is what lets the model describe triage
dispatching to a specialist without implying that RDCO has already reviewed the paper.

## Consequences

**Positive.**
- A thesis with patentable work can reach ITSO.
- Triage can actually triage.
- An Adviser can close out a Proposal without waiting on RDCO.
- No specialist office can end someone else's submission on its own.
- "Who holds this?", "who sent it there?" and "what was asked of the submitter?" all become
  stored fields instead of guesswork.
- A revision that changes only metadata can be resubmitted.
- Proposals no longer leak into Discover or Ask IRIS.

**Negative.**
- A non-additive migration on `Record.pipeline_status`, the column that IR-153's visibility
  predicate reads.
- About 2,700 lines of workflow tests describe the pipeline being replaced, including the
  characterisation suite from IR-197. Retiring them is a recorded decision, not tidying up.
- Every reviewer-facing screen is rebuilt.
- A record can bounce between two offices indefinitely; nothing in the model stops that.
- Unrelated authenticated users lose read access to approved and completed Proposals.

**Risk.** IR-233 is an open `mvp-blocker`: a resubmitted record lands straight back in
`declined`, so clearance-aware resubmission cannot be seen working today. The implementation
plan makes it slice 0. It is reproduced first and captured as a behaviour-level strict-xfail
test *outside* any suite that gets retired, so the refactor cannot make the failure invisible.

## MVP Impact

MVP-required and thesis-critical. Rough effort: 13–16 dev-days for this ADR and about 3 for
ADR-022, across the slices in IR-255. **Deciding which other work this displaces from the
semester budget is a project-management call, recorded separately. It does not reopen this
workflow.**

## SaaS Impact

Positive. The party graph makes a second institution's routing configuration rather than code.
An institution that staffs triage and its research office with different teams changes the
role-to-party map, nothing else. Offices themselves are still defined in code (`Office`,
`RoleName`, seeded `Role` rows), so ADR-002's criterion for a fourth office is unchanged.

## Security Impact

- **`holds_open_assignment(user, record)` is added to `core/permissions.py`** and used by the
  route, action, tracker and document-request endpoints.
- **The tracker is record data**, gated by `visible_to()`, and refuses with 404 rather than 403.
- **Two reductions in authority:** intake and specialist offices can no longer reject.
- **One narrowing of visibility:** approved and completed Proposals leave the public catalogue
  and Ask IRIS retrieval.
- **Deletion review is unchanged**, because it now branches on its own tuple.

## Deployment Impact

One migration that is **not** additive:

- rewrites `pipeline_status` on every in-flight record;
- renames the intake value in `Review.stage`;
- turns `declined` records into `in_review` with an open `ResubmissionRequest`.

It runs after the additive migration and backfill have been verified. Test it against a copy of
a seeded database, and back up `postgres_data` before applying it to the pilot. The full plan is
in [`workflow_routing_architecture.md` §7](../workflow_routing_architecture.md#7-migration-plan).

## Research considerations

These are **separate research questions. They do not change the settled workflow.**

**Where the novelty claim sits.** ADR-003 answered the BPMN objection ("parallel gateways have
existed for years") by pointing out that BPMN has no native way to express "reset only the
branch that rejected". That answer still holds, and §11 states the rule more generally. But
routing chosen by reviewers over a shared case file sits closer to CMMN and to ad-hoc case
management, so a thesis panel may bring that literature up. The team should decide how to
position the claim before the defence.

**ADR-004's evaluation.** Participants now choose the route, so route length becomes a source of
variance that the controlled comparison did not plan for. ADR-011's protocol should be reviewed
before data collection.

## Related Requirements

FR-M5-01 · FR-M5-03 · NFR-R3 · NFR-S4. These IDs are stable labels only.

## Related Tasks

IR-254 (this ADR) · **IR-255** and its subtasks IR-256 to IR-264 (implementation) · **IR-233**
(slice 0) · IR-53 · IR-134/IR-136 · IR-144, IR-216 · IR-197, IR-140 (suites retired by IR-260) ·
IR-224 · IR-118.
