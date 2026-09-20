# CLAUDE.md — IRIS

Guidance for AI assistants working in this repository. Keep changes grounded in what the code actually does.

## Repository

IRIS is an institutional research and IP disclosure workflow system for CIT-U, built as a four-person capstone thesis with a commercial track.

**The thesis contribution is the workflow**: type-differentiated routing, parallel multi-office clearance, and **clearance-aware resubmission** — when one office requires revisions, only that office's clearance resets and the others are preserved. **RAG is thesis-critical too, as of 2026-09-04** — the earlier "not the AI" framing is reversed; see [ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) §Research Impact (amended) and the Scope rule below.

## Baseline branch

**`main`.** Cut every branch from it and target it in PRs. `feat/rag-service` — where the RAG/AI work in this file was built — is merged in as of this commit and is no longer a separate baseline.

`refactor/docker-service` is **retired** — it is fully contained in `main` (`git merge-base --is-ancestor` confirms it), so cutting from it now would branch from a dead ref. Earlier guidance naming it as the baseline, or as an "integration branch" alongside `main`, is superseded by this line.

## Jira and Git convention

**Every development task corresponds to a Jira issue, and the issue key is the identifier that ties the whole lifecycle together.**

**Branch** — `<type>/IR-XXX-short-description`, types `feature` `fix` `refactor` `test` `docs` `chore`:
```
feature/IR-124-rag-retrieval      fix/IR-131-pdf-validation
test/IR-140-document-ingestion    docs/IR-150-rag-architecture
```

**Commit** — Conventional Commits with the key as scope:
```
feat(IR-124): implement RAG retrieval
fix(IR-131): validate uploaded PDFs
```

**PR title** — `IR-124 Implement RAG retrieval`.

### Rules

1. **Identify the Jira issue before starting.** Read it and its acceptance criteria; confirm it is the right thing to work on.
2. **Never invent a Jira issue key.** If no issue exists for substantive work, **create one first or flag it** — do not fabricate an identifier or work without one.
3. Create the branch from the integration branch, named per the convention.
4. Move the card to **In Progress** when you start.
5. Implement, adding or updating tests where applicable.
6. Run the relevant checks and record what you ran and what happened.
7. Commit with the key in the scope. **No AI attribution** — no `Co-Authored-By`, no generated-with trailer.
8. Push **and open the PR in the same step.** A pushed branch without a PR is incomplete work.
9. Report CI and test status honestly, including failures and why.
10. Update the Jira card, moving it to **In Review** only once the PR exists.
11. **Never mark work Done because the implementation was written.** Done is defined in `docs/engineering/DEFINITION_OF_DONE.md` §4 and requires review, approval and evidence.

Full specification: [`docs/engineering/SDLC.md`](docs/engineering/SDLC.md) §2-4a.

## Architecture — what actually exists

