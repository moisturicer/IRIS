# 06 — RAG

Six tasks, **timeboxed to 3 dev-days ending Week 6**. Governed by [ADR-006](../adr/006-minimum-rag-pipeline.md), [ADR-007](../adr/007-pgvector-vector-store.md), [ADR-008](../adr/008-ai-degradation-to-fts.md).

> **Pre-committed decision rule.** If grounded generation (`R-04`) is not working by the end of Week 6, ship semantic search only and reclassify generation as Phase 2. This is decided now, not under pressure in Week 7. RAG is the item most likely to overrun and the only one with a fallback already agreed.

**Excluded from MVP:** full-text chunking · conversational memory · summarization · reranking · agents · multiple providers · any AI microservice.

---

# R-01 · Restore PDF text extraction

## Objective
Make extraction succeed on a real upload, unblocking FTS, embeddings and everything downstream.

## Problem
The three-tier extractor chain imports three libraries, **none of which is installed**. Every extractor raises `ImportError`, the chain raises `RuntimeError`, the task retries three times and marks the extraction permanently `failed`.

## Evidence

| Extractor | Imports | In requirements? |
|---|---|---|
| `_extract_with_opendataloader` | `unstructured.partition.auto` | **No** |
| `_extract_with_pymupdf` | `fitz` | **No** |
| `_extract_with_tesseract` | `pytesseract`, `PIL`, `fitz` | **No** |

`requirements/base.txt:14-17` records the deliberate removal for a Docling migration that was never made — `grep -rn "DOCLING_API_URL" backend/apps/` returns nothing. `_clean_text()` is written and correct.

## Current State
PDF extraction cannot succeed on any input. FR-M3-01 is unmet.

## Proposed State
`pymupdf` in requirements; the chain reduced to PyMuPDF; extraction succeeds on born-digital PDFs.

## Scope
Add `pymupdf`; keep the chain's structure so tiers can return; verify end-to-end on a committed fixture.

## Out of Scope
Docling-serve — SRS-specified but deferred ([ADR-006](../adr/006-minimum-rag-pipeline.md)); requires the `F-03` SRS amendment.

## Technical Approach
A submitted thesis is a born-digital, text-layer PDF, which PyMuPDF handles in ~50 MB with no external service. Scanned documents extract empty and are marked `failed` — honest and visible.

## Dependencies
`B-03` (queue routing) — without it the task never runs.

## Risks
Low. **Licence note:** PyMuPDF is AGPL-3.0 with a commercial option. Fine for a thesis and internal university deployment; flag before commercialisation. `pdfplumber` (MIT) is the drop-in fallback.

## Security Impact
None.

## Performance Impact
Enables NFR-P4 (10-page/10 MB PDF indexed within 30 s) to be measured at all.

## SaaS Impact
Per-instance extraction; no shared service.

## Research/Thesis Impact
Document processing must work for the pilot; extraction feeds the search capability participants evaluate.

## MVP Classification
MVP REQUIRED

## Priority
P1 — Week 4

## Complexity
XS

## Acceptance Criteria
- [ ] Uploading a text-layer PDF yields `PdfExtraction.status == "done"` with non-empty text.
- [ ] `search_vector` is populated and the document is findable by full-text search.
- [ ] A scanned PDF is marked `failed` with a clear error, not a silent empty success.
- [ ] `requirements/base.txt` lists every library the code imports.

## Testing Requirements
A test extracting a committed 2-page fixture PDF and asserting content.

## Documentation Requirements
The extraction hierarchy corrected in `F-03`.

## Definition of Done
Merged; fixture test in CI; NFR-P4 timing captured for `V-08`.

---

# R-02 · Provider protocols and configuration alignment

## Objective
Resolve the three-way vendor contradiction and make the provider swappable in one module.

## Problem
Three configuration sources name three different vendors. A developer copying `.env.example` gets a key the settings never read.

## Evidence

| Source | Says |
|---|---|
| `settings/base.py:180` | `OPENAI_API_KEY` |
| `settings/base.py:179` | `AI_EMBEDDING_MODEL` default **`"TBD"`** |
| `.env.example:31` | **`ANTHROPIC_API_KEY`** |
| `.env.example:32` | `all-MiniLM-L6-v2` — a *local* model |
| `apps/ai/tasks.py:51` | imports `sentence_transformers` — **not in requirements** |
| `apps/ai/services/cohere_reranker.py` | a third vendor, as an empty class |

