# ADR-071: Whether to run more than one backend container behind nginx

## Status

**Proposed** — 2026-11-15 ([IR-1145](https://citiris.atlassian.net/browse/IR-1145)), drafted by Claude Code at Ashlee Sean's request. Not accepted. AI does not make architecture decisions (CLAUDE.md), so this records the options and a recommendation for a named person to accept or reject. Nothing in Compose changes until then.

Depends on [IR-200](https://citiris.atlassian.net/browse/IR-200), which is what makes any replica option possible.

## Context

**Why this comes up now.** Until IR-200, `frontend/nginx.conf` proxied to a literal `http://backend:8000`. nginx looked `backend` up once, when it loaded, and kept that address. A second backend container would never have received a request, and recreating the one that existed broke the API until nginx restarted. IR-200 gives nginx Docker's resolver and a variable upstream. nginx now asks Docker's DNS again every 10 seconds, and when several containers answer to `backend` it takes turns between them. `scripts/check_nginx_backend_resolution.sh` proves both in CI. So load balancing between backend containers is now one Compose setting away, and the question is whether it is worth having.

**The topology today** (`docker-compose.prod.yml` on `main`, 2026-11-15):

| Piece | What it is |
|---|---|
| Host | One EC2 instance, `m7i-flex.large` by default (2 vCPU, 8 GB; `deploy/aws/iris-demo.yaml`). Switched off when not needed to save cost |
| Edge | Caddy (TLS, ADR-057) → nginx in `frontend` (static app, routing, `/django-admin/` allowlist) |
| `backend` | **One container**: gunicorn with 4 Uvicorn (ASGI) workers, ADR-017. Limited to 2 CPUs and 2 GB |
| `ai-runs-worker` | 5 replicas. They take work from a queue in PostgreSQL, so they share load with no load balancer |
| `migrate` | A one-shot service that runs before the backend starts (ADR-039), so extra backend containers would not race each other on migrations |
| State | PostgreSQL (`max_connections=300`), Redis (Django cache, DRF throttles, Celery broker), the `media_files` volume. JWT sign-in, so no server-side session lives in a backend process |

**What already works across containers**, checked in the settings: Django's cache is Redis (`config/settings/base.py`), so throttle counts are shared; sign-in lockout (django-axes) is stored in the database; the media volume is a named volume that several containers on one host can mount. Nothing found keeps request state inside one backend process. That is a reading of the settings, not a test with two backends against the real app.

**What a second container would and wouldn't buy on this host:**

- **Capacity: little.** The backend is already allowed both of the host's CPUs. A second container competes for the same two cores and the same 8 GB, shared with PostgreSQL, Redis, five runs workers and the Celery workers. Four more gunicorn workers in the one container would do the same job with less memory.
- **Crash isolation: some.** If one container dies, the other keeps answering while Docker restarts it (`restart: unless-stopped`). With one container, the API is down for those seconds. Inside one container, gunicorn already restarts a single crashed worker.
- **Zero-downtime deploys: not by itself.** `scripts/deploy.sh` runs `docker compose up -d --build`, which recreates every replica at about the same time. A rolling update needs a script that replaces one container at a time and waits for it to be healthy. The backend has no Compose healthcheck yet.

## Options

### A. Keep one backend container (recommended for now)

Change nothing. If the backend needs more throughput on this host, raise gunicorn's `--workers` in the one container.

- **Gains:** no new moving parts; memory stays as IR-1012 sized it; nothing for teammates to learn or debug; IR-200 already removed the outage the restart workaround covered.
- **Costs:** a crashed backend container still takes the API down until Docker restarts it; deploys still have a short API gap.

### B. Two backend replicas on the same host

`deploy.replicas: 2` on `backend`, each with 2 workers so the total stays at 4, and a Compose healthcheck so `deploy.sh` can tell when each is ready.

- **Gains:** one container can crash or restart without the API going down; it exercises the nginx round-robin IR-200 enabled, which is the groundwork for option C.
- **Costs:** about a second Django's worth of memory (each container loads the full app) on an 8 GB host that is already shared; more database connections held by the backend; logs split across two containers, so diagnosing a request means reading both (as with the IR-1049 log pull); no capacity gain, because both share the same two CPUs; a deploy still recreates both at once unless `deploy.sh` also changes.

### C. Several hosts behind a cloud load balancer

An AWS Application Load Balancer in front of two or more instances.

- **Gains:** real capacity and real failover, including a whole host failing; rolling deploys become natural.
- **Costs:** the database, Redis and the media volume would have to move off the single host (managed services or a shared filesystem), which is a different deployment from ADR-010's single VPS and ADR-005's instance per tenant; a load balancer bills by the hour even when traffic is zero, which works against keeping the server off to save cost; much more for a four-person team to operate before the thesis is done.

## Decision (proposed)

**Option A.** Keep one backend container. IR-200's resolver change stays, because it fixes a real outage and costs nothing, and it leaves options B and C open.

## Revisit when

- The backend's CPU or memory, measured on the server under the pilot's load, is the limit and the host has room to spare; or
- a deploy's API gap, or a backend crash, is seen to interrupt real users; or
- IRIS moves to more than one host, which would be its own ADR, superseding parts of ADR-010.

## Consequences

- If A is accepted: no code change. `deploy.sh` keeps its frontend restart as a fallback until a server deploy shows IR-200 made it unnecessary.
- If B is accepted instead: a follow-up ticket adds the replicas, the healthcheck and a one-at-a-time update in `deploy.sh`, tested on the server with logs collected first (deploys delete container logs).
- If C is accepted instead: it needs its own ADR for the data layer before any load balancer is created.
