# ADR-041: Every paid provider attempt is admitted against shared limits before it is sent

## Status

**Proposed** — 2026-10-12 (IR-545, under IR-551). **Awaiting approval by a named person.** The code ships **off** (`AI_PROVIDER_ADMISSION=off`). Switching it on does not approve any number: every limit is a required setting with no default, and **no value has been approved** (fixed-workflow pilot README §6). An agent wrote this record. It decides nothing.

## Context

IR-544 ([ADR-040](040-durable-queued-ask-iris-questions.md)) lets a question be answered by a Celery worker. Several web processes, several workers and possibly several replicas can now spend the same vendor accounts at the same time. The pilot README §6 gates enablement on three things nobody had built:

- shared quotas across workers, retries and fallbacks;
- per-stage and per-run values, enforced before paid work;
- queue sizing.

What existed did not cover these:

- **Per-run, in-process budgets.** `research/budget.py` (ADR-038 §5) counts a planner run's rounds and tool calls in memory. Two workers each enforce their own.
- **A rate limiter on one lane only.** `resilience/rate_limit.py` is a Redis token bucket per minute, used only by the evidence shadow lane. It knows nothing of US$, output tokens or attempts.
- **Hidden attempts.** The OpenAI SDK retried up to twice on its own, inside one IRIS call. A spending limit cannot count attempts it never sees.

IR-545 asks for the following:

- atomic shared admission across processes;
- every physical attempt counted, including retries and fallbacks;
- reservations made before sending, persisted across restarts;
- unknown usage charged conservatively;
- a bounded, fair queue within the original 30 s deadline;
- explicit busy or partial results;
- store failure denying paid work;
- one campaign ceiling (pilot README §7) with a protected reserve.

## Decision

1. **Postgres is the shared store** (`apps/ai/models/admission.py`, migration 0024).
   - `ProviderCampaign` holds one ceiling's running totals.
   - `ProviderReservation` holds one physical attempt.
   - Both are written through their own database alias, `admission` (the same database on another connection). A reservation therefore commits the moment it is made, even when its caller is inside a transaction. A queued run that embeds its answer while writing its Turn is one such caller.
   - **Why not Redis**, which `rate_limit.py` uses: Redis as deployed is not durable across restarts, and reservations must be. Postgres is already the system of record and is shared by every process.
2. **One lock serialises admission.** `admit()` takes the campaign row `FOR UPDATE`, checks every limit and inserts the reservation in one transaction. Every process meets the same row. Without the lock, the two-process test admits 4 attempts against a lane limit of 3.
3. **The unit is the physical attempt.**
   - **Chat models.** The admission decorator (`AdmittedLLMProvider`) sits directly on the chat adapter, *inside* `RetryingLLMProvider` and `FallbackLLMProvider`. The first try, the retry and each fallback model are therefore each admitted. Under enforcement the adapter turns the SDK's own retries off (`max_retries=0`) and asks streams to report their usage (`stream_options.include_usage`).
   - **Voyage.** Embedding and rerank are admitted in `voyage._post`, one request each.
   - **Jev.** Decisions are admitted in `OpenRouterDecisionsAdapter._post`.
   - **Fakes.** Local fakes are injected above the adapter and are never admitted, so they cost nothing.
4. **Worst case first.** Before sending, a reservation holds:
   - one attempt;
   - an upper bound on input tokens, as UTF-8 bytes plus a per-text overhead (no tokenizer emits more tokens than bytes);
   - the completion cap the request carries. Under enforcement every chat request carries `min(task cap, AI_ADMISSION_MAX_OUTPUT_TOKENS)`, tool calls included. A request with no cap is refused;
   - the cost of those tokens at the **highest price among every model that may answer**. OpenRouter may bill any model in a `models` list, so that list's worst price is the reservation;
   - active time equal to the attempt's timeout plus a grace period.

   A model with no price is refused.
5. **Settled to what the vendor reported.**
   - Anything not reported stays at its reservation, so unknown usage is never charged as zero.
   - An attempt that failed before its request was handed to the transport is released. The adapter calls `mark_sent()` just before sending.
   - A stream closed early (the reader left, or the deadline passed) is settled at whatever usage it reported.
6. **Leases, not timeouts, free a slot.**
   - An open reservation holds its lane and account slots until it is settled or its lease ends.
   - The lease is never shorter than the attempt's timeout, so a slot is not handed on while the request may still be talking to the vendor.
   - A stream renews its lease once half the grace period has passed since the last renewal, so at least one whole read timeout of lease always lies ahead of each delta. A refused renewal stops the stream (`AdmissionLost`).
   - **Lock order** is always the campaign row, then the reservation, for admitting, renewing and settling alike, so the three cannot deadlock.
   - A reservation whose lease ran out unsettled (its worker died) is marked abandoned at the next admission. It keeps its full reserved charge.
   - Leases are read against the database's clock, so replicas agree on the time.
7. **Limits** (`apps/ai/admission/limits.py`):
   - the campaign: attempts, input and output tokens, US$ and active minutes. A protected fraction is held back until `AI_ADMISSION_RESERVE_RELEASED` records the budget owner's release;
   - per-run caps, summed over the run's key. A queued question's key is `ask:<run id>`;
   - attempts in flight per lane (`AI_ADMISSION_LANE_CONCURRENCY`) and per vendor account (`AI_ADMISSION_ACCOUNT_CONCURRENCY`). The account is a digest of the key alone, so a credential shared by two lanes, tasks or endpoints shares one limit;
   - prices per model.

   A lane is the workload that caused the call: chat, research, ingestion, overview or shadow. When no workload names one, the provider's own default applies (embedding, reranking, or the Inference task's lane). Lanes travel in context variables, entered around each step of a streamed generator, because under ASGI each step may run in another thread.
