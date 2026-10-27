# Controller recovery and failure checks (IR-597)

Authority: ADR-042 and the approved general-tools specification sections 7 and 10.
These controls do not approve a pilot, prices, provider use or production enablement.
The new-run engine remains `lanes-v1`; human review and the existing release gates still apply.

## Invariants

- Submission captures controller/research bounds in `AskRun.request.controller_budget`.
  Every round, tool attempt (including a malformed or duplicate call), and prompt charge
  commits under the current attempt fence before work. Redelivery retains those counters,
  the original deadline, declared admission ceiling and admission run key. Queue time consumes the declared wall allowance.
- Evidence, handles, continuations and tool-result caches are rebuilt after a worker crash.
  No document-bearing checkpoint is restored. Current permissions, disclosure, source versions
  and conversation revision are checked again. An explicit user retry is a new run with fresh
  spend/deadline, the same declared bounds, and the original conversation revision check.
- Research cannot consume the configured ANSWER/repair input allowance or shared per-run
  attempt/output/cost allowance. Admission input units are conservative UTF-8 bytes plus framing;
  a composed prompt exceeding its declared input allowance is unavailable, not sent.
  Cost holds use the most expensive configured prices. These are bounds, not throughput estimates.
  Other runs may still exhaust the campaign or occupy concurrency slots; no successful answer
  is promised under global exhaustion. Unknown usage remains charged at its original reservation.
- Supersession, cancellation, deletion, a terminal state or the original deadline fences new
  admissions and late writes. The adapter rechecks the run immediately before transport.
  Already-sent work is not recalled: its reservation remains charged until settlement, or
  conservatively abandoned after its lease. No raw provider response is needed to inspect it.
- Envelopes keep private source pointers. Every subsequent planning prompt and answer handoff
  checks the exact title/abstract and active chunk-set hash as well as current access.
  Metadata/filter/taxonomy/index eligibility changes invalidate computed facts even when visible
  record IDs are unchanged. Replaced historical citations leave prompt/recall reuse; changes during
  RESOLVE or PLAN discard derived rewrites, completions and tool arguments before another send. The answer and display summary
  are withheld if their computed facts or history lose authorization during composition.
  Withdrawn source positions stay stable during answer validation; stale text is not resent.

## Recovery and rollback

1. Inspect the owned run state, deadline, current attempt and ordered journal. Use the existing
   `public-1` projection for readers; internal budget state and failure diagnostics are not public DTOs.
2. A crashed delivery may be redelivered through the existing queued-question task. Claiming
   supersedes the old attempt. Repeated completed deliveries produce no second final Turn.
   Never edit a deadline, counters, source pointers or context revision to make a run succeed.
3. Cancel through the authenticated cancel endpoint. Reconnect with the existing ordered cursor;
   cancellation has one terminal event and no later Turn/state commit. A genuine user retry uses
   the retry endpoint and its fresh admission, not a counter reset on the old run.
4. Roll back the code selecting the engine for **new** runs. Keep implementations of every
   supported in-flight engine/protocol/PLAN/ANSWER prompt bundle available until those jobs drain.
   This release accepts its exact bundle and unpinned pre-controller legacy runs; an unsupported
   bundle fails closed before preparation or a resolver/provider call. It never runs new prompts
   under an old version label. Old transcripts retain the existing safe public projection.
5. Shared-store failure denies paid admission. Restore the store before retrying; do not turn
   admission off or report unfinished research as zero matches. Reconnect still reports the run's
   truthful busy/unavailable/cancelled result where the store is reachable.

## Operational signals

Use run/attempt IDs, pinned version labels, lifecycle/failure codes, elapsed times, cumulative
round/tool/prompt counters, charged/reserved admission totals, open/abandoned lease counts,
controller stop reasons, validation codes and reconnect cursor/terminal-event counts.
Alert on sustained admission store failures, expired/orphaned runs, unsupported version bundles,
repeated fenced attempts or duplicate-terminal anomalies. Existing `provider_campaign` reports
shared charges. Do not put questions, source text, titles, model drafts, raw reasoning,
continuation artifacts, credentials or private tool payloads into routine metrics/logs.

## Acceptance evidence map

| Contract | Deterministic verification |
|---|---|
| Original bounds/deadline, pre-work charge, retry | `test_controller_durable_budget.py`, `test_admission_http.py` |
| Answer/repair reserve, unknown usage, retry/fallback | `admission/tests/test_answer_reserve.py`, `test_shared_processes.py` |
| Cancel/supersession/late answer | `test_controller_recovery_http.py`, `test_durable_processes.py` |
| Crash, redelivery, one Turn and contiguous journal | `test_durable_processes.py`, `test_durable_ask_http.py` |
| Rechunk, metadata change, revoked facts | `test_controller_security_http.py`, `research/tests/test_registry_contract.py` |
| Stale conversation revision, source revocation | `test_conversation_state.py`, `test_controller_http.py`, `test_public_history_http.py` |
| Closed tools, malicious document, Paper Chat scope | `test_controller_security_http.py`, `test_controller_http.py` |
| Exact version pins, rollback, reconnect/public compatibility | `test_controller_recovery_http.py`, `test_controller_http.py`, `test_public_history_http.py`, `test_public_protocol_http.py` |
| Shared-store failure and independent-process accounting | `admission/tests/test_ledger.py`, `test_shared_processes.py` |

The process probes use separate interpreters and real Postgres, with stdin gates choosing the
winning commit. The controller crash probe uses production preparation, version checks, budget
binding, controller and admission with deterministic providers; it crashes after a paid attempt is
reserved, then restores cumulative spend on redelivery. The simpler ownership probes replace answer
orchestration while retaining production claim, admission, Turn/state writes and journal. They are correctness/race evidence, not real model quality, Celery-broker
availability or paid capacity evidence. Full authenticated controller and public replay tests cover
the HTTP boundaries separately. No paid load test, institutional transmission or deployment ran.
