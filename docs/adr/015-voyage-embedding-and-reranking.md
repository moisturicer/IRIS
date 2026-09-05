# ADR-015: Voyage for embedding and reranking

## Status

Accepted — 2026-09-02, **conditional on the data-governance sign-off in §Security Impact.**

**Extends [ADR-007](007-pgvector-vector-store.md)**, which decided the vector *store*. It does not supersede it — pgvector remains the store. This ADR decides the embedding and reranking *provider*, which ADR-007 left open and [ADR-006](006-minimum-rag-pipeline.md) described only as "a provider protocol."

## Context

ADR-006 excluded multiple providers; [ADR-013](013-chunk-level-rag-pipeline.md) reverses that and adds reranking, which makes the provider a decision rather than a default. ADR-007 rejected Pinecone partly on data governance — *"research abstracts would leave campus"* — and that objection is about a **hosted API**, not specifically about a vector database. It applies with equal force here and is dealt with below rather than sidestepped.

The concrete blockers today: `apps/ai/models/embedding.py` uses `VectorField(dimensions=settings.AI_EMBEDDING_DIMENSIONS)` while migration `0002` hardcodes `1536`; those can silently disagree. `AI_EMBEDDING_PROVIDER` is declared in `config/settings/base.py:188` and read by no code. The gateway carries its own independent `EMBEDDING_PROVIDER`. Two switches, one vector column, and a mismatch that produces plausible rankings rather than an error.

## Decision

**Voyage for embedding and for reranking. One vendor.**

| Stage | Choice |
|---|---|
| Embedding | Voyage, 1024 dimensions, `input_type` document/query |
| Reranking | Voyage rerank, over the top ~100 recalled chunks |
| Store | **pgvector, unchanged** (ADR-007) |
| Local fallback | Ollama, for anything the disclosure policy refuses |

**One vendor, one API key, one rate-limit budget, one adapter family, one set of failure modes.** Cohere Rerank is the marginally stronger reranker; at this corpus size the difference does not repay a second integration, a second key and a second outage mode.

Three rules the implementation must satisfy:

1. **`EmbeddingSpace` is data, not schema.** `(model_id, dimensions, metric, state)` as a row. Vectors are keyed by `(chunk_id, space_id)`. The hardcoded `1536` is replaced and the migration derives its dimension from configuration.
2. **One switch.** The dead `AI_EMBEDDING_PROVIDER` setting is deleted; the active `EmbeddingSpace` is the single source of truth, read by both the indexing and the query path, with a startup assertion that they agree.
3. **Document and query embedding are separate methods**, not a flag — `embed_documents()` and `embed_query()`. Voyage models are asymmetric and mixing the input types degrades retrieval measurably. A boolean makes the wrong call possible; two methods make it impossible.

**The invariant, stated once:** within one `EmbeddingSpace`, the same model embeds documents and queries. Always. Comparing vectors across two models does not error — it returns rows, ranked plausibly, and wrong. Reranking is the exception and composes freely, because a reranker reads text and never touches a vector.

## Alternatives Considered

**Ollama only, nothing leaves campus.** Rejected as the default, retained as the fallback lane. It is the only option with no governance question at all, and if the sign-off in §Security Impact is refused it becomes the decision by default. Retrieval quality is materially below the hosted models, and CPU-only embedding of the full corpus is slow.

**Cohere for reranking, Voyage for embedding.** Rejected. Best-of-breed on paper; two vendors, two keys, two rate limiters and two failure modes for a quality difference that this corpus size does not surface. Revisit if the eval set shows reranking is the binding constraint.

**OpenAI `text-embedding-3-small`.** Rejected as the default. It is what the code assumes today and its 1536 dimensions are what the migration hardcodes — but it is the weaker retriever of the two, and staying with it would mean keeping the dimension coupling this ADR exists to remove. Remains a valid adapter.

**Pinecone Inference for embedding and reranking.** Rejected. It pulls toward Pinecone as the store, which ADR-007 settled against on hybrid-search and sync grounds that this ADR does not reopen.

