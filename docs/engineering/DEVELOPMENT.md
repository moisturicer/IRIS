# Development Guide

**Purpose.** How to run, build and work on IRIS locally.
**Owns.** Prerequisites, setup, commands, environment variables, troubleshooting.
**Does not own.** Process (`SDLC.md`) · the Ready/Review/Done gates (`DEFINITION_OF_DONE.md`) · Jira states (`../agents/issue-tracker.md`) · architecture and decisions (`../adr/`).
**Authority.** Authoritative for commands. **Every command here has been checked against this branch.**
**Update when.** A command, script, dependency or service changes.

> **Baseline branch: `feat/rag-service`.** `main` carries the requirements, design and ADRs and is merged in; RAG and AI work continues here.

---

## 1 · Known-broken on this branch

Read this first — several obvious commands fail for reasons that are already understood and ticketed. See `CLAUDE.md`'s "Known-broken" section for the authoritative, currently-maintained list; this table exists so setup failures aren't mistaken for a local mistake.

| Symptom | Cause | Item |
|---|---|---|
| `docker compose up --build` fails | `ai-gateway` builds from `./ai`, which now exists, but Compose also requires `./ai/.env`, which does not; even with that supplied, `ai/api/chat.py` imports `ai.services.chat_service`, which does not exist. [ADR-014](../adr/014-ai-gateway-as-a-service.md) adopts the gateway under five preconditions — none met yet, so it stays undeployed, not rejected | IR-58 |
| Every API request 500s / no route resolves | `apps/records/views.py` has undefined names; `config/urls.py:11` imports it, so the URLconf fails at import | IR-57 |
| Celery tasks never ran | Fixed (IR-164) — `CELERY_TASK_ROUTES`/`CELERY_TASK_DEFAULT_QUEUE` now match the workers' queues, verified against the real stack. Not currently known-broken | — |
| Frontend unreachable in prod compose | Prod maps `80:80`; nginx-unprivileged listens on `8080` | IR-58 |
| `npm run lint` / `npm run build` fail | Not currently known-broken — both pass on this branch (verified 2026-09-06) | — |
| `npm test` not found | No test runner is installed in `frontend/package.json` | deferred (P3) |
| `/media/` serves any uploaded PDF unauthenticated | `frontend/nginx.conf:52-56` | IR-59 |

**Until IR-57 and IR-58 land, the stack does not start end to end.** Backend and frontend each build, lint and test independently of that — see §4/§5/§8 below.

---

## 2 · Prerequisites

- Docker and Docker Compose
- Python 3.11+ and Node 18+ if running outside containers
- PostgreSQL 15+ and Redis if running services natively

---

## 3 · Repository layout

```
backend/          Django + DRF
  apps/           accounts · records · reviews · documents
                  notifications · audit · ai
                  (apps/storage removed — IR-62)
  config/         settings, urls, celery
  core/           permissions, shared utilities
  requirements/   base.txt · development.txt · production.txt
  manage.py · Dockerfile · entrypoint.sh · .env.example

ai/               FastAPI AI gateway, ports-and-adapters (`domain/`, `infrastructure/`, `api/`) — ADR-014

frontend/         React 18 + TypeScript + Vite
  src/
    api/          one module per backend area
    components/   ui/ · shared/ · layout/ · auth/ · compliance/
    features/     one directory per feature area
    hooks/ lib/ router/ store/ types/
  nginx.conf · package.json · tailwind.config.js

docs/             see docs/README.md for the map
docker-compose.yml · docker-compose.prod.yml
```

---

## 4 · Backend

```bash
cd backend

pip install -r requirements/development.txt

cp .env.example .env          # then fill in real values; see §7 -- the repo root needs its own .env for Compose

python manage.py check        # passes (one deprecation warning: AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python -m pytest -q           # pytest.ini + conftest.py (IR-82); tests skip cleanly with no Postgres reachable
python manage.py inspect_chunks <record_id> --limit 50   # read a record's chunks (IR-116)
```

**Requirements are split three ways.** `base.txt` holds what both environments need; `development.txt` and `production.txt` each include base. Add a runtime dependency to `base.txt`, not to one of the leaves.

### Migrations

```bash
python manage.py makemigrations <app>
python manage.py migrate
python manage.py showmigrations
```

Rules: every model change ships with its migration · test against a copy of a realistic database, not only an empty one · **never edit a migration that has been applied anywhere** — supersede it.

---

## 5 · Frontend

```bash
cd frontend

npm install
npm run dev        # vite dev server
npm run build      # tsc && vite build  — type errors fail the build
npm run preview    # serve the built output
npm run lint       # eslint src --ext ts,tsx
```

**There is no `npm test`.** No test runner is installed. Do not add one casually — a frontend test harness is currently P3 and deliberately deferred.

`npm run build` runs `tsc` first, so **a type error fails the build**. That is the intended behaviour; do not weaken it to get a build through.

---

## 6 · Docker

```bash
# from the repository root
docker compose config              # validate without building
cp .env.example .env               # repo root — Compose needs it; see §7
docker compose up --build          # currently FAILS — see §1
docker compose logs -f backend
docker compose down                # add -v to drop volumes
```

**Services:** `db` (PostgreSQL) · `redis` · `backend` (Django) · `frontend` (nginx) · `docling` (docling-serve, structured extraction — ADR-016) · `ai-gateway` (FastAPI, ADR-014) · `celery-default` / `celery-extraction` / `celery-embedding` / `celery-beat` (Celery workers, routed by queue).

