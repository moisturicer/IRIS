# IRIS — Intelligent Research & IP System

A web-based platform for Cebu Institute of Technology - University (CIT-U) that centralises the management of student and faculty research outputs and intellectual property records. It supports the full lifecycle — submission, peer review, IP tagging, document storage, download requests, and AI-assisted discovery — across all colleges and departments.

**Documentation**

| Guide                                                                    | Description                                               |
| ------------------------------------------------------------------------ | --------------------------------------------------------- |
| [Documentation hub](docs/README.md)                                      | Index of all engineering, SDLC, security, and QA docs     |
| [Software engineering plan](docs/SOFTWARE_ENGINEERING_PLAN.md)           | Scope, phases, milestones, RACI, open decisions (M5/M7)   |
| [SDLC process](docs/SDLC_PROCESS.md)                                     | Lifecycle, branching, PR workflow, quality gates, release |
| [Security overview](docs/SECURITY.md)                                    | Threat model, controls, NFR-S mapping, deploy checklist   |
| [Security risk register](docs/SECURITY_RISK_REGISTER.md)                 | Threats, scores, mitigations, review log                  |
| [Test plan](docs/TEST_PLAN.md)                                           | Test levels, role matrix, UAT, automation roadmap         |
| [Traceability matrix](docs/TRACEABILITY_MATRIX.md)                       | SRS FR/NFR → code, UI, tests, status                      |
| [Development guide](docs/DEVELOPMENT_GUIDE.md)                           | Step-by-step build order, phases, local setup             |
| [Frontend implementation plan](frontend/docs/FRONTEND_IMPLEMENTATION.md) | UI tasks, wireframes, routes, design tokens               |
| [Changelog](CHANGELOG.md)                                                | Version history                                           |
| SRS / SDD (repo root)                                                    | Official requirements and software design PDFs            |

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
| Charts    | Recharts                     |
| HTTP      | Axios                        |

### Backend

|               |                                        |
| ------------- | -------------------------------------- |
| Framework     | Django 5 + Django REST Framework       |
| Auth          | SimpleJWT (access + refresh tokens)    |
| Database      | PostgreSQL 18                          |
| Task Queue    | Celery + Redis                         |
| Email         | SMTP (configurable, defaults to Gmail) |
| Rate Limiting | django-axes                            |

### Infrastructure

|                   |                         |
| ----------------- | ----------------------- |
| Containerisation  | Docker + Docker Compose |
| Web Server (prod) | Gunicorn + Nginx        |

---

## Project Structure

```
IRIS/
├── backend/
│   ├── apps/
│   │   ├── accounts/      # Users, roles, colleges, departments, courses
│   │   ├── records/       # Research records, review pipeline
│   │   ├── documents/     # File uploads per record
│   │   ├── notifications/ # In-app notifications
│   │   ├── audit/         # Audit log
│   │   ├── storage/       # Folder/file browser
│   │   └── ai/            # Semantic search & RAG Q&A
│   ├── config/
│   │   └── settings/      # base / development / production
│   ├── core/              # Shared permissions, pagination, utils
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── development.txt
│   │   └── production.txt
│   └── manage.py
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
- PostgreSQL 14+ (running locally)
- Redis (running locally — required for Celery/email tasks)

---

### 1 — Database setup

Open **pgAdmin** or `psql` and run:

```sql
CREATE USER iris_user WITH PASSWORD 'iris_password';
CREATE DATABASE iris_db OWNER iris_user;
GRANT ALL PRIVILEGES ON DATABASE iris_db TO iris_user;
```

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
SECRET_KEY=change-me-to-a-long-random-string
DEBUG=True

DB_NAME=iris_db
DB_USER=iris_user
DB_PASSWORD=iris_password
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

| Variable              | Default                    | Description                            |
| --------------------- | -------------------------- | -------------------------------------- |
| `SECRET_KEY`          | _(required)_               | Django secret key                      |
| `DEBUG`               | `False`                    | Set `True` for local development       |
| `ALLOWED_HOSTS`       | `localhost`                | Comma-separated list of allowed hosts  |
| `DB_NAME`             | `iris_db`                  | PostgreSQL database name               |
| `DB_USER`             | `iris_user`                | PostgreSQL user                        |
| `DB_PASSWORD`         | `iris_password`            | PostgreSQL password                    |
| `DB_HOST`             | `localhost`                | PostgreSQL host                        |
| `DB_PORT`             | `5432`                     | PostgreSQL port                        |
| `FRONTEND_URL`        | `http://localhost:5173`    | Used to build email verification links |
| `EMAIL_HOST`          | `smtp.gmail.com`           | SMTP server                            |
| `EMAIL_PORT`          | `587`                      | SMTP port                              |
| `EMAIL_HOST_USER`     | _(blank)_                  | SMTP username                          |
| `EMAIL_HOST_PASSWORD` | _(blank)_                  | SMTP password / app password           |
| `CELERY_BROKER_URL`   | `redis://localhost:6379/0` | Redis broker URL                       |

---

## Notes

- **Role requests**: new accounts do not get a role immediately. An admin must approve or decline the role request in the admin panel before the user can access role-restricted pages.
