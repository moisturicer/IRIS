# 08 — Testing Tasks

Five tasks. Two are blockers.

**Why these are rated Critical.** Of the five defects that stop IRIS running, an import-smoke test catches three, `makemigrations --check` catches a fourth, and `docker compose config` catches the fifth. Jira holds 51 issues and **not one** covers testing. This is the root cause of the architecture review, not a side finding.

**Strategy: test the seams, not coverage.** Broad coverage on a codebase this size is not achievable before the thesis deadline and would not have caught any of the five blockers. The tests below are ordered by defects-caught-per-hour.

---

# TEST-01 · Backend test harness and import-smoke tests

## Objective
Establish `pytest` and write the handful of tests that would have caught most of the defects in this review.

## Problem
Zero test files exist across eight Django apps. There is no runner, no fixtures, no factories and no configuration.

## Current State
No test file anywhere in `backend/`. `requirements/development.txt:4` still reads `# TODO: add pytest-django and factory-boy when writing tests`.

Consequences, all verified:
- `apps/records/views.py` uses six undefined names and nothing noticed (`BE-01`)
- Four methods are indented into the wrong class, breaking three routed endpoints (`BE-02`)
- `apps.ai` is installed with no migrations and shadowed modules (`BE-04`)
- Celery workers consume queues nothing publishes to (`BE-03`)

## Proposed State
`pytest` + `pytest-django` + `factory-boy` configured, with tier-1 tests running in CI.

## Scope
- Add the three dev dependencies and `pytest.ini` / `pyproject` configuration
- `conftest.py` with database and authenticated-client fixtures
- Factories for `User`, `Record`, `RecordUpload`, `Review`, `RecordClearance`
- **Tier 1 tests:**
  - `test_urlconf_imports` — walks `django.urls.get_resolver().url_patterns`
  - `test_no_missing_migrations` — `makemigrations --check --dry-run`
  - `test_all_apps_importable` — imports every module in `apps/`
  - `test_celery_tasks_routable` — asserts each task's queue has a consumer in Compose

## Out of Scope
Broad endpoint coverage. Lifecycle and policy tests (`TEST-03`, `TEST-04`).

## Technical Approach
`test_urlconf_imports` is four lines and catches the entire class of defect behind `BE-01`, `BE-02` and `BE-04`. Write it first.

## Dependencies
`BE-01` must land or the harness cannot import the URLconf. Feeds `ARCH-01`.

## Risks
None. Expect tier-1 tests to fail on first run — that is the point.

## Security Impact
Indirect but large: makes `TEST-04`'s authorization tests possible, which is what stops the security fixes silently regressing.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
`+pytest`, `+pytest-django`, `+factory-boy` (dev only).

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `pytest` runs and collects tests.
- [ ] `test_urlconf_imports` passes and fails if an undefined name is introduced into any view module (demonstrated).
- [ ] `test_no_missing_migrations` passes and fails when a model field is added without a migration (demonstrated).
- [ ] Factories create a valid `User`, `Record` and `Review`.
- [ ] The suite runs in under 60 seconds.
- [ ] All four tier-1 tests run in CI.

## Definition of Done
Merged; both demonstrations recorded in the PR; wired into `ARCH-01`.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`testing`, `backend`, `mvp-blocker`, `tooling`

---

# TEST-02 · CI enforcement of the test suite

## Objective
Make the tests load-bearing rather than decorative by running them on every push.

## Problem
Tests that are not enforced do not prevent regressions. This task is the enforcement half of `ARCH-01`.

## Current State
No CI. See `ARCH-01`.

## Proposed State
`pytest`, `npm test`, `typecheck`, `lint`, `makemigrations --check` and `docker compose config` all run on push and pull request, and a failure blocks merge.

## Scope
- Wire all six checks into the `ARCH-01` workflow
- Postgres service container for the backend job
- Cache pip and npm
- Document required checks for branch protection

## Out of Scope
Coverage thresholds — premature. Deployment automation.

## Technical Approach
Fail fast: run `manage.py check` before the full suite so import errors surface in seconds.

## Dependencies
`ARCH-01`, `TEST-01`, `FE-02`.

## Risks
Low. Branch protection is the repo owner's action, not a code change.

## Security Impact
Prevents silent reintroduction of the `05-security-tasks.md` defects once fixed.

## Performance Impact
None on the application.

## Deployment Impact
Becomes the gate for deployment later.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] All six checks run on every push and pull request.
- [ ] A pull request with a failing test cannot be merged (branch protection enabled).
- [ ] Total runtime is under 5 minutes.
- [ ] A deliberately broken commit is demonstrated to fail, then reverted.
- [ ] The required-checks list is documented.

## Definition of Done
Workflow green; branch protection enabled; demonstration recorded.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`testing`, `ci`, `mvp-blocker`, `tooling`

---

# TEST-03 · Table-driven lifecycle tests

## Objective
Prove the record lifecycle behaves as specified, across every legal and a representative set of illegal transitions.

## Problem
The workflow is the core domain and has zero tests. `WF-01` is the highest-risk refactor in the backlog and cannot be attempted safely without them.

## Current State
No tests. Transition logic spans `reviews/services.py` (11 sites) and `records/views.py` (7 sites), reachable only through authenticated HTTP requests.

SRS Module 5 is marked draft, so this logic will change.

## Proposed State
A parametrised test over the transition table covering every legal edge, illegal edges, and the three routing variants (Proposal / Thesis-Research / Project).

## Scope
- Every legal `(from_status, event, role) → to_status` edge
- Representative illegal transitions raising `InvalidPipelineTransition`
- The three type-differentiated routes end to end
- Clearance-smart resubmission: only the declining office resets
- Rollback behaviour from `WF-05`

