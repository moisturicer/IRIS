# Workflow audit export

**Purpose.** What each workflow audit event means and carries, and how ADR-011's workflow
metrics are computed from `GET /api/v1/audit/` rows alone.
**Owns.** The workflow event types and their metadata keys.
**Does not own.** The metrics' definitions ([ADR-011](../adr/011-evaluation-framework.md)),
the resubmission arms ([ADR-003](../adr/003-clearance-aware-resubmission.md),
[ADR-004](../adr/004-restart-all-comparison-mode.md)). The CSV column mapping is below.
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
document's `reason`. The log is readable by the System Admin only (ADR-051 §3, IR-781). It was RDCO's from IR-165 until then.

**Kept apart (ADR-022).** A document request writes only `DOCUMENT_REQUEST*` events and a
revision only revision events, so "you forgot a form" is never counted as "revise the work".

## The row

`GET /api/v1/audit/` (the System Admin only), filterable by `event_type`, `record`, `user`, `from` and
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

### Research metadata corrections (IR-563, ADR-046)

`SYSTEM_SETTING_CHANGED` is an administrative event, excluded from workflow metrics. The actor is the System Admin that changed the setting (RDCO before IR-781). Metadata contains `key`, `old_value` and `new_value`. Writing the value a setting already holds records nothing.

`RETENTION_CLEANUP_RUN` (IR-794) is an administrative event, excluded from workflow metrics. The daily retention cleanup writes one each run, with no actor and no record, even when every period is blank. Metadata is `counts`, the number of rows erased per data type (`{"download_notes": 0}`), and never a name, an email or any erased text.

`RESEARCH_METADATA_CORRECTED` is an administrative metadata event, excluded from workflow metrics. The actor is the active superuser named by the correction command. Metadata contains `reason`, per-record `evidence`, and `before`/`after` objects with `origin`, nullable `publication_year`, and ordered `authors`. Corrections and audit rows share one transaction: failure rolls back the entire manifest. Dry runs produce no audit rows.

### Download requests (IR-688, ADR-048)

