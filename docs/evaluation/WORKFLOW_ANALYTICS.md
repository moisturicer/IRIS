# Workflow analytics and the ADR-011 evaluation

**Purpose.** What the Workflow Analytics page (`/review/analytics`,
`GET /api/v1/reviews/analytics/`) reports, how each figure is computed, and how
those figures relate to the [ADR-011](../adr/011-evaluation-framework.md)
evaluation, so that **neither is cited as the other**.
**Owns.** The analytics' definitions and thresholds.
**Does not own.** The event types and their metadata keys ([AUDIT_EXPORT.md](AUDIT_EXPORT.md)),
the due-date rules ([ADR-043](../adr/043-review-turnaround-reminders-and-escalation.md)),
and the evaluation's design (ADR-011, [ADR-004](../adr/004-restart-all-comparison-mode.md)).
**Update when.** A figure, threshold or scope rule in `backend/apps/reviews/analytics.py`
changes. Change that file and this one in the same PR.

---

## They are not the evaluation

| | Workflow analytics (IR-626) | ADR-011 evaluation |
|---|---|---|
| **Question** | How is the workflow running *now*, office by office? | Is IRIS usable, and does clearance-aware resubmission beat restart-all? |
| **Data** | Every workflow event the live system logged | Phase 3 sessions: SME participants walking pre-built scenarios under both arms, counterbalanced |
| **Time** | Elapsed time in stage, nights and waits on the author included | Time-on-task, measured by the session protocol |
| **Preserved clearances** | An operational count of what happened | Not primary evidence. ADR-004 rejects counting them as a finding: given which office asked, the count is an arithmetic identity |
| **Who sees it** | An office its own figures, RDCO every party's | The researchers, anonymised under RA 10173 |

So:

- **Do not cite a time-in-stage figure as ADR-011's per-stage turnaround or
  time-on-task.** It is elapsed time on organic records, not effort on a
  controlled scenario. ADR-011's per-stage turnaround is computed from the
  *evaluation's* audit export ([AUDIT_EXPORT.md](AUDIT_EXPORT.md) §Computing
  the metrics) over the scenario records only.
- **Do not cite the page's preserved-clearance count as evidence for the
  contribution.** Under `restart_all` it is zero by construction; the
  contribution is evaluated by ADR-004's within-subjects comparison.
- **Do cite the page for operational context**: pilot volume, how often
  resubmission occurs in practice, and where records wait. ADR-011 names
  organic volume as its dominant risk, and these figures show whether it
  materialised.

The two share their arithmetic. The page replays the same per-party clock
rule that AUDIT_EXPORT.md writes down, so a figure on the page can be
reproduced from an audit export of the same events.

## What each figure is

All counting is in **Asia/Manila**. Weeks start on Monday. `from` and `to`
are inclusive dates.

| Figure | Definition |
|---|---|
| **Time in stage** | Per party, and per party and record type: from the party receiving the record (`SUBMITTED`, `ROUTED` with `opened`, or a `RESUBMITTED` that reopens a party with no clock running) to its `ASSIGNMENT_CLOSED` with `how` `completed`. A revision or a document request does not stop the clock, and a seat reassignment does not restart it. A turn counts in the range its close falls in, in full. **Median**, and the **90th percentile by nearest rank** (the smallest value at or above 90% of the sorted turns) |
| **Not measured** | Per party: closes with no start in the log (the record entered before IR-144's deployment; never shown as zero) and turns ended by a decision or a withdrawal (not finished, so not a duration), both within the range; and clocks running now, whatever the range |
| **Open now** | Active assignments, the pool among them (no open seat), open seats, assignments with no due date (opened before IR-619, or a party with no Turnaround), paused (an open revision or document request), overdue (a due date, a running clock, and past it: `deadline_payload`'s rule), and the open seats on overdue assignments. Not filtered by date |
| **Throughput** | Per party per week: clock starts (entered) and `ASSIGNMENT_CLOSED` rows of any kind (left) |
| **New versions** | Per policy: `RESUBMITTED` rows the office took part in (re-reviewed, reset or preserved), those that preserved at least one of the office's clearances, and the `CLEARANCE_PRESERVED` rows |

## Small numbers

A cell shows **no median below 5 distinct records** and **no 90th percentile
below 10**, and says "Too few records (n of 5)". Below ten records, the
nearest-rank 90th percentile is simply the slowest record. The thresholds are
judgement, not derived; they are in `analytics.py` and the payload carries
them. They count distinct records, while the median and percentile are taken
over turns: a record reopened under restart-all adds a second turn to its cell.

## Scope

An ITSO, IERC or KTTO account reads its own office; RDCO reads every
assignable party, the Adviser stage included. Scope is applied in the
queryset (`analytics.scoped_events`, `scoped_open_assignments`), so a row about
only another office never leaves the database. A new Version's row names every
party it touched and is read whole, but only the scoped parties' counts reach
the payload. Asking for another office is a 403.
**No figure names, counts or ranks a reviewer**, and the payload carries no
user or seat id.

## What it leaves in

Time in stage keeps the author's share of a revision: AUDIT_EXPORT.md gives
`RESUBMITTED − RESUBMISSION_REQUESTED` to subtract it, and the page does not,
so it reports elapsed time and says so. A document-request pause moves the due
date (ADR-043 §4) but not the elapsed time. Every request reads the whole
scoped log, because a turn ending in the range may have started before it;
that is fine at pilot volume and is the first thing to bound if it grows.

## Coverage

Figures start at the first workflow event in scope, which the page states.
IR-144 has no backfill, so earlier work is absent, not zero. Due dates start
at IR-619's deployment for the same reason: an older assignment shows as
"no due date", never as on time. A workflow event that failed to insert
(AUDIT_EXPORT.md §What is logged) is missing here too.
