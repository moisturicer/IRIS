# Core journeys run — `<SHA>` (`<YYYY-MM-DD>`)

Copy this file to `runs/<YYYY-MM-DD>-core-journeys-<short-sha>.md` for a run.
Plan and status rules: [`../CORE_JOURNEYS.md`](../CORE_JOURNEYS.md).

## Build, settings, data

| | |
|---|---|
| Commit | `<full SHA>` |
| Workflow run | `<link to the core-journeys run>` |
| Artifact | `core-journeys-<SHA>` |
| Settings | `config.settings.production`; flags at defaults; no disclosure bypass |
| Env keys set (no values) | `<from e2e/.env.e2e: key names only>` |
| Data | fresh DB, `seed_demo --accounts-only`, Turnaround `<n>` working days per party |
| Idle pass | `SESSION_IDLE_TIMEOUT_MINUTES=2` — ran / not run |
| Run by | `<name>` |

## Limitations

- TLS not terminated; `X-Forwarded-Proto: https` sent as the proxy would.
- Mail delivered to Mailpit inside the stack.
- Turnaround is demonstration data, not an agreed value.
- No capacity or throughput claim; latency figures carry no verdict (IR-95).
- `<anything else that differed>`

## Results

| AC | Check | Status | Evidence | Defect |
|---|---|---|---|---|
| 1 | Account lifecycle | Passed / Failed / Unmeasured — reason | `<report link or trace>` | `<IR-…>` |
| 2 | Thesis/Project | | | |
| 3 | Proposal → Continuation | | | |
| 4 | Coordination | | | |
| 5 | Discussion/history | | | |
| 6 | Reading and Ask IRIS (reused IR-630, IR-605/608 on this SHA) | | | |
| 7 | Adversarial access | | | |
| 8 | Integrity | | | |
| 9 | Keyboard, zoom, 360px — automated | | | |
| 9 | Keyboard, zoom, 360px — manual (below) | | | |
| 10 | Concurrency/recovery — consistency | | | |
| 10 | Concurrency/recovery — observed latency (no verdict) | Recorded | `<figures>` | — |

## Manual checklist (AC9)

Run by a person on the same stack, each journey's key screen:

| Screen | Keyboard only | 400% zoom | 360px | Screen reader | Notes |
|---|---|---|---|---|---|
| Sign in / Register | | | | | |
| Paper View — Review timeline | | | | | |
| My Reviews — overdue | | | | | |
| Coordinator console | | | | | |
| Proposal with Continuation | | | | | |
| Audit log + export | | | | | |

## Sign-off

A failed required journey blocks completion. Approval is a person's, under
`docs/engineering/DEFINITION_OF_DONE.md` §4.

| Reviewer | Date | Decision |
|---|---|---|
| | | |
