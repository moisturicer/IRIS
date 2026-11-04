# Spec 2: Durable AskRun execution, recovery and shared spending

**Jira spec:** [IR-713](https://citiris.atlassian.net/browse/IR-713)

**Design accepted; implementation not started.** 31 October 2026. Authority: ADR-049. Parent epic: IR-146.

## Problem Statement

Readers should not lose a long investigation when a browser disconnects or a worker restarts. Moving agent execution must preserve bounded spending, fair queues, cancellation and exactly one delivered result rather than splitting these guarantees between runtimes.

## Solution

Let one AI-owned AskRun module coordinate durable progress, leases, queue admission, all paid attempts and atomic Turn delivery. Independently hosted workers recover verified work within the original remaining allowance; readers reconnect or explicitly Stop.

## User Stories

1. As a reader, I want research to continue when my browser disconnects, so that I do not lose a long investigation.
2. As a reader, I want to reconnect to the same AskRun, so that I see current progress rather than create duplicate work.
3. As a reader, I want Stop to prevent further work admissions, so that I can end an investigation I no longer need.
4. As a reader, I want cancel and final delivery to have one consistent outcome, so that the system does not both cancel and publish.
5. As a reader, I want repeated submissions with the same request identity to be idempotent, so that network retries do not duplicate paid research.
6. As a reader, I want a worker recover completed steps, so that a restart does not reread every paper.
7. As a reader, I want recovered evidence reauthorized, so that saved progress cannot restore revoked material.
8. As a reader, I want one final Turn committed, so that redelivery does not duplicate answers.
9. As a reader, I want concurrent questions to respect Conversation revision, so that the second paper does not silently change meaning.
10. As a reader, I want short requests to have protected capacity, so that deep research does not make ordinary interaction unusable.
11. As a researcher, I want deep to work eventually scheduled, so that short requests cannot starve my investigation.
12. As a reader, I want clear busy/deadline outcomes, so that I understand when work could not be admitted or completed.
13. As an operator, I want per-reader queues and concurrency bounded, so that one account cannot monopolize resources.
14. As an operator, I want ingestion to run separately, so that imports do not consume all research capacity.
15. As a budget owner, I want every physical provider attempt reserved before sending, so that retries cannot escape spending controls.
16. As a budget owner, I want unknown usage charged conservatively, so that unreported cost is not counted as free.
17. As an operator, I want deadlines and spending to survive restarts, so that recovery cannot renew an exhausted allowance.
18. As an operator, I want durable checkpoints independent of queue notifications, so that lost notifications do not lose committed work.
19. As an operator, I want uncertain remote outcomes reconciled, so that a timeout is not treated as proof no money was spent.
20. As a reader, I want account/Conversation deletion cancel associated to work, so that deleted research cannot later publish an answer.
21. As a release owner, I want measured queue-inclusive performance, so that worker-only timing does not hide waiting.

## Implementation Decisions

- The AI runtime is the sole writer of AskRun, Conversation/Turn commitment, progress/checkpoints and paid-attempt state after cutover. Preserve external reader behavior while transferring schema migration ownership once. Django does not commit a second competing terminal outcome.
- Use the existing durable-run concepts: original request/scope/revision, pinned versions, deadline, allowance, lease/fencing token, ordered progress, terminal state and idempotency identity. Successful finalization commits the Turn, citations, Conversation state revision and terminal journal atomically. A provider call happens outside transactions.
- PostgreSQL stores durable queued work/outbox state. Redis carries notifications, queue transport and progress wakeups, not authoritative completion. At-least-once work delivery is safe through idempotent claims and fencing. Recovery scans committed unclaimed/recoverable work when notifications are lost.
- Checkpoints persist completed model/tool exchange groups, plan/context revision, authorized source pointers, compaction identity and all consumed/reserved allowance. A replacement worker verifies current access and compatibility before reuse. If an in-flight step cannot be recovered, its reservation remains and any retry is separately charged.
- Queue admission applies bounded per-reader and per-Conversation work populations. A Conversation has at most one state-advancing run at a time; conflicting revisions return a recoverable conflict rather than applying stale ordinal choices. Protect ordinary interactive work, schedule deep work fairly, and isolate ingestion workers. No arbitrary production concurrency defaults.
- Every model, embedding, reranking, compaction, repair, retry and fallback attempt uses one shared reservation/settlement mechanism before transport. SDK-level hidden retries are disabled or accounted individually. Unknown usage/remote outcomes retain conservative reservations; never refund merely because a worker died.
- Missing deadline/token/attempt/cost/concurrency limits refuse paid work. Pin the approved deployment profile at admission, preserve original bounds through redelivery and reserve answer/one-repair capacity. Queue waiting is included in the declared deadline and latency.
- Disconnect is not cancellation. Stop atomically fences new admissions and final state advancement; remote work already sent may finish and be billed. A reader-requested Retry is an explicitly new AskRun with its own separately admitted allowance and retry link, not a redelivery budget reset.
- Conversation/account deletion first denies access and cancels/fences work, then performs idempotent content cleanup. Keep only deployment-policy-required non-content spending audit. Progress streams, polling and reconnect are owner-checked and exclude private evidence/tool traces.
- Expose queue time, execution time, provider/tool latency, retry/repeated-work counts, reserved/reported spend, memory and database pressure without recording raw protected prompts. Use bounded pools and short row locks; no per-token database write or global lock spanning external work.

## Testing Decisions

- Primary seam: authenticated submit/status/Stop/reconnect/Retry and saved Conversation. Assert one terminal outcome, correct owner visibility and allowance behavior, not internal scheduler call counts.
- Real PostgreSQL and independent worker processes are mandatory for claims, leases, cancellation/finalization races, queue population and shared cost ceilings. Process-local fakes cannot prove these properties.
- Kill workers before/after reservation, after a provider response, before/after checkpoint and during final commit. Lose Redis notification, redeliver, and verify completed steps resume without budget reset or duplicate final Turn.
- Mix ordinary/deep/ingestion queues under configured synthetic loads; prove bounded connections, per-reader fairness and eventual deep scheduling. Real provider capacity remains a separately approved measurement.
- Prior art: existing durable independent-process tests, shared admission contract tests, controller budget persistence and IR-608 recovery scenarios. Extend IR-605 run files to retain failed/cancelled/capped attempts and missing usage.

## Out of Scope

- Executing paid capacity tests without funding/provider/data approvals.
- Exactly-once remote inference or billing guarantees.
- Fixed production caps guessed from fake-provider tests.
- Moving institutional workflow writes to the AI runtime.
- Unbounded background work after disconnect.

## Further Notes

Authority: ADR-049, accepted design on 31 October 2026 following the owner’s instruction to choose the recommended options and publish specs/subtickets. Parent epic: IR-146. Related prior work: IR-605 evaluation and IR-703 immediate controller fixes. This is specified implementation work, not evidence of completion or approval for paid inference, institutional transmission, production settings, deletion or deployment. Production profile values must be explicit and validated; absent values refuse paid enablement. Subtickets are unassigned, ready-for-agent and linked by native dependencies; a blocked prerequisite is not permission to skip its tests.

### Acceptance criteria

- [ ] One request identity admits at most one active AskRun; foreign readers cannot inspect or Stop it.
- [ ] Browser disconnect/reconnect follows the same run and does not reset state or allowance.
- [ ] Cancellation/final commit races deliver one coherent terminal state and at most one Turn.
- [ ] Worker redelivery restores consumed/reserved allowance and reauthorizes checkpoints.
- [ ] Every physical paid attempt is admitted and unknown usage remains conservatively charged.
- [ ] Lost notifications are recovered from durable work without duplicate final delivery.
- [ ] Configured pools/queues remain bounded and deep work does not starve under the declared test workload.
- [ ] Conversation deletion fences later writes and removes content-bearing dependencies according to policy.

### Implementation slices

- **IR-722 — Establish AI-owned durable run and atomic Conversation commitment.** Transfer run/Conversation persistence ownership and final state fencing. Prerequisites: IR-717.
- **IR-723 — Add durable queue dispatch and fair bounded worker admission.** Separate request handling, research workers and ingestion capacity. Prerequisites: IR-722.
- **IR-724 — Checkpoint agent progress and recover fenced workers.** Persist completed exchanges and restore compatible current evidence. Prerequisites: IR-722.
- **IR-725 — Move shared provider admission to every AI physical attempt.** Preserve reservations/settlement across model, retrieval-provider and compaction work. Prerequisites: IR-722.
- **IR-726 — Prove Stop reconnect recovery and shared spending across processes.** Complete lifecycle reader contracts and independent-worker evidence. Prerequisites: IR-723, IR-724, IR-725.