| Component | Reality |
|---|---|
| Backend | Django 5 + DRF, `backend/apps/{accounts,records,reviews,documents,notifications,audit,ai}` |
| Frontend | React 18 + TypeScript + Vite + Tailwind + Zustand, `frontend/src/` |
| Database | PostgreSQL. `Record.search_vector` (GIN, weighted) is maintained and **works** |
| Async | Celery + Redis |
| Deployment | Docker Compose, dev and prod |
| **AI gateway** | `ai/` is FastAPI in ports-and-adapters shape: `domain/ports.py`, `infrastructure/openai_adapter.py` (the only adapter — no local model, ADR-008/015), `api/`. **[ADR-014](docs/adr/014-ai-gateway-as-a-service.md) adopts it as a sixth service, under five preconditions** — service-to-service auth, no public port, no CORS, **no direct DB access** (Django owns retrieval and visibility filtering), and it must boot. **[ADR-017](docs/adr/017-asgi-deployment-for-gateway-streaming.md) adds a sixth requirement on Django's side**: ASGI deployment (`gunicorn` + `uvicorn.workers.UvicornWorker`), so Django can call the gateway without blocking one of its four workers. **Corrected 2026-09-17, verified by importing the app**: the gateway **boots** and mounts `/api/v1/ai/ask` and `/api/v1/ai/embed` — `ai/services/chat_service.py` and `embedding_service.py` both exist (IR-156). The earlier "`chat_service` does not exist" claim is stale and removed. What is still undone: auth, CORS and the public-port preconditions, and `backend` still runs plain WSGI. **[ADR-024](docs/adr/024-embedding-path-bypasses-the-gateway.md) takes embedding off the gateway entirely** — `tasks.embed_record` posted to `/api/v1/ai/internal/embed/` (a route that does not exist), and `EmbedResponse` returns no vector field anyway, so that call could never have worked. Django now embeds in-process via the `EmbeddingProvider` port — **done in IR-281**, for both record-level and chunk-level vectors, with a test that fails if any module under `apps/ai/` reads `AI_GATEWAY_URL` again. The gateway keeps only its ADR-014 streaming-chat mandate. Tracked in [IR-58](https://citiris.atlassian.net). Do not deploy it until all preconditions hold |
| **Ask IRIS (chat)** | **Implemented, in Django — not via the AI gateway above — and on chunk-level retrieval as of IR-283.** `POST /api/v1/ai/ask/` (`ChatQueryView`) and `POST /api/v1/ai/search/` (`SemanticSearchView`) answer from **passages**, not from titles and abstracts: the stack is assembled in `apps/ai/composition.py` (degradation → reranking → two-stage vector retrieval) and the views hold no wiring. `composition_root()` is **overridable** (`use_composition_root`), which is what lets `apps/ai/tests/test_ask_http.py` drive the HTTP boundary with the deterministic fakes and no vendor account. Visibility is `Record.objects.visible_to(user)`, applied inside retrieval before anything is scored — the old `publicly_visible()` second rule is gone from this path. Synthesis is `apps/ai/providers/openai_compatible.py` (`LLM_API_KEY`, `LLM_MODEL`); when no model is reachable the answer is replaced by an explicit unavailable state and the sources are still returned (ADR-008) — **the extractive fallback that composed an answer out of the sources is gone**. `GET /api/v1/ai/status/` reports the active `EmbeddingSpace` and whether generation is configured, replacing the hardcoded `"postgres_fts"`. **Citations are Passages as of IR-284** — each one carries its record, the page and the quoted text, `/ai/search/` returns the same shape, and the Record cards ride alongside both so the interface needs no fetch per citation. Acting on a citation opens the paper at that page (`/records/<id>?page=N` → `#page=N`). **`apps/ai/services/` is gone (IR-285)** — the record-level pipeline, its full-text retrieval module and `llm_generator`, plus the unreferenced legacy `text_chunker`, `vector_store` and `summarizer`. There is one retrieval stack and one visibility predicate: `GET /records/<id>/similar/` moved onto record-vector similarity (`apps/ai/similarity.py`, ADR-029 §5/§7) and was the last caller of `publicly_visible()` on a retrieval path. `apps/ai/tests/test_one_retrieval_stack.py` fails if either comes back. **Nothing real is indexed yet**: the disclosure gate refuses every record while `Record` carries no embargo field (IR-250), so on a live deployment every question answers "no readable sources" until that lands |
| **pgvector** | **Implemented.** `apps/ai/models/embedding.py` has a real `VectorField` + HNSW `vector_cosine_ops`, migrations `0001`/`0002`. ADR-007. **Migration `0002` hardcodes `dimensions=1536`** while the model reads a setting — [ADR-015](docs/adr/015-voyage-embedding-and-reranking.md) replaces this with `EmbeddingSpace`, and IR-280 re-dimensioned both vector columns to 1024. **Consumed by Ask IRIS retrieval as of IR-283** — the earlier "not yet consumed" line is superseded |
| **Chunking** | **Implemented end to end (IR-89 A–H).** [ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) makes the chunk the retrievable unit. `apps/ai/chunking/` holds the domain, strategies and context-path decorator; `apps/ai/repositories.py` persists a `ChunkSet` and swaps it atomically, re-embedding only chunks whose `text_hash` changed; `apps/ai/ingestion/` holds the lifecycle transition table, the job idempotency key, and `pipeline.py`, which normalizes, chunks and persists. `ai.tasks.chunk_record_document` runs it in a worker and is queued by `documents.tasks.extract_pdf_text`, so an upload reaches an active chunk set with no manual step. **What is not done is IR-116's actual exit criterion**: nobody has read fifty chunks from a real submission, so `AI_CHUNK_MAX_TOKENS=512` and the front-matter policy are untested defaults. **That setting counts whitespace words, not tokenizer tokens** — measured against docling-core's `HybridChunker` on the same PDF it is ~44% more real BPE tokens than it reads as, and IR-243 deliberately left the number alone rather than recalibrate it ahead of IR-133's recall@10 evidence. `manage.py inspect_chunks <record_id>` is the tool for that. **Chunk vectors are computed as of IR-281**: `apps/ai/indexing.py` embeds an active chunk set through the `EmbeddingProvider` port and `ai.tasks.embed_chunk_set` is queued automatically by `chunk_extraction`. **No real corpus can be indexed yet** — the disclosure gate refuses every record because `Record` carries no embargo field (IR-250), and every vector observed so far came from the deterministic fake, not from Voyage. Design: [`docs/chunker_architecture.md`](docs/chunker_architecture.md) |
| **Embedding / rerank provider** | **Voyage, always** — embedding (`voyage-context-4`, a contextualized chunk embedder, 1024 dims default) and reranking, both stages, no alternative provider in scope. **IR-281 moved every embedding call to the contextualized endpoint** (`/contextualizedembeddings`) and added `EmbeddingProvider.embed_document_chunks`, which takes chunks grouped by document — the flat `/embeddings` endpoint serves the standard models and discards the sibling-chunk context this model exists for ([ADR-015](docs/adr/015-voyage-embedding-and-reranking.md)). **Not gated on governance sign-off** — that precondition was dropped 2026-09-04. Still gated on a `DisclosurePolicy` module (per-record IP status/embargo/consent) and confirmed vendor no-training terms |
| **Docling** | **Implemented (IR-107).** [ADR-016](docs/adr/016-docling-structured-extraction.md) amends ADR-006's deferral: the chunker needs structure, and flattening destroys the coordinates citations anchor to. `apps/ai/extraction/` is the `StructuredExtractor` port with `DoclingExtractor` as its only adapter — `POST {DOCLING_API_URL}/v1/convert/file`, over `httpx`. `PdfExtraction` now stores `structure` (the serialized `NormalizedDocument`), `content_hash` and `extractor` alongside `extracted_text`. **There is no fallback extractor**: ADR-016's PyMuPDF clause was dropped (see its divergence note) because a flat-text fallback yields chunks with no regions. The prototype three-tier chain and its three undeclared libraries are deleted |

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
npm test             # vitest run — non-interactive, jsdom, axe-core (IR-210)
npm run test:watch   # vitest in watch mode
# Queries go through the accessible tree (role + accessible name), never a class
# or a test id. axe-core fails the build on serious/critical only, and cannot
# check colour contrast under jsdom — contrast stays a manual check.
# On Windows the runner needs vitest's `forks` pool; see vitest.config.ts.

