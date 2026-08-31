# 07 — Deployment Tasks

Six tasks. Two are blockers: the stack cannot build, and the production frontend cannot accept connections.

---

# DEP-01 · Make the Docker stack buildable

## Objective
Get `docker compose up` to a running state.

## Problem
Both Compose files declare a service built from a directory that does not exist, so the build fails before any container starts.

## Current State
`docker-compose.yml:103-107` and `docker-compose.prod.yml:91-95`:

```yaml
ai-gateway:
  build:
    context: ./ai
    dockerfile: Dockerfile
  env_file:
    - ./ai/.env
```

```
$ ls ./ai                     → No such file or directory
$ git ls-files | grep '^ai/'  → (nothing tracked)
```

`docs/docker_compose_rag_services.md` specifies the context as `./ai-gateway` — a *third* non-existent path.

Five of the ten declared services run no code (see `ARCH-02` for the full audit): `ai-gateway` (no source), `docling` (called by nothing), `celery-extraction` / `celery-embedding` (dead queues), `celery-beat` (no schedule).

## Proposed State
Every declared service either builds and runs, or is removed. `docker compose config` exits 0.

## Scope
- Remove `ai-gateway` from both Compose files
- Reconcile the worker services with `BE-03`'s routing
- Remove `celery-beat` until a periodic task exists, or give it a schedule
- Resolve the `docling` question per `FW-03`

## Out of Scope
Building an AI gateway (`FW-05`). The SRS topology reconciliation (`ARCH-02`) — this task is the minimum to make it start.

## Technical Approach
Delete the blocks, then verify with `docker compose config` followed by an actual `up`.

## Dependencies
`BE-03` (queue routing), decisions `FW-03` and `FW-05`.

## Risks
Low. Coordinate with the author of `refactor/docker-service` so the intent behind the 10-service design is captured in `FW-05` before it is reversed.

## Security Impact
Smaller attack surface. Note `SEC-01` removes the `/media/` route from the same nginx config.

## Performance Impact
Memory drops from a claimed ~8 GB to ~2 GB without Docling, ~6 GB with it.

## Deployment Impact
The stack becomes startable — the precondition for every validation task in `10-mvp-validation-tasks.md`.

## Framework Impact
Removes FastAPI, uvicorn and asyncpg from the prospective surface.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `docker compose -f docker-compose.yml config` exits 0.
- [ ] `docker compose -f docker-compose.prod.yml config` exits 0.
- [ ] `docker compose up` reaches a state where every service is running or healthy.
- [ ] No service references a build context absent from the repository.
- [ ] A fresh clone can `docker compose up` after copying `.env.example` to `.env`.

## Definition of Done
Merged; verified from a clean clone; `docker compose config` in CI (`ARCH-01`).

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`deployment`, `docker`, `mvp-blocker`, `bug`

---

# DEP-02 · Fix the production port mapping and serve the built frontend

## Objective
Make the production frontend reachable, and stop running a dev server in the dev stack's place.

## Problem
Two separate defects: production maps a port nothing listens on, and development ignores the production Dockerfile entirely.

## Current State
**(a) Port mismatch.** `frontend/Dockerfile` uses `nginxinc/nginx-unprivileged:1.25-alpine`; `frontend/nginx.conf:2` listens on **8080** (the unprivileged image cannot bind 80). `docker-compose.prod.yml:213-214` maps:

```yaml
ports:
  - "80:80"          # nothing listens on container port 80
```

Should be `"80:8080"`. As written, the production frontend accepts no connections.

**(b) Dev ignores the built image.** `docker-compose.yml` runs the frontend as `image: node:20-alpine` with `command: sh -c "npm install && npm run dev -- --host"`, ignoring the multi-stage Nginx `frontend/Dockerfile` that already exists and produces static files.

**(c) `collectstatic` runs twice.** `backend/Dockerfile:53` runs it at build with `SECRET_KEY=dummy`; `backend/entrypoint.sh` runs it again — and `entrypoint.sh` is referenced by neither Compose file nor the Dockerfile `CMD`. The Dockerfile's own comment flags this: `# TODO: run this during CI/CD, not at image build time`.

