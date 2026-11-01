# IR-363 visual evidence

Captured on 2026-11-01 in Chromium, at 1440 × 1050, with the Asia/Manila timezone.
The Docker development backend was running and `python manage.py seed_demo`
completed successfully. Both frontend versions used real authentication as
`rdco@cit.edu`, the seeded RDCO staff account, and the same development database.
No token or browser storage is included in this evidence.

**Before** is the PR's merge base, `86478f1be9b68f71e30bfa979c8584e0d21f8b42`.
**After** is the IR-363 implementation, including the follow-up shared controls
and warning style. Separate Vite servers and dependency caches kept the two
versions isolated from the main checkout.

| Screen | Before | After | Coverage |
|---|---|---|---|
| Download requests | [Before](before-download-requests.png) | [After](after-download-requests.png) | Pending, live approval, declined, revoked, cancelled, expired approval; All selected |
| Delete requests | [Before](before-delete-requests.png) | [After](after-delete-requests.png) | Pending, approved, declined, deletion warning; All selected |
| Role requests | [Before](before-role-requests-live.png) | [After](after-role-requests-live.png) | Pending request from the real endpoint |
| Users | [Before](before-users.png) | [After](after-users.png) | Demo student account and its actions |
| Audit log | [Before](before-audit.png) | [After](after-audit.png) | Real events filtered to the seeded RDCO actor |
| Import records | [Before](before-import.png) | [After](after-import.png) | Initial import form and template action |
| Sessions component | [Before](before-sessions-component.png) | [After](after-sessions-component.png) | First five active RDCO demo sessions from the real endpoint |
| Role request states component | [Before](before-role-states-component.png) | [After](after-role-states-component.png) | Synthetic pending, approved and declined states |

## Evidence boundaries

- `seed_demo` does not seed the request queues. For these captures, six download
  request rows, three deletion request rows and one pending role request were
  temporarily added against a demo record and demo student. Notes identify them
  as IR-363 visual evidence. They are rendering fixtures, not proof that workflow
  transitions ran. No record was deleted or approved during capture. The fixture
  rows were removed afterward, fenced by their IDs, notes and demo account.
- An expired download approval remains **Approved**, with an hourglass, a quiet
  tone and an explicit **Expired** date. It offers no Revoke action.
- The role-request endpoint returns only pending requests. The live captures
  therefore show pending only. The separate, visibly labelled component harness
  supplies the other states without changing the endpoint.
- `SessionsPage` has no route or navigation entry in this revision. A temporary,
  visibly labelled harness rendered the actual component with the real sessions
  API, restricted to the first five RDCO demo sessions. It was not added to the
  application. The endpoint lists active sessions only, so an expired-session
  screenshot is not applicable. Routing and session behavior were not changed.
- Non-demo rows were omitted from the role-request and user-list DOM immediately
  before capture. The user-list footer still reports the server's total; these
  images demonstrate the palette on demo data, not search-result correctness.
- Refresh and Pending/All controls were exercised against the live backend after
  conversion to `Button`. The download queue returned six rows for All and one
  for Pending. The existing deletion endpoint returns all three fixture rows
  even with `status=pending`; this frontend palette change does not alter it.

The temporary harnesses, Vite configuration and frontend cache were removed after
capture. The running Docker services and unrelated checkout changes were preserved.

## Verification

- TypeScript: `npx tsc --noEmit -p .` passed.
- ESLint on the four follow-up source files passed.
- Palette, request-state chip, admin, accounts and audit tests: **43 passed in
  6 files**. No existing test was modified.
- The first full-suite attempt, with two workers, exhausted host memory before
  completing. The serial retry result is recorded in the PR.

Human review and approval remain required before merge and Jira Done.
