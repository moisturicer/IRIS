# ADR-006: Minimum RAG pipeline, no orchestration framework

## Status

Accepted — 2026-09-01

## Context

`docs/rag_pipeline_service_map.md` documents an eleven-phase RAG pipeline in the present tense. Verified against the working tree, **two phases exist**: PDF upload and PostgreSQL full-text indexing. `apps/ai/services/` contains eight classes — `RAGPipelineService`, `VectorRetriever`, `LLMGenerator`, `TextChunkerService`, `CohereReranker`, `SummarizationService`, `PDFExtractorService`, `VectorStoreService` — whose entire body is `pass`. `apps/ai/models/` contains five field-less model stubs that shadow the real models in `models.py`.

Extraction does not work: `documents/tasks.py` imports `unstructured`, `fitz` and `pytesseract`, none of which is in any requirements file. Embedding does not work: `apps/ai/tasks.py` imports `sentence_transformers`, also absent, and imports models that are shadowed.

Jira tickets `IR-9`, `IR-15` and `IR-35` specify Qdrant, LangChain and Cohere reranking. **The current SRS specifies none of them** — LangChain appears once, in a change-history line recording that a proposed switch to n8n was rejected; Cohere appears zero times in the SRS.

The team has no prior end-to-end RAG experience, and RAG is explicitly not the thesis contribution (ADR-003).

## Decision

Build the **minimum pipeline that satisfies FR-M4-01**, in Django, with explicit code:

```
PDF → extraction (PyMuPDF) → embedding (provider protocol)
    → pgvector retrieval → grounded answer + citations
```

**Excluded from the MVP:** full-text chunking (embed title and abstract only) · conversational memory and history · summarization · reranking · agents · multiple LLM providers · any AI microservice.

**Timeboxed to 3 dev-days, ending Week 6.** If grounded generation is not working by that point, **ship semantic search only** — pgvector similarity with no LLM call — and reclassify generation as Phase 2. This is a pre-committed decision rule, not a judgement to be made under pressure in Week 7.

Retrieval must filter by record visibility. A user must never receive a citation to a record they cannot see.

## Alternatives Considered

**LangChain orchestration** (as `IR-15`/`IR-35` specify). Rejected. IRIS's pipeline is: embed query → `ORDER BY embedding <=> q LIMIT 5` → format prompt → one completion → return text and ids. That is roughly 60 lines. LangChain brings a large transitive dependency tree and frequent breaking changes to abstract a single chain. **Deletion test:** removing it moves complexity out of a dependency and into readable code — a gain, not a relocation. Provider swappability, its one real benefit here, costs ~20 lines of `Protocol`.

**Cohere reranking** (as `IR-35` specifies). Rejected — zero SRS mentions, and `docs/rag_pipeline_service_map.md` itself notes reranking *"was not carried forward into the formal SRS/SDD."* A third vendor and a second external call for marginal gain on a corpus of hundreds of documents.

**Full-text chunking in the MVP.** Rejected for now. Chunking plus per-chunk embedding roughly doubles the RAG cost in both dev-days and API spend. Abstracts are dense, human-written summaries — for a corpus this size they retrieve well. Deferred, not abandoned.

**Conversational memory and history.** Rejected. `Conversation` and `ChatMessage` are field-less stubs; an 840-line chat UI exists and is routed to nothing. Single-shot Q&A satisfies FR-M4-01's core claim.

**Separate FastAPI AI gateway.** Rejected — see ADR-010. It contradicts the SRS service table and would duplicate authentication and visibility filtering, creating a second place for the ADR-009 defects to recur.

## Decision Rationale

RAG is a supporting capability with an inexperienced team, a 3-day budget, and no bearing on the thesis claim. Every excluded item is defensible individually and indefensible collectively against 27 dev-days.

The timebox with a pre-committed fallback matters more than the scope itself. RAG is the item most likely to consume the whole window; bounding it converts the project's largest schedule risk into a known-cost decision.

Explicit code is also *easier to defend* at a technical defence than framework configuration. Every step is visible and independently testable.

## Consequences

**Positive.** ~3 dev-days instead of ~15. No LangChain, Qdrant or Cohere dependency. Every step legible and testable with a fake provider. The fallback guarantees something demonstrable.

**Negative.** Retrieval quality is bounded by abstract-level embeddings; full-document semantic search is unavailable until chunking lands. Answers cite records, not passages.

**Risk.** Even 3 days may be optimistic without prior experience. Mitigated by the ~2.5 days of Weeks 4–7 slack, which is reserved for exactly this.

## MVP Impact

**MVP Required, P1**, timeboxed. Degradable to semantic-search-only without failing the MVP.

## SaaS Impact

Under ADR-005, vector data is isolated per instance — no cross-tenant retrieval risk and no metadata filtering to get right.

## Security Impact

**Significant.** Retrieval is a potential bypass around every access control in ADR-009: an unfiltered vector query returns content regardless of record visibility. Retrieval **must** apply the same visibility scope as the record endpoints. This is the single most important detail in the RAG work.

Also removes `pickle.loads` over database rows (see ADR-007).

## Deployment Impact

No new services. Avoids the 4 GB Docling container and the FastAPI gateway.

## Research Impact

Minimal by design. RAG is demonstrated, not evaluated as a contribution.

## Related Requirements

FR-M3-01 (extraction) · FR-M3-02 (FTS) · FR-M3-03 (embeddings) · FR-M4-01 (RAG chatbot) · FR-M4-02 (summarization — **deferred**) · NFR-P3 (see ADR-011) · NFR-P4.

## Related Tasks

`R-01`…`R-06`. See [`06-rag.md`](../architecture-tasks/06-rag.md).
