# ADR-008: Graceful degradation to PostgreSQL FTS

## Status

Accepted — 2026-09-01

## Context

The RAG pipeline depends on external services: an embedding provider and an LLM provider. It also depends on internal infrastructure: Celery, Redis, and pgvector retrieval. Any of these can be unavailable — provider outage, rate limiting, exhausted API credit, network failure, or a wedged worker.

The customer pilot runs in Weeks 11–12 and the technical defence in Weeks 16–17. An AI failure during either would, with the current design, present as a broken system rather than a degraded one.

There is one asset here: **PostgreSQL full-text search already works.** `records/signals.py` populates `Record.search_vector` on save, with a GIN index and weighted title/abstract vectors. It is the only phase of the documented eleven-phase pipeline that functions today, and it requires no external service.

## Decision

**AI failure degrades to PostgreSQL full-text search. It never takes down the core product.**

Behaviour by failure mode:

| Failure | Behaviour |
|---|---|
| Embedding provider unavailable | Search falls back to FTS. Banner: semantic search unavailable. Indexing queues for retry |
| LLM provider unavailable | Retrieval still returns records; the answer is replaced by an explicit "AI unavailable" state. **Never a fabricated answer** |
| Provider timeout | Bounded at ~30 s, then HTTP 503 with a clear message |
| pgvector retrieval fails | Fall back to FTS |
| Celery or Redis unavailable | Uploads still succeed; extraction and embedding queue. Record submission and the entire workflow are unaffected |
| Rate limit or credit exhausted | Same as provider unavailable, with a distinct operator-facing log |

**No second AI implementation is built.** There is no local fallback model, no secondary provider, no cached-answer service. FTS is the fallback.

The degraded path is **demonstrated deliberately** as a resilience test during system testing (`V-10`), not discovered in production.

The core workflow — submission, routing, clearance, resubmission, publication, audit — has **no AI dependency at all** and must continue to function with every AI component down.

## Alternatives Considered

**A secondary LLM provider for failover.** Rejected. A second provider means a second API key, a second data-governance question, a second cost line and a second integration to test — for a supporting capability, against a 3-day RAG budget.

**A local fallback model (Ollama or similar).** Rejected. Needs a GPU for usable latency; adds a service and several GB of weights. This is building a second AI system to insure the first.

**Cache previous answers and serve them on failure.** Rejected as misleading. Serving a stale answer to a different question is worse than saying the service is unavailable.

**Fail the whole request when AI is down.** Rejected. It couples a supporting capability to the core product and turns a provider outage into a system outage during the pilot.

**Do nothing and hope.** Rejected explicitly. This is the current behaviour and it is a single point of failure on demonstration day.

## Decision Rationale

FTS is already implemented, requires no external dependency, and returns genuinely useful results for a corpus this size — users find records by keyword every day in every repository system. It is a legitimate degraded mode, not a placeholder.

It costs ~0.5 dev-days because the hard part already exists.

**It also serves as insurance against an unresolved external blocker.** If the data-governance question returns "no external transmission permitted," the system still has working search on day one, and the RAG capability becomes a documented Phase 2 item rather than a hole in the product.

Demonstrating a designed degradation is a stronger defence answer than an AI feature that happened to work on the day. It evidences NFR-R2 thinking without a separate reliability workstream.

## Consequences

**Positive.** No single point of failure on demo day. The core workflow — which is the thesis — is insulated from every external dependency. Insurance against the data-governance blocker.

**Negative.** Users in the degraded state get keyword rather than semantic results, and the UI must make that state visible without alarming them.

**Risk.** Silent degradation. If the banner is missing or unclear, users may believe semantic search is working and draw conclusions from keyword results — which would contaminate usability evaluation data. The visible-state requirement is part of the acceptance criteria, not a nicety.

## MVP Impact

**MVP Required, P1.** ~0.5 dev-days.

## SaaS Impact

Per-instance under ADR-005: one institution's provider outage or exhausted quota cannot affect another's.

## Security Impact

Positive. Bounded timeouts prevent request pile-up from a hanging provider. Explicit failure prevents the far worse outcome of a fabricated answer being presented as grounded — which in a research-integrity system is a correctness *and* reputational risk.

## Deployment Impact

None. Uses infrastructure already deployed.

## Research Impact

The degradation test is a named system-test scenario (`V-10`) and evidence of reliability engineering for the technical defence.

## Related Requirements

FR-M3-02 (FTS indexing) · FR-M4-01 (RAG chatbot) · NFR-R2 (failure recovery) · NFR-P3 (see ADR-011).

## Related Tasks

`R-05` (implementation), `V-10` (validation). See [`06-rag.md`](../architecture-tasks/06-rag.md).
