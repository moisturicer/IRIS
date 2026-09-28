# ADR-008: Graceful degradation to PostgreSQL FTS

## Status

Accepted — 2026-09-01 · **amended 2026-09-28 (IR-376, IR-391)**

**Amended — 2026-09-28 (IR-376): model fallback inside one vendor account is
permitted; cross-vendor failover remains rejected.** See §Amendment — IR-376
below. This narrows one sentence of the Decision — *"no secondary provider"* —
and nothing else. Every other rule here, including the degraded-mode behaviour
table and *"never a fabricated answer"*, is untouched.

**Amended — 2026-09-28 (IR-391): full-text search now has two jobs.** It
remains the outage fallback this ADR chose, and it additionally runs on the
normal path as a retrieval signal. See §Amendment — IR-391 below and
[ADR-033](033-hybrid-retrieval-and-passage-selection.md). Nothing in the
degraded-mode table changes.

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

**No second AI implementation is built.** There is no local fallback model, no secondary provider, no cached-answer service. FTS is the fallback. *(Amended 2026-09-28 — "no secondary provider" now means no secondary **vendor**; a fallback model list inside the one configured account is permitted. See §Amendment.)*

The degraded path is **demonstrated deliberately** as a resilience test during system testing (`V-10`), not discovered in production.

The core workflow — submission, routing, clearance, resubmission, publication, audit — has **no AI dependency at all** and must continue to function with every AI component down.

## Amendment — 2026-09-28 (IR-376): model fallback within one vendor, not across vendors

**What this supersedes.** One clause of the Decision: *"no secondary provider."*
Read literally it also forbade trying a second **model** on the same account,
which was never the risk the clause was written about. The amended rule:

> **A fallback list of models inside one vendor account is permitted. Failover
> to a second vendor is not.**

**Why the distinction holds.** Everything this ADR rejected a secondary
provider *for* is about the account, not the model string: a second API key, a
second data-governance question (a second company receiving IRIS text), a
second cost line, a second integration to test. Naming a second model on the
account already configured adds none of them. It is one more value in an
existing `.env`, over the same wire protocol, to the same company under the
same terms, on the same bill — and it covers the failure that is actually
common on a free or shared lane: one model being rate-limited, deprecated or
capacity-starved while the account itself is fine.

Cross-vendor failover stays rejected for exactly the original reasons, which
this amendment does not weaken. Note that **two vendors configured for two
different Inference tasks is not failover** — see
[ADR-021](021-openai-compatible-inference-provider.md) §Amendment
(2026-09-28), which makes the vendor a per-task choice. Each task has one
vendor and no vendor stands in for another.

**Bounds.**

* The fallback list is within **one** account: same `base_url`, same
  `api_key`, a different `model`.
* When every model on the list fails, the answer degrades per the table above —
  an explicit unavailable state, never a fabricated answer. The list changes
  how often degradation is reached; it does not change what degradation is.
* This permits nothing about *which* vendors are sanctioned. ADR-021 decides
  that.

**What this closes.** IR-321 (*Wire the resilience decorators around
`LLMProvider`, and add a model fallback list*) built a cross-vendor
`FallbackLLMProvider` and recorded the contradiction openly in
`apps/ai/resilience/llm.py`'s module docstring and in `apps/ai/composition.py`'s,
rather than reconciling it quietly. This amendment resolved the docs half: the
same-vendor model list is sanctioned, and the cross-vendor path was confirmed
as the part that goes. **IR-385 closed the code half on 2026-09-29** — the
`LLM_FALLBACK_*` settings and the provider they configured are deleted, and
setting one of them now refuses startup, so there is no second vendor left to
reach.

## Alternatives Considered

**A secondary LLM provider for failover.** Rejected — and **still rejected** after the 2026-09-28 amendment. A second provider means a second API key, a second data-governance question, a second cost line and a second integration to test — for a supporting capability, against a 3-day RAG budget.

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

## Amendment — 2026-09-28 (IR-391): full-text search has a second job

**What changes.** This ADR chose FTS as the **fallback** — the thing that runs
when the vendor is unreachable. That job is unchanged. What is added is a
second one: FTS also runs **on the normal path**, alongside vector search, as
one of two retrieval signals whose results are merged before reranking.

**Why.** Dense embeddings blur exactly the queries an institutional repository
receives most — an exact identifier, a surname, an instrument name, an
uncommon acronym. FTS answers those well, and in this codebase it already
searches chunks through the same `visible_to(user)` predicate as the vector
path. Reaching it only through a failure path meant the system's best tool for
a common query shape was available only when something was broken.

**What does not change.**

* The degraded-mode behaviour table above, unaltered. When the vendor is down,
  FTS is what remains — now as the sole signal rather than one of two.
* *Never a fabricated answer.* Hybrid retrieval widens the candidate set; it
  does not change what happens when generation is unavailable.
* Degraded mode has **no relevance cut-off**, because there is no reranker
  score to threshold — [ADR-033](033-hybrid-retrieval-and-passage-selection.md) §3.

**Design, reasoning and rejected alternatives:**
[ADR-033](033-hybrid-retrieval-and-passage-selection.md) (fusion by rank
position, the database-maintained chunk keyword index, the relevance cut-off,
passage selection, and the rule that every technique ships off until a harness
run shows it helps). Not restated here.

## MVP Impact

**MVP Required, P1.** ~0.5 dev-days.

## SaaS Impact

Per-instance under [ADR-005](005-instance-per-tenant.md): one institution's provider outage or exhausted quota cannot affect another's.

## Security Impact

Positive. Bounded timeouts prevent request pile-up from a hanging provider. Explicit failure prevents the far worse outcome of a fabricated answer being presented as grounded — which in a research-integrity system is a correctness *and* reputational risk.

## Deployment Impact

None. Uses infrastructure already deployed.

## Research Impact

The degradation test is a named system-test scenario (`V-10`) and evidence of reliability engineering for the technical defence.

## Related Requirements

FR-M3-02 (FTS indexing) · FR-M4-01 (RAG chatbot) · NFR-R2 (failure recovery) · NFR-P3 (see [ADR-011](011-evaluation-framework.md)).

## Related Tasks

`R-05` (implementation), `V-10` (validation). See [`06-rag.md`](../architecture-tasks/06-rag.md).
