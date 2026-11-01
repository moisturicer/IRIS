# Core application journeys — check plan (IR-631)

IR-631 verifies that the application works **as one integrated build**: one
pinned `main` commit, production settings, every service running, and every
core journey driven end to end. A set of separately green feature tests does
not establish that, because each one stubs or skips what the others provide.

This file is the plan: which checks prove which acceptance criterion (AC),
how each is run, and what it reuses. The *results* of a run go in a run
record under [`runs/`](runs/), copied from
[`runs/TEMPLATE-core-journeys.md`](runs/TEMPLATE-core-journeys.md).

## How a run works

| | |
|---|---|
| Build | One commit SHA, chosen when the delivery gates (below) have landed |
| Stack | `docker-compose.prod.yml` + [`docker-compose.e2e.yml`](../../docker-compose.e2e.yml): production settings, gunicorn + UvicornWorker, every Celery worker and beat, Docling (CPU), nginx. Feature flags at their defaults; no disclosure bypass |
| Data | Fresh database; `seed_demo --accounts-only`; a 5-working-day Turnaround per party (`review_clock_for_testing`). Every Record is created by the journey that uses it, with a unique `[E2E …]` title, origin `synthetic` |
| Runner | `.github/workflows/core-journeys.yml`, started by hand with the SHA. Locally: [`e2e/README.md`](../../e2e/README.md) |
| Browser | Chromium, one journey at a time, no retries — a pass on a second attempt is not a pass |
| Evidence | Playwright HTML report, JSON results, traces/video of failures, axe results per key screen, `build.json` (SHA, settings, Turnaround) and the stack log, uploaded as one artifact named for the SHA |

**Limitations a run record must restate.** TLS is out of scope: nothing in
the repository terminates it, so the run sends `X-Forwarded-Proto: https` as
the fronting proxy would, and follows emailed links' paths on the plain-HTTP
address. Mail goes to Mailpit inside the stack. The Turnaround is
demonstration data, not an agreed value. The inactivity-expiry check runs in
a separate short pass with `SESSION_IDLE_TIMEOUT_MINUTES=2`, because the
server enforces the 30-minute default. DRF's general request throttles are
raised to 20000/day for the run: through nginx every signed-out request comes
from one address, and the 100/day default runs out partway through one full
run. No acceptance criterion measures them; the lockout under test (axes,
three failures) is unchanged. These two are the only settings that differ.

## Statuses

Every row of a run record ends in exactly one of:

- **Passed** — the check ran on the pinned build and every assertion held.
- **Failed** — it ran and an assertion did not hold, or it errored. Linked to a
  defect key (an existing one where it exists; a new ticket only for a genuinely
  uncovered defect, created after a person confirms it). **A failed required
  journey blocks IR-631's completion.**
- **Unmeasured** — it did not run, with the reason. Not a pass, and not
  quietly dropped.

## Delivery gates

The final run waits for: IR-250 (embargo field — without it the disclosure
gate refuses every Record, so Ask IRIS can only answer "no readable
sources"), IR-630 (upload → grounded answer → page citation), IR-414
(accessibility verification) and IR-95 (DEV-20 performance/reliability).
Every other gate named on IR-631 was Done on 2026-11-01.

## Checks by acceptance criterion

| AC | What is checked | How | Spec / instrument | Reuses |
|---|---|---|---|---|
| 1 · Account lifecycle | Register, verify by emailed link, await approval, RDCO approves the requested role, sign in, three failures lock out with the server's notice, recovery by emailed link, inactivity expiry and reauthentication | Browser + Mailpit; expiry in the short idle pass | `e2e/specs/00-account-lifecycle.spec.ts` | IR-166, IR-555, IR-642 |
| 2 · Thesis/Project | Draft, edit, upload, submit; adviser-first; document request and fulfilment; accept & route to three parallel pools; member claim and coordinator assignment; IERC Revision request; new Version resets only IERC while ITSO and KTTO are **Preserved** (API and Paper View); Hand-back to RDCO; RDCO's Decision; published Record readable anonymously | API acts, browser for what the owner is shown | `e2e/specs/01-thesis-project.spec.ts` | IR-624, IR-625 |
| 3 · Proposal | Adviser accepts; non-owner refused; two simultaneous `continue-as` requests make exactly one Continuation (201 + 409); the Continuation cannot be submitted without its own manuscript; lineage both ways in API and on the page | API + browser | `e2e/specs/03-proposal-continuation.spec.ts` | IR-417 |
| 4 · Coordination | RDCO grants and removes a coordinator, and the grant is what permits assigning; assign and reassign with reason; Extension needs a reason, is coordinator-only and moves the date later; an overdue turn escalates to coordinators and changes no state; analytics scoped to own office, RDCO sees all | API + browser (My Reviews overdue) + `review_clock_for_testing` | `e2e/specs/04-coordination.spec.ts` | IR-478, IR-619–IR-623, IR-626 |
| 5 · Discussion/history | Comments and replies bound to their Version; private to participants; owner's next action follows a Revision request and the new Version; both Versions in history; RDCO's audit filters; CSV export row count equals the filtered total; non-RDCO refused | API + browser | `e2e/specs/05-discussion-history.spec.ts` | IR-419, IR-529, IR-625 |
| 6 · Reading and Ask IRIS | Permitted discovery, truthful author/origin/provenance, manuscript/page citation, follow-up, conversation switching, retry/cancel/reload, one logical Turn | **Reused, not re-run here**: IR-630 and IR-605/IR-608 evidence from the same SHA. Unmeasured until IR-250 lands | — | IR-630, IR-605, IR-608, IR-563 |
| 7 · Adversarial access | Anonymous, another user, cross-office, guessed file ids and a withdrawn Seat fail safely; a hidden Record answers exactly as a missing id; the UI shows a stranger no part of it; private Records stay out of search, notifications and exports | API + browser | `e2e/specs/02-adversarial-access.spec.ts` | IR-153, IR-615/616, IR-627 |
| 8 · Integrity | Double submit → one submission; simultaneous claims → one Seat per reviewer; a stale decision form → 409 and nothing changed; double new Version → one Version; a retried reminder job → each notification once | Simultaneous API requests | `e2e/specs/06-integrity.spec.ts` | IR-561, IR-370 |
| 9 · Keyboard, zoom, 360px | axe (serious/critical, WCAG 2.1 A/AA, contrast included) and 360px reflow on each journey's key screen; keyboard, 400% zoom and screen-reader use by a person | Automated in each spec; manual checklist in the run record | `support/a11y.ts` + run record §Manual | IR-414 and its linked defects |
| 10 · Concurrency and recovery | Consistency after concurrent and retried requests (AC8). Latency recorded as observed numbers with **no verdict**: no application target is agreed | Annotations in AC8's spec | `e2e/specs/06-integrity.spec.ts` | IR-95, DEV-20 defects |
| 11 · Evidence | Every row passed, failed or unmeasured with the build, settings and data | The run record | `docs/testing/runs/` | — |
| 12 · Completion | All applicable ACs, migrations, UI/backend integration, executed evidence and human approval under `docs/engineering/DEFINITION_OF_DONE.md` §4 | A person | — | — |

## What this plan does not do

It does not re-implement or re-own any feature: a failure is a defect in the
ticket that owns the feature. It does not enable a proposed AI engine,
spend provider credits, measure capacity or throughput, or exercise hosting,
TLS, backups or production provisioning (IR-631 §Scope).
