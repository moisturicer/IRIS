# ADR-013: Chunk-level RAG pipeline with reranking

## Status

Accepted — 2026-09-02 · **amended 2026-09-04, §Research Impact**

**Supersedes [ADR-006](006-minimum-rag-pipeline.md).** ADR-006's exclusions of full-text chunking, reranking and multiple providers are reversed. Its retrieval-visibility requirement and its timebox-with-fallback discipline are **retained** and restated below.

> **Amendment, 2026-09-04 — RAG is reclassified as thesis-critical.** §Research Impact below originally read "RAG remains a supporting capability, not the thesis contribution." That framing is reversed, on the instruction of the project lead: RAG is thesis-critical work, alongside the clearance-aware resubmission workflow [ADR-003](003-clearance-aware-resubmission.md) describes, not subordinate to it. `CLAUDE.md`'s Scope rule — "cut RAG first if capacity is short" — is corrected to match. This does **not** change what ADR-003/ADR-004's controlled comparison measures: that evaluation is still of the workflow mechanism, unaffected by chunking. What changes is priority and protection, not the evaluation design.

## Context

ADR-006 scoped RAG to the minimum that satisfies FR-M4-01: embed title and abstract only, no chunking, no reranking, no second provider. It was written against `refactor/docker-service`, where nothing in the AI pipeline functioned, and it budgeted three dev-days.

Three things have changed.

**The corpus is already extracted and thrown away.** `documents/models.py:86` stores every uploaded PDF's text in `PdfExtraction.extracted_text`. Nothing reads it for retrieval. `apps/ai/tasks.py:19` embeds `f"{record.title}. {record.abstract}"` and nothing else. IRIS therefore pays the full cost of extraction — Docling or PyMuPDF, a Celery queue, storage — and indexes none of it. ADR-006's "abstracts retrieve well" is a defensible claim about *retrieval quality*; it is not an argument for discarding work already done.

**The abstract-only bound is sharper than it reads.** A thesis abstract does not contain its methodology, its instruments, its sample, or its findings in retrievable detail. A reviewer asking *"which 2024 aquaculture studies used weekly pond sampling?"* is querying a corpus in which no methodology section has ever been indexed. The answer returns, fluently, built from abstracts. That is a worse failure than no answer, because it is not visibly wrong.

**Part of the budget is already spent.** `feat/rag-service` implements the pgvector work ADR-007 scheduled as ~1.5 dev-days: `apps/ai/models/embedding.py` declares a real `VectorField` with an HNSW index on `vector_cosine_ops`, with migrations `0001` and `0002`. `apps/documents/services/pdf_extractor.py` exists. The chunker design is specified in `docs/chunker_architecture.md`.

ADR-006's judgement was correct for the tree it read. It is not correct for this one.

## Decision

**The retrievable unit is the chunk, not the record.**

```
PDF → extraction → normalize → chunk → embed (per chunk)
    → pgvector recall → rerank → grounded answer + citations
```

**In scope, reversing ADR-006:**

1. **Full-text chunking.** Structure-aware over the extracted markdown, with a **context-path prefix** on every chunk — `Thesis Title > 3 Methodology > 3.2 Sampling`. Design in [`../chunker_architecture.md`](../chunker_architecture.md).
2. **Reranking**, as a step inside retrieval between recall and prompt assembly. Recall widened to feed it.
3. **Provider swappability** through the port defined in [ADR-014](014-ai-gateway-as-a-service.md), with the vendor chosen in [ADR-015](015-voyage-embedding-and-reranking.md).

**Retained from ADR-006, unchanged:**

- **Retrieval must filter by record visibility.** ADR-006 called this *"the single most important detail in the RAG work."* It is more important now, not less: a chunk is a fragment of a document, and a fragment of an embargoed thesis is still embargoed. One `visible_to(user)` predicate, applied in retrieval, shared with the record endpoints.
- **No orchestration framework.** LangChain and LlamaIndex remain rejected on ADR-006's deletion test.
- **A timebox with a pre-committed fallback.** Revised to **7 dev-days**, ending Week 7. If chunk-level retrieval is not working at that point, ship **abstract-level semantic search** — the ADR-006 pipeline, which the schema still supports — and reclassify chunking as Phase 2. This is a decision rule fixed now, not a judgement to be made under pressure.

**Still excluded:** conversational memory and history · summarization (FR-M4-02, deferred by ADR-001) · agents · HyDE.