SRS §632: LLM inference via OpenAI; *"embedding generation will be handled by a third-party embedding API (provider TBD)."* SRS §197 commits to sending *"exclusively anonymized, extracted text chunks."*

## Current State
Configuration is internally inconsistent and the governance question is unresolved.

## Proposed State
`EmbeddingProvider` and `LLMProvider` protocols with one adapter each; all three sources agree; startup fails loudly on a missing key.

## Scope
The two protocols; align settings, `.env.example` and requirements; replace `"TBD"` with a real default; remove `sentence_transformers` usage or add it to requirements.

## Out of Scope
The provider decision itself — **blocked on external approval for AI data transmission** (open blocker #2).

## Technical Approach
Thin `Protocol` classes, ~20 lines, so tests inject a fake and never call a paid API. This is also what makes the eventual provider decision reversible in one module.

## Dependencies
**External blocker #2.** `R-03` needs the vector dimension this fixes.

## Risks
Low technically. **Governance risk is real:** if transmission is not approved, the adapter becomes local sentence-transformers — the protocol makes that a one-module change rather than a redesign.

## Security Impact
Determines whether unpublished research leaves university systems. SRS §197's claim must match the implementation.

## Performance Impact
Provider latency drives NFR-P3 (`V-10`).

## SaaS Impact
Per-instance keys and per-institution provider choice become possible — some institutions may require local-only processing.

## Research/Thesis Impact
Supports the RAG capability; not itself evaluated.

## MVP Classification
MVP REQUIRED

## Priority
P1 — Week 4

## Complexity
M

## Acceptance Criteria
- [ ] Both protocols exist with one adapter each.
- [ ] `settings`, `.env.example` and `requirements` name the same provider.
- [ ] `AI_EMBEDDING_MODEL` has a real default, not `"TBD"`.
- [ ] Starting with no API key fails at startup, not at first query.
- [ ] Tests inject a fake provider and make zero network calls.
- [ ] `grep -rn "sentence_transformers\|cohere" backend/` returns nothing, or the libraries are in requirements.

## Testing Requirements
A blocked-socket fixture asserting no outbound calls in the test suite.

## Documentation Requirements
The provider decision as an ADR; `.env.example` verified by a clean-clone setup run.

## Definition of Done
Merged; clean-clone setup verified; governance answer recorded.

---

# R-03 · pgvector storage and retrieval

## Objective
Deliver FR-M3-03 as the SRS specifies — a `VectorField` with an HNSW index, queried with the cosine distance operator.

## Problem
The stack advertises pgvector everywhere and uses none of it. Vectors are pickled into a `BinaryField` and searched with a Python loop over the whole table.

## Evidence
`apps/ai/models.py:26` — `embedding = models.BinaryField()` with a 20-line TODO describing exactly this migration. `apps/ai/tasks.py:57` — `pickle.dumps(embedding)`. `apps/ai/views.py` loads **every** `RecordEmbedding`, `pickle.loads` each, computes cosine similarity in NumPy, sorts in Python. `pgvector` is absent from `INSTALLED_APPS` and listed **twice** in `requirements/base.txt`. The Compose `db` image is already `pgvector/pgvector:pg16`.

Jira `IR-9`/`IR-15` specify Qdrant, contradicting SRS §456 and §624.

## Current State
O(n) rows into application memory per query, plus an unsafe-deserialization pattern.

## Proposed State
`VectorField(dimensions=N)`, an HNSW index created in a migration, retrieval via `CosineDistance` with `LIMIT k`. No `pickle` anywhere.

## Scope
Add `pgvector` to `INSTALLED_APPS`; deduplicate the requirements entry; replace `BinaryField`; HNSW index migration including `CREATE EXTENSION`; rewrite `embed_record`; rewrite search; remove all `pickle`.

## Out of Scope
Chunking — the MVP embeds title and abstract only ([ADR-006](../adr/006-minimum-rag-pipeline.md)).

## Technical Approach
Follow the TODO in `apps/ai/models.py`, which is correct. **`dimensions` must match the provider**, so `R-02` lands first or the migration is redone.

## Dependencies
`B-04`, `R-02`.

## Risks
Low — no production embeddings exist to migrate.

## Security Impact
**Removes `pickle.loads` over database rows** — a code-execution primitive that becomes reachable the moment `apps/ai` is un-shadowed.

## Performance Impact
Replaces an O(n) in-Python scan with an indexed ANN query.

## SaaS Impact
Per-instance vector isolation is structural under [ADR-005](../adr/005-instance-per-tenant.md) — no metadata filtering to get right.

## Research/Thesis Impact
None directly.

## MVP Classification
MVP REQUIRED

## Priority
P1 — Weeks 4–6

## Complexity
M

## Acceptance Criteria
- [ ] `RecordEmbedding.embedding` is a `VectorField`.
- [ ] A migration creates the extension and an HNSW index.
- [ ] `grep -rn "pickle" backend/apps/` returns nothing.
- [ ] Similarity search issues **one** SQL query with `ORDER BY … <=> … LIMIT k` (verified in query logs).
- [ ] Retrieval over ≥100 embedded records returns in under 200 ms.
- [ ] `pgvector` appears once in requirements and is in `INSTALLED_APPS`.

## Testing Requirements
Query-shape test asserting one indexed query; latency measured for `V-09`.

## Documentation Requirements
Jira `IR-9`/`IR-15` rewritten (`13-jira-reconciliation.md`).

## Definition of Done
Merged with migrations; query-shape test in CI.

---

# R-04 · Retrieval and grounded answer generation

## Objective
Deliver FR-M4-01 — semantic search and a grounded answer with citations — inside Django.

## Problem
Phases 6–10 do not exist. `rag_pipeline.py`, `vector_retriever.py` and `llm_generator.py` are all `class X: pass`.

## Evidence
`apps/ai/views.py` (shadowed) contains `SemanticSearchView` and `AskView` skeletons with TODO comments describing the intended implementation; `AskView` returns `{"answer": None, "citations": [...]}`. SRS §478 names `SemanticSearchView` and `AskView` as pgvector's consumers — confirming these Django views, not a separate service, are the specified home. Jira `IR-35` specifies Qdrant, Cohere and LangChain, none required by the SRS.

## Current State
Retrieval without generation; endpoints unrouted.

## Proposed State
`SemanticSearchView` returns top-k records by cosine distance; `AskView` retrieves, builds a prompt, calls the LLM, returns a grounded answer with citations.

## Scope
Query embedding via `R-02`; pgvector retrieval via `R-03`; explicit prompt construction; LLM call via the protocol; citations as record ids.

## Out of Scope
Reranking (0 SRS mentions) · conversation persistence · summarization · LangChain.

## Technical Approach
~60 lines of explicit Python. **Retrieval must apply `Record.objects.visible_to(user)`** — a student must never receive an answer citing another student's unpublished draft.

## Dependencies
`R-02`, `R-03`, `B-04`, `B-05`.

## Risks
**Medium.** NFR-P3 requires a 3-second p95 complete response against a 3–10 s LLM round-trip — likely unachievable as written; amendment tracked in `F-03`. Team has no prior RAG experience; the ~2.5 days of Weeks 4–7 slack is reserved for this task.

## Security Impact
**Highest in the RAG work.** An unfiltered vector query returns content regardless of record visibility, bypassing every control in [ADR-009](../adr/009-authorization-model.md).

## Performance Impact
Governed by NFR-P3. Retrieval is fast; generation dominates.

## SaaS Impact
Per-instance corpus; no cross-tenant retrieval possible.

## Research/Thesis Impact
Supporting capability demonstrated in the pilot, not evaluated as a contribution.

## MVP Classification
MVP REQUIRED — **timeboxed; degradable to search-only**

## Priority
P1 — Weeks 5–6

## Complexity
L

## Acceptance Criteria
- [ ] `POST /api/v1/ai/search/` returns top-k records ordered by similarity with scores.
- [ ] `POST /api/v1/ai/ask/` returns a non-null answer plus citations.
- [ ] **Every citation refers to a record the requesting user may see** — tested with a student asking about another user's unpublished draft.
- [ ] With no embeddings present, a clear message rather than an error.
- [ ] Provider failure returns 503 and **never** a fabricated answer.

## Testing Requirements
Visibility test (hard fail on any leak); groundedness spot-check feeding `V-09`.

## Documentation Requirements
Jira `IR-35` rewritten.

## Definition of Done
Merged; visibility test in CI; NFR-P3 latency measured for `V-10`. **If not met by end of Week 6, ship `R-03` search only and defer this.**

---

# R-05 · Graceful degradation to FTS

## Objective
Ensure AI failure degrades the product rather than breaking it, and demonstrate it deliberately.

## Problem
Every AI dependency is currently a single point of failure during the pilot and the defence.

## Evidence
PostgreSQL FTS already works — `records/signals.py` populates `search_vector` with a GIN index. It is the only phase of the documented eleven-phase pipeline that functions today and needs no external service.

## Current State
No fallback. A provider outage presents as a broken system.

## Proposed State

| Failure | Behaviour |
|---|---|
| Embedding provider down | Fall back to FTS; banner; indexing queues for retry |
| LLM provider down | Retrieval still returns records; answer replaced by an explicit unavailable state |
| Timeout | Bounded ~30 s, then 503 |
| pgvector retrieval fails | Fall back to FTS |
| Celery/Redis down | Uploads succeed; extraction queues; **workflow entirely unaffected** |
| Rate limit / credit exhausted | As unavailable, with a distinct operator log |

## Scope
Timeouts; try/except around retrieval falling back to FTS; a visible UI state; a distinct log per failure mode.

## Out of Scope
Any second AI implementation — no local fallback model, no secondary provider, no cached-answer service ([ADR-008](../adr/008-ai-degradation-to-fts.md)).

## Technical Approach
FTS is the fallback. ~0.5 dev-days because the hard part already exists.

## Dependencies
`R-04`.

## Risks
**Silent degradation.** If the banner is missing, users may believe semantic search is working and draw conclusions from keyword results — contaminating `V-11` usability data. The visible-state requirement is an acceptance criterion, not a nicety.

## Security Impact
Bounded timeouts prevent request pile-up. Explicit failure prevents a fabricated answer being presented as grounded.

## Performance Impact
FTS is faster than the AI path.

## SaaS Impact
One institution's outage or exhausted quota cannot affect another.

## Research/Thesis Impact
**Insurance for the pilot and the defence**, and insurance against external blocker #2 returning "no transmission permitted." Demonstrated as a named system-test scenario (`V-10`).

## MVP Classification
MVP REQUIRED

## Priority
P1

## Complexity
XS

## Acceptance Criteria
- [ ] With the provider unreachable, search returns FTS results and the UI shows a clear unavailable state.
- [ ] With the LLM unreachable, retrieval still returns records; no fabricated answer is produced.
- [ ] With Celery/Redis down, record submission and every workflow transition still succeed.
- [ ] Provider calls are bounded by an explicit timeout.
- [ ] Each failure mode produces a distinct operator log entry.

## Testing Requirements
One test per failure mode with a fake provider that raises; `V-10` demonstrates it live.

## Documentation Requirements
Failure modes tabulated in `DOC-05` and the runbook.

## Definition of Done
Merged; all five modes tested; demonstrated during system testing.

---

# R-06 · Route the AI endpoints

## Objective
Make the AI API reachable — the frontend currently calls routes Django never mounts.

## Problem
`config/urls.py` has ten `path()` entries; none includes `apps.ai.urls`. Every frontend `/api/v1/ai/*` call 404s.

## Evidence
`config/urls.py` lines 7-17. `apps/ai/urls.py:2` imports six names from `.views`, which resolves to the stub package that exports none — so it would `ImportError` if routed today. `apps/ai/serializers.py`, imported by `views.py`, does not exist.

## Current State
The AI app is installed, unroutable and unreachable.

## Proposed State
`path("api/v1/ai/", include("apps.ai.urls"))` added; the missing serializer module created; endpoints respond.

## Scope
Route the URLconf; add `apps/ai/serializers.py`; verify each endpoint resolves.

## Out of Scope
Endpoint behaviour (`R-03`, `R-04`).

## Technical Approach
**Do not route before `R-03`** — the current views ship `pickle.loads` over database rows.

## Dependencies
`B-04`, `R-03`.

## Risks
Low, provided the ordering above is respected.

## Security Impact
Routing the pre-`R-03` views would expose an unsafe-deserialization path. Ordering is the control.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
FR-M8-03 (embedding index administration) becomes reachable, supporting pilot operations.

## MVP Classification
MVP REQUIRED

## Priority
P1

## Complexity
XS

## Acceptance Criteria
- [ ] `POST /api/v1/ai/search/` resolves and returns 200 for an authenticated user.
- [ ] `POST /api/v1/ai/ask/` resolves.
- [ ] FR-M8-03 admin endpoints resolve for staff.
- [ ] The frontend's existing AI calls no longer 404.
- [ ] The URLconf import-smoke test covers the AI routes.

## Testing Requirements
Covered by `T-01`'s URLconf walk.

## Documentation Requirements
Endpoints listed in `DOC-06`.

## Definition of Done
Merged after `R-03`; smoke test green.
