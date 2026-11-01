# ADR-050: Calls & Conferences lists calls for papers, and RDCO confirms an Adviser's

## Status

**Proposed** — 2026-11-01 (IR-759, spec IR-758), awaiting acceptance by Lee Jasmin Adolfo, the project lead. The decisions come from a design session with Hermoine Zozobrado on 2026-11-01. ADR-049 is skipped because IR-716 already names it.

This is the feature's first ADR. It replaces IR-121's decisions on types, posting and saving, and ADR-044's Q3 on saves.

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
   - **Automatic:** Posted by, always the signed-in account. It shows a name and never falls back to an email address.
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
- **The pilot runs before this is built**, on the current rules: Advisers publish immediately, and saves stay in the browser. Real Calls and saves may exist by then, which is why decision 16 keeps a copy of each deleted Call, and why dropped browser saves are a real, accepted loss.
- There is no public archive of past Calls.

## MVP Impact

None. The feature is outside the MVP and is built after it. IR-757's narrowing of who may post is already merged.

## SaaS Impact

The types and Areas apply to any institution. RDCO's role here would map to whichever office runs another institution's research coordination, as it does elsewhere.

## Security Impact

It closes the unvetted-link risk (decision 8) and the typed-office impersonation (decision 3), and makes every change attributable (decision 15). Decision 3 also stops a poster's email address from appearing when they have no name. A compromised RDCO account can still publish a bad link immediately, and the audit trail records it. The authorization matrix gains the new routes.

## Deployment Impact

Migrations change `Opportunity`'s fields and types, add a status and a saved-Call table, and add audit event types. One more scheduled job expires requests. No new service or setting.

## Research Impact

None on the workflow contribution or RAG. Ask IRIS doesn't read Calls. The board isn't part of the thesis evaluation.

## Related Requirements

None. IR-121 records that no requirement backs this feature. Implementation tickets add entries to `docs/testing/TRACEABILITY.md`.

## Related Tasks

IR-758 (spec, under IR-671), IR-759 (this ADR), IR-760, IR-761, IR-762, IR-763, IR-649, IR-764, IR-765 and IR-766. Also IR-121, IR-530, IR-757, IR-566 and ADR-044.
