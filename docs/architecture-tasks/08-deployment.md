# 08 — Deployment

Five tasks. Two are P0 blockers, and deployment is now a **Week 1** activity because the MVP must be publicly accessible for Weeks 1–2 validation. Governed by [ADR-010](../adr/010-deployment-topology.md).

---

# D-01 · Make the Docker stack buildable

## Objective
Get `docker compose up` to a running state.

## Problem
Both Compose files declare a service built from a directory that does not exist, so the build fails before any container starts.

## Evidence
`docker-compose.yml:103-107` and `docker-compose.prod.yml:91-95` declare `ai-gateway` with `build.context: ./ai` and `env_file: ./ai/.env`. `ls ./ai` → no such directory; `git ls-files | grep '^ai/'` → nothing tracked. `docs/docker_compose_rag_services.md` specifies the context as `./ai-gateway` — a *third* non-existent path.

Five of ten services run no code: `ai-gateway` (no source) · `docling` (4 GB, `grep DOCLING_API_URL backend/apps/` returns nothing) · `celery-extraction`, `celery-embedding` (dead queues) · `celery-beat` (no schedule).

The SRS service table (§393-405) lists nginx, web, celery-worker, celery-worker-rag, celery-beat, docling, db, redis — **no FastAPI gateway**. SRS:1380's "internal AI gateway" denotes a code-level abstraction, not a container.

## Current State
Neither Compose file builds.

## Proposed State
Five services: `db`, `redis`, `backend`, `celery`, `frontend`. Memory ~8 GB → ~2 GB.

## Scope
Remove `ai-gateway` from both files; remove `docling`, `celery-extraction`, `celery-embedding`, `celery-beat`; reconcile the remaining worker with `B-03`'s routing.

## Out of Scope
Building an AI gateway — contradicts the SRS ([ADR-010](../adr/010-deployment-topology.md)). Docling — deferred, requires the `F-03` amendment.

## Technical Approach
Delete the blocks; verify with `docker compose config`, then an actual `up`.

## Dependencies
`B-03`.

## Risks
Low. Coordinate with the author of `refactor/docker-service` so the intent behind the ten-service design is captured before it is reversed.

## Security Impact
Smaller attack surface. `S-01` removes `/media/` from the same nginx config.

## Performance Impact
~2 GB footprint widens hosting options and cuts cost.

## SaaS Impact
The five-service stack is the unit of deployment under [ADR-005](../adr/005-instance-per-tenant.md); keeping it small directly reduces per-tenant operational cost.

## Research/Thesis Impact
Precondition for every validation task.

## MVP Classification
MVP BLOCKER

## Priority
P0 — Week 1

## Complexity
S

## Acceptance Criteria
- [ ] `docker compose -f docker-compose.yml config` exits 0.
- [ ] `docker compose -f docker-compose.prod.yml config` exits 0.
- [ ] `docker compose up` reaches a state where every service is running or healthy.
- [ ] No service references a build context absent from the repository.
- [ ] A fresh clone can `docker compose up` after copying `.env.example`.

## Testing Requirements
`docker compose config` in CI (`F-01`).

## Documentation Requirements
Service list reconciled with the SRS in `F-03`; `docs/docker_compose_rag_services.md` corrected in `DOC-02`.

## Definition of Done
Merged; verified from a clean clone.

---

# D-02 · Fix the production port and serve the built frontend

## Objective
Make the production frontend reachable and stop shipping a dev server as production.

## Problem
Production maps a port nothing listens on, and development ignores the production Dockerfile entirely.

## Evidence
`frontend/Dockerfile` uses `nginxinc/nginx-unprivileged:1.25-alpine`; `frontend/nginx.conf:2` listens on **8080** (the unprivileged image cannot bind 80). `docker-compose.prod.yml:213-214` maps `"80:80"` — nothing listens there.

`docker-compose.yml` runs the frontend as `node:20-alpine` with `npm install && vite dev`, ignoring the multi-stage Nginx Dockerfile that exists. It also sets `DJANGO_SETTINGS_MODULE=config.settings.development` with `DEBUG=True` and `CORS_ALLOW_ALL_ORIGINS`.

`collectstatic` runs twice — `backend/Dockerfile:53` at build with `SECRET_KEY=dummy`, and again in `entrypoint.sh`, which is referenced by neither Compose file.

## Current State
The production frontend accepts no connections.

## Proposed State
Production maps `80:8080` and serves the built SPA; `collectstatic` runs once; the dev/prod distinction is documented.

## Scope
Correct the port mapping; document that `docker-compose.yml` is development-only; resolve the duplicate `collectstatic`; wire or delete `entrypoint.sh`.

