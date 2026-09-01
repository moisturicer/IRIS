# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

IRIS is a research/IP management platform for Cebu Institute of Technology – University: submission, peer review, IP tagging, document storage, download requests, and AI-assisted discovery across colleges and departments. Three independently deployed services:

- **`backend/`** — Django 5 + DRF REST API (business logic, auth, records, workflow)
- **`ai/`** — FastAPI async gateway (LLM/embeddings/vector search — the RAG pipeline)
- **`frontend/`** — React 18 + Vite + TypeScript SPA

They run together via `docker-compose.yml` (10 services: db, redis, backend, frontend, docling, ai-gateway, celery-default/extraction/embedding, celery-beat).

## Commands

### Backend (Django)
```bash
cd backend
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements/development.txt
python manage.py migrate
python manage.py runserver                     # http://localhost:8000
python manage.py test apps.<app_name>           # run one app's tests (no tests written yet as of this writing)
celery -A config worker -l info                 # background tasks (email, extraction, embedding)
```
Settings are split: `config/settings/{base,development,production}.py`, selected via `DJANGO_SETTINGS_MODULE`. Requires PostgreSQL (with `pgvector`) and Redis running locally, plus a `backend/.env` (see README for the minimum vars).

### AI Gateway (FastAPI)
```bash
cd ai
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```
Config comes from `ai/infrastructure/settings.py` (pydantic-settings, reads `ai/.env`). Key vars: `LLM_PROVIDER` / `EMBEDDING_PROVIDER` (`openai` or `local`), `OPENAI_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`.

### Frontend
```bash
cd frontend
npm install
npm run dev       # http://localhost:5173
npm run build      # tsc typecheck + vite build
npm run lint        # eslint src --ext ts,tsx
```

### Full stack
```bash
docker-compose up      # all 10 services
```

## Architecture

### Backend: Django apps under `backend/apps/`
- `accounts` — users, `Role` (seeded via data migration, not user-creatable), `College → Department → Course` hierarchy, `StudentProfile`/`AdviserProfile`, `RoleRequest` (signup requests a role; an admin must approve before the user gets access — see `core/permissions.py` role constants: Student, Adviser, KTTO, RDCO, ITSO, IERC)
- `records` — research records and the review/submission pipeline
- `documents` — per-record file uploads, PDF text extraction (`PdfExtraction` model, Celery tasks)
- `reviews` — review actions per record
- `storage` — a general-purpose folder/file browser, unrelated to the record review pipeline
- `notifications` — in-app notifications
- `audit` — audit log
- `ai` — models/routes for chat, summarization, and RAG exist as scaffolding here (`apps/ai/services/*` are currently stub files); the actual RAG/LLM logic lives in the standalone `ai/` FastAPI gateway, not this Django app

Shared code lives in `backend/core/`: `permissions.py` (role-based `BasePermission` classes — prefer these over ad hoc role checks), `exceptions.py` (domain `APIException` subclasses), `pagination.py`, `utils.py`.

Role/permission pattern to follow: define role constants and permission classes once in `core/permissions.py`, compose sets (`REVIEWER_ROLES`, `STAFF_ROLES`, `ADMIN_ROLES`) rather than hardcoding role name comparisons in views. `is_django_staff()` always grants access, on top of any role check.

Document model is being redesigned — see `docs/document_requirements_architecture.md` for the target three-layer model (Department Templates → Office Checklists → Supplementary Attachments) that the current `UploadSlot`/`RecordFile` models will evolve toward. Read it before touching document requirement logic.

### AI Gateway (`ai/`): hexagonal/clean architecture, actively being restructured on this branch
```
ai/
├── main.py                    # FastAPI app, CORS, router mounting
├── api/                       # routes + pydantic request/response schemas (the "driving" adapters)
├── domain/ports.py            # abstract interfaces: LLMProvider, EmbeddingProvider
├── infrastructure/            # concrete adapters + config
│   ├── settings.py            # pydantic-settings, reads ai/.env
│   ├── dependencies.py        # provider factory / singleton wiring (FastAPI Depends)
│   ├── openai_adapter.py      # OpenAILLMProvider, OpenAIEmbeddingProvider
│   └── local_adapter.py       # Local/self-hosted equivalents (e.g. Ollama)
└── services/                  # use-case orchestration, composed from domain ports
```
Provider selection is env-driven (`LLM_PROVIDER`/`EMBEDDING_PROVIDER` = `openai` or `local`) via `infrastructure/dependencies.py` — add a new provider by implementing the `LLMProvider`/`EmbeddingProvider` ABCs in `domain/ports.py`, not by branching in routes. This module was just reorganized from a flatter `core/models/routes/services` layout into this ports-and-adapters shape (see recent commits); some route handlers reference service classes that don't exist yet under `ai/services/` — check before assuming a route is wired end to end.

The full 11-phase pipeline (upload → Docling extraction → cleaning → FTS indexing → embedding → query encoding → pgvector retrieval → [reranking, not implemented] → prompt augmentation → LLM answer → summarization) and which Docker service/file executes each phase is documented in `docs/rag_pipeline_service_map.md` — read it before changing anything in the ingestion or Q&A flow. Note the gateway talks to Postgres directly via `asyncpg` for vector search, not through Django.

### Frontend (`frontend/src/`)
```
api/         # Axios clients, one per domain (auth, storage, audit, notifications, ...)
features/    # page-level components, grouped by domain (auth, records, review, ...)
components/  # shared UI (components/ui) and layout components
store/       # Zustand stores
hooks/       # shared React hooks
types/       # TypeScript interfaces (mirror backend serializer shapes)
router/      # React Router config, PrivateRoute guard
```
Stack: Zustand for state, React Hook Form + Zod for forms, TanStack Table for data grids, Axios for HTTP, react-markdown for rendering AI responses.

## Documentation map

`docs/README.md` is the index. Source-of-truth order: SRS/SDD PDFs (repo root) → `docs/` process docs (living) → code + `.env.example`. Notably:
- `docs/SDLC_PROCESS.md` — branching/PR workflow, quality gates
- `docs/SECURITY.md` + `docs/SECURITY_RISK_REGISTER.md` — read before touching auth/RBAC
- `docs/TRACEABILITY_MATRIX.md` — SRS FR/NFR → code/UI/tests mapping; update in the same PR when an FR/NFR is touched
- `docs/rag_pipeline_service_map.md`, `docs/docker_compose_rag_services.md` — AI/RAG infra
- `docs/document_requirements_architecture.md` — target document model (see above)

Modules 5 (hierarchical submission workflow) and 7 (KPI dashboards) are marked draft/unstable in the SRS — don't hard-code assumptions about their final shape into the UI.
