# ADR-017: ASGI deployment so Django can actually use the gateway asynchronously

## Status

Accepted — 2026-09-04.

**Reaffirms [ADR-014](014-ai-gateway-as-a-service.md). Does not supersede it.** Completes it: ADR-014 adopted the gateway on the strength of an async/streaming argument that Django's current deployment cannot actually deliver. This ADR closes that gap rather than reopening the gateway-or-not question.

## Context

A reasonable challenge was raised against ADR-014's premise: isn't Django synchronous anyway, so what does a separate async FastAPI service actually buy? Checked against the working tree, both halves of that challenge are more concrete than the abstract debate suggested:

**The speed argument is real, and understated.** `backend/Dockerfile:60` runs `gunicorn config.wsgi:application --workers 4` — classic synchronous WSGI, four processes. `config/asgi.py` exists but nothing serves it: no `uvicorn`, no `daphne` in any requirements file. The Dockerfile carries its own unactioned marker: `# TODO: switch to uvicorn if async views are added`. DRF's `APIView` dispatch is synchronous by design. So "Django could just use async views" was not a live option without first doing this work — which is exactly what this ADR does.

**The resilience argument is also concrete, not hypothetical.** With only **four gunicorn workers**, a burst of slow or hanging AI calls handled synchronously in-process — or proxied to the gateway with a blocking `httpx.Client` call — can occupy all four simultaneously. At that point the entire application stops responding: record submission, clearance, everything, not only the AI feature. [ADR-008](008-ai-degradation-to-fts.md)'s degrade-to-FTS path protects against a *wrong or missing* AI answer; it does not protect against this, because the blocking call still holds the worker for its full duration (bounded at ADR-008's ~30 s, or gunicorn's own 120 s timeout) before anything degrades.

**ADR-014's own justification for the gateway already named this**, without the fix: *"LLM calls are I/O-bound, long-lived and concurrent, and Django's synchronous request path is the wrong shape for them... Streaming, in particular, is expressible in FastAPI and awkward in synchronous Django."* True — but a synchronous Django caller negates the benefit on its side of the wire. The gateway being async only helps the gateway's own concurrency unless Django's call *into* it is non-blocking too.

**[ADR-011](011-evaluation-framework.md) already flagged the requirement this blocks.** NFR-P3 demands a 3-second p95 for a complete chatbot response, which ADR-011 already called unachievable for a synchronous LLM round-trip, recommending it be restated as **time-to-first-token ≤ 3 s, complete response ≤ 15 s p95**. Time-to-first-token is a streaming metric. There is no way to satisfy it by making the LLM call faster — it requires the response to start reaching the client before it finishes generating, which a fully-buffered synchronous request/response cannot do regardless of which process the LLM call happens in.

`httpx>=0.27.0` is already a dependency, with the comment *"For proxying requests to ai-gateway"* — the team had already anticipated Django making outbound calls to the gateway; what was missing was doing so without blocking a worker.

## Decision

**Move Django's production deployment from `gunicorn`/WSGI to `gunicorn` managing `uvicorn.workers.UvicornWorker` processes — ASGI, not a rewrite.**

```
# backend/Dockerfile, production CMD
CMD ["gunicorn", "config.asgi:application", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
```

`uvicorn` is added to `backend/requirements/production.txt`. `config/asgi.py` already exists and needs no change to serve as the entry point; `config/wsgi.py` is retained for `manage.py` management commands, which still run synchronously.

**Every existing view is unaffected.** Django and DRF run ordinary synchronous views under ASGI by dispatching them to a thread pool automatically — this is a standard, supported Django capability, not a hack. `gunicorn -k uvicorn.workers.UvicornWorker` is a drop-in process-manager change, not an application rewrite.

**Exactly one new code path is written as genuinely async: the RAG answer endpoint.** An `async def` Django view uses `httpx.AsyncClient` to call the gateway's `/ask` route and relays its response to the browser as a stream (`StreamingHttpResponse` over Server-Sent Events, or an equivalent chunked-transfer response — the exact wire format is an implementation detail for whoever builds IR-108, not this ADR). While that request is in flight, the worker is not blocked waiting on the LLM — it is suspended on I/O, exactly as ADR-014 assumed Django could not do.

**No other endpoint is converted to `async def`.** This is deliberate scope discipline: the problem being solved is one specific I/O-bound, long-lived, streamed request, not "make Django async." Converting sync-only code (the ORM calls most views make) to `async def` for no reason adds risk — a sync ORM call inside an `async def` view blocks the event loop for every other concurrent request on that worker, which is worse than not converting it at all.

## Alternatives Considered

**Revert to ADR-012 (no gateway, in-process Django).** Rejected — this was the position argued for immediately before this ADR, and the four-worker starvation risk is the reason it doesn't hold. In-process AI calls draw from the same four-worker pool that serves the actual thesis workflow; the gateway's isolation is what keeps an AI slowdown from becoming a system outage. This ADR exists to make that isolation real, not to abandon it.

