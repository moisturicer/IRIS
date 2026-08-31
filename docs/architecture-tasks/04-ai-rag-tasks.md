# 04 — AI / RAG Tasks

Eight tasks. **Two of eleven pipeline phases currently exist.** These tasks build the other nine, aligned to the SRS rather than to the stale Jira tickets.

---

## Governing context

`docs/rag_pipeline_service_map.md` documents eleven phases in the present tense. Verified against the working tree:

| Phase | Documented | Reality |
|---|---|---|
| 1 · PDF upload | `SubmitDocumentView` | **Exists** (no ownership check — `SEC-03`) |
| 2 · Extraction | Docling `/convert` | **Never happens** — code calls a 3-tier chain whose libraries are uninstalled |
| 3 · Cleaning | `_clean_text()` | **Exists**, unreachable — phase 2 raises first |
| 4 · FTS indexing | `records/signals.py` | **Exists and works** |
| 5 · Embedding | `celery-embedding` → gateway | **Never happens** — `sentence_transformers` uninstalled, models shadowed |
| 6–10 · Query, retrieval, prompt, LLM | `ai-gateway/routes/*.py` | **Files do not exist** |
| 11 · Summarization | gateway | **Does not exist**; `SummarizeView` returns HTTP 501 |

**The SRS settles the stack**, and it disagrees with Jira `IR-9` / `IR-15` / `IR-35`:

- **pgvector, not Qdrant** — SRS §456: *"eliminating the need for a separate vector database service"*; §624: *"There is no separate vector database service or additional network port."* 13 SRS mentions vs 2 for Qdrant (both incidental).
- **No LangChain requirement** — 1 SRS mention, in the change history only.
- **No reranking requirement** — 0 SRS mentions of Cohere.
- **Docling-serve is required** — FR-M3-01, service table §402, interface Table 18 §481-489; PyMuPDF/pytesseract are the *fallback* per §361.
- **RAG lives in Django** — SRS §478 names `SemanticSearchView` and `AskView` (the `apps/ai` views) as the consumers of pgvector. **No FastAPI gateway exists in the SRS service table.**

---

# AI-01 · Restore PDF text extraction (interim, PyMuPDF)

## Objective
Make text extraction succeed on a real upload, unblocking FTS, embeddings and every downstream phase.

## Problem
`documents/tasks.py` runs a three-tier extractor chain. **None of the three libraries is installed**, so every extractor raises `ImportError`, the chain raises `RuntimeError`, the task retries three times and marks the extraction permanently `failed`.

## Current State

| Extractor | Imports | In `requirements/base.txt`? |
|---|---|---|
| `_extract_with_opendataloader` | `unstructured.partition.auto` | **No** |
| `_extract_with_pymupdf` | `fitz` (PyMuPDF) | **No** |
| `_extract_with_tesseract` | `pytesseract`, `PIL`, `fitz` | **No** |

`requirements/base.txt:14-17` records the deliberate removal: *"REMOVE when Docling + pgvector migration is complete: (Removed legacy ML dependencies)."* The Docling migration was never made — `documents/tasks.py` never reads `settings.DOCLING_API_URL`, and the file's own 27-line header TODO still describes the change as pending.

`_clean_text()` is written and correct.

## Proposed State
`pymupdf` in requirements; the chain reduced to PyMuPDF for now; extraction succeeds on born-digital PDFs.

## Scope
Add `pymupdf` to `requirements/base.txt`; keep the chain's structure so tiers can return; verify end-to-end on a committed fixture PDF.

## Out of Scope
Docling-serve integration — that is `AI-02` and is the SRS target state.

## Technical Approach
Interim only. A submitted thesis is a born-digital, text-layer PDF, which PyMuPDF handles in ~50 MB with no external service. Scanned documents will extract empty and be marked `failed` — honest and visible, pending `AI-02`.

## Dependencies
`BE-03` (queue routing) — without it the task never runs.

