# Assignment deadline contract (IR-619)

Authority: [ADR-043 §§1–6](../adr/043-review-turnaround-reminders-and-escalation.md).

`Turnaround` and `Holiday` are maintained in Django admin. No turnaround row
means no clock. Demo seeding inserts **demonstration-only** five-working-day
values for unconfigured parties; it preserves values administrators already set.

Migration `reviews/0017` deliberately leaves every existing assignment's four
clock fields null. It does not invent opening dates or backfill deadlines.
Assignment opening and new-Version rereview sample the current turnaround;
ordinary saves, reassignment and nominations into active assignments do not.

Working days are Monday–Friday excluding `Holiday.date`, counted after the
opening day in Asia/Manila, with the deadline at 23:59. Document pauses use the
same convention: working dates after the first request opens through the last
request's closure. A same-day wait adds zero days. Overlapping own requests
share one pause. Rejection of an uploaded document starts a new pause when it
reopens the request. Changes to holidays affect future counting operations,
never rewrite stored running deadlines.

`POST /api/v1/assignments/<id>/extend/` accepts an ISO-8601 timezone-aware
`due_at` at 23:59 Manila and a nonblank `reason`. It moves only a configured,
active office assignment later. A party waiting on its revision has no running
clock to extend. Adviser assignments have no manual extension authority.

## Authorization matrix declaration (IR-615 / IR-616)

The endpoint is declared in IR-615's generic route-walking matrix at
`apps/tests/access/table.py::REVIEW_DEADLINES`, executed by
`AccessMatrixTests.test_review_deadline_routes`. The configured-success cases
also live in `apps/tests/test_authorization_matrix.py::ASSIGNMENT_EXTENSION_ACCESS`,
executed by `AssignmentExtensionMatrixTests`. `test_deadlines.py` pins hidden
versus missing responses and invalid extension bodies.

| Viewer | Visible assignment | Hidden or missing assignment |
|---|---|---|
| Anonymous | 401 | 401 |
| Owner or assigned Adviser | 403 | 404 |
| Office member, seat holder included | 403 | 404 |
| Coordinator of a different office | 403 | 404 |
| Coordinator of this office | 200 with valid later date and reason | 404 |
| RDCO acting outside its office | 403 | 404 |
| Roleless Django superuser | 404 | 404 |

Tracker parties, current assignment capabilities, reviewer seats and My Reviews
rows share `deadline_payload`: `due_at`, `original_due_at`, `is_overdue`,
`clock_paused`, `extensions` and `can_extend`. Extension prose and actor ids
follow the tracker's existing review-content visibility predicate. An open own
revision or document pause suppresses overdue; closed assignments are never
overdue. Workflow transitions and clearances do not consume these fields.

Each manual or system Extension writes `ASSIGNMENT_EXTENDED` in its own date
movement transaction. Metadata: assignment id, party, extension id,
previous_due_at, due_at, reason, system. A failed audit insert rolls back the
Extension and date movement. New-Version clocks retain earlier Extension rows
as history; `original_due_at` names the current Version's original deadline.
