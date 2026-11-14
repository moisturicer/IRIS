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

### API rate limits during development (IR-371)

Every API call counts, including Paper View reloads and polling. Each budget
counts over two windows (IR-999): a per-minute burst a person can reach, whose
refusal clears in under a minute, and a daily backstop only a script reaches.
Unset, `API_THROTTLE_ANON_BURST`/`API_THROTTLE_ANON` are `180/minute` and
`30000/day` per address, `API_THROTTLE_USER_BURST`/`API_THROTTLE_USER` are
`180/minute` and `75000/day` per person, and
`API_THROTTLE_AI_QUERY_BURST`/`API_THROTTLE_AI_QUERY` are `15/minute` and
`750/day`. `backend/.env.example` opts into higher local values; copy those
keys into your local `backend/.env` and restart backend processes to use them.
`DEBUG` never raises a limit. Each rate must be a positive integer followed by
`/second`, `/minute`, `/hour` or `/day` (short forms s/sec, m/min, h and d
also work). Invalid values stop startup and name the offending key.
The separate AI overview budget is unchanged.

Login and registration have budgets of their own (IR-661): `API_THROTTLE_LOGIN_BURST`
and `API_THROTTLE_LOGIN` (`120/minute`, `3000/day`), and `API_THROTTLE_REGISTER_BURST`
and `API_THROTTLE_REGISTER` (`60/minute`, `750/day`), same format. They count per
client address, read as `TRUSTED_PROXY_COUNT` says, and do not spend the anonymous
budget. A refusal is a 429 with `Retry-After`. The axes lockout is separate and
still answers per account and address.

