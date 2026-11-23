# ADR-010: Five-service topology and interim VPS deployment

## Status

Accepted — 2026-09-01. **Amended by [ADR-014](014-ai-gateway-as-a-service.md)** — 2026-09-02: the topology is six services, adding `ai-gateway`. Every other reduction below stands.

**Amendment proposed 2026-11-23 (IR-1275), awaiting approval by Ashlee Sean: production is one AWS EC2 instance running the Compose stack.** See *Amendment — 2026-11-23* at the end. Until it is approved, the Decision below still reads "interim VPS, then CIT-U hardware".

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

## Amendment — 2026-11-23 (IR-1275): production is one AWS EC2 instance

**Status: Proposed**, 2026-11-23. Drafted by an AI agent while writing SRS v2 (IR-1275). **Approver: Ashlee Sean.** Not accepted until she records approval here.

### Context

The Decision above sends production first to an interim VPS, then to CIT-U hardware "if and when confirmed". Neither happened. Production runs on **one AWS EC2 instance**, made by CloudFormation (`deploy/aws/iris-demo.yaml`), with guards in `deploy/aws/iris-guards.yaml` and updates through `scripts/deploy.sh`. No ADR records that choice, so the SRS's constraints had nothing to cite. The topology also grew past six services: `docker-compose.prod.yml` now runs `db`, `redis`, `clamav` (ADR-074), `migrate` (ADR-039), `backend` (ASGI, ADR-017), `ai-gateway` and `ai-runs-worker` (ADR-014, ADR-049), `celery-default`, `celery-extraction`, `celery-embedding`, `celery-beat`, `frontend` and `caddy` (ADR-057), on a `private` network with no outside access and an `egress` network for the containers that call vendors.

### Decision

1. **Production is one AWS EC2 instance running the same Docker Compose stack as development.** Ubuntu 24.04, `m7i-flex.large` (8 GB, with `t3.large` as the fallback where it is not offered) plus a 4 GB swap file, an **encrypted** gp3 EBS volume (64 GiB by default), an Elastic IP, and a security group that opens only 80 and 443 (22 only when asked for, from one address). The shell is AWS Systems Manager Session Manager, not SSH keys.
2. **Guards:** an account budget alert, automatic recovery onto healthy hardware, and an optional daily stop and start schedule.
3. **The server is kept off when it is not in use**, to save cost (approved by the adviser, 2026-11-15). Availability during the pilot is by schedule.
4. **This is still the single-box decision above, on rented hardware.** It uses no AWS managed services (ECS, RDS, ElastiCache, ALB), which the Alternatives above reject on cost. Moving to CIT-U hardware stays `pg_dump` plus `docker compose up`.
5. **The interim VPS stage is retired**, and "CIT-U hardware" becomes a possible later move, not a planned one.

### Consequences

- **Data residency changes.** v1 SRS §456's on-premise requirement is not met. Everything IRIS stores is on the EC2 instance in one AWS region, and paper content reaches Unstructured, Voyage and a language model through OpenRouter, behind the disclosure gate (ADR-052, ADR-054). SRS v2 states this.
- **NFR-S1 (encryption at rest)** is met by EBS encryption, not LUKS.
- **NFR-R4 (backup) is not met:** nothing in `deploy/` sets up a backup, and v1's separate backup drive does not exist. A follow-up should add daily EBS snapshots (AWS Data Lifecycle Manager) or `pg_dump` to S3.
- **NFR-R1 (uptime)** cannot be met while the server is switched off between sessions. It stays the target for an always-on deployment.
- **A deployment wipes container logs**, so collect logs before deploying.

### Open

- The production region is to be confirmed by the person who created the stack (the deploy README's example is Singapore, `ap-southeast-1`).