> **Sequencing warning:** fixing (a) exposes the unauthenticated `/media/` route (`SEC-01`). **`SEC-01` must land first or simultaneously.**

## Proposed State
Production maps `80:8080` and serves the built SPA; `collectstatic` runs once; the dev/prod distinction is documented.

## Scope
- Correct the prod port mapping
- Decide and document whether dev uses the built image or the Vite dev server (dev server is reasonable *for development*)
- Resolve the duplicate `collectstatic`; wire or delete `entrypoint.sh`
- Add TLS termination guidance for `NFR-S3`

## Out of Scope
Hosting choice (`DEP-06`).

## Technical Approach
Keep the Vite dev server for development — it is the right tool — but make the README explicit that `docker-compose.yml` is development-only, since it also sets `DJANGO_SETTINGS_MODULE=config.settings.development` with `DEBUG=True`.

## Dependencies
**`SEC-01` first or simultaneously.**

## Risks
Medium precisely because of that ordering.

## Security Impact
Fixing the port without `SEC-01` publishes every uploaded document. Sequence carefully.

## Performance Impact
A built SPA is static files — far faster than a dev server.

## Deployment Impact
Production becomes reachable.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `curl http://localhost/` against the prod stack returns the SPA with HTTP 200.
- [ ] `curl http://localhost/api/v1/...` proxies to the backend.
- [ ] `curl http://localhost/media/<known file>` does **not** return the file (`SEC-01`).
- [ ] `collectstatic` runs exactly once per deployment.
- [ ] `entrypoint.sh` is wired into the image or deleted.
- [ ] The README states which Compose file is development-only.

## Definition of Done
Merged; verified against a running prod-profile stack; smoke test added.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`deployment`, `docker`, `nginx`, `mvp-blocker`, `bug`

---

# DEP-03 · Automated backups with a rehearsed restore

## Objective
Satisfy NFR-R4: daily backups, RPO ≤ 24 hours, monthly verified restore.

## Problem
There is no backup of any kind. `postgres_data` and `media_files` are unnamed local Docker volumes with no snapshot, no dump schedule and no documented restore.

## Current State
No backup configuration in either Compose file, no cron, no script. `docs/SRS.md` §384 specifies a *"500 GB secondary drive … target for daily automated pg_dump database backups … and weekly PDF file archive via rsync. Must be a separate physical drive from primary storage."*

NFR-R4's validation is explicit: *"review of the backup schedule configuration confirming daily execution; restoration drill performed on a staging instance using the most recent backup, verifying all records and uploaded files are intact."*

## Proposed State
Nightly `pg_dump` plus a `media_files` archive to a separate drive, with a documented and **rehearsed** restore.

## Scope
- Nightly `pg_dump` (compressed, timestamped, rotated)
- Weekly/nightly media archive via `rsync` or tar
- Write both to a separate physical drive per SRS §384
- A `docs/RUNBOOK.md` restore procedure
- **Perform one restore drill** and record the result

## Out of Scope
Off-site or cloud backup (the SRS requires on-premise); point-in-time recovery.

## Technical Approach
A host cron job, or a small backup container. Do not put backups on the same volume as the data.

## Dependencies
`DEP-01` (stack must run).

## Risks
**The main risk is a backup that has never been restored.** The drill is not optional — it is the acceptance criterion.

## Security Impact
Backups contain confidential IP disclosures and must be encrypted at rest per NFR-S1.

## Performance Impact
Schedule off-peak; `pg_dump` holds no long locks at this size.

## Deployment Impact
Requires the secondary drive from SRS §384.

## Framework Impact
None.

## MVP Classification
**MVP Required** — NFR-R4 is an explicit, validated requirement

## Acceptance Criteria
- [ ] A `pg_dump` runs daily and produces a timestamped file on the secondary drive.
- [ ] Uploaded media is archived on the same schedule.
- [ ] **A restore drill has been performed on a staging instance** and all records and files verified intact.
- [ ] The restore procedure is documented step by step in `docs/RUNBOOK.md`.
- [ ] Backup files are encrypted at rest (NFR-S1).
- [ ] Measured RPO ≤ 24 hours.

