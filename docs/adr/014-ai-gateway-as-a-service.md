# ADR-014: The AI gateway is adopted as a deployed service

## Status

Accepted — 2026-09-02

**Supersedes [ADR-012](012-ai-provider-abstraction-not-a-service.md).** **Amends [ADR-010](010-deployment-topology.md)** — the topology becomes six services, not five. ADR-010 is otherwise unchanged and remains accepted.

## Context

ADR-012 adopted the ports-and-adapters design from `ai/` and rejected the container. Its reasoning was not about the design, which it called clean and portable — it was about what the code did and did not do:

| ADR-012's objection | Status today |
|---|---|
| It cannot start — `ai/api/chat.py` imports `ai.services.chat_service`, which does not exist | **Still true.** `ai/services/` holds only `__init__.py` |
| No authentication — both endpoints open to anything that reaches the container | **Still true** |
| Permissive CORS — `allow_credentials=True` with `allow_methods=["*"]` | **Still true**, `ai/main.py:14-20` |
| `asyncpg` implies direct database access bypassing Django's permission layer | **Still true** as an intent; no query is written yet |
| Compose declares it with no `ai/.env` or `.env.example` | **Still true** |

**None of those objections has been answered by code.** What has changed is the decision about whether they are worth answering.

ADR-012 reasoned that answering them means building authentication, visibility filtering and CORS correctly a second time, in a second runtime, immediately after twelve dev-days spent fixing exactly those defects in Django. That argument is sound and this ADR does not claim otherwise. It is overridden on the grounds below, and the objections are converted into **preconditions** rather than dismissed.

`feat/rag-service` has since restructured `ai/` into a clean hexagonal layout: `domain/ports.py`, `infrastructure/{openai,local}_adapter.py`, `infrastructure/dependencies.py`, `api/`.

## Decision

**The gateway is adopted as a sixth service.** `ai-gateway` stays in both Compose files.

It is adopted **subject to five preconditions**, each of which must be met before it handles any request carrying record content. Until all five are met the service is not deployed and `apps/ai` calls the provider ports in-process.

1. **Service-to-service authentication.** A shared secret in a header, verified by FastAPI middleware on every route, sourced from the environment. Django is the only client. A request without it is rejected before routing.
2. **No public exposure.** The gateway binds only to the Compose network. No published port, no reverse-proxy route, no path through nginx. Reachable from `backend` and `celery` only.
3. **CORS removed entirely.** The gateway serves no browser. `CORSMiddleware` is deleted rather than narrowed — a middleware that exists can be misconfigured; one that does not, cannot.
4. **No direct database access for retrieval.** `asyncpg` is removed from `ai/requirements.txt`. Django performs retrieval, applies `visible_to(user)`, and passes the candidate chunks to the gateway as request payload. **The gateway never decides what a user may see.** This is the precondition that answers ADR-012's central objection: there is no second permission layer because there is no second data path.
5. **It boots.** `ai/services/chat_service.py` and `embedding_service.py` exist, `ai/.env.example` is committed, and `docker compose config` validates.

**The provider ports stay in `ai/domain/ports.py`** and are the single definition. Django reaches them over HTTP.

## Alternatives Considered

**Keep ADR-012 — port the adapters into `apps/ai/providers/`.** Rejected, and it remains the fallback if the preconditions prove too expensive. Its argument is the strongest one against this ADR: it costs nothing to implement, adds no service, and cannot leak because there is no second process. What it gives up is below.

**Adopt the gateway as written, without preconditions.** Rejected outright. An unauthenticated service holding the provider API key, with permissive CORS and a database driver, is not a deployment decision — it is the defect class [ADR-009](009-authorization-model.md) exists to close, reintroduced in a second language. Precondition 4 is not negotiable.

**Let the gateway own retrieval, with its own visibility filter.** Rejected — this is precisely what ADR-012 warned against, and it is the one shape of this service that would justify ADR-012's rejection standing. Two implementations of `visible_to(user)` in two runtimes will drift, and the drift is a confidentiality breach rather than a bug.

**Run the gateway only in development.** Rejected. A component exercised in one environment and not the other is untested where it matters.

## Decision Rationale

The case for the gateway is not that Django cannot do this work. It is that **LLM calls are I/O-bound, long-lived and concurrent, and Django's synchronous request path is the wrong shape for them.** Celery covers asynchrony for indexing, which is fire-and-forget; it does not cover a user waiting on a streamed answer. Streaming, in particular, is expressible in FastAPI and awkward in synchronous Django — and [ADR-013](013-chunk-level-rag-pipeline.md)'s pipeline is long enough per query that streaming stops being cosmetic.

The second reason is ownership. On a four-person team the AI work has one owner, and a separate codebase with its own dependency set is a place that owner can work without contending with the Django tree on every change.

Precondition 4 is what makes this defensible. With retrieval in Django and the gateway receiving already-filtered chunks, the gateway is a **stateless transformation over text it was handed**. It has no database, no user model, no notion of visibility, and nothing to get wrong about permissions. ADR-012's objection was to a gateway that owned retrieval. This is not that service.

## Consequences

**Positive.** Async and streaming become natural. The AI codebase is separately ownable, separately testable, separately deployable. The provider ports have one definition.

**Negative.** A sixth container every tenant runs, secures, backs up and pays for, against a plan already at capacity. One more service to keep booting in CI. A shared secret to rotate. The five preconditions are real work that buys no user-visible feature.

**Risk.** The preconditions are the whole safety argument, and preconditions are exactly what gets skipped under schedule pressure. **CI must fail if the gateway starts without its auth secret set** — that is the enforcement, not this document.

## Revisit when

The preconditions are not met by the end of the [ADR-013](013-chunk-level-rag-pipeline.md) timebox, or a sixth service proves unaffordable per tenant. Reverting is cheap by construction: the ports move into `apps/ai/providers/` and the HTTP hop disappears.

## MVP Impact

**MVP Required, P1.** ~2 dev-days for the preconditions, inside the ADR-013 budget.

## SaaS Impact

**Negative and worth stating plainly.** Under [ADR-005](005-instance-per-tenant.md) every institution runs its own stack, so this is a sixth container per tenant. It raises the per-tenant memory floor and the onboarding surface.

## Security Impact

**The preconditions are the security impact.** Met, the gateway holds no data, makes no authorization decision, and is unreachable from outside the Compose network. Unmet, it is an unauthenticated service holding the provider API key. There is no middle state, and no partial deployment.

The SRS service table (§393-405) still lists no FastAPI gateway. **This ADR creates a contradiction with the SRS and it is recorded, not reconciled** — an SRS amendment is required, alongside the Docling amendment already outstanding.

## Deployment Impact

Six services: `db`, `redis`, `backend`, `celery`, `frontend`, `ai-gateway`. ADR-010's other reductions stand — `docling`, the split Celery queues and `celery-beat` remain removed. Memory rises by roughly 300 MB over ADR-010's ~2 GB.

## Research Impact

None. The gateway does not touch the workflow the thesis evaluates.

## Related Requirements

FR-M4-01 · NFR-S3 (secure configuration) · NFR-S4 (server-side authorization) · SRS §393-405, §1380.

## Related Tasks

`IR-58` (revised — the service stays, the topology is corrected) · `R-01`…`R-06`.
