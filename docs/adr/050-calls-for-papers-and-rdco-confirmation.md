# ADR-050: Calls & Conferences lists calls for papers, and RDCO confirms an Adviser's

## Status

**Accepted** — 2026-11-01 by Lee Jasmin Adolfo, the project lead, as relayed by Hermoine Zozobrado (IR-759, spec IR-758). The decisions come from a design session with Hermoine Zozobrado on 2026-11-01. ADR-049 is skipped because IR-716 already names it.

This is the feature's first ADR. It replaces IR-121's decisions on types, posting and saving, and ADR-044's Q3 on saves.

[ADR-051](051-system-admin-account-deletion-and-consent.md), Accepted 2026-11-01, changes two things here: the System Admin rather than RDCO reads these events in the Audit Log (decision 15), and the Call Requests page sits at `/rdco/call-requests`, in a nav section named RDCO.

An amendment of 2026-11-12 (IR-758, below) restates both in this ADR's own text and settles which list a Call's Areas come from.

An amendment of 2026-11-15 (IR-762, below, accepted 2026-11-15) deletes a request whose paper deadline passes instead of expiring it, and stops an Adviser saving a past paper deadline.

## Context

Observed on `main`, 2026-11-01:

- The board (`/opportunities`, `apps/opportunities`, IR-121 and IR-530) lists four types: Internal Call, Conference Deadline, Funding Window and Institutional Grant. No requirement or ADR backs it, and IR-121 left open whether it belongs in the pilot.
- RDCO and Advisers post through a form (IR-757 removed KTTO). **A post goes public immediately**, with an outside link. The feature's own tests call an unvetted link "a phishing vector aimed at the whole institution".
- `posted_by` is set from the signed-in account and can't be supplied by a client. `posting_office` is free text, so an Adviser can type "RDCO", and the calendar file labels that text "Posted by".
- Any poster can tick **Feature this call**.
- A call stores one date. It turns "Closed" after that date and leaves the board 30 days later, so IRIS can't tell "stopped accepting papers" from "already happened".
- Nothing about a call is audited, and deleting one erases it.
- Saves stay in the browser (`lib/opportunityLibrary.ts`), so they don't follow the reader, and the next person on a shared PC can see them. ADR-044 Q3 left this for a follow-up ticket.
- `Classification`, one kind of **Area**, already groups papers and has a list endpoint that Discover uses.

## Decision

1. **The board is for viewing and saving calls for papers.** It is outside the MVP (`post-mvp-candidate`). It stays visible during the pilot, with no setting to hide it. Grants, funding windows and internal CIT-U calls are off the board.
2. **Types:** Conference, Congress, Symposium, Workshop, Journal and Book Chapter. The board filters by each.
3. **Fields.**
   - **Required:** type, title, about, paper deadline, location, at least one Area (from `Classification`), link.
   - **Optional:** start date, end date, registration fee (free text, because fees are often tiered or in another currency).
   - **Automatic:** Posted by, always the signed-in account's name.
   - **Removed:** posting office, audience, funding ceiling, tags and source.
4. **Journal and Book Chapter have no event.** Their form hides the start and end dates and fills location with "Online", which the poster can change. They store no event dates.
5. **The server checks no date**, against today or against another date. The poster is responsible for them.
6. **Every Call carries two independent tags**, worked out by the server:
   - **Papers:** Accepting papers through the paper deadline, then Submissions closed.
   - **Event:** Happening now from the start date through the end date (a one-day event uses its start date as its end), then Over.

   A Call with no event dates is Over the day after its paper deadline. Over is decided by the latest date entered, so a mistyped date can't end a Call early.
7. **An Over Call leaves the board** and stays in the database. This replaces the 30-day rule.
8. **RDCO's Calls go public immediately. An Adviser's Call waits for RDCO to confirm it.**
   - A waiting Call is visible only to its Adviser and RDCO. Anyone else gets the same 404 as a missing Call.
   - RDCO reviews from a **Call Requests** page in Administration, beside its other request queues, and is notified in-app of each request.
   - RDCO confirms or rejects. A rejection needs a reason, which the Adviser receives.
   - A rejected Call stays visible to its Adviser, who may edit and resubmit it, or delete it.
   - Calls that exist when this ships are treated as confirmed.
9. **A request whose paper deadline passes expires.** It leaves RDCO's list and the Adviser is told. A request entered with a past deadline expires straight away.
10. **An Adviser's edit to a confirmed Call returns it to waiting**, and it leaves the board until RDCO confirms again. RDCO's own edits don't.
11. **Who may change a Call.** An Adviser may edit or delete their own. RDCO may edit or delete any. Removing an Adviser's Call needs a reason, which the Adviser receives.
12. **Featured is RDCO's alone**, on a request or a confirmed Call. It adds a star and the label "Featured", and doesn't change a Call's position.
13. **A saved Call is stored per account**, in its own table in `apps/opportunities`, because `SavedRecord` (ADR-044) points at papers.
    - It appears in its own section of My Library and under the board's Saved filter.
    - It stays in My Library, with its tags, until the reader removes it or RDCO deletes the Call.
    - A saved Call that returns to waiting or is rejected shows as unavailable, with nothing more about it.
    - Saving isn't audited (ADR-044 §3). Browser saves are dropped, not imported. This replaces ADR-044 Q3.
