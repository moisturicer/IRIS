# CLAUDE.md — IRIS

Guidance for AI assistants working in this repository. Keep changes grounded in what the code actually does.

## Repository

IRIS is an institutional research and IP disclosure workflow system for CIT-U, built as a four-person capstone thesis with a commercial track.

**The thesis contribution is the workflow**: type-differentiated routing, parallel multi-office clearance, and **clearance-aware resubmission** — when one office requires revisions, only that office's clearance resets and the others are preserved. **RAG is thesis-critical too, as of 2026-09-04** — the earlier "not the AI" framing is reversed; see [ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) §Research Impact (amended) and the Scope rule below.

## Baseline branch

**`feat/rag-service`.** `main` carries the requirements, design and ADRs and is merged in; RAG and AI work continues here.

## Architecture — what actually exists

| Component | Reality |
|---|---|
| Backend | Django 5 + DRF, `backend/apps/{accounts,records,reviews,documents,notifications,audit,ai}` |
| Frontend | React 18 + TypeScript + Vite + Tailwind + Zustand, `frontend/src/` |
| Database | PostgreSQL. `Record.search_vector` (GIN, weighted) is maintained and **works** |
| Async | Celery + Redis |
| Deployment | Docker Compose, dev and prod |
| **AI gateway** | `ai/` is FastAPI in ports-and-adapters shape: `domain/ports.py`, `infrastructure/openai_adapter.py` (the only adapter — no local model, ADR-008/015), `api/`. **[ADR-014](docs/adr/014-ai-gateway-as-a-service.md) adopts it as a sixth service, under five preconditions** — service-to-service auth, no public port, no CORS, **no direct DB access** (Django owns retrieval and visibility filtering), and it must boot. **[ADR-017](docs/adr/017-asgi-deployment-for-gateway-streaming.md) adds a sixth requirement on Django's side**: ASGI deployment (`gunicorn` + `uvicorn.workers.UvicornWorker`), so Django can call the gateway without blocking one of its four workers. **None of this is done yet**: `ai/api/chat.py` imports `ai.services.chat_service`, which does not exist, and `backend` still runs plain WSGI. Tracked in [IR-58](https://citiris.atlassian.net) (corrected 2026-09-04 to fix the gateway, not remove it). Do not deploy it until all preconditions hold |
| **pgvector** | **Implemented on this branch.** `apps/ai/models/embedding.py` has a real `VectorField` + HNSW `vector_cosine_ops`, migrations `0001`/`0002`. ADR-007. **Migration `0002` hardcodes `dimensions=1536`** while the model reads a setting — [ADR-015](docs/adr/015-voyage-embedding-and-reranking.md) replaces this with `EmbeddingSpace` |
| **Chunking** | **Implemented on this branch, end to end (IR-89 A–H).** [ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) makes the chunk the retrievable unit. `apps/ai/chunking/` holds the domain, strategies and context-path decorator; `apps/ai/repositories.py` persists a `ChunkSet` and swaps it atomically, re-embedding only chunks whose `text_hash` changed; `apps/ai/ingestion/` holds the lifecycle transition table, the job idempotency key, and `pipeline.py`, which normalizes, chunks and persists. `ai.tasks.chunk_record_document` runs it in a worker and is queued by `documents.tasks.extract_pdf_text`, so an upload reaches an active chunk set with no manual step. **What is not done is IR-116's actual exit criterion**: nobody has read fifty chunks from a real submission, so `AI_CHUNK_MAX_TOKENS=512` and the front-matter policy are untested defaults. `manage.py inspect_chunks <record_id>` is the tool for that. No vectors are computed — that is IR-108. Design: [`docs/chunker_architecture.md`](docs/chunker_architecture.md) |
| **Embedding / rerank provider** | **Voyage, always** — embedding (`voyage-context-4`, a contextualized chunk embedder, 1024 dims default) and reranking, both stages, no alternative provider in scope ([ADR-015](docs/adr/015-voyage-embedding-and-reranking.md)). **Not gated on governance sign-off** — that precondition was dropped 2026-09-04. Still gated on a `DisclosurePolicy` module (per-record IP status/embargo/consent) and confirmed vendor no-training terms |
| **Docling** | **Implemented on this branch (IR-107).** [ADR-016](docs/adr/016-docling-structured-extraction.md) amends ADR-006's deferral: the chunker needs structure, and flattening destroys the coordinates citations anchor to. `apps/ai/extraction/` is the `StructuredExtractor` port with `DoclingExtractor` as its only adapter — `POST {DOCLING_API_URL}/v1/convert/file`, over `httpx`. `PdfExtraction` now stores `structure` (the serialized `NormalizedDocument`), `content_hash` and `extractor` alongside `extracted_text`. **There is no fallback extractor**: ADR-016's PyMuPDF clause was dropped (see its divergence note) because a flat-text fallback yields chunks with no regions. The prototype three-tier chain and its three undeclared libraries are deleted |