## Definition of Done
Schedule live; drill performed and dated in the ticket; runbook merged; evidence recorded for `VAL-17`.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`deployment`, `backup`, `reliability`, `nfr-r4`, `mvp-required`

---

# DEP-04 · Observability: logging, health checks and error reporting

## Objective
Make it possible to tell what happened when something breaks.

## Problem
No logging configuration, no error reporting, and health checks only on the two services that do not exist.

## Current State
- **No `LOGGING` config** in `settings/base.py`, so Django defaults apply and Celery logs go to container stdout only
- `sentry-sdk` is in `requirements/production.txt` and **never initialised**
- **Health checks exist only on `docling` and `ai-gateway`** — the two non-functional services. `backend`, `frontend` and every Celery service have none, so `depends_on: condition: service_healthy` cannot be used against them and a wedged worker never restarts
- Log rotation (10 MB × 3) is configured for four of ten services in the prod file only
- No `/healthz` endpoint exists in Django

This compounds `BE-07`: twelve bare `except Exception: pass` blocks discard failures, and there is nowhere for them to go even once logged.

## Proposed State
Explicit `LOGGING`; a `/healthz` endpoint; health checks on every service; Sentry initialised or the dependency removed.

## Scope
- `LOGGING` configuration with sensible levels and structured output
- `/healthz` returning 200 plus a database connectivity check
- Health checks on `backend` (hit `/healthz`), `celery` (`celery inspect ping`), `frontend`
- Initialise Sentry with the DSN from environment, or remove `sentry-sdk`
- Log rotation on all services in both files

## Out of Scope
Metrics/Prometheus, log aggregation, uptime monitoring (`VAL-16` covers the NFR-R1 measurement).

## Technical Approach
Keep it small: stdout logging with rotation is sufficient at one-box scale. Sentry's free tier is ample for a thesis project.

## Dependencies
`BE-07` (logging must have somewhere to go). `DEP-01`.

## Risks
Low. Ensure logs never contain PII or document content — audit metadata already carries emails.

## Security Impact
Positive: `SEC-07`'s audit-write failures currently vanish. Logs themselves must not become a PII leak.

## Performance Impact
Negligible.

## Deployment Impact
Health checks enable orderly startup and automatic restart of wedged services.

## Framework Impact
Possibly removes `sentry-sdk`.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] `GET /healthz` returns 200 with a database check, and 503 when the database is unreachable.
- [ ] Every Compose service defines a health check.
- [ ] Killing the Celery worker causes its health check to fail and the container to restart.
- [ ] An unhandled exception appears in logs with a stack trace and correlation context.
- [ ] Sentry receives an error from a deliberate test exception, **or** `sentry-sdk` is removed.
- [ ] Logs contain no document content or passwords (spot-checked).

## Definition of Done
Merged; health checks verified by killing each service; logging documented in the runbook.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`deployment`, `observability`, `logging`, `reliability`, `nfr-r1`

---

# DEP-05 · Remove hardcoded credentials from Compose

## Objective
Stop shipping working database credentials in version control.

## Problem
The same password appears in three tracked files and as a settings default.

## Current State
`docker-compose.yml` and `docker-compose.prod.yml` both hardcode:

```yaml
environment:
  POSTGRES_DB: iris_db
  POSTGRES_USER: iris_user
  POSTGRES_PASSWORD: iris_password
```

`settings/base.py:79-82` defaults `DB_PASSWORD` to `iris_password`. `.env.example` ships `SECRET_KEY=change-me-in-production`.

`SECRET_KEY` has no default, which is correct — it fails loudly. Download tokens are signed with the same `SECRET_KEY` as JWTs (`records/download_tokens.py`), so a rotation invalidates both — worth documenting, or use a separate key.

## Proposed State
All credentials from `.env`; no working secret in any tracked file.

## Scope
- Move DB credentials to `.env` in both Compose files
- Remove the `iris_password` default from settings
- Ensure `.env` is gitignored (it is) and `.env.example` carries only placeholders
- Document secret generation in the setup guide

