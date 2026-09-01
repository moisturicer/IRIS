# 07 — Deployment Architecture

**Subject:** `docker-compose.yml`, `docker-compose.prod.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `backend/entrypoint.sh`, and the hosting question.

**Target profiles, per the brief:** (1) thesis MVP, (2) low-budget deployment, (3) small production system, (4) future business product.

---

## Headline

**Neither compose file can start.** Both declare an `ai-gateway` service built from `./ai` — a directory that is not in the repository — so `docker compose up` fails at build resolution before any container runs.

```
$ ls ./ai                     → No such file or directory
$ git ls-files | grep '^ai/'  → (nothing tracked)
```

`docker-compose.yml:103-107` and `docker-compose.prod.yml:91-95`:

```yaml
ai-gateway:
  build:
    context: ./ai
    dockerfile: Dockerfile
  env_file:
    - ./ai/.env
```

This is a **MVP BLOCKER**, and a one-line CI check (`docker compose config`) prevents it recurring.

---

## Service-by-service audit

`docker-compose.yml` declares ten services. What each actually does today:

| # | Service | Declared purpose | Reality | Verdict |
|---|---|---|---|---|
| 1 | `db` | Postgres 16 + pgvector | Works. pgvector extension unused by the app (`RecordEmbedding` is a `BinaryField`) | **KEEP** |
| 2 | `redis` | Celery broker + cache | Works. Used as broker; not used as a cache anywhere | **KEEP** |
| 3 | `backend` | Django API | Cannot import `records/views.py` (BLOCK-1) | **KEEP**, fix |
| 4 | `frontend` | Vite dev server | `node:20-alpine` running `npm install && vite dev`, ignoring the multi-stage Nginx Dockerfile that exists | **KEEP**, fix for prod |
| 5 | `docling` | PDF extraction API, **4 GB limit** | **No code calls it.** `documents/tasks.py` never reads `DOCLING_API_URL` | **REMOVE** |
| 6 | `ai-gateway` | FastAPI RAG service, 1 GB | **Build context does not exist** | **REMOVE** |
| 7 | `celery-default` | `-Q default` | No task publishes to `default` | **MERGE** → one worker |
| 8 | `celery-extraction` | `-Q extraction` | No task publishes to `extraction` | **REMOVE** |
| 9 | `celery-embedding` | `-Q embedding` | No task publishes to `embedding` | **REMOVE** |
| 10 | `celery-beat` | Nightly `embed_all_records` | **No `CELERY_BEAT_SCHEDULE` defined anywhere** | **REMOVE** |

**Five of ten services run no code.** Two cannot build.

---

## DEP-1 · Collapse to five services

**Problem.** Ten services, five functional, two unbuildable.

**Evidence.** Above, plus: `grep -rn "task_routes|beat_schedule|queue" backend/config/ backend/apps/*/tasks.py` → **no matches**. Every `@shared_task` publishes to Celery's built-in default queue, named `celery`, which no worker consumes.

**Recommendation.** `db`, `redis`, `backend`, `celery` (one worker, no `-Q`), `frontend`.

```yaml
# the MVP shape
db:       pgvector/pgvector:pg16
redis:    redis:7-alpine
backend:  build ./backend        # gunicorn in prod, runserver in dev
celery:   build ./backend        # celery -A config worker -l info
frontend: build ./frontend       # multi-stage → nginx, in prod
```

Memory falls from a claimed ~8 GB to roughly **2 GB** — which changes what this can be hosted on.

| Component | Before | After |
|---|---|---|
| `docling` | 4 GB | — |
| `ai-gateway` | 1 GB | — |
| Postgres + Redis | ~1.2 GB | ~1.2 GB |
| Backend + workers | ~2 GB (5 processes) | ~0.7 GB (2 processes) |
| Frontend | negligible (static) | negligible |
| **Total** | **~8 GB** | **~2 GB** |

**Alternatives.** Keep the split and add `CELERY_TASK_ROUTES` — makes the workers functional but keeps four idle processes for two task modules, one of which cannot import its dependencies. Rejected for MVP; revisit when measured throughput demands it.

- **Complexity:** Low — deleting compose blocks
- **Risk:** Low — removes only non-functioning services
- **Dependencies:** None; resolves BLOCK-3
- **MVP:** **MVP BLOCKER**
- **Framework impact:** Drops FastAPI, uvicorn, asyncpg, Docling from the future surface
- **Testing implications:** `docker compose config` becomes meaningful in CI.

---

## DEP-2 · Production deployment defects

Four independent problems that would each break a real deployment.

### (a) Port mismatch — the frontend is unreachable

`frontend/Dockerfile` uses `nginxinc/nginx-unprivileged:1.25-alpine` and `frontend/nginx.conf:2` listens on **8080** (the unprivileged image cannot bind 80). `docker-compose.prod.yml:213-214` maps:

```yaml
ports:
  - "80:80"          # nothing listens on container port 80
```

Should be `"80:8080"`. As written, the production frontend accepts no connections.

### (b) Unauthenticated media exposure

`frontend/nginx.conf:52-56` serves user uploads as static files:

```nginx
location /media/ {
    alias /usr/share/nginx/html/media/;
    expires 30d;
}
```

with `docker-compose.prod.yml:210` mounting `media_files:/usr/share/nginx/html/media:ro`.

**Every uploaded thesis PDF is reachable at `https://host/media/documents/<filename>` with no authentication**, bypassing every permission check in `documents/views.py`. `upload_to="documents/"` derives filenames from the uploaded name, so they are guessable. This is **SEC-12** and is arguably the most severe finding in the review — currently masked only by defect (a).

**Fix:** delete the `/media/` location. Serve uploads through the authenticated Django endpoints that already exist, or via nginx `X-Accel-Redirect` with Django authorizing.

### (c) The dev compose runs development settings

`docker-compose.yml` sets `DJANGO_SETTINGS_MODULE=config.settings.development` and `command: python manage.py runserver`. That is correct *for development* — but `development.py` sets `DEBUG=True` and `CORS_ALLOW_ALL_ORIGINS=True`, and `runserver` is not a production server. Any deployment that reaches for the default compose file gets a debug server with tracebacks enabled. Make the distinction explicit in the README.

### (d) `collectstatic` runs at image build with a dummy key

`backend/Dockerfile:53`:

```dockerfile
RUN SECRET_KEY=dummy python manage.py collectstatic --noinput
```

`STATICFILES_STORAGE` is WhiteNoise's `CompressedManifestStaticFilesStorage`, so this is needed at build time — but it imports Django with `DJANGO_SETTINGS_MODULE=config.settings.production`, which will fail the moment `ALLOWED_HOSTS` or another setting is made strict. `entrypoint.sh` also runs `collectstatic`, so it happens twice and `entrypoint.sh` is not referenced by either compose file or the Dockerfile `CMD`. The Dockerfile's own comment flags this: `# TODO: run this during CI/CD, not at image build time`.

- **Complexity:** Low (all four) · **Risk:** Low
- **MVP:** **MVP BLOCKER** (a, b) · **MVP REQUIRED** (c, d)
- **Testing implications:** A deployment smoke test — `curl` the frontend, assert 200; `curl /media/<known file>`, assert not 200.

---

## DEP-3 · Missing operational fundamentals

**Problem.** Four properties a "small production system" needs, none present.

| Concern | State | Minimum viable answer |
|---|---|---|
| **Backups** | **None.** No `pg_dump` schedule, no volume snapshot, no documented restore. `postgres_data` and `media_files` are unnamed local volumes | A nightly `pg_dump` + a `media_files` tar to off-box storage, and **a documented restore that has been performed once**. An untested backup is not a backup |
| **Observability** | **None.** `sentry-sdk` is in `production.txt` and never initialised. No `LOGGING` config, so Django's defaults apply and Celery logs go to container stdout only. Log rotation is configured in prod compose (10 MB × 3) but only for four of ten services | Configure `LOGGING` explicitly; initialise Sentry (free tier is ample) or remove the dependency; add `/healthz` to Django — note only `docling` and `ai-gateway`, the two non-existent services, have healthchecks |
| **Failure recovery** | Partial. `restart: unless-stopped` and `depends_on: condition: service_healthy` are set — but `backend`, `frontend` and all Celery services have **no healthcheck**, so `service_healthy` cannot be used against them and a wedged worker restarts never | Add a healthcheck to `backend` (hit `/healthz`) and to the Celery worker (`celery inspect ping`) |
| **Secrets** | Hardcoded. `POSTGRES_PASSWORD: iris_password` in both compose files; `DB_PASSWORD` defaults to the same in `settings/base.py:81`; `.env.example` ships `SECRET_KEY=change-me-in-production` | Move DB credentials to `.env`; generate a real `SECRET_KEY`; ensure `.env` is gitignored (it is) |

- **Complexity:** Low (backups, logging, healthchecks) · **Risk:** Low
- **MVP:** **MVP REQUIRED** (backups, secrets) · **MVP RECOMMENDED** (observability, healthchecks)
- **Testing implications:** A restore drill is the only test that matters for backups.

---

## DEP-4 · Scaling and concurrency

**Current posture.** `gunicorn --workers 4 --timeout 120` (sync workers). Four concurrent requests per backend container; a fifth waits.

**Assessment against the four target profiles:**

| Profile | Verdict |
|---|---|
| **Thesis MVP** | Ample. Four sync workers serve a demo and a defence comfortably |
| **Low-budget deployment** | Ample for one university office — tens of users, single-digit concurrent requests |
| **Small production system** | Adequate for CRUD. **Inadequate the moment a synchronous LLM call is added**: a 3–10 s provider round-trip occupies a sync worker for its whole duration, so four concurrent AI questions block all other traffic |
| **Future business product** | Needs horizontal scaling, a load balancer, and separated read paths — but that is a different document |

**Recommendation.** When AI endpoints ship, change one line: `--worker-class gthread --threads 8`. That serves ~32 concurrent I/O-bound requests per container instead of 4, at almost no memory cost, because a provider call is a blocked socket rather than CPU work.

This is the cheap answer to the problem `docs/docker_compose_rag_services.md` uses to justify a separate FastAPI gateway. Its "~15 GB for 100 concurrent RAG users" figure assumes 100 *sync* worker processes; `gthread` reaches the same concurrency in a fraction of the memory, and Django's ASGI stack (`config/asgi.py` already exists) goes further still. See [04](04-ai-rag-architecture.md).

- **Complexity:** Trivial · **Risk:** Low — verify no thread-unsafe module-level state
- **Dependencies:** Only relevant once AI endpoints exist
- **MVP:** **POST-MVP**
- **Framework impact:** None — a Gunicorn flag

---

## DEP-5 · Hosting

The prior review's analysis here is sound and this review endorses it, with one correction: its memory table budgets 1 GB for an `ai-gateway` that does not exist. Removing that and Docling takes the requirement from ~8 GB to ~2 GB, which materially widens the options.

| Option | Shape | ~Monthly | Trade-off |
|---|---|---|---|
| **On-prem + Cloudflare Tunnel** | A lab PC or mini-PC on campus, exposed via `cloudflared` | **$0** | **Recommended.** No static IP, no port forwarding, no IT ticket. Research data never leaves campus — which independently answers the IP-confidentiality question the whole system exists to serve. You own uptime, backups and power |
| Oracle Cloud Always Free | One Ampere ARM instance (up to 4 cores / 24 GB) | **$0** | Genuinely free indefinitely and far larger than needed. Free ARM capacity is often unavailable per-region, and every image must be ARM64 — verify `pgvector/pgvector:pg16` has an arm64 tag before committing |
| Budget VPS | Hetzner / Contabo, 4–8 GB, Docker Compose, Caddy for TLS | ~$5–12 | The pragmatic fallback. Predictable and boring. At the reduced 2 GB footprint, the cheapest tier now suffices |
| Managed free tiers stitched | Neon/Supabase (both ship pgvector) + Upstash + Fly.io/Render + Cloudflare Pages | $0–20 | No servers to patch, CDN for the SPA. But four vendors, four dashboards, free tiers that sleep on idle — a cold start during a defence is a bad demo. The Celery worker is the awkward part; most free tiers assume a web process |
| Student credits | GitHub Student Pack, Azure for Students | $0 until exhausted | Fine for the defence window, dangerous as a plan — the bill arrives after the credit does. Use it to buy a year of VPS, not to build habits around services you cannot afford later |
| AWS ECS/Fargate/RDS/ALB | The path in the referenced (missing) AWS roadmap | ~$350–450 | **Not justified.** NAT Gateway and ALB alone exceed a VPS that runs everything. Right only for a university-adopted production deployment with an ops owner |

> Figures are order-of-magnitude and change often. Verify current pricing before committing; free-tier terms change without notice.

**Recommendation: one box, Docker Compose, on campus, behind a Cloudflare Tunnel.** Zero recurring cost, data stays on university hardware, and the deployment artefact is identical to what a VPS would take if campus networking or power proves unreliable. That portability is the point — the fallback requires no re-architecture.

**Three changes make every option above cheaper**, in order of impact:

1. **DEP-1** — drop five services (~8 GB → ~2 GB).
2. **Build the frontend.** Compose currently runs `vite dev`; the multi-stage Nginx Dockerfile already exists and produces static files that are free to serve anywhere.
3. **Skip Docling for the MVP.** 4 GB for a scanned-PDF path PyMuPDF covers for born-digital theses (BLOCK-4).

- **Complexity:** Low · **Risk:** Low
- **MVP:** **MVP RECOMMENDED**
- **Testing implications:** None directly — but a single-box Compose deployment is the only target a student team can realistically smoke-test end to end, which is itself an argument for it.

---

## DEP-6 · No CI/CD

**Problem.** No `.github/` directory. No pipeline of any kind. Nothing runs on push.

**Impact.** This is the root cause of most of this review. Every blocker in [00](00-review-summary.md) is machine-detectable, and none was detected:

| Blocker | Would have been caught by |
|---|---|
| BLOCK-1 undefined names | `python -c "import config.urls"` — or `ruff` |
| BLOCK-2 missing `ai/` | `docker compose config` |
| BLOCK-3 queue routing | A Celery task test under `CELERY_TASK_ALWAYS_EAGER` |
| BLOCK-4 missing libraries | `pip install -r requirements/base.txt` then import |
| BLOCK-5 missing migrations | `python manage.py makemigrations --check --dry-run` |
| Frontend lint suppression | `npm run lint` — once a config exists |

**Recommendation.** One GitHub Actions workflow. Six steps, roughly 40 lines, under two minutes:

```
1. pip install -r requirements/development.txt
2. python manage.py makemigrations --check --dry-run
3. python manage.py check
4. pytest                                  # even with one import-smoke test
5. npm ci && npm run typecheck && npm run lint && npm run build
6. docker compose -f docker-compose.yml config
```

**Alternatives.** Pre-commit hooks — useful, but bypassable and not enforced on merge. Do both; CI is the one that must exist.

- **Complexity:** Low — an afternoon
- **Risk:** None
- **Dependencies:** FE-7 (eslint config, typecheck script), BE-13 (pytest)
- **MVP:** **MVP BLOCKER** — this is the control that prevents the next five blockers
- **Framework impact:** None (GitHub Actions is free for public repos)
- **Testing implications:** This is what makes every test in this review load-bearing rather than decorative.

---

## Summary

| Question | Answer |
|---|---|
| Does the current compose start? | **No.** `./ai` does not exist |
| How many services are justified? | **Five.** Ten declared, five run no code |
| Is Docling justified? | **Not for MVP.** 4 GB, called by nothing, PyMuPDF covers born-digital PDFs |
| Is a separate vector DB justified? | **No.** pgvector in the existing Postgres |
| Is AWS justified? | **No.** ~$400/mo for a workload that fits on a $0–10 box |
| Database | **Postgres — keep.** Correct choice; pgvector image is right, just unused |
| Redis | **Keep.** Broker today; also the right place for the caching AI-6 needs |
| Workers | **One.** Three specialised workers consume dead queues |
| Frontend hosting | Static build behind nginx — the Dockerfile exists and is unused in dev |
| Backend hosting | Gunicorn on the same box; `gthread` when AI ships |
| Storage | Local volume for MVP; **remove the unauthenticated nginx `/media/` route immediately** |
| Observability | Absent — configure logging, initialise or drop Sentry, add healthchecks |
| Backups | Absent — nightly `pg_dump` + media tar, and rehearse a restore |
| Scaling | Adequate for profiles 1–3; profile 4 is a later document |
| Failure recovery | `restart:` set, healthchecks missing on every service that exists |
| CI/CD | **Absent — and it is the root cause.** DEP-6 is the highest-leverage item in this document |