## Alternatives Considered

**Keep ADR-006 unchanged.** Rejected, but it remains the fallback. Its cost argument is real and its timebox discipline is the best thing in it. What defeats it is that the extraction cost is already being paid and the result is discarded — the marginal cost of chunking is the embedding spend and the chunker, not the pipeline.

**Chunk, but skip reranking.** Rejected. Reranking is the cheapest quality gain available: it is priced per query rather than per corpus, it needs no re-indexing, and it composes with any embedding space because a reranker reads text and never touches a vector. Excluding it saves almost nothing.

**Chunk the whole document including bibliography and front matter.** Rejected. A bibliography is 10–20% of a thesis by tokens and retrieves uniformly badly. Section exclusion is a policy in `ChunkingOptions`, not a hardcoded rule — but the default excludes references.

**Late-interaction retrieval (ColBERT-style).** Rejected for this budget. Stronger in principle, materially more storage and a harder operational story, and it cannot be evaluated without the eval set that does not yet exist.

## Decision Rationale

ADR-006 optimised for the risk that RAG consumes the whole semester. That risk is real and this ADR does not dismiss it — it keeps the timebox and the fallback, and enlarges the budget by four dev-days against work already banked elsewhere.

What ADR-006 undervalued is that **abstract-only retrieval is not a smaller version of the product; it is a different product.** Semantic search over abstracts is a better search box. Grounded question-answering over document contents is what FR-M4-01 describes and what a demonstration audience will test. The gap between them is not visible in a status table and is very visible in a live query.

The fallback is what makes this safe. The schema after this ADR is a superset: `RecordEmbedding` remains and continues to serve abstract-level retrieval. If chunking is abandoned in Week 7, nothing is rolled back — one config flip selects the abstract path.

## Consequences

**Positive.** Retrieval reaches document contents. Citations point at passages rather than whole records. The extraction pipeline stops being dead weight. Reranking gives a quality lever independent of the embedding choice.

**Negative.** Embedding spend rises roughly 40× per document — from one vector per record to ~40 chunks. At IRIS scale that is single-digit dollars, but it is no longer zero. Storage rises correspondingly. Re-chunking invalidates vectors, which is why `chunkset_hash` and per-chunk hashing are part of the design rather than an optimisation.

**Risk.** Seven dev-days is optimistic for a team without prior RAG experience. Mitigated by the fallback, and by the chunker being pure, synchronous and testable without infrastructure — the highest-risk component is the one that needs no database to develop.

## Revisit when

Chunk-level retrieval measurably fails to beat abstract-level on the eval set, or the Week 7 timebox expires without working grounded generation.

## MVP Impact

**MVP Required, P1**, timeboxed to 7 dev-days ending Week 7. Degradable to abstract-level semantic search without failing the MVP.

## SaaS Impact

Unchanged from ADR-006. Under [ADR-005](005-instance-per-tenant.md), chunk data is isolated per instance. Chunk volume raises per-tenant storage; at institutional scale this is not material.

## Security Impact

**Significant, and the reason the visibility requirement is restated rather than assumed.** Chunk-level retrieval multiplies the number of rows a bad query can leak by roughly forty. A retrieval path that forgets its filter now returns fragments of unpublished methodology rather than published abstracts.

Chunks inherit their record's visibility. There is no chunk-level permission model in this ADR, and adding one would require [ADR-009](009-authorization-model.md) to be reopened.

## Deployment Impact

No new services beyond those in [ADR-014](014-ai-gateway-as-a-service.md). Chunking is CPU-bound and runs in the Celery worker, off the request path.

## Research Impact

~~Minimal by design. RAG remains a supporting capability, not the thesis contribution ([ADR-003](003-clearance-aware-resubmission.md)).~~ **Superseded by the 2026-09-04 amendment above: RAG is thesis-critical, not merely supporting.** What still holds: chunking does not change what the controlled comparison in [ADR-003](003-clearance-aware-resubmission.md)/[ADR-004](004-restart-all-comparison-mode.md) measures — that experiment is of the workflow mechanism, and RAG's priority status doesn't fold it into that measurement.

## Related Requirements

FR-M3-01 (extraction) · FR-M3-02 (FTS) · FR-M3-03 (embeddings) · FR-M4-01 (RAG chatbot) · NFR-P3 · NFR-P4.

## Related Tasks

`R-01`…`R-06`, revised. See [`06-rag.md`](../architecture-tasks/06-rag.md).
