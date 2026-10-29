# ADR-043: Review turnaround, reminders and escalation

## Status

**Accepted — 2026-10-28, by Lee Jasmin Adolfo.** IR-618 (parent IR-612). Proposed the same day after a design grilling with Lee Jasmin Adolfo. IR-619, IR-620, IR-621 and IR-622–IR-626 build to it.

Amends ADR-032 by adding a time dimension to its assignments. It changes no ADR-032 decision: no act, state, routing edge or visibility rule.

## Context

ADR-032's routing is largely built: adviser-first entry, office Pools and Seats, coordinator assignment, Versions and clearance-aware resubmission. None of it has a time dimension. No review carries a due date, nothing reminds a reviewer, and a Record left in a Pool stays there with nobody told. `apps/reviews`, `apps/records` and `apps/notifications` hold no due, deadline or overdue field or logic, and `backend/config` defines no Celery beat schedule.

ADR-032's own Consequences name the risk: "a stale or absent Adviser [is] a blocker for the whole record. There is no triage fallback."

Decided before this ADR (IR-612, 2026-10-28):

- Each office has a default turnaround, applied when its review starts. The office coordinator can extend it.
- The reviewer gets an in-app reminder before the due date and on it.
- Once overdue, the office coordinator is notified.
- **A deadline never decides anything.** It does not clear, reject, record a finding, route or withdraw. Human review stays the gate.
- Analytics read IR-144's workflow `AuditEvent`s. Office staff see their own office, and RDCO sees every office. There is no backfill before IR-144.

## Decision

### 1. The due date belongs to the assignment, not the Seat

The clock attaches to the party's `RecordAssignment` and starts when the party receives the Record. For a specialist office that is one [Review round](../../CONTEXT.md), starting when the office is routed the Record. For the Adviser it starts at submission, and for RDCO at the Hand-back. Every Seat on that assignment shows its due date; no Seat carries its own.

- **Why.** A routed Record lands in the office's Pool as an assignment with **no Seat** (ADR-032 §4). A per-Seat clock would leave an unclaimed Pool, the most stuck case, with no due date, no reminder and no escalation. The assignment is also the span that ADR-011's per-stage turnaround and IR-626's time-in-stage measure.
- **Re-routing.** An office routed the same Record again starts a new round (ADR-032 §4, *Amendment* 2026-10-08), so it gets a new clock with no special rule.
- **Corrects IR-619**, whose title read "every open office seat carries a due date". The due date belongs to the assignment, and Seats display it.
- *Rejected: a due date per Seat.* It names exactly who is late, but it leaves an unclaimed Pool with no clock, and it understates the office's real wait when a Seat is created days after routing.
- *Rejected: both, with a Seat able to override the round.* That is two clocks to store, remind on, extend and explain. It can be added later on top of this decision if per-person deadlines prove necessary.
- *Cost:* two reviewers in one office share one due date, so one slow Seat makes the office overdue, not only its holder.

### 2. Turnaround is configured per party, by an administrator, and is off until set

A `Turnaround` row per party (`adviser`, `itso`, `ierc`, `ktto`, `rdco`) holds a number of working days, edited in Django admin.

- **A party with no row gets no due date, no reminder and no escalation.** It behaves exactly as IRIS does today. IRIS invents no default value, on the same principle as ADR-041's provider limits: an unset value means "not configured", never a guessed number. The real numbers belong to the offices.
- **A due date is fixed when the assignment opens.** Changing a party's turnaround affects only assignments opened afterwards. A running due date moves only by an Extension (§6) or a pause (§4).
- `seed_demo` sets demonstration values, marked as such in the command's output.
- *Rejected: environment settings.* Every change would need a redeploy that only developers can make.
- *Rejected: a built-in default (e.g. 5 working days).* The number would be invented, not the offices'.
- *Cost:* nothing is visible until someone enters values.

### 3. Days are working days, minus an administrator-kept holiday table, in Manila time

