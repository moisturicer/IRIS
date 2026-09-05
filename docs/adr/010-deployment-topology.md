# ADR-010: Five-service topology and interim VPS deployment

## Status

Accepted — 2026-09-01. **Amended by [ADR-014](014-ai-gateway-as-a-service.md)** — 2026-09-02: the topology is six services, adding `ai-gateway`. Every other reduction below stands.

## Context

`docker-compose.yml` and `docker-compose.prod.yml` declare **ten services**. Audited against the working tree:

| Service | State |
|---|---|
| `db` (pgvector/pg16) | Works |
| `redis` | Works |
| `backend` | Cannot import `records/views.py` |
| `frontend` | Runs `npm install && vite dev`, ignoring the multi-stage Nginx Dockerfile that exists |
| `docling` (4 GB limit) | **No code calls it** — `grep DOCLING_API_URL backend/apps/` returns nothing |
| `ai-gateway` | **Build context `./ai` does not exist** |
| `celery-default` | Consumes queue `default`; nothing publishes there |
| `celery-extraction` | Consumes `extraction`; nothing publishes there |
| `celery-embedding` | Consumes `embedding`; nothing publishes there |
| `celery-beat` | No `CELERY_BEAT_SCHEDULE` defined anywhere |

**Neither Compose file builds**, because both reference `./ai`. Five of ten services run no code. No `CELERY_TASK_ROUTES` exists, so every `@shared_task` publishes to Celery's built-in `celery` queue, which no worker consumes.

The SRS service table (§393-405) specifies: nginx, web, celery-worker, celery-worker-rag, celery-beat, docling, db, redis. **It contains no FastAPI gateway.** The single "internal AI gateway" phrase at SRS:1380 denotes a code-level abstraction for reaching the external AI service, not a container — the Compose file materialised a code abstraction into a service.

Production deployment target is unconfirmed: SRS §384 and §456 assume CIT-U on-premise hardware with a 500 GB secondary backup drive, but its existence has not been verified. Meanwhile the course requires a deployed, accessible MVP in **Weeks 1–2**.

Two further deployment defects: `frontend/nginx.conf:2` listens on **8080** (nginx-unprivileged cannot bind 80) while `docker-compose.prod.yml` maps `"80:80"` — so the production frontend accepts no connections; and `collectstatic` runs both at image build (`backend/Dockerfile:53`) and in `entrypoint.sh`, which is referenced by neither Compose file.

## Decision

**Five services:** `db`, `redis`, `backend`, `celery` (one worker, default queue), `frontend`.

Removed: `ai-gateway` (no source, contradicts the SRS service table) · `docling` (deferred, ADR-006) · `celery-extraction`, `celery-embedding`, `celery-beat` (dead queues, no schedule). `CELERY_TASK_ROUTES` is defined so queues and consumers agree.

**Deployment proceeds in two stages.** An **interim VPS** hosts the Weeks 1–2 validation deployment — publicly reachable, HTTPS, **synthetic and already-published data only**. Migration to CIT-U hardware follows if and when confirmed. The interim environment is explicitly a validation environment, not the production target.

**Nothing is exposed publicly until the ADR-009 gate is met**: boot fixed, `/media/` closed, record and document object-level authorization enforced, HTTPS, secrets out of version control, database not publicly bound, basic logging.

Memory falls from a claimed ~8 GB to **~2 GB**.

## Alternatives Considered

**Keep ten services and add task routing.** Rejected. It makes three workers functional but retains four idle processes for two task modules, and keeps a gateway with no source and a 4 GB container nothing calls.

**Wait for CIT-U hardware before deploying.** Rejected. It risks missing the Weeks 1–2 requirement entirely, on an external dependency with an unknown timeline.

**Free-tier hosting.** Rejected for validation. Cold starts and idle sleep make for a poor validation session, and Celery workers fit most free tiers badly.

**Developer laptop behind a tunnel.** Rejected as the primary target — unreliable availability for scheduled validation sessions. Acceptable only as an emergency fallback.

**Managed cloud (AWS ECS/RDS/ElastiCache/ALB).** Rejected. ~$350–450/month for a workload that fits on a $5–12 box; NAT Gateway and ALB alone exceed a VPS. It also conflicts with SRS §456's on-premise data-residency requirement.

## Decision Rationale

Five of ten services run no code — this is not a scaling decision, it is removing scaffolding for a system that was never built. The refactor that introduced the ten-service topology replaced a five-service compose that worked with one that cannot boot; scalability was traded for availability against a workload that has never been observed.

The interim VPS decouples the Weeks 1–2 requirement from an external blocker. Because the artefact is Docker Compose and tenancy is instance-per-tenant (ADR-005), migration to CIT-U hardware is `pg_dump` plus `docker compose up` — hours, not re-architecture. **That portability is what the single-box decision bought.**

The security gate is not negotiable: "publicly accessible" plus twelve unauthorized endpoints plus an unauthenticated `/media/` route means publishing a system where any visitor reads any document.

## Consequences

**Positive.** The stack builds and starts. ~2 GB footprint widens hosting options and cuts cost. Fewer services to secure, monitor and test. Weeks 1–2 requirement met without waiting on CIT-U.

**Negative.** A future genuine need for independent worker scaling means reinstating a split — cheap, once `CELERY_TASK_ROUTES` exists. Two migrations (interim → CIT-U) rather than one.

**Risk.** The interim VPS becomes the permanent home by inertia, leaving NFR-S1 (encryption at rest), NFR-R4 (separate backup drive) and SRS §456's on-premise requirement unmet. Mitigation: the CIT-U hardware question stays an open external blocker with a named owner, and the SRS position is revisited in the Week 3 refactor if hardware is unavailable.

## Revisit when

Measured load demonstrates that one Celery worker or four Gunicorn workers is the bottleneck; or CIT-U hardware is confirmed; or an institution requires on-premise deployment as a contract term.

## MVP Impact

**MVP Blocker, P0.** ~3.5 dev-days across Weeks 1–3 (Compose fix, port fix, interim deployment).

## SaaS Impact

One Compose stack per institution (ADR-005). Onboarding is provisioning. The five-service stack is the unit of deployment, so keeping it small directly reduces per-tenant operational cost — the main weakness of instance-per-tenant.

## Security Impact

Removing five services shrinks the attack surface. The public-exposure gate is the operative control. `SEC` tasks S-01 and S-04 are prerequisites for any public URL.

## Deployment Impact

Defining.

## Research Impact

Enables the Weeks 1–2 validation and the Weeks 11–12 pilot. A separate evaluation instance for ADR-004's comparison is one more stack.

## Related Requirements

NFR-S1 (encryption at rest) · NFR-S3 (HTTPS, 301 redirect) · NFR-R1 (uptime) · NFR-R2 (recovery) · NFR-R4 (backup, RPO) · SRS §384, §393-405, §456.

## Related Tasks

`D-01`…`D-05`, `S-01`, `S-04`, `B-03` (Celery routing). See [`08-deployment.md`](../architecture-tasks/08-deployment.md).
