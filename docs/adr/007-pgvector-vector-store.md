# ADR-007: pgvector as the vector store

## Status

Accepted — 2026-09-01. Ratifies a decision the SRS already made.

## Context

Jira `IR-9` and `IR-15` specify **Qdrant**. The current SRS specifies **pgvector**, emphatically and in several places:

| Source | Statement |
|---|---|
| SRS §456 | *"The pgvector extension enables cosine similarity queries using HNSW indexes directly within PostgreSQL, **eliminating the need for a separate vector database service**."* |
| SRS §624 | *"**There is no separate vector database service or additional network port.**"* |
| SRS §462-478 | Interface tables specify `pgvector 0.5+`, `VectorField`, HNSW, the `<=>` operator |
| SRS mentions | pgvector **13** · Qdrant **2** (a change-history line and one backup-table row) |

The Jira tickets predate the May 2026 SRS revision and were never updated. This is not a live disagreement — it is stale backlog.

The code implements neither. `apps/ai/models.py:26` declares `embedding = models.BinaryField()`; `apps/ai/tasks.py:57` stores `pickle.dumps(vector)`; `apps/ai/views.py` loads **every** `RecordEmbedding` row, `pickle.loads` each one, and computes cosine similarity in a Python loop. `pgvector` is listed **twice** in `requirements/base.txt` (`>=0.3` at line 11, `>=0.2.4` at line 21) and is absent from `INSTALLED_APPS`, while the Compose `db` image is already `pgvector/pgvector:pg16`.

## Decision

**pgvector, inside the existing PostgreSQL instance.**

`RecordEmbedding.embedding` becomes a `VectorField(dimensions=N)` with an HNSW index created in a migration. Retrieval uses the ORM's `CosineDistance` annotation with `LIMIT k` — one indexed SQL query. All `pickle` usage is removed. The duplicate requirements entry is deduplicated and `pgvector` added to `INSTALLED_APPS`.

Jira `IR-9` and `IR-15` are rewritten to match; `IR-35`'s Qdrant retrieval is likewise replaced.

## Alternatives Considered

**Qdrant** (as Jira specifies). Rejected. It contradicts the team's own governing document, adds a stateful service with its own backup target and consistency story, and introduces an ID-sync path between two stores. Under ADR-005 it would also mean one Qdrant instance per tenant.

**Weaviate / Milvus.** Rejected for the same reasons, with more operational weight.

**Pinecone or another managed service.** Rejected. Recurring cost, vendor lock-in, and research abstracts would leave campus — which conflicts with the unresolved data-governance question and with SRS §456's on-premise requirement.

**FAISS in-process.** Rejected. No persistence, no concurrency story, no transactional consistency with `Record`.

**Keep `BinaryField` + pickle + NumPy.** Rejected. O(n) rows into application memory per query, and unpickling database content is an unsafe-deserialization pattern.

## Decision Rationale

**Deletion test on a separate vector database: fails.** Removing Qdrant and using pgvector *reduces* total complexity by one service, one backup target, one credential and one sync path. An abstraction whose removal simplifies the system does not earn its place.

The corpus is a single university's research records — hundreds to low thousands of documents. HNSW in PostgreSQL is sub-second well past that scale, by orders of magnitude.

Under ADR-005, tenant isolation of vector data is free: separate instance, separate database, no metadata filtering to implement correctly and no cross-tenant retrieval risk. Qdrant would require collection-per-tenant or payload filtering — more work and a new class of bug.

The SRS is the governing document and it is already correct. This ADR exists so the decision is findable, since its previous home was a single change-history line that the backlog did not track.

## Consequences

**Positive.** No new service. Transactional consistency with `Record`. Backup and restore cover vectors automatically. Removes a code-execution primitive.

**Negative.** Vector search scales with the PostgreSQL instance; a genuinely large corpus would eventually need dedicated infrastructure. Not reachable at institutional scale.

**Risk.** `dimensions` must match the embedding provider (ADR-006, provider protocol). Fixing it before the provider is chosen means redoing the migration — so the provider decision must land first.

## Revisit when

Corpus exceeds ~1M vectors, or p95 retrieval latency exceeds ~200 ms at production scale with the HNSW index tuned.

## MVP Impact

**MVP Required, P1.** ~1.5 dev-days as part of the RAG timebox.

## SaaS Impact

Positive. Per-instance isolation is structural. Onboarding an institution requires no vector-store provisioning beyond the database that already exists.

## Security Impact

Removes `pickle.loads` over database rows — a code-execution primitive one SQL injection or one compromised backup restore away from the application. Currently unreachable because the module is shadowed, but it would become reachable the moment `apps/ai` is un-shadowed.

## Deployment Impact

None — the Compose image already provides the extension. The migration must issue `CREATE EXTENSION vector`.

## Research Impact

None directly. Supports the RAG capability the product demonstrates.

## Related Requirements

FR-M3-03 (vector embedding generation) · FR-M4-01 (RAG chatbot) · FR-M8-03 (embedding index administration) · SRS §456, §462-478, §624.

## Related Tasks

`R-03`, `B-04` (un-shadow `apps/ai`), `13-jira-reconciliation.md` (IR-9, IR-15, IR-35 rewrites).