14. **No in-app reminders.** The deadline is the reader's to track, and the calendar download of the paper deadline stays.
15. **Audited:** posting, editing (with old and new values, including Featured), deleting (with a copy of the Call), confirming, rejecting and removing (with RDCO's reason). RDCO sees them in the Audit Log.
16. **Moving existing data.** A Conference Deadline becomes a Conference, and its new required fields may stay blank until it is next edited. Internal Calls, Funding Windows and Institutional Grants are deleted, each with an audit event carrying a copy.

## Alternatives Considered

- **Keep the four original types.** The board would also cover funding. Rejected: the team wants one purpose, finding where to send a paper.
- **Conferences only, with no journals.** Every Call would have the same fields and stages. Rejected: a journal's special issue is also a call for papers, and researchers need to find those too.
- **Only two types, Conference and Journal.** Simpler filters. Rejected: posters and readers want a workshop or symposium labelled as what it is, and these types behave the same.
- **Free-text tags instead of Areas.** No list to maintain. Rejected: "AI" and "A.I." would become separate filters, and Discover already uses Classification names.
- **Keep a typed posting office, locked for Advisers.** RDCO could still post on another office's behalf. Rejected: Posted by already says who is responsible, and a second name invites confusion.
- **Advisers publish immediately, with RDCO notified afterwards.** No queue or delay. Rejected: a bad link would be live until someone at RDCO acted.
- **A pending list on the board instead of a page in Administration.** Less to build. Rejected: RDCO's other request queues are in Administration, and the board stays free of RDCO's work.
- **Keep the old version live while an edit waits.** A small correction wouldn't hide a Call. Rejected: it means storing two versions of every Call.
- **Server checks on dates.** They would catch typos. Rejected: conferences do unusual things, such as late-breaking deadlines during the event, and the poster knows the Call.
- **One "closed" tag.** Simpler. Rejected: a conference can stop accepting papers and still be held.
- **Keep Over Calls on the board.** "Over" would show there too. Rejected: the board would fill with events nobody can act on.
- **A deployment setting to hide the board during the pilot.** Participants couldn't reach it. Rejected: the tag is enough, and the setting is one more thing to test.
- **Saved Calls in `apps/library`.** One app for everything a reader keeps. Rejected: it would tie the board to that app, and IR-121 keeps the board removable as a unit.
- **Clear browser saves on sign-out.** It ends the shared-PC leak cheaply. Rejected: readers would lose their saves every time.
- **In-app deadline reminders.** IR-121's reason against them no longer holds, because review reminders now run on Celery. Rejected anyway: this page is for viewing and saving.

## Decision Rationale

Narrowing the board to calls for papers gives it one job, and every other decision follows from that: fewer fields, one rule for when a Call ends, and a filter by Area. RDCO's confirmation closes the one real risk in the feature, an institution-wide link that nobody checked, without slowing RDCO's own posts.

## Consequences

- **RDCO has a new queue.** A slow review can cost an Adviser their post, because a request expires at its paper deadline. The notification and the notice on expiry soften that but don't remove it.
- **A small correction hides a Call** until RDCO confirms it again. An extended deadline, a common edit, does this too.
- **An unchecked date is visible.** A mistyped date shows wrong tags until someone corrects it, though RDCO sees the dates on an Adviser's request.
- **Readers can't tell why a Call is Featured.** It is a signal from RDCO with no stated reason.
- **Two save tables and APIs** exist, one for papers and one for Calls.
- **Ended Calls collect in My Library** until the reader removes them.
- **The pilot runs before this is built**, on the current rules: Advisers publish immediately, and saves stay in the browser. Real Calls and saves may exist by then, which is why decision 16 keeps a copy of each deleted Call. Calls saved in a browser before this ships are dropped once, an accepted loss; every save after that is stored per account.
- There is no public archive of past Calls.

## MVP Impact

None. The feature is outside the MVP and is built after it. IR-757's narrowing of who may post is already merged.

## SaaS Impact

The types and Areas apply to any institution. RDCO's role here would map to whichever office runs another institution's research coordination, as it does elsewhere.

## Security Impact

It closes the unvetted-link risk (decision 8) and the typed-office impersonation (decision 3), and makes every change attributable (decision 15). A compromised RDCO account can still publish a bad link immediately, and the audit trail records it. The authorization matrix gains the new routes.

## Deployment Impact

Migrations change `Opportunity`'s fields and types, add a status and a saved-Call table, and add audit event types. One more scheduled job expires requests. No new service or setting.

## Research Impact

None on the workflow contribution or RAG. Ask IRIS doesn't read Calls. The board isn't part of the thesis evaluation.

## Related Requirements

None. IR-121 records that no requirement backs this feature. Implementation tickets add entries to `docs/testing/TRACEABILITY.md`.

## Related Tasks

IR-758 (spec, under IR-671), IR-759 (this ADR), IR-760, IR-761, IR-762, IR-763, IR-649, IR-764, IR-765 and IR-766. Also IR-121, IR-530, IR-757, IR-566 and ADR-044.

## Amendment — 2026-11-12 (IR-758): Areas, the Audit Log and the Call Requests page

**Status of this amendment: Accepted** — 2026-11-13: reviewed, accepted and merged by Ashlee Sean (PR #711), as relayed by Hermoine Zozobrado. Recorded before any of IR-760 to IR-766 is built.

1. **A Call's Areas are Classifications only** (decisions 3 and the board's Area filter). CONTEXT.md defines an **Area** as a Classification or a PSCED category; for a Call it is always a Classification, the same topic names Discover filters by. PSCED fields are too broad to help a reader find a call for papers, and a second picker and filter would add work for no use. Decided by Hermoine Zozobrado, 2026-11-12.
2. **Only the System Admin reads these events** (decision 15). RDCO no longer reads the Audit Log at all (ADR-051 decision 15). Read decision 15's last sentence as "The System Admin sees them in the Audit Log."
3. **The Call Requests page is at `/rdco/call-requests`, in the RDCO section of the navigation** (decision 8), not under Administration. This restates ADR-051, which already placed it there.
4. **A saved Call is declared in both account-data registries** (decision 13): `apps/accounts/deletion/registry.py`, saying what deleting the account does to it, and `apps/accounts/personal_data/registry.py`, saying which section of the personal-data download carries it. Both registries came after this ADR (IR-794, IR-786); their guard tests fail until a new table that points at a person is declared. The likely rules, for IR-649 to confirm: deleting the account deletes the person's saved Calls, and the download lists them.
5. **The posting form follows IR-585**: it marks optional fields, not required ones.

## Amendment — 2026-11-15 (IR-762): a lapsed request is deleted, and an Adviser can't enter a past deadline

**Status of this amendment: Accepted** — decided by Hermoine Zozobrado, 2026-11-15, while building IR-762. Accepted by Lee Jasmin Adolfo on 2026-11-15, as relayed by Hermoine Zozobrado, when IR-762's PR (#808) merged.

1. **An Adviser can't save a Call whose paper deadline has passed** (decision 5). The check uses Manila's date, and covers a new Call and an edit. RDCO's dates stay unchecked, so RDCO can still post a late-breaking deadline. A request can no longer be entered already expired, so decision 9's last sentence no longer applies.
   - Consequence: once its paper deadline has passed, an Adviser can still edit their Call, but only by moving the deadline to today or later. The edit returns it to waiting (decision 10). An edit that keeps the past deadline is refused, since point 2 would delete it. RDCO's edits stay unchecked.
2. **A request whose paper deadline passes is deleted, not expired** (decision 9).
   - It leaves RDCO's list at once, and RDCO can no longer confirm or reject it.
   - A daily job deletes it just after midnight in Manila. Its Adviser gets one notice saying they may post a new one.
   - There is no expired status. A Call is waiting, confirmed or rejected.
   - A rejected Call is deleted the same way. Until the job runs, its Adviser can still resubmit it by moving its deadline forward (point 1).
   - These deletions are deletions under decision 15, with a copy of the Call (IR-763).
3. **Which removals need a reason** (decision 11): removing a Call posted by an account that isn't RDCO, and that still exists. RDCO removes its own Calls, a colleague's, or one whose poster's account is gone without a reason, since nobody would receive it. Each case has one way in: a Call needing a reason is removed with one, and one needing none is deleted.
4. **RDCO decides the version it saw** (decision 8). A confirm or reject names the Call's last-changed time as RDCO read it. An Adviser may edit a waiting Call meanwhile, and a decision on a Call changed since is refused, so RDCO never confirms content it hasn't read.
5. **Consequences, restated.** A slow review now costs an Adviser their post outright, not only its place in RDCO's list. The notice softens that but doesn't remove it.

## Amendment — 2026-11-15 (IR-763): the daily job's deletions have their own audit type

**Status of this amendment: Proposed** — decided by Hermoine Zozobrado, 2026-11-15, while building IR-763. It is accepted when IR-763's PR merges.

1. **A lapsed request's deletion is audited as `CALL_LAPSED`**, not `CALL_DELETED`. It has no actor and carries a snapshot of the Call. This refines the 2026-11-15 (IR-762) amendment's point 2: these are still deletions under decision 15, with a copy of the Call, but they get a type of their own so they can be told apart from a person's delete and counted.
2. **Decision 15's acts are therefore seven event types:** `CALL_POSTED`, `CALL_EDITED`, `CALL_DELETED`, `CALL_CONFIRMED`, `CALL_REJECTED`, `CALL_REMOVED` and `CALL_LAPSED`. `CALL_POSTED` carries a full snapshot too, so the log alone can follow a Call's versions. Areas appear as ids and names. The keys are in `docs/evaluation/AUDIT_EXPORT.md`.
