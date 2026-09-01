# 10 — Audit & History

**Verdict: KEEP both surfaces. The UI is not the problem — the event vocabulary is.**

Two distinct surfaces, often conflated:

| Surface | Audience | Question |
|---|---|---|
| **Record history** — a block on record detail | Anyone who can see the record | *"What happened to my submission?"* |
| **Audit log** — `/audit` | RDCO only | *"Who did what, across the system?"* |

---

## 1 · The finding

`backend/apps/audit/models.py` defines **fourteen** event types:

```
LOGIN · LOGOUT · FAILED_LOGIN · ACCESS · UPLOAD · DOWNLOAD · DELETE
RENAME · PIN_GENERATED · PIN_VERIFIED · ROLE_CHANGE · ACCOUNT_LOCKED
ACCOUNT_UNLOCKED · SESSION_REVOKE
```

Every one is authentication, file handling, or account administration.

**There is no workflow event.** No `SUBMITTED`. No `DECISION_RECORDED`. No `RESUBMITTED`. No `CLEARANCE_PRESERVED`. No `STAGE_CHANGED`.

Three consequences, in ascending order of seriousness:

1. The audit log cannot answer any question about the workflow. It is a file-access log.
2. The record history block therefore falls back to `reviews[]` — decisions only. **A resubmission leaves no trace.** A student who revised and resubmitted on 20 September sees the 18 September decline and then the next decision, with nothing in between.
3. **The research metrics have no source.** [`docs/mvp-validation/03-final-evaluation-plan.md`](../mvp-validation/03-final-evaluation-plan.md) draws turnaround time and preserved-clearance counts from the audit export. Those events do not exist. `W-04` is not an instrumentation nicety — without it there is no data, and the pilot in Weeks 11–12 does not run twice.

A second, smaller defect: `types/audit.ts` declares seven of the fourteen types. The other seven cannot be filtered in the UI, and rows carrying them fall through `EVENT_COLORS` to the `default` badge. A `FAILED_LOGIN` and an `ACCOUNT_LOCKED` render identically to an unclassified event.

---

## 2 · Record history

The block on record detail ([06](06-record-detail.md) §2, block 6). It must show the workflow, not a subset of it.

```
HISTORY

  ● Published                                   26 Sep
    RDCO · "Cleared for publication."

  ● IERC cleared                                24 Sep
    A. Reyes, IERC · "Consent form now complete."

  ● Resubmitted                                 20 Sep
    You · Revised manuscript uploaded
    ITSO and KTTO clearance preserved

  ● IERC requested revisions                    18 Sep
    A. Reyes, IERC · "Consent form is missing section 4."

  ● KTTO cleared                                16 Sep
    M. Lim, KTTO · "No IP conflict identified."

  ● ITSO cleared                                14 Sep
  ● Submitted                                   12 Sep
```

| Rule | Reason |
|---|---|
| **Newest first** | Users open history to see what just happened |
| **Resubmission is an entry**, with the preserved offices named | The contribution occurred at 20 Sep and must be legible there. Today the row does not exist |
| Office and person on every decision | Accountability, and it answers *"who do I contact?"* |
| Comments shown in full, not truncated | This is the record of record. A clipped decline reason forces a second click for the one thing that matters |
| Institution-supplied labels | *"IERC cleared"* is configuration, not a string literal ([11](11-saas-admin.md)) |
| **No raw enum, ever** | Not `parallel_review`, not `declined` |

### Specification — Record History

**User.** Record owner, adviser, all office roles, RDCO.

**Goal.** Understand what has happened to this record and who did it.

**Primary action.** Read. (There is no action; this is deliberate — history is not a control surface.)

**Secondary actions.** Expand a long comment · open the document version attached to an entry *(post-MVP)*.

**Required data.** `reviews[]` **plus** workflow `AuditEvent`s for the record — `SUBMITTED`, `RESUBMITTED`, `STAGE_CHANGED`, `PUBLISHED` — merged into one chronological list. Per entry: type, actor, office, timestamp, comment, and for resubmissions the preserved-office array.

**Permissions.** Visible to anyone who may view the record. **Do not show `ACCESS` or `DOWNLOAD` events here** — who read a record is an RDCO-level concern and surfacing it to peers turns history into surveillance.

**States.** Populated · single entry (just submitted) · loading · fetch failed.

**Errors.** History fetch fails → *"History could not be loaded"* with retry, **inside the block**. The rest of the record renders. History is never a reason to fail a page.

**Empty states.** A draft → *"This record hasn't been submitted yet."* Never an empty container; never *"No history"* on a record that plainly has some.

**Loading states.** Three skeleton entries. History resolves independently of the record body ([06](06-record-detail.md)).

**Accessibility.** An `<ol>` in reverse-chronological order, marked `reversed`. Each entry: `<time datetime>` with the full timestamp in `title`. The timeline dot is `aria-hidden` — the entry type is text. The preserved-clearance line is part of the entry's text content, not a tooltip. Expanding a long comment uses `<button aria-expanded>`.

**Responsive.** Single column. At < 768 px the timeline rail is dropped and entries become stacked cards, since a 12 px rail plus indentation costs a third of a 360 px viewport ([13](13-responsive.md)).