## Risks
Low. **Licence note:** PyMuPDF is AGPL-3.0 with a commercial option. Fine for a thesis and internal university deployment; flag for `FW-06` before any commercial phase. `pdfplumber` (MIT) is the drop-in fallback.

## Security Impact
None.

## Performance Impact
Enables `NFR-P4` (10-page/10 MB PDF indexed within 30 s) to be measured at all.

## Deployment Impact
+~30 MB in the image; avoids a 4 GB Docling container for now.

## Framework Impact
`+pymupdf`.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] Uploading a text-layer PDF results in `PdfExtraction.status == "done"` with non-empty `extracted_text`.
- [ ] The record's `search_vector` is populated afterwards and the document is findable by full-text search.
- [ ] A test extracts a committed 2-page fixture PDF and asserts text content.
- [ ] A scanned/image PDF is marked `failed` with a clear error, not a silent empty success.
- [ ] `requirements/base.txt` lists every library the code imports.

## Definition of Done
Merged; fixture test in CI; `NFR-P4` timing captured for `VAL-04`.

## Complexity
XS

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`ai`, `backend`, `mvp-blocker`, `fr-m3-01`, `extraction`

---

# AI-02 · Integrate Docling-serve as the SRS-specified extractor

## Objective
Deliver FR-M3-01 as specified: PDF bytes POSTed to a self-hosted Docling-serve instance, returning structured Markdown.

## Problem
`AI-01` is an interim fix. The SRS specifies Docling-serve as the primary extractor, with PyMuPDF/pytesseract as the fallback when it is unavailable.

> **This corrects `docs/architecture-review/` (04, 08)**, which recommended deferring Docling. That recommendation ignored that Docling is SRS-specified in four places. It stands only as *sequencing* advice — unblock with PyMuPDF first — not as a target-state decision.

## Current State
`docker-compose.yml` runs `quay.io/docling-project/docling-serve:latest` with a 4 GB memory limit and a healthcheck. `settings/base.py:181` defines `DOCLING_API_URL`. Compose passes `DOCLING_API_URL=http://docling:5001`.

**No code reads it.** `grep -rn "DOCLING_API_URL" backend/apps/` returns nothing. The container runs and is called by nobody.

SRS §481-489 (Table 18) specifies the contract: POST raw PDF bytes to Docling-serve, receive structured Markdown, clean it, store in `PdfExtraction.extracted_text`. SRS §361 requires automatic retry and fallback to PyMuPDF/pytesseract when Docling is unavailable.

## Proposed State
`extract_pdf_text` POSTs to `<DOCLING_API_URL>/convert`; on failure it retries, then falls back to PyMuPDF per §361; `_clean_text()` is applied to the result either way.

## Scope
- Replace the primary extractor with a Docling HTTP call using `requests` (SRS §479 names it) or `httpx` (already in requirements)
- Keep PyMuPDF as the documented fallback; keep `_clean_text()`
- Timeout, retry and fallback behaviour per §361
- Confirm the Docling container is reachable and healthy

## Out of Scope
Whether Docling ships in the MVP at all — that is decision `FW-03`. This task implements the SRS answer; `FW-03` may defer it.

## Technical Approach
`EXTRACTION_TIMEOUT` is already passed in Compose (900 s) — honour it. Test the fallback path by pointing `DOCLING_API_URL` at a closed port.

## Dependencies
`AI-01`, `BE-03`, and decision `FW-03`.

## Risks
Medium. 4 GB is over half a small host's memory (`DEP-06`). Docling's first-run model load is slow — the Compose healthcheck already allows a 60 s `start_period`.

## Security Impact
Positive: extraction stays on-premise, satisfying the SRS's RA 10173 constraint that raw files never leave university hardware.

## Performance Impact
Must still meet `NFR-P4` (30 s for a 10-page/10 MB PDF). **Measure this** — Docling OCR on a scanned document may exceed it.

## Deployment Impact
+4 GB memory. Materially changes hosting options (`DEP-06`).

## Framework Impact
`+requests` if not already transitive. Retains the `docling` service.

