# Workflow routing — current state, conflicts, and the shape of the change

**Status: analysis, not a decision.** The decisions live in
[ADR-021](adr/021-reviewer-directed-routing.md) and
[ADR-022](adr/022-explicit-document-requests.md), both **Proposed**. This document is the
inspection those ADRs rest on: what the code does today, where it contradicts the clarified
business rule of 2026-09-15, what must change, and — as importantly — what must not.

Every claim about current behaviour below is cited to a file and line and was read, not
recalled. Tracked on [IR-254](https://citiris.atlassian.net/browse/IR-254).

---

## 1. The clarified rule, in one paragraph

Intake is **administrative triage**: IRIS has received a submission and determines what
reviews, documents or corrections are required before an institutional decision. It is *not*
RDCO substantively reviewing the work and then handing it down. Specialist offices
(ITSO/IERC/KTTO) review only when their specialism is actually engaged. RDCO makes the final
institutional decision and may also assess a record itself. Any reviewer who discovers that
another review is needed may reroute, to one or more destinations at once. A record therefore
has several concurrent assignments, a review history, a routing history, document requests and
a clearance ledger — not one stage field.

---

## 2. What the code does today

### 2.1 The pipeline

`backend/apps/records/lifecycle.py` (IR-136) holds `STAGES` (5 nodes) and `TRANSITIONS`
(~30 edges keyed `(from_status, event)`). `Record.pipeline_status` is a single
`CharField`. Routing is resolved by four functions, not chosen by anyone:

| Resolver | `lifecycle.py` | What it decides |
|---|---|---|
| `_resolve_first_status` / `first_status_for` | `:691`, `:737` | Proposal → `adviser_review`, else `rdco_intake` |
| `_resolve_enter_clearance_stage` | `:505` | Which `RecordClearance` rows exist, from three booleans |
| `_clearance_entry_for` | `:532` | `itso_review` / `parallel_review` / `rdco_review` from an office set |
| `_resolve_after_clearance` | `:553` | ITSO-then-IERC sequencing; "all clear" → `rdco_review` |

### 2.2 What is genuinely right already

Worth stating before the conflicts, because two of the clarified rule's requirements are
**already satisfied** and should not be rebuilt:

- **A record is not forced through every office.** `_clearance_entry_for([])` returns
  `rdco_review` (`lifecycle.py:550`). A Thesis requesting no specialist office already goes
  intake → RDCO final. ADR-018 did this.
- **IERC and KTTO genuinely run concurrently.** Two `RecordClearance` rows, both `pending`,
  either may clear first; `_all_clearances_done` (`lifecycle.py:729`) gates advancement. The
  parallel half of the model exists.
- **Per-office clearance survives a peer's decline.** `_resolve_after_resubmission`
  (`lifecycle.py:606`) resets only the declining office. This is the thesis contribution and it
  is implemented.

---

## 3. Conflicts with the clarified rule

Nine, ordered by how much they cost to fix. **A–C are semantic and cheap. D–F are structural.
G–I are gaps.**

### A. Intake is modelled as a substantive review, and can terminally reject

The clarified rule says intake must not be represented as RDCO having already decided. The code
represents it as exactly that:

| Evidence | |
|---|---|
| `core/enums.py:57` | `RDCO_INTAKE = "rdco_intake", "RDCO Intake **Review**"` |
| `core/enums.py:89` | `ReviewStage.RDCO_INTAKE` — intake writes a `Review` row with a **decision** |
| `lifecycle.py:285` | `(RDCO_INTAKE, REJECT) → PipelineStatus.REJECTED` — **triage can terminally reject** |
| `notifications/services.py:125` | labels it `"RDCO (intake review)"` to the student |
| `EvaluationPage.tsx:53` | `rdco_intake: "RDCO Intake Review"` |
| `EvaluationPage.tsx:20–46` | intake gets the same three-action form as a final review: Approve / Request Revision / **Reject** |

A triage step that writes a verdict and can end the record is not triage. This is the single
clearest instance of the "backward" problem the clarification names.

### B. Triage has none of the triage actions

§2 of the clarified rule lists what intake must determine: required reviews, required
documents, whether the record can go straight to RDCO. The intake actor can do **none** of
these deliberately:

- **Which offices review** is read off three booleans *the student set in the wizard*
  (`Record.requested_itso/ierc/ktto`, `records/models.py:170–172`), consumed at
  `lifecycle.py:505`. ADR-018 §Decision states plainly that RDCO's ability to amend that set
  "is **not implemented by this ADR** — `EvaluationPage` currently shows the request
  read-only."
- **Requesting a document** has no mechanism at all. ADR-018 §Status says so in its own words:
  *"there is no `request_document` mechanism in the system, and the request is therefore
  invisible to the record."*
- **Routing** does not exist as an action anywhere.

So the one job the clarified rule assigns to triage is precisely the job the triage step cannot
perform. Fixing A (the label) without fixing B would be cosmetic.

### C. Terminology binds RDCO to intake in the enum key itself

`rdco_intake` is the stored value, not just a label — in `PipelineStatus`, in `ReviewStage`, in
every `Review.stage` row already written, and in the frontend's `constants.ts:47`,
`utils.ts:20`, `StatusBadge.tsx:9`, `PaperViewPage.tsx:45`, `workspaceStages.ts:41`.

**And there is a test that exists specifically to stop this rename.**
`backend/apps/tests/test_enum_vocabulary.py:8` — *"if someone 'tidies' `rdco_intake` to
`intake`, this fails before a migration is ever written."* That test is correct and doing its
job; it means the rename is a deliberate data migration, never a find-and-replace. See §8.

### D. Thesis/Research **cannot** reach ITSO — the clarified rule's own example is impossible

The clarification gives this example:

> Thesis involving IP + ethics: Submitter → Intake & Triage → **ITSO + IERC** → RDCO final review

`lifecycle.py:519`:

```python
if type_name == RecordTypeName.PROJECT and record.requested_itso:
    offices.append(Office.ITSO)
```

**ITSO is Project-only, structurally.** A Thesis/Research with `requested_itso=True` gets no
ITSO clearance row, silently. ADR-018 §Decision states this as intent: *"ITSO remains
structurally Project-only — Thesis/Research never enters `itso_review`, requested or not."*

This is a direct contradiction between an accepted ADR and the clarified business rule, and it
is the finding with the highest ratio of impact to fix cost: a thesis that produces patentable
work is exactly the case IRIS exists for.

### E. Specialist offices can terminally reject the record

`reviews/services.py:submit_clearance` maps decision `rejected` → `ClearanceStatus.REJECTED`
and dispatches `WorkflowEvent.REJECT`, whose edges (`lifecycle.py:316`, `:328`) go to
`PipelineStatus.REJECTED`. `EvaluationPage.tsx:39–45` offers **Reject** to every reviewer,
office reviewers included.

§8 of the clarified rule: *"Do not model a specialist office's negative finding as
automatically equivalent to a final institutional rejection."* Today it is exactly that. One
ITSO officer can end a submission the institution has not ruled on.

### F. A single scalar cannot hold concurrent assignments across parties

`pipeline_status` is one value. Concurrency exists only *inside* two hardcoded groups —
`itso_review = (ITSO, KTTO)`, `parallel_review = (IERC, KTTO)` (`lifecycle.py:242–249`). So:

- Adviser and ITSO can never hold a record simultaneously. §5's example
  `Intake → Adviser → ITSO + IERC → RDCO` is unrepresentable.
- KTTO appears in **two** groups, which forces `_stage_reviewed_by` (`lifecycle.py:655`) to
  disambiguate which stage a resubmission returns KTTO to. That function is a symptom of a
  scalar being asked to encode a set.
- `reviews/views.py:63–68` maps role → statuses to build the review queue. A queue built from
  "what status is the record in" cannot express "this office was asked, that one was not."

### G. Proposal never reaches RDCO — **this is new, and it conflicts with ADR-021 v1 too**

The clarified rule's §3:

> Proposal: Submitter → Adviser → … → **RDCO final institutional decision** → Published / Completed

The code (`lifecycle.py:495`, `_resolve_after_adviser_review`):

```python
return PipelineStatus.APPROVED if type_name == PROPOSAL else PipelineStatus.PUBLISHED
```

A Proposal goes `adviser_review → approved` and stops. RDCO's only involvement is
`records/views.py`'s `/complete/` action — bookkeeping, not a review. ADR-003's own route table
records the same: `Proposal: draft → adviser_review → approved → completed`.

**This also contradicts the first draft of ADR-021**, which kept the Adviser as sole reviewer on
Proposals and gave them reject authority on that basis. It is an open question, not a settled
one — see §5.1.

### H. A dead branch becomes live under rerouting

The `else PipelineStatus.PUBLISHED` half of `_resolve_after_adviser_review` is unreachable
today, because a non-Proposal never enters `adviser_review`. Under the clarified rule an Adviser
*can* hold a Thesis (`Intake → Adviser → …`). If Adviser holding is implemented by putting the
record in `adviser_review`, **an adviser approving a Thesis publishes it, bypassing RDCO
entirely.**

Nothing is wrong with the line today. It is a landmine that arms itself the moment rerouting
ships on top of the existing statuses, and it is the strongest single argument against
implementing rerouting as extra edges in the current table (which §12 of the clarification also
forbids, for different reasons).

### I. No routing history, no document requests, no persisted tracker

- **Who sent it to IERC** is unrecoverable at any price. No table records it.
- **Document requests** do not exist (§3.B).
- **The tracker** is `ClearanceTrack.tsx` (105 lines) plus `PeerClearanceStrip.tsx` — per-office
  clearance only. It cannot answer "which offices were never requested" versus "requested and
  not started", and it has no routing history to show. §10 of the clarified rule requires nine
  questions answered; the current surface answers three.

---

## 4. Which ADRs are affected

| ADR | Effect |
|---|---|
| **002** Workflow as a declarative transition table | **Amended.** The table stops resolving inter-office destinations; it keeps the record's own lifecycle edges and gains a party graph. Its `(from_status, event) → to_status` key no longer describes routing. |
| **003** Clearance-aware resubmission | **Mechanism untouched**, and simpler to state. Its §Context route table becomes historical. §Research Impact is an open question — see ADR-021. |
| **004** Restart-all comparison policy | **Both arms survive**, differing in one statement as IR-137 requires. Route length becomes participant-chosen, which adds variance to ADR-011's measurement. |
| **009** Authorization model | **Additive.** One new per-record predicate, `holds_open_assignment`. |
| **011** ISO 9241-11 evaluation spine | **Needs review before implementation**, for the variance point above. |
| **018** Conditional parallel-office routing | **Partially superseded.** Requested offices become a triage *suggestion*, not the route. Its ITSO-is-Project-only rule (§3.D) is **reversed**. Its unimplemented "RDCO amend UI" fast-follow is subsumed by rerouting. |
| **021** Reviewer-directed routing | **Rewritten** for this clarification: intake becomes a party distinct from RDCO, ITSO opens to Thesis, and §3.G is raised as an open question. |
| **022** Explicit document requests | **Confirmed and extended.** §9 of the clarification restates it; the `awaiting_document` state is added to the derived lifecycle. |

Not affected: 001 (scope — but see the budget question), 005, 007, 008, 010, 012–017, 019, 020.

---

## 5. Proposed minimal domain change

Two new models, one extended, one narrowed. Nothing else in the domain moves.

```
NEW  RecordAssignment   (record, party, state, opened_by/at, closed_by/at, reason)
                        ≤ 1 active row per (record, party)
NEW  RoutingEvent       (record, actor, from_party, to_party, reason, group_id, created_at)
NEW  DocumentRequest    + DocumentRequestItem                    — ADR-022
EXT  Review             + assignment FK (nullable); `stage` unchanged
KEEP RecordClearance    unchanged — the clearance ledger, and ADR-003's contribution
NARROW Record.pipeline_status  → lifecycle phase only (see §5.2)
```

**`RecordAssignment` and `RecordClearance` stay separate.** An assignment answers *"is this
party acting now?"*; a clearance answers *"has this office signed off, and does that signature
still stand?"* The contribution is that the second survives events ending the first. One row
with one status cannot express a preserved clearance.

### 5.1 The party set — and the question §3.G raises

```
Party = intake | adviser | itso | ierc | ktto | rdco
```

`intake` and `rdco` are **distinct parties staffed by the same role** (`RoleName.RDCO`), via a
role→party map that is configuration. This is what makes "intake → ITSO" forward movement
rather than backward: triage dispatches, RDCO decides, and they are not the same step even when
they are the same people. The clarified rule's own tracker example confirms the split — it
lists `Submitter → Intake` in the routing history and `○ RDCO — Awaiting specialist reviews` as
a separate tracker row.

**Open question for the team, not decided here.** §3.G says a Proposal should reach an RDCO
final institutional decision. Three readings, and they cost differently:

1. **RDCO final review becomes mandatory for Proposals too.** Cleanest model — one rule for
   every type, `ENTRY_PARTY` differs and nothing else. Changes real behaviour: a proposal
   that today is approved by an adviser and immediately visible as ongoing research would now
   wait on RDCO. Ask whether CIT-U's RDCO wants that volume.
2. **`/complete/` already is the institutional decision**, and the terminology just needs to say
   so. Zero behaviour change; arguably a relabelling of a bookkeeping action as an authority it
   does not exercise.
3. **Adviser clears, then routes to RDCO when an institutional decision is warranted** —
   discretionary rather than mandatory. Matches §3's wording *"route toward RDCO when
   institutional decision is required"* most literally, and is the reading this analysis
   favours, but it leaves "required" undefined.

This changes who does how much work at CIT-U, so it is a business decision. **It blocks nothing
else** — every other part of the design is identical under all three.

### 5.2 Lifecycle state: stored versus derived

§11 of the clarification lists `DRAFT · SUBMITTED · IN_REVIEW · AWAITING_DOCUMENT ·
AWAITING_RESUBMISSION · FINAL_REVIEW · PUBLISHED · REJECTED · DECLINED · COMPLETED` and says not
to collapse everything into one field.

**Proposal — and it is a proposal, because it departs from the literal list.** Store the phases
that are facts about the *record*; derive the ones that are facts about its *assignments and
requests*. Expose the full list as one derived `workflow_state` the UI reads, so nothing is
lost to the user.

| State | Stored or derived | Why |
|---|---|---|
| `draft` | **stored** | The record is not in the workflow |
| `in_review` | **stored** | The record is in the workflow |
| `declined` | **stored** | Awaiting the submitter; `visible_to()` and Discover depend on it |
| `rejected` · `published` · `approved` · `completed` · `pending_delete` | **stored** | Terminal / visible states, unchanged |
| `submitted` | derived | `in_review` with no assignment yet closed |
| `awaiting_document` | derived | an open `DocumentRequest` exists |
| `awaiting_resubmission` | derived | = `declined`; the same fact, named from the submitter's side |
| `final_review` | derived | the only open assignment is `rdco` |

**The reason for deriving rather than storing** is the defect being removed. The moment
"awaiting document" is a stored status, two things can disagree: the status column and the
open-request table. Today's bug class is exactly this — `_stage_reviewed_by` exists because
`pipeline_status` and `RecordClearance` each half-know where KTTO is. Deriving means the
question has one answer by construction.

`pipeline_status` is narrowed rather than deleted: `Record.objects.visible_to()` and
`PUBLICLY_VISIBLE_STATUSES` (IR-153) filter on it, and that predicate was only just secured.

**If the team wants these stored instead, say so** — it is one migration either way, and the
cost lands on consistency, not effort.

---

## 6. The tracker, mechanically

§10 requires nine questions answered from persisted backend records. One endpoint,
`GET /api/v1/records/<id>/tracker/`, serves all nine — none of it stored, all of it derived from
rows that exist for other reasons:

| # | Question | Source |
|---|---|---|
| 1 | Who currently has it? | `RecordAssignment` where `state=active` |
| 2 | Who has already reviewed? | `RecordAssignment` where `state=cleared` + its `Review` |
| 3 | Who is currently reviewing? | same as 1 |
| 4 | Requested but not complete? | `state=active` with no `Review` yet |
| 5 | Not requested? | `PARTIES` minus every party with any assignment row |
| 6 | Documents requested? | `DocumentRequest` + items |
| 7 | Which uploaded? | `DocumentRequestItem.upload` non-null |
| 8 | Where has it been routed? | `RoutingEvent`, grouped by `group_id` |
| 9 | Decisions/findings recorded? | `Review` rows + `RecordClearance` |

A party's tracker state is `not_requested → active → cleared`, plus `declined`/`rejected`, and
`awaiting_document` when that party has an open request. Because state 5 is *"has no assignment
row at all"*, the distinction the current UI cannot draw — never asked versus asked and not
started — falls out of the model rather than needing a flag.

The whole payload goes through `Record.objects.visible_to(user)`; a refusal is a 404 identical
to a missing record (IR-153). A routing history naming which offices hold a colleague's
unpublished disclosure is exactly as sensitive as the disclosure.

---

## 7. Frontend: what changes, screen by screen

| Surface | Today | Change |
|---|---|---|
| `EvaluationPage.tsx` (359 ln) | 3 radio actions (approve / decline / reject); stage label from `pipeline_status` | **Rebuilt.** Six actions: Clear · Reroute (multi-select + reason) · Request Document · Request Resubmission · Reject (RDCO only) · Final Decision (RDCO only). Header names the *party you are acting as*, not the record's stage |
| `ClearanceTrack.tsx` (105 ln) | Per-office clearance, 4 states | **Superseded** by the tracker: all parties, five states, plus routing history and document requests. Its `preserved` badge — the contribution made visible — is kept verbatim |
| `PeerClearanceStrip.tsx` | Peer office statuses, no comments | **Kept nearly as-is.** Reads the tracker instead of `clearances[]`; the no-peer-comments rule stays |
| `ReviewQueuePage.tsx` (200 ln) | Rows from role → `pipeline_status` | **Requeried** off `RecordAssignment` where `state=active` and party = mine. Simpler than today |
| `workspaceStages.ts` | `currentStage()` switch over 5 statuses; `currentOfficeLabel()` | **Rewritten** against assignments. `needsAuthorAction()` gains "has an open document request" |
| `StatusBadge.tsx`, `utils.ts`, `constants.ts` | Hardcoded status→label maps | **Trimmed** to the narrowed phase list. Labels already come from the API for clearances (IR-139); extend that to parties |
| `PaperViewPage.tsx:44–48` | `canReview()` switch on `pipeline_status` | **Replaced** by "do I hold an open assignment", answered by the server |
| Submission wizard | Office request checkboxes (ADR-018) | **Unchanged in shape**, re-labelled: it suggests, triage confirms |

**New:** a reroute modal (multi-select + mandatory reason), a document-request modal
(picklist + message), and an "Action required" panel on the submitter's record page.

---

## 8. Tests that must change

~2,700 lines of backend test describe the pipeline being replaced. None of it should be edited
to pass — CLAUDE.md forbids that, and these tests are correct about today.

| File | Lines | Disposition |
|---|---|---|
| `reviews/test_workflow_matrix.py` | 1109 | **Rewritten.** A type × status × actor matrix over five stages; the axes stop existing |
| `reviews/test_workflow_characterisation.py` | 720 | **Retired deliberately, not deleted quietly.** IR-197 wrote it as the pre-IR-136 behavioural baseline. It has done its job; retiring it is a decision to record in the PR, and the new suite should be written *before* it goes |
| `records/tests.py` | 519 | **Partial.** `:72`, `:423`, `:447` assert submission lands in `rdco_intake`. Most of the file is CRUD and is untouched |
| `reviews/test_resubmission_policy.py` | 303 | **Partial.** Both ADR-004 arms survive; the re-entry assertions change from a status to an assignment |
| `apps/tests/test_authorization_matrix.py` | 266 | **Partial.** `:241` iterates `("rdco_intake", "rdco_review")` |
| `reviews/test_clearance_payload.py` | 226 | **Mostly survives.** `preserved` is unchanged |
| `reviews/tests.py` | 150 | **Rewritten** — service-level pipeline assertions |
| `reviews/test_clearance_state.py` | 107 | **Survives.** Pure functions on clearance rows; only `declining_office`'s sequential-stage docstring is stale |
| `apps/tests/test_enum_vocabulary.py` | — | **Deliberately updated.** Its §8 docstring names this exact rename as the thing it exists to catch. It should fail, be read, and be changed with the migration — never before it |
| `frontend/.../EvaluationPage.test.tsx` | — | **Rewritten** with the page |

**New tests required:** the party graph's legal routes; multi-assignment concurrency; routing
authorization (holder-only); an office cannot reject; intake cannot reject; the tracker's nine
questions; document request does not reset clearance; clearance-aware resubmission end to end
(IR-224).

---

## 9. What does not change

Worth reading, because it is most of the system:

- **`RecordClearance` and `clearance_state.py`.** `is_preserved`, `clearance_payload`,
  `peer_summary` are pure and stay exactly as they are. The thesis contribution and its
  observability (IR-139) survive this change untouched — that is the main design constraint.
- **ADR-004's policy switch.** Both arms, unchanged, still differing in one statement.
- **`Record.objects.visible_to()` and IR-153's 404-not-403 refusal.** Narrowing
  `pipeline_status` keeps every value the predicate reads.
- **The whole documents app.** `UploadSlot`, `RecordUpload`, versioning,
  `authorize_record_documents()` (IR-153). ADR-022 adds no new file path and no new download
  route, deliberately.
- **Notifications.** Recipients and message bodies change; the plumbing does not.
- **Everything downstream of publication.** Discover, search (`Record.search_vector`), RAG,
  chunking, extraction, Ask IRIS — none of them reads `pipeline_status` beyond
  `PUBLICLY_VISIBLE_STATUSES`.
- **Accounts, roles, audit, opportunities, settings.** Untouched.

---

## 10. Sequencing, and one blocker

**[IR-233](https://citiris.atlassian.net/browse/IR-233) is open and is an `mvp-blocker`:**
resubmitting a declined record lands straight back in `declined`, so clearance-aware
resubmission — the thesis contribution — does not visibly run today. This change rewrites the
module that bug lives in. **Reproduce and understand it first**, even if the rewrite is what
fixes it; otherwise the bug travels across and nobody can say whether it was ever fixed.

Three stages, not interleaved:

1. **Model and services** — the two new models, the migration, `route()`, the party graph,
   tests. The API keeps serving today's shape from the new model, so nothing downstream breaks.
2. **Surfaces** — routing action, tracker and history endpoints, frontend rebuilt.
3. **Document requests** — ADR-022. Depends on assignments; on nothing else.

Estimate: 12–16 dev-days for stages 1–2, ~3 for stage 3. Against ADR-001's ~27-day semester
budget, already reversed four times. **What it displaces is a team decision and is not taken
here.**

---

## 11. Terminology recommendation (clarification §13)

**Recommendation: key `intake`; staff-facing label "Intake & Triage"; student-facing label
"Intake".**

The key must lose `rdco`. It is not a label problem — `rdco_intake` is the stored value in
`PipelineStatus`, `ReviewStage`, every `Review.stage` row, and eight frontend files. As long as
the word `rdco` is in the identifier, every reader re-derives the wrong mental model, and the
party split in §5.1 cannot be stated in code.

On the label, the options:

| Candidate | Against |
|---|---|
| **"Intake & Triage"** | Slightly clinical for a student-facing screen |
| "Institutional Intake" | *Institutional* is the word carrying RDCO's authority in "final institutional decision". Using it for triage blurs the exact distinction being drawn |
| "Intake" alone | Loses the *determines what is required* half — which is the half that makes routing out of intake forward movement rather than backward |
| "Pre-Review" / "Screening" | "Pre-Review" implies a review happened. "Screening" implies filtering out, which triage is not |

**"Intake & Triage" wins on the staff side** because it names both acts — receipt *and*
determination — and because "triage" is widely understood as routing without treating, which is
precisely the semantics. Its only weakness is register, and that weakness only applies to the
student.

**Two labels off one key costs nothing**, and the architecture already supports it: ADR-002's
amendment §4 establishes that labels are configuration and "the frontend still never maps a key
to English — it reads whichever label the API serialized." A student sees *"Your submission is
in Intake"*; RDCO staff see *"Intake & Triage"* with the triage actions attached. A second
institution overrides both.

**Also rename, for the same reason:** `ReviewStage.RDCO_INTAKE` → party `intake`, and
`PipelineStatus.RDCO_INTAKE` disappears into `in_review` (§5.2). `ReviewStage.RDCO` keeps its
name — RDCO final review *is* RDCO, and that was never the confusion.
