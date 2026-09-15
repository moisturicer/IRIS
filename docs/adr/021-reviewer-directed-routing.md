# ADR-021: Intake, specialist review, and reviewer-directed routing

## Status

**Proposed** — 2026-09-15. **Revised the same day**, before acceptance, on a business-rule
clarification from the project lead. Tracked on
[IR-254](https://citiris.atlassian.net/browse/IR-254).

**Not accepted. Three questions in it are not the author's to settle** and are marked
**OPEN** where they arise: whether a Proposal must reach an RDCO institutional decision (§3.2),
whether the derived lifecycle states of §4 should instead be stored, and — in §Research
Impact — whether ad-hoc routing strengthens or weakens ADR-003's novelty argument. A fourth,
what this displaces against ADR-001's budget, is in §MVP Impact.

**Partially supersedes [ADR-018](018-conditional-parallel-office-routing.md)** — including
reversing its ITSO-is-Project-only rule — and **amends
[ADR-002](002-workflow-transition-table.md)**.

The inspection this rests on, with file-and-line evidence for every claim about current
behaviour, is [`docs/workflow_routing_architecture.md`](../workflow_routing_architecture.md).
This ADR states decisions; that document states findings.

### What the revision changed

The first draft got the routing mechanism right and the **semantics of intake wrong**. It
carried `rdco_intake` forward as a party named `rdco`, which reproduced the very reading the
clarification rejects: RDCO substantively reviewing a paper and then handing it down to a
specialist office. §1 and §2 below are new. §3.2 (Proposal → RDCO) and §5 (ITSO on
Thesis/Research) are new conflicts the first draft did not surface.

## Context

### The reading being corrected

Written as `Submitter → RDCO Intake → ITSO/IERC/KTTO → RDCO`, the workflow invites a backwards
reading: the institution's senior office reviews the work, then passes it *down* to a smaller
office, then takes it back. Under that reading every reroute looks like a regression and the
model is incoherent.

The intended model has three different things in it, and the pipeline names only two:

| | What it is | Who |
|---|---|---|
| **Intake & Triage** | *Administrative.* IRIS has received a submission; determine what reviews, documents or corrections are required before an institutional decision can be made. | RDCO staff, acting administratively |
| **Specialist review** | *Substantive, narrow.* Ethics, protectability, commercial viability — whichever are actually engaged by this work. | ITSO / IERC / KTTO, and the Adviser |
| **Final institutional review** | *Substantive, whole-record.* The institution's decision, informed by whatever specialist findings exist. | RDCO |

Triage dispatching to a specialist office is forward movement. The first and third being
performed by the same people is a staffing fact, not a workflow fact, and the model must not
confuse the two.

### What the code does, and where it contradicts that

Nine conflicts are catalogued in
[`workflow_routing_architecture.md` §3](../workflow_routing_architecture.md#3-conflicts-with-the-clarified-rule).
The four that drive decisions here:

- **Intake is a substantive review that can terminally reject.** `core/enums.py:57` labels it
  "RDCO Intake **Review**"; it writes a `Review` row carrying a decision; and
  `lifecycle.py:285` gives it an edge straight to `rejected`.
- **Triage has none of the triage actions.** Which offices review is read off three booleans
  *the student* set (`lifecycle.py:505`); ADR-018 records that RDCO's ability to amend them "is
  not implemented"; requesting a document has no mechanism; routing does not exist.
- **Thesis/Research cannot reach ITSO at all** (`lifecycle.py:519`), so the clarification's own
  example — *thesis involving IP + ethics → ITSO + IERC* — is impossible.
- **Specialist offices can terminally reject** (`reviews/services.py`, `EvaluationPage.tsx:39`).

And two things are already right and are not being rebuilt: a record requesting no specialist
office already goes intake → RDCO final (`lifecycle.py:550`), and IERC/KTTO genuinely run
concurrently.

## Decision

**A record's position is a set of open assignments plus a routing history, over six parties of
which `intake` and `rdco` are distinct. Any party holding an open assignment may route to one
or more other parties, with a reason. Entry is fixed by record type; only RDCO decides.**

### 1. Intake is a party, distinct from RDCO

```
Party = intake | adviser | itso | ierc | ktto | rdco
```

`intake` and `rdco` are **two parties staffed by the same role** (`RoleName.RDCO`), resolved
through a role→party map that is configuration, not code.

This is the decision that dissolves the backwards reading. Triage and final decision are
different acts with different authority, and modelling them as one party named `rdco` — which
the first draft did — keeps the confusion alive in the identifiers no matter what the labels
say. The clarification's own tracker example already assumes the split: it shows
`Submitter → Intake` in the routing history and `○ RDCO — Awaiting specialist reviews` as a
separate row.

**Intake's authority is deliberately narrower than RDCO's.** It may route, request documents,
request resubmission, and clear (dispatching the record onward). **It may not reject and it may
not publish.** A triage step that can end a submission is not triage; that is conflict A above,
and removing the edge is most of the fix.

**Intake gains the actions that make it triage** — routing and document requests — which today
it lacks entirely (conflict B). Confirming or amending the submitter's suggested office set
*is* rerouting; no separate "amend" screen is needed, which subsumes ADR-018's unimplemented
fast-follow.

### 2. Terminology

**Key `intake`. Staff-facing label "Intake & Triage". Student-facing label "Intake".**

The full comparison of candidates is in
[`workflow_routing_architecture.md` §11](../workflow_routing_architecture.md#11-terminology-recommendation-clarification-13).
In short: the key must lose `rdco`, because `rdco_intake` is a stored value in `PipelineStatus`,
`ReviewStage`, every `Review.stage` row and eight frontend files, and while that word is in the
identifier every reader re-derives the wrong model. "Institutional Intake" was rejected because
*institutional* is the word carrying RDCO's authority in "final institutional decision", and
reusing it for triage blurs the exact distinction being drawn. "Intake" alone was rejected
because it loses the *determines what is required* half — the half that makes routing out of
intake forward movement.

Two labels off one key costs nothing: ADR-002's amendment §4 already establishes that labels
are configuration and that the frontend never maps a key to English.

**This rename is a deliberate data migration, never a find-and-replace.**
`apps/tests/test_enum_vocabulary.py:8` exists to catch exactly this — *"if someone 'tidies'
`rdco_intake` to `intake`, this fails before a migration is ever written."* That test is
correct. It should fail, be read, and be updated alongside the migration.

### 3. Entry and exit are fixed by type; the middle is not

#### 3.1 Entry

| Type | Enters at |
|---|---|
| Proposal | `adviser` |
| Thesis / Research | `intake` |
| Project | `intake` |

A submitter never chooses their first reviewer.

#### 3.2 Exit — **OPEN QUESTION**

RDCO holds final institutional authority. For Thesis/Research and Project that is settled: only
`rdco` may reach `published`, `completed` or `rejected`.

**For a Proposal it is not settled, and this ADR does not settle it.** The clarification's §3
says a Proposal reaches an *"RDCO final institutional decision"*. Today it does not: a Proposal
goes `adviser_review → approved` and stops (`lifecycle.py:495`), with RDCO's only involvement a
bookkeeping `/complete/` call. ADR-003's route table records the same. The first draft of this
ADR also assumed the Adviser was the sole reviewer, and gave them reject authority on that
basis — so this contradicts the previous draft as well as the code.

Three readings, costed in
[`workflow_routing_architecture.md` §5.1](../workflow_routing_architecture.md#51-the-party-set--and-the-question-3g-raises):
mandatory RDCO review for Proposals; `/complete/` relabelled as the decision it already is; or
the Adviser routing to RDCO at discretion. **This analysis favours the third** as the most
literal reading of *"route toward RDCO when institutional decision is required"*, but it leaves
"required" undefined, and the first changes real workload at CIT-U. It is a business decision.

**It blocks nothing.** Every other part of this design is identical under all three readings,
so implementation of stages 1–2 can proceed while it is decided.

### 4. Lifecycle state: stored versus derived — **OPEN QUESTION**

The clarification §11 lists ten lifecycle states and says not to collapse everything into one
field. **Agreed on the instruction; this ADR proposes a different split than the literal list,
and flags it rather than making it quietly.**

Store what is a fact about the *record*. Derive what is a fact about its *assignments and
requests*. Expose the whole list as a derived `workflow_state` the UI reads, so nothing is lost
to the user.

| Stored on `Record.pipeline_status` | Derived |
|---|---|
| `draft` · `in_review` · `declined` · `rejected` · `approved` · `completed` · `published` · `pending_delete` | `submitted` · `awaiting_document` · `awaiting_resubmission` · `final_review` |

The reasoning is the defect being removed. The moment `awaiting_document` is a stored status,
two things can disagree — the status column and the open-request table. That is today's bug
class exactly: `_stage_reviewed_by` (`lifecycle.py:655`) exists because `pipeline_status` and
`RecordClearance` each half-know where KTTO is. Deriving gives the question one answer by
construction.

`pipeline_status` is **narrowed, not deleted**: `Record.objects.visible_to()` and
`PUBLICLY_VISIBLE_STATUSES` filter on it and IR-153 only just secured that predicate.

**If the team prefers these stored, say so** — one migration either way. The cost lands on
consistency, not on effort.

### 5. Specialist review is conditional, and ITSO opens to Thesis/Research

No record is forced through an office because the office exists. Which specialists review is
determined at triage from the work itself, and revised by whoever discovers a need later.

**ADR-018's rule that ITSO is structurally Project-only is reversed.** It makes the
clarification's own example impossible, and a thesis that produces patentable work is exactly
the case IRIS exists for. `requested_itso` stops being ignored for Thesis/Research; ITSO becomes
a party any record may be routed to.

ADR-018's four `Record` fields survive with a demoted job: the submitter's requested set becomes
a **triage suggestion**, not the route. Its stated negative — *"a submitter can under-request…
the only present safeguard is RDCO noticing"* — stops being a safeguard problem, because any
holder can correct an under-request at any time.

### 6. Initial routing and dynamic rerouting are the same mechanism, named differently

One action, `route(record, actor, targets, reason)`. What the clarification calls **initial
routing** is triage's first use of it; **dynamic rerouting** is any later use by any holder. The
distinction is real to a reader of the tracker and is recoverable from `RoutingEvent`
(`from_party is null` ⇒ submission; `from_party == intake` and first ⇒ initial routing). It is
**not** two mechanisms, and making it two would be the beginning of the hardcoded state machine
§12 of the clarification forbids.

The action:

- Refuses unless `actor` holds an open assignment on the record.
- Refuses a target the actor's party may not route to, per the party graph.
- Opens a `RecordAssignment` per target if none is active, and writes one `RoutingEvent` per
  target, all sharing a `group_id` — so `Intake → ITSO + IERC` renders as one movement.
- Opens a `RecordClearance` for a clearing-office target if none exists. **An existing
  `cleared` row is not reset by routing.** Re-routing to an office that has already cleared is
  a legitimate "please look again"; whether that invalidates the prior clearance is that
  office's call, made by its next `Review`, not the router's.
- Does not close the actor's own assignment. An office may bring in a peer and keep working.
- `transaction.atomic()`, like every other lifecycle write (IR-138).

### 7. The action set

| Action | Intake | Adviser | ITSO / IERC / KTTO | RDCO |
|---|---|---|---|---|
| **Clear** (close my assignment) | ✓ | ✓ | ✓ | ✓ |
| **Reroute** (multi-select) | ✓ | ✓ | ✓ | ✓ |
| **Request document** | ✓ | ✓ | ✓ | ✓ |
| **Request resubmission** | ✓ | ✓ | ✓ | ✓ |
| **Record a finding / recommendation** | — | ✓ | ✓ | ✓ |
| **Reject** (terminal) | ✗ | **OPEN, §3.2** | ✗ | ✓ |
| **Final decision** (publish / complete) | ✗ | **OPEN, §3.2** | ✗ | ✓ |

**A specialist office cannot reject, and this is a change to current behaviour.** Today
`submit_clearance` maps a `rejected` decision straight to `PipelineStatus.REJECTED`, and
`EvaluationPage` offers Reject to every reviewer — so one ITSO officer can end a submission the
institution has not ruled on. Per the clarification §8, a specialist's negative finding feeds
the institutional decision; it is not the decision. An objecting office clears with a negative
`Review` and routes to RDCO. Three terminal vetoes would make the final decision structurally
meaningless — RDCO would be ratifying whichever office moved first.

**Authorization stays out of the table.** ADR-002's amendment §6 makes the point and it holds
harder here: `_can_review` checks `record.adviser_id == user.pk` — the *assigned* adviser — and
now also "does this user's party hold an open assignment", which is a per-record condition a
role-keyed table cannot express. The table declares which routes are *legal*; `core.permissions`
decides who may take them. Two checks, both must pass.

### 8. Data model

```
NEW  RecordAssignment  (record, party, state, opened_by/at, closed_by/at, reason)
                       state ∈ active | cleared | declined | rejected | withdrawn
                       ≤ 1 active row per (record, party)
NEW  RoutingEvent      (record, actor, from_party, to_party, reason, group_id, created_at)
NEW  DocumentRequest + DocumentRequestItem                       — ADR-022
EXT  Review            + assignment FK (nullable); `stage` unchanged, so historical
                         rdco_intake rows stay readable
KEEP RecordClearance   unchanged
```

**`RecordAssignment` and `RecordClearance` are deliberately not merged.** An assignment answers
*"is this party acting now?"*; a clearance answers *"has this office signed off, and does that
signature still stand?"* The whole contribution is that the second survives events ending the
first. One row with one status makes a preserved clearance unrepresentable.

`RecordClearance` stays the three clearing offices per `core.enums.Office`. Intake, Adviser and
RDCO record `Review` rows against their assignment instead. Widening `Office` would let a caller
construct an RDCO clearance the workflow has no gate for — the same argument `core/enums.py`
already makes for keeping RDCO out of that enum.

### 9. `lifecycle.py` — evolved, not extended

The module stays, settings-overridable, as ADR-002 decided:

- **`STAGES` → `PARTIES`**: per party, its labels, whether it clears or gates, and which parties
  it may route to.
- **`TRANSITIONS` narrows to record-level edges** — roughly nine rows: submit, decline,
  resubmit, publish, complete, reject, and the delete/restore edges. Inter-party movement stops
  being an edge.
- **`ENTRY_PARTY`** replaces `_resolve_first_status`.
- `_resolve_after_clearance`, `_resolve_enter_clearance_stage`, `_clearance_entry_for` and
  `_stage_reviewed_by` are **deleted**. They compute a status from an office set; the office set
  is now the answer, not the input.

**Why not just add edges — `RDCO → ITSO`, `ITSO → IERC`, and so on.** The clarification §12
forbids it on complexity grounds, and the code supplies a sharper reason. `_resolve_after_
adviser_review` (`lifecycle.py:495`) ends `else PipelineStatus.PUBLISHED`. That branch is
unreachable today because a non-Proposal never enters `adviser_review`. Add an edge letting an
Adviser hold a Thesis and **an adviser approving it publishes it, bypassing RDCO entirely.** The
existing statuses carry assumptions about which types can reach them; extending the table arms
those assumptions as live defects one at a time.

### 10. "All clear" becomes a notification, not a transition

Today `_all_clearances_done()` advancing to `rdco_review` is the pipeline's engine. Under
assignments: when the last non-RDCO assignment closes and RDCO holds none, IRIS opens one for
RDCO and tells them the record is ready. The phase was already `in_review` and does not change.

The two models differ in one line: **the old pipeline advanced records; the new one hands them
to RDCO.**

### 11. Clearance-aware resubmission

ADR-003's rule is unchanged in substance and simpler to state, because "which offices had
cleared" is a set of rows rather than a set inferred from a status:

**On resubmission after a decline, every `cleared` `RecordClearance` is preserved except the
declining party's, which resets to `pending`. The declining party's assignment is reopened.
Assignments closed as `cleared` stay closed. Review and routing history are never deleted.**

The sequential-vs-parallel branch in `_resolve_after_resubmission` disappears — there is no
"restart from the top", because there is no top. A decline at intake reopens intake; a decline
by IERC reopens IERC. Two policies become one rule.

**ADR-004's restart-all arm survives**, unchanged: reset *every* clearance row rather than one.
The arms still differ in exactly one statement against the same rows, which is IR-137's
acceptance criterion.

### 12. Read surface

`GET /api/v1/records/<id>/tracker/` answers all nine questions the clarification §10 requires,
each from rows that exist for other reasons — mapping in
[`workflow_routing_architecture.md` §6](../workflow_routing_architecture.md#6-the-tracker-mechanically).
Nothing about it is stored, and nothing is frontend-only state.

The distinction the current UI cannot draw — a party never asked versus asked and not started —
falls out of the model: "never asked" is *has no assignment row at all*.

The payload goes through `Record.objects.visible_to(user)`; a refusal is a 404 identical to a
missing record (IR-153).

## What this changes in the accepted record

**ADR-018 — partially superseded.** Its ITSO-is-Project-only rule is reversed (§5). Its
requested-office booleans become a triage suggestion. Its unimplemented "RDCO amend UI"
fast-follow is subsumed by rerouting. Its recorded gap — no `request_document` mechanism — is
closed by ADR-022.

**ADR-002 — amended, and the amendment costs it something.** Its key
`(from_status, event, actor_role) → to_status` no longer describes inter-party movement, because
the destination is now an argument rather than a computation. The table keeps the record's own
lifecycle and gains a party graph. What it loses is the claim that *all* routing is a table
lookup, and that should be recorded plainly rather than sold as an enhancement: a reader told
"the workflow is thirty rows of data" will find nine rows and a graph.

**ADR-003 — untouched at the mechanism level.** Its §Context route table becomes historical.
§Research Impact below is open.

**ADR-009 — additive.** One new per-record predicate, `holds_open_assignment`.

**ADR-011 — needs a look before implementation**, per §Research Impact.

## Alternatives Considered

**Relabel `rdco_intake` and change nothing else.** The cheapest response to the clarification:
the objection was about how the workflow *reads*, so fix the words. Rejected because conflict B
survives it — the triage step would still have no way to determine what reviews or documents are
required, which is the entire job the clarified rule assigns it. A correct label on a step that
cannot do the thing it is named for is worse than the wrong label, because it stops anyone
looking.

**Keep the fixed pipeline; let intake amend the office set at intake only.** ADR-018's own
fast-follow. Rejected: the information deciding which specialists are needed arrives *while
they are reading*, so a better intake screen improves the initial guess without removing the
need to revise it. It also leaves ITSO closed to Thesis/Research, and leaves no routing history.

**Add the transitions as edges** — `intake → itso`, `itso → ierc`, `ierc → ktto`, `ktto → rdco`.
Rejected on the clarification's own §12 grounds and on §9's evidence: the existing statuses
carry unreachable-branch assumptions that extending the table turns into live defects.

**Model intake as a `Party` but keep RDCO as one party performing both roles.** Nearly this
design, one identifier cheaper. Rejected because it is the first draft's mistake: while the same
party name covers triage and final decision, the tracker cannot show "✓ Intake / ○ RDCO awaiting
specialist reviews", and the backwards reading has nowhere to be corrected.

**Model it as free-form assignment with no fixed bookends.** Rejected. Type-differentiated entry
and RDCO's exclusive terminal authority are what make this an *institutional* workflow rather
than a shared inbox, and they are what is left of the type-differentiation half of the thesis
claim.

**Adopt a case-management engine (CMMN — Flowable, Camunda's case module).** The honest prior
art, and it deserves naming rather than the BPMN comparison ADR-002 and ADR-003 both use:
ad-hoc, reviewer-directed routing over a shared case file is exactly CMMN's subject. Rejected
for the reasons ADR-002 rejected BPM engines — a JVM service beside the existing five, for a
graph that fits in a dict, and it would move the contribution into a third-party engine. But
rejecting the *engine* does not dispose of the *prior art*: see §Research Impact.

**Ship the fixed pipeline; describe this as future work.** Viable, and worth weighing because
§MVP Impact's number is large. Against it: the pilot runs real disclosures in Week 11, and this
pipeline's failure mode under real use is a decline sent to a student for an office-routing
problem the student cannot fix — plus a thesis with patentable output that cannot reach ITSO at
all.

## Decision Rationale

The subtractive argument is the strong one. Four pieces of machinery exist today purely because
a scalar is asked to encode a set: `_stage_reviewed_by` disambiguating KTTO's two stages,
`_clearance_entry_for` reconstructing an entry status from an office set,
`_resolve_after_clearance`'s ITSO special case, and the `itso_review` / `parallel_review` split
itself — which is a sequence artefact, not a real distinction, since both mean "some offices are
clearing". All four are deleted and none is replaced. On that axis the new model is *smaller*,
not merely more capable.

The deletion test passes on the new structures too: remove `RecordAssignment` and `RoutingEvent`
and the questions they answer — who holds this, who sent it there, why — become unanswerable
rather than answered elsewhere. "Who asked IERC to look at this?" is currently unrecoverable at
any price.

Separating `intake` from `rdco` earns its place differently: it costs one identifier and buys
the coherence of the whole model. With one `rdco` party, "RDCO reviews it, then sends it to
ITSO, then reviews it again" is the only available description, and it is the description the
clarification was written to reject.

What this costs is honesty about ADR-002. "The workflow is a declarative table" was a clean
claim; it becomes a compound one — the table holds the record's lifecycle, the party graph holds
who may hand work to whom, and what a reviewer does is neither, it is an action with an
argument. That is a less elegant sentence to defend at a panel, and it is the real price.

## Consequences

**Positive.** A thesis with patentable output can reach ITSO. Triage can do the job it is named
for. "Which offices have this?" and "who sent it to IERC?" become fields rather than
inferences — the second is currently unrecoverable. No office can unilaterally end another
person's submission. The audit trail IR-144/IR-216 needs is largely a serialization of
`RoutingEvent`. Four pieces of sequence-reconstruction machinery are deleted.

**Negative.** A data migration on `Record.pipeline_status`, the central domain object, touched
by the visibility predicate IR-153 just secured. Roughly 2,700 lines of backend test describe
the pipeline being replaced (inventory in
[`workflow_routing_architecture.md` §8](../workflow_routing_architecture.md#8-tests-that-must-change)),
including IR-197's characterisation suite, whose retirement is a decision to record rather than
a cleanup. Every reviewer-facing frontend surface is rebuilt. And a reviewer can now route a
record somewhere useless; nothing prevents a record circulating between two offices
indefinitely.

**Risk.** [IR-233](https://citiris.atlassian.net/browse/IR-233) is open and is an `mvp-blocker`:
resubmitting a declined record lands straight back in `declined`, so clearance-aware
resubmission — the thesis contribution — **does not visibly run today**. This ADR rewrites the
module that bug lives in. **Reproduce and understand IR-233 before implementing**, even if the
rewrite is what fixes it; otherwise it travels across and nobody can say whether it was ever
fixed.

## MVP Impact

| Piece | Estimate |
|---|---|
| Data model, migration, `lifecycle.py` and `reviews/services.py` rewrite | 6–7 d |
| Permission predicate, authorization tests, new workflow suite | 3 d |
| API: routing action, tracker and history | 1–2 d |
| Frontend: reroute modal, tracker, routing history, action set | 3–4 d |
| **Total (routing only)** | **13–16 d** |

ADR-022 adds ~3 d.

**That is roughly half the semester's implementation budget, on a budget ADR-001 costed at ~27
dev-days and which has already been reversed four times** (ADR-013, ADR-016, ADR-019, ADR-020).
Each reversal is expected to name what it displaces. **This one does not — that is the team's
call.** In the order this author would cut: ADR-020's assessment brief, ADR-019's persisted
conversation history, then the supporting frontend work CLAUDE.md's Scope rule already names as
first to go.

**Sequencing — three stages, not interleaved.** (1) Model and services, with the API still
serving today's shape so nothing downstream breaks. (2) Surfaces. (3) ADR-022. Stage 1 touches
the write path for the central domain object; ADR-002 already calls that the highest-risk
refactor in the plan, and that was before it also carried a migration.

## SaaS Impact

Positive, and this is arguably what makes ADR-002's SaaS claim true rather than nearly true. Its
amendment concedes that adding a fourth office "touches one enum, one role map and the table";
under a party graph the routing half is genuinely data. The role→party map also means a second
institution that separates triage from its research office into two actual teams changes
configuration, not code. Office *identity* still lives in code — `core.enums.Office`, `RoleName`,
a seeded `Role` row — so ADR-002's honest criterion is unchanged, not improved.

## Security Impact

**One new object-level predicate, written once.** `holds_open_assignment(user, record)` joins
`owns_or_staffs_record()` in `core/permissions.py`. Three new endpoints (route, tracker, history)
check it — CLAUDE.md's rule that no endpoint ships without an object-level check.

**The tracker and history are record data, not metadata.** Both through
`Record.objects.visible_to(user)`; refusal is a 404 identical to a missing record (IR-153). A
routing history naming which offices hold a colleague's unpublished disclosure is exactly as
sensitive as the disclosure.

**Two authority reductions are net security improvements**: intake loses terminal rejection, and
specialist offices lose it too. No single office account can end someone else's submission.

## Deployment Impact

One migration, **not** additive: it rewrites `pipeline_status` on every non-terminal record,
renames the intake vocabulary, and backfills two new tables from `RecordClearance` plus record
type. Per CLAUDE.md, test it against a copy of a realistic database, not an empty one. Take a
`postgres_data` backup before applying it in the pilot environment.

## Research Impact

**OPEN — this is the team's to answer, not the author's.**

ADR-003 answers the anticipated objection — *"BPMN has done parallel gateways for fifteen
years"* — by arguing that standard BPMN does not natively express "on rejection at branch B,
reset B only, preserve A and C". **That answer is unaffected at the mechanism level: the rule
survives verbatim, and §11 states it more cleanly than the pipeline did.**

What changes is the comparison class. A workflow where any holder may route to any party, over a
shared case file with a clearance ledger, is not an extended BPMN workflow — it is close to
**CMMN**, and to the ad-hoc-routing literature in case and document management. A panel that
would have asked about Camunda will ask about Flowable's case engine, DSpace/EPrints workflow
steps, and ticketing systems with arbitrary reassignment. Two readings, and the team must pick
one rather than discover which at defence:

- *Strengthens it.* Per-office clearance surviving **ad-hoc** rerouting is a sharper claim than
  the same state surviving a fixed pipeline, because ad-hoc routing is precisely where naive
  implementations reset everything. The contribution is demonstrated against a harder baseline.
- *Weakens it.* Ad-hoc routing moves IRIS into a well-populated prior-art field; the novelty
  argument must now clear CMMN as well as BPMN. A narrow defensible claim becomes a narrow claim
  in a crowded area.

**A second, concrete problem for ADR-004's evaluation.** The comparison measures clearance-aware
against restart-all on time-on-task. Under a fixed pipeline, route length was determined by
record type, so the arms differed in one variable. Under reviewer-directed routing **the route
is chosen by participants**, so route length becomes variance the design did not account for.
The comparison stays well-defined — one statement differs — but the measurement is noisier, and
with a capstone-sized participant pool that may matter. **ADR-011's protocol needs a look before
implementation, not after data collection.**

Per CLAUDE.md, AI does not make research decisions. Both are recorded here unresolved.

## Related Requirements

FR-M5-01 (hierarchical submission workflow) · FR-M5-03 · NFR-R3 (integrity under concurrency) ·
NFR-S4 (object-level authorization). Ids are stable labels only — do not read the SRS for their
meaning (CLAUDE.md, source-of-truth hierarchy).

## Related Tasks

[IR-254](https://citiris.atlassian.net/browse/IR-254) (this ADR) · IR-53 (Epic B) ·
IR-134/IR-136 (the table this amends) · IR-144 and IR-216 (workflow audit events — `RoutingEvent`
is most of what they need) · IR-197 (characterisation suite, retired by this change) ·
IR-224 (end-to-end clearance-aware demonstration) · **IR-233 (open `mvp-blocker`; reproduce
first)** · IR-118 (Office Checklists — deferred, see ADR-022).