## MVP Classification
**MVP Required** if `FW-03` confirms Docling · **Post-MVP** if `FW-03` defers it

## Acceptance Criteria
- [ ] A PDF upload results in a POST to `<DOCLING_API_URL>/convert` (assert via a mocked HTTP layer).
- [ ] Returned Markdown is cleaned by `_clean_text()` and stored in `PdfExtraction.extracted_text`.
- [ ] With Docling unreachable, extraction falls back to PyMuPDF and still reaches `status == "done"` (§361).
- [ ] A scanned PDF extracts non-empty text via Docling's OCR.
- [ ] A 10-page/10 MB PDF completes within 30 s (`NFR-P4`), measured and recorded.

## Definition of Done
Merged; fallback test in CI; `NFR-P4` timing recorded; `FW-03` ADR referenced.

## Complexity
M

## Suggested Jira Type
Story

## Suggested Priority
High

## Suggested Labels
`ai`, `backend`, `docling`, `fr-m3-01`, `nfr-p4`, `srs-alignment`

---

# AI-03 · Store embeddings in pgvector, remove pickle

## Objective
Deliver FR-M3-03 as the SRS specifies: a `VectorField` with an HNSW index, queried with the cosine distance operator.

## Problem
The stack advertises pgvector everywhere and uses none of it. Vectors are pickled into a `BinaryField` and searched with a Python loop over the entire table.

## Current State
- `apps/ai/models.py:26` — `embedding = models.BinaryField()`, with a 20-line TODO describing exactly this migration
- `apps/ai/tasks.py:57` — `"embedding": pickle.dumps(embedding)`
- `apps/ai/views.py` — loads **every** `RecordEmbedding`, `pickle.loads` each, computes cosine similarity in NumPy, sorts in Python. O(n) rows into application memory per query
- `pgvector` is **not** in `INSTALLED_APPS` and is listed **twice** in `requirements/base.txt` (`>=0.3` line 11, `>=0.2.4` line 21)
- The Compose `db` image is already `pgvector/pgvector:pg16`

SRS §462-478 specifies `pgvector 0.5+`, `VectorField`, HNSW, and the `<=>` operator. **Jira `IR-9` and `IR-15` specify Qdrant instead — they contradict the SRS.**

## Proposed State
`VectorField(dimensions=N)`, an HNSW index created in a migration, retrieval via the ORM's `CosineDistance` annotation with `LIMIT k`. No `pickle` anywhere.

## Scope
- Add `pgvector` to `INSTALLED_APPS`; deduplicate the requirements entry
- Replace `BinaryField` with `VectorField`; add an HNSW index migration
- Rewrite `embed_record` to store the raw vector
- Rewrite search to use `CosineDistance` with `LIMIT`
- Remove every `pickle` import and call

## Out of Scope
Which embedding provider supplies the vector (`AI-05` — it determines `dimensions`).

## Technical Approach
Follow the TODO in `apps/ai/models.py`, which is correct. `dimensions` must match the provider (1536 for `text-embedding-3-small`), so `AI-05` should be decided first or the migration will need redoing.

## Dependencies
`BE-04` (un-shadow models, create migrations). `AI-05` (provider fixes `dimensions`).

## Risks
Low — no production embeddings exist to migrate.

## Security Impact
**Removes an unsafe-deserialization pattern** (`SEC-11`). `pickle.loads` on database content is a code-execution primitive one SQL-injection or compromised restore away from the application.

## Performance Impact
Large. Replaces an O(n) in-Python scan with an indexed ANN query — the difference between meeting and missing `NFR-P3`.

## Deployment Impact
Requires the pgvector extension enabled in Postgres (the image provides it; the extension still needs `CREATE EXTENSION`, which the migration should do).

