# ADR-030: Ask IRIS chat bypasses the gateway; the streaming architecture built on that fact

## Status

Accepted — 2026-09-22.

**Narrows [ADR-017](017-asgi-deployment-for-gateway-streaming.md) and [ADR-024](024-embedding-path-bypasses-the-gateway.md). Does not supersede [ADR-014](014-ai-gateway-as-a-service.md)'s adoption of the gateway.** ADR-014's six preconditions, and the gateway's continued existence as an accepted-but-undeployed service, stand unchanged. This ADR corrects what ADR-017 assumed about where the chat call happens, and records the streaming decision that is being built on the corrected foundation.

## Context

ADR-017 justified moving Django to ASGI on the premise that the RAG answer endpoint would call the gateway over HTTP — its own Decision section describes "an `async def` Django view [that] uses `httpx.AsyncClient` to call the gateway's `/ask` route." ADR-024 later audited the embedding path and found the same shape of gap there: `AI_GATEWAY_URL` was never actually called, and Django computed vectors in-process instead. Nobody had gone back and checked whether the same was true of chat generation, because until IR-283 there was no working generation path to check.

There now is one, and it does not call the gateway.

**Audited in the tree, 2026-09-22:**

| Finding | Detail |
|---|---|
| The LLM seam is built in-process | `CompositionRoot.llm()` (`backend/apps/ai/composition.py:157-166`) calls `apps.ai.resilience.llm.build_resilient_llm()`, which wraps `apps/ai/providers/openai_compatible.py`'s `OpenAICompatibleAdapter` directly. No HTTP client, no gateway URL |
| `AI_GATEWAY_URL` is read nowhere on this path | `backend/apps/ai/tests/test_indexing_does_not_use_the_gateway.py` already asserts no module under `apps/ai/` reads the setting for indexing (ADR-024); the same is true of `composition.py`, `resilience/llm.py` and `providers/openai_compatible.py` — grepped directly, not inferred |
| The current answer view is synchronous | `apps/ai/views/chatbot.py`'s `ChatQueryView` is an ordinary DRF `APIView`, not `async def`. There is no `StreamingHttpResponse`, no SSE endpoint, and no `httpx.AsyncClient` anywhere in `apps/ai/` |
| The gateway's own `/ask` route is unexercised | Nothing in `apps/ai/` or `apps/documents/` constructs a request to it. It remains reachable only by calling the `ai-gateway` container directly |

This is the same pattern ADR-024 documented for embedding, just never written down for chat: `LLMProvider` is a port (ADR-012's design, per [ADR-028](028-no-tool-calling-in-the-answer-path.md)'s `generate(system, user) -> str`), and `CompositionRoot` satisfies it with an in-process adapter, the same way `embedder()` and `reranker()` do. The gateway was never plugged into the seam that was built to accept it.

**Why this went unnoticed as long as it did.** ADR-017 was written 2026-09-04, before IR-283 (chunk-level retrieval) or IR-284 (citations) existed — there was no answer path to observe yet, only the plan for one. `CompositionRoot` was introduced by IR-283 to wire the retrieval stack that already existed, and its `llm()` method was written against the port `apps/ai/providers/openai_compatible.py` already exposed, not against the gateway, because the gateway was never a dependency the retrieval work needed to reach. Nobody revisited ADR-017's assumption once the code existed to check it against.

**ADR-017's deployment decision is unaffected by this correction.** The four-worker starvation risk ADR-017 exists to close does not depend on *where* the blocking call goes — an in-process `httpx` (or vendor-SDK) call to an LLM provider blocks a gunicorn worker exactly as a blocking call to the gateway would have. ASGI plus a genuinely `async def` view is still the only way to keep that worker free while a long-lived generation call is in flight; only the callee at the end of that call changes, from "the gateway's `/ask` route" to "the vendor directly, via the same in-process adapter `CompositionRoot.llm()` already builds."

## Decision

**Record the corrected foundation, and build the streaming architecture on it.**

1. **Ask IRIS chat generation calls the vendor in-process, through `LLMProvider`, and always has.** The gateway is not on this path today and this ADR does not put it there. `CompositionRoot.llm()` is the seam; streaming work extends what it builds, it does not route around it to the gateway.

2. **ADR-017's ASGI deployment decision is reaffirmed as already implemented and unaffected by this correction.** `backend/Dockerfile`'s production `CMD` already runs `gunicorn` with `uvicorn.workers.UvicornWorker` against `config.asgi:application` (ADR-017 §Decision), and that remains the correct deployment shape for the reason ADR-017 gives — worker-starvation avoidance during a long-lived generation call — regardless of which process ultimately makes that call. Nothing here reopens ADR-017's Decision.

3. **IR-108's original spec text, which described the async view calling out to the gateway, is superseded by this ADR rather than edited.** Per this project's ADR discipline (`docs/adr/README.md` §Writing a new ADR: "Never edit an accepted ADR's Decision"), the same rule extends to spec/ticket text once it is stale: IR-108's description is left as written, historically, and this ADR is the record that its gateway-call premise did not hold once the path was actually built.

