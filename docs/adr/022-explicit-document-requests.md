# ADR-022: Explicit document requests, distinct from resubmission

## Status

**Proposed** — 2026-09-15. Tracked on [IR-254](https://citiris.atlassian.net/browse/IR-254).

Depends on [ADR-021](021-reviewer-directed-routing.md) for the notion of a party *holding* a
record; everything else here stands alone. **Closes a gap ADR-018 recorded against itself** and
takes a narrow slice of what [IR-118](https://citiris.atlassian.net/browse/IR-118) (FR-M2-01,
Office Checklists) describes, deliberately leaving the rest deferred.

## Context

### The gap, in ADR-018's own words

> This ADR states below that documents are "requested later, by the office that actually needs
> it," and that this "required no new document infrastructure." That is true only in the sense
> that an office can ask in a decline comment and the owner uploads through `DocumentsPage` —
> there is **no `request_document` mechanism in the system**, and the request is therefore
> invisible to the record. […] nothing distinguishes "you forgot a form" from a substantive
> revision — which matters to IR-144's audit events.

### Why "ask in a decline comment" is worse than it sounds

It is not merely informal. Declining is a workflow transition with three side effects, and all
three fire when an office asks for a missing form:

1. **The record leaves review.** `pipeline_status` becomes `declined`
   (`TRANSITIONS[(*, DECLINE)] → declined`). Every other office's in-flight work stops being
   in-flight.
2. **A clearance resets.** `_resolve_after_resubmission` sets the declining office's
   `RecordClearance` back to `pending` — correct for a substantive revision, wrong for a
   missing consent form the office has not finished reading around.
3. **The submitter is forced through the resubmit path**, which has a guard:
   `resubmit_record` refuses unless a `RecordUpload` exists with
   `created_at > last_decline.created_at`. So the student must upload *something* — which
   happens to be right here, by accident, and is wrong the moment the office wants a document
   the record has no slot for.

The net effect is that the cheapest possible interaction — *"send me the ethics clearance"* —
is modelled as the most expensive one the workflow has.

### What exists to build on

| Model | What it is | Fit |
|---|---|---|
| `UploadSlot` | Named document requirement, scoped to `RecordType` only | A usable **menu**; not a per-record request |
| `RecordUpload` | A file against a slot, versioned, with `UploadReview` | The fulfilment target, unchanged |
| `RecordFile` | Unstructured attachment, no slot | Not the answer — nothing tracks *why* it is there |
| `DocumentsPage` | Per-slot upload against an existing record | The submitter-side surface, already built |

`documents/migrations/0003_seed_upload_slots.py` seeds **13 required slots for
Thesis/Research** — NDA, Patent Search Report, Patent Draft, Utility Model, Industrial Design,
Trademark, Copyright and the rest. IR-118's complaint is that requiring all thirteen *at
submission* runs straight into NFR-U2's ten-minute target, and ADR-018 responded by cutting the
wizard's checklist to the manuscript alone.

**Those thirteen rows are a bad requirement list and a good picklist.** Nothing about them is
wrong as a vocabulary of documents an office might ask for; what was wrong was demanding them
all up front. This ADR reuses them at the moment they make sense.

## Decision

**A reviewer asking for a document creates a `DocumentRequest` against the record. The record
stays in review. No clearance resets, no status changes, and the submitter is not sent through
resubmission.**

Requesting a document and requesting a resubmission become two different actions with two
different meanings:

| | **Request document** | **Request resubmission** |
|---|---|---|
| Means | "Send me this file before I can continue" | "Revise the work and submit it again" |
| `pipeline_status` | unchanged (`in_review`) | → `declined` |
| Requesting party's clearance | unchanged | reset to `pending` |
| Other parties' clearances | unchanged | preserved (ADR-003) |
| Other parties' work | continues | interrupted |
| Submitter's action | upload against the request | edit, upload, resubmit |
| Returns to | the requesting party only | the declining party (ADR-021 §7) |

### 1. Data model

```
DocumentRequest
├── record        FK Record
├── assignment    FK RecordAssignment, null   (which holding this was asked under)
├── party         CharField  → Party           (denormalised; survives the assignment closing)
├── requested_by  FK User
├── message       TextField                    (why — shown to the submitter verbatim)
├── state         CharField  → open | fulfilled | withdrawn
├── created_at    DateTime
└── closed_at     DateTime, null

DocumentRequestItem
├── request       FK DocumentRequest
├── slot          FK UploadSlot, null          (picked from the menu)
├── label         CharField                    (free text when slot is null; else slot.name)
├── upload        FK RecordUpload, null        (set on fulfilment)
├── state         CharField  → missing | uploaded | accepted | rejected
└── sort_order    Integer
```

`party` is stored as well as reachable through `assignment` on purpose. An office may close its
assignment while a request is still open — it cleared on everything except the form — and the
request must still say who is waiting.

### 2. The request menu

The reviewer's picker is `UploadSlot` rows for the record's type, plus a free-text **Other**.
No new configuration, no new seed, and the existing thirteen become useful rather than
obstructive.

**This is explicitly not IR-118's Office Checklist**, and the difference should not blur:

- An **Office Checklist** (FR-M2-01, deferred) is a *pre-declared, per-office, conditional*
  list — "KTTO always needs an NDA; if `for_commercialization` then also a Market Analysis" —
  evaluated automatically when a record reaches that office.
- A **`DocumentRequest`** is *one reviewer, on one record, asking for specific things now.*

They compose rather than compete. When checklists are built, they become a **source of
pre-filled items** on a request the reviewer still reviews and sends — the checklist proposes,
the office asks. Nothing in this ADR has to be undone for that to happen; `slot` becomes
`requirement` and gains a second possible source.

### 3. Fulfilment

1. Reviewer creates the request. The submitter is notified; the record's tracker shows the
   requesting party as **awaiting document** (derived from `state="open"`, not stored).
2. The submitter uploads through the existing `DocumentsPage` flow against a request item. A
   slot-backed item creates a normal `RecordUpload`; an **Other** item creates one against a
   per-record ad-hoc slot so the file is still slot-shaped rather than a loose `RecordFile`.
3. Item → `uploaded`. When every item is `uploaded`, the request → `fulfilled` and the
   requesting party is notified.
4. The requesting party accepts or rejects each item. Rejecting returns that item to `missing`
   with a comment and reopens the request.

**A request never blocks another party.** ITSO can clear while IERC waits for a consent form.
That is the whole point of not using `declined`.

**A request does not gate the record's own transitions either.** RDCO can still make a final
decision with an open document request outstanding; the tracker shows it, and whether that is
acceptable is a judgement for the person, not a lock. Blocking would reintroduce the
`declined`-shaped freeze this ADR exists to remove.

### 4. Withdrawal, and the failure mode this creates

The requesting party may withdraw a request (→ `withdrawn`, closed, no fulfilment needed) —
the office read further and no longer needs it.

**The honest negative: a record can now sit indefinitely.** Under today's model a missing
document produced a `declined` record, which is at least visibly stuck and appears in the
submitter's action list. An open `DocumentRequest` on an `in_review` record is a quieter state.
Mitigations in MVP are notification and visibility only — the tracker shows it, the submitter's
workspace shows it as **Action required**, and the requesting office's queue shows it as
waiting. **No automatic escalation, no due dates, no reminders in MVP**; if the pilot shows
records stalling, that is a real finding and the cheapest fix is a reminder job, filed then.

### 5. API

```
POST   /api/v1/records/<id>/document-requests/     create (holder only)
GET    /api/v1/records/<id>/document-requests/     list (visible_to)
PATCH  /api/v1/document-requests/<id>/             withdraw
PATCH  /api/v1/document-request-items/<id>/        accept / reject (requesting party only)
```

Uploading is the existing documents endpoint with a `request_item` parameter; it does not
become a second upload path.

## Alternatives Considered

**Leave it as a decline comment (status quo).** Rejected on the three side effects in §Context:
it stops other offices' work, resets a clearance that was never at issue, and makes a missing
form indistinguishable from a substantive revision in the audit trail — which is the specific
thing ADR-018 filed against itself and IR-144/IR-216 need.

**Add a reason code to `decline`** — `decline(reason="missing_document")` — so the audit trail
can tell them apart, with no new model. Cheapest option that addresses the audit complaint.
Rejected because it addresses only the audit complaint: the record still leaves review, the
clearance still resets, the submitter is still sent through resubmission. It makes the wrong
behaviour better-labelled.

**Build IR-118's Office Checklists first and derive requests from them.** The requirement as
the SRS actually writes it. Rejected for now, not on merit: it is a multi-day, unscoped feature
(three models plus a rules engine plus a decision about what happens to existing `UploadSlot`
and `RecordUpload` rows), and it does not remove the need for ad-hoc requests — no pre-declared
list anticipates "your consent form is scanned at an unreadable resolution." Ad-hoc requests
are needed whether or not checklists exist; checklists are not needed for ad-hoc requests to
work. Build the one that is a prerequisite for neither.

**Let the reviewer attach a required-document flag to the existing `RecordFile`.** Rejected:
`RecordFile` has no slot, no state and no requester, so "required" would be a boolean on an
unstructured attachment, and fulfilment would have nothing to link to.

**Block the record while a request is open.** Rejected in §3. It is `declined` with a nicer
name, and it re-breaks parallel review.

## Decision Rationale

The action already exists — offices already ask for documents — and today it is expressed by
the only verb available, which has three side effects none of which the asker wants. Adding
the verb is not new capability so much as removing a mismatch between what people do and what
the system lets them say.

The deletion test is unusually clean here. Remove `DocumentRequest` and the behaviour does not
move somewhere else: it reverts to a decline, and the record demonstrably loses information —
who asked, for what, and whether it arrived. That information is not recoverable from any other
table, which is the same argument ADR-021 makes for `RoutingEvent`.

The reuse of `UploadSlot` as a picklist is worth stating as rationale rather than as a
detail: it turns IR-118's most-cited problem — thirteen mandatory slots nobody can satisfy at
submission — into the feature's vocabulary, at zero cost, without pre-empting the decision
IR-118 still needs about what those slots should be.

## Consequences

**Positive.** A missing form no longer costs a clearance. The audit trail distinguishes "you
forgot a form" from "revise the work", which is what IR-144/IR-216 need and what ADR-018 said
was missing. The submitter sees a specific, actionable list instead of a prose comment. The
thirteen seeded slots become useful. ADR-018's claim that documents are "requested later, by
the office that actually needs it" becomes literally true rather than aspirational.

**Negative.** Two new models and a second reason a record can be waiting, which the tracker now
has to render distinctly from "being reviewed". A reviewer can request a document *and* decline
on the same reading, producing an open request against a `declined` record — legal, and
`resubmit_record`'s existing upload guard happens to make it coherent, but it needs a test
rather than an assumption.

**Risk.** The stall described in §4. It is a real regression in *visibility* against the
decline-based status quo, traded for a real improvement in *cost*, and the trade should be
revisited with pilot data rather than defended in advance.

## MVP Impact

**~3 dev-days**, on top of ADR-021's 11–15. Two models and a migration (~0.5 d), service and
API (~1 d), reviewer modal and submitter action-required surface (~1 d), tests (~0.5 d).

Lower risk than ADR-021: the models are additive, no existing column is rewritten, and nothing
already working changes behaviour. It can ship after ADR-021 stage 2 without blocking anything.

## SaaS Impact

Neutral now, positive later. The request vocabulary is `UploadSlot` rows, which are already
per-record-type data, so a second institution's document names are already configuration. When
checklists arrive they attach to the same seam.

## Security Impact

`DocumentRequest` is record data: list and read go through `Record.objects.visible_to(user)`,
and a refusal is a 404 identical to a missing record (IR-153). Creating a request requires
holding the record (ADR-021's `holds_open_assignment`); accepting or rejecting an item requires
being the requesting party. Uploads go through the existing `authorize_record_documents()` —
this ADR adds no new file path and no new download route, which is deliberate: CLAUDE.md's rule
against exposing a file path that bypasses Django's permission layer is easiest to keep by not
adding one.

`message` is reviewer-authored free text rendered to the submitter. It is displayed as text,
never as markup.

## Deployment Impact

One additive migration. No backfill: records with no request simply have none.

## Research Impact

Indirect but real. ADR-003's contribution is that a resubmission preserves clearances it need
not reset. Every decline issued for a missing form is a resubmission the workflow did not
actually need — noise in exactly the measurement ADR-004 takes. Separating the two actions
makes the resubmissions that *do* occur substantive ones, which sharpens rather than
contaminates the comparison.

It also removes a confound from ADR-011's time-on-task protocol: a participant timed through a
"resubmission" that is really a file upload is not doing the task being measured.

## Related Requirements

FR-M2-01 (Record Types, Department Templates and Office Checklists — this takes a slice; the
rest stays with IR-118) · FR-M5-03 · NFR-U2 (the ten-minute submission target ADR-018 cut the
checklist for). Ids are stable labels only.

## Related Tasks

[IR-254](https://citiris.atlassian.net/browse/IR-254) (this ADR) ·
[IR-118](https://citiris.atlassian.net/browse/IR-118) (Office Checklists — related, still
deferred, and this ADR does not close it) · IR-144 and IR-216 (workflow audit events, which
need the distinction this ADR creates) · ADR-018 §Status (the gap this closes).