## Framework Impact
`pgvector` correctly wired; duplicate requirement removed. **No Qdrant** — contradicts `IR-9`/`IR-15`, which the SRS overrides.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `RecordEmbedding.embedding` is a `VectorField`.
- [ ] A migration creates the pgvector extension and an HNSW index.
- [ ] `grep -rn "pickle" backend/apps/` returns no matches.
- [ ] Similarity search issues **one** SQL query with `ORDER BY ... <=> ... LIMIT k` (assert with `assertNumQueries` and captured SQL).
- [ ] Retrieval over ≥100 embedded records returns in under 200 ms.
- [ ] `pgvector` appears exactly once in `requirements/base.txt` and is in `INSTALLED_APPS`.

## Definition of Done
Merged with migrations; query-shape test in CI; `IR-9`/`IR-15` rewritten per `12-jira-ready-tasks.md`.

## Complexity
M

## Suggested Jira Type
Story

## Suggested Priority
Critical

## Suggested Labels
`ai`, `backend`, `pgvector`, `fr-m3-03`, `security`, `srs-alignment`

---

# AI-04 · Chunking without LangChain

## Objective
Split extracted text into overlapping chunks for embedding, using explicit code.

## Problem
No chunking exists — `apps/ai/services/text_chunker.py` is `class TextChunkerService: pass`. Jira `IR-15` specifies LangChain's `RecursiveCharacterTextSplitter`; the SRS does not require LangChain.

## Current State
`apps/ai/services/text_chunker.py` — 2 lines, body `pass`. `embed_record` (`apps/ai/tasks.py`) embeds `f"{record.title}. {record.abstract}"` — title and abstract only, **not the extracted full text**, so the chunking step is genuinely absent rather than inlined.

`DocumentChunk` exists in `apps/ai/models/metadata.py` as a field-less stub.

## Proposed State
A `chunk_text(text, size, overlap) -> list[str]` function plus a real `DocumentChunk` model linking chunks to their source record and offset.

## Scope
- Implement chunking as a pure function
- Make `DocumentChunk` a real model (record FK, ordinal, text, offsets)
- Chunk `PdfExtraction.extracted_text`, not just title+abstract

## Out of Scope
Embedding (`AI-05`), retrieval (`AI-06`).

## Technical Approach
Fixed-size overlapping chunks with sentence-boundary preference — roughly 40 lines. **Deletion test on LangChain:** removing it moves complexity out of a large dependency into readable code, which is a gain, not a relocation. IRIS has one chain, not an agent graph.

## Dependencies
`AI-01`/`AI-02` (needs real extracted text). `BE-04` (real models).

## Risks
Low. Chunk size and overlap affect retrieval quality — make them settings, not literals, so `VAL-08` can tune them.

## Security Impact
None.

## Performance Impact
Chunk count drives embedding cost and count. Record both for `VAL-18`.

## Deployment Impact
None.

## Framework Impact
**No LangChain.** Contradicts `IR-15` — see `FW-02` and `12-jira-ready-tasks.md`.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `chunk_text` is a pure function with unit tests covering empty input, shorter-than-chunk input, and exact-boundary input.
- [ ] Chunks overlap by the configured amount; concatenating them with overlap removed reproduces the source text.
- [ ] `DocumentChunk` rows are created for a processed record and link back to it.
- [ ] Chunk size and overlap are configurable via settings.
- [ ] `grep -rn "langchain" backend/` returns no matches.

## Definition of Done
Merged; unit tests in CI; chunk statistics recorded for `VAL-07`.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`ai`, `backend`, `chunking`, `fr-m3-02`, `srs-alignment`

---

# AI-05 · One embedding/LLM provider behind a protocol

## Objective
Resolve the three-way configuration contradiction and make the provider swappable in one module.

## Problem
Three configuration sources name three different vendors. A developer copying `.env.example` gets a key the settings never read.

## Current State

| Source | Says |
|---|---|
| `settings/base.py:180` | `OPENAI_API_KEY`, comment "GPT-4.1-mini LLM inference + embedding API" |
| `settings/base.py:179` | `AI_EMBEDDING_MODEL` default **`"TBD"`** |
| `backend/.env.example:31` | **`ANTHROPIC_API_KEY=your-anthropic-key`** |
| `backend/.env.example:32` | `AI_EMBEDDING_MODEL=all-MiniLM-L6-v2` — a *local* sentence-transformers model |
| `requirements/base.txt:10` | `openai>=1.30` |
| `apps/ai/services/cohere_reranker.py` | a third vendor, as an empty class |
| `apps/ai/tasks.py:51` | imports `sentence_transformers` — **not in requirements** |

