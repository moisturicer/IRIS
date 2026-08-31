# 09 — Framework Evaluation Tasks

Six decision tasks. Each answers the nine questions the brief requires: problem solved · do we need it · can the current stack solve it · simplest alternative · cost · free-tier viability · deployment impact · thesis suitability · business suitability · migration risk.

**Two of these are already settled by the SRS** and are recorded as ratification tasks rather than open questions — `FW-01` and `FW-02`. Treating them as open would re-litigate a decision the team already made.

---

# FW-01 · RATIFY — Vector store: pgvector, not Qdrant

## Objective
Formally close the vector-store question and correct the Jira tickets that contradict the SRS.

## Problem
Jira `IR-9` and `IR-15` specify Qdrant. The SRS specifies pgvector, emphatically and repeatedly. The backlog has been stale since the SRS was revised in May 2026.

## Current State

| Source | Says |
|---|---|
| **SRS §456** | *"The pgvector extension enables cosine similarity queries using HNSW indexes directly within PostgreSQL, **eliminating the need for a separate vector database service**."* |
| **SRS §624-626** | *"**There is no separate vector database service or additional network port.**"* |
| SRS §462-478 | Interface tables specify `pgvector 0.5+`, `VectorField`, HNSW, the `<=>` operator |
| SRS mentions | pgvector **13**; Qdrant **2** (change history + a backup table row) |
| `docker-compose.yml` | `pgvector/pgvector:pg16` |
| `requirements/base.txt` | `pgvector` (listed **twice**) |
| **Jira IR-9, IR-15** | **Qdrant** |
| Code reality | Neither — `BinaryField` + `pickle` + a Python cosine loop |

## The nine questions

| Question | Answer |
|---|---|
| **Problem solved** | Similarity search over document embeddings |
| **Do we need it** | Yes — FR-M3-03 and FR-M4-01 require semantic search |
| **Can the current stack solve it** | **Yes.** PostgreSQL is already deployed; the Compose image already includes pgvector |
| **Simplest alternative** | pgvector *is* the simplest — it adds no service |
| **Cost** | £0 — same container |
| **Free-tier viability** | Excellent. Neon and Supabase both ship pgvector |
| **Deployment impact** | **None.** Qdrant would add a stateful service, a backup target and an ID-sync path |
| **Thesis suitability** | High — one fewer moving part to explain and defend |
| **Business suitability** | High to hundreds of thousands of vectors, far beyond one university's corpus |
| **Migration risk** | **None** — no production embeddings exist |

**Deletion test on a separate vector DB: fails.** Removing Qdrant and using pgvector *reduces* total complexity by one service.

## Proposed State
An ADR ratifying pgvector; `IR-9` and `IR-15` rewritten; `AI-03` implements it.

## Scope
ADR plus the two Jira rewrites. Implementation is `AI-03`.

## Out of Scope
Implementation.

## Dependencies
None. Unblocks `AI-03`.

## Risks
None technically. The only risk is *not* doing it: two tickets would otherwise be built against a store the SRS excludes.

## Security Impact
Fewer services, fewer network boundaries, no second credential.

## Performance Impact
HNSW is sub-second well past this corpus size.

## Deployment Impact
Avoids a service.

## Framework Impact
No Qdrant client dependency; deduplicate the double `pgvector` entry.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] ADR recorded citing SRS §456 and §624.
- [ ] `IR-9` and `IR-15` no longer reference Qdrant.
- [ ] No Qdrant client appears in any requirements file.
- [ ] `AI-03` references the ADR.

## Definition of Done
ADR merged; both tickets rewritten per `12-jira-ready-tasks.md`.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`architecture-decision`, `adr`, `ai`, `srs-alignment`

---

# FW-02 · RATIFY — RAG orchestration: explicit code, not LangChain

## Objective
Close the RAG-framework question and correct the tickets specifying LangChain.

## Problem
`IR-15` and `IR-35` specify LangChain. The SRS does not require it — it appears once, in a change-history line recording that a proposed switch to n8n was rejected.

## Current State
LangChain: **1** SRS mention (change history only), 2 in SDD. Cohere: **0** SRS mentions. `apps/ai/services/` contains `RAGPipelineService`, `LLMGenerator`, `CohereReranker` and five more — every body `pass`.

## The nine questions