## Out of Scope
A secrets manager — disproportionate for a one-box deployment.

## Technical Approach
`${DB_PASSWORD:?err}` in Compose so a missing value fails loudly rather than silently defaulting.

## Dependencies
Overlaps `SEC-09` — do them together.

## Risks
Low. A missing `.env` will now fail the stack — which is the point, but document it.

## Security Impact
Removes credentials from version control and from the repository's history going forward.

## Performance Impact
None.

## Deployment Impact
Deployers must generate secrets.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `grep -rn "iris_password" docker-compose*.yml backend/config/` returns no matches.
- [ ] Starting the stack without `DB_PASSWORD` set fails with a clear error.
- [ ] `.env.example` contains no value usable as a real secret.
- [ ] Setup instructions include generating a `SECRET_KEY`.
- [ ] Existing deployments have had credentials rotated.

## Definition of Done
Merged; clean-clone setup verified; credentials rotated on any live instance.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`deployment`, `security`, `secrets`, `mvp-required`

---

# DEP-06 · Choose and document the hosting target

## Objective
Pick where IRIS runs, and record why — covering thesis MVP, low-budget deployment and a path to small production.

## Problem
No hosting decision is recorded. The referenced AWS roadmap document does not exist, and the memory budget in the existing review assumed a service that was never built.

## Current State
`docs/backend_frontend_architecture_review.md` §6 evaluates options and recommends on-premise behind a Cloudflare Tunnel — sound reasoning, but its memory table budgets 1 GB for the non-existent `ai-gateway`. With `DEP-01` and the Docling decision, the real requirement is **~2 GB without Docling, ~6 GB with it**.

SRS §384 requires on-premise CIT-U hardware with a 500 GB secondary backup drive; §456 requires the database *"strictly on-premise on CIT-U server hardware in compliance with RA 10173."*

**The SRS therefore largely settles this: on-premise is a requirement, not a preference.** Cloud options are only relevant as a fallback and would need an SRS amendment.

## Proposed State
A recorded decision naming the target, its specification, and the fallback.

## Scope
- Confirm on-premise hardware availability against SRS §384
- Size the box against the post-`DEP-01` footprint and the `FW-03` Docling decision
- Cloudflare Tunnel or equivalent for public HTTPS without inbound firewall changes (`NFR-S3`)
- Record as an ADR

## Out of Scope
Procurement. AWS design — explicitly not justified (~$350–450/mo for a workload that fits on one box; NAT Gateway and ALB alone exceed a VPS).

## Technical Approach
One box, Docker Compose, on campus. A Cloudflare Tunnel gives a public HTTPS URL with no static IP, no port forwarding and no IT ticket — and keeps research data on university hardware, which independently satisfies the RA 10173 constraint.

Fallback: a budget VPS (~$5–12/mo). The deployment artefact is identical either way, which is the point.

## Dependencies
`DEP-01` (footprint), `FW-03` (Docling ±4 GB).

## Risks
Campus power and network reliability sit against NFR-R1's 99.5% uptime. The VPS fallback should be a documented, tested path, not an idea.

## Security Impact
On-premise satisfies the SRS's data-residency requirement. A tunnel avoids exposing inbound ports.

## Performance Impact
Determines headroom for `NFR-P1` (100 concurrent sessions).

## Deployment Impact
Defining.

## Framework Impact
None.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] An ADR records the target, its specification and the fallback.
- [ ] The chosen host meets the post-`DEP-01` memory requirement with headroom.
- [ ] Public HTTPS works with a valid certificate (`NFR-S3`).
- [ ] HTTP on port 80 redirects to HTTPS with a 301 (`NFR-S3` validation).
- [ ] The SRS §384 backup drive is present and used by `DEP-03`.
- [ ] Estimated monthly operating cost is recorded for `VAL-18`.

## Definition of Done
ADR merged; a deployment reachable over HTTPS; cost recorded.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`deployment`, `hosting`, `adr`, `nfr-s3`, `nfr-r1`