SRS §632: LLM inference via OpenAI GPT-4.1-mini; *"Vector embedding generation will be handled by a third-party embedding API (provider TBD)."* The SRS itself leaves the embedding provider open — so this is a live decision (`FW-06`).

## Proposed State
One provider chosen and recorded; `EmbeddingProvider` and `LLMProvider` protocols; all configuration sources agree; startup fails loudly when a key is missing.

## Scope
- Implement the two protocols with one concrete adapter each
- Align `settings/base.py`, `.env.example` and `requirements/base.txt`
- Replace `AI_EMBEDDING_MODEL="TBD"` with a real default
- Fail fast at startup on a missing key
- Remove `sentence_transformers` usage or add it to requirements — currently neither

## Out of Scope
The provider decision itself (`FW-06`), including the data-governance question of whether abstracts may leave campus.

## Technical Approach
Thin `Protocol` classes, ~20 lines, so tests inject a fake and never call a paid API. This is also what makes `FW-06` reversible.

## Dependencies
Decision `FW-06`. `AI-03` needs the vector dimension this fixes.

## Risks
Low technically. **Governance risk is real:** IRIS manages confidential pre-publication IP. Whether abstracts may be sent to a third party is an institutional decision, not a technical one — `FW-06`.

## Security Impact
Determines whether unpublished research leaves university systems. SRS §197 asserts only "anonymized, extracted text chunks" are transmitted — verify the implementation honours that claim.

## Performance Impact
Provider latency drives `NFR-P3` (3 s p95 chatbot). See `VAL-12`.

## Deployment Impact
API keys become deployment secrets (`DEP-05`).

## Framework Impact
Retains `openai`; drops `sentence_transformers` unless local embeddings are chosen; drops `cohere` entirely (0 SRS mentions).

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `EmbeddingProvider` and `LLMProvider` protocols exist with one adapter each.
- [ ] `settings`, `.env.example` and `requirements` name the **same** provider.
- [ ] `AI_EMBEDDING_MODEL` has a real default, not `"TBD"`.
- [ ] Starting with no API key fails at startup with a clear message, not at first query.
- [ ] Tests inject a fake provider and make zero network calls (assert with a blocked-socket fixture).
- [ ] `grep -rn "sentence_transformers\|cohere" backend/` returns no matches, or the libraries are in requirements.

## Definition of Done
Merged; `FW-06` ADR referenced; `.env.example` verified by a clean-clone setup run.

## Complexity
M

## Suggested Jira Type
Story

## Suggested Priority
Critical

## Suggested Labels
`ai`, `backend`, `configuration`, `provider`, `mvp-required`

---

# AI-06 · Retrieval and grounded answer generation in Django

## Objective
Deliver FR-M4-01 — semantic search and the RAG chatbot — inside the Django application, as the SRS specifies.

## Problem
Phases 6–10 do not exist. `apps/ai/services/rag_pipeline.py`, `vector_retriever.py` and `llm_generator.py` are all `class X: pass`. Jira `IR-35` specifies Qdrant retrieval, Cohere reranking and LangChain orchestration — none of which the SRS requires.

## Current State
`apps/ai/views.py` (shadowed, unreachable) contains `SemanticSearchView` and `AskView` skeletons with extensive TODO comments describing the intended implementation. `AskView` currently returns `{"answer": None, "citations": [...]}` — retrieval without generation.

SRS §478 names `SemanticSearchView` and `AskView` as the consumers of pgvector's `<=>` operator — confirming these Django views, not a separate service, are the specified home.

`config/urls.py` never includes `apps.ai.urls`, so the frontend's `/api/v1/ai/ask/` calls 404.

