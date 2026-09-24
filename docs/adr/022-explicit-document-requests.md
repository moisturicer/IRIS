# ADR-022: Explicit document requests, distinct from resubmission

## Status

**Accepted** — 2026-09-15 · **amended 2026-09-24, §Amendment (fulfilment and refusals)**. Settled as a business decision by **Lee Jasmin Adolfo** (project lead);
takes effect when [PR #81](https://github.com/moisturicer/IRIS/pull/81) merges. Tracked on
[IR-254](https://citiris.atlassian.net/browse/IR-254); implemented by
[IR-262](https://citiris.atlassian.net/browse/IR-262) (backend) and
[IR-263](https://citiris.atlassian.net/browse/IR-263) (frontend).

Depends on [ADR-021](021-reviewer-directed-routing.md) for assignments, the party vocabulary
(including `intake`), `ResubmissionRequest` and the derived `workflow_state`. **It closes a gap
that ADR-018 recorded against itself.** It also takes a narrow slice of
[IR-118](https://citiris.atlassian.net/browse/IR-118) (FR-M2-01, Office Checklists); the rest of
that card stays deferred.

## Context

### The gap, in ADR-018's own words

> there is **no `request_document` mechanism in the system**, and the request is therefore
> invisible to the record. […] nothing distinguishes "you forgot a form" from a substantive
> revision — which matters to IR-144's audit events.

### Why asking in a decline comment is worse than it sounds

Today, the only way to ask for a missing document is to decline. A decline is a workflow
transition, and it has three side effects:

1. **The record leaves review.** `pipeline_status` becomes `declined`. Every other office's work
   stops.
2. **A clearance resets.** On resubmission, the declining office's `RecordClearance` goes back to
   `pending`. That is correct for a substantive revision. It is wrong when the office only needs
   a missing form.
3. **The submitter is forced through resubmission.** `resubmit_record` refuses unless something
   was uploaded after the decline. That guard works here by accident. It fails as soon as the
   office wants a document the record has no upload slot for.

So the cheapest request in the workflow — *"send me the ethics clearance"* — is modelled as the
most expensive transition it has.

### What already exists

| Model | What it is | Role in this design |
|---|---|---|
| `UploadSlot` | A named document requirement, scoped only to `RecordType` | The **picklist** a reviewer chooses from |
| `RecordUpload` | A versioned file stored against a slot | Where a fulfilled request lands; unchanged |
| `RecordFile` | An unstructured attachment with no slot | Not used: nothing records *why* such a file is there |
| `DocumentsPage` | Per-slot upload against an existing record | The submitter's upload screen, already built |

`documents/migrations/0003_seed_upload_slots.py` seeds **13 required slots for
Thesis/Research**. IR-118 correctly calls that unworkable *at submission*. **As a list a reviewer
picks from, the same 13 slots work well.** What was wrong was demanding all of them up front.

## Decision

**When a reviewer needs a document, they create a `DocumentRequest` on the record. The record
stays in review. No clearance resets, no assignment closes, the stored lifecycle does not
change, and the submitter does not go through resubmission.**

Resubmission is only for when the submission itself must change.

| | **Request document** | **Request resubmission** (ADR-021 §11) |
|---|---|---|
| Means | "Send me this file before I can continue" | "Revise the manuscript or metadata and resubmit" |
| Creates | `DocumentRequest` + items | `ResubmissionRequest` + a `Review` (resubmission requested) |
| `pipeline_status` | unchanged (`in_review`) | unchanged (`in_review`) |
| `workflow_state` | `awaiting_document` | `awaiting_resubmission` |
| Requesting party's clearance | unchanged | set to `declined`, reset to `pending` on resubmit |
| Other parties' clearances | unchanged | preserved (ADR-003) |
| Other parties' work | continues, including clearing | continues, but nobody may clear or decide until resubmitted |
| Assignments | unchanged | unchanged |
| Review, routing and clearance history | preserved | **preserved — nothing is deleted** |
| Submitter's action | upload against the request | edit and/or upload, then resubmit |
| Review continues with | the requesting party | the requesting parties, whose assignments stayed active |

The two actions no longer differ in how they store status: `pipeline_status` stays `in_review`
in both cases. They differ in which request object is created and what that object blocks. That
is what ADR-021 §4 requires: waiting states are derived from requests, not stored twice.

### 1. Data model

```
DocumentRequest
├── record        FK Record
├── assignment    FK RecordAssignment, null   (the assignment the request was made under)
├── party         CharField → Party           (stored directly; stays valid after the assignment closes)
├── requested_by  FK User
├── message       TextField                   (why — shown to the submitter as written)
├── state         open | fulfilled | withdrawn
├── created_at    DateTime
└── closed_at     DateTime, null

DocumentRequestItem
├── request       FK DocumentRequest
├── slot          FK UploadSlot, null         (chosen from the picklist)
├── label         CharField                   (free text when slot is null, otherwise slot.name)
├── upload        FK RecordUpload, null       (set when the item is fulfilled)
├── state         missing | uploaded | accepted | rejected
└── sort_order    Integer
```

`party` is stored directly as well as through `assignment`. An office may close its assignment
while a request is still open — for example, it has cleared everything except one form — and
the request still has to say who is waiting.

**Any party may request a document, including `intake`.** Spotting an incomplete submission is
triage's first job, and "you have not attached the endorsement sheet" is the most common thing
intake will say.

### 2. The picklist

A reviewer chooses from the `UploadSlot` rows for the record's type, plus a free-text **Other**.
This needs no new configuration and no new seed data.

**This is not IR-118's Office Checklist.**

- An **Office Checklist** is a *pre-declared, per-office, conditional* list, evaluated
  automatically when a record reaches that office. It remains deferred.
- A **`DocumentRequest`** is *one reviewer, on one record, asking for specific documents now.*

The two fit together. When checklists are built, they can pre-fill the items of a request that
the reviewer still reviews and sends: the checklist proposes, the office asks. Nothing in this
ADR would need to be undone for that.

### 3. Fulfilment

1. **The reviewer creates the request.** The submitter is notified. The requesting party's
   tracker row shows *awaiting document*, and the record's `workflow_state` becomes
   `awaiting_document` (ADR-021 §4). Both are derived from open requests and never stored.
2. **The submitter uploads against an item** through the existing documents upload endpoint,
   using a `request_item` parameter.
   - A slot-backed item creates an ordinary `RecordUpload`.
   - An **Other** item creates one against a per-record ad-hoc slot, so the file still belongs
     to a slot instead of being a loose `RecordFile`.
3. **Each item is marked `uploaded`.** When every item is uploaded, the request becomes
   `fulfilled` and the requesting party is notified.
4. **The requesting party accepts or rejects each item.** A rejected item goes back to `missing`
   with a comment, and the request reopens.

**An open request never blocks another party.** ITSO can clear while IERC waits for a consent
form. That is the reason for not using a decline.

**A decision closes open requests.** A decision (ADR-021 §12) moves any open `DocumentRequest`
to `withdrawn` and records the decision as the reason. The request stays in the history. RDCO
or, for a Proposal, the Adviser can see on the tracker that a request was still outstanding. It
is their judgement whether that matters; it is not a lock.

### 4. Withdrawal, and the stall this allows

The requesting party may withdraw a request — for example, after reading further it no longer
needs the document.

**A record can now wait indefinitely.** Under the old model, a missing document produced a
`declined` record, which was at least visibly stuck. An open request on an `in_review` record is
quieter. In the MVP the mitigations are visibility only:

- the tracker shows the open request;
- the submitter's workspace shows it as **Action required**;
- the requesting office's queue shows the record as waiting.

**The MVP has no escalation, due dates or reminders.** If the pilot shows records stalling, add a
reminder job then.

### 5. API

```
POST   /api/v1/records/<id>/document-requests/     create (holder only)
GET    /api/v1/records/<id>/document-requests/     list (visible_to)
PATCH  /api/v1/document-requests/<id>/             withdraw (requesting party only)
PATCH  /api/v1/document-request-items/<id>/        accept / reject (requesting party only)
```

Uploading uses the existing documents endpoint with a `request_item` parameter. It is not a
second upload path.

## Amendment — 2026-09-24: who fulfils a request, how, and what a refusal says

Settled by **Lee Jasmin Adolfo** after the post-merge review of IR-262 ([PR #117](https://github.com/moisturicer/IRIS/pull/117)). IR-262 implemented §1–§3 and §5 as written. This amendment changes §3 in two ways, adds one route to §5, and writes down the refusal convention §Security Impact relied on without stating it.

**1. The owner may fulfil a request through the ordinary upload.** It amends §3.2. When the Record owner uploads a requested **canonical** document to its slot through the normal Documents flow (`POST /documents/submit/` or `/documents/uploads/create/` with `slot`), every open request item asking for that slot on that Record is answered. The owner is not required to use the Action required panel. A free-text **Other** item has no canonical slot to infer, so it still needs `request_item`. As implemented in IR-262, only a `request_item` upload counts, which leaves a request stalled after the owner has in fact provided the document (§4). **Not yet built:** [IR-346](https://citiris.atlassian.net/browse/IR-346).

**2. The requesting party cannot fulfil its own request.** It amends §3. Fulfilment is by the Record owner or an authorised submitter. A reviewer or office that asked for a document may accept, reject or withdraw (§3.4, §4). It may **not** answer its own request by uploading the file just because staff have generic document-upload permission (`authorize_record_documents` admits every office). As implemented in IR-262, any staff upload against an item fulfils it. **Not yet built:** [IR-263](https://citiris.atlassian.net/browse/IR-263) (for `request_item` uploads) and IR-346 (for slot uploads).

**3. The picklist route.** It adds to §5. `GET /api/v1/records/<id>/document-requests/slots/` serves the record type's upload slots, excluding any ad-hoc slot. It is served per Record because Record detail names its type rather than giving its id, and because Advisers cannot use the documents app's per-record slot listing. Record detail also carries `can_request_document`, the parties the viewer may ask as. Both shipped in IR-262.

**4. 404 versus 403. The existing behaviour is kept and stated.**

| Response | Means | Where |
|---|---|---|
| **404** | The caller cannot see the Record or object at all. The response is identical to a missing id, so it confirms nothing (IR-153). | Listing requests, creating one, and the picklist, for a Record outside `visible_to()`. An upload naming a request item of another Record. |
| **403** | The caller can see the Record but may not perform this action on it. | Creating a request on a visible Record the caller does not hold (§Security Impact). Uploading through the documents endpoints without owner-or-staff access, per `authorize_record_documents`'s deliberate 403. The owner-only fulfilment refusal in point 2. |

No authorization code changes with this amendment. Where the documents endpoints answer 403 to a caller who could not see the Record, that is `authorize_record_documents`' existing rule (the caller named the Record id themselves, so a 404 hides nothing). IR-262's "users without access get 404" acceptance criterion is read against the document-request routes, not the documents app's upload route.

## Alternatives Considered

**Keep asking in a decline comment (the status quo).** Rejected because of the three side effects
above.

**Add a reason code to decline or resubmission.** It would fix the audit trail and nothing else:
the record would still pause every office, and the submitter would still be forced through
resubmission.

**Build IR-118's Office Checklists first.** Rejected for now, not on merit. It is a multi-day
feature that is not yet scoped, and it does not remove the need for one-off requests: no
pre-declared list anticipates *"your consent form is scanned at an unreadable resolution."*

**Mark a `RecordFile` as required.** Rejected. A `RecordFile` has no slot, no state and no
requester, so there is nothing for a fulfilment to link to.

**Block the record while a request is open.** Rejected. That is a decline under another name,
and it breaks parallel review.

## Decision Rationale

Offices already ask for documents. Today they have only one way to say it, and that way carries
three side effects none of them want. This ADR adds the missing way to say it.

It also passes the deletion test. Remove `DocumentRequest` and the behaviour falls back to a
decline, which loses who asked, for what, and whether it arrived. No other table holds that
information.

## Consequences

**Positive.**

- A missing form no longer costs a clearance.
- The audit trail can tell "you forgot a form" apart from "revise the work".
- The submitter sees a specific list of what to provide instead of prose in a comment.
- The 13 seeded slots become useful.

**Negative.**

- Two new models, and a second kind of waiting that the tracker has to show separately.
- A reviewer can open a document request and a resubmission request on the same record. That is
  allowed and coherent: the resubmission blocks clearing, and the upload can satisfy both. It
  still needs a test.

**Risk.** The stall described in §4. It trades some visibility for a large reduction in cost.
Revisit it with pilot data.

## MVP Impact

About 3 dev-days (IR-262, IR-263). The models are additive and no existing behaviour changes, so
this work depends only on `RecordAssignment` existing (IR-256).

## SaaS Impact

Neutral now, positive later. The picklist is made of `UploadSlot` rows, which are already data
per record type.

## Security Impact

- Listing and reading requests go through `Record.objects.visible_to(user)`, and access is
  refused with a 404 rather than a 403 (IR-153).
- Creating a request requires `holds_open_assignment`.
- Accepting or rejecting an item requires being the requesting party.
- Uploads go through the existing `authorize_record_documents()`. This ADR adds no new file path
  and no new download route.
- `message` is displayed as text, never rendered as markup.

## Deployment Impact

One additive migration. No backfill.

## Research Impact

A decline issued only to get a missing form counts as a resubmission the workflow never needed,
and adds noise to exactly what ADR-004 measures. Separating the two actions means every
remaining resubmission is a substantive one, which sharpens the comparison. It also removes a
confound from ADR-011's time-on-task protocol.

## Related Requirements

FR-M2-01 (partially) · FR-M5-03 · NFR-U2. These IDs are stable labels only.

## Related Tasks

IR-254 · IR-262 · IR-263 · IR-346 · IR-118 (still deferred) · IR-144, IR-216 · ADR-018 §Status.
