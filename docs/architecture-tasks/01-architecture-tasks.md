# 01 — Architecture Foundation Tasks

Cross-cutting tasks that unblock or constrain everything else. Six tasks: one Critical, four decision records, one register.

---

# ARCH-01 · Establish a CI pipeline that runs on every push

## Objective
Create a GitHub Actions workflow that fails the build on import errors, missing migrations, broken Compose config, lint errors and type errors.

## Problem
There is no CI of any kind. All five defects that stop IRIS running are machine-detectable and none was detected. This is the root cause of the entire architecture review, not a side finding.

## Current State
No `.github/` directory exists in the repository. `package.json` defines `dev`, `build`, `preview`, `lint` — no `test`, no `typecheck`. `requirements/development.txt:4` still reads `# TODO: add pytest-django and factory-boy when writing tests`.

## Proposed State
`.github/workflows/ci.yml` runs on push and pull request, executing six checks in under two minutes.

## Scope
- Workflow file with Python and Node jobs
- Steps: install deps → `makemigrations --check --dry-run` → `manage.py check` → `pytest` → `npm ci && npm run typecheck && npm run lint && npm run build` → `docker compose config`
- Branch protection guidance documented (enabling it is the repo owner's action)

## Out of Scope
Deployment automation, container publishing, coverage gates, matrix builds across Python versions.

## Technical Approach
Single workflow, two jobs (`backend`, `frontend`), `services: postgres` for the backend job so `manage.py check` and `pytest` can reach a database. Pin action versions. Cache pip and npm.

## Dependencies
`TEST-01` (pytest must exist for step 4), `FE-02` (eslint config + typecheck script must exist for step 5). CI can land first with those steps commented and enabled as they arrive.

## Risks
Low. A red build on first run is expected and is the point — budget time to fix what it surfaces.

## Security Impact
Indirect and large: prevents silent reintroduction of the authorization defects in `05-security-tasks.md` once fixed.

## Performance Impact
None on the application.

## Deployment Impact
None initially. Becomes the gate for deployment later.

## Framework Impact
None. GitHub Actions is free for this repository.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] Pushing a commit triggers the workflow.
- [ ] A commit that introduces an undefined name in any Django module fails the build at `manage.py check`.
- [ ] A commit that adds a model field without a migration fails at `makemigrations --check`.
- [ ] A commit that references a non-existent Compose build context fails at `docker compose config`.
- [ ] A commit with a TypeScript error fails at `npm run typecheck`.
- [ ] Total wall-clock runtime is under 5 minutes.

## Definition of Done
Workflow merged and green on `refactor/docker-service`; `docs/SDLC_PROCESS.md` updated with the required-checks list; a deliberately broken commit demonstrated to fail and then reverted.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`ci`, `architecture`, `mvp-blocker`, `tooling`

---

# ARCH-02 · Reconcile Docker service topology with the SRS

## Objective
Bring `docker-compose.yml` and `docker-compose.prod.yml` into agreement with the SRS service table, so the stack builds and matches the specification it is assessed against.

## Problem
The Compose files declare ten services. Two build from a directory that does not exist, three consume Celery queues nothing publishes to, one is called by no code, and one has no schedule. Separately, the topology does not match the SRS.

## Current State
`docker-compose.yml` / `docker-compose.prod.yml` declare: `db`, `redis`, `backend`, `frontend`, `docling`, `ai-gateway`, `celery-default`, `celery-extraction`, `celery-embedding`, `celery-beat`.

`ai-gateway` builds from `./ai` — **the directory does not exist** (`git ls-files | grep '^ai/'` returns nothing). `docs/docker_compose_rag_services.md` specifies the context as `./ai-gateway`, a *third* non-existent path.

The SRS service table (`docs/SRS.md` §393-405) specifies: `nginx`, `web`, `celery-worker`, `celery-worker-rag`, `celery-beat`, `docling`, `db` (postgres:16 + pgvector), `redis`. **There is no FastAPI gateway in the SRS.** The phrase "internal AI gateway" at SRS:1380 describes a code-level abstraction for reaching the external AI service, not a container.

## Proposed State
Compose matches the SRS: `nginx`, `web`, `celery-worker`, `celery-worker-rag`, `celery-beat`, `docling`, `db`, `redis`, plus the SPA build. `ai-gateway` is removed.

## Scope
- Remove the `ai-gateway` service from both Compose files
- Reconcile worker services with the SRS's `celery-worker` / `celery-worker-rag` split and add matching `CELERY_TASK_ROUTES` (see `BE-03`)
- Add `nginx` as its own service per the SRS, or document why it is folded into the frontend image
- Fix the `db` image/version mismatch between the Compose files and `docs/docker_compose_rag_services.md`

## Out of Scope
Building an AI gateway (see `FW-05`). Removing Docling (see `FW-03`). Hosting choice (see `DEP-06`).

## Technical Approach
Edit both Compose files; verify with `docker compose config` then `docker compose up` to a healthy state.

## Dependencies
`BE-03` (queue routing must exist before named-queue workers are meaningful). Decision `FW-05` (gateway) and `FW-03` (Docling) should be recorded first.