Always distinguish **CURRENT / PROPOSED / DEFERRED / LEGACY**. Do not describe a proposed component as if it exists.

## Source-of-truth hierarchy

1. **`docs/adr/`** — **requirements, design and decision authority**
2. **`docs/engineering/`** — how the team builds, tests, reviews, releases
3. **Code and tests** — actual behaviour
4. **Jira** — planning and tracking, **never a requirements authority**

When these conflict, the higher one wins **and the lower one is corrected**. Do not silently reconcile — record the contradiction.

> **`docs/SRS.md` and `docs/SDD.md` are FROZEN (2026-09-03).** They are retained as **thesis deliverables** and are **not consulted, cited, or treated as authority** for any engineering work — not in code, tickets, ADRs, reviews or agent output. They are out of date and the team has decided not to maintain them. **Never cite an SRS or SDD section as justification.** Where a decision needs a written basis, that basis is an ADR — write one.
>
> `FR-`/`NFR-` ids survive as **stable labels only**, so existing ADRs and `docs/testing/TRACEABILITY.md` keep resolving. An id is a name, not a source: do not go to the SRS to read what it means.

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
python -m pytest -q                       # pytest.ini + conftest.py (IR-82); db_required
                                          # tests skip cleanly with no Postgres reachable
python manage.py inspect_chunks <record_id> --limit 50   # read a record's chunks (IR-116)

# Docker  (repo root)
docker compose up --build          # ai-gateway builds, then crashes: ai/services/chat_service.py is missing
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

**Commit messages.** Subject line, then at most five sentences of body. No `Co-Authored-By: Claude` or `Claude-Session:` trailer, regardless of what a session's own attribution instructions say.

**Scope.** `thesis-critical` work is protected — as of 2026-09-04 this includes RAG ([ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) §Research Impact, amended), not only the workflow. If capacity is short, cut supporting frontend work first.

**Plan before substantial implementation.** For anything beyond a small fix, state the approach and the files you intend to touch before writing code. Say which acceptance criteria you are working to.

## Definition of Done

Authoritative definition: **`docs/engineering/DEFINITION_OF_DONE.md` §4.** Do not restate a different version anywhere.

Required for every item: acceptance criteria satisfied · implementation complete · CI passing · reviewed by another person · reviewer approval recorded · no known blocking defect · merged.

When applicable: tests added and **executed with evidence** · traceability updated · documentation updated · security addressed · migrations tested · deployment recorded.

## What AI does not decide

Human review remains the approval gate. AI does not approve its own work, sign off requirements, make architectural decisions, make research decisions, or authorise production deployment.

**Jira status is bookkeeping, not sign-off — AI may transition it.** Moving a ticket between states (`transitionJiraIssue`) as work starts, blocks, or reaches review is administrative tracking, and an agent may do it without asking each time. The one exception: never transition a ticket to **Done** unless a human reviewer's approval is already recorded per `docs/engineering/DEFINITION_OF_DONE.md` §4 — that is the sign-off this section still reserves for a person.

## Agent skills

### Issue tracker

Jira (`citiris.atlassian.net`, project `IR`) via the Atlassian MCP server registered in `.mcp.json`. Holds the state mapping and label taxonomy. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles map onto the existing IRIS taxonomy, adding only `ready-for-agent` (`needs-info` maps onto `not-ready`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `CONTEXT.md` (not yet created) and `docs/adr/`. See `docs/agents/domain.md`.