8. **Fail closed.**
   - No limit has a default. Under `enforce`, an unset limit refuses every paid attempt (`not_configured`), and a malformed one stops Django at startup.
   - A database error while admitting refuses the attempt (`store_unavailable`). One while settling leaves the reservation charged in full.
   - `AI_DURABLE_ASK` without `AI_PROVIDER_ADMISSION=enforce` stops Django at startup.
9. **A refusal is explicit, never silent.**
   - `AdmissionDenied` is an `LLMUnavailable`, so every answer path shows its explicit unavailable state with the sources it holds (ADR-008). Screening marks candidates unassessed, never as non-matches.
   - It is also a `RateLimited`, so retrieval degrades to full text.
   - It is not retried, never fails over and never counts against a circuit.
   - Within a run, a denial that holds for every later attempt (campaign or run budget exhausted, nothing configured) is sticky: the run asks no more. A refusal tied to one lane, one model or one transient error is not sticky, so an unpriced rerank does not stop the answer that follows it.
   - A queued run whose refusals cost it its answer (it ends without one, or with one no model wrote) journals `capacity_limited` `{"status": "busy", "reasons": [...]}` before its terminal event. **No client renders this event yet.** The reader sees the answer's explicit unavailable state, and a full queue's `503` `detail` text.
10. **A bounded, fair queue.**
    - A submission is admitted only while fewer than `AI_ADMISSION_QUEUE_DEPTH` questions are unfinished, and fewer than `AI_ADMISSION_QUEUE_PER_USER` of them are the asker's. Otherwise the response is `503 {"status": "busy", "reason": ...}` with `Retry-After`, and nothing is queued.
    - The count and the insert are serialised by a transaction-scoped advisory lock.
    - Every vendor call a worker makes is bounded by the time left until the run's original `deadline_at`. A retry, a fallback or a redelivery never restarts it. Crossing the soft 10 s goal cancels nothing.

## Alternatives considered

- **Extend the Redis token bucket.** It is atomic across replicas, but it is not durable, has no notion of a reservation that is later settled, and would need Lua for multi-key checks. Rejected for the ledger. It stays as the shadow lane's per-minute limit.
- **Celery worker concurrency as the limit.** The ticket rules it out: it does not cover web processes, retries or fallbacks, and says nothing about money.
- **Admit per logical call (around the whole retry/fallback chain).** Simpler, but a retry and a fallback would then spend without a reservation of their own. Rejected by the ticket's "physical attempts".
- **Reserve on the default connection.** The reservation would stay invisible to other processes until the caller's transaction committed, and the campaign lock would be held across a vendor call. Rejected.

## Consequences

**Gains**
- A spending ceiling holds whatever the number of processes, and a test shows it does.
- Every retry and fallback is visible and charged.
- A dead worker's spend is charged and its slot comes back.
- A refusal is a status a reader can see.

**Costs**
- Each paid attempt takes two short transactions on the campaign row: one to reserve, one to settle. Admissions take turns on one row lock. This has not been measured under load.
- One more database connection per process (the `admission` alias).
- The byte-based input bound over-reserves by roughly 3–4× for English text. That limits headroom near a ceiling, not spend.
- Active time is summed per attempt, so three concurrent attempts accrue three times the wall clock. That is conservative.
- Under enforcement, tool calls carry a completion cap they did not carry before. The `route` task's 256-token cap now applies to its tool call too.
- A deployment must point every replica sharing a vendor key at the same database, or each has its own ceiling. Nothing can enforce this across databases.
- A process frozen past its lease (not crashed) could still be inside a non-streaming call when its slot is reused. The lease includes the call's own timeout plus a grace period, and the SDK's retries are off. The exposure is a stall longer than that grace.

**Not decided here**
- **Every number.** Run caps, lane and queue allocations, prices, the campaign ceiling and whether its reserve is released all need the budget owner's approval (pilot README §6). Sizing for 100 simultaneous submissions has not been done. "Three concurrent research calls" is an evaluation starting point only.
- Any paid run, load test or institutional transmission.

## MVP Impact

None while off. Enablement remains a recorded decision.

## SaaS Impact

The ledger is per database. A multi-tenant deployment would key campaigns per tenant.

## Security Impact

- The account digest is the only form of a key that is stored, and it is not reversible.
- Reason codes are public names. No vendor message or key reaches a reader.
- Refusing on store failure means a database outage cannot turn into unbounded spend.

## Deployment Impact

- New settings, all listed in `backend/.env.example`.
- Migration 0024.
- The `admission` alias needs nothing new: it is the same database.
- `manage.py provider_campaign` prints spend against both ceilings.

## Research Impact

The campaign ledger is the cost evidence pilot metric §6 asks for. It records attempts, tokens and US$ per lane and per run, and marks which charges are worst case because usage went unreported.

## Related Requirements

Pilot README §1 (deadline), §6 (gates), §7 (campaign).

## Related Tasks

IR-545; IR-544 (ADR-040); IR-551; IR-132 (`rate_limit.py`).