**A second `EmbeddingSpace` to A/B Voyage against Cohere.** Deferred, not rejected. It costs a second full corpus embedding — there is no cheaper form of that experiment — which is affordable but not before the eval set exists to judge the result.

## Decision Rationale

The vendor matters less than the two structural fixes attached to it. `EmbeddingSpace`-as-data is what makes **any** provider decision reversible: without it, `OneToOneField` plus a hardcoded dimension means no shadow index, no A/B and no rollback — only a destructive re-index in both directions. That is a one-way door, and it is open today.

Voyage specifically: strong retrieval quality, a free tier large enough to embed this corpus at no cost, embedding and reranking from one vendor, and 1024 dimensions — which halves storage against 1536 and is a real consideration once ADR-013 multiplies row count by forty.

Reranking is the cheapest quality lever available: priced per query rather than per corpus, needing no re-indexing, and independent of the embedding space.

## Consequences

**Positive.** One vendor to integrate, monitor and pay. Reranking without re-indexing. `EmbeddingSpace` makes every future provider decision reversible. 1024 dimensions cut storage by a third against the current assumption.

**Negative.** A recurring external dependency and cost where there was none. A vendor outage degrades retrieval — mitigated by [ADR-008](008-ai-degradation-to-fts.md), which is unchanged and remains the fallback. Migration `0002` must be revised before any corpus is indexed.

**Risk.** The free tier is a trial tier with rate limits, not a production allowance. Backfill must batch and respect a token budget, and the ingestion and query lanes need separate budgets so a re-index cannot starve interactive queries.

## Revisit when

The eval set shows a different provider materially ahead, the free tier is exhausted, or the governance sign-off is refused — in which case the Ollama lane becomes the decision.

## MVP Impact

**MVP Required, P1.** ~1 dev-day for the adapters and the `EmbeddingSpace` migration, inside the ADR-013 budget.

## SaaS Impact

Each tenant needs its own Voyage key, or the operator holds one and bills through. Under [ADR-005](005-instance-per-tenant.md) vector data stays isolated; **the API key does not**, and a shared key means one tenant's usage is visible in another's rate limit. Per-tenant keys are the correct model and add an onboarding step.

## Security Impact

**This is the blocking condition on this ADR.**

Chunk text leaves the deployment on every index and every query. Under [ADR-013](013-chunk-level-rag-pipeline.md) that text is no longer abstracts — it is methodology, findings and instruments from **unpublished theses and pre-filing IP disclosures**. `security/SECURITY.md` §8 records that permission for external AI transmission is **UNCONFIRMED**, and ADR-007 rejected a hosted store partly on those grounds.

**This ADR does not resolve that. It cannot — it is not a technical question.**

Required before any record content reaches Voyage:

1. **Written sign-off** from KTTO and IERC that pre-publication research content may be transmitted to a commercial API, naming the vendor.
2. **A `DisclosurePolicy` module** consulted at every outbound call, gating on IP status, embargo date and author consent. Anything it refuses routes to the local Ollama lane.
3. **Vendor no-training terms confirmed in writing** and recorded — an explicit account setting, not an assumption.
4. **Synthetic and already-published data only** until 1 and 3 are complete.

If sign-off is refused, the Ollama lane is the decision and ADR-008's FTS fallback is the product. **Search still works either way.**

## Deployment Impact

No new services. Adds one required secret, `VOYAGE_API_KEY`, which the application must refuse to start without rather than defaulting silently.

## Research Impact

None directly. The provider choice does not affect what the controlled comparison in [ADR-004](004-restart-all-comparison-mode.md) measures.

## Related Requirements

FR-M3-03 (embeddings) · FR-M4-01 (RAG chatbot) · FR-M8-03 (embedding index administration) · NFR-S3 · NFR-R2.

## Related Tasks

`R-03`, `R-04` (revised) · a new task for the `EmbeddingSpace` migration · the governance sign-off, which is not an engineering task.
