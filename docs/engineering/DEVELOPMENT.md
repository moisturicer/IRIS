# Development Guide

**Purpose.** How to run, build and work on IRIS locally.
**Owns.** Prerequisites, setup, commands, environment variables, troubleshooting.
**Does not own.** Process (`SDLC.md`) · state definitions (`WORK_ITEM_LIFECYCLE.md`) · architecture (SDD).
**Authority.** Authoritative for commands. **Every command here has been checked against this branch.**
**Update when.** A command, script, dependency or service changes.

> **Baseline branch: `refactor/docker-service`.** Not `main`. The two branches have diverged substantially, including in `docs/`.

---

## 1 · Known-broken on this branch

Read this first — several obvious commands fail for reasons that are already understood and ticketed.

| Symptom | Cause | Item |
|---|---|---|
| `docker compose up` fails | `ai-gateway` builds from `./ai`, which now exists, but Compose also requires `./ai/.env`, which does not. The service is not deployed under [ADR-010](../adr/010-deployment-topology.md) | IR-58 |
| Every API request 500s / no route resolves | `apps/records/views.py` has six undefined names; `config/urls.py:11` imports it, so the URLconf fails at import | IR-57 |
| Frontend unreachable in prod compose | Prod maps `80:80`; nginx-unprivileged listens on `8080` | IR-58 |
| `pytest` does nothing | **No test files and no pytest config exist yet** | IR-73 *(pending)* |
| `npm test` not found | No test runner is installed in `frontend/package.json` | deferred (P3) |

**Until IR-57 and IR-58 land, the stack does not start.** That is expected, not a setup mistake on your part.

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
                  notifications · audit · ai · storage
  config/         settings, urls, celery
  core/           permissions, shared utilities
  requirements/   base.txt · development.txt · production.txt
  manage.py · Dockerfile · entrypoint.sh · .env.example

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

cp .env.example .env          # then fill in real values

python manage.py check        # validates configuration; currently FAILS until IR-57
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
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
docker compose up --build          # currently FAILS — see §1
docker compose logs -f backend
docker compose down                # add -v to drop volumes
```

**Services:** `db` (PostgreSQL) · `redis` · `backend` (Django) · `worker` (Celery) · `frontend` (nginx).

**`ai-gateway` is declared in both Compose files.** Commit `7f73e97` added an `ai/` FastAPI source tree, so the build context now exists — but the service still does not run: Compose requires `./ai/.env`, which is absent, and `ai/api/chat.py` imports `ai.services.chat_service` and `ai.services.embedding_service` from an `ai/services/` package that contains only an `__init__.py`, so the container would die at import even with the env file present.

This is **not** a missing file to add. [ADR-010](../adr/010-deployment-topology.md) rejects a separate AI gateway; AI belongs inside Django. [ADR-012](../adr/012-ai-provider-abstraction-not-a-service.md) settles the question: the provider abstraction is ported into Django as `apps/ai/providers/`, and the service is not adopted. The service declaration is removed by IR-58. Do not build on `ai/`.

### Celery

Workers consume `default`, `extraction` and `embedding`; tasks currently publish to `celery`. **No worker consumes the queue that tasks publish to**, so no task is ever processed. Fixed by the Celery routing work in Epic C.

---

## 7 · Environment variables

`backend/.env.example` is the authoritative list. It holds keys and no real values.

**Rules**
- Never commit a real secret. If one is committed, **rotate it** — removing it from the diff is not enough
- The application should fail to start on a missing required secret rather than defaulting silently
- Production must run with `DEBUG=False`, an explicit `ALLOWED_HOSTS`, and an explicit `CORS_ALLOWED_ORIGINS`

`CORS_ALLOW_ALL_ORIGINS` together with `CORS_ALLOW_CREDENTIALS` is currently set in development. It permits any origin to make authenticated requests on a logged-in user's behalf and is removed by IR-61.

---

## 8 · Tests

**There are currently no tests.** This is the single largest engineering gap, and the first thing CI will enforce once the harness lands.

Intended:

```bash
# backend  (once the harness exists)
cd backend && pytest
cd backend && pytest apps/reviews -v
```

The first test to write is an **import smoke test** — it catches three of the five current blockers on its own.

Rules: **never modify a test to make it pass**; if the test is wrong, fix it deliberately and say so in the PR. A requirement is not satisfied because code exists — only when a test demonstrates it and the evidence is recorded.

---

## 9 · Contributing

1. Pull a `ready-to-pull` item from the board and assign yourself
2. Branch from `refactor/docker-service` — `feat/IR-69-transition-table`
3. Implement, with tests where applicable
4. Verify each acceptance criterion yourself and note how
5. Open a PR referencing the Jira key, with evidence
6. Move the item to **In Review** only when the conditions in `WORK_ITEM_LIFECYCLE.md` §7 hold
7. Address review; merge on approval

Full process: [`SDLC.md`](SDLC.md). State definitions: [`WORK_ITEM_LIFECYCLE.md`](WORK_ITEM_LIFECYCLE.md).

---

## 10 · Troubleshooting

| Problem | Check |
|---|---|
| Nothing responds | IR-57 — the URLconf fails at import. `python manage.py check` |
| Compose will not start | IR-58 — `ai-gateway` has no `ai/.env` and cannot import its own service package |
| Frontend up, not reachable | Prod port mapping, `80:80` vs `8080` |
| Celery tasks never run | Queue routing mismatch — workers and publishers disagree |
| Uploads not extracted | `documents/tasks.py` imports `unstructured`, `fitz`, `pytesseract` — **none are in any requirements file** |
| Migrations conflict | `showmigrations`, then resolve deliberately; never edit an applied migration |
| Type error on build | Intended — `npm run build` runs `tsc` first. Fix the type |
