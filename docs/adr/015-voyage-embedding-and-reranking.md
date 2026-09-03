# ADR-015: Voyage for embedding and reranking

## Status

Accepted — 2026-09-02. **Revised 2026-09-04:** dropped the governance-sign-off precondition (see §Security Impact); adopted `voyage-context-4` as the embedding model; removed the local Ollama fallback this ADR had introduced, which contradicted [ADR-008](008-ai-degradation-to-fts.md)'s already-accepted rejection of a local model. There is no local lane. A `DisclosurePolicy` refusal means that content is not sent to Voyage and is not AI-processed at all — it degrades to the same FTS path ADR-008 already specifies for a vendor outage.

**Extends [ADR-007](007-pgvector-vector-store.md)**, which decided the vector *store*. It does not supersede it — pgvector remains the store. This ADR decides the embedding and reranking *provider*, which ADR-007 left open and [ADR-006](006-minimum-rag-pipeline.md) described only as "a provider protocol."

## Context

ADR-006 excluded multiple providers; [ADR-013](013-chunk-level-rag-pipeline.md) reverses that and adds reranking, which makes the provider a decision rather than a default. ADR-007 rejected Pinecone partly on data governance — *"research abstracts would leave campus"* — and that objection is about a **hosted API**, not specifically about a vector database. It applies with equal force here and is dealt with below rather than sidestepped.

The concrete blockers today: `apps/ai/models/embedding.py` uses `VectorField(dimensions=settings.AI_EMBEDDING_DIMENSIONS)` while migration `0002` hardcodes `1536`; those can silently disagree. `AI_EMBEDDING_PROVIDER` is declared in `config/settings/base.py:188` and read by no code. The gateway carries its own independent `EMBEDDING_PROVIDER`. Two switches, one vector column, and a mismatch that produces plausible rankings rather than an error.

## Decision

**Voyage for embedding and for reranking, always. One vendor for both stages, with no alternative embedding or reranking provider in scope.**

| Stage | Choice |
|---|---|
| Embedding | Voyage `voyage-context-4`, 1024 dimensions (default), `input_type` document/query |
| Reranking | Voyage rerank, over the top ~100 recalled chunks |
| Store | **pgvector, unchanged** (ADR-007) |
| Content a `DisclosurePolicy` refuses | **Not sent to Voyage, not AI-processed.** Degrades to ADR-008's FTS path — the same behavior as a Voyage outage. No local model. |

**One vendor, one API key, one rate-limit budget, one adapter family, one set of failure modes.** Cohere Rerank is the marginally stronger reranker; at this corpus size the difference does not repay a second integration, a second key and a second outage mode.