- A turnaround of *N* counts *N* working days after the day the assignment opens. Working days are Monday to Friday, excluding the dates in a `Holiday(date, name)` table that an administrator maintains in Django admin.
- All counting uses **Asia/Manila**. A due date is the end of that working day (23:59 Manila time), so an assignment is never overdue on the morning it is due.
- An empty holiday table degrades to Monday to Friday. Forgetting to fill it is unfair to offices, but it breaks nothing.
- *Rejected: calendar days.* A weekend or a campus closure such as Holy Week would eat into an office's turnaround.
- *Rejected: working days with no holiday table.* It is simpler, but a review due across Holy Week goes overdue through no fault of the office.
- *Cost:* one small model, and one more thing for an administrator to keep current.

### 4. The clock pauses while the party's own document request is open

While an ADR-022 document request **made by that party** is open, the party cannot finish (ADR-032 §4, *Amendment* 2026-10-08), so it is waiting on the owner, not late. When the request is settled or withdrawn, the due date moves later by the number of working days it was open.

- Overlapping requests from the same party count as one span, never twice.
- The move is recorded as a **system Extension** (§6) in the timeline and the audit log, so a changed date always carries its reason.
- Another party's request does not pause this party's clock, because this party can still finish.
- *Rejected: no pause.* It produces false overdues and false escalations, and a turnaround measure that counts the student's speed as the office's.
- *Rejected: no pause, but suppress reminders while a request is open.* The due date itself would still be wrong, and the Record would show "overdue" with no explanation.

### 5. Revision, new Versions, reassignment and re-routing

- **Revision request and new Version.** While a party's Revision request is open, the Record waits on its author and that party has no running clock. When the owner submits the next Version, each assignment that reopens gets a **fresh due date** from its party's turnaround. Parties whose clearances are preserved get no new date, because they have no new work. This is clearance-aware resubmission (ADR-003) applied to time.
- **Reassignment within an office.** Moving a Seat from one member to another **does not change the due date**. The commitment is the office's. If more time is needed, a coordinator records an Extension. A reassignment can never quietly reset a clock.
- **Routing to an office that already has an active assignment** opens nothing new (ADR-032 §4), so the existing due date stands. A nomination only adds a Seat.

### 6. Extensions

- **Any coordinator of the office** (`User.is_office_coordinator`, within their own office only, ADR-032 §4) may move an office assignment's due date later, with a required reason. Each Extension writes an `AuditEvent` and appears in the Review timeline beside the original date.
- **An Adviser assignment cannot be extended by hand.** It has no coordinator, and letting the Adviser extend their own due date would make it meaningless. It moves only by a §4 pause.
- A due date only ever moves later. Bringing one forward is not an act.

### 7. Reminders and escalation

Reminders and escalation are in-app notifications through `apps/notifications`. Email is out of scope.

| Moment | Sent to |
|---|---|
| 2 working days before the due date | Every holder of a Seat on the assignment that is not done. **If the assignment has no Seat yet (an unclaimed Pool), the office's coordinators instead.** |
| On the due date | The same recipients |
| First working day overdue: **Escalation** | Every coordinator of that office |
| Every further 5 working days while still overdue | Every coordinator of that office |

- **Each moment is sent at most once per assignment, per due date, per kind.** An Extension or a pause sets a new due date and re-arms every moment.
- **An office with no coordinator** escalates to RDCO's coordinators instead, and a warning is logged. RDCO only learns of it: its coordinators cannot act inside another office.
- **The Adviser stage gets reminders but no Escalation**, because no coordinator stands above an Adviser. Once an Adviser assignment is overdue, the owner's status view (IR-625) says so plainly, e.g. "Waiting on your Adviser · 4 days overdue", so the owner knows why the Record is stuck and can chase their Adviser in person.
    - *Rejected: escalate an overdue Adviser to RDCO.* RDCO has no reassign-Adviser act, so it could do nothing, and on the Adviser accept & publish path ADR-032 keeps RDCO out of the workflow. Revisit when an Adviser first leaves mid-review, the trigger ADR-032 itself names.
