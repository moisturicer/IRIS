# Workflow audit export

**Purpose.** What each workflow audit event means and carries, and how ADR-011's workflow
metrics are computed from `GET /api/v1/audit/` rows alone.
**Owns.** The workflow event types and their metadata keys.
**Does not own.** The metrics' definitions ([ADR-011](../adr/011-evaluation-framework.md)),
the resubmission arms ([ADR-003](../adr/003-clearance-aware-resubmission.md),
[ADR-004](../adr/004-restart-all-comparison-mode.md)), and the CSV column mapping (IR-529
adds it here).
**Update when.** An event type or metadata key changes. The keys are fixed in
`backend/apps/audit/workflow.py`; change that file and this one in the same PR.

---

## What is logged, and what is not

IR-144 added one event type per workflow act. Each row is written by the workflow
service **inside the act's own transaction**, after the per-record lock, so:

- a refused or rolled-back act leaves no row;
- a row that fails to insert is rolled back to its own savepoint, logged at `ERROR`
  (`audit event <TYPE> for record <id> was not written`), and the act still succeeds.
  **A missing row is therefore possible, and the `ERROR` log is the only trace of it.**
  Check the backend log for those lines before trusting a pilot export.

**No backfill.** The log holds only observed events. Pilot data starts at the deployment
that carries IR-144; acts taken before it have no rows.

**No review prose.** Decision and finding comments are never copied (IR-479). The only
free text is a revision request's `reason`, a document request's `message` and a rejected
document's `reason`. The log is readable by RDCO only (IR-165).

**Kept apart (ADR-022).** A document request writes only `DOCUMENT_REQUEST*` events and a
revision only revision events, so "you forgot a form" is never counted as "revise the work".

## The row

`GET /api/v1/audit/` (RDCO only), filterable by `event_type`, `record`, `user`, `from` and
`to` (`YYYY-MM-DD`, inclusive), paginated (`page_size` up to 100), newest first.

| Field | Meaning |
|---|---|
| `id` | Insertion order. **Sort by `id`** to replay a record's history; `created_at` can tie |
| `event_type` | One of the types below |
| `user` | The acting user's id, or `null` when IRIS acted itself (the hand-back to RDCO) |
| `record` | The Record's id |
| `created_at` | When the row was inserted, inside the act's transaction (ISO 8601). Rows of one act are milliseconds apart |
| `metadata` | The keys listed per type |

Conventions in `metadata`: every party is a `Party` value (`adviser`, `itso`, `ierc`, `ktto`,
`rdco`); every id is a primary key; `version` is the record version's **number** (1, 2, …).

## Event types

### Assignment deadlines (IR-619, ADR-043)

| Type | Written when | `metadata` |
|---|---|---|
| `ASSIGNMENT_EXTENDED` | A coordinator extends an assignment, or a completed document-request pause moves its deadline | `assignment`, `party`, `extension`, `previous_due_at`, `due_at` (ISO-8601 timestamps), `reason`, `system` (true for a pause) |
| `ASSIGNMENT_ESCALATED` | The hourly job records the latest overdue escalation moment (IR-621) | `assignment`, `party`, `due_at` (ISO-8601), `step` (0 initially, incremented every five working days), `overdue_working_days`, `recipients` (visible coordinator user ids) |

Escalations have no actor. Their audit row is mandatory and commits with the
sent-moment ledger; an audit failure rolls back the moment so the next tick
can retry. Recipients are the visibility-checked intended recipients;
notification delivery remains best effort and failures are logged. An empty
recipient list records a moment with no eligible coordinator. Escalation
changes no workflow state, clearance or Seat.

The actor is null on a system Extension. Its reason is deliberately recorded
as the explanation for a changed deadline. Unlike IR-144's best-effort events,
this event is mandatory: an insert failure rolls back both the Extension and
the deadline movement. New-Version clock starts are not Extensions; the
assignment keeps its original date for that clock and earlier Extensions as
history. Existing assignments receive no backfilled date or event.

### Entering review and moving between parties