| Question | Answer |
|---|---|
| **Problem solved** | Orchestrating multi-step LLM pipelines, retriever abstractions, provider swapping, memory |
| **Do we need it** | **No.** IRIS's pipeline is: embed query → `ORDER BY embedding <=> q LIMIT 5` → format prompt → one completion → return text + ids |
| **Can the current stack solve it** | Yes — roughly 60 lines of explicit Python |
| **Simplest alternative** | Explicit code, with ~20-line `EmbeddingProvider` / `LLMProvider` protocols for swappability |
| **Cost** | £0 either way |
| **Free-tier viability** | Explicit code has a smaller image and fewer transitive dependencies |
| **Deployment impact** | LangChain adds a large transitive tree to every backend and worker image |
| **Thesis suitability** | Explicit code is **more** defensible — every step is legible and independently testable |
| **Business suitability** | Fine. Revisit if the pipeline becomes an agent graph with tool use |
| **Migration risk** | None — nothing is built yet |

**Deletion test:** removing LangChain from a five-step pipeline moves complexity *out* of a dependency and into 60 readable lines. That is a gain, not a relocation.

**Reranking is separately descoped:** 0 SRS mentions of Cohere; `docs/rag_pipeline_service_map.md` itself flags that reranking *"was not carried forward into the formal SRS/SDD."*

## Proposed State
ADR ratifying explicit orchestration; `IR-15` and `IR-35` rewritten; reranking descoped.

## Scope
ADR plus two Jira rewrites. Implementation is `AI-04` and `AI-06`.

## Out of Scope
Implementation. Revisiting n8n — already rejected by the team; agreed.

## Dependencies
None. Unblocks `AI-04`, `AI-06`.

## Risks
Low. If the pipeline later needs agents or tool use, revisit — and record that trigger in the ADR.

## Security Impact
Fewer transitive dependencies, smaller supply-chain surface.

## Performance Impact
Neutral to positive — no framework overhead.

## Deployment Impact
Smaller images.

## Framework Impact
No `langchain`, no `cohere`.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] ADR recorded, including the trigger that would justify revisiting (agents, tool use, multi-provider routing).
- [ ] `IR-15` and `IR-35` no longer reference LangChain or Cohere.
- [ ] Reranking is explicitly descoped with the `rag_pipeline_service_map.md` note cited.
- [ ] No `langchain` or `cohere` in any requirements file.

## Definition of Done
ADR merged; both tickets rewritten; `apps/ai/services/cohere_reranker.py` deleted with `BE-04`.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`architecture-decision`, `adr`, `ai`, `srs-alignment`

---

# FW-03 · DECIDE — Docling-serve for the MVP, or PyMuPDF only

## Objective
Decide whether the 4 GB Docling container ships in the MVP.

## Problem
Docling is SRS-specified but is over half a small host's memory budget, and no code calls it today. `AI-01` unblocks extraction with PyMuPDF; `AI-02` implements the SRS target. Which ships for the MVP is a real trade-off.

## Current State
`docker-compose.yml` runs `quay.io/docling-project/docling-serve:latest` with a 4 GB limit and a healthcheck. `settings/base.py:181` defines `DOCLING_API_URL`. **`grep -rn "DOCLING_API_URL" backend/apps/` returns nothing** — the container runs and is called by nobody.

SRS specifies Docling in four places (FR-M3-01, service table §402, interface Table 18 §481-489) and names PyMuPDF/pytesseract as the fallback (§361).

## The nine questions

| Question | Answer |
|---|---|
| **Problem solved** | Structured extraction from complex layouts and scanned/OCR PDFs |
| **Do we need it** | For *scanned* submissions, yes. For born-digital theses, PyMuPDF suffices |
| **Can the current stack solve it** | Partly — PyMuPDF handles text-layer PDFs, which is what a submitted thesis usually is |
| **Simplest alternative** | PyMuPDF only, with Docling deferred to post-MVP |
| **Cost** | £0 licence; **4 GB RAM**, the dominant hosting cost |
| **Free-tier viability** | **Poor.** 4 GB rules out most free tiers; ~2 GB without it opens several |
| **Deployment impact** | Largest single lever on hosting cost. Slow first-run model load (60 s healthcheck `start_period`) |
| **Thesis suitability** | Deviating from the SRS needs an amendment; the SRS is an assessed artefact |
| **Business suitability** | High — scanned-document support matters at institutional scale |
| **Migration risk** | Low — `AI-02` keeps PyMuPDF as the documented fallback either way |

## The decision to make
**A** ship Docling now (SRS-conformant, +4 GB); **B** PyMuPDF only for the MVP and amend the SRS to mark Docling Phase 2; **C** ship Docling but make it optional via a feature flag.

**Recommendation: B or C.** Deferring requires an SRS amendment — a documentation change, not a silent deviation. Option C keeps the SRS satisfied while allowing a low-memory deployment.

