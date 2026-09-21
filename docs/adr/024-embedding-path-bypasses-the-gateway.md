# ADR-024: The embedding path does not go through the AI gateway

## Status

**Accepted** — 2026-09-17. **Implemented 2026-09-20 by IR-281** — see §Implementation below. That note is recorded by an agent and awaits a reviewer's acceptance; it reports what was built and changes none of the decision above.

**Narrows [ADR-014](014-ai-gateway-as-a-service.md); does not supersede it.** ADR-014's adoption of the gateway stands, along with all six preconditions (its five, plus [ADR-017](017-asgi-deployment-for-gateway-streaming.md)'s ASGI requirement). This ADR removes one workload from it.

**Partially reinstates [ADR-012](012-ai-provider-abstraction-not-a-service.md)'s reasoning** for the indexing path specifically. ADR-012 remains superseded for the chat path.

## Context

`apps/ai/tasks.embed_record` computes a record's vector by calling the gateway over HTTP:

```python
url = f"{settings.AI_GATEWAY_URL}/api/v1/ai/internal/embed/"
response = httpx.post(url, json={"text": text}, timeout=60.0)
vector = response.json().get("embedding")
```

This is the only reason the gateway sits on the indexing path.

### Audited in the tree, 2026-09-17

| Finding | Detail |
|---|---|
| **The route does not exist** | The gateway registers `POST /api/v1/ai/embed` (`ai/main.py` mounts the router at `/api/v1/ai`). The task posts to `/api/v1/ai/internal/embed/` — different path, trailing slash. A 404 on a healthy container |
| **The endpoint returns no vector** | `EmbedResponse` carries `record_id`, `dimensions`, `success`. There is no `embedding` field. `.get("embedding")` yields `None`, and `None` is written into a `VectorField` |
| **It is wired to the wrong provider** | The gateway's `EMBEDDING_MODEL` is `text-embedding-3-small` — OpenAI, 1536 dimensions. [ADR-015](015-voyage-embedding-and-reranking.md) settled Voyage at 1024 as the only embedding provider in scope |
| **The gateway does boot** | ADR-012's audit found `ai/services/` empty. It no longer is: `chat_service.py` (41 lines) and `embedding_service.py` (40) both exist, fixed under IR-156. **CLAUDE.md's claim that the gateway crashes on a missing `chat_service` is stale and is corrected by this ADR** |

Three independent failures, none of which is the one the project believed it had. The gateway is not broken here — it is simply not connected to anything that works, and is pointed at a provider the project replaced.

**The gateway holds no database connection**, by ADR-014 precondition 4, which that ADR calls not negotiable. On the embedding path it is therefore a pure text-in, vector-out hop.

## Decision

**Django computes embeddings in-process, through the `EmbeddingProvider` port, for both record-level and chunk-level vectors.**

`VoyageEmbeddingProvider` is called directly from the Celery task, exactly as `DoclingExtractor` and the LLM provider already are. No network hop, no second container on the indexing path.

**The gateway keeps its ADR-014 mandate for streaming chat.** That workload has a real justification — a long-lived streaming response that would otherwise occupy a Django worker, which is why ADR-017 exists. Embedding has none of that shape: it is a short request/response inside a background worker that is already asynchronous.

**`AI_GATEWAY_URL` is removed from the indexing path**, and with it the requirement that a Celery worker have a second container alive to index anything.

## Alternatives Considered

**Repair the gateway's embed endpoint.** Fix the route, add the vector to `EmbedResponse`, re-point it at Voyage, then satisfy ADR-014's six preconditions before it may be deployed. Rejected: it is real work ending somewhere functionally identical to calling the provider directly. Because the gateway may hold no database connection, nothing on this path can ever live behind it except the vendor call itself — so the boundary buys no isolation, no reuse and no separation of concerns. It only buys a failure mode.

**Keep the hop for symmetry with the future chat path.** Rejected. Symmetry between two workloads with different shapes is not a benefit; ADR-012 made this argument and ADR-014 answered it only for streaming.

**Skip record-level vectors entirely and build chunk embedding alone.** Rejected. [ADR-013](013-chunk-level-rag-pipeline.md)'s two-stage retrieval ranks candidate *records* on `RecordEmbedding` before ranking chunks within them. Without record vectors, stage 1 returns nothing and stage 2 never runs.

## Decision Rationale