`DOWNLOAD_REQUEST_CANCELLED` is written when a reader withdraws their own pending request; the actor is the reader and metadata is `request` (the `DownloadRequest` id). `DOWNLOAD_GRANT_REVOKED` is written when RDCO ends a live grant; the actor is RDCO and metadata is `request` plus `requested_by` (the reader's user id). RDCO's note is kept on the request, not in the audit row. Both are administrative events, excluded from workflow metrics.

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

### Review threads (ADR-032 §7, 2026-11-04; IR-874)

No thread text is copied: never a body, an answer's note, a finished review's summary or a closing reason. `party` is the thread's party, or `null` for an owner's thread.

| Type | Written when | `metadata` |
|---|---|---|
| `REVIEW_FINISHED` | A Seat holder finishes a review, *Comment only* included, which writes no `DECISION_RECORDED`. Any other verdict's own events sit beside it | `party`, `verdict` (`comment_only`, `request_revision`, `send_to_rdco`, `cleared`, `finding`, `accept`, `publish`, `keep_unlisted`, `reject`), `round` (the `ReviewRound` id), `review` (the verdict's Review id, or `null` for *Comment only*), `threads` (the ids it sent), `must_fix` (how many of them), `version` |
| `REVIEW_THREAD_RESOLVED` | A participant resolves an open thread | `thread`, `party`, `severity` |
| `REVIEW_THREAD_REOPENED` | A participant reopens a resolved thread | `thread`, `party`, `severity` |
| `REVIEW_THREAD_SEVERITY_CHANGED` | A Seat holder of the thread's party changes a sent thread's severity. A draft's changes aren't logged: nobody else has seen it | `thread`, `party`, `severity` (the new one), `previous` |
| `REVIEW_THREAD_ANSWERED` | An owner marks a reviewer's thread Addressed or Declined, each time | `thread`, `party`, `severity`, `answer` (`addressed` or `declined`) |
| `REVIEW_THREADS_CLOSED` | A Decision closes the open threads, right after its `DECISION_RECORDED` | `decision` (the deciding Review's id), `threads`, `must_fix` |

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

### A paper's embargo (ADR-052 §8, IR-812)

| Type | Written when | `metadata` |
|---|---|---|
| `EMBARGO_ANSWERED` | An owner answers Publish's question on a draft, each time they change it. `seed_demo`, `load_corpus --clear-for-ai` and `mark_corpus_cleared` write it too, for test papers | `embargoed`, `until` (an ISO date, or `null`) |
| `EMBARGO_SET` | An owner or the Adviser puts a submitted paper under an embargo, including a paper released before | `until`, `previous_state` (`unknown`, `none` or `released`) |
| `EMBARGO_EXTENDED` | An owner or the Adviser moves an active embargo's date, earlier or later | `until`, `previous_until` |
| `EMBARGO_RELEASED` | The Adviser or RDCO ends an active embargo | `until`, the date it held |
| `IP_RELEASED` | KTTO releases an IP-marked paper for the AI. The mark stays (IR-813) | `ip_type`, or null when none is set |

There is no backfill: answers saved before this have no row. The Record holds only who gave the latest answer or set the current date, and when.

### A person's answer to the data notice (ADR-054, IR-789)

| Type | Written when | `metadata` |
|---|---|---|
| `NOTICE_ANSWERED` | A person answers the current data notice, at registration or after a new one is published. `user` is the person. Each answer writes a row, including a later answer to the same version. `seed_demo` writes one for each account it answers for, with a Yes | `notice_version`, `ai_consent` (the Yes or No on AI), `previous_notice_version` and `previous_ai_consent` (`null` on a first answer) |

It has no `record`. There is no backfill: accounts that existed before IR-789 start unanswered and write their first row at next sign-in.

### Withdrawal

| Type | Written when | `metadata` |
|---|---|---|
| `RECORD_WITHDRAWN` | A record in review is soft-deleted, by its owner (IR-508) or by RDCO (IR-797); `user` is whoever deleted it | `version`, `closed_parties` (the parties whose open assignment closed), and `reason` when RDCO withdrew it (absent on an owner's deletion) |

It is followed by an `ASSIGNMENT_CLOSED` (`how`: `withdrawn`) per party, and a
`REVISION_REQUEST_WITHDRAWN` or `DOCUMENT_REQUEST_WITHDRAWN` (`closed_by`:
`record_withdrawn`) per request it closed. Deleting a record that is not in review
writes none of these.

### RDCO's acts on a paper in review (ADR-051 decision 10, IR-797)

Each act is one event. Withdrawing writes `RECORD_WITHDRAWN` above, with RDCO's `reason`.

| Type | Written when | `metadata` |
|---|---|---|
| `ADVISER_REPLACED` | RDCO names another Adviser while the paper's Adviser review is open. The old Adviser's seat is withdrawn and the new one seated in the same act, so no `SEAT_*` event is written | `assignment`, `previous_adviser` (null if that account is gone), `adviser`, `previous_seat`, `seat` (the new one), `reason` (optional, may be empty) |
| `OWNER_ADDED` | RDCO adds an owner to a paper in review. The Contact person is unchanged | `owner` |

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

### CSV export (IR-529)

The Audit Log's **Export CSV** downloads `GET /api/v1/audit/export/`. It is the System Admin's alone,
read-only, and applies the same validated `event_type`, `record`, `user`, `from` and
`to` filters as the list. Dates are inclusive in Django's configured timezone.
Apply the screen's Filter button first: export uses the applied filters. It exports
**all matching rows**, ignoring pagination, in insertion (`id`) order. The list is
newest first, breaking timestamp ties by `id`. An empty export contains its header.

Columns are fixed, in this exact order; missing scalar values are empty cells:

| Column | Source |
|---|---|
| `created_at` | Row timestamp, ISO 8601 with offset |
| `event_type` | Row type |
| `actor_id` | Row `user_id`, retained even if the account was deleted |
| `actor_role` | Existing account's **current** role name; blank for missing/no account or no role. Historical roles were not captured and are not inferred |
| `record_id` | Row `record_id`, retained even if the Record was deleted |
| `party` | `metadata.party` |
| `from_party` | `metadata.from_party` |
| `to_party` | `metadata.to_party` |
| `outcome` | `metadata.outcome` |
| `version` | `metadata.version` (version number) |
| `policy` | `metadata.policy` |
| `preserved_parties` | `metadata.preserved_parties`, JSON array when present |
| `reset_parties` | `metadata.reset_parties`, JSON array when present |
| `request_id` | `metadata.request` (singular); resubmission's plural `requests` stays in `metadata_json` |
| `item_ids` | JSON array of each `metadata.items[].id`; `[]` if absent |
| `reason` | `metadata.reason` |
| `metadata_json` | Complete metadata as JSON, including `opened`, `final`, `how`, `rereview_parties`, item labels and other keys not given a dedicated column |

CSV quoting preserves commas, double quotes, Unicode and embedded newlines. Text
cells whose first non-whitespace character is `=`, `+`, `-` or `@` receive a leading
apostrophe to prevent spreadsheet formula execution. `metadata_json` retains the
original text without that display escape. Neither export nor display edits a row.

The fixed columns deliberately omit `id`: keep CSV row order to replay history
when timestamps tie. For metric recipes below, use `json.loads(row["metadata_json"])`
as metadata, `actor_id` as the user, and iterate CSV rows in their existing order.
`AuditCsvTests.test_exports_every_matching_row_and_workflow_metrics_without_pagination`
demonstrates total turnaround of 7,200 seconds and one preserved clearance from CSV
alone, including the final-decision flag in `metadata_json`. The existing workflow
tests exercise per-party clocks across resubmissions using the same metadata.

Exports are not completeness certificates: pre-deployment or failed inserts cannot
be reconstructed. Keep unmatched start/stop events as incomplete observations;
never impute a zero duration or invent an event. Check the backend error log before
trusting metrics, and widen the date filter if a clock begins outside the export.

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