4. **The streaming architecture this cluster (IR-323) implements:**
   - A new SSE endpoint (`StreamingHttpResponse` over Server-Sent Events, per ADR-017's already-accepted wire-format choice), replacing `ChatQueryView`'s buffered response for the answer path.
   - An event-yielding answer service: the retrieval-through-generation pipeline is restructured to yield discrete events (retrieval complete, reasoning/token deltas, citation resolved, answer complete) rather than returning one assembled `ChatResponse`, so the endpoint can relay them as they occur instead of waiting for the whole pipeline to finish.
   - **The sync-to-async boundary sits at retrieval, not at generation.** Retrieval (`TwoStageRetriever`, reranking, the disclosure gate — all synchronous ORM-bound code, per ADR-013's stack) runs as it does today, off the event loop, exactly as ADR-017 §Decision requires for "sync ORM calls inside an `async def` view." The `async def` view awaits that synchronous work via Django's standard sync-to-async bridging, then streams the LLM provider's token-by-token output as it is produced. This keeps ADR-017's scope discipline: one new async path, not a rewrite of the retrieval stack into async code.

5. **This does not reopen [ADR-028](028-no-tool-calling-in-the-answer-path.md)'s rejection of tool-calling.** Streaming changes *how* the assembled prompt's answer is delivered to the caller — token by token instead of buffered — not *what* decides what to retrieve or whether the model can call anything. `LLMProvider` stays `generate(system, user) -> str` in shape; a streaming variant of that same narrow port yields the same text incrementally. The caller still decides what reaches the prompt, per ADR-028 §Decision. Nothing about event-shaping the response surface implies exposing retrieval as tools.

## Alternatives Considered

**Route chat generation through the gateway now, to match what ADR-017 assumed.** Rejected, for the same reason ADR-024 rejected repairing the embedding hop: `LLMProvider` already exists as a working, tested, in-process seam (`apps/ai/providers/openai_compatible.py`, exercised by `apps/ai/tests/test_ask_http.py` via `composition_root()` overriding), and the gateway's ADR-014 preconditions (auth, CORS removal, no public port) are still unmet. Adding a live dependency on an undeployable service to satisfy a premise that turned out to be wrong is not a fix.

**Treat this as silently correcting ADR-017 in place.** Rejected — this project's rule is to record a correction as a new decision, not edit an accepted one (`docs/adr/README.md` §Writing a new ADR). ADR-017's Decision (the ASGI deployment change) was right regardless; only its Context's description of the callee was wrong, and that is what this ADR narrows.

**Defer recording this until the gateway's preconditions are met and the gap is closed instead of documented.** Rejected. The preconditions are unmet with no committed date, chat generation already works today without the gateway, and leaving the discrepancy unrecorded is exactly the condition that let ADR-024's three independent embedding-path failures go unnoticed for as long as they did.

## Decision Rationale

The gateway's justification was always the async/streaming shape of LLM calls (ADR-014 §Decision Rationale), not a *language or process boundary* requirement — nothing in ADR-014 or ADR-017 required the call to leave the Django process, only that it not block a worker. IR-283 built the working seam (`LLMProvider` via `CompositionRoot`) against that same shape, in-process, because the retrieval work had no reason to introduce a second service dependency for a port that already existed and already had a real adapter. The streaming decision in this ADR keeps that seam and adds the one piece ADR-017 actually mandates — an async view and non-blocking I/O around the long-lived call — without requiring the gateway to be deployable first.

## Consequences

- CLAUDE.md's Ask IRIS (chat) row already states composition is in-process (`composition.py`) and predates the specific gateway-bypass framing; this ADR is that framing's written record.
- The gateway (`ai-gateway`, `ai/`) remains an accepted-but-undeployed service per ADR-014, unaffected — no code there changes as a result of this ADR.
- `AI_GATEWAY_URL` remains defined in settings for ADR-014's still-live streaming-chat mandate on the gateway's own side (per ADR-024's Consequences), read by nothing in the Django chat path — the same statement ADR-024 already makes for embedding, now also true for generation.
- A future regression test analogous to `test_indexing_does_not_use_the_gateway.py`, scoped to `apps/ai/composition.py` and `apps/ai/resilience/`, is left to IR-323's implementation subtasks rather than specified here — this ADR records the fact and the architecture decision, not the test.

## Revisit when

ADR-014's six preconditions are all met and a deliberate decision is made to route chat generation through the deployed gateway instead of in-process — at that point this ADR would be superseded, not amended, per this project's ADR discipline.

## MVP Impact

None. This corrects the record and sets direction for IR-323's streaming subtasks; it changes no shipped behavior by itself.

## SaaS Impact

None beyond ADR-024's — one fewer live dependency on the gateway per tenant, on the chat path as well as the embedding path.

## Security Impact

None new. The `system`/`user` prompt separation ADR-028 relies on to resist injection from uploaded documents is unaffected — this ADR changes transport and delivery shape, not what is placed in which argument. Streaming does not change `visible_to(user)`-filtered retrieval, which still runs entirely inside Django before any text reaches the LLM provider.

## Deployment Impact

None beyond ADR-017's, already implemented. No new service, no new container, no change to what must be deployed for the gateway to go live under ADR-014.

## Research Impact

Directly relevant. RAG is thesis-critical as of 2026-09-04 (CLAUDE.md §Repository, ADR-013 §Research Impact amended), and the streaming architecture this ADR authorizes is what IR-323's event-shaped answer path — including the reasoning-token foundation and inline citation chips — is built on. Keeping generation on the already-tested, in-process `LLMProvider` seam rather than introducing a new gateway dependency mid-cluster keeps ADR-023's retrieval-quality comparisons unaffected by an unrelated infrastructure change.

## Related Requirements

NFR-P3 (restated by ADR-011 as time-to-first-token ≤ 3 s, complete ≤ 15 s p95) · FR-M4-01 — stable labels only, per the frozen-SRS rule.

## Related Tasks

IR-323 (parent — event-shaped Ask IRIS answer path) · IR-324 (this ADR) · IR-108 (superseded spec text) · IR-283, IR-284 (the retrieval and citation stack this streaming work is built on) · IR-321 (the resilient `LLMProvider` this ADR's seam already wraps).
