# ADR-071: Whether to run more than one backend container behind nginx

## Status

**Proposed** — 2026-11-15 ([IR-1145](https://citiris.atlassian.net/browse/IR-1145)). Drafted by an AI agent (Claude Code) at Ashlee Sean's request. **Not decided.** AI does not make architecture decisions (CLAUDE.md), so this ADR sets out the options and a recommendation. The Decision section stays empty until a named person accepts one option or rejects them all. Nothing in Compose changes before then.

**Depends on [IR-200](https://citiris.atlassian.net/browse/IR-200), which is not merged yet** (PR [#787](https://github.com/moisturicer/IRIS/pull/787)). Where this ADR says what nginx does "after IR-200", it describes that PR, not `main`.

## Context

**Why this comes up now.** On `main`, `frontend/nginx.conf` proxies to a literal `http://backend:8000`. nginx looks `backend` up once, when it loads, and keeps that address. A second backend container would never get a request, and recreating the one that exists breaks the API until nginx restarts. IR-200 changes that. It gives nginx Docker's resolver and a variable upstream, so nginx reuses an answer for at most 10 seconds and then looks the name up again. When several containers answer to `backend`, nginx takes turns between them. PR #787 adds `scripts/check_nginx_backend_resolution.sh`, which proves both against a real nginx in CI. Once it merges, load balancing between backend containers is one Compose setting away, and the question becomes whether it is worth having.

**The topology today** (`docker-compose.prod.yml` on `main`, 2026-11-15). Everything runs on one host:

| Piece | What it is |
|---|---|
| Host | One EC2 instance, `m7i-flex.large` by default (2 vCPU, 8 GB; `deploy/aws/iris-demo.yaml`). IR-1015's optional daily stop and start can switch it off when nobody needs it |
| Edge | `caddy` (TLS, ADR-057; 0.5 CPU / 256 MB) → nginx in `frontend` (the built app, routing, `/django-admin/` allowlist; 0.5 CPU / 512 MB) |
| `backend` | **One container**: gunicorn with 4 Uvicorn (ASGI) workers, ADR-017, no `--preload`. Limited to 2 CPUs and 2 GB. No Compose healthcheck |
| `ai-gateway` | One container, 1 GB limit |
| `ai-runs-worker` | 5 replicas, 1 GB each. They take work from a queue in PostgreSQL, so they share load with no load balancer |
| Celery | `celery-default`, `celery-extraction` (concurrency 2), `celery-embedding` (concurrency 4) and `celery-beat`, with no memory limits |
| `migrate` | A one-shot service that runs before the backend starts (ADR-039), so extra backend containers would not race each other on migrations |
| State | PostgreSQL (`max_connections=300`), Redis, and the `media_files` volume (already mounted by the backend and the Celery workers) |

**What is already shared across processes.** Checked in the settings on `main`:
- Django's cache is Redis (`config/settings/base.py`), so DRF throttle counts are shared.
- Sign-in is JWT, so no server-side session lives in a backend process.
- django-axes keeps lockout state in the database. It is switched off by default today (`AXES_ENABLED=False`, IR-865), and open PR #651 would require it in production.
- `CONN_MAX_AGE` is not set, so each request opens and closes its own database connection.

**What is not shared.** Each process keeps its own:
- **Circuit breakers.** `apps/ai/resilience/llm.py` holds them in a module-level dict behind a `threading.Lock`. They are already split across the 4 gunicorn workers, so more containers split them further but don't change their kind.
- **Long-lived responses.** The Ask IRIS journal replay (`apps/ai/streaming.py`, an event stream) and the audit CSV export (`apps/audit/views.py`, a `StreamingHttpResponse`) stay on the one process that started them. Restarting that container cuts them off. The event stream can be resumed from its cursor; the CSV download must be started again.

None of this has been tested with two backend containers against the real app.

**What a second container would and wouldn't buy on this host:**
- **Capacity: little.** The backend is already allowed both of the host's CPUs. A second container competes for the same two cores and 8 GB, shared with PostgreSQL, the gateway, five runs workers and four Celery services.
- **Crash isolation: some.** If one container dies, the other keeps answering while Docker restarts it (`restart: unless-stopped`). With one container, the API is down for those seconds. Inside one container, gunicorn already replaces a single crashed worker.
- **Zero-downtime deploys: not by itself.** `scripts/deploy.sh` runs `docker compose up -d --build`, which recreates every replica at about the same time. A rolling update needs a script that replaces one container at a time and waits for it to be healthy, and the backend has no healthcheck yet.

## Decision

**None yet.** To be filled in by the person who accepts an option.

## Alternatives Considered

### A. Keep one backend container

Change nothing. If the backend needs more throughput on this host, raise gunicorn's `--workers`. More than 4 would also need the 2 GB memory limit raised, because IR-1012 sized it for 4.
- **Gains:** no new moving parts; nothing for teammates to learn or debug; once IR-200 merges, recreating the backend no longer breaks the API, which was the outage the frontend-restart workaround covered.
- **Costs:** a crashed backend container still takes the API down until Docker restarts it; deploys still have a short API gap.

### B. Two backend replicas on the same host

`deploy.replicas: 2` on `backend`, each with 2 workers so the total stays at 4, and a Compose healthcheck so `deploy.sh` can tell when each is ready.
- **Gains:** one container can crash or restart without the API going down; it uses the nginx round-robin IR-200 adds, which is groundwork for option C.
- **Costs:**
  - **Memory:** a little more than today, one extra gunicorn master. Without `--preload` each worker already loads the whole app, so 2 × 2 workers cost about what 1 × 4 do.
  - **Limits:** each replica gets its own `cpus`/`memory` limit, so the limits must be halved, or the backend's allowed share of the host doubles.
  - **Logs:** they split across two containers, so diagnosing one request means reading both (as in IR-1049's log pull).
  - **Long-lived responses:** a stream or CSV export is cut whenever its container restarts.
  - **Capacity:** no gain, because both share the same two CPUs.
  - **Deploys:** they still recreate both at once unless `deploy.sh` changes too.

### C. Several hosts behind a cloud load balancer

An AWS Application Load Balancer in front of two or more instances.
- **Gains:** real capacity and real failover, including a whole host failing; rolling deploys become natural.
- **Costs:** ADR-010 §Alternatives Considered already rejected managed cloud with an ALB: about $350–450 a month against a workload that fits one small server. It also noted a conflict with on-premise data residency. Beyond the bill:
  - PostgreSQL, Redis and the media volume would have to move off the single host.
  - A load balancer bills by the hour even when the instances are off.
  - It is much more for a four-person team to operate before the thesis is done.

## Recommendation

**Option A.** Keep one backend container. IR-200's resolver change fixes a real outage at no cost, so it should merge regardless. It leaves B and C open for later.

## Decision Rationale

On a 2-vCPU host, a second backend container adds a failure-isolation benefit measured in seconds of API time, and costs halved limits, split logs and a deploy script change. The workload has not been measured as limited by the backend. Until it is, A keeps the system the team already knows how to debug.

## Revisit when

- the backend's CPU or memory, measured on the server under the pilot's load, is the limit, and the host has room to spare; or
- a deploy's API gap, or a backend crash, is seen to interrupt real users; or
- IRIS moves to more than one host. That would be its own ADR, superseding parts of ADR-010.

## Consequences

- **If A is accepted:** no code change. `deploy.sh`, as changed by IR-200, restarts `frontend` only when the API fails and says so, so a deploy's output shows whether IR-200 held on the server.
- **If B is accepted:** a follow-up ticket adds the replicas with halved limits, a healthcheck and a one-at-a-time update in `deploy.sh`. It is tested on the server, with logs collected first, because a deploy deletes container logs.
- **If C is accepted:** it needs its own ADR for the data layer before any load balancer is created.

## MVP Impact

None under A. B or C would take deployment time from the validation window.

## SaaS Impact

ADR-005 runs one instance per tenant. Replicas scale one tenant's instance; they don't change tenancy.

## Security Impact

None under A. Under B, nginx's `/django-admin/` allowlist and Caddy's forwarded-address handling are unchanged, because both sit in front of every replica alike. Under C, the load balancer becomes the TLS edge and ADR-057 would need amending.

## Deployment Impact

As in each option above. Every option keeps `migrate` as the one-shot service ADR-039 made it.

## Research Impact

None. The thesis workflow and the RAG pipeline do not depend on how many backend containers serve them.

## Related Requirements

None by FR- id. ASVS and the open risks in `docs/security/SECURITY.md` §11 are unaffected.

## Related Tasks

- [IR-200](https://citiris.atlassian.net/browse/IR-200): nginx looks the backend up per request (PR #787).
- [IR-1145](https://citiris.atlassian.net/browse/IR-1145): this ADR.
- [IR-1012](https://citiris.atlassian.net/browse/IR-1012): sized the current backend limits.
- [IR-1015](https://citiris.atlassian.net/browse/IR-1015): cost guards and the optional daily stop and start.