## Proposed State
`SemanticSearchView` returns top-k records by cosine distance; `AskView` retrieves, builds a prompt, calls the LLM and returns a grounded answer with citations.

## Scope
- Query embedding via `AI-05`'s provider
- pgvector retrieval via `AI-03`'s `CosineDistance` with `LIMIT k`
- Prompt construction from retrieved chunks (explicit string building)
- LLM call via the provider protocol
- Citations as record ids the frontend renders as links
- Route `apps.ai.urls` in `config/urls.py`

## Out of Scope
Reranking — **0 SRS mentions**; explicitly descoped. Conversation persistence (`AI-08`). Summarization (`AI-07`).

## Technical Approach
Roughly 60 lines of explicit Python. Retrieval must respect record visibility — a student must not receive an answer citing another student's unpublished draft. **Reuse `BE-06`'s `visible_to(user)` scope.**

## Dependencies
`AI-03`, `AI-04`, `AI-05`, `BE-04`, `BE-06`. Decision `FW-05` (in-Django vs gateway).

## Risks
Medium. **`NFR-P3` requires a 3 s p95 response; a synchronous LLM round-trip is 3–10 s.** This requirement may be unachievable as designed — see `FW-05` and `VAL-12`. Streaming or an NFR amendment is likely needed.

## Security Impact
**High.** Retrieval must filter by visibility or the RAG endpoint becomes a bypass around every access control in `05-security-tasks.md`. This is the single most important detail in the task.

## Performance Impact
Governed by `NFR-P3`. Retrieval is fast; generation dominates.

## Deployment Impact
None beyond the provider key.