> This corrects `docs/architecture-review/`, which recommended deferring Docling **without noting that it is SRS-specified**. Deferral is legitimate; doing it silently is not.

## Proposed State
An ADR recording the choice and, if B, an SRS amendment ticket.

## Scope
Decision, ADR, and an SRS amendment ticket if deferring.

## Out of Scope
Implementation (`AI-01`, `AI-02`).

## Dependencies
Blocks `AI-02` scope and `DEP-06` sizing.

## Risks
Choosing B without amending the SRS creates a documented-vs-built mismatch — exactly the problem `AI-07`/`DOC-02` exist to fix.

## Security Impact
Docling is on-premise, satisfying the SRS's RA 10173 constraint that raw files never leave university hardware. A cloud extraction API would not.

## Performance Impact
Docling OCR on a scanned document may exceed `NFR-P4`'s 30-second budget. **Measure before committing.**

## Deployment Impact
±4 GB — decisive for `DEP-06`.

## Framework Impact
Retains or drops the `docling` service and the `requests` dependency.

## MVP Classification
**MVP Required** (the decision)

## Acceptance Criteria
- [ ] ADR records the choice with reasoning.
- [ ] If B: an SRS amendment ticket exists marking Docling Phase 2.
- [ ] If A or C: `NFR-P4` measured with Docling on a 10-page/10 MB PDF.
- [ ] `DEP-06` sizing reflects the decision.
- [ ] The fallback path (§361) is implemented regardless.

## Definition of Done
ADR merged; `AI-02` scoped accordingly; SRS amendment ticketed if needed.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`architecture-decision`, `adr`, `ai`, `extraction`, `deployment`

---

# FW-04 · DECIDE — Server-state library on the frontend

## Objective
Decide whether to adopt TanStack Query, hand-roll a small hook, or keep the status quo.

## Problem
Server state is hand-rolled in 28 components, mostly by omission, producing at least one user-visible defect.

## Current State
`@tanstack/react-query` is **not** installed (only `@tanstack/react-table`). Evidence in `FE-04`: a missing `.catch` that renders "No pending records" on a network failure; a discarded error; a `JSON.stringify(filters)` dependency with the codebase's only `eslint-disable`; a notification store that diverges from the server on first use; an error-shape cast copy-pasted across 8 files.

## The nine questions

| Question | Answer |
|---|---|
| **Problem solved** | Caching, deduplication, invalidation-after-mutation, retry, one loading/error path |
| **Do we need it** | The *problems* are real and already causing defects. The *library* is one way to solve them |
| **Can the current stack solve it** | Partly. A ~40-line `useApi<T>` hook fixes error handling and loading duplication but not dedup, cache or invalidation |
| **Simplest alternative** | The `useApi<T>` hook |
| **Cost** | ~13 KB gzipped, one dependency |
| **Free-tier viability** | Irrelevant — client-side |
| **Deployment impact** | None |
| **Thesis suitability** | Good — a defensible, citable decision. Costs 1–2 days of team learning |
| **Business suitability** | High — the de-facto standard |
| **Migration risk** | Low — incremental; both styles coexist. Lock-in low: hooks are swappable |

## The deciding argument
This codebase has **already hand-rolled two of the three things option B does not cover, and got both wrong**: `PublishedRecordsPage.tsx:71` is a query key (with the suppression needed to make it work), and `notifications.store.ts` is a cache that diverges from the server. Writing those correctly *is* writing a smaller, worse TanStack Query.

**Recommendation: adopt it (MVP Recommended, not blocker).** If time is short, do the `useApi<T>` hook and stop — it captures the error-handling win for free. Do not do neither. **Do not** adopt Query while keeping `notifications.store.ts`.

## Proposed State
ADR recording the choice; `FE-04` implements it.

## Scope
Decision and ADR.

## Out of Scope
Implementation (`FE-04`).

## Dependencies
`FE-01` must land before implementation either way.

## Risks
Scope: 28 components is real work. Sequence after P0/P1.

## Security Impact
Minor positive — one error path means auth failures are handled consistently.

## Performance Impact
Positive: deduplication and caching support `NFR-P2`.

## Deployment Impact
None.

## Framework Impact
+1 dependency; removes `notifications.store.ts`.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] ADR records the choice and the fallback position.
- [ ] If adopted: `FE-04` is scheduled after `FE-01`.
- [ ] If not adopted: the `useApi<T>` hook is ticketed instead — the status quo is not an option.
- [ ] The ADR states that `notifications.store.ts` is deleted either way.

