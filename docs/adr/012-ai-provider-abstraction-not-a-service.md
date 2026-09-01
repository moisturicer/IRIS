# ADR-012: The AI provider abstraction lives in Django, not in a separate service

## Status

Accepted — 2026-09-02

**Reaffirms [ADR-010](010-deployment-topology.md).** It does not supersede it. ADR-010 remains accepted and unedited.

## Context

[ADR-010](010-deployment-topology.md) settled a five-service topology — `db`, `redis`, `backend`, `celery`, `frontend` — and removed `ai-gateway` on three grounds:

1. Its build context `./ai` did not exist.
2. It contradicts the SRS service table (§393-405), which lists nginx, web, celery-worker, celery-worker-rag, celery-beat, docling, db and redis — **and no FastAPI gateway**.
3. The single "internal AI gateway" phrase at SRS:1380 denotes a **code-level abstraction** for reaching the external AI service, not a container. The Compose file had materialised a code abstraction into a service.

Commit `7f73e97 feat: add AI service` then added `ai/` — a FastAPI application with `POST /api/v1/ai/ask` and `POST /api/v1/ai/embed`, `LLMProvider` and `EmbeddingProvider` abstract base classes, OpenAI and local adapters, and pydantic settings.

**One of the three objections changed. Two did not.** The SRS service table is unchanged, and SRS:1380 still says what it said.

### What the new service actually is, audited in the tree

| Finding | Detail |
|---|---|
| **It cannot start** | `ai/api/chat.py` imports `ai.services.chat_service` and `ai.services.embedding_service`. `ai/services/` contains **only a one-line comment file** — neither module exists. `main.py` includes that router at module scope, so the container fails at import |
| **No authentication** | The only `Depends` are provider injection. Both endpoints are open to anything that can reach the container, which holds the OpenAI API key |
| **Permissive CORS** | `allow_credentials=True` with `allow_methods=["*"]`, origins parsed by string-splitting an env var. The same defect class as `CORS_ALLOW_ALL_ORIGINS` in Django (IR-61) |
| **A second data path** | `asyncpg` in `ai/requirements.txt` implies direct database access, bypassing Django's ORM and its permission layer entirely |
| **Retrieval is destined here** | `sources=[]` carries the comment *"To be populated by vector search later"* |
| **Compose still broken** | No `ai/.env` or `ai/.env.example`, so `docker compose config` fails on a missing env file |

## Decision

**The AI provider abstraction is adopted. The separate service is not.**

1. `ai-gateway` is **not** deployed as a container. The five-service topology of ADR-010 stands.
2. The **ports-and-adapters design is kept** and ported into Django as `apps/ai/providers/` — the `LLMProvider` / `EmbeddingProvider` interfaces with OpenAI and local adapters, which is precisely the provider protocol [ADR-006](006-minimum-rag-pipeline.md) already specifies. The adapters port over nearly unchanged.
3. Retrieval, generation and embedding run inside Django, behind the existing authentication and the single `visible_to(user)` predicate.
4. `IR-58` remains correct: remove the `ai-gateway` service from both Compose files.
5. `ai/` is **not deleted by this decision**. Its disposition belongs to IR-58, under review.

## Alternatives Considered

**Adopt the gateway and supersede ADR-010.** Rejected, and this was the serious alternative.

The argument for it is real: FastAPI gives genuinely async LLM calls where Django is synchronous, the ports-and-adapters structure is clean, and a separate codebase gives whoever owns the AI work an isolated place to work — which matters on a four-person team.

It was rejected because the code as written **strengthens ADR-010's objection rather than answering it**. ADR-006 and ADR-010 warned that a gateway would duplicate authentication and visibility filtering, creating a second place for the [ADR-009](009-authorization-model.md) defects to recur. What was built has *no authentication at all*, permissive CORS, and a database driver implying a second path to the same data — with retrieval, the part that most requires visibility filtering, explicitly planned to land there.

Adopting it would mean building authentication, visibility filtering and CORS correctly a second time, in a second language runtime, having just spent twelve dev-days fixing exactly those defects the first time. Under [ADR-005](005-instance-per-tenant.md)'s instance-per-tenant model it is also a sixth container that **every institution** runs, secures, backs up and pays for — against a plan already at 102% of capacity.

The async benefit is marginal at pilot scale. Celery already provides asynchrony for the work that needs it, and the RAG budget is three dev-days total.

**Adopt the gateway but restrict it to the internal Docker network.** Rejected. "Unauthenticated but only reachable internally" is one misconfigured port publish away from being unauthenticated and public, and it still requires visibility filtering to be reimplemented before retrieval can be added.

**Keep both — Django for authenticated paths, the gateway for internal ones.** Rejected as the worst option. Two implementations of the same capability drift, and the question "which one is authoritative?" has no good answer.

**Delete `ai/` immediately.** Rejected as out of scope here. The code has value and deleting it is a separate reviewed change (IR-58).

## Decision Rationale

The deciding fact is not that a gateway is architecturally wrong in general — for a larger system it would be reasonable. It is that **this gateway reproduces, in a new runtime, the precise class of defect the project has just spent its largest block of remediation effort removing**, and it does so at a recurring per-tenant cost, in a semester with no capacity headroom.

The abstraction is the valuable part, and the abstraction does not need a container. `LLMProvider` and `EmbeddingProvider` as Python protocols give provider swappability — the one real benefit — for roughly twenty lines inside Django, where authentication and the visibility predicate already exist and are being tested (IR-84).

Keeping the design and dropping the deployment takes the benefit and leaves the cost.

## Consequences

**Positive.** Five services, not six. One authentication implementation, one visibility predicate, one place for the ADR-009 fixes to hold. No per-tenant cost increase. Compose becomes buildable once IR-58 lands. The provider abstraction is preserved rather than discarded.

**Negative.** LLM calls remain synchronous within a Django request unless dispatched to Celery. The author of `ai/` has work redirected rather than adopted as-is — the design survives, the deployment does not. If the AI work is owned by one person, they own `backend/apps/ai/` instead of a separate repository-within-a-repository.

**Risk.** The `ai/` directory remains in the tree until IR-58, so a reader may still assume it is live. Mitigated by `CLAUDE.md` recording its status explicitly.

## Revisit when

Any of the following, and this ADR should be superseded rather than ignored:

- Measured load shows synchronous LLM calls inside Django are a real bottleneck, and Celery dispatch does not resolve it.
- The AI capability grows beyond what ADR-006 scopes — full-text chunking, reranking, agents, multiple providers — enough that isolation genuinely pays.
- The SRS is amended to specify a gateway service, which would remove objection 2.
- A second consumer of the AI capability appears that is not the Django application.

Note that a service **with authentication, visibility filtering, and a working boot** would be a materially different proposal from the one assessed here, and deserves a fresh decision rather than this one.

## MVP Impact

None to the schedule. The decision costs 0.25 dev-days to record; porting the abstraction is inside IR-89's existing three-day RAG timebox.

## Security Impact

Decisive. Avoids a second unauthenticated surface holding a provider API key, and avoids duplicating the visibility predicate that IR-60 and IR-84 exist to get right once.

## SaaS Impact

One fewer container per institution. Under instance-per-tenant, per-service cost is paid again for every customer, so keeping the stack at five services directly protects the model's main weakness.

## Related Requirements

FR-M4-01 · NFR-S3 · NFR-S4 · SRS §393-405, SRS:1380.

## Related Tasks

**IR-106** (this decision) · **IR-58** (remove `ai-gateway` from Compose) · **IR-89** (RAG pipeline, which absorbs the ported provider abstraction).