## Risks
Medium — this is the file the branch was created to refactor. Coordinate with whoever authored `refactor/docker-service` so the intent behind the 10-service design is captured in `FW-05` before it is reversed.

## Security Impact
Indirect: fewer services, smaller attack surface. `SEC-01` removes the `/media/` route from the same nginx config.

## Performance Impact
Memory falls from a claimed ~8 GB to roughly 2–4 GB depending on the Docling decision.

## Deployment Impact
Large and positive — the stack becomes startable.

## Framework Impact
Drops FastAPI, uvicorn and asyncpg from the prospective dependency surface.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `docker compose -f docker-compose.yml config` exits 0.
- [ ] `docker compose -f docker-compose.prod.yml config` exits 0.
- [ ] `docker compose up` reaches a state where every service is running or healthy.
- [ ] No service references a build context that does not exist in the repository.
- [ ] The service list is reconciled against SRS §393-405, with any deliberate deviation recorded in an ADR.

## Definition of Done
Both Compose files start cleanly; `docs/docker_compose_rag_services.md` updated to match reality (`DOC-02`); `docker compose config` added to CI (`ARCH-01`).

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`docker`, `architecture`, `deployment`, `mvp-blocker`, `srs-alignment`

---

# ARCH-03 · ARCHITECTURE DECISION REQUIRED — Storage ownership model

## Objective
Decide whether `apps/storage` is personal, institutional, or both, so the missing authorization can be implemented correctly rather than guessed.

## Problem
`SEC-04` cannot be implemented without this answer. Filtering by owner is wrong if storage is meant to be a shared institutional drive; leaving it open is wrong in every reading.

## Current State
`apps/storage/models.py` carries `StorageFolder.created_by` and `StorageFile.uploaded_by`, which model personal ownership. `apps/storage/views.py` consults neither: all six endpoints are bare `IsAuthenticated`, and `StorageFolderDetailView` / `StorageFileDetailView` use unfiltered `Model.objects.all()`. Any authenticated user can delete any other user's folders, cascading to the whole subtree.

The SRS defines **FR-M2-06 Institutional File Storage Management** and SDD 3.2.7 defines **Personal File Storage** — two different features that the one app currently serves with no distinction.

Additionally `/storage` routes to a 13-line `ComingSoonPage` stub while a 204-line `FolderBrowserPage` sits unrouted.

## Proposed State
A recorded decision (ADR) selecting one of: **A** personal-only (filter by owner); **B** institutional (reads open, writes/deletes staff-only); **C** both, via a `scope` field.

## Scope
Decision and ADR only. Implementation is `SEC-04`.

## Out of Scope
Writing the code.

## Technical Approach
Compare FR-M2-06 and SDD 3.2.6/3.2.7 against the models; choose; record as `docs/adr/0001-storage-ownership.md`.

## Dependencies
None. Blocks `SEC-04` and the `FolderBrowserPage` routing decision in `FE-07`.

## Risks
Low as a decision. High if skipped — `SEC-04` gets guessed.

## Security Impact
Decisive. Determines what "correct" means for a live IDOR affecting every stored file.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Blocker** (blocks a blocker)

## Acceptance Criteria
- [ ] ADR recorded naming the chosen option and the FR it satisfies.
- [ ] The ADR states explicitly which roles may read, write and delete.
- [ ] A decision is recorded on whether `FolderBrowserPage` or `ComingSoonPage` ships at `/storage`.

## Definition of Done
ADR merged under `docs/adr/`; `SEC-04` updated to reference it; the losing frontend page deleted or ticketed.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`architecture-decision`, `adr`, `security`, `storage`, `mvp-blocker`

---

# ARCH-04 · ARCHITECTURE DECISION REQUIRED — `is_staff` semantics and separation of duties

## Objective
Decide whether IRIS office roles (RDCO, KTTO, ITSO, IERC) are Django site administrators, so the authorization bypass can be closed without removing access people legitimately rely on.

## Problem
Two meanings of "staff" were merged. The result is that ITSO and IERC accounts can change any user's role, lock any account, revoke any session, and approve at any workflow stage — including RDCO's final publication.

## Current State
`accounts/migrations/0005_set_is_staff_for_staff_roles.py` sets `is_staff=True` for `{RDCO, KTTO, ITSO, IERC}`. `core/permissions.py:23-25` defines `is_django_staff()` as `is_superuser or is_staff`. `IsAdmin` is documented as "KTTO, RDCO, or Django staff" but evaluates `is_django_staff(user) or role in ADMIN_ROLES` — so `ADMIN_ROLES` never constrains anyone. The same helper short-circuits `_can_review()` (`reviews/services.py:76-79`) and `_can_submit_clearance()`.

This directly contradicts **NFR-S4**: *"no authenticated user can view, modify, approve, or export records belonging to a workflow tier above their assigned role."*

## Proposed State
A recorded decision selecting: **A** separate the concepts (reverse `is_staff` for ITSO/IERC); **B** keep the flag but remove it from all authorization paths; or **C** accept the status quo explicitly.