- **Every recipient is checked against `Record.objects.visible_to(user)`** before a notification naming a Record is sent. Office staff see every record today, so this filters nothing yet. It makes sure a future narrowing of the predicate cannot turn reminders into a leak.
- Nothing in this section, or anywhere else, reads a due date to decide, clear, reject, route or withdraw. A test pins it.

### 8. The scheduler

- A new **`celery-beat`** Compose service, in development and production, runs one task **hourly**. The task asks the database which moments are owed now, so the schedule lives in data, not in beat.
- **Catch-up.** After downtime the next run sends what is owed, at most once per moment, and skips a moment that has since been superseded. A Record that went overdue during the outage gets one Escalation, not a stale "due in 2 days" reminder followed by it.
- **Idempotency is enforced by the database**: a uniqueness constraint on (assignment, due date, kind) for sent notifications. A re-run, a missed tick or two beat instances can never double-send.
- A failed notification is logged and does not abort the batch (IR-300).
- *Rejected: a cron entry calling a management command.* It costs the same as a container and is less visible in Compose.

## Alternatives Considered

- **No time dimension, and rely on analytics alone.** Stalls would only be visible after the fact, and nobody is told while it still matters.
- **Automatic action on overdue** (auto-clear, auto-route, auto-withdraw a Seat). Rejected outright: it makes a clock a decision-maker and removes human review as the gate.
- **Email reminders.** They reach people who are not logged in, but they need production mail delivery, bounce handling and an opt-out. Deferred.

Per-decision alternatives are recorded in §1–§8.

## Decision Rationale

The design adds the minimum time machinery that catches the stalls that actually happen: an unclaimed Pool, a slow Adviser, a forgotten Seat. It changes no workflow decision. The due date sits where completion and clearance already sit (the assignment), so it needs no new concept of an office's work. Every number is the institution's to set, so IRIS ships no invented policy.

## Consequences

- **Positive.** Every stage that has a turnaround can be measured and nudged. Coordinators learn about stalls while they can still act. Turnaround becomes a product capability as well as ADR-011's evaluation measure.
- **Negative.** There is a new Compose service, two small admin-maintained tables and a new notification stream that could become noise if turnarounds are set too tight.
- **Neutral.** Until an administrator enters a turnaround, nothing changes for anyone.

## MVP Impact

The backend slices (IR-619–IR-621) and their measurement (IR-626) are thesis-critical, because they make the workflow's turnaround observable. The frontend slices (IR-622–IR-625) are supporting, and are cut first if capacity is short.

## SaaS Impact

Turnaround and holidays are per deployment, which matches one institution per deployment. A multi-tenant deployment would need both scoped per tenant.

## Security Impact

- No new decision right. Extension authority is the existing coordinator grant, within its own office.
- The extend endpoint must be declared in the IR-611 authorization matrix (IR-615/IR-616).
- Notifications name Records, so every recipient passes `visible_to` (§7).

## Deployment Impact

Adds a `celery-beat` service to both Compose files, and migrations for the turnaround table, the assignment due date, the holiday table and the sent-moment ledger. They run through ADR-039's existing one-shot migrate. Assignments already open at deployment receive no due date unless IR-619 records an explicit backfill rule.

## Research Impact

Gives ADR-011's per-stage turnaround a product-side source, and IR-626 can report how many revision cycles preserved clearances. Figures exist only from IR-144's deployment onward, and the analytics must say so.

## Related Requirements

ADR-011 efficiency measures (per-stage and total workflow turnaround).

## Related Tasks

IR-612 (spec) · IR-618 (this ADR) · IR-619 (due dates) · IR-620 (reminders) · IR-621 (escalation) · IR-622 (My Reviews) · IR-623 (coordinator console) · IR-624 (Review timeline) · IR-625 (owner status) · IR-626 (analytics) · IR-144 · IR-300

## Related

ADR-003 · ADR-011 · ADR-021 · ADR-022 · ADR-032 §4–§5, §9 · ADR-039 · ADR-041