# Backend  (backend/)
pip install -r requirements/development.txt
python manage.py check
python manage.py migrate
python manage.py runserver
python -m pytest -q                       # pytest.ini + conftest.py (IR-82); db_required
                                          # tests skip cleanly with no Postgres reachable
python manage.py seed_demo                # accounts + Discover catalogue + every pipeline state
                                          # (IR-227). Logins are <role>@cit.edu / IrisDemo123!,
                                          # plus admin@cit.edu (Django superuser, no app role).
                                          # Replaced scripts/seed_demo_{users,records,clearances}.py
                                          # and seed_test_users, all deleted. Idempotent for records;
                                          # re-running resets passwords. Refuses with DEBUG off
                                          # unless --force. --accounts-only for logins alone
python manage.py inspect_chunks <record_id> --limit 50   # read a record's chunks (IR-116)
python manage.py backfill_embeddings --dry-run           # what indexing the corpus would cost (IR-282).
                                   # Prints records/chunks/tokens and an approximate cost, then stops.
                                   # Drop --dry-run to run it inline; --queue hands each record to a
                                   # worker on the `embedding` queue instead. Refuses to start when
                                   # the estimate exceeds AI_EMBEDDING_TOKEN_CEILING (--token-ceiling
                                   # overrides; 0 disables). Resumable and idempotent: it embeds only
                                   # chunks with no vector in the space, recomputed every run.
                                   # --space N fills a pending space (chunk vectors only).
                                   # Verified on the dev database 2026-09-20: 26 records, 1,236 chunks,
                                   # 381,073 estimated tokens