## Out of Scope
Notification content (`WF-03` asserts emission, not wording).

## Technical Approach
`@pytest.mark.parametrize` over the table from `WF-01`. Pure-function predicates need no database; state transitions need one but no HTTP.

**This is the largest single testability gain in the backend** — the reason `WF-01` is worth doing.

## Dependencies
`TEST-01`, `BE-05`, `WF-01`.

## Risks
Low. Writing these *before* `WF-01` (as characterisation tests of current behaviour) is safer than after — recommended.

## Security Impact
Covers the separation-of-duties rules that `SEC-05` restores.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] Every edge in the `WF-01` table has a passing test.
- [ ] An illegal transition raises `InvalidPipelineTransition` and leaves the record unchanged.
- [ ] All three record types route correctly from `draft` to their terminal state.
- [ ] Resubmission after an IERC decline resets only the IERC clearance, preserving KTTO's.
- [ ] Resubmission after a sequential decline clears all clearances.
- [ ] Tests run without HTTP and complete in under 10 seconds.

## Definition of Done
Merged; running in CI; edge coverage against the table documented.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`testing`, `backend`, `workflow`, `fr-m5-01`

---

# TEST-04 · Authorization regression suite

## Objective
Prove every fixed access-control defect stays fixed, and satisfy NFR-S4's validation method.

## Problem
Twelve endpoints currently lack object-level authorization. Without regression tests, the thirteenth ships unchecked and the twelve reopen.

## Current State
No authorization tests. The defects are enumerated in `05-security-tasks.md`: `SEC-02` (record retrieve), `SEC-03` (six document endpoints), `SEC-04` (six storage endpoints), `SEC-05` (`is_staff` bypass).

**NFR-S4's validation is explicitly a test:** *"boundary test using a Student-role account to attempt direct API calls to RDCO-restricted endpoints, verifying all such requests return HTTP 403 Forbidden with no restricted data in any response body."*

## Proposed State
A parametrised matrix over `(role, endpoint, ownership) → expected status`, plus one regression test per fixed defect.

## Scope
- Matrix covering the six roles against every record, document and storage endpoint
- One explicit regression test per `SEC-0x` defect
- A `(role, stage, action)` table for `SEC-05` / `WF-02`
- Assert response **bodies** contain no restricted data, not only status codes

## Out of Scope
Penetration testing. Rate-limit and brute-force testing (`VAL-01` covers NFR-S6).

## Technical Approach
One fixture set: two students each owning a record, one adviser, one per office, one superuser. Parametrise across it. This is the single highest-value test suite in the project.

## Dependencies
`TEST-01`. Written alongside `SEC-02`…`SEC-05` — **in the same PRs**, not after.

## Risks
Low. The risk is deferring it: fixes without tests reopen.

## Security Impact
This *is* the durable security fix. The `SEC-0x` tasks close the holes once; this keeps them closed.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] A Student account calling any RDCO-restricted endpoint receives 403 with no restricted data in the body (NFR-S4 validation).
- [ ] A non-owner retrieving another user's draft record receives 404.
- [ ] A non-owner calling `files/download-all/` receives 403.
- [ ] A non-owner deleting another user's storage folder receives 403/404.
- [ ] An ITSO account calling `PATCH /users/<id>/role/` receives 403.
- [ ] An ITSO account approving at `rdco_review` is refused and the record does not advance.
- [ ] Every test is tagged so the suite can be run alone as an NFR-S4 evidence artefact.

## Definition of Done
Merged with the `SEC-0x` fixes; running in CI; output recorded as NFR-S4 evidence for `VAL-02`.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`testing`, `security`, `rbac`, `nfr-s4`, `mvp-required`

---

# TEST-05 · Frontend test harness

## Objective
Make the frontend testable at the seams `FE-01`, `FE-03` and `FE-04` create.

## Problem
Zero frontend tests, no runner, and types checked only as a side effect of `npm run build`.

## Current State
No test file in `frontend/src/`. No `test` script. `vitest` is not installed.

Defects a harness would have caught: the refresh interceptor never updating the store (`FE-01`); two colliding `useRole` exports with different return types (`FE-03`); `PendingRecordsPage` rendering "No pending records" on a network failure (`FE-04`).

## Proposed State
Vitest + React Testing Library, with tests on the three modules that carry real logic.

## Scope
- Install and configure `vitest` and `@testing-library/react`
- Tests for the token module: single in-flight refresh, store update, post-logout clearing
- Tests for `useRole`: superuser-without-role, each of the six roles
- Tests for query hooks: loading, error and success states
- `axe-core` accessibility assertions (`FE-08`)

## Out of Scope
Component snapshots (brittle, low value). End-to-end browser tests — `VAL-13` covers usability manually.

## Technical Approach
Vitest reuses the Vite config, so no separate transform pipeline. Test behaviour at the seams, not implementation detail.

## Dependencies
`FE-02` (configuration). Tests follow `FE-01`, `FE-03`, `FE-04`.

## Risks
Low.

## Security Impact
`FE-01`'s post-logout token clearing becomes a permanent assertion.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
`+vitest`, `+@testing-library/react` (dev only).

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] `npm test` runs and passes.
- [ ] A test proves ten concurrent 401s trigger exactly one refresh.
- [ ] A test proves `localStorage` is empty after logout.
- [ ] A test proves `useRole` treats a superuser with no role as staff.
- [ ] A test proves a list page renders an error state on a rejected request.
- [ ] `npm test` runs in CI.

## Definition of Done
Merged; running in CI; the five assertions above passing.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`testing`, `frontend`, `vitest`, `mvp-recommended`
