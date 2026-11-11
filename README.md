# IRIS — Intelligent Research & IP System

A web-based platform for Cebu Institute of Technology - University (CIT-U) that centralises the management of student and faculty research outputs and intellectual property records. It supports the full lifecycle — submission, peer review, IP tagging, document storage, download requests, and AI-assisted discovery — across all colleges and departments.

## Live deployment

| | |
| --- | --- |
| URL | **https://iris-citu.duckdns.org/** |
| Hosting | Amazon Web Services EC2, one Ubuntu 24.04 instance running `docker-compose.prod.yml` |
| HTTPS | Caddy terminates TLS 1.2/1.3 ([ADR-057](docs/adr/057-caddy-terminates-tls.md)); nginx and the other services are not published |
| Server setup and updates | [`deploy/README.md`](deploy/README.md): CloudFormation template, `deploy/bootstrap_server.sh`, `scripts/deploy.sh` |

**Documentation**

| Guide                                                                    | Description                                                   |
| ------------------------------------------------------------------------ | ------------------------------------------------------------- |
| [Documentation hub](docs/README.md)                                      | Governance index — what is authoritative and what is legacy   |
| [SRS](docs/SRS.md)                                                       | Frozen 2026-09-03; thesis deliverable, not maintained         |
| [SDD](docs/SDD.md)                                                       | Frozen 2026-09-03; thesis deliverable, not maintained         |
| [Architecture decisions](docs/adr/README.md)                             | **Requirements and design authority.** ADR index              |
| [Deployment](deploy/README.md)                                           | AWS server setup, HTTPS edge, one-command updates             |
| [SDLC process](docs/engineering/SDLC.md)                                 | Branching, commits, PRs, review, release, traceability        |
| [Work item lifecycle](docs/engineering/WORK_ITEM_LIFECYCLE.md)           | DoR, pull-based Kanban, and the **Definition of Done** (§9)   |
| [Development guide](docs/engineering/DEVELOPMENT.md)                     | Local setup, known-broken commands, troubleshooting           |
| [Security](docs/security/SECURITY.md)                                    | Threat model, controls, NFR-S mapping, open defects           |
| [Test plan](docs/testing/TEST_PLAN.md)                                   | Test levels, evaluation design, evidence requirements         |
| [Traceability](docs/testing/TRACEABILITY.md)                             | Requirement status → code → tests → evidence                  |
| [Frontend implementation plan](frontend/docs/FRONTEND_IMPLEMENTATION.md) | UI tasks, wireframes, routes, design tokens                   |
| [Changelog](CHANGELOG.md)                                                | Version history                                               |

---

## Tech Stack

### Frontend

|           |                              |
| --------- | ---------------------------- |
| Framework | React 18 + Vite + TypeScript |
| Styling   | Tailwind CSS v3              |
| Routing   | React Router v6              |
| State     | Zustand                      |
| Forms     | React Hook Form + Zod        |
| Tables    | TanStack Table v8            |
| HTTP      | Axios                        |

### Backend

|               |                                        |
| ------------- | -------------------------------------- |
| Framework     | Django 5 + Django REST Framework       |
| Auth          | SimpleJWT (access + refresh tokens)    |
| Database      | PostgreSQL 16 (`pgvector/pgvector:pg16`) |
| Task Queue    | Celery + Redis                         |
| Email         | SMTP (configurable, defaults to Gmail) |
| Rate Limiting | DRF throttles; django-axes login lockout (off unless `AXES_ENABLED=True`) |
| Vector search | pgvector (HNSW) |

### AI services

|                    |                                                                |
| ------------------ | -------------------------------------------------------------- |
| AI runtime         | FastAPI service in `ai/` (gateway and run workers) that answers Ask IRIS and Paper Chat |
| PDF extraction     | LlamaParse                                                     |
| Embedding, rerank  | Voyage (`voyage-context-4`)                                    |
| Language model     | Any OpenAI-compatible chat-completions endpoint (OpenRouter by default) |

### Infrastructure