## Definition of Done
ADR merged; `FE-04` scoped accordingly.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`architecture-decision`, `adr`, `frontend`

---

# FW-05 · DECIDE — AI gateway service, and the NFR-P3 latency conflict

## Objective
Decide where RAG query handling runs, and resolve a requirement that may be unachievable as specified.

## Problem
Two coupled questions. The Compose files declare a FastAPI `ai-gateway` the SRS does not contain. And `NFR-P3` demands a 3-second p95 chatbot response while a synchronous LLM round-trip is 3–10 seconds.

## Current State
**The gateway.** `docker-compose.yml` builds `ai-gateway` from `./ai` — a directory that does not exist. The SRS service table (§393-405) lists nginx, web, celery-worker, celery-worker-rag, celery-beat, docling, db, redis. **No FastAPI service.** The one "internal AI gateway" phrase (SRS:1380) describes a *code-level abstraction* for reaching the external AI service. SRS §478 names `SemanticSearchView` and `AskView` — Django views — as pgvector's consumers.

`docs/docker_compose_rag_services.md` justifies the gateway with *"~15 GB RAM for 100 concurrent RAG users"* versus 500 MB async.

**The latency conflict — not covered in the architecture review.** `NFR-P3`: *"The IRIS RAG chatbot shall return a complete response within 3 seconds for the 95th percentile of all user queries."* Validation: 20 consecutive queries, p95 measured. A single GPT-4.1-mini completion with retrieved context typically takes 3–10 s. **The requirement is likely unachievable for a complete non-streamed response**, regardless of where the code runs.

## The nine questions (gateway)

| Question | Answer |
|---|---|
| **Problem solved** | Preventing slow LLM calls from occupying Gunicorn workers needed for CRUD |
| **Do we need it** | The *problem* is real at load. The *service* is one solution |
| **Can the current stack solve it** | **Yes.** `--worker-class gthread --threads 8` serves ~32 concurrent I/O-bound requests per container. `config/asgi.py` already exists for async views |
| **Simplest alternative** | A Gunicorn flag — one line |
| **Cost** | Gateway: a second runtime, dependency tree, deployment unit and duplicated auth. Flag: nothing |
| **Free-tier viability** | The gateway's 1 GB budget matters on a small host |
| **Deployment impact** | +1 service, +1 image, +1 healthcheck, +1 secret path |
| **Thesis suitability** | The SRS does not contain it; adding it needs an amendment |
| **Business suitability** | Reasonable at genuine scale — extract when measured, not projected |
| **Migration risk** | Low now (nothing built); high later if RAG is written to gateway-specific assumptions |

**The 15 GB figure assumes 100 synchronous worker processes.** A provider call is a blocked socket, not CPU work. `NFR-P1`'s 100 concurrent *sessions* is not 100 concurrent *RAG queries* — the doc conflates them.

> This corrects the architecture review's claim that the 100-user figure was unsourced: `NFR-P1` **does** mandate 100 concurrent sessions. The extrapolation to 100 concurrent RAG queries is what lacks a source.

## The decisions to make
1. **Gateway:** A build it (needs an SRS amendment) · **B RAG in Django, `gthread` when needed (recommended)** · C defer and revisit on measurement.
2. **NFR-P3:** A stream the response and measure time-to-first-token · B amend the NFR to a realistic figure · C keep 3 s and accept it will fail.

**Recommendation: 1-B and 2-A or 2-B.** Streaming is the honest engineering answer; amending the NFR is the honest documentation answer. Doing neither means a documented requirement that measurably fails at defence.

## Proposed State
Two ADRs; `AI-06` scoped accordingly; `VAL-12` measures whichever target is chosen.

## Scope
Both decisions and their ADRs; an SRS amendment ticket if NFR-P3 changes.

## Out of Scope
Implementation (`AI-06`, `DEP-04`).

## Dependencies
Blocks `AI-06` and `ARCH-02`. Feeds `VAL-12`.

## Risks
Leaving NFR-P3 unaddressed guarantees a failed validation in the thesis defence.

## Security Impact
A gateway would duplicate authentication and record-visibility logic — a second place for `SEC-02`-class defects.

## Performance Impact
The entire subject of the task.

## Deployment Impact
±1 service, ±1 GB.

## Framework Impact
FastAPI, uvicorn and asyncpg, or none.

## MVP Classification
**MVP Required** (both decisions)

