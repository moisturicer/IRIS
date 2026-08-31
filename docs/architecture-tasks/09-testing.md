# 09 — Testing

Four tasks. **Test the seams, not coverage.** Broad coverage is not reachable in 27 dev-days and would not have caught any of the five current blockers. These are ordered by defects-caught-per-hour.

> Of the five things that stop IRIS running today, an import-smoke test catches three, `makemigrations --check` catches a fourth, and `docker compose config` catches the fifth. Jira holds 51 issues and **not one** covers testing.

---

# T-01 · Backend test harness and import-smoke tests

## Objective
Establish `pytest` and write the handful of tests that would have caught most of the defects in this review.

## Problem
Zero test files exist across eight Django apps. No runner, no fixtures, no factories, no configuration.

## Evidence
No test file anywhere in `backend/`. `requirements/development.txt:4`: `# TODO: add pytest-django and factory-boy when writing tests`.

What went undetected as a result: six undefined names causing a `NameError` at import (`B-01`) · four methods indented into the wrong class breaking three routed endpoints (`B-02`) · `apps.ai` installed with no migrations and shadowed modules (`B-04`) · Celery workers consuming queues nothing publishes to (`B-03`).

## Current State
Nothing verifies that the code imports, let alone works.

## Proposed State
`pytest` + `pytest-django` + `factory-boy` configured, with tier-1 tests in CI.

## Scope
Add the three dev dependencies and configuration; `conftest.py` with database and authenticated-client fixtures; factories for `User`, `Record`, `RecordUpload`, `Review`, `RecordClearance`; **tier-1 tests**: `test_urlconf_imports` (walk `django.urls.get_resolver().url_patterns`) · `test_no_missing_migrations` · `test_all_apps_importable` · `test_celery_tasks_routable`.

## Out of Scope
Broad endpoint coverage. Authorization matrix (`T-02`) and workflow tests (`T-03`).

## Technical Approach
`test_urlconf_imports` is four lines and catches the entire class of defect behind `B-01`, `B-02` and `B-04`. **Write it first, in the same PR as `B-01`.**

## Dependencies
`B-01` must land or the harness cannot import the URLconf. Feeds `F-01`.

## Risks
None. Expect tier-1 to fail on first run — that is the point.

## Security Impact
Indirect and large: makes `T-02` possible, which is what stops the security fixes silently regressing.

## Performance Impact
None.

## SaaS Impact
Per-instance releases gate on the same suite.

## Research/Thesis Impact
Protects thesis-critical workflow code from regression during `W-01`, the riskiest refactor.

## MVP Classification
MVP BLOCKER

## Priority
P1 — Week 4

## Complexity
S

## Acceptance Criteria
- [ ] `pytest` runs and collects tests.
- [ ] `test_urlconf_imports` fails when an undefined name is introduced into any view module (demonstrated, then reverted).
- [ ] `test_no_missing_migrations` fails when a model field is added without a migration (demonstrated).
- [ ] Factories create a valid `User`, `Record` and `Review`.
- [ ] The suite runs in under 60 seconds.

## Testing Requirements
This task is the testing requirement. Both demonstrations recorded in the PR.

## Documentation Requirements
Test strategy feeds `DOC-04`.

## Definition of Done
Merged; four tier-1 tests green in CI.

---

# T-02 · Authorization regression suite

## Objective
Prove every fixed access-control defect stays fixed, and satisfy NFR-S4's validation method.

## Problem
Twelve endpoints currently lack object-level authorization. Without regression tests the thirteenth ships unchecked and the twelve reopen.

## Evidence
Defects enumerated in `05-security.md`: `S-02` (record retrieve), `S-03` (six document endpoints), `S-05` (`is_staff` bypass), plus `SC-01` (six storage endpoints, removed rather than fixed).

**NFR-S4's validation is explicitly a test:** *"boundary test using a Student-role account to attempt direct API calls to RDCO-restricted endpoints, verifying all such requests return HTTP 403 Forbidden with no restricted data in any response body."*

## Current State
No authorization tests.

## Proposed State
A parametrised matrix over `(role, endpoint, ownership) → expected status`, plus one regression test per fixed defect, plus a `(role, stage, action)` table for `S-05`.

## Scope
Matrix across six roles and every record and document endpoint; one explicit regression test per `S-0x`; the role × stage table; **assert response bodies contain no restricted data**, not only status codes.

## Out of Scope
Penetration testing. Rate-limit and brute-force testing (`V-06` covers NFR-S6).

## Technical Approach
One fixture set: two students each owning a record, one adviser, one per office, one superuser. Parametrise across it. **Written in the same PRs as the `S-0x` fixes, not after.**

## Dependencies
`T-01`. Written alongside `S-02`, `S-03`, `S-05`.

## Risks
Low. The risk is deferring it — fixes without tests reopen.

## Security Impact
**This is the durable security fix.** The `S-0x` tasks close the holes once; this keeps them closed.

## Performance Impact
None.

## SaaS Impact
Under pooled multi-tenancy every case would gain a tenant dimension (`SA-03`). Under instance-per-tenant, intra-institution only.

## Research/Thesis Impact
Its output is the NFR-S4 evidence artefact for `V-07`.

## MVP Classification
MVP REQUIRED

## Priority
P1 — alongside the `S-0x` fixes

## Complexity
M

