# ADR-040: Ask IRIS questions can be answered by a worker and resumed

## Status

**Proposed** — 2026-10-12 (IR-544, under IR-551). **Awaiting approval by a named person.** The code ships **off** (`AI_DURABLE_ASK=False`), and switching it on is gated separately by the fixed-workflow pilot README §6 (queue sizing, shared quotas), which IR-545 addresses.

## Context

Today `/ask/stream/` answers inside the request. A reader whose connection drops loses the live view, and the server records whatever text had arrived as a `partial` Turn (IR-328). The fixed-workflow pilot (IR-551) needs a question that:

- shows actual queued and running progress;
- survives the reader disconnecting and reconnecting;
- ends in exactly one final result, within a deadline counted from the original submission (pilot README §1, a [Jira] figure: 30 s).

The ticket constrains the shape: reuse the existing event stream and parser, with no competing transport; dispatch to the existing Celery workers after commit; extend the run models deliberately; never duplicate a final Turn or resurrect a deleted conversation; re-check permissions on every read; and never expose raw tools, provider internals or private reasoning.

## Decision

1. **Three new tables** (`apps/ai/models/queued.py`, migration 0023):
   - `AskRun`: owner, Conversation, validated request, state, original `deadline_at`, a fencing pointer `current_attempt`, `last_sequence`, a **one-to-one** `turn` and an `end_reason` code.
   - `AskRunAttempt`: one per worker delivery, linked to the `ResearchRun` its planner wrote, if any.
   - `AskRunEvent`: the ordered public journal, unique on `(run, sequence)`.

   `ResearchRun` is **not** extended. It is the planner's private telemetry and exists only on the research lane, while any lane can be queued. The attempt links to it instead.
2. **Transport is unchanged.** With the switch on, a question asked over `POST /ask/stream/` inside a Conversation is queued, and the same response streams the run's journal. Every record gains an SSE `id:` (the sequence), which existing parsers already ignore. `GET /ask/runs/<uuid>/stream/?after=N` (or `Last-Event-ID`) replays from a cursor and then tails. New event names (`run_queued`, `run_started`, `run_failed`) are ignored by older clients. The terminal event of a run with a Turn is the existing `done`. One-off questions and `/ask/` JSON are not queued.
3. **Transactional dispatch.** The run and its `run_queued` event are created in one transaction. `answer_queued_question` is enqueued in `on_commit` on the `default` queue with `acks_late` and `reject_on_worker_lost`, so a lost worker's message is delivered again.
4. **Fencing.** Each delivery claims a new attempt and supersedes the previous one. Every journal write and the final Turn lock the run row and check that it still names that attempt. A terminal run refuses every claim.
5. **No resurrection.** Writing the final Turn locks the Conversation row first, then the run. Conversation deletion now locks the same row before collecting what cascades. A Turn is therefore either collected by the delete or never written.
6. **Deadline.** `deadline_at` is fixed at submission. A claim after it ends the run `expired`. A worker that passes it mid-answer stops, keeping a `partial` Turn if answer text had arrived (IR-328's rule). A run nobody finishes is expired by the next reader once `AI_DURABLE_ASK_STALE_SECONDS` have passed beyond the deadline. That fences out any attempt that later wakes.
7. **Public journal only.** Reasoning deltas are never journaled, and the replayed `done` carries no `reasoning`. Routing is journaled without the router's probabilities. Planner steps carry their code-owned tool names and counts, as IR-504 already sends.
8. **Permissions on every read.** Subscription and replay use `AskRun.objects.owned_by(user)`, so a foreign run is the same 404 as a missing one. Replayed citations are filtered to Records visible now. `done` is rebuilt from the stored Turn by `turn_for_reader` on every replay. A follower whose run disappears simply ends.
9. **Disconnect only unsubscribes.** The streaming response follows the run and does not own it. Following stops on disconnect and touches nothing.
10. **One run in flight per Conversation.** A question asked while an earlier run is unfinished gets a 409. Otherwise its worker would prepare it against a history missing the earlier Turn, and could write its Turn first.
11. **Celery time limits follow the deadline.** They are set per dispatch to deadline + stale grace, so a stalled vendor call releases its worker when a reader would expire the run anyway.

## Consequences

**Gains**
- A reader can leave and return and gets one final answer.
- Redelivery is safe by construction.
- The reopened transcript and the replayed `done` are the same re-resolved Turn.

**Costs**
- One row per streamed text delta in the journal.
- A follower polls the database (`AI_DURABLE_ASK_POLL_SECONDS`) instead of being pushed to.
- With the switch on, every Conversation question uses a worker.
- A superseded attempt that is still alive keeps spending until its next write is refused.
- No per-user fairness, queue bound or shared spend limit existed here. IR-545 adds them ([ADR-041](041-shared-provider-admission.md), Proposed), and switching this on now requires `AI_PROVIDER_ADMISSION=enforce`.
- §5's lock ordering holds for the Conversation delete endpoint only. Deleting a Record or a user cascades to Conversations without taking the lock. If that coincides with a run's final write, the cascade's commit fails on the orphaned Turn and can be retried. It is never a resurrection.
- Each follower holds a request thread and a database connection while it polls, and notices a departed reader only on its next write (at most `HEARTBEAT_SECONDS`).

**Not decided here**
- Whether `Turn.reasoning` keeps being written. IR-381 stands until a recorded policy changes it, and there is no bulk deletion of historical reasoning.
- Queue sizing and enablement (pilot README §6).
- Real-provider throughput. Only deterministic fakes have exercised this.