A 429 recovers after its `Retry-After` window. **Production must wait out
that window.** Locally, after changing a limit, old counters can still lock
an account out. Open `docker compose exec backend python manage.py shell`
and paste the following to inspect only DRF's `throttle_*` keys in Django's
configured cache database (Compose uses Redis database 1, not Celery's 0):

```python
from django.conf import settings
from redis import Redis

if not settings.DEBUG:
    raise RuntimeError("Local development only; production must wait out the window.")
client = Redis.from_url(settings.CACHES["default"]["LOCATION"])
pattern = f"{settings.CACHES['default'].get('KEY_PREFIX', '')}:*:throttle_*"
keys = list(client.scan_iter(match=pattern))
dry_run = True
print(f"{len(keys)} throttle keys in the configured cache database")
print("Dry run: nothing deleted" if dry_run else client.delete(*keys) if keys else 0)
```

To clear the local lockout, rerun with `dry_run = False`. This resets request
budgets for **all local accounts**, including the throttled one, without
flushing unrelated cache entries or Celery jobs. For a single authenticated
account, narrow the pattern to `iris:*:throttle_user_42` (replace `42` with
the numeric user id, and `iris` if you customized the prefix). Anonymous
budgets are keyed by IP.

---

### Password recovery (IR-642)

Run `python scripts/setup_env.py` before starting this revision. It adds missing
recovery HMAC and mail-encryption keys to `backend/.env` without replacing
existing values. Both keys are required at startup. Production also requires
a fixed HTTPS `FRONTEND_URL` origin and populated SMTP configuration. Retain old
mail-encryption keys until every pending or issued payload using them is terminal;
an issued token can outlive the ten-minute request-intent lifetime.

Apply accounts migration `0014_account_recovery` and audit migration
`0009_recovery_event_types` before serving requests, then restart backend,
Celery workers and beat together. This rollout deliberately signs out existing
JWT holders: old access/refresh tokens lack the new credential version. Password
reset and authenticated password change end every device session. A profile edit
already in flight may finish, but cannot restore pre-reset credentials.

Recovery uses the `default` worker queue and beat's thirty-second dispatcher.
The HTTP request commits an encrypted delivery intent; neither SMTP nor account
lookup runs on that path. Broker loss is recovered from the intent. SMTP uses
a thirty-second timeout, up to four attempts, and the same single-use link on
retry. Monitor aggregate failed-intent counts and the age of pending work;
neither logs nor alerts should contain recipients, bodies or links.

Development mail stays in memory, so recovery and legacy activation links are
never printed to container logs. To exercise actual delivery, configure
`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and a development
SMTP server. Production continues to use SMTP. Verification resend and legacy
activation retirement remain IR-643; this rollout implements password recovery.
No production deployment was performed.

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

### Demo data

```bash
python manage.py seed_demo                  # accounts + catalogue + every pipeline state
python manage.py seed_demo --accounts-only  # the seven logins, nothing else
python manage.py seed_demo --password hunter2
```

**One command replaced four** (IR-227). `scripts/seed_demo_users.py`, `scripts/seed_demo_records.py` and `scripts/seed_demo_clearances.py` — each run by hand through `manage.py shell <`, in the right order — plus `seed_test_users`, which seeded a second `iris-*` account set at a different password. All four are deleted.

**The logins are `<role>@iris.test` at `IrisDemo123!`.** They were `<role>@cit.edu` until IR-1067, but the office addresses there are CIT-U's real mailboxes, so a demo server's notifications reached the real offices. `.test` is reserved (RFC 6761) and never receives mail. An older database is renamed in place by the commands in `docs/testing/traceability/IR-1067.md`.

| Login | Role |
|---|---|
| `student@iris.test` | Student — owns the demo records |
| `adviser@iris.test` | Adviser |
| `rdco@iris.test` | RDCO — administers people's accounts and the request queues, and gives Student and Adviser (`ADMIN_ROLES` is `{RDCO}`) |
| `itso@iris.test` · `ierc@iris.test` · `ktto@iris.test` | The three clearing offices |
| `admin@iris.test` | **System Admin**, and a Django superuser — the Audit Log, system settings and office roles in IRIS, and Django's admin site (ADR-051, IR-781). Only this demo login holds both |

Re-running is idempotent for records (keyed by title) but **resets all seven passwords** to the default, so say so before a rehearsal if someone has changed one.

**Everything is driven through `lifecycle.apply` and the review services, never by assigning `pipeline_status`.** That is the point rather than a style preference: the deleted scripts wrote `pipeline_status = "published"` directly, and `seed_demo_clearances.py` hand-built `Review` and `RecordClearance` rows and backdated their timestamps past the ORM. Both produced states the workflow never produced, so neither proved anything about it — and a faked state drifts silently the moment the real routing changes.

Two records carry the thesis contribution:

- **`[DEMO] Declined by IERC, ITSO and KTTO preserved`** — the one you *drive*. It sits in `declined`. Upload a document as the student (resubmission requires one since IR-139 — that refusal is part of the demo), resubmit, and watch IERC reset while ITSO and KTTO survive.
- **`[DEMO] Resubmitted, ITSO and KTTO preserved`** — the one you *look at*. Already resubmitted, so the paper view's "Preserved" badges render on arrival.

`scripts/seed_demo_opportunities.py` is still a shell script — it seeds the Calls & Conferences board (IR-121), a separate feature, and depends on `rdco@iris.test` which `seed_demo` creates.

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

**Services:** `db` (PostgreSQL) · `redis` · `backend` (Django) · `frontend` (nginx) · `ai-gateway` (FastAPI, ADR-014) · `celery-default` / `celery-extraction` / `celery-embedding` / `celery-shadow` / `celery-beat` (Celery workers, routed by queue).

**`ai-gateway` now has a real build context (`./ai`)** and builds, given `./ai/.env` (gitignored, absent in CI and on a fresh checkout) — but it crashes at runtime: `ai/api/chat.py` imports `ai.services.chat_service` and `ai.services.embedding_service` from an `ai/services/` package that contains only an `__init__.py`. [ADR-014](../adr/014-ai-gateway-as-a-service.md) supersedes ADR-010/012's earlier rejection and adopts the gateway as a service under five preconditions, none yet met — this is what's tracked in IR-58, not a missing file to bolt on. Do not deploy it.

### Migrations

Both Compose files run migrations once in a dedicated `migrate` service after PostgreSQL is healthy. The backend and all five Celery services wait for that service to complete successfully before starting (IR-528; proposed ADR-039). The shared image entrypoint only launches the requested process:

```bash
docker compose up --build          # migrate runs once, then backend and workers start
docker compose logs migrate        # inspect the one migration run
```

If a migration fails, the backend and workers remain stopped. Read `docker compose logs migrate`, correct the reported issue, then recreate the migration service and dependent services with `docker compose up --build --force-recreate`.

#### Refreshing old seeded workflow records

The seeder skips existing records by title, so it does not repair fixtures from
retired workflows. The reset command lists every `[DEMO]` record first and only
deletes database rows linked to those records when `--execute` is supplied. It
is limited to development (`DEBUG=True`); it leaves non-demo records, demo
accounts, catalogue lookup data, and uploaded files alone. Preview, then
explicitly delete and reseed when the development database is meant to be
refreshed:

```bash
docker compose run --rm --no-deps backend python manage.py reset_demo_records
docker compose run --rm --no-deps backend python manage.py reset_demo_records --execute
docker compose up --build --force-recreate
docker compose exec backend python manage.py seed_demo
```

### Celery

Workers consume the `default`, `extraction`, `embedding` and `shadow` queues (`docker-compose.yml`'s `celery-default`/`celery-extraction`/`celery-embedding`/`celery-shadow` services). `shadow` (IR-466) runs only `decide_evidence_shadow` at concurrency 1 and is idle unless `AI_EVIDENCE_DECISION=shadow`. `config/settings/base.py` sets `CELERY_TASK_ROUTES` (`extract_pdf_text` → `extraction`, `embed_record` → `embedding`) and `CELERY_TASK_DEFAULT_QUEUE = "default"` for everything else, including `chunk_record_document` (IR-164) — so publishers and consumers agree on queue names. Verified against the real docker-compose stack, not just the config: a task dispatched over the real Redis broker was consumed and completed by the real `celery-default` and `celery-extraction` containers.

**`celery-beat` schedules the reminder tasks.** Recovery mail's dispatch (ADR-045) runs too.

- **Review deadlines (IR-620, ADR-043 §8).** `CELERY_BEAT_SCHEDULE` in `config/settings/base.py` sends `apps.reviews.tasks.send_deadline_notifications` to `default` at minute 0 of every hour. The task asks the database which deadline reminders are owed, so beat keeps no reminder schedule of its own: a missed tick is caught up by the next one, and the `DeadlineMoment` unique key stops a re-run or a second beat instance from sending twice. Beat keeps its own bookkeeping in `/tmp/celerybeat-schedule` inside the container, which is safe to lose. Until an administrator enters a Turnaround, no assignment has a due date and the task sends nothing. To run it once by hand: `docker compose exec backend python manage.py shell -c "from apps.reviews.reminders import run_deadline_notifications; print(run_deadline_notifications())"`.
- **Embargo reviews (IR-814, ADR-052 §9).** `apps.records.tasks.send_embargo_reminders` runs on `default` daily at 00:00 UTC, which is 08:00 in Manila (Celery runs on UTC here, and Manila has no daylight saving). It reminds the owners and the Adviser in-app on an active embargo's review date, then every 5 working days, and changes nothing about the embargo. The `EmbargoReminder` unique key stops a re-run sending twice, and after downtime only the latest reminder is sent. To run it once by hand: `docker compose exec backend python manage.py shell -c "from apps.records.embargo_reminders import run_embargo_reminders; print(run_embargo_reminders())"`.

**Each worker declares a healthcheck** (IR-225). `celery -A config inspect ping -d <node>@$HOSTNAME` round-trips through the broker to that specific node, so it fails if the process is dead, wedged, or cannot reach Redis. This exists because `celery-extraction` once crash-looped for nine hours on a missing dependency in a stale image while `docker ps` showed only `Restarting` — with `restart: unless-stopped` and no healthcheck, a permanently broken worker looks exactly like one that happened to bounce. **When a worker misbehaves, check `docker ps` for `unhealthy` first, and rebuild it (`docker compose up -d --build <service>`) before debugging the task**: the four workers share one build spec but are separate images, and only one of them going stale is the failure that hides best.

`apps/tests/test_worker_boot.py` keeps the two halves honest — every queue named in `CELERY_TASK_ROUTES` has a worker consuming it, and every worker still declares a healthcheck. It reads `docker-compose.yml`, so it skips inside the `backend` container (which mounts only `backend/`) and runs in CI, where `IRIS_REQUIRE_DB` turns that skip into a failure.

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
python scripts/setup_env.py   # creates both; never overwrites, except to add
                              # missing recovery secrets to backend/.env (IR-642)
```

It derives the repo-root `.env` from your existing `backend/.env` when you have
one, so the credentials match the `postgres_data` volume already on your
machine — which is the failure below, avoided rather than documented. On a
fresh checkout it generates a real `SECRET_KEY` and a random DB password and
prints the `CREATE USER` / `CREATE DATABASE` statements to run. It is
idempotent; run it whenever you are unsure.

By hand instead, if you prefer:

```bash
cp .env.example .env          # repo root, for Compose
cp backend/.env.example backend/.env
```

> **If you already have a `postgres_data` volume**, it was initialised with the
> credentials this change retired, and `POSTGRES_*` is only read on *first*
> init — so new credentials in the root `.env` produce authentication failures
> against the existing volume, not a re-provisioned database. Either put the
> values the volume was created with into `.env`, or drop the volume and let it
> re-init: `docker compose down -v` (**destroys local data**).

**Rules**
- Never commit a real secret. If one is committed, **rotate it** — removing it from the diff is not enough
- The application fails to start on a missing required secret rather than defaulting silently. `SECRET_KEY`, `DB_NAME`, `DB_USER` and `DB_PASSWORD` have **no defaults**: `config/settings/base.py`'s `required()` raises `ImproperlyConfigured` naming the variable, and a value set to the empty string counts as missing
- Production must run with `TRUSTED_PROXY_COUNT` set to the number of proxies in front of Django, nginx included (IR-656). `apps/accounts/client_address.py` reads the sign-in lockout's client address from it.
- Compose publishes development Postgres and Redis on `127.0.0.1` only, and Redis requires `REDIS_PASSWORD` in both stacks (IR-669). `python scripts/setup_env.py` generates it in the repo-root `.env` when it is missing. **After pulling this change, run that script again**, or Compose stops by name. If a local Postgres or Redis already holds the port, Compose stops with "ports are not available": set `DB_HOST_PORT` or `REDIS_HOST_PORT` in the repo-root `.env`. A Django or Celery run on the host keeps using `backend/.env`. To point it at Compose's Redis, use `redis://:<REDIS_PASSWORD>@localhost:<port>/0`.
- To test from a phone on the same network, publish the frontend for that session in the gitignored `docker-compose.override.yml`, then delete the file. Anyone on that network can reach the frontend meanwhile, so use it on a network you trust. This recipe hasn't been run on a phone yet.

  ```yaml
  services:
    frontend:
      ports: !override
        - "5173:5173"
  ```
- `/django-admin/` answers 403 in production unless the client is in `DJANGO_ADMIN_ALLOWED_NETWORKS` (IR-668). Set it in the repo-root `.env`, as addresses or CIDRs separated by spaces or commas: `DJANGO_ADMIN_ALLOWED_NETWORKS=203.0.113.0/24, 198.51.100.7`. Empty allows nobody. With a value set, also put `TRUSTED_PROXY_COUNT` in that `.env`, matching `backend/.env`, because nginx reads the client address the same way. A bad value, `/0` or a missing count stops the frontend container. Restart it after a change: `docker compose -f docker-compose.prod.yml up -d frontend`. Port 80 must be reachable only from the TLS proxy, or a client could forge its address (IR-662). Development has no nginx, so it is unaffected. Django's admin is at `/django-admin/` in every environment, `http://localhost:8000/django-admin/` in development (IR-782); `/admin/...` is IRIS's own pages.
- Production must run with `DEBUG=False`, an explicit `ALLOWED_HOSTS`, and an explicit `CORS_ALLOWED_ORIGINS`. `config/settings/production.py` re-reads the last two without base's `localhost` default and refuses to start on an empty, `*` or non-https value

`CORS_ALLOW_ALL_ORIGINS` is **gone** from every settings module (IR-154 — earlier text here attributing this to IR-61 is superseded; IR-61 was replaced by IR-154). It was set in development and, combined with `CORS_ALLOW_CREDENTIALS`, permitted any origin to make authenticated requests on a logged-in user's behalf. `development.py` now lists its dev origins explicitly, and `production.py` refuses to start if the setting reappears anywhere.

---

## 8 · Tests

**The backend harness exists (IR-82)**: `pytest.ini` + `conftest.py`, DB-required tests skip cleanly when no Postgres is reachable. Coverage is concentrated in `apps/ai` (chunking, extraction, ingestion) and `apps/documents`, built out through IR-89 and IR-107.

```bash
cd backend && python -m pytest -q
cd backend && python -m pytest apps/reviews -v
cd backend && python -m pytest apps/ai apps/documents   # the RAG pipeline suites
cd backend && python -m pytest -m "not slow"           # skip the slowest tests locally (IR-835)
```

**One run per Postgres server (IR-835).** Two runs sharing one server slow each
other several-fold (measured: 24 minutes alone, about two hours shared), and two
checkouts with the same `DB_NAME` fight over one test database. A run that needs
the database takes a session advisory lock in the server's `postgres` database;
a second run exits at once naming the holder's pid and directory. The lock dies
with its connection, so a crashed run leaves nothing to clean up. Collect-only
runs and pytest runs started from inside a locked run do not take it.

**`slow` (IR-835)** marks every `*_migration.py` test automatically (each migrates
the schema backwards and forwards) and a few tests marked by hand. `-m "not slow"`
saves about five minutes locally. CI selects nothing and runs all of them.

**Tests do not read your AI configuration (IR-853).** A test run reads only what
CI supplies from `backend/.env`: `SECRET_KEY`, the two `RECOVERY_*` keys and the
`DB_*` connection. Vendor keys, LLM profiles and AI switches there are ignored,
so a local run tests the same configuration CI does and cannot reach a paid
vendor. `testing/hermetic_env.py` sets `IRIS_DOTENV_ALLOWLIST` before Django
loads; `config/settings/dotenv.py` applies it, and child processes inherit it.
A value exported in your shell still applies, as it would in CI. To test with
real settings, run the app, not the suite.

**Full suite in parallel (IR-854).** After installing
`backend/requirements/development.txt`, run `cd backend && python -m pytest -n 4`.
Use fewer workers if memory or database connections are limited; `-n 0` runs
serially. Every selected test still runs. pytest-django creates one migrated
database per worker (`test_<DB_NAME>_gw0`, etc.). The controller holds IR-835's
server lock before starting workers, so separate invocations cannot collide.
Each worker restores migration-created lookup rows when moving from a test
that flushes tables back to rollback-based tests. This preserves the initial data
that serial pytest-django normally protects through test ordering.
Whole modules stay on one worker, and the research-role consumers share one
worker because Postgres roles belong to the server. Schema rewinds and advisory
locks stay inside their worker's database. Tests launching child processes must
pass the active connection's database name/DSN, as the existing process tests do.
Run on Linux (or in a Linux container) for the PDF validation suites.

**Backend CI (IR-810, IR-854)** runs the complete collection across four isolated
runners/Postgres services. Complete modules are assigned longest-first to the
shard with the lowest estimated duration, with stable path/index tie breaks.
`backend/testing/module_durations.json` holds seconds including setup/teardown
from successful CI run **41455637632** (2026-11-02). Unseen modules use **0.2 seconds
per collected test**; old entries for removed modules are ignored. To refresh,
download all four `backend-tests-*` JUnit artifacts from one successful run and
execute, from `backend`:

```bash
python -m testing.timings path/to/shard1/pytest-results.xml path/to/shard2/pytest-results.xml path/to/shard3/pytest-results.xml path/to/shard4/pytest-results.xml
```

Commit the updated JSON. Duplicate cases and invalid durations are refused;
keep reports from different runs separate. Refresh after substantial suite
changes. The required `Backend` check still waits for all four shards.

The CI shard plugin is opt-in; local runs use one process unless `-n` is supplied.
Regression tests verify complete coverage and stable assignment.

**AI gateway:** CI's `AI gateway` job runs `ai/tests` with `ai/requirements-dev.txt` (IR-844). Run it with `cd ai && python -m pytest -ra`.

**Frontend:** CI runs `npm run lint`, `npm test` (Vitest with axe-core, IR-210) and `npm run build`.

Rules: **never modify a test to make it pass**; if the test is wrong, fix it deliberately and say so in the PR. A requirement is not satisfied because code exists — only when a test demonstrates it and the evidence is recorded.

---

## 9 · Contributing

1. Pull a `ready-for-agent` / `ready-to-pull` item from the board and assign yourself
2. Branch from `main` — `feature/IR-124-rag-retrieval` (`feat/rag-service` is merged in and is no longer a baseline; see [`../../CLAUDE.md`](../../CLAUDE.md))
3. Implement, with tests where applicable
4. Verify each acceptance criterion yourself and note how
5. Open a PR referencing the Jira key, with evidence
6. Move the item to **In Review** only when the conditions in `DEFINITION_OF_DONE.md` §2 hold
7. Address review; merge on approval

### Recording traceability

Add `docs/testing/traceability/IR-XXX.md` for your ticket, and change a row in `docs/testing/TRACEABILITY.md` only when a requirement's status changes ([ADR-055](../adr/055-traceability-evidence-lives-in-one-file-per-ticket.md)). A conflict on a row is then a real disagreement, so read both sides. A branch that appended to the old file should move its entry into its own file when it merges `main`.

Fixing the row format so this stops happening is IR-276.

Full process: [`SDLC.md`](SDLC.md). Done gates: [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md). Jira states and labels: [`../agents/issue-tracker.md`](../agents/issue-tracker.md).

---

## 10 · Troubleshooting

| Problem | Check |
|---|---|
| Nothing responds | IR-57 — the URLconf fails at import. `python manage.py check` |
| Compose will not start / `ai-gateway` container exits | IR-58 — `ai-gateway` has no `ai/.env`, and even with one, its service package is missing (`ai.services.chat_service`, `ai.services.embedding_service`); do not deploy it |
| Celery task never runs | First check the worker is actually up: `docker ps` for `unhealthy` or `Restarting`, then `docker compose up -d --build <service>` — a stale image missing a dependency crash-loops silently (IR-225). Routing itself is fixed (IR-164, §6 above), so once the worker is healthy, look at the task, not queue names |
| Frontend up, not reachable | Prod port mapping, `80:80` vs `8080` |
| Uploads not extracted | LlamaParse reads every Manuscript (ADR-056). With `DEBUG` on and no `LLAMAPARSE_API_KEY`/`LLAMAPARSE_VERSION`, every read fails as unavailable (IR-843). Otherwise check the `celery-extraction` worker's outbound access, and the consent and embargo gate, which holds a paper with no answer unread; there is no fallback extractor. Unstructured (`unstructured_client.py`, IR-985) is built but not selectable until IR-988's cutover (ADR-067); `selection.unstructured_extractor()` builds it and refuses without `UNSTRUCTURED_PLATFORM_API_KEY` |
| Migrations conflict | `showmigrations`, then resolve deliberately; never edit an applied migration |
| Type error on build | Intended — `npm run build` runs `tsc` first. Fix the type |
| `npm run lint` can't find a config | Shouldn't happen — `eslint.config.js` is committed. If it does, check it wasn't accidentally removed |
