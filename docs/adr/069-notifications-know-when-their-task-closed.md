# ADR-069: A notification that asks for action says when that task has closed

## Status

**Accepted** — 2026-11-14 (IR-1072), by **Lee Jasmin Adolfo** (project lead and frontend owner), as decision D2 of the UI/UX audit ([IR-1071](https://citiris.atlassian.net/browse/IR-1071), [`docs/frontend_ui_audit_spec.md`](../frontend_ui_audit_spec.md) §4.2 and §7.1). Not built yet: [IR-1075](https://citiris.atlassian.net/browse/IR-1075) builds it.

No ADR owned the notification contract until now. It is spread across [ADR-029](029-proposal-similarity-and-collaboration.md) (match notices), [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) (who hears about a Decision, a withdrawal, a delete) and [ADR-043](043-review-turnaround-reminders-and-escalation.md) (reminders). This ADR adds one field pair to that contract and leaves the rest alone.

## Context

Observed on the deployed site and on `main`, 2026-11-13 and 2026-11-14:

- **A notification is never settled.** The audit (finding WF-01) signed in as an ITSO coordinator. An unread notification said RDCO had sent a paper to the office and it waited in the pool. My Reviews showed **To review 0** and the record sat under **Done**. The notification still asked for action that was no longer possible.
- **The model has no such state.** `Notification` holds a sender, a direct recipient or a broadcast role, a record, a type, a message and `created_at`. Read state is per person in `NotificationRead` (`apps/notifications/models.py`). Nothing records that the task a notification asked for has ended.
- **Broadcasts are shared; reading is not.** A notification to a role (ITSO's pool, RDCO) is one row that every member of the role sees. Whether the task behind it is still open is a fact about the record, not about one reader.
- **The client cannot work it out.** The task's state lives on seats, assignments, requests and decisions that the notification list does not carry, and the frontend must not infer workflow state ([IR-374 §0](../frontend_redesign_spec.md)).
- **Clearance-aware resubmission makes tasks reopen.** When an author resubmits, an office whose clearance resets is asked again. Whatever a notification says about the first request must stay true after that.

## Decision

1. **A notification that asks the recipient to act can be resolved.** Once the task it asked for has ended, the server sends `resolved_at` and `resolved_label` with it, for example "Cleared by ITSO · no action needed". The client renders a settled line from them and never infers one.
2. **It leaves the unread count.** A resolved notification is no longer counted as unread. It stays in the list, drawn as settled.
3. **Which notifications resolve.** Only those that ask for action: a review request or assignment, a revision or document request, a new Version to review, a download or delete request, a role request, a deadline reminder. Informational notifications (a decision, a publication, a comment, a mention) never resolve. IR-1075 lists the types; this ADR fixes the rule, not the list.
4. **When.** A notification resolves when the task leaves the recipient, **whoever closed it**: it was cleared, a colleague claimed it, the request was withdrawn, or a Decision closed the record's review. The label says what happened. For a broadcast to a pool the task is the pool's, so it resolves for every member at once, while read state stays per person.
5. **Resolved is final.** A resolved notification is never reopened. When a resubmission resets a clearance, IR-1075 sends a new notification for the new request. The old one keeps saying what happened the first time.
6. **The mechanism is IR-1075's.** Working the state out when the list is read heals old notifications with no migration but costs a lookup per notification. Storing it on the notification reads cheaply but needs a backfill and a write in every path that closes a task. Because of decision 5, whichever is chosen must remember the closing event, so a later reset cannot undo it. IR-1075 chooses and records the reason.
7. **The copy defect is fixed in the same ticket.** The notification the audit saw joined two sentences ("please check It is in your office's pool"). It becomes two sentences: "RDCO sent *Title* to ITSO. It waits in ITSO's pool until a reviewer claims it."

## Alternatives Considered

- **The client hides a notification when the record has moved on.** Needs a request per notification, and the client would be deciding workflow state, which IR-374 §0 forbids.
- **Resolve only for the person who closed the task.** A colleague who did not act would keep an unread request that nobody can do any more, which is the audit's finding again.
- **Reopen a notification on a reset.** Keeps one row per task, but the unread count could rise on its own and "cleared on v1" would be lost from the history.
- **Delete the notification when its task closes.** Loses the history that clearance-aware resubmission exists to show.

## Decision Rationale

Coordinators lose trust in the queue when a notification contradicts it, and on a busy week they cannot tell which notifications still need them (PRODUCT principle 1, "Say what is waiting on whom"). Making the server say it keeps the rule in one place, and making it final keeps the history honest across resubmissions, which is the thesis contribution.

## Consequences

- IR-1075 adds the two fields to the notification payload and changes the unread count. It ships backend tests and, if it stores the state, a migration tested on a copy of a realistic database. It adds `docs/testing/traceability/IR-1075.md` (ADR-055).
- The notifications page renders a settled line for a resolved notification and no longer treats it as unread.
- Every producer in `apps/notifications/services.py` that asks for action must say which task it asked for, so the server can tell when that task ends.
- Notifications sent before this ships have no closing event. IR-1075 decides whether they are resolved from today's state or left as they are, and says so.

## MVP Impact

In scope for the redesign's first phase (IR-1075, priority High). No new service.

## SaaS Impact

None. The rule does not name an institution.

## Security Impact

A resolved label must not tell a reader about a record they cannot see. It is built only from what the notification's own message already shows its recipient. The notification list keeps its object-level filtering.

## Deployment Impact

If IR-1075 stores the state, it ships one migration. No new setting.

## Research Impact

Supports the workflow contribution. A resolved line that reads "Cleared by ITSO on v1" beside a new notification for v2 shows clearance-aware resubmission in the place coordinators already look.

## Related Requirements

- ADR-032 §9 (My Reviews) and §10 (who is told).
- ADR-043 (reminders), ADR-029 (match notices).
- IR-374 §0 (the frontend decides no workflow state).

## Related Tasks

- [IR-1072](https://citiris.atlassian.net/browse/IR-1072) — this decision.
- [IR-1075](https://citiris.atlassian.net/browse/IR-1075) — builds it, under [IR-671](https://citiris.atlassian.net/browse/IR-671).
- [IR-1071](https://citiris.atlassian.net/browse/IR-1071) — the audit (WF-01, US-10, A11Y-07).