## Scope
Decision and ADR. Implementation is `SEC-05`.

## Out of Scope
Writing the code.

## Technical Approach
Review NFR-S4 and SRS Module 5 against the four office roles; decide; record as `docs/adr/0002-staff-semantics.md`.

## Dependencies
None. Blocks `SEC-05` and `WF-02`.

## Risks
The decision removes capabilities current staff accounts may be using day to day. Confirm with the team before implementation, not after.

## Security Impact
Decisive. This is the highest-blast-radius authorization defect in the system.

## Performance Impact
None.

## Deployment Impact
May require a data migration reversing `is_staff` on existing accounts.

## Framework Impact
None.

## MVP Classification
**MVP Blocker** (blocks a blocker)

## Acceptance Criteria
- [ ] ADR recorded naming the chosen option.
- [ ] The ADR states whether office roles retain Django admin access and why.
- [ ] The ADR states whether any break-glass bypass exists and what audits it.
- [ ] Traceability to NFR-S4 is explicit.

## Definition of Done
ADR merged; `SEC-05` references it; team confirmation recorded in the ticket.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`architecture-decision`, `adr`, `security`, `rbac`, `mvp-blocker`, `nfr-s4`

---

# ARCH-05 · ARCHITECTURE DECISION REQUIRED — Record access PIN semantics

## Objective
Decide what `RecordAuthPin` is for, so it either enforces access or stops claiming to.

## Problem
The PIN mechanism issues and verifies one-time emailed PINs correctly and then enforces nothing. It is relied upon by the UI while gating no server-side resource — the worst of both states.

## Current State
`reviews/views.py:234-326`. `generate` looks up the record by id with no authorization check, so any authenticated user can trigger a PIN email for any record id (also an existence oracle). `verify` sets `is_used=True` and returns `{"verified": true}`, persisting no grant. `grep -rn "RecordAuthPin" backend/` returns only the model, its serializer, this view and its migrations — **no other view consults it**.

SDD 3.5.2 describes this as "Auth PIN for Gated Record Access."

## Proposed State
A recorded decision: **A** real access control (verification creates a server-side grant that record/document endpoints require); **B** confirmation-of-intent only (keep the UX, stop calling it access control); **C** remove.

## Scope
Decision and ADR. Implementation is `SEC-06`.

## Out of Scope
Writing the code.

## Technical Approach
Read SDD 3.5.2 and the relevant FR; decide; record as `docs/adr/0003-record-auth-pin.md`.

## Dependencies
Interacts with `SEC-02` — once record visibility is fixed, the PIN may be redundant.

## Risks
Low. Option A is the largest implementation; B and C are near-free.

## Security Impact
Moderate. Currently the control provides assurance it does not deliver.

## Performance Impact
Negligible.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] ADR recorded naming the chosen option and the governing FR.
- [ ] If A: the ADR names the grant mechanism and which endpoints enforce it.
- [ ] If B or C: the SDD wording is scheduled for correction in `DOC-06`.

## Definition of Done
ADR merged; `SEC-06` scoped to match; SDD correction ticketed if needed.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`architecture-decision`, `adr`, `security`, `mvp-required`

---

# ARCH-06 · Create an ADR register

## Objective
Establish `docs/adr/` so decisions stop being re-litigated and future architecture reviews do not re-suggest rejected options.

## Problem
Several decisions have been made and lost. The SRS change history records that switching the RAG framework to n8n was "rejected" in May 2026 — with no reasoning captured — and the Qdrant→pgvector change appears only as a one-line history entry, which is why the Jira backlog still specifies Qdrant nine months later.

## Current State
No `docs/adr/` directory. Decisions live in SRS change-history table rows, code comments, and the heads of individual contributors.

## Proposed State
`docs/adr/` with a short template and the decisions from `ARCH-03`, `ARCH-04`, `ARCH-05`, `FW-03`, `FW-05`, `FW-06` recorded, plus retrospective entries for pgvector-over-Qdrant and no-LangChain.

## Scope
- `docs/adr/README.md` with the template (Context / Decision / Consequences / Status)
- Retrospective ADRs for the two already-made AI-stack decisions
- Index linked from `docs/README.md`

## Out of Scope
Rewriting the SRS. Decisions themselves (those are their own tasks).

## Technical Approach
Standard lightweight ADR format, numbered sequentially, one file per decision, status `Proposed` / `Accepted` / `Superseded`.

## Dependencies
None. Receives output from `ARCH-03`, `ARCH-04`, `ARCH-05`, `FW-03`, `FW-05`, `FW-06`.

## Risks
None.

## Security Impact
None directly; makes security decisions durable.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] `docs/adr/` exists with a documented template.
- [ ] At least two retrospective ADRs recorded: vector store (pgvector over Qdrant, citing SRS §456/§624) and RAG framework (explicit code over LangChain).
- [ ] `docs/README.md` links the register.
- [ ] Every ADR states Status and the requirement it traces to.

## Definition of Done
Register merged; the six decision tasks in this backlog produce ADRs into it.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`documentation`, `adr`, `architecture`, `thesis`