## Acceptance Criteria
- [ ] ADR records the gateway decision, citing the SRS service table.
- [ ] ADR records the NFR-P3 decision.
- [ ] If NFR-P3 is amended, an SRS amendment ticket exists with the new target and rationale.
- [ ] If streaming is chosen, `AI-06` includes SSE and `VAL-12` measures time-to-first-token.
- [ ] `ARCH-02` reflects the gateway decision.

## Definition of Done
Both ADRs merged; `AI-06` and `VAL-12` scoped; SRS amendment ticketed if needed.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`architecture-decision`, `adr`, `ai`, `performance`, `nfr-p3`, `srs-alignment`

---

# FW-06 · DECIDE — Embedding provider and data governance

## Objective
Choose the embedding provider, and answer the institutional question underneath it: may unpublished research abstracts leave campus?

## Problem
Three configuration sources name three different vendors, and the SRS leaves the embedding provider explicitly open — while asserting a data-handling guarantee the implementation must honour.

## Current State

| Source | Says |
|---|---|
| `settings/base.py:180` | `OPENAI_API_KEY` |
| `.env.example:31` | **`ANTHROPIC_API_KEY`** |
| `settings/base.py:179` | `AI_EMBEDDING_MODEL = "TBD"` |
| `.env.example:32` | `all-MiniLM-L6-v2` (a *local* model) |
| `apps/ai/tasks.py:51` | imports `sentence_transformers` — **not in requirements** |
| SRS §632 | *"Vector embedding generation will be handled by a third-party embedding API (provider TBD)"* |
| SRS §197 | *"operating exclusively on anonymized, extracted text chunks. No raw files, personally identifiable information, or unprocessed IP disclosures are transmitted to external services"* |

## The nine questions

| Question | Answer |
|---|---|
| **Problem solved** | Turning text into vectors for similarity search |
| **Do we need it** | Yes — FR-M3-03 |
| **Can the current stack solve it** | Locally, yes — sentence-transformers runs on CPU |
| **Simplest alternative** | A hosted embedding API: no weights, no GPU, no CPU inference in the worker |
| **Cost** | API ≈ $0.02 per 1M tokens — negligible for this corpus. Local: £0 marginal |
| **Free-tier viability** | Local is free forever; API needs a card |
| **Deployment impact** | Local adds ~500 MB of weights and CPU load to the worker; API adds a network dependency |
| **Thesis suitability** | Both defensible. Local is a stronger data-privacy story |
| **Business suitability** | API scales better operationally; local avoids per-query cost |
| **Migration risk** | **Low if implemented behind `AI-05`'s protocol** — otherwise medium, since vector dimensions differ and re-embedding is required |

## The real question
IRIS manages **confidential pre-publication IP disclosures**. Whether abstracts may be sent to a third party is an institutional data-governance decision, not a technical one. SRS §197 already commits to sending only "anonymized, extracted text chunks" — the implementation must be able to demonstrate that.

**This should be confirmed with the research office, not decided by the development team.**

## The decision to make
**A** API embeddings + API chat · **B** local embeddings + API chat (abstracts stay on campus; only questions leave) · **C** fully local.

**Recommendation: A for the MVP behind `AI-05`'s protocols — but confirm with the research office first.** If the answer is "unpublished IP may not leave university systems," it is B, and that changes the deployment profile.

## Proposed State
ADR recording the provider, the governance confirmation, and the dimension it fixes for `AI-03`.

## Scope
Decision, governance confirmation, ADR.

## Out of Scope
Implementation (`AI-05`). Cost controls (`AI-06` in the review; `VAL-18` measures).

## Dependencies
Blocks `AI-05`, and `AI-03` (vector `dimensions`).

## Risks
Deciding without the research office risks a compliance problem discovered at defence.

## Security Impact
Determines whether unpublished research leaves university systems. Highest-stakes question in this document.

## Performance Impact
Local embedding adds CPU load and may affect `NFR-P4`'s 30-second budget.

## Deployment Impact
API keys become deployment secrets; local adds ~500 MB.

## Framework Impact
Retains `openai`, or reinstates `sentence-transformers` (currently imported and uninstalled).

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] ADR records the provider and the vector dimension.
- [ ] The data-governance question is confirmed **in writing** with the research office and cited.
- [ ] `AI-05` aligns `settings`, `.env.example` and `requirements` to the choice.
- [ ] The ADR states how SRS §197's "anonymized chunks only" claim is verified.
- [ ] Estimated monthly cost recorded for `VAL-18`.

## Definition of Done
ADR merged with the governance confirmation attached; `AI-05` and `AI-03` scoped.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`architecture-decision`, `adr`, `ai`, `privacy`, `compliance`, `ra-10173`