**MVP/Post-MVP.** **MVP** — merged decision and workflow timeline including resubmissions. **Post-MVP** — document versions per entry, diff between submissions, export.

**Backend/API dependencies.** **`W-04`** — workflow event types, written inside the transition transaction (`W-03`) so an event cannot exist without its transition, or the reverse. `W-07` for the preserved-office array. `reviews[]` **exists**.

---

## 3 · Audit log

`AuditLogPage` — 147 lines, one of only two `DataTable` importers, with pagination, search and an event-type filter. **Structurally this is the healthiest screen in the codebase.** It needs three corrections, not a rebuild.

| # | Correction | Why |
|---|---|---|
| 1 | **Add the seven missing event types** to `types/audit.ts` and `EVENT_COLORS` | Seven of fourteen are unfilterable and render as `default` |
| 2 | **Render `metadata` as readable text**, not `JSON.stringify` | The Details column currently shows raw JSONB in a truncated monospace span. A human cannot read `{"old_name":"a.pdf","new_name":"b.pdf"}` at 180 px |
| 3 | **CSV export** — the file's own `TODO` | Not a convenience. It is the extraction path for the evaluation metrics |

Plus the second `TODO` already noted in the file: link the Record column to the record.

Once `W-04` lands, add a **date range** and a **record** filter. Turnaround analysis is *"events for record X between two dates"*; without those two filters the export is a full-table dump the team filters by hand.

### Specification — Audit Log

**User.** RDCO only.

**Goal.** Answer a question about system activity, or extract evidence.

**Primary action.** Filter and read.

**Secondary actions.** Export CSV · open the referenced record · page through results.

**Required data.** `auditApi.list({ event_type, record, user, search, page })` → `{ count, results[] }`. Per row: timestamp, type, actor, record, metadata.

**Permissions.** **RDCO only.** `AUDIT_LOG_ROLES` in `lib/constants.ts` is already `[RDCO]` and correct. The backend uses `IsAdminUser`, which under the `accounts/0005` seeding of `is_staff = True` for ITSO, IERC, KTTO and RDCO **admits all four offices**. `S-05` and `S-07` narrow it.

> The frontend constant is right and the backend is wrong. Do not "fix" the frontend to match. An ITSO reviewer can read the whole system's audit trail today, including who downloaded which document — this is a live confidentiality defect ([12](12-accessibility.md) is not the concern here; `S-05` is).

**States.** Populated · filtered · filtered-to-empty · loading · page beyond range · export in progress.

**Errors.** Fetch fails → inline error above the table with retry; filters retained so the query is not retyped. Export fails → toast naming the failure; **never a partially written file**. A 403 → *"Audit access is limited to RDCO"*, not a blank table.

**Empty states.** No events at all → *"No activity has been recorded yet"* (realistic only on a fresh instance). Filtered to empty → *"No events match these filters"* plus a clear-filters action. Distinct messages, as everywhere.

**Loading states.** `DataTable`'s loading prop, with skeleton rows at final height. **Filters stay enabled during load** — a user refining a slow query should not be locked out of it.

**Accessibility.**
- A real `<table>` with `<caption>`, `<th scope="col">`, and a described sort state
- Filters are labelled controls; the bare `<select>` needs a visible or visually-hidden label
- The `Filter` button is not the only path — Enter in the search field already works; keep it
- Result count in `aria-live="polite"`
- Badge colour is not the only signal: the event type is text inside the badge, which is already the case — preserve it when adding the seven types
- Pagination announces the current page and total
- The table scrolls inside its own container at narrow widths; **the page never scrolls horizontally** ([13](13-responsive.md))

**Responsive.** ≥ 1024 px full table. 768–1023 px drop the Details column into a per-row expander. < 768 px cards: type badge, timestamp, actor, record, then details on expand. Filters stack full-width. A five-column table cannot be made to work at 360 px and should not be attempted.

**MVP/Post-MVP.** **MVP** — existing table, all fourteen event types, readable metadata, CSV export, record links, date-range and record filters once `W-04` lands. **Post-MVP** — retention policy UI, saved queries, per-record audit view for non-RDCO staff, tamper-evidence display.

**Backend/API dependencies.**

| Dependency | Task | Status |
|---|---|---|
| **Workflow event types** | **`W-04`** | **Not built — blocks both the history block and the evaluation metrics** |
| Audit narrowed to RDCO | `S-05`, `S-07` | **Not built — all four offices have access today** |
| CSV export endpoint | `W-04` | Not built (`TODO` in the page) |
| Date-range and record filters | `W-04` | Not built |
| `GET /audit/` with pagination and filters | — | **Exists and works** |

---

## 4 · Why this file matters more than its screen count

Two of the eight communications identified in [00](00-design-direction.md) as absent — *when a resubmission occurred* and *which clearances survived it* — are recorded nowhere at all. Not hidden by the UI: **not written**.

That makes `W-04` the one task on this list whose absence is unrecoverable. A missing screen can be built in Week 13. Events not written during the Weeks 11–12 pilot cannot be reconstructed afterwards, and the evaluation has no second pilot to fall back on.