python manage.py promote_embedding_space --space N --check   # is this space ready to go live? (IR-282)
                                   # Drop --check to promote. Refuses while any active chunk lacks a
                                   # vector in that space and names the short records. Nothing
                                   # promotes automatically

# Docker  (repo root)
python scripts/setup_env.py         # REQUIRED first (IR-154): creates the repo-root .env Compose
                                   # interpolates DB_NAME/DB_USER/DB_PASSWORD from, deriving it from
                                   # backend/.env so it matches an existing postgres_data volume.
                                   # Idempotent; never overwrites. Without it Compose stops by name
docker compose up --build          # ai-gateway needs ./ai/.env (gitignored, absent in CI) or Compose stops.
                                   # Given one it now boots (IR-156); it is still undeployable per ADR-014's
                                   # auth/CORS/public-port preconditions. Nothing on the indexing path calls
                                   # it any more — see ADR-024
docker compose config              # validate without building
```

**Do not document a command without verifying it runs.** Several obvious-looking commands currently fail.

## Known-broken — do not be surprised

- **Corrected on this merge (2026-09-06), verified against the code, not assumed:** the URLconf imports cleanly (`manage.py check` and `python -c "import config.urls"` both pass) and `apps/ai` has real, field-bearing models (`chunk.py`, `embedding.py`, `embedding_space.py`, `ingestion_job.py`) — the "six undefined names" and "field-less stub models" claims below were stale and are removed. `frontend/nginx.conf` no longer serves `/media/` unauthenticated — the nginx alias, prod web-container mount, and Django's `DEBUG` `static()` route were all removed (IR-152); see `docs/testing/TRACEABILITY.md` NFR-S4
- **Fixed 2026-09-09 (IR-153):** `RecordViewSet.get_queryset` now applies `Record.objects.visible_to(user)` on **every** action — office staff, owner, assigned adviser, or the public catalogue. Because the filtering is in the queryset rather than a permission class, a refusal is a **404 identical to a missing record**, so the API never confirms someone else's draft exists. `list` narrows further to `PUBLICLY_VISIBLE_STATUSES` so Discover stays a catalogue rather than surfacing your own drafts. Supersedes the "returns any record to any authenticated user" claim previously here
- **Fixed 2026-09-07 (IR-164):** `CELERY_TASK_ROUTES` and `CELERY_TASK_DEFAULT_QUEUE` are now set in `config/settings/base.py`, routing `extract_pdf_text` to `extraction`, `embed_record` to `embedding`, and everything else (including `chunk_record_document`) to `default` — matching the three queues docker-compose's workers actually consume. Verified against the real stack, not just asserted from config: a task dispatched over the real Redis broker was observed consumed and completed by the real `celery-default` and `celery-extraction` containers. Supersedes the "no Celery task is ever processed" claim previously here — see `docs/engineering/DEVELOPMENT.md` §6
- **Audited and fixed 2026-09-09 (IR-153):** `apps/documents/` has now been swept endpoint-by-endpoint. Six endpoints resolved a record from a request parameter with **no ownership check at all** — `submit/`, `records/<id>/slots/`, `uploads/?record=`, `uploads/create/`, `files/?record=`, and `files/download-all/?record=`, the last returning a ZIP of every supplementary file on any record to anyone who knew its id. All six now go through `authorize_record_documents()`. The five hand-written `get_role_name(...) in STAFF_ROLES or record.owners.filter(...)` checks (four here, one in `apps/reviews/views.py`) are replaced by the single `core.permissions.owns_or_staffs_record()`
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