## Framework Impact
No LangChain, no Qdrant, no Cohere. Contradicts `IR-35` — the SRS overrides.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `POST /api/v1/ai/search/` returns top-k records ordered by similarity with scores.
- [ ] `POST /api/v1/ai/ask/` returns a non-null answer plus citations.
- [ ] Every citation refers to a record the requesting user is permitted to see (test with a student asking about another user's unpublished draft — it must not appear).
- [ ] With no embeddings present, the endpoint returns a clear message rather than an error.
- [ ] Provider failure returns HTTP 503 with a clear message and **never** a fabricated answer.
- [ ] `apps.ai.urls` is routed; the frontend's existing calls no longer 404.

## Definition of Done
Merged; visibility test in CI; `NFR-P3` latency measured and recorded for `VAL-12`; `IR-35` rewritten.

## Complexity
L

## Suggested Jira Type
Story

## Suggested Priority
High

## Suggested Labels
`ai`, `backend`, `rag`, `fr-m4-01`, `security`, `nfr-p3`

---

# AI-07 · Structured document summarization

## Objective
Deliver FR-M4-02 — a four-part structured summary of a record's extracted text.

## Problem
The endpoint exists and returns HTTP 501.

## Current State
`apps/ai/views.py::SummarizeView.post` returns `{"detail": "Summarization not yet implemented."}, status=501`. Its docstring specifies the intended behaviour: fetch the completed `PdfExtraction`, prompt for objectives / methodology / findings / conclusion, return structured JSON. `apps/ai/services/summarizer.py` is `class SummarizationService: pass`.

Jira `IR-20`, `IR-37`, `IR-38` cover this and are consistent with the SRS.

## Proposed State
`SummarizeView` returns the four-section summary, sourced from `PdfExtraction.extracted_text`.

## Scope
- Fetch the completed extraction; 404 when none exists
- Structured prompt returning parseable JSON
- Persist to `DocumentSummary` (make it a real model) so repeat requests are not re-charged
- Handle provider failure explicitly

## Out of Scope
Frontend components (`IR-36`).

## Technical Approach
Request JSON output from the model and validate the shape before returning. Persisting is a deliberate deviation from `rag_pipeline_service_map.md`, which says summaries are "never persisted" — persisting is cheaper and supports `VAL-18` cost control. Record the deviation.

## Dependencies
`AI-01`/`AI-02` (extraction must succeed), `AI-05`, `BE-04`.

## Risks
Low. Long documents may exceed the context window — truncate or summarise per chunk, and state which.

## Security Impact
Same visibility requirement as `AI-06`: only summarise records the caller may see.

## Performance Impact
A long-document summary may exceed 30 s. Consider making it a Celery task with a polled result rather than a blocking request.

## Deployment Impact
None.

## Framework Impact
None beyond `AI-05`.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `POST /api/v1/ai/summarize/<pk>/` returns all four sections populated.
- [ ] A record with no completed extraction returns 404 with a clear message.
- [ ] A user without visibility of the record receives 403.
- [ ] A second request for the same record returns the persisted summary without a new provider call (assert zero provider calls).
- [ ] Provider failure returns 503, never a partial or fabricated summary.

## Definition of Done
Merged; tests with a fake provider; `IR-20`/`IR-37`/`IR-38` linked.

## Complexity
M

## Suggested Jira Type
Story

## Suggested Priority
Medium

## Suggested Labels
`ai`, `backend`, `summarization`, `fr-m4-02`

---

# AI-08 · Conversation persistence for the chatbot

## Objective
Deliver the conversation-history half of FR-M4-01 and decide the fate of the existing chat UI.

## Problem
`Conversation` and `ChatMessage` are field-less stubs. Meanwhile an 840-line chat UI exists on the frontend and is routed to nothing.

## Current State
`apps/ai/models/conversation.py` — `class Conversation(models.Model): pass` and `class ChatMessage(models.Model): pass`. `apps/ai/views/chatbot.py` — `ConversationListView`, `ConversationDetailView`, `ChatQueryView`, all `pass`.

Frontend: `features/ai/RAGChatPage.tsx` plus seven components plus `lib/chatStorage.ts` and `types/chat.ts` (~840 lines) exist but `router/index.tsx` mounts `AIHubPage` instead, which calls no endpoints. Chat history is currently held in `chatStorage.ts` (browser storage), not the server.

Jira `IR-19`, `IR-33`, `IR-34` cover this.

## Proposed State
Real `Conversation` and `ChatMessage` models with CRUD endpoints; the existing chat UI wired to them — or the UI deleted if conversation history is out of MVP scope.

## Scope
- Make both models real (user FK, title, timestamps; role, content, citations)
- `ConversationListView` / `ConversationDetailView` CRUD scoped to the owner
- Persist each `AskView` exchange
- Route the existing `RAGChatPage`, or delete it

## Out of Scope
Building new chat UI — 840 lines already exist.

## Technical Approach
**Decide first whether conversation history is MVP.** If not, delete the UI (`FE-07`) and defer this task rather than leaving both half-built.

## Dependencies
`AI-06`, `BE-04`. Blocks the chat-UI decision in `FE-07`.

## Risks
Low. Main risk is leaving the current split state — a UI with no backend and a backend with no models.

## Security Impact
Conversations must be scoped per user; one user must not read another's history. Citations must respect record visibility.

## Performance Impact
Negligible.

## Deployment Impact
New tables.

## Framework Impact
None.

## MVP Classification
**MVP Recommended** — FR-M4-01 mentions conversational RAG; whether *persistent history* is MVP is a scope decision

## Acceptance Criteria
- [ ] `Conversation` and `ChatMessage` have real fields and migrations.
- [ ] A user can list, open and delete only their own conversations (403 otherwise).
- [ ] Each `AskView` exchange persists a user message and an assistant message with citations.
- [ ] `RAGChatPage` is routed and functional, **or** deleted with the decision recorded.
- [ ] `lib/chatStorage.ts` is removed once history is server-side.

## Definition of Done
Merged with migrations and ownership tests; the chat-UI decision recorded; `IR-19`/`IR-33`/`IR-34` updated.

## Complexity
M

## Suggested Jira Type
Story

## Suggested Priority
Medium

## Suggested Labels
`ai`, `backend`, `frontend`, `chat`, `fr-m4-01`