## Out of Scope
Hosting choice (`D-03`).

## Technical Approach
Keep the Vite dev server for development — it is the right tool there. Make the README explicit about which file is which.

> **Sequencing warning: `S-01` must land first or simultaneously.** Fixing the port without closing `/media/` publishes every uploaded document.

## Dependencies
**`S-01`.**

## Risks
Medium, entirely because of that ordering.

## Security Impact
Directly gated by `S-01`.

## Performance Impact
A built SPA is static files — far faster than a dev server.

## SaaS Impact
The production profile becomes the per-instance deployment artefact.

## Research/Thesis Impact
Required for the Weeks 1–2 accessible MVP.

## MVP Classification
MVP BLOCKER

## Priority
P0 — Week 1

## Complexity
S

## Acceptance Criteria
- [ ] `curl http://<host>/` against the prod stack returns the SPA with 200.
- [ ] `curl http://<host>/api/v1/...` proxies to the backend.
- [ ] `curl http://<host>/media/<known file>` does **not** return the file.
- [ ] `collectstatic` runs exactly once per deployment.
- [ ] The README states which Compose file is development-only.

## Testing Requirements
Deployment smoke test covering all four HTTP checks.

## Documentation Requirements
Dev/prod distinction in the README and `docs/RUNBOOK.md`.

## Definition of Done
Merged; verified against the interim deployment.

---

# D-03 · Interim VPS deployment

## Objective
Deliver a publicly accessible MVP for Weeks 1–2 validation without waiting on unconfirmed CIT-U hardware.

## Problem
The course requires a deployed, accessible MVP in Weeks 1–2. CIT-U hardware existence, specs and access are unconfirmed, with an unknown lead time.

## Evidence
SRS §384 and §456 assume CIT-U on-premise hardware with a 500 GB secondary backup drive; none of it is verified. Open external blocker #3.

## Current State
No deployment of any kind.

## Proposed State
A small VPS (~$5–12/month) running the five-service stack over HTTPS, with **synthetic and already-published data only**, explicitly a temporary validation environment.

## Scope
Provision the VPS; deploy; TLS with a valid certificate and HTTP→HTTPS 301 (NFR-S3); firewall so only 80/443 are public and Postgres/Redis are not externally bound; seed synthetic data; verify the `S-01` media check.

## Out of Scope
Final production deployment — subject to CIT-U confirmation. Backups (`D-04`).

## Technical Approach
Caddy or nginx for TLS, or a Cloudflare Tunnel. Because the artefact is Docker Compose and tenancy is instance-per-tenant, migration to CIT-U hardware is `pg_dump` plus `docker compose up` — hours, not re-architecture.

## Dependencies
**Hard gate: `B-01`, `B-02`, `D-01`, `D-02`, `S-01`, `S-02`, `S-03`, `S-04`, `SC-01` must all be complete before any public URL.**

## Risks
**The interim becomes permanent by inertia**, leaving NFR-S1, NFR-R4 and SRS §456's on-premise requirement unmet. Mitigation: blocker #3 stays open with a named owner; if hardware is unavailable, `F-03` amends those requirements rather than pretending they hold.

## Security Impact
The gate above is the operative control. Synthetic data only until data-governance and hosting are resolved.

## Performance Impact
Establishes the baseline for `V-13`.

## SaaS Impact
The first execution of the `SA-02` provisioning runbook.

## Research/Thesis Impact
Enables Weeks 1–2 validation — Phase 1 of [ADR-011](../adr/011-evaluation-framework.md).

## MVP Classification
MVP BLOCKER

## Priority
P0 — Weeks 1–2

## Complexity
S

## Acceptance Criteria
- [ ] The MVP is reachable over HTTPS with a valid certificate.
- [ ] HTTP on port 80 redirects with a **301** (NFR-S3).
- [ ] Postgres and Redis are not reachable from the public internet.
- [ ] Only synthetic or already-published records are loaded.
- [ ] `GET /media/<known file>` does not return the file.
- [ ] All nine gate tasks are verified complete before the URL is shared.

## Testing Requirements
Deployment smoke suite run against the live host, including the authorization checks from `T-02`.

## Documentation Requirements
Recorded in `docs/RUNBOOK.md`; the temporary status stated explicitly.

## Definition of Done
Deployed, gate verified, URL shared with validation participants only.

---

# D-04 · Backups and a rehearsed restore

## Objective
Satisfy NFR-R4 — daily backups, RPO ≤ 24 hours, monthly verified restore.

## Problem
No backup of any kind exists.

## Evidence
No backup configuration in either Compose file, no cron, no script. `postgres_data` and `media_files` are unnamed local volumes. SRS §384 specifies a 500 GB secondary drive for daily `pg_dump` and weekly PDF archives.