| Type | Written when | `metadata` |
|---|---|---|
| `SUBMITTED` | The owner submits; the record enters review at its Adviser | `to_party` (`adviser`), `version` |
| `ROUTED` | One row per target of a routing movement: accept & route, route, and the automatic hand-back to RDCO | `from_party`, `to_party`, `opened` (true when the target got a new assignment; false when it already held the record and only a nominee was seated), `nominee` (user id or `null`), `group` (rows of one movement share it), `hand_back` (true only for the hand-back, which has no actor) |
| `ASSIGNMENT_CLOSED` | A party's assignment closes | `party`, `assignment`, `how` (`completed`: the party finished, by the completion rule or as the decider; `closed_by_decision`: a Decision ended another party's turn; `withdrawn`: the owner withdrew the record), `decision` (the deciding Review's id, or `null`), `withdrawn_seats` (seat ids closed with it) |

### Verdicts and decisions

| Type | Written when | `metadata` |
|---|---|---|
| `DECISION_RECORDED` | Every verdict | `party`, `outcome`, `final`, `review` (the Review's id), `version` |
| `PUBLISHED` | **Beside** a `DECISION_RECORDED`, only when the decision made the record publicly visible | `party`, `version` |

`outcome` values: an office's `cleared` or `finding`; the Adviser's `accepted_and_routed`
(not a Decision: the record stays in review, `final` false); and the final outcomes `accept`
(a Proposal), `publish`, `keep_unlisted` and `reject` (`final` true). Keep-unlisted, reject
and a Proposal's accept write no `PUBLISHED`.

### Revisions and resubmission

| Type | Written when | `metadata` |
|---|---|---|
| `RESUBMISSION_REQUESTED` | A party asks the owners to revise the work | `party`, `request`, `reason`, `version` (the version it was made against) |
| `REVISION_REQUEST_WITHDRAWN` | The request is withdrawn unanswered | `party`, `request`, `closed_by` (`requesting_party`, or `record_withdrawn` when the owner withdrew the record) |
| `RESUBMITTED` | The owner submits a new version answering every open request | `version`, `policy` (`clearance_aware` or `restart_all`, the active ADR-004 arm), `requests` (the request ids it answered), `rereview_parties` (the parties that review the new version: those that asked, and under `restart_all` the offices it reopens, IR-632), `reset_parties` (the offices whose clearance the policy reset), `preserved_parties` (the offices whose `cleared` clearance it kept) |
| `CLEARANCE_PRESERVED` | One row per office in `preserved_parties`, right after its `RESUBMITTED` | `party`, `version`, `policy` |

### Reviewer seats (ADR-032 §4)

Every seat event carries `party`, `assignment`, `seat`, `reviewer` (user id) and `source`.

| Type | Written when | Extra `metadata` |
|---|---|---|
| `SEAT_CLAIMED` | An office member takes the record from the pool | |
| `SEAT_ASSIGNED` | A coordinator seats a member | |
| `SEAT_NOMINATED` | The router named the member when routing | |
| `REVIEWER_ADDED` | A seat holder adds a colleague from their own office | |
| `SEAT_REASSIGNED` | A coordinator moves a seat to another member; `seat` is the new one | `previous_seat`, `previous_reviewer`, `reason` (required since IR-623; absent on earlier rows) |
| `SEAT_WITHDRAWN` | A coordinator takes a seat away | |
| `SEAT_OPENED` | The holder opens their review for the **first** time; a second open writes nothing | |

The Adviser's entry seat writes no seat event: `SUBMITTED` is that act.

### Withdrawal

| Type | Written when | `metadata` |
|---|---|---|
| `RECORD_WITHDRAWN` | A record in review is soft-deleted, which today only its owner can do (IR-508); `user` is whoever deleted it | `version`, `closed_parties` (the parties whose open assignment closed) |

It is followed by an `ASSIGNMENT_CLOSED` (`how`: `withdrawn`) per party, and a
`REVISION_REQUEST_WITHDRAWN` or `DOCUMENT_REQUEST_WITHDRAWN` (`closed_by`:
`record_withdrawn`) per request it closed. Deleting a record that is not in review
writes none of these.

### Document requests (ADR-022)

Every document-request event carries `party` (the **requesting** party), `request` and
`items`, a list of `{"id", "label"}`.

| Type | Written when | `items` | Extra `metadata` |
|---|---|---|---|
| `DOCUMENT_REQUESTED` | A holder creates a request | all | `message` |
| `DOCUMENT_REQUEST_FULFILLED` | The last missing item receives an upload, through `request_item` or a slot upload | all | |
| `DOCUMENT_REQUEST_ACCEPTED` | The requesting party accepts an uploaded item | that item | |
| `DOCUMENT_REQUEST_REJECTED` | The requesting party rejects an item; it returns to missing | that item | `reason` |
| `DOCUMENT_REQUEST_WITHDRAWN` | The request closes unanswered | all | `closed_by` (`requesting_party`, `decision` or `record_withdrawn`), `closed_by_decision` (true when a Decision closed it) |

## Computing the metrics

Fetch every row for the record (`?record=<id>`, all pages) and sort by `id`.
`apps/audit/tests/test_workflow_events.py::MetricsFromTheExportTests` does exactly this
for one record's whole life, then checks each clock against the workflow tables.

### Per-party turnaround

A party's clock **starts** when it is handed work and **stops** when its assignment closes:

- start: `SUBMITTED` (for `to_party`), or `ROUTED` with `opened` true (for `to_party`), or
  `RESUBMITTED` (for each of `rereview_parties` with no clock running);
- stop: `ASSIGNMENT_CLOSED` (for `party`).

```python
started, turnaround = {}, []
for row in sorted(rows, key=lambda r: r["id"]):
    m, at = row["metadata"], parse(row["created_at"])
    if row["event_type"] == "SUBMITTED" or (row["event_type"] == "ROUTED" and m["opened"]):
        started[m["to_party"]] = at
    elif row["event_type"] == "RESUBMITTED":
        for party in m["rereview_parties"]:
            started.setdefault(party, at)
    elif row["event_type"] == "ASSIGNMENT_CLOSED":
        turnaround.append((m["party"], m["how"], at - started.pop(m["party"])))
```

A party routed to again after it finished gets a second clock. Exclude `how ==
"withdrawn"` and `"closed_by_decision"` when measuring how long a party took to finish:
those turns were ended, not completed.

**A revision does not stop the clock, so `RESUBMITTED` restarts none.** IR-144's card says a
clock also starts at `RESUBMITTED` for `reset_parties`. That rule was not built as written:

- a party that asked has an open revision request and cannot complete, so its clock is
  still running, and restarting it would erase the time before the request. `setdefault`
  leaves it alone;
- under `restart_all`, an office that had completed is reopened and reviews the new
  version (ADR-032 §5, IR-632 amendment). It is in `rereview_parties` with no clock
  running, so `RESUBMITTED` starts its second clock. Under `clearance_aware` no such
  office exists, so the rule starts nothing there;
- a reset office still reviewing is not in `rereview_parties` unless it asked; its first
  clock simply keeps running.

The author's share of a requesting party's clock is
`RESUBMITTED.created_at - RESUBMISSION_REQUESTED.created_at` for each party in
`rereview_parties`; subtract it to get the reviewer-side time.

### Total turnaround

From the record's `SUBMITTED` to its final `DECISION_RECORDED` (`final` true). On
the specialist path that decision is RDCO's; on the Adviser-only path and for a Proposal,
the Adviser's.

### Preserved-clearance count

The number of `CLEARANCE_PRESERVED` rows, per record or across the evaluation, split by
the `policy` they carry. Under `restart_all` it is zero by construction, which is what
ADR-004's comparison measures against. Each row names the office, so the count can also
be broken down by which office's clearance survived.

### Hands-on time (cross-check only)

Time-on-task is measured by ADR-011's session protocol, not here. `SEAT_OPENED` →
`DECISION_RECORDED` for the same person (`SEAT_OPENED.metadata.reviewer` equals
`DECISION_RECORDED.user`) and `party` gives a per-reviewer hands-on
interval to cross-check it against.