## Acceptance Criteria
- [ ] A Student calling any RDCO-restricted endpoint receives 403 with no restricted data in the body.
- [ ] A non-owner retrieving another user's draft receives 404.
- [ ] A non-owner calling `files/download-all/` receives 403.
- [ ] An ITSO account calling `PATCH /users/<id>/role/` receives 403.
- [ ] An ITSO account approving at `rdco_review` is refused and the record does not advance.
- [ ] Tests are tagged so the suite can run alone as an NFR-S4 evidence artefact.

## Testing Requirements
Runs in CI on every push; run against the deployed instance for `V-07`.

## Documentation Requirements
Output recorded as NFR-S4 evidence in `DOC-05` and `DOC-06`.

## Definition of Done
Merged with the `S-0x` fixes; green in CI; run against the interim deployment.

---

# T-03 · Workflow transition tests across both policies

## Objective
Prove the lifecycle behaves as specified under both resubmission policies — the correctness evidence behind the thesis contribution.

## Problem
The workflow is the core domain and has zero tests. `W-01` is the highest-risk refactor in the plan and cannot be attempted safely without them.

## Evidence
No tests. Transition logic spans `reviews/services.py` (11 sites) and `records/views.py` (7 sites), reachable only through authenticated HTTP. SRS Module 5 is marked draft, so this logic will change.

## Current State
Untested and about to be refactored.

## Proposed State
A parametrised test over the `W-01` table covering every legal edge, representative illegal ones, all three routing variants, and **both resubmission policies**.

## Scope
Every legal `(from_status, event, role) → to_status` edge · illegal transitions raising `InvalidPipelineTransition` · the three type-differentiated routes end to end · clearance-aware resubmission preserving unaffected offices · restart-all resetting everything · rollback behaviour from `W-03`.

## Out of Scope
Notification content — `W-04` asserts emission, not wording.

## Technical Approach
`@pytest.mark.parametrize` over the table. **Write these as characterisation tests of current behaviour *before* `W-01`** — safer than after, and they become the regression suite for the refactor.

## Dependencies
`T-01`, `F-02`. Precedes and then validates `W-01`, `W-02`.

## Risks
Low, and it reduces the risk of the highest-risk task in the plan.

## Security Impact
Covers the separation-of-duties rules `S-05` restores.

## Performance Impact
None.

## SaaS Impact
The same suite validates any institution's configured table — the generality claim becomes testable.

## Research/Thesis Impact
**Thesis-critical.** This is the correctness evidence for [ADR-003](../adr/003-clearance-aware-resubmission.md) and the sanity check on [ADR-004](../adr/004-restart-all-comparison-mode.md)'s comparison — if the two policies are not provably different in behaviour, the experiment measures nothing.

## MVP Classification
MVP REQUIRED — thesis-critical

## Priority
P1

## Complexity
M

## Acceptance Criteria
- [ ] Every edge in the `W-01` table has a passing test.
- [ ] An illegal transition raises and leaves the record unchanged.
- [ ] All three record types traverse `draft` → terminal state.
- [ ] Under `CLEARANCE_AWARE`, an IERC decline then resubmit resets only IERC; KTTO's `cleared` persists.
- [ ] Under `RESTART_ALL`, the same sequence resets every clearance.
- [ ] Tests run without HTTP in under 10 seconds.

## Testing Requirements
This task is the testing requirement. Runs in CI.

## Documentation Requirements
Edge coverage against the table recorded in `DOC-04`.

## Definition of Done
Merged; green in CI; coverage documented.

---

# T-04 · Frontend test harness

## Objective
Make the frontend testable at the seams `FE-01` and `FE-05` create.

## Problem
Zero frontend tests, no runner, types checked only as a side effect of `npm run build`.

## Evidence
No test file in `frontend/src/`. No `test` script. `vitest` not installed.

Defects a harness would have caught: the refresh interceptor never updating the store (`FE-01`); two colliding `useRole` exports with different return types (`FE-05`).

## Current State
No frontend test capability.

## Proposed State
Vitest + React Testing Library, with tests on the modules that carry real logic.

## Scope
Install and configure; tests for the token module (single in-flight refresh, store update, post-logout clearing) and `useRole` (superuser-without-role, six roles).

## Out of Scope
Component snapshots — brittle, low value. End-to-end browser tests — `V-11` covers usability with real participants.

## Technical Approach
Vitest reuses the Vite config, so no separate transform pipeline. Test behaviour at the seams, not implementation detail.

## Dependencies
`FE-04` (configuration). Tests follow `FE-01`, `FE-05`.

## Risks
Low.

## Security Impact
`FE-01`'s post-logout token clearing becomes a permanent assertion.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
Session instability would contaminate `V-11` usability data.

## MVP Classification
MVP RECOMMENDED

## Priority
P3

## Complexity
M

## Acceptance Criteria
- [ ] `npm test` runs and passes.
- [ ] A test proves ten concurrent 401s trigger exactly one refresh.
- [ ] A test proves `localStorage` is empty after logout.
- [ ] A test proves `useRole` treats a superuser with no role as staff.
- [ ] `npm test` runs in CI.

## Testing Requirements
This task is the testing requirement.

## Documentation Requirements
Frontend test approach in `DOC-04`.

## Definition of Done
Merged; four assertions passing in CI.