**Django Channels, with a Redis channel layer, for WebSocket streaming.** Rejected for this problem. Channels solves bidirectional, connection-oriented realtime (chat presence, live collaboration) and needs its own ASGI routing, its own channel layer (another Redis usage to reason about), and its own testing story. A one-directional token stream from gateway to browser doesn't need a persistent bidirectional channel — SSE over a plain ASGI streaming response does it with no new infrastructure. Revisit if a genuinely bidirectional realtime feature is proposed later (ADR-002's workflow board gaining live updates, say) — that would be a reason to adopt Channels on its own merits, not this one.

**Keep gunicorn/WSGI and accept a blocking proxy call to the gateway.** Rejected outright. This is the status quo the challenge exposed: it keeps the gateway's own async benefit from ever reaching the client, reintroduces the four-worker starvation risk this ADR exists to close, and cannot satisfy NFR-P3's restated form under any load.

**Ship without streaming; return the complete buffered answer.** Not rejected — kept as the timeboxed fallback, consistent with ADR-006 and ADR-013's own discipline of a pre-committed degradation rule. If the ASGI switch or the async endpoint is not done inside IR-108's budget, buffered responses are a working, honest product state; they simply do not satisfy NFR-P3 as restated, and that gap should be recorded rather than quietly accepted.

## Decision Rationale

`uvicorn` under `gunicorn` is a strict superset of the current deployment for every existing code path — nothing that works today stops working, because sync views keep running exactly as they do now, in a thread pool instead of a dedicated process. The risk surface of this change is therefore narrow: one new async view, one Dockerfile line, one new dependency.

This also finishes, rather than starts, a decision the team already made: the Dockerfile's own comment anticipated switching to uvicorn once async views existed. This ADR is that trigger.

Doing this is also what makes ADR-014's precondition 4 fully pay off. Precondition 4 makes the gateway "a stateless transformation over text it was handed" — cheap to call, safe to call, and *fast to call*, but only if the caller does not block on it. Without this ADR, Django would carry all of the gateway's deployment cost (a sixth container, four preconditions of security work) while capturing none of its speed benefit.

## Consequences

**Positive.** NFR-P3's restated form (time-to-first-token ≤ 3 s) becomes achievable. The four-worker starvation risk closes for the one request type most likely to trigger it. No new infrastructure service — Channels and a channel-layer Redis usage are avoided.

**Negative.** One more deployment detail that must be gotten right and kept right in CI (the worker class flag) — a plain revert to `gunicorn config.wsgi:application` by someone unfamiliar with this ADR would silently undo it without an error. A discipline requirement, not a technical one: reviewers must reject `async def` added to a view for no reason, per the Decision's scope-discipline point.

**Risk.** `uvicorn.workers.UvicornWorker` plus Django's sync-view thread pool is a well-trodden production pattern, but it is new to this team. It should be exercised under the same load test ADR-014 §8 (scale) already calls for, not assumed correct from a clean local run.

## Revisit when

A genuinely bidirectional realtime feature is proposed (revisit Channels then, on its own merits) · load testing shows the thread-pool dispatch for sync views under ASGI is itself a bottleneck at the concurrency levels in ADR-014's scale table · NFR-P3 is renegotiated away from a streaming metric entirely, removing the requirement this ADR exists to satisfy.

## MVP Impact

**Small, inside IR-108's existing budget.** The deployment change is a Dockerfile line and a dependency; the async endpoint is one view inside IR-108 (RAG query path), not new scope on top of it.

## SaaS Impact

None beyond ADR-014's. The deployment unit is unchanged (still one Compose stack per tenant, per ADR-005); this only changes what runs inside the `backend` container.

## Security Impact

None new. Still governed entirely by ADR-014's five preconditions — in particular precondition 4, which this ADR is what makes worth having. An async Django view calling the gateway is not a new permission surface: it is the same `visible_to(user)`-filtered retrieval Django already performs, followed by a stream relay of text the gateway returns.

## Deployment Impact

`backend/Dockerfile`: production `CMD` changes from `gunicorn config.wsgi:application` to `gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker`. `uvicorn` added to `backend/requirements/production.txt`. `config/asgi.py` unchanged. Dev (`manage.py runserver`) is unaffected — it already handles async views adequately for local development.

## Research Impact

None directly. Streaming latency is a product-quality property, not something ADR-004's controlled comparison measures.

## Related Requirements

NFR-P3 (restated by ADR-011 as time-to-first-token ≤ 3 s, complete ≤ 15 s p95) · FR-M4-01 (RAG chatbot) · NFR-S3, NFR-S4 (unchanged, carried from ADR-014).

## Related Tasks

`IR-108` (RAG query path — the async endpoint is built there, against this ADR) · `IR-58` (revised again by this ADR — see its corrected description) · a new task for the Dockerfile/requirements change, small enough to fold into `IR-108` rather than open separately.