**`ai-gateway` now has a real build context (`./ai`)** and builds, given `./ai/.env` (gitignored, absent in CI and on a fresh checkout) — but it crashes at runtime: `ai/api/chat.py` imports `ai.services.chat_service` and `ai.services.embedding_service` from an `ai/services/` package that contains only an `__init__.py`. [ADR-014](../adr/014-ai-gateway-as-a-service.md) supersedes ADR-010/012's earlier rejection and adopts the gateway as a service under five preconditions, none yet met — this is what's tracked in IR-58, not a missing file to bolt on. Do not deploy it.

### Celery

Workers consume the `default`, `extraction` and `embedding` queues (`docker-compose.yml`'s `celery-default`/`celery-extraction`/`celery-embedding` services). `config/settings/base.py` sets `CELERY_TASK_ROUTES` (`extract_pdf_text` → `extraction`, `embed_record` → `embedding`) and `CELERY_TASK_DEFAULT_QUEUE = "default"` for everything else, including `chunk_record_document` (IR-164) — so publishers and consumers agree on queue names. Verified against the real docker-compose stack, not just the config: a task dispatched over the real Redis broker was consumed and completed by the real `celery-default` and `celery-extraction` containers.

---

## 7 · Environment variables

There are **two** example files, and they are not alternatives (IR-154):

| File | Read by | Holds |
|---|---|---|
| `backend/.env.example` → `backend/.env` | Django and Celery, via `decouple` | Every application key. The authoritative list |
| `.env.example` (repo root) → `.env` | **Docker Compose**, for `${VAR}` substitution | `DB_NAME`, `DB_USER`, `DB_PASSWORD` only |

Compose needs its own file because `${DB_PASSWORD}` in a compose file is interpolated by Compose itself, which reads the repo-root `.env` and never looks inside `backend/.env`. Putting the credential there means the same three values provision the Postgres container *and* reach Django and every worker, so the two cannot drift. Both example files hold keys and no real values.

**`docker compose up` fails by name without the root `.env`** — every reference is written `${DB_NAME:?set DB_NAME in the repo-root .env}`, which is the intended behaviour, not a bug to work around:

```bash
cp .env.example .env          # repo root, for Compose
cp backend/.env.example backend/.env
```

**Rules**
- Never commit a real secret. If one is committed, **rotate it** — removing it from the diff is not enough
- The application fails to start on a missing required secret rather than defaulting silently. `SECRET_KEY`, `DB_NAME`, `DB_USER` and `DB_PASSWORD` have **no defaults**: `config/settings/base.py`'s `required()` raises `ImproperlyConfigured` naming the variable, and a value set to the empty string counts as missing
- Production must run with `DEBUG=False`, an explicit `ALLOWED_HOSTS`, and an explicit `CORS_ALLOWED_ORIGINS`. `config/settings/production.py` re-reads the last two without base's `localhost` default and refuses to start on an empty, `*` or non-https value

`CORS_ALLOW_ALL_ORIGINS` is **gone** from every settings module (IR-154 — earlier text here attributing this to IR-61 is superseded; IR-61 was replaced by IR-154). It was set in development and, combined with `CORS_ALLOW_CREDENTIALS`, permitted any origin to make authenticated requests on a logged-in user's behalf. `development.py` now lists its dev origins explicitly, and `production.py` refuses to start if the setting reappears anywhere.

---

## 8 · Tests

**The backend harness exists (IR-82)**: `pytest.ini` + `conftest.py`, DB-required tests skip cleanly when no Postgres is reachable. Coverage is concentrated in `apps/ai` (chunking, extraction, ingestion) and `apps/documents`, built out through IR-89 and IR-107.

```bash
cd backend && python -m pytest -q
cd backend && python -m pytest apps/reviews -v
cd backend && python -m pytest apps/ai apps/documents   # the RAG pipeline suites
```

**Frontend still has no test runner** — `npm test` is not wired up, deliberately deferred (P3). `npm run lint` and `npm run build` (`tsc && vite build`) are the only automated frontend checks.

Rules: **never modify a test to make it pass**; if the test is wrong, fix it deliberately and say so in the PR. A requirement is not satisfied because code exists — only when a test demonstrates it and the evidence is recorded.

---

## 9 · Contributing

1. Pull a `ready-for-agent` / `ready-to-pull` item from the board and assign yourself
2. Branch from `feat/rag-service` — `feat/IR-69-transition-table`
3. Implement, with tests where applicable
4. Verify each acceptance criterion yourself and note how
5. Open a PR referencing the Jira key, with evidence
6. Move the item to **In Review** only when the conditions in `DEFINITION_OF_DONE.md` §2 hold
7. Address review; merge on approval

Full process: [`SDLC.md`](SDLC.md). Done gates: [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md). Jira states and labels: [`../agents/issue-tracker.md`](../agents/issue-tracker.md).

---

## 10 · Troubleshooting

| Problem | Check |
|---|---|
| Nothing responds | IR-57 — the URLconf fails at import. `python manage.py check` |
| Compose will not start / `ai-gateway` container exits | IR-58 — `ai-gateway` has no `ai/.env`, and even with one, its service package is missing (`ai.services.chat_service`, `ai.services.embedding_service`); do not deploy it |
| Celery task never runs | Routing was the gap and is fixed (IR-164, see §6 Celery above) — if a task still doesn't run, look at the task itself, not queue names |
| Frontend up, not reachable | Prod port mapping, `80:80` vs `8080` |
| Uploads not extracted | `DoclingExtractor` calls `POST {DOCLING_API_URL}/v1/convert/file` — check the `docling` service is up and reachable; there is no fallback extractor (ADR-016) |
| Migrations conflict | `showmigrations`, then resolve deliberately; never edit an applied migration |
| Type error on build | Intended — `npm run build` runs `tsc` first. Fix the type |
| `npm run lint` can't find a config | Shouldn't happen — `eslint.config.js` is committed. If it does, check it wasn't accidentally removed |