**Embedding model, revised 2026-09-04: `voyage-context-4`.** This is a *contextualized chunk* embedding model — it produces a chunk's vector already carrying the surrounding document's context, without any manual metadata or context-string augmentation. Voyage's own benchmarks show it retrieving better than standard embeddings both with and without manual context augmentation, while being simpler, faster and cheaper to run, and it is a drop-in replacement for a standard embedder — no downstream retrieval or storage changes. It also **reduces sensitivity to the chunking strategy** — since the model itself supplies document context, a chunk's own vector needs it less. This bears directly on [chunker §5's context-path decorator](chunker_architecture.md#the-context-path--the-single-highest-value-idea-here) (IR-112): default to relying on `voyage-context-4`'s own context-awareness rather than the manual context-path prefix. The prefix and `Chunk.context_path` are kept for one reason only now — display, a citation's breadcrumb — not as an embedding fallback, since there is no second embedding path for it to feed. See [chunker §14, open question on this exact point](chunker_architecture.md#14-open-questions).

**Constraint that must be enforced by the batching code, not assumed:** total input tokens across a batch must not exceed 120,000 when `enable_auto_chunk = true`, or 32,000 when it is false. This replaces the illustrative `VOYAGE_MAX_BATCH_SIZE` item-count cap in [chunker §10](chunker_architecture.md#10-voyage-integration) as the real ceiling batch assembly must respect.

Three rules the implementation must satisfy:

1. **`EmbeddingSpace` is data, not schema.** `(model_id, dimensions, metric, state)` as a row. Vectors are keyed by `(chunk_id, space_id)`. The hardcoded `1536` is replaced and the migration derives its dimension from configuration.
2. **One switch.** The dead `AI_EMBEDDING_PROVIDER` setting is deleted; the active `EmbeddingSpace` is the single source of truth, read by both the indexing and the query path, with a startup assertion that they agree.
3. **Document and query embedding are separate methods**, not a flag — `embed_documents()` and `embed_query()`. Voyage models are asymmetric and mixing the input types degrades retrieval measurably. A boolean makes the wrong call possible; two methods make it impossible.

**The invariant, stated once:** within one `EmbeddingSpace`, the same model embeds documents and queries. Always. Comparing vectors across two models does not error — it returns rows, ranked plausibly, and wrong. Reranking is the exception and composes freely, because a reranker reads text and never touches a vector.

## Alternatives Considered

**A local model (Ollama) as a fallback lane for content the `DisclosurePolicy` refuses.** Rejected outright, not deferred — [ADR-008](008-ai-degradation-to-fts.md) already rejected exactly this ("needs a GPU for usable latency; adds a service and several GB of weights... a second AI system to insure the first") and this ADR's original text contradicted that acceptance without ever revisiting it. There is no local model anywhere in this architecture. Content the `DisclosurePolicy` refuses is simply not AI-processed — it gets the same FTS degradation ADR-008 specifies for a Voyage outage, not a second, cheaper AI path.

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

The eval set shows a different provider materially ahead, or the free tier is exhausted. If `DisclosurePolicy` refusals turn out to affect a large share of the corpus in practice, that is a product gap worth its own decision — reduced AI coverage for that content, not a reason to reconsider a local model, which ADR-008 already settled.

## MVP Impact

**MVP Required, P1.** ~1 dev-day for the adapters and the `EmbeddingSpace` migration, inside the ADR-013 budget.

## SaaS Impact

Each tenant needs its own Voyage key, or the operator holds one and bills through. Under [ADR-005](005-instance-per-tenant.md) vector data stays isolated; **the API key does not**, and a shared key means one tenant's usage is visible in another's rate limit. Per-tenant keys are the correct model and add an onboarding step.

## Security Impact

**Revised 2026-09-04: this is no longer gated on an external governance sign-off.** The prior revision of this ADR made written KTTO/IERC sign-off a precondition for any record content reaching Voyage; that precondition is removed, and Phase 3 of the RAG rollout is not blocked by it. Chunk text still leaves the deployment on every index and every query, and under [ADR-013](013-chunk-level-rag-pipeline.md) that text is methodology, findings and instruments from unpublished theses and pre-filing IP disclosures — so this stays a real security surface, just not one this ADR treats as blocked on an outside approval process. Required before any record content reaches Voyage:

1. **A `DisclosurePolicy` module** consulted at every outbound call, gating on IP status, embargo date and author consent. Anything it refuses is not sent to Voyage and is not AI-processed by any provider — there is no local model to fall back to.
2. **Vendor no-training terms confirmed in writing** and recorded — an explicit account setting, not an assumption.
3. `VOYAGE_API_KEY` treated as a required production secret per CLAUDE.md's Environment and secrets rule — the application refuses to start without it rather than defaulting silently.

[ADR-008](008-ai-degradation-to-fts.md)'s FTS fallback is the *only* fallback, for both a Voyage outage and a `DisclosurePolicy` refusal — the same mechanism, not two. **Search still works either way.**

## Deployment Impact

No new services. Adds one required secret, `VOYAGE_API_KEY`, which the application must refuse to start without rather than defaulting silently.

## Research Impact

None directly. The provider choice does not affect what the controlled comparison in [ADR-004](004-restart-all-comparison-mode.md) measures.

## Related Requirements

FR-M3-03 (embeddings) · FR-M4-01 (RAG chatbot) · FR-M8-03 (embedding index administration) · NFR-S3 · NFR-R2.

## Related Tasks

`R-03`, `R-04` (revised) · a new task for the `EmbeddingSpace` migration · the `DisclosurePolicy` module.