|                   |                                                           |
| ----------------- | --------------------------------------------------------- |
| Containerisation  | Docker + Docker Compose                                   |
| Web Server (prod) | Caddy (HTTPS) → nginx → Gunicorn with Uvicorn workers (ASGI) |
| Hosting           | AWS EC2 (see [Live deployment](#live-deployment))         |

---

## Project Structure

```
IRIS/
├── backend/
│   ├── apps/
│   │   ├── accounts/      # Users, roles, colleges, departments, courses
│   │   ├── records/       # Research records, workflow state, embargo
│   │   ├── reviews/       # Adviser-first review, office pools, clearances
│   │   ├── documents/     # File uploads per record
│   │   ├── notifications/ # In-app notifications
│   │   ├── audit/         # Audit log
│   │   ├── library/       # Saved records and feeds
│   │   ├── opportunities/ # Calls & Conferences
│   │   ├── publication/   # Durable processing work for published papers
│   │   ├── tests/         # Cross-app tests (authorization matrix)
│   │   └── ai/            # Extraction, chunking, embedding, reader grants
│   ├── config/
│   │   └── settings/      # base / development / production
│   ├── core/              # Shared permissions, pagination, utils
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── development.txt
│   │   └── production.txt
│   └── manage.py
├── ai/                    # AI runtime (FastAPI gateway, run workers, agent)
├── deploy/                # Caddyfile, AWS templates, server bootstrap
├── e2e/                   # Playwright core journeys
├── scripts/               # setup_env.py, deploy.sh
├── docs/                  # ADRs, engineering, testing, security
└── frontend/
    └── src/
        ├── api/           # Axios API clients per domain
        ├── features/      # Page components (auth, records, review, …)
        ├── components/    # Shared UI & layout components
        ├── store/         # Zustand stores (auth, ui)
        ├── types/         # TypeScript interfaces
        ├── lib/           # Constants, helpers, static data
        └── router/        # React Router config
```

---

## Running Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 16 (running locally, to match the Compose image)
- Redis (running locally — required for Celery/email tasks)

---

### 0 — Environment files

```bash
python scripts/setup_env.py
```

Creates `backend/.env` and the repo-root `.env` (the second is what Docker
Compose interpolates the database credentials from). It never overwrites an
existing file, and on a fresh checkout it generates a real `SECRET_KEY` and a
random database password, then prints the SQL below already filled in. Since
IR-154 `SECRET_KEY`, `DB_NAME`, `DB_USER` and `DB_PASSWORD` have no defaults —
Django refuses to start when any is missing or blank.

---

### 1 — Database setup

Open **pgAdmin** or `psql` and run:

```sql
-- Choose your own name and password; nothing in the repository supplies them
-- (IR-154), and whatever you pick here must match backend/.env, and the
-- repo-root .env if you run the stack under Docker.
CREATE USER <db_user> WITH PASSWORD '<db_password>';
CREATE DATABASE <db_name> OWNER <db_user>;
GRANT ALL PRIVILEGES ON DATABASE <db_name> TO <db_user>;
```

> The user needs `CREATEDB` if you intend to run the test suite: Django builds
> and drops a `test_<db_name>` database per run.
> `ALTER USER <db_user> CREATEDB;`

---

### 2 — Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements/development.txt

# Create a .env file in the backend/ folder
```

Minimum `.env` (copy-paste and adjust):

```env
# SECRET_KEY, DB_NAME, DB_USER and DB_PASSWORD have no defaults: Django
# refuses to start when one is missing or blank (IR-154).
# python -c "import secrets; print(secrets.token_urlsafe(64))"
SECRET_KEY=<generate one>
DEBUG=True

DB_NAME=<db_name>
DB_USER=<db_user>
DB_PASSWORD=<db_password>
DB_HOST=localhost
DB_PORT=5432

FRONTEND_URL=http://localhost:5173

# Email — leave blank to skip verification emails in dev
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# Redis (needed for Celery; leave default unless your Redis is on a different port)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

```

```bash
# Run migrations
python manage.py migrate

# Create a superuser (use any username/email; password can be anything)
python manage.py createsuperuser

# Mark the superuser as email-verified so you can log in immediately using username
python manage.py shell -c "
from apps.accounts.models import User
u = User.objects.get(username='<your-superuser-username>')
u.is_verified = True
u.save()
print('Done:', u.username, '| verified =', u.is_verified)
"

# Mark the superuser as email-verified so you can log in immediately using email
python manage.py shell -c "
from apps.accounts.models import User
u = User.objects.get(email='<your-superuser-email>')
u.is_verified = True
u.save()
print('Done:', u.email, '| verified =', u.is_verified)
"

# Start the dev server
python manage.py runserver
```

Backend runs at **http://localhost:8000**

---

### 3 — Frontend

```bash
cd frontend

npm install
npm run dev
```

With `docker compose up`, browse **http://localhost:8080**: a dev nginx edge (the production routing in front of Vite) that makes Ask IRIS work. Vite alone at http://localhost:5173 cannot reach the AI runtime.

Frontend runs at **http://localhost:5173**

Open your browser to `http://localhost:5173` and sign in with the superuser credentials you just created.

---

### 4 — (Optional) Celery worker

Email verification and other background tasks require a running Celery worker. In a separate terminal:

```bash
cd backend
venv\Scripts\activate
celery -A config worker -l info
```

> If you skip this step, sign-up emails will not be sent, but everything else works normally.

---

## Environment Variables Reference

Names only. Each `.env.example` file lists every variable with a comment, and none holds a real value. Copy a file to `.env` beside it and fill it in; the real `.env` files are gitignored.

| File | Read by | Variables |
| ---- | ------- | --------- |
| [`.env.example`](.env.example) | Docker Compose (repo root) | `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `AI_GATEWAY_SERVICE_SECRET`; production also `IRIS_DOMAIN`, `REDIS_PASSWORD`, `TRUSTED_PROXY_COUNT`, `DJANGO_ADMIN_ALLOWED_NETWORKS` |
| [`backend/.env.example`](backend/.env.example) | Django and Celery | see below |
| [`ai/.env.example`](ai/.env.example) | AI runtime | `SERVICE_SECRET`, `RUNS_DATABASE_URL`, `RUNS_REDIS_URL`, the `RUNS_*` limits, `RUNS_EXECUTOR`, `RUNS_AGENT_*`, the `AGENT_LLM_*` model settings (`AGENT_LLM_ENDPOINT`, `AGENT_LLM_API_KEY`, …), `VOYAGE_API_KEY`, the `AI_ADMISSION_*` limits |

Main names in `backend/.env`:

| Group | Variables |
| ----- | --------- |
| Required (Django will not start without them) | `SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, the `RECOVERY_*` secrets (`RECOVERY_COUNTER_HMAC_KEY`, `RECOVERY_MAIL_ENCRYPTION_KEY`) |
| Required in production | `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `TRUSTED_PROXY_COUNT`, `REGISTRATION_EMAIL_DOMAINS`, `LLAMAPARSE_API_KEY`, `LLAMAPARSE_VERSION`, `LLAMAPARSE_TIER` |
| Database and cache | `DB_HOST`, `DB_PORT`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `REDIS_URL`, `REDIS_CACHE_URL` |
| General | `DEBUG`, `FRONTEND_URL`, `SESSION_IDLE_TIMEOUT_MINUTES`, `AXES_ENABLED`, `AXES_FAILURE_LIMIT`, `AXES_COOLOFF_TIME_MINUTES`, `API_THROTTLE_*` |
| Email | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` |
| Extraction | `EXTRACTION_BACKEND`, `LLAMAPARSE_*` |
| Embedding and AI | `VOYAGE_API_KEY`, `VOYAGE_EMBED_MODEL`, `VOYAGE_RERANK_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, the per-task `LLM_<TASK>_*` settings, `AI_GATEWAY_SERVICE_SECRET`, `AI_RESEARCH_*`, `AI_PROVIDER_ADMISSION` and the `AI_ADMISSION_*` limits |

---

## Notes

- **Role requests**: new accounts do not get a role immediately. An admin must approve or decline the role request in the admin panel before the user can access role-restricted pages.
