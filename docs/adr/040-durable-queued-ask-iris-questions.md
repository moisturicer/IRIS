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

## Amendment — IR-548: cancel, retry and conversation addresses (Proposed, 2026-10-14)

**Context.** A reader who opens a conversation directly, refreshes it or goes Back needs to land on the same run's
progress. They also need to stop a question they no longer want, and to ask one again when it ended without an
answer. Retry must not be confused with redelivery, which this ADR already makes safe and which must never reset a
budget.

**Decision.**

12. **Cancel is a terminal state.** `cancelled` joins the terminal states, carries no Turn and is journaled as
    `run_cancelled`. `POST /ask/runs/<uuid>/cancel/` takes the Conversation's lock and then the run's, the order a
    finishing attempt takes (§5), so a cancel and a final Turn cannot both commit. Whichever commits first wins. A
    cancel after completion is a 409 naming the state it ended in; a second cancel changes nothing.
13. **Nothing after a cancel is heard.** The fenced writes of §4 refuse the attempt, so no later event, partial Turn
    or whole Turn is written. The run's admission scope asks before every provider attempt whether its run was
    cancelled, and refuses with the sticky reason `run_cancelled`. A call already sent finishes and is charged; it is
    not interrupted.
14. **Retry is a new run, linked.** `POST /ask/runs/<uuid>/retry/` accepts a run that ended with no Turn
    (`failed`, `expired`, `cancelled`). A `partial` run is refused: it already wrote its fragment as a Turn, and a
    retry would put a second Turn for the same question in the transcript. It creates a new `AskRun` with `retry_of` (one-to-one) pointing at
    the original, the same validated request, a new deadline, its own per-run caps (`ask:<new id>`) and the same queue
    admission, one-run-per-Conversation rule (409) and busy refusal (503) as a new question. The original keeps its
    state. Asking to retry the same run again returns that retry (200) and never starts a third, even if that retry
    has itself failed; the reader then retries the retry, so each run has at most one successor and the chain is
    linear. The shared campaign is untouched: retry spends from it like any question. A Celery redelivery is still
    §4's new attempt on the same run, same deadline and same `ask:<id>` caps; it is never a retry.
15. **The conversation names its unfinished run.** The Conversation detail carries `latest_run` while no Turn shows for
    the latest run: still `queued`/`running`, or ended without an answer and not since answered by a later Turn. A
    client opening the conversation follows it from event 0, through the same re-authorising replay as §8.
16. **Addresses grant nothing.** The interface gives every conversation its own address. Opening it goes through the
    owner-scoped API, so a foreign, missing or deleted conversation is the same "not available".

**Consequences.**

- Gains: a reader can stop paying attention to, and stop spending on, a question they abandoned. A failed question
  can be asked again in one action. A link, a refresh and Back all reach the same progress.
- Costs: each provider admission inside a queued run adds one indexed read of the run's state. A cancel does not save
  the cost of a call already in flight. A retried question is a second run and, if it succeeds, its Turn is the only
  one; the original's journal stays for replay. Paper Chat does not re-attach to an unfinished run when its panel
  opens; the same conversation at its Ask IRIS address does.
- A research or listing run cancelled mid-plan stops at its next provider admission (refused) or its next journal
  write (fenced), whichever comes first; there is no separate job to cancel, because the planner runs inside the
  attempt.
- Not decided: whether a cancelled run should keep a partial Turn. It does not, because the reader's cancel says they
  do not want the answer.

**Reasoning policy, recorded (IR-548).** Unchanged: `Turn.reasoning` is still written as IR-381 decided, nothing
historical is deleted, the journal and every replayed `done` still carry no reasoning, and the transcript and export
projection are untouched. A cancelled or failed run writes no Turn, so it stores no reasoning at all. Changing any of
this needs its own recorded policy.