NFR-R4's validation requires *"restoration drill performed on a staging instance using the most recent backup, verifying all records and uploaded files are intact."*

## Current State
No backups; no restore procedure.

## Proposed State
Nightly `pg_dump` plus a media archive to separate storage, with a documented and **rehearsed** restore.

## Scope
Nightly compressed, timestamped, rotated `pg_dump`; media archive; write to storage separate from the data volume; restore procedure in `docs/RUNBOOK.md`; **perform one restore drill** and record it.

## Out of Scope
Off-site cloud backup — the SRS requires on-premise for production. Point-in-time recovery.

## Technical Approach
Host cron or a small backup container. Never write backups to the same volume as the data.

## Dependencies
`D-03`.

## Risks
**A backup that has never been restored is not a backup.** The drill is the acceptance criterion, not a follow-up.

## Security Impact
Backups contain confidential IP — encrypt at rest (NFR-S1). `SA-04`'s deletion procedure must cover them.

## Performance Impact
Schedule off-peak; `pg_dump` holds no long locks at this size.

## SaaS Impact
Per-institution backups are trivial under [ADR-005](../adr/005-instance-per-tenant.md) — no filtering, no risk of mixing institutions.

## Research/Thesis Impact
Protects pilot and evaluation data. Losing `W-04`'s instrumentation would be unrecoverable.

## MVP Classification
MVP REQUIRED

## Priority
P2 — before Week 11

## Complexity
M

## Acceptance Criteria
- [ ] A `pg_dump` runs daily, producing timestamped files on separate storage.
- [ ] Uploaded media is archived on the same schedule.
- [ ] **A restore drill has been performed** and all records and files verified intact.
- [ ] The restore procedure is documented step by step.
- [ ] Backups are encrypted at rest.
- [ ] Measured RPO ≤ 24 hours.

## Testing Requirements
The restore drill is the test. Repeat before Week 11.

## Documentation Requirements
`docs/RUNBOOK.md`; evidence recorded for `V-14`.

## Definition of Done
Schedule live; drill performed and dated in the ticket.

---

# D-05 · Logging, health checks and error reporting

## Objective
Make it possible to tell what happened when something breaks.

## Problem
No logging configuration, no error reporting, and health checks only on the two services that do not exist.

## Evidence
No `LOGGING` in `settings/base.py`. `sentry-sdk` in `requirements/production.txt`, never initialised. **Health checks exist only on `docling` and `ai-gateway`** — the two non-functional services; `backend`, `frontend` and every Celery service have none, so `depends_on: condition: service_healthy` cannot be used against them and a wedged worker never restarts. No `/healthz` endpoint. Log rotation is configured for four of ten services, prod file only.

Compounds `B-06`: twelve bare `except Exception: pass` discard failures, and there is nowhere for them to go once logged.

## Current State
Failures are invisible.

## Proposed State
Explicit `LOGGING`; a `/healthz` endpoint; health checks on every service; Sentry initialised or the dependency removed.

## Scope
`LOGGING` with sensible levels; `/healthz` returning 200 plus a database check; health checks on `backend`, `celery` (`celery inspect ping`) and `frontend`; initialise or remove Sentry; log rotation on all services in both files.

## Out of Scope
Metrics/Prometheus, log aggregation. Uptime monitoring (`V-13`).

## Technical Approach
Keep it small — stdout logging with rotation is sufficient at one-box scale. Sentry's free tier is ample.

## Dependencies
`B-06`, `D-01`.

## Risks
Low. Ensure logs never contain PII or document content — audit metadata already carries emails.

## Security Impact
Positive: audit-write failures currently vanish. Logs must not themselves become a PII leak.

## Performance Impact
Negligible.

## SaaS Impact
Per-instance logs; no cross-institution log mixing.

## Research/Thesis Impact
Reliability evidence for the technical defence; supports NFR-R1 and NFR-R2 measurement.

## MVP Classification
MVP RECOMMENDED

## Priority
P2

## Complexity
M

## Acceptance Criteria
- [ ] `GET /healthz` returns 200 with a database check, 503 when the database is unreachable.
- [ ] Every Compose service defines a health check.
- [ ] Killing the Celery worker causes a restart within 60 s.
- [ ] An unhandled exception appears in logs with a stack trace and context.
- [ ] Sentry receives a deliberate test exception, or `sentry-sdk` is removed.
- [ ] Logs contain no document content or passwords (spot-checked).

## Testing Requirements
Health checks verified by killing each service in turn.

## Documentation Requirements
Log locations and the health-check contract in `docs/RUNBOOK.md`.

## Definition of Done
Merged; health checks verified; logging documented.
