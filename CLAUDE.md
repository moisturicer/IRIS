# CLAUDE.md — IRIS

Guidance for AI assistants working in this repository. Keep changes grounded in what the code actually does.

## Repository

IRIS is an institutional research and IP disclosure workflow system for CIT-U, built as a four-person capstone thesis with a commercial track.

**The thesis contribution is the workflow**, not the AI: type-differentiated routing, parallel multi-office clearance, and **clearance-aware resubmission** — when one office requires revisions, only that office's clearance resets and the others are preserved.

## Baseline branch

**`refactor/docker-service`.** Not `main`. All work starts here.

## Architecture — what actually exists

| Component | Reality |
|---|---|
| Backend | Django 5 + DRF, `backend/apps/{accounts,records,reviews,documents,notifications,audit,ai}` |
| Frontend | React 18 + TypeScript + Vite + Tailwind + Zustand, `frontend/src/` |
| Database | PostgreSQL. `Record.search_vector` (GIN, weighted) is maintained and **works** |
| Async | Celery + Redis |
| Deployment | Docker Compose, dev and prod |
| **AI gateway** | `ai/` exists in the tree (FastAPI, added in `7f73e97`) but **is not deployed and does not run** — it imports `ai.services.chat_service`, which does not exist, and has no authentication. **[ADR-012](docs/adr/012-ai-provider-abstraction-not-a-service.md) settles this:** the provider abstraction is ported into Django as `apps/ai/providers/`; the service is not adopted. Compose still declares `ai-gateway`; IR-58 removes it. **Do not build on `ai/`** |
| **pgvector** | **Not yet implemented.** ADR-007 selects it; the service classes are `pass` bodies |
| **Docling** | **Not implemented.** SRS-specified, deferred by ADR-006 pending an SRS amendment |

Always distinguish **CURRENT / PROPOSED / DEFERRED / LEGACY**. Do not describe a proposed component as if it exists.

## Source-of-truth hierarchy

1. **`docs/SRS.md`** — requirements authority
2. **`docs/SDD.md`** — system and design authority
3. **`docs/adr/`** — architectural decisions and rationale
4. **`docs/engineering/`** — how the team builds, tests, reviews, releases
5. **Code and tests** — actual behaviour
6. **Jira** — planning and tracking, **never a requirements authority**

When these conflict, the higher one wins **and the lower one is corrected**. Do not silently reconcile — record the contradiction.

## Commands that actually work

```bash
# Frontend  (frontend/)
npm install
npm run dev          # vite
npm run build        # tsc && vite build
npm run lint         # eslint src --ext ts,tsx
# NOTE: there is no `npm test` — no test runner is installed yet

# Backend  (backend/)
pip install -r requirements/development.txt
python manage.py check
python manage.py migrate
python manage.py runserver
# NOTE: there is no pytest config and no test files yet

# Docker  (repo root)
docker compose up --build          # currently FAILS: ai-gateway requires ./ai/.env, which does not exist
docker compose config              # validate without building
```

**Do not document a command without verifying it runs.** Several obvious-looking commands currently fail.

## Known-broken — do not be surprised

- `backend/apps/records/views.py` has **six undefined names**; `config/urls.py:11` includes it, so the URLconf fails at import and **no endpoint responds**
- `frontend/nginx.conf:52-56` serves `/media/` unauthenticated — every uploaded PDF is public
- `RecordViewSet.get_queryset` filters only on `list`; `retrieve` returns any record to any authenticated user
- Six `documents/` endpoints have no ownership check
- `apps/ai` models are shadowed by field-less stubs; service classes are `pass`
- `AuditEvent` has 14 event types, **none of them workflow events**

## Rules

**Security.** Never commit secrets. Never widen CORS. Never add an endpoint without an object-level permission check. Never expose a file path that bypasses Django's permission layer. Treat visibility filtering as one predicate used everywhere — including RAG retrieval, so a citation can never point at an unreadable record.

**Migrations.** Every model change ships with a migration. Test it against a copy of a realistic database, not only an empty one. Never edit an applied migration.

**Environment and secrets.** Configuration comes from environment variables. `backend/.env.example` documents the keys and holds no real values. The app should fail to start on a missing required secret rather than defaulting silently.

**Tests.** Do not modify a test to make it pass. If a test is wrong, fix it deliberately and say so in the PR. **A requirement is not complete because code exists for it** — it is complete when a test demonstrates it and the evidence is recorded.

**Traceability.** A change that implements or alters a requirement updates `docs/testing/TRACEABILITY.md`.

**Scope.** `thesis-critical` work is protected. If capacity is short, cut RAG and supporting frontend work first.

**Plan before substantial implementation.** For anything beyond a small fix, state the approach and the files you intend to touch before writing code. Say which acceptance criteria you are working to.

## Definition of Done

Authoritative definition: **`docs/engineering/WORK_ITEM_LIFECYCLE.md` §9.** Do not restate a different version anywhere.

Required for every item: acceptance criteria satisfied · implementation complete · CI passing · reviewed by another person · reviewer approval recorded · no known blocking defect · merged.

When applicable: tests added and **executed with evidence** · traceability updated · documentation updated · security addressed · migrations tested · deployment recorded.

## What AI does not decide

Human review remains the approval gate. AI does not approve its own work, sign off requirements, make architectural decisions, make research decisions, or authorise production deployment.
