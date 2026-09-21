# ADR-015: Voyage for embedding and reranking

## Status

Accepted — 2026-09-02. **Revised 2026-09-04:** dropped the governance-sign-off precondition (see §Security Impact); adopted `voyage-context-4` as the embedding model; removed the local Ollama fallback this ADR had introduced, which contradicted [ADR-008](008-ai-degradation-to-fts.md)'s already-accepted rejection of a local model. There is no local lane. A `DisclosurePolicy` refusal means that content is not sent to Voyage and is not AI-processed at all — it degrades to the same FTS path ADR-008 already specifies for a vendor outage. **Revised again 2026-09-04:** "vendor no-training terms confirmed in writing" is replaced with the verified, actual mechanism — an opt-out toggle, not a default, not a written confirmation (see §Security Impact).

**Revised 2026-09-20 (IR-281, IR-282) — recorded by an agent, awaiting a reviewer's acceptance.** Adds rule 4 below (chunks are embedded grouped by document, on the contextualized endpoint) and §Indexing operations (a spend ceiling and a promotion gate). Both record decisions that were taken while implementing IR-281 and IR-282 and that had no written basis; neither changes the vendor, the model, the store or the disclosure gate. Per CLAUDE.md §What AI does not decide, an agent may record these but may not accept them.

**Revised 2026-09-21 — permits a development-only disclosure bypass (IR-317).** Adds §A development bypass below. The gate itself is unchanged; what is added is a narrow, loud, `DEBUG`-only way to stand beside it while [IR-250](https://citiris.atlassian.net/browse/IR-250) waits on decisions CIT-U has to make. Recorded by an agent and awaiting a reviewer's acceptance.

**Revised 2026-09-20 — pins the reranker.** This ADR always said "Voyage rerank" without naming a model, and the deployed `.env` had drifted to `rerank-3` while the code default and every docstring referencing it said `rerank-2` — an undocumented choice contradicting a stale one, neither written down. Decided in a live operator session (manual end-to-end verification against a real dev corpus, this ADR's first): **`rerank-3`**, same price as `rerank-2` ($0.05/M tokens either way), so the choice was about not leaving code and environment disagreeing rather than about cost. The code default and `.env.example` are updated to match; nothing about the vendor, the embedding model, the store or the disclosure gate changes.

**Extends [ADR-007](007-pgvector-vector-store.md)**, which decided the vector *store*. It does not supersede it — pgvector remains the store. This ADR decides the embedding and reranking *provider*, which ADR-007 left open and [ADR-006](006-minimum-rag-pipeline.md) described only as "a provider protocol."

## Context

ADR-006 excluded multiple providers; [ADR-013](013-chunk-level-rag-pipeline.md) reverses that and adds reranking, which makes the provider a decision rather than a default. ADR-007 rejected Pinecone partly on data governance — *"research abstracts would leave campus"* — and that objection is about a **hosted API**, not specifically about a vector database. It applies with equal force here and is dealt with below rather than sidestepped.

The concrete blockers today: `apps/ai/models/embedding.py` uses `VectorField(dimensions=settings.AI_EMBEDDING_DIMENSIONS)` while migration `0002` hardcodes `1536`; those can silently disagree. `AI_EMBEDDING_PROVIDER` is declared in `config/settings/base.py:188` and read by no code. The gateway carries its own independent `EMBEDDING_PROVIDER`. Two switches, one vector column, and a mismatch that produces plausible rankings rather than an error.

## Decision

**Voyage for embedding and for reranking, always. One vendor for both stages, with no alternative embedding or reranking provider in scope.**

| Stage | Choice |
|---|---|
| Embedding | Voyage `voyage-context-4`, 1024 dimensions (default), `input_type` document/query |
| Reranking | Voyage `rerank-3`, over the top ~100 recalled chunks |
| Store | **pgvector, unchanged** (ADR-007) |
| Content a `DisclosurePolicy` refuses | **Not sent to Voyage, not AI-processed.** Degrades to ADR-008's FTS path — the same behavior as a Voyage outage. No local model. |

**One vendor, one API key, one rate-limit budget, one adapter family, one set of failure modes.** Cohere Rerank is the marginally stronger reranker; at this corpus size the difference does not repay a second integration, a second key and a second outage mode.

**Embedding model, revised 2026-09-04: `voyage-context-4`.** This is a *contextualized chunk* embedding model — it produces a chunk's vector already carrying the surrounding document's context, without any manual metadata or context-string augmentation. Voyage's own benchmarks show it retrieving better than standard embeddings both with and without manual context augmentation, while being simpler, faster and cheaper to run, and it is a drop-in replacement for a standard embedder — no downstream retrieval or storage changes. It also **reduces sensitivity to the chunking strategy** — since the model itself supplies document context, a chunk's own vector needs it less. This bears directly on [chunker §5's context-path decorator](chunker_architecture.md#the-context-path--the-single-highest-value-idea-here) (IR-112): default to relying on `voyage-context-4`'s own context-awareness rather than the manual context-path prefix. The prefix and `Chunk.context_path` are kept for one reason only now — display, a citation's breadcrumb — not as an embedding fallback, since there is no second embedding path for it to feed. See [chunker §14, open question on this exact point](chunker_architecture.md#14-open-questions).

**Constraint that must be enforced by the batching code, not assumed:** total input tokens across a batch must not exceed 120,000 when `enable_auto_chunk = true`, or 32,000 when it is false. This replaces the illustrative `VOYAGE_MAX_BATCH_SIZE` item-count cap in [chunker §10](chunker_architecture.md#10-voyage-integration) as the real ceiling batch assembly must respect.

Three rules the implementation must satisfy:

1. **`EmbeddingSpace` is data, not schema.** `(model_id, dimensions, metric, state)` as a row. Vectors are keyed by `(chunk_id, space_id)`. The hardcoded `1536` is replaced and the migration derives its dimension from configuration.
2. **One switch.** The dead `AI_EMBEDDING_PROVIDER` setting is deleted; the active `EmbeddingSpace` is the single source of truth, read by both the indexing and the query path, with a startup assertion that they agree.
3. **Document and query embedding are separate methods**, not a flag — `embed_documents()` and `embed_query()`. Voyage models are asymmetric and mixing the input types degrades retrieval measurably. A boolean makes the wrong call possible; two methods make it impossible.

4. **Chunks are embedded grouped by the document they came from, on the contextualized endpoint** (added 2026-09-20, IR-281). `voyage-context-4` is served from `POST /v1/contextualizedembeddings`, whose payload is a list of *documents*, each a list of that document's chunks. The flat `/v1/embeddings` endpoint serves the standard models; sending a contextualized model's traffic there is accepted by the API and **silently discards the sibling-chunk context that is the entire reason this ADR chose the model** — a passage reading "this approach reduced error by 12%" stops meaning anything once retrieved alone. The port therefore grows a third method, `embed_document_chunks(documents)`, taking and returning the grouping; `embed_documents` and `embed_query` route through the same endpoint with each text as its own one-chunk document, so there is one wire format rather than two to keep in step.

   **Two consequences that follow from the grouping being load-bearing.** Batch assembly's unit becomes the *document*: a document is never split across two requests, because half a document's chunks in view is not the context the model was chosen for. And a document larger than the whole token budget is sent alone and whole, letting the vendor reject it and say so, rather than being quietly split.

   **Why this is a rule and not an implementation detail.** Nothing downstream can detect the mistake. A chunk embedded without its siblings produces a well-formed vector of the right width in the right space; it simply means less than it should, and the only symptom is retrieval that is worse than it ought to be for reasons no test would attribute to the endpoint. That is the same class of failure as rule 3's asymmetry and is guarded the same way — by making the wrong call hard to express rather than by remembering not to make it.

**The invariant, stated once:** within one `EmbeddingSpace`, the same model embeds documents and queries. Always. Comparing vectors across two models does not error — it returns rows, ranked plausibly, and wrong. Reranking is the exception and composes freely, because a reranker reads text and never touches a vector.

## Indexing operations: a spend ceiling and a promotion gate

*Added 2026-09-20 (IR-282). §Consequences already named the risk — "the free tier is a trial tier with rate limits, not a production allowance" — without saying what enforces it. This is what.*

**A corpus run states its cost before it spends anything, and a ceiling refuses.** `backfill_embeddings` prints the records, chunks and estimated tokens it would send, and stops when the estimate exceeds `AI_EMBEDDING_TOKEN_CEILING`. The estimate is deliberately an **upper bound, not a quote**: it reuses the same estimator batch assembly uses, so the number an operator is shown and the number the run batches against cannot drift apart, and both overcount — an overcount costs one extra request, an undercount costs money.

This is a refusal rather than a warning because the risk is live, not theoretical. `AI_CHUNK_MAX_TOKENS` counts whitespace **words**, not tokenizer tokens, and is about 44% under the real BPE count (IR-243, which deliberately left the number alone pending IR-133's evidence). A ceiling that only warned would be read past exactly once.

**Resume and skip are properties of the query, not of a checkpoint.** What a run embeds is "active chunks with no vector in this space", recomputed every time. So a crash at record 3,000 resumes at record 3,000, and a finished corpus re-runs for one query per record and no vendor call — without any bookkeeping that could itself be lost in the crash that made it necessary. "Already has a vector in this space" *is* the unchanged-text skip, because a chunk whose text survives a re-chunk carries its vector across (ADR-013); there is deliberately no second definition of "unchanged" to disagree with the first.

**Promotion is a separate, refusable command, and nothing promotes automatically.** An `EmbeddingSpace` may not become `active` while any active chunk lacks a vector in it. A half-indexed space is worse than an empty one: it answers confidently from the half it holds, and a chunk with no vector does not rank low — it is not there, invisibly, to the reader and to the ranking alike. The refusal names which records are short and by how much, because "4,910 chunks short" is not something an operator can act on.

Promotion also refuses a **retired** space and a space whose width disagrees with the vector columns, so that what may be promoted and what may be written to cannot disagree about the same row.

**Recorded limitation.** A pending space can be filled with *chunk* vectors only. `RecordEmbedding` is one row per record with no space key, so a summary vector cannot exist in two spaces at once, and writing one while filling a pending space would overwrite the live space's. Making record-level vectors space-keyed is schema work that has not been done, and it is a precondition for the first real model change — at which point stage 1 of ADR-013's retrieval would otherwise have to be re-indexed in place, live.

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
2. **Training opt-out exercised via Voyage's dashboard toggle before any record content is sent** — an explicit account setting, not an assumption, and not the default. Verified against [voyageai.com/tos](https://www.voyageai.com/tos), 2026-09-04: Voyage's ToS §3(iii) grants Voyage a license to train on Customer Content **unless** the account opts out; the toggle lives in the dashboard under Terms of Service, and **requires a payment method on file** — the free tier alone cannot opt out. Two consequences to carry into ops: opting out is retroactive only from that point forward (content submitted before the toggle is flipped remains subject to the training license), and Voyage may void free credits once opted out. This ADR's requirement is the toggle flipped and a payment method on file *before* Phase 3 sends any record content — a written confirmation from Voyage was never how this worked and is dropped as a precondition.
3. `VOYAGE_API_KEY` treated as a required production secret per CLAUDE.md's Environment and secrets rule — the application refuses to start without it rather than defaulting silently.

[ADR-008](008-ai-degradation-to-fts.md)'s FTS fallback is the *only* fallback, for both a Voyage outage and a `DisclosurePolicy` refusal — the same mechanism, not two. **Search still works either way.**

### A development bypass, added 2026-09-21 (IR-317)

Requirement 1 above is working exactly as specified, and the consequence is that **nothing can be indexed at all**: `Record` carries no embargo field, an undetermined embargo is treated as an embargo, and so every record is refused. That is [IR-250](https://citiris.atlassian.net/browse/IR-250), and it cannot be closed by engineering — it turns on four questions CIT-U has to answer, with external lead time. Meanwhile the whole RAG feature set is being built and reviewed without anyone able to run it end to end outside a test harness.

**This ADR permits a bypass for development, under conditions, and permits nothing else.**

**What is explicitly not permitted: inventing a policy.** The shortcut this rules out is shipping a rule that merely sounds defensible — "published records are not embargoed" — because a plausible rule is *more* dangerous than a labelled bypass. It reads as a decision somebody made. Months on, nobody can separate CIT-U's actual policy from a placeholder added to unblock a sprint, and the placeholder has quietly become the policy. A switch named `BYPASS_FOR_DEVELOPMENT` can never be mistaken for one.

**What is also not permitted: a schema change.** Adding `Record.embargoed_until` now looks like "add the missing fact," which is what this ADR would otherwise ask for, but a nullable column reads as `None` on every existing row and `None` means *known not embargoed*. That does not open the gate temporarily; it removes it permanently and silently, with nothing left to switch back. The field's shape is also IR-250's first open question. The bypass is therefore **runtime only**, so IR-250 later lands as one migration and a deliberate backfill.

**The conditions, all four required.** The switch is not what makes this acceptable — these are:

1. **It cannot run in production.** Set while `DEBUG=False`, the application raises `ImproperlyConfigured` and refuses to start. It takes the service down rather than quietly disabling a control, which is the same posture requirement 3 takes toward a missing `VOYAGE_API_KEY`.
2. **It is loud while on** — a warning logged on every affected request, and a flag on `GET /api/v1/ai/status/` so the interface can say so and a demo screenshot labels itself.
3. **It is off by default**, and both 1 and 2 are asserted by tests, so leaving it behind breaks the build rather than going unnoticed.
4. **It points only at content already cleared to leave.** The dev corpus is public CIT-U papers deliberately loaded for the purpose. Pointing it at real unpublished student submissions is not permitted, which is why it must be removed **before [IR-278](https://citiris.atlassian.net/browse/IR-278) delivers a real corpus** — not merely before release.

**Removal is IR-250.** When the embargo fact exists, the setting, its startup guard, the dev command and the status flag come out together.

#### Two divergences in the implementation, recorded rather than reconciled (2026-09-21)

Both surfaced in review of IR-317 and are named here because CLAUDE.md §Source-of-truth hierarchy asks for the contradiction to be written down rather than smoothed over. Recorded by an agent; a reviewer decides whether to accept them or to change the code.

1. **`index_with_disclosure_bypass --force` runs with `DEBUG` off.** Condition 1 above says the bypass cannot run in production. The *setting* honours that absolutely — Django refuses to start. The *command* does not: it follows `seed_demo` and `load_corpus`'s refuse-unless-`DEBUG`-unless-`--force` pattern, which IR-317's acceptance criteria asked for explicitly. The distinction being relied on is that a command is run deliberately by a person at a terminal, while a setting travels in an environment file and runs unattended — but that distinction is this note's, not condition 1's. If it is not accepted, `--force` should go.
2. **The status flag reports the setting, not the command.** Condition 2 asks that the bypass be visible on `GET /api/v1/ai/status/`. It reports `AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT`, so a corpus indexed by the command on a deployment with the setting off is *not* self-labelling — the index was built without an embargo check and nothing in the API says so. Making it honest needs a durable fact about how a vector was produced, which is schema, and schema is what this bypass refuses to add. The command prints the gap in its own pre-send warning instead.

### One consequence of requirement 2 that just became live

Requirement 2 records that Voyage's training opt-out **requires a payment method on file**, and that opting out is **not retroactive** — content sent before the toggle is flipped stays under the training license granted by ToS §3(iii).

A payment method was added to the Voyage account on 2026-09-20. That removes the blocker on flipping the toggle, and it also means the question is now live rather than theoretical: **real CIT-U paper content was sent to Voyage on 2026-09-20** (records 29, 45, 54 and 55, during manual verification) — under a monkeypatched gate, before this section existed, and with the opt-out status not verified at the time.

Two things follow, neither of which this ADR can settle by itself:

* **The toggle should be confirmed flipped before the IR-317 bypass sends anything further.** A bypass that increases the volume of content going to a vendor while the training opt-out is unverified compounds exactly the exposure requirement 2 exists to bound.
* **What was already sent cannot be un-sent.** That is a fact for a person to weigh, not an engineering task — it concerns three published CIT-U papers and one summary vector. It is recorded here rather than left in a terminal scrollback.

## Deployment Impact

No new services. Adds one required secret, `VOYAGE_API_KEY`, which the application must refuse to start without rather than defaulting silently.

## Research Impact

None directly. The provider choice does not affect what the controlled comparison in [ADR-004](004-restart-all-comparison-mode.md) measures.

## Related Requirements

FR-M3-03 (embeddings) · FR-M4-01 (RAG chatbot) · FR-M8-03 (embedding index administration) · NFR-S3 · NFR-R2.

## Related Tasks

`R-03`, `R-04` (revised) · a new task for the `EmbeddingSpace` migration · the `DisclosurePolicy` module.