The decisive fact is precondition 4. A component that may not read the database can only ever be a proxy for the vendor call on this path, and a proxy that adds a hop, a container dependency and a 404 is worse than the call it wraps.

The second reason is evidential: three independent breakages went unnoticed because nothing on this path has ever produced a vector. Removing the hop removes the place the failures hid.

## Implementation

*Added 2026-09-20 (IR-281). This ADR was accepted three days before anything implemented it; this records what landed, so the next reader does not have to diff the tree to find out whether an accepted decision is real.*

Each consequence below is the one this ADR predicted, with what actually happened:

| This ADR said | What landed |
|---|---|
| "`tasks.embed_record` is rewritten against the port" | Done. It calls `apps.ai.indexing.embed_record_summary`, which goes through `EmbeddingProvider`. No `httpx` call, no gateway URL |
| "the chunk-embedding task is written against the same port from the start" | Done — `ai.tasks.embed_chunk_set`, and `index_record` for the corpus backfill. `apps/ai/indexing.py` is the seam all three share |
| "Indexing no longer depends on the `ai-gateway` container being up" | Done, and **asserted rather than trusted**: `apps/ai/tests/test_indexing_does_not_use_the_gateway.py` walks every module under `apps/ai/` and fails if any reads `AI_GATEWAY_URL`. The way this regresses is one `import httpx` in a task nobody looks at again, which is precisely how the three breakages below went unnoticed |
| "The gateway's `/embed` endpoint becomes dead code on the Django side" | Confirmed. Left in place, as this ADR directed; nothing calls it |
| "`AI_GATEWAY_URL` is no longer required by the Celery workers" | Confirmed. The setting remains in `config/settings/base.py` for ADR-014's streaming-chat mandate and is read by nothing |

**One thing this ADR did not anticipate.** It framed the gateway hop as a pure text-in, vector-out proxy, which is true of the *transport* — but it is also where an outbound call to a commercial vendor would have been made, and [ADR-015](015-voyage-embedding-and-reranking.md) §Security Impact puts a `DisclosurePolicy` gate in front of every one of those. Moving the call in-process moves the gate's enforcement point with it, so `apps/ai/indexing.py` applies it before either kind of vector is computed.

The consequence is worth stating plainly: **the gate refuses every record today**, because `Record` carries no embargo field and an undetermined embargo is treated as an embargo (IR-250). That is the correct failure direction for a gate whose purpose is to stop content leaving, and it means this ADR's path is complete and correct while indexing a real corpus still waits on IR-250. Nothing in the implementation works around it — the way past a fail-closed gate is to supply the missing fact, not to make the gate optional.

## Consequences

- `tasks.embed_record` is rewritten against the port; the chunk-embedding task is written against the same port from the start.
- Indexing no longer depends on the `ai-gateway` container being up.
- The gateway's `/embed` endpoint becomes dead code on the Django side. It is left in place rather than deleted, since ADR-014 keeps the service, but nothing calls it.
- CLAUDE.md's architecture table is corrected: the gateway boots, and the reason not to deploy it is ADR-014's preconditions, not a missing module.
- The gateway's OpenAI configuration (`text-embedding-3-small`, `OPENAI_API_KEY`) is now unused by any live path and should not be taken as evidence of a second embedding provider. ADR-015's "Voyage, always" is unchanged.

## MVP Impact

Removes a service dependency from the critical indexing path. Net simplification.

## SaaS Impact

One fewer container that must be healthy for a tenant to index. Under [ADR-005](005-instance-per-tenant.md) that cost was per-tenant.

## Security Impact

Positive and material. The gateway's embed endpoint has no authentication — ADR-012's audit recorded that both endpoints are open to anything that can reach the container, which holds an API key. Taking the indexing path off it means record text is no longer sent to an unauthenticated endpoint, and removes the pressure to deploy the gateway before its auth precondition is met.

## Deployment Impact

`AI_GATEWAY_URL` is no longer required by the Celery workers. The gateway stays undeployed until ADR-014's preconditions hold.

## Research Impact

None directly. Indirectly it is what allows a vector to exist at all, which every retrieval result in [ADR-023](023-retrieval-quality-evaluation.md) depends on.

## Related Requirements

FR-M4 — stable label only, per the frozen-SRS rule.

## Related Tasks

IR-58 (gateway preconditions, unchanged), IR-108, IR-156.
