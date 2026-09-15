# ADR-021: Reviewer-directed routing

## Status

**Proposed** — 2026-09-15. Tracked on [IR-254](https://citiris.atlassian.net/browse/IR-254).

**Not accepted, and two of the questions it raises are not the author's to settle.** §Research
Impact asks whether this change strengthens or weakens ADR-003's novelty argument, and
§MVP Impact asks what it displaces against a budget that has already been reversed four times.
Both are decisions for the team; this ADR states the case and leaves them open.

**Partially supersedes [ADR-018](018-conditional-parallel-office-routing.md)** and **amends
[ADR-002](002-workflow-transition-table.md)** — see §What this changes in the accepted record.

## Context

### What IRIS does today, read off the code rather than the diagrams

Routing is a fixed, type-differentiated pipeline. `Record.pipeline_status` is a single scalar,
and `apps/records/lifecycle.py` (IR-136) holds two structures that decide where it goes next:

- `STAGES` — five nodes: `adviser_review`, `rdco_intake`, `rdco_review` (sequential) and
  `itso_review`, `parallel_review` (parallel, with a fixed office group each).
- `TRANSITIONS` — edges keyed `(from_status, event)`, each carrying either a literal `to`
  status or a named resolver.

Which offices review a disclosure is decided **once**, at RDCO intake, from three booleans the
submitter set in the wizard — `requested_itso` / `requested_ierc` / `requested_ktto`
(ADR-018). `_resolve_enter_clearance_stage` reads them, creates `RecordClearance` rows, and
from that point the route is fixed: ITSO clears, IERC joins, all offices clear, RDCO decides.

Three consequences of that shape matter here:

1. **Nobody can redirect a record.** Not RDCO, not an office. If IERC reads a manuscript and
   concludes it needs a patentability opinion, there is no action that sends it to ITSO. The
   only tool is `decline`, which bounces the record to the submitter and asks them to
   re-request the office through the wizard.
2. **"Which offices already have this?" is answered by inference, not by a field.** It is
   recoverable — join `RecordClearance` against `Review` and read the statuses — but nothing
   in the model records *who sent it there*, so "who asked IERC to look at this?" has no
   answer at all.
3. **The stage vocabulary leaks the sequence.** `itso_review` admits ITSO *and* KTTO;
   `parallel_review` admits IERC *and* KTTO; so KTTO exists in two stages and
   `_stage_reviewed_by()` has to disambiguate which one a resubmission returns to. That
   function is a symptom: a status scalar is being asked to encode a set.

### What the team actually described

Restated, from the workflow session of 2026-09-15:

> IRIS is a controlled research review and routing system, not a fixed sequence of offices.
> A record has a current holder (possibly several), a review history and a routing history.
> Any authorised reviewer can reroute it to one or more destinations. RDCO retains final
> institutional decision authority.

The organizational reality behind that: RDCO does not know at intake which offices a
disclosure needs, and neither does the student. It is discovered *by reading the work*, by
whoever is holding it. ITSO reads a prototype and sees a commercialization angle KTTO should
assess. IERC reads a methodology and finds no human subjects after all. The office that
discovers the need is the office that should be able to act on it.

The fixed pipeline models a decision (which offices?) as if it were made once, up front, by
the person least equipped to make it.

### The half of this that is already a known gap

ADR-018's own Status section records it:

> there is **no `request_document` mechanism in the system**, and the request is therefore
> invisible to the record […] nothing distinguishes "you forgot a form" from a substantive
> revision.

That half is [ADR-022](022-explicit-document-requests.md). This ADR covers routing only. The
two were settled in the same session and are split because they are two decisions, with
different alternatives and different costs.

## Decision

**A record's position in the workflow becomes a set of open assignments and a routing history,
not a status scalar. Any party holding an open assignment may route the record to one or more
other parties, with a reason. The bookends — who receives a submission, and who may publish —
stay fixed by record type.**

"Controlled" is the operative word, and it is discharged by four constraints, not by
restricting the graph:

1. **Entry is fixed by type.** A Proposal enters at Adviser. A Thesis/Research or Project
   enters at RDCO intake. A submitter never chooses their first reviewer.
2. **Only a party that currently holds the record may route it.** Holding is an open
   `RecordAssignment` row, not a role. An ITSO officer with no open assignment on a record has
   no routing action on it, exactly as they have no review action today.
3. **Only RDCO may reach a terminal institutional state** — `published`, `completed`,
   `rejected`. Any other party's "final" action closes their own assignment; it does not close
   the record.
4. **Every route is recorded, with an actor and a reason.** Routing is not a silent side
   effect of approving; it is its own event with its own row.

### 1. Data model

Three structures. Two are new; the third already exists and does not change.

```
RecordAssignment          who holds the record now, and who held it before
├── record          FK Record
├── party           CharField  → Party (adviser | rdco | itso | ierc | ktto)
├── state           CharField  → active | cleared | declined | rejected | withdrawn
├── opened_by       FK User, null  (null = opened by submission, not by a person)
├── opened_at       DateTime
├── closed_by       FK User, null
├── closed_at       DateTime, null
└── reason          TextField  (why this party was brought in)

    Constraint: at most one `active` row per (record, party).
    A party may hold several *historical* rows — being routed back to IERC
    twice is two assignments, not one reopened.

RoutingEvent              who sent it where, and why
├── record          FK Record
├── actor           FK User
├── from_party      CharField, null  (null = submission)
├── to_party        CharField
├── reason          TextField
├── group_id        UUID             (one multi-select reroute = N rows, one group)
└── created_at      DateTime

RecordClearance           UNCHANGED — one office's clearance verdict
```

**`RecordAssignment` and `RecordClearance` are deliberately not merged**, and the distinction
is the one ADR-003 rests on. An assignment answers *"is this office looking at it now?"*. A
clearance answers *"has this office signed off, and is that signature still valid?"*. The
whole contribution is that the second survives events that end the first. Collapsing them into
one row with one status makes "preserved clearance" unrepresentable.

**Does `RecordClearance` extend to RDCO and Adviser? No.** It stays the three clearing offices,
per `core.enums.Office`. RDCO's intake and final decisions and the Adviser's gate are recorded
as `Review` rows against their assignment, as now. Widening `Office` would let a caller
construct an RDCO clearance the workflow has no concept of — the same argument
`core/enums.py` already makes for keeping RDCO out of that enum.

**`Review` gains an `assignment` FK and keeps `stage`.** Nullable, because existing rows have
no assignment to point at. `stage` is not renamed and not re-valued: `rdco_intake` and `rdco`
remain distinguishable on historical rows, which they would not be if the column were
collapsed to a party.

### 2. What happens to `pipeline_status`

**It is retained, narrowed to a phase, and the five stage values are collapsed.**

Deleting it is not on the table: `Record.objects.visible_to()` and `PUBLICLY_VISIBLE_STATUSES`
(IR-153) filter on it, Discover narrows on it, and the security predicate that keeps a draft
invisible is `pipeline_status`-shaped. Those must keep working unchanged.

| Today | After |
|---|---|
| `draft` | `draft` |
| `adviser_review` · `rdco_intake` · `itso_review` · `parallel_review` · `rdco_review` | **`in_review`** |
| `declined` · `rejected` · `approved` · `completed` · `published` · `pending_delete` | unchanged |

`in_review` says *the record is with reviewers*. **Which** reviewers is the open assignment
set, which is the only place that question is answered and therefore the only place it can
drift out of date.

This is the expensive part of the change and it should be named as such: it is a data
migration on the central domain object, mapping five statuses to one and backfilling an
assignment per record from `RecordClearance` plus record type. It is mechanical, and it is
cheaper now than after the Week-11 customer load.

### 3. Routing as an action

```python
route(record, actor, targets: list[Party], reason: str) -> list[RecordAssignment]
```

- Refuses unless `actor` holds an open assignment on `record` (or is RDCO — see the matrix).
- Refuses a target the actor's role may not route to.
- For each target: opens a `RecordAssignment` if none is active, and writes a `RoutingEvent`.
  All events from one call share a `group_id`, so the history renders "Adviser → ITSO, IERC"
  as one movement rather than two.
- For a clearing office target, opens a `RecordClearance` row if none exists. **An existing
  `cleared` row is not reset by routing** — re-routing to an office that has already cleared
  is a legitimate "please look again", and whether that invalidates the prior clearance is the
  office's call, made by its next `Review`, not the router's.
- Does not close the actor's own assignment. Routing and clearing are separate acts: an office
  may bring in a peer and keep working.
- Wrapped in `transaction.atomic()`, like every other lifecycle write (IR-138).

### 4. The action set, and who gets which

Every holder sees the same six actions. What differs is the target set and the reach.

| Action | Adviser | RDCO | ITSO / IERC / KTTO |
|---|---|---|---|
| **Clear** (close my assignment, cleared) | ✓ | ✓ | ✓ |
| **Reroute** to one or more parties | ✓ | ✓ | ✓ |
| **Request document** (ADR-022) | ✓ | ✓ | ✓ |
| **Request resubmission** (→ `declined`) | ✓ | ✓ | ✓ |
| **Reject** (terminal) | Proposal only | ✓ | ✗ — clears with objection instead |
| **Final institutional decision** (→ `published` / `completed`) | ✗ | ✓ | ✗ |

Two rows need their reasoning on the record:

**An office cannot reject.** ITSO concluding "this is not patentable" is not the institution
refusing the work; it is one office's finding. Letting three offices each hold a terminal veto
makes the final decision structurally meaningless — RDCO would be rubber-stamping whichever
office moved first. An office that objects clears with a negative `Review` and routes to RDCO.

**An Adviser can reject, but only a Proposal.** That is today's behaviour
(`TRANSITIONS[(adviser_review, REJECT)] → rejected`) and the Adviser is the sole reviewer on
that route, so their rejection *is* the institution's. On a Thesis/Research or Project the
Adviser is one consulted party among several and gets the office treatment.

**Authorization stays out of the table.** ADR-002's amendment §6 makes this point and it holds
harder here: `_can_review` checks `record.adviser_id == user.pk` — the *assigned* adviser, not
any Adviser — and now also "does this user's party hold an open assignment", which is a
per-record condition a role-keyed table cannot express. The table declares which routes are
*legal*; `core.permissions` and the services decide who may take them. Two checks, both must
pass.

### 5. What `lifecycle.py` becomes

The module stays, settings-overridable, as ADR-002 decided. Its content changes:

- **`STAGES` is replaced by `PARTIES`** — per party: its label, whether it clears (holds a
  `RecordClearance`) or gates, and which parties it may route to. This is the per-institution
  seam ADR-002 claims; it is a better one than `STAGES` was, because a second institution's
  routing graph is now data rather than a sequence baked into resolvers.
- **`TRANSITIONS` narrows to record-level edges only** — `draft → in_review`,
  `in_review → declined`, `declined → in_review`, `in_review → published/completed/rejected`,
  and the delete/restore edges. Roughly nine rows instead of thirty. Inter-office movement is
  no longer an edge; it is a routing action against the party graph.
- **`ENTRY_PARTY`** replaces `_resolve_first_status`: `Proposal → adviser`, everything else
  `→ rdco`.
- `_resolve_after_clearance`, `_resolve_enter_clearance_stage`, `_clearance_entry_for` and
  `_stage_reviewed_by` are **deleted**. They exist to compute a status from an office set, and
  the office set is now the answer rather than the input.

### 6. What "all clear" means without a sequence

Today `_all_clearances_done()` advancing to `rdco_review` is the pipeline's engine. Under
assignments it becomes a **notification, not a transition**: when the last non-RDCO assignment
closes and RDCO holds no open assignment, IRIS opens one for RDCO and tells them the record is
ready for decision. The record was already `in_review`; nothing about its phase changes.

This is the mechanical difference between the two models stated in one line: **the old pipeline
advanced records, the new one hands them back to RDCO.**

### 7. Clearance-aware resubmission under the new model

ADR-003's rule is unchanged in substance and gets *easier* to state, because "which offices had
cleared" is now a set of rows rather than a set inferred from a status:

**On resubmission after a decline, every `cleared` `RecordClearance` is preserved except the
declining party's, which resets to `pending`. The declining party's assignment is reopened.
Assignments closed as `cleared` stay closed.**

The sequential-vs-parallel branch in `_resolve_after_resubmission` disappears — there is no
"restart from the top", because there is no top to restart from. A decline by RDCO at intake
reopens RDCO's assignment; a decline by IERC reopens IERC's. What used to be two policies is
one rule.

**ADR-004's restart-all comparison arm survives**, and its definition is unchanged: reset
*every* clearance row rather than one. The two arms still differ in exactly one statement, run
against the same rows with a different filter, which is IR-137's acceptance criterion. See
§Research Impact for the part that does *not* survive unchanged.

### 8. Read surface

Two derived views, both server-computed, neither stored:

**Review tracker** — one entry per party that has ever held the record, plus the parties that
never did:

```
GET /api/v1/records/<id>/tracker/
{
  "phase": "in_review",
  "current_holders": ["ierc"],
  "parties": [
    {"party": "rdco", "label": "RDCO", "state": "cleared", "decided_at": "...", "note": "Intake completed"},
    {"party": "itso", "label": "ITSO", "state": "cleared", "decided_at": "..."},
    {"party": "ierc", "label": "IERC", "state": "active",  "opened_at": "...", "opened_by": "..."},
    {"party": "ktto", "label": "KTTO", "state": "not_requested"}
  ],
  "clearances": [ ... ],            // RecordClearance, unchanged (IR-139's payload)
  "document_requests": [ ... ]      // ADR-022
}
```

**Routing history** — `RoutingEvent` rows, grouped by `group_id`, newest last.

Both go through `Record.objects.visible_to(user)` like everything else. A tracker is a
description of who is reviewing someone's work: it is not more public than the record.

## What this changes in the accepted record

**ADR-018 is partially superseded.** Its four `Record` fields survive with a demoted job: the
submitter's requested set becomes the **suggested opening assignment set at intake**, which
RDCO confirms or edits. It no longer determines the route, because there is no longer a route
to determine. Two things follow: ADR-018's "RDCO amend UI" fast-follow is subsumed — amending
*is* rerouting — and its stated Negative consequence ("a submitter can under-request… the only
present safeguard is RDCO noticing") stops being a safeguard problem, because any office can
correct an under-request later.

**ADR-002 is amended, and the amendment costs it something.** Its key
`(from_status, event, actor_role) → to_status` no longer describes inter-office movement,
because the destination is now chosen by the actor rather than computed from the origin. The
table keeps the record-level edges and gains a party graph; what it loses is the claim that
*all* routing is a table lookup. This should be recorded plainly rather than presented as an
enhancement: the table shrinks, and a reader who was told "the workflow is thirty rows of data"
will now find nine rows of data and a graph.

**ADR-003 is untouched at the mechanism level** and its §Research Impact is open — below.

**ADR-009's authorization model is untouched.** One new per-record predicate
(`holds_open_assignment`) joins `owns_or_staffs_record()`; it does not replace anything.

## Alternatives Considered

**Keep the fixed pipeline; let RDCO amend the office set at intake.** This is ADR-018's own
fast-follow, and it is much cheaper — one screen, no data model. Rejected because it fixes the
wrong moment. The information that decides which offices are needed arrives *while the offices
are reading*, not at intake, so a better intake screen improves the guess without removing the
need to revise it. It also leaves (2) and (3) from §Context untouched: no routing history, no
way for an office to act on what it found.

**Add a single "escalate to RDCO" action and keep everything else fixed.** The minimal change
that addresses the most common real case. Rejected as a special case of the general one that
would have to be deleted when the general one arrived; and it does not help ITSO reach KTTO,
which is the example the team raised first.

**Model it as free-form assignment with no fixed bookends** — any reviewer routes to anyone,
including back to the submitter, with no mandatory intake. Rejected. The entry rule and RDCO's
exclusive terminal authority are what make this an *institutional* workflow rather than a
shared inbox, and they are also what is left of the type-differentiation half of the thesis
claim. Removing them would save very little code and lose the argument.

**Adopt a case-management engine (CMMN — Flowable, Camunda's case module).** This is the honest
prior art for what is being described, and it deserves naming rather than the BPMN comparison
ADR-002 and ADR-003 both use: ad-hoc, reviewer-directed routing over a shared case file is
exactly CMMN's subject. Rejected for the same reasons ADR-002 rejected BPM engines — a JVM
service alongside the existing five, for a graph that fits in a dict, and it would move the
contribution into a third-party engine. But see §Research Impact: rejecting the *engine* does
not dispose of the *prior art*.

**Do nothing this semester; ship the fixed pipeline and describe rerouting as future work.**
Genuinely viable and should be weighed seriously, because §MVP Impact's number is large. The
case against: the pilot runs a real institution's real disclosures in Week 11, and the fixed
pipeline's failure mode under real use is a decline sent to a student for an office-routing
problem the student cannot fix. That is a bad thing to discover with a customer watching.

## Decision Rationale

The deletion test passes, on a narrow reading. Remove `RecordAssignment` and `RoutingEvent` and
the questions they answer — who holds this, who sent it there, why — go back to being
un-answerable rather than answerable elsewhere. That is the signature of a structure earning
its place rather than relocating complexity.

The clearer argument is subtractive. Four pieces of machinery exist today purely because a
scalar is being asked to encode a set: `_stage_reviewed_by` disambiguating KTTO's two stages,
`_clearance_entry_for` reconstructing an entry status from an office set,
`_resolve_after_clearance`'s ITSO special case, and the `itso_review` / `parallel_review` split
itself, which is a sequence artefact rather than a real distinction — both are "some offices
are clearing". All four disappear, and none of them is replaced by an equivalent. The new model
is not merely more capable; on this axis it is smaller.

What it costs is honesty about ADR-002. "The workflow is a declarative table" was a clean claim
and it becomes a compound one. The table still holds the record's own lifecycle; the party
graph holds who may hand work to whom; and what a reviewer actually does is neither, it is an
action with an argument. That is a less elegant sentence to defend at a panel, and it is the
real price of this change.

## Consequences

**Positive.** "Which offices have this?" and "who sent it to IERC?" become fields rather than
inferences — the second is currently unrecoverable at any price. The audit trail IR-144/IR-216
needs is largely a serialization of `RoutingEvent` rather than a new mechanism. An
under-requested disclosure is correctable by any office instead of only by bouncing it to the
student. Four pieces of sequence-reconstruction machinery are deleted.

**Negative.** A data migration on `Record.pipeline_status`, the central domain object, touched
by the visibility predicate that IR-153 just secured. Every workflow test is rewritten — the
characterisation suite (IR-197) describes the pipeline this replaces. The frontend's review
surfaces (`EvaluationPage`, `ClearanceTrack`, `PeerClearanceStrip`) are rebuilt around holders
rather than stages. And a reviewer can now route a record somewhere useless; nothing in the
model prevents a record circulating between two offices indefinitely.

**Risk — the one worth stating separately.** [IR-233](https://citiris.atlassian.net/browse/IR-233)
is open and is an `mvp-blocker`: resubmitting a declined record lands straight back in
`declined`, so the clearance-aware path — the thesis contribution — **does not visibly run
today**. This ADR rewrites the module that bug lives in. Building the new model on top of an
unreproduced bug risks carrying it across and losing the ability to tell whether it was ever
fixed. **IR-233 should be reproduced and understood before this ADR is implemented**, even if
it ends up being fixed by the rewrite rather than before it.

## MVP Impact

**This is a large change and the estimate should be read before the design.** Against ADR-001's
~27 dev-day semester budget:

| Piece | Estimate |
|---|---|
| Data model, migration, `lifecycle.py` rewrite, `reviews/services.py` rewrite | 5–6 d |
| Permission predicate, authorization tests, workflow transition tests | 2–3 d |
| API: routing action, tracker and history read surfaces | 1–2 d |
| Frontend: reroute modal, review tracker, routing history, action set | 3–4 d |
| **Total (this ADR, routing only)** | **11–15 d** |

ADR-022 adds a further ~3 d.

**That is a third to a half of the entire semester's implementation budget, on a budget already
reversed four times** (ADR-013, ADR-016, ADR-019, ADR-020 each drew on it). Each reversal is
expected to name what it displaces, and **this one does not yet — that is the team's call, not
this ADR's.** The candidates, in the order this author would cut them: ADR-020's assessment
brief, ADR-019's persisted conversation history, and the remaining supporting frontend work
that CLAUDE.md's Scope rule already names as the first thing to go.

**Sequencing, if it is taken.** Three stages, each independently shippable:

1. **Model and services** — `RecordAssignment`, `RoutingEvent`, the migration, `route()`,
   `lifecycle.py`'s party graph, and every test. The API keeps serving today's shape from the
   new model, so nothing downstream breaks yet.
2. **Surfaces** — the routing action, the tracker and history endpoints, and the frontend
   rebuilt against them.
3. **Document requests** — ADR-022, which depends on assignments existing but on nothing else.

Do not interleave them. Stage 1 touches the write path for the central domain object; ADR-002
already warns that this is the highest-risk refactor in the plan, and that was before it also
carried a migration.

## SaaS Impact

Positive, and arguably this is the change that makes ADR-002's SaaS claim true rather than
nearly true. ADR-002's amendment concedes that adding a fourth office "touches one enum, one
role map and the table". Under a party graph the routing half of that is genuinely data: a
second institution with a different office structure edits `PARTIES` and its edges. Office
*identity* still lives in code — `core.enums.Office`, `RoleName`, a seeded `Role` row — so the
honest criterion ADR-002 settled on is unchanged, not improved.

## Security Impact

**One new object-level predicate, and it must be written once.** `holds_open_assignment(user,
record)` joins `owns_or_staffs_record()` in `core/permissions.py`. Every routing and review
endpoint checks it. CLAUDE.md's rule — never add an endpoint without an object-level permission
check — applies to three new endpoints here (route, tracker, history).

**The tracker and history are record data, not metadata.** Both go through
`Record.objects.visible_to(user)`; a refusal is a 404 identical to a missing record, per
IR-153. A routing history naming which offices hold a colleague's unpublished disclosure is
exactly as sensitive as the disclosure.

**A widened action set is a widened attack surface, and the office-cannot-reject rule is part
of the mitigation**: no single office account can terminate someone else's submission.

## Deployment Impact

One migration, and unlike ADR-018's it is **not** additive: it rewrites `pipeline_status`
values on every non-terminal record and backfills two new tables. Per CLAUDE.md it must be
tested against a copy of a realistic database, not an empty one. Take a `postgres_data` backup
before applying it in the pilot environment.

## Research Impact

**This is the section the team must answer, and it is deliberately left open.**

ADR-003 names clearance-aware resubmission as the primary contribution and answers the
anticipated objection — *"BPMN has done parallel gateways for fifteen years"* — by arguing that
standard BPMN does not natively express "on rejection at branch B, reset B only, preserve A and
C". **That answer is unaffected at the mechanism level: the rule survives this change verbatim,
and §Decision 7 arguably states it more cleanly than the pipeline did.**

What changes is the surrounding system, and therefore the comparison class. A workflow where
any holder may route to any party, over a shared case file with a clearance ledger, is not a
BPMN workflow being extended — it is close to **CMMN**, and to the ad-hoc-routing literature in
case and document management. A panel that would have asked about Camunda will now ask about
Flowable's case engine, about DSpace/EPrints workflow steps, and about ticketing systems with
arbitrary reassignment. **Two readings are available and the team must pick one, not discover
which at defence:**

- *Strengthens it.* Per-office clearance state that survives ad-hoc rerouting is a sharper
  claim than the same state surviving a fixed pipeline, because the ad-hoc case is where naive
  implementations reset everything. The contribution is now demonstrated against a harder
  baseline.
- *Weakens it.* Ad-hoc routing moves IRIS into a well-populated prior-art field, and the
  novelty argument now has to clear CMMN as well as BPMN. The narrow, defensible claim becomes
  a narrow claim in a crowded area.

**A second, concrete problem for ADR-004's evaluation.** The controlled comparison measures
clearance-aware against restart-all on time-on-task. Under a fixed pipeline the route length
was determined by record type, so the arms differed in one variable. Under reviewer-directed
routing **the route is chosen by participants**, so route length becomes a source of variance
the design did not account for. The comparison is still well-defined — the two arms differ in
one statement — but the measurement is noisier, and with a capstone-sized participant pool that
may matter. ADR-011's protocol needs a look before this is implemented, not after data
collection.

**Per CLAUDE.md, AI does not make research decisions.** Both questions above are recorded here
for the team, unresolved.

## Related Requirements

FR-M5-01 (hierarchical submission workflow) · FR-M5-03 · NFR-R3 (integrity under concurrency)
· NFR-S4 (object-level authorization). Ids are stable labels only — do not read the SRS for
their meaning (CLAUDE.md, source-of-truth hierarchy).

## Related Tasks

[IR-254](https://citiris.atlassian.net/browse/IR-254) (this ADR) · IR-53 (Epic B: Workflow and
Thesis Contribution) · IR-134/IR-136 (the transition table this amends) · IR-144 and IR-216
(workflow audit events — `RoutingEvent` is most of what they need) · IR-197 (characterisation
suite, which describes the pipeline this replaces) · **IR-233 (open `mvp-blocker`; reproduce
before implementing)** · IR-118 (Office Checklists — related but deferred, see ADR-022).
