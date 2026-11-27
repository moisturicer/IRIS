# ADR-022: Explicit document requests, distinct from resubmission

## Status

> **Note, 2026-09-26:** [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) (Accepted)
> retires the `intake` party. Every rule below still holds for the remaining parties (Adviser,
> ITSO, IERC, KTTO, RDCO). Read "including `intake`" as historical.

> **Corrected 2026-11-04.** **Built** (IR-262, IR-263), not "not yet built" as the index said. A Decision withdraws open requests with `closed_by_decision` (`apps/reviews/decisions.py:467-473`). Two statements below are out of date:
>
> - **"No escalation, due dates or reminders"** is superseded by [ADR-043](043-review-turnaround-reminders-and-escalation.md), whose §4 pauses the requesting party's clock while its own request is open.
> - **"Other parties' work continues, but nobody may clear or decide"** no longer holds. Other offices may clear (`apps/reviews/revisions.py:24-27`), and RDCO may decide (ADR-047 §5). What a document request blocks is its own party's finishing act (ADR-032 §4, IR-269 amendment).
>
> Uploads answering a request now join the current Version ([ADR-058](058-each-version-keeps-its-text-and-its-files.md) §2).

> **Amended 2026-11-24 ([IR-1322](https://citiris.atlassian.net/browse/IR-1322); decided by Hermoine Zozobrado; accepted 2026-11-24 when PR #1006 merged, with Ashlee Sean's security review of point 4).** A reviewer's *Request revision* is shown as *Request changes* and may ask for documents in the same act. An owner's uploads to a submitted record are held, seen by its owners only, until *Submit new version* or *Submit added documents* sends them. See *Amendment 8*.

> **Amended 2026-11-27 ([IR-1338](https://citiris.atlassian.net/browse/IR-1338); decided by Hermoine Zozobrado; Proposed until its PR merges).** A sent document is **Supplied**: there is no Accept or Reject. A reviewer sees **New** on a supplied version until they open it in the reader. If it is the wrong file, they ask again with a new request. See *Amendment 10*.

> **Amended 2026-11-24 ([IR-1325](https://citiris.atlassian.net/browse/IR-1325); decided by Hermoine Zozobrado; accepted 2026-11-24 when PR #1010 merged, approved by Ashlee Sean as relayed by Hermoine Zozobrado).** Documents are asked for only in the Documents tab, where each request waits as the reviewer's draft until their *Finish review* sends it. *Request changes* always asks for a new version and no longer carries documents. The owner gets *Upload* only on what was asked for. See *Amendment 9*.

> **Amended 2026-11-18 ([IR-1226](https://citiris.atlassian.net/browse/IR-1226); accepted 2026-11-18 with PR #895's merge; security review approved verbally by Ashlee Sean, relayed by Hermoine Zozobrado).** Creating, deciding and withdrawing a request takes a seat on the requesting party, not membership of it. See *Amendment 7*.

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

1. **The reviewer creates the request.** The submitter is notified. The record's
   `workflow_state` becomes `awaiting_document` (ADR-021 §4). **For workflow participants
   only** (§Amendment 5), the requesting party's tracker row also shows *awaiting document*.
   Both are derived from open requests and never stored.

   > **Amended 2026-09-24.** This step originally said, without qualification, that the
   > requesting party's tracker row shows *awaiting document*. Per §Amendment 5:
   > - Only authorised workflow participants receive document-request workflow information:
   >   owners and submitters, and parties that hold, held or acted on the Record, or that took
   >   part in the request.
   > - A non-participant receives `null` for that per-party flag and for the tracker's
   >   `document_requests`, and no other request information.
   > - Published-record visibility alone never grants it.
   > - The generic `workflow_state` stays visible to anyone who may view the Record.
2. **The submitter uploads against an item** through the existing documents upload endpoint,
   using a `request_item` parameter.
   - A slot-backed item creates an ordinary `RecordUpload`.
   - An **Other** item creates one against a per-record ad-hoc slot, so the file still belongs
     to a slot instead of being a loose `RecordFile`.
3. **Each item is marked `uploaded`.** When every item is uploaded, the request becomes
   `fulfilled` and the requesting party is notified.
4. **The requesting party accepts or rejects each item.** A rejected item goes back to `missing`
   with a comment, and the request reopens.

   > **Settled 2026-09-24 by Lee Jasmin Adolfo; built in IR-263.**
   > - **Rejection returns the item to `missing` and reopens the request.** No `rejected`
   >   state is persisted and none is introduced for this: §1's `rejected` value stays in the
   >   enum, and nothing writes it. The comment is kept as the item's `rejection_reason`, with
   >   `decided_at`. The owner sees it in Action required and is notified. The rejected file is
   >   not deleted; the item just stops pointing at it.
   > - **Accepting** marks the item `accepted`. A request whose items were all uploaded is
   >   already `fulfilled`, so accepting every item leaves it closed.
   > - **"The requesting party" is the workflow party, not a person.** Any authorised staff
   >   member of the requesting party (anyone who can staff the request's `party`) may accept,
   >   reject or withdraw. Permission never depends on who `requested_by` is.

**An open request never blocks another party.** ITSO can clear while IERC waits for a consent
form. That is the reason for not using a decline.

**A decision closes open requests.** A decision (ADR-021 §12) moves any open `DocumentRequest`
to `withdrawn` and records the decision as the reason. The request stays in the history. RDCO
or, for a Proposal, the Adviser can see on the tracker that a request was still outstanding. It
is their judgement whether that matters; it is not a lock.

### 4. Withdrawal, and the stall this allows

The requesting party may withdraw a request — for example, after reading further it no longer
needs the document.

> **Settled 2026-09-24 by Lee Jasmin Adolfo.** Withdrawal records **no reason**. IR-263 adds no
> withdrawal-reason field, and none is added in advance for IR-270. When IR-270 builds §3's
> "a decision closes open requests", it defines whatever reason that needs.

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

> **As built in IR-263 (2026-09-24).** The bodies are `{"action": "withdraw"}` and
> `{"action": "accept"} | {"action": "reject", "reason": str}`, and both answer with the whole
> request. Only an **open** request can be withdrawn, and only an `uploaded` item decided.
> Refusals follow §Amendment 4 as settled on 2026-09-24:
> - **404** when the id does not exist or the caller cannot see the Record;
> - **403** when the caller can see the Record but may not read its request data (§Amendment 5),
>   the same refusal as the list endpoint;
> - **403** when the caller may read it but cannot staff the requesting party.
>
> The request payload gains a per-viewer `can_manage`, and each item gains `rejection_reason`
> and `decided_at`, all behind the same read rule.

> **Amended 2026-09-24.** The list line originally read `list (visible_to)`. Document-request
> data is internal workflow data, and being able to read a Record does not grant access to it.
> See §Amendment 5. The same rule governs the tracker's `document_requests[]`.

## Amendment — 2026-09-24: who fulfils a request, how, and what a refusal says

Settled by **Lee Jasmin Adolfo** after the post-merge review of IR-262 ([PR #117](https://github.com/moisturicer/IRIS/pull/117)). IR-262 implemented §1–§3 and §5 as written. This amendment:
- changes §3 in two ways (points 1 and 2);
- adds one route to §5 (point 3);
- writes down the refusal convention §Security Impact relied on without stating it, including one existing exception (point 4);
- **corrects who may read document-request data**, which §5 and §Security Impact had set too wide (point 5).

**1. The owner may fulfil a request through the ordinary upload.** It amends §3.2. When the Record owner uploads a requested **canonical** document to its slot through the normal Documents flow (`POST /documents/submit/` or `/documents/uploads/create/` with `slot`), every open request item asking for that slot on that Record is answered. The owner is not required to use the Action required panel. A free-text **Other** item has no canonical slot to infer, so it still needs `request_item`. As implemented in IR-262, only a `request_item` upload counts, which leaves a request stalled after the owner has in fact provided the document (§4). **Built in [IR-346](https://citiris.atlassian.net/browse/IR-346) (2026-10-03):**
- Both slot endpoints store the file through one helper, `views._store_slot_upload`. For a Record owner it then calls `requests.fulfil_by_slot_upload` **in the same transaction**, so a request is never fulfilled for a file that was not stored.
- An item matches when its `slot` is the upload's slot, it is `missing`, and its request is `open` and on the same Record. One upload answers every such item, across requests, and each request that has nothing left missing is fulfilled and notifies its party once, on commit — the same `fulfil_item` path as a `request_item` upload.
- An ad-hoc slot is never matched, so an **Other** item is answered only through `request_item`, as above.
- Items are locked, then their requests, in the order `resolve_item_for_upload` locks them, and the request is re-read under its lock; an item already answered or a request closed in between is skipped.
- A rejected item is `missing` again (§3.4), so a later slot upload answers it under the same rule.
- No status, clearance or assignment changes (§3).

The Documents page offered owners an upload only while a Record is `draft` or `declined`, and a request is made during review, so the owner could not in fact reach this path from the interface. **As built, the page also offers an upload on a slot that an open request is still waiting on, naming who asked, and on no other slot.** Deleting a version and resubmitting keep the old `draft`/`declined` rule. This interface choice was made while building IR-346, to make the ticket's own scenario reachable; it is recorded here for reviewer sign-off, not settled by the implementer.

**2. The requesting party cannot fulfil its own request.** It amends §3. Fulfilment is by the Record owner or an authorised submitter. A reviewer or office that asked for a document may accept, reject or withdraw (§3.4, §4). It may **not** answer its own request by uploading the file just because staff have generic document-upload permission (`authorize_record_documents` admits every office). As implemented in IR-262, any staff upload against an item fulfils it. **Built for `request_item` uploads in [IR-263](https://citiris.atlassian.net/browse/IR-263)** (`requests.may_fulfil`: a Record owner, otherwise 403 with the item left `missing` and nobody notified). **Slot uploads: built in IR-346** — a staff or reviewer upload into a requested slot is stored as before and answers nothing.

**3. The picklist route.** It adds to §5. `GET /api/v1/records/<id>/document-requests/slots/` serves the record type's upload slots, excluding any ad-hoc slot. It is served per Record because Record detail names its type rather than giving its id, and because Advisers cannot use the documents app's per-record slot listing (no longer true since Amendment 6, which lets the Adviser read it; the picklist route stays). Record detail also carries `can_request_document`, the parties the viewer may ask as. Both shipped in IR-262, and **both are retained as intentional additions to this ADR's API**. The picklist serves slot names only, not request data, so point 5 does not restrict it.

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
| Anyone but a Record owner uploading against a `request_item`, including the requesting party (point 2) | **403** | IR-263, `SubmitDocumentView` via `requests.may_fulfil` |
| Accepting, rejecting or withdrawing a request that does not exist, or on a Record the caller cannot see | **404** | IR-263, `requests.request_on_visible_record` |
| Accepting, rejecting or withdrawing on a visible Record whose request data the caller may not read (point 5) | **403**, the list endpoint's refusal. A 404 is never used to hide request authorization on a visible Record (settled 2026-09-24) | IR-263, `requests.may_read_requests` |
| Accepting, rejecting or withdrawing as a reader who cannot staff the requesting party | **403** | IR-263, `requests.is_requester` |

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

## Amendment 6 — 2026-11-17: the Adviser reads the documents of the papers they advise

Decided by Hermoine Zozobrado on 2026-11-17 for [IR-1200](https://citiris.atlassian.net/browse/IR-1200), part of the review-page cleanup (IR-1199). **Security review: approved verbally by Ashlee, relayed by Hermoine Zozobrado on 2026-11-17.** The project lead accepts it by merging this amendment.

**The problem.** The documents app's listing routes refused the record's Adviser with 403, because `authorize_record_documents` asked `owns_or_staffs_record`, and an Adviser is neither an owner nor office staff. Point 3 above already worked around it for the picklist ("Advisers cannot use the documents app's per-record slot listing"). The Adviser reviews the paper first, but on the review page saw "Could not load this record's files" and could not open an Ethics Clearance or a Consent Paper the owner had uploaded.

**The rule.** The record's Adviser (`record.adviser`) may **read and download** its documents, and may not write any of them:

| Route | Owner | Office staff | The record's Adviser | Anyone else |
|---|---|---|---|---|
| `GET documents/records/<id>/slots/`, `GET documents/uploads/?record=`, `GET documents/files/?record=`, `GET documents/files/download-all/?record=` | Yes | Yes | **Yes** (was 403) | 403 |
| `GET documents/uploads/<id>/download/`, `GET documents/files/<id>/download/` | Yes | Yes | **Yes** (was 403) | 404 or 403, as before |
| `POST documents/submit/`, `POST documents/uploads/create/`, `DELETE documents/uploads/<id>/`, `DELETE documents/files/<id>/` | as before | as before | **No** (403) | as before |

- **Who counts.** Whoever `record.adviser` names right now. RDCO's replacement (`rdco_acts.replace_adviser`) changes the field, so a replaced Adviser loses access at once. When nobody replaces them, access continues after the review ends, the same as an owner's.
- **One predicate.** `core.permissions.may_read_record_documents` is `owns_or_staffs_record` plus the Adviser. `authorize_record_documents(..., reading=True)` uses it on the four listing routes, and the two download views call it directly. The upload and delete routes keep `owns_or_staffs_record`, so this amendment admits no new writer.
- **Request data is unchanged.** Reading a file is not reading the requests around it. Who asked for a document, its messages and reject reasons stay under point 5 (`may_read_requests`), which already admits an Adviser who took part.
- **The 403 exception in point 4 still covers these routes.** An Adviser of some other paper is "anyone else".

The access matrix declares it (`apps/tests/access/table.py`, `READS_DOCUMENTS`), and `apps/documents/tests/test_record_document_authorization.py::AdviserReadsDocumentsTests` proves the Adviser, a replaced Adviser, an unrelated Adviser and a finished review at the HTTP routes.

## Amendment 7 — 2026-11-18: acting on a request takes a seat

Decided by Hermoine Zozobrado on 2026-11-18 for [IR-1226](https://citiris.atlassian.net/browse/IR-1226); accepted 2026-11-18 with PR #895's merge; security review approved verbally by Ashlee Sean, relayed by Hermoine Zozobrado. It is one part of [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) §10's *Amendment, 2026-11-18 (IR-1226)*, which holds the reasons: every act on a paper's review needs a seat on it that was not withdrawn.

- **Creating a request, accepting or rejecting an upload, and withdrawing a request** need a seat on the requesting party's assignment that is not withdrawn: assigned, in review or done. Until now, anyone who could staff the party could do them (§3, §5), seated or not.
- **The request still belongs to the party, not the person.** §3's *"permission never depends on who `requested_by` is"* stands: any seat holder of the requesting party may decide or withdraw it. A reviewer taken off the paper leaves their requests open for whoever holds the seat.
- **Reading request data is unchanged** (§Amendment 5, `may_read_requests`).

## Amendment 8 — 2026-11-24: *Request changes*, and the owner sends what they added

Decided by Hermoine Zozobrado on 2026-11-24 for [IR-1322](https://citiris.atlassian.net/browse/IR-1322); **accepted 2026-11-24**, when its pull request (#1006) merged. Point 4 changes who may read a file; Ashlee Sean reviewed it for security before it was built. Transcribed by an agent. It amends §3 and the 2026-09-24 Amendment's point 1 (fulfilment), [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) §7 (the verdict's name) and [ADR-058](058-each-version-keeps-its-text-and-its-files.md) §2 (when a file joins a Version).

**The problem.**
- **Two acts, two items.** A reviewer who wanted both a revision and a form made two acts, and the owner saw two items for one reviewer: *Revision requested by Adviser* and *Documents requested by Adviser*.
- **Each file went out at once.** Every upload reached the reviewer the moment it landed, so a reviewer who asked for five documents got five notifications and could see a half-finished set.
- **No taking back.** An upload could not be withdrawn once it answered a request (ADR-058, IR-872 point 3).
- **Upload only on requested slots.** While a paper was in review, the Documents tab offered *Upload* only on a requested slot. An owner could not add a file nobody had named, though the server accepts it.

**The decision: one request in the screens, two records underneath.** `ResubmissionRequest` and `DocumentRequest` stay as they are, and so does clearance-aware resubmission: a revision still resets only the asking party's clearance (ADR-021, ADR-032 §5).

1. **The verdict is called *Request changes*.** ADR-032 §7's *Request revision* verdict is shown as *Request changes*. Its value (`request_revision`), its capability and the service that checks it (`revisions`) are unchanged.
2. **One act may ask for both.** *Request changes* in *Finish review* has the §2 picklist beside it, and *The paper itself needs changes (a new version)*, ticked by default:
   - Ticked, it opens a `ResubmissionRequest`. Any documents chosen open a `DocumentRequest` from the same party in the **same transaction**: if either is refused, neither is made.
   - Unticked, with documents chosen, it opens the `DocumentRequest` alone, and no revision.
   - Unticked with nothing chosen is refused, because that is *Comment only*.
   - *Request documents* on the Documents tab (ADR-032 §7, IR-1254 amendment) stays, for asking for a document without finishing a review.
3. **The owner sees one item per party.** `submitter_status.waiting_on_you` merges a party's open revision and document request into one entry, labelled *Changes requested by {party}*. Its `kind` is `revision` while that party's revision is open, otherwise `document`, so the act offered stays the right one.
4. **An owner's upload is held until they send it.** `RecordUpload` gains `sent_at` (nullable).
   - **Sent at once:** an upload by anyone but one of the Record's owners, as now. Also an owner's upload while the Record is a draft, since a draft is its creator's alone (ADR-009 decision 6).
   - **Held:** an owner's upload on a submitted Record (`sent_at` null), until the owner sends it by either:
     - **Submit new version** (ADR-032 §5), which sends every held upload in the transaction that writes the Version, so the Version names them; or
     - **Submit added documents**, the new `POST /api/v1/records/<id>/documents/send/`, for a Record with no open revision.
   - **A held upload is the owners' alone.** Every route that lists, downloads or opens an upload shows it only to the Record's owners: Amendment 6's table, the reader and a Version comparison. To anyone else it does not exist, and they get a 404, as for an unreadable record. `RecordUpload.objects.visible_to(user, record)` is the one predicate.
   - **A held upload answers nothing.** It fulfils no item, notifies nobody, and does not stop the requesting party's clock (ADR-043 §4).
5. **Sending fulfils what it answers.** In the sending transaction:
   - Each open request's `missing` item whose slot now has a sent upload is answered by the newest one. Items are matched as `fulfil_by_slot_upload` matches them today, and an **Other** item through its own ad-hoc slot.
   - Each request with nothing left missing is `fulfilled`.
   - Each requesting party is notified **once** per send, not once per file.
   - Files nobody asked for are sent too, and join the current Version (ADR-058 §2).
6. ***Submit added documents* is refused**:
   - with 409 while a revision is open, because the owner sends with *Submit new version*;
   - with 400 when nothing is held;
   - with 403 for anyone who is not an owner (`may_fulfil`).

   It writes no Version and starts no review round.
7. **A held upload can be deleted by its owner**, whatever its version number. The *version 1 needs staff* rule in `delete_upload` and ADR-058's refusal apply only to a sent upload, since a held one is named by no Version and answers no request.
8. **Upload is offered on every slot while a request is open.** While any party has an open revision or document request, the Documents tab offers *Upload* on each of the Record type's slots, not only the requested ones. The server already accepts these, so only the screen changes.
9. **"Added during vN" is read from `sent_at`** (ADR-058, IR-872 amendment point 2), so a held file is added when it is sent, not when it was stored. The owner's new-version hint (IR-1318, `unsent`) reads the held uploads instead of upload times.
10. **Nothing in flight is re-sent.** The migration sets `sent_at = created_at` on every existing upload. An item already `uploaded` stays answered.

**What the owner sees.**
- One bar at the top of the Documents tab. Its button reads *Submit new version* while a revision is open, and *Submit added documents* otherwise.
- The button is grey (disabled, with the reason as its description) until something is held, and solid maroon once something is.
- Each held file says *Added, not sent yet* and has a trash can.

**Rejected alternatives.**
- **Fully merging the two records, so every request is answered by a new Version.** A party that needs only a signed form would force a new Version and a new review round. The change would also reach clearance-aware resubmission, the thesis contribution.
- **Keeping each upload sent at once and adding only a trash can.** A file the reviewer has already seen, accepted or rejected can't honestly be taken back (ADR-058 §2). The reviewer would still get a notification per file.
- **Holding uploads but letting reviewers see them.** The reviewer would read and judge a set the owner has not finished, which is what holding is meant to stop.
- **Removing *Request documents* from the Documents tab.** A reviewer would have to finish their review to ask for one form.

**Consequences.**
- **Code:** one additive migration (`RecordUpload.sent_at`, with its backfill) and one new route.
- **Access matrix** (`apps/tests/access/table.py`): gains the send route, and a held upload's 404 for every role but the owners.
- **An unsent upload is sent to nobody.** An owner who uploads and never presses Submit has sent nothing. *Waiting on you* keeps the request open, and the button stays maroon while something is held.
- **Research Impact is unchanged:** a documents-only request still makes no resubmission.

## Amendment 9 — 2026-11-24: document requests are drafts until *Finish review* sends them

**Status: Accepted** — 2026-11-24, when IR-1325's PR (#1010) merged after Ashlee Sean's review, as relayed by Hermoine Zozobrado. Decided by Hermoine Zozobrado on 2026-11-24, in chat, while reviewing IR-1322's result. Transcribed by an agent. It replaces Amendment 8's points 2 and 8, and amends [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) §7 (what *Finish review* sends).

**The problem.**
- **Two places to ask.** After Amendment 8, a reviewer could ask for documents in *Finish review → Request changes* and also with *Request documents* in the Documents tab. Nothing said which to use.
- **A request went out mid-review.** *Request documents* sent the request at once, so the owner was asked for a form while the reviewer was still reading and before their review came.
- **Upload on every slot.** Amendment 8 point 8 offered *Upload* on every slot while anything was asked, which the owner did not want: a slot nobody asked for should take no file.

**The decision.**
1. **Documents are asked for in one place: the Documents tab.** *Request changes* in *Finish review* no longer has the picklist or *The paper itself needs changes* tick. It always asks for a new version (`revisions.request_revision`), as it did before Amendment 8. `POST /records/<id>/finish-review/` no longer reads `documents` or `new_version`.
2. **A request is a draft until its reviewer finishes.** `DocumentRequestState` gains `draft`. `POST /records/<id>/document-requests/` makes a draft:
   - Only its asker sees it. The list endpoint and the tracker leave out everyone else's drafts, and the request routes answer someone else's draft with 404 (`request_on_visible_record`).
   - It writes no audit event and sends no notification, since nobody has been asked yet.
   - Every reader that counts open requests reads `open` and is unchanged: the owner's *Waiting on you*, the tracker's `awaiting_document`, deadlines, readiness, withdrawal and a Decision. A draft makes no one a participant (`may_read_requests`).
   - Its asker can undo it with the same `PATCH /document-requests/<id>/ {"action": "withdraw"}`. A draft is deleted, not withdrawn, because it was never sent (204).
3. ***Finish review* sends the drafts.** Under the record lock, in the round's transaction, *Request changes* and *Comment only* open the caller's drafts for the Seat's party (`requests.send_drafts`). Each is dated now, takes the party's current assignment, writes `document_requested`, and notifies the owners once the transaction commits.
   - Request changes plus drafts is a revision and document requests from one party. The owner still sees one *Changes requested by {party}* entry (Amendment 8 point 3).
   - Comment only plus drafts is documents only, with no revision.
4. **Every other verdict is refused while drafts wait (400).** *Send to RDCO*, *Clear*, *Record finding*, *Accept*, *Accept & publish*, *Keep unlisted* and *Reject* all say: *"You have N document requests waiting. Remove them in the Documents tab, or choose Request changes or Comment only."* The pop-up shows those verdicts as unavailable with the same words. This follows the *Must fix* rule (ADR-032 §7): a verdict that says the paper needs nothing more can't go out with an ask that says it does.
5. **Upload only on what was asked for** (replaces Amendment 8 point 8).
   - While the paper is a draft, the owner may upload to every slot.
   - Once submitted, *Upload* is offered only on a slot or **Other** item an open request names, and only while it still needs a file.
   - A revision asks for the manuscript, which its own row takes.
   - Every other slot shows its files with no *Upload*. This is a screen rule: the server's upload routes are unchanged (Amendment 8 point 4 still holds what an owner uploads until they send it).

**Who can still send at once.** Nobody needs to. Since IR-1226, asking for documents needs an open Seat (`requestable_parties`), the same thing *Finish review* needs, so every reviewer who can draft a request can also send it. A reviewer whose Seat is assigned but not yet opened can draft one; they send it by opening the review and finishing it, as *Finish review* already requires.

**Rejected alternatives.**
- **Keep the picklist in *Request changes*, and remove it from the Documents tab** (Amendment 8's shape, kept). The reviewer asks for documents where they look at them, which is the Documents tab. Asking for documents would also always finish the review.
- **Send drafts with any verdict.** *Accept* with an open request for a missing form contradicts itself.
- **Discard drafts quietly on any other verdict.** A reviewer could lose a request without noticing.
- **Keep *The paper itself needs changes* tick for documents only.** *Comment only* already sends the drafts without a revision, so the tick would be a second way to say the same thing.

**Consequences.**
- **Code:** one migration (`0030_document_request_draft`). It adds the choice and alters no stored row, because every existing request is already `open`, `fulfilled` or `withdrawn`.
- **Removed:** the screen's *Request changes* fields (`RequestChangesFields.tsx`).
- **A draft that is never sent asks nobody anything.** If the reviewer's seat closes another way (a Decision, a withdrawal, being taken off the paper), it stays a draft that only they could see, as draft comments do.
- **Research Impact is unchanged:** a documents-only request still makes no resubmission, and a revision still resets only its party's clearance.

## Amendment 10 — 2026-11-27: a sent document is supplied, with no Accept or Reject

**Status: Proposed** — becomes Accepted when IR-1338's PR merges after a person's review. Decided by Hermoine Zozobrado on 2026-11-27, in chat. Transcribed by an agent. It replaces §3.4 (accept and reject) and the parts of §4 and Amendment 7 that let the requesting party decide an item.

**The problem.**
- **A second step nobody needed.** Since IR-262 a request is already fulfilled once every item has a file; Accept closed nothing more. A reviewer still had to press Accept or Reject on each one.
- **Reject did what a new request does.** A rejection sent the item back to `missing` with a reason, so the owner uploaded again. Asking again does the same with words the reviewer chooses.
- **Nothing said what had just arrived.** A reviewer returning to the Documents tab could not tell which files were new to them.

**The decision.**
1. **A sent document is supplied.** An item answered by a sent upload is `uploaded` and stays so. `PATCH /document-request-items/<id>/` is removed (404), with `accept_item`, `reject_item`, `notify_document_rejected` and the `document_accepted`/`document_rejected` audit writers. The screens read **Supplied** for `uploaded`, and for `accepted` stored before this.
2. **A wrong file is asked for again.** The reviewer makes a new request in the Documents tab (Amendment 9). Nothing else is added for it.
3. **New, per reviewer, until they open it.** `UploadSeen` (`documents/0031`) marks one person having opened one upload. `RecordUpload.is_new` is true for a viewer who is not an owner, on a sent upload that answered a request item, until they have a mark. `POST /documents/uploads/<id>/seen/` stores the caller's mark (204, idempotent), behind the same access as the download: 404 for a paper they can't see, 403 without document access.
   - Opening the version in the reader marks it. A download does not.
   - Each reviewer's mark is their own; it decides nothing and nobody else reads it.
   - It is personal data: exported as `uploads_seen` and deleted with the account.

**History is kept.** `DocumentRejection` rows, `rejected` items, a `missing` item's `rejection_reason` and the `DOCUMENT_REQUEST_ACCEPTED`/`_REJECTED` audit types stay, and still read as before (*Replacement needed* with the reason).

**Rejected alternatives.**
- **Keep Reject, drop Accept.** Reject would still be a second way to ask again.
- **New until the reviewer finishes their review, or for a fixed time.** It would say "new" about a file they had already read, or stop saying it about one they hadn't.
- **A download counts as opening.** A saved copy is not proof it was read, and the reader is where a reviewer works.

**Consequences.**
- **Code:** one migration (`0031_upload_seen`), a new table; no stored row changes.
- **Research Impact is unchanged:** a document request still makes no resubmission and resets no clearance.

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

IR-254 · IR-262 · IR-263 · IR-1322 · IR-346 · IR-349 · IR-118 (still deferred) · IR-144, IR-216 · ADR-018 §Status.
