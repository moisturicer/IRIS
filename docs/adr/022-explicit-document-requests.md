# ADR-022: Explicit document requests, distinct from resubmission

## Status

**Accepted** — 2026-09-15 · **amended 2026-09-24, §Amendment (fulfilment, who may read request data, refusals)**. Settled as a business decision by **Lee Jasmin Adolfo** (project lead);
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
GET    /api/v1/records/<id>/document-requests/     list (owners + relevant parties — §Amendment 5)
PATCH  /api/v1/document-requests/<id>/             withdraw (requesting party only)
PATCH  /api/v1/document-request-items/<id>/        accept / reject (requesting party only)
```

Uploading uses the existing documents endpoint with a `request_item` parameter. It is not a
second upload path.

> **Amended 2026-09-24.** The list line originally read `list (visible_to)`. Document-request
> data is internal workflow data, and being able to read a Record does not grant access to it.
> See §Amendment 5. The same rule governs the tracker's `document_requests[]`.

## Amendment — 2026-09-24: who fulfils a request, how, and what a refusal says

Settled by **Lee Jasmin Adolfo** after the post-merge review of IR-262 ([PR #117](https://github.com/moisturicer/IRIS/pull/117)). IR-262 implemented §1–§3 and §5 as written. This amendment:
- changes §3 in two ways (points 1 and 2);
- adds one route to §5 (point 3);
- writes down the refusal convention §Security Impact relied on without stating it, including one existing exception (point 4);
- **corrects who may read document-request data**, which §5 and §Security Impact had set too wide (point 5).

**1. The owner may fulfil a request through the ordinary upload.** It amends §3.2. When the Record owner uploads a requested **canonical** document to its slot through the normal Documents flow (`POST /documents/submit/` or `/documents/uploads/create/` with `slot`), every open request item asking for that slot on that Record is answered. The owner is not required to use the Action required panel. A free-text **Other** item has no canonical slot to infer, so it still needs `request_item`. As implemented in IR-262, only a `request_item` upload counts, which leaves a request stalled after the owner has in fact provided the document (§4). **Not yet built:** [IR-346](https://citiris.atlassian.net/browse/IR-346).

**2. The requesting party cannot fulfil its own request.** It amends §3. Fulfilment is by the Record owner or an authorised submitter. A reviewer or office that asked for a document may accept, reject or withdraw (§3.4, §4). It may **not** answer its own request by uploading the file just because staff have generic document-upload permission (`authorize_record_documents` admits every office). As implemented in IR-262, any staff upload against an item fulfils it. **Not yet built:** [IR-263](https://citiris.atlassian.net/browse/IR-263) (for `request_item` uploads) and IR-346 (for slot uploads).

**3. The picklist route.** It adds to §5. `GET /api/v1/records/<id>/document-requests/slots/` serves the record type's upload slots, excluding any ad-hoc slot. It is served per Record because Record detail names its type rather than giving its id, and because Advisers cannot use the documents app's per-record slot listing. Record detail also carries `can_request_document`, the parties the viewer may ask as. Both shipped in IR-262, and **both are retained as intentional additions to this ADR's API**. The picklist serves slot names only, not request data, so point 5 does not restrict it.

**4. 404 versus 403. The convention is kept, and so is one existing exception.**

The convention:
- **404**: the caller cannot see the Record or object. The response is identical to a missing id, so it confirms nothing (IR-153).
- **403**: the caller can see the Record but may not perform this action on it.

What the code does today, verified against `main` on 2026-09-24:

| Situation | Response | Where it comes from |
|---|---|---|
| Listing requests, creating one, or the picklist, for a Record outside `visible_to()` | **404** | `RecordViewSet.get_object()` |
| Creating a request on a visible Record the caller does not hold as a party | **403** | `create_request` raises `NotAHolder` |
| Uploading with a `request_item` that belongs to a different Record, or does not exist | **400**, "That requested document does not exist." | `resolve_item_for_upload`. The item is looked up *within* the named Record, so a foreign item reads exactly like a missing one and confirms nothing. It is a 400, not a 404, because the Record is found; it is the request body that names nothing valid. |
| Uploading through `/documents/submit/` or `/documents/uploads/create/` to a Record that exists but that the caller neither owns nor staffs | **403**, **even when the caller cannot see the Record** | `authorize_record_documents` (IR-153) |
| Uploading to another Record's ad-hoc slot | **404**, "Record or slot not found." | `_slot_for_record` |
| A requesting party uploading against its own request (point 2) | **403**, once built | IR-263 |

**The one exception to the convention is recorded here, not converted.** `authorize_record_documents` answers 403 to a caller who cannot see the Record. That is an **intentional existing exception**, chosen in IR-153 and documented in the function itself: the documents endpoints take the Record id from the caller's own request parameter, so "a 404 would hide nothing, and 403 says what actually happened". The exception covers the documents app's upload and listing routes only; every document-request route follows the convention. No ticket exists to change it, and this amendment does not create one. **Aligning the documents app with the 404 convention would be a separate decision and a separate ticket**, and would touch every endpoint that calls `authorize_record_documents`, not just this ADR's.

No authorization code changes with this amendment. IR-262's "users without access get 404" acceptance criterion is read against the document-request routes, not the documents app's upload route.

**5. Document-request data is internal workflow data.** It corrects §5 and §Security Impact. Being able to read a Record does **not** grant access to its document requests. Two cases matter: a published Record, which any authenticated user can read, and a Record an office sees only because `visible_to()` shows office staff everything.

The data covered:
- document-request history (requests and their items);
- request messages;
- reviewer and office comments attached to requests, including IR-263's reject reasons;
- request state and history as served by the tracker and detail APIs.

Who may read it:
- the Record's owners and authorised submitters;
- the workflow parties relevant to the current or historical request, under IRIS workflow permissions.

Uninvolved offices and public readers may not.

**As shipped in IR-262 this is not met.** The list endpoint and the tracker's `document_requests[]` both authorise through `visible_to()`. **To build:** [IR-349](https://citiris.atlassian.net/browse/IR-349). The refusal follows point 4's convention:
- 404 when the Record is not visible;
- 403 on the list endpoint when the Record is visible but the data is not;
- `null` in the tracker's `document_requests` for such a viewer.

**Who counts as relevant is decided by participation, not by role** (settled by Lee Jasmin Adolfo on 2026-09-24). A user may read a Record's document-request data only if at least one of these holds:
- they own or submitted the Record;
- they can staff a party that **currently holds** an assignment on the Record;
- they can staff a party that **previously held**, or **acted on** (recorded a review, finding or clearance under), an assignment on the Record;
- they **created or took part in** a document request on the Record: they are its `requested_by`, or they can staff its requesting party.

**A role alone grants nothing.** Being an Adviser, RDCO, ITSO, IERC or KTTO user is not participation. So:

| Who | Access to request data |
|---|---|
| A named Adviser never assigned to, or involved in, the Record | No |
| RDCO before it has held or acted on the Record | No |
| An office that actually held, reviewed or requested on the Record | Yes |
| Owners and authorised submitters | Yes |
| Public readers and uninvolved offices | No |

**Record-level status stays; request details do not** (settled 2026-09-24). The generic `workflow_state` value `awaiting_document`, and its label, remain visible to anyone otherwise allowed to view the Record. That is ADR-021 §4's derived state, and the UI relies on it. It is the *only* document-request fact such a viewer learns. Anyone without request access must not be shown:
- which office or party asked;
- the messages;
- the request or fulfilment history;
- accept, reject or withdraw details;
- any other request metadata.

This includes the tracker's per-party `awaiting_document` flag, because it names the requesting party. For such a viewer the flag is `null`, meaning "not disclosed". Owners and participating parties see everything.

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

- **Amended 2026-09-24 (§Amendment 5).** Document-request data is internal workflow data.
  Only the Record's owners and authorised submitters, and the workflow parties that actually
  participated in the Record's workflow or in the request, may read it: through the list endpoint
  and through the tracker's `document_requests[]` and per-party `awaiting_document` flag alike.
  §Amendment 5 defines participation. A role alone is never enough. The generic
  `workflow_state = awaiting_document` stays visible to anyone who may view the Record. Reading the Record, whether published or visible to an office through
  `visible_to()`, does not grant it. A caller who cannot see the Record gets a 404 (IR-153). A
  caller who can see the Record but not its requests gets a 403 from the list, and `null` in the
  tracker. This line originally said listing and reading go through `visible_to()`. IR-262
  shipped that, and IR-349 corrects it.
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

IR-254 · IR-262 · IR-263 · IR-346 · IR-349 · IR-118 (still deferred) · IR-144, IR-216 · ADR-018 §Status.
