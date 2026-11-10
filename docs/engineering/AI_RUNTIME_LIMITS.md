# AI runtime limits: proposal for approval

**Status: Partly decided. Approver: Jive Tyler I. Revalde.** Drafted by an AI agent for IR-1002 on 2026-11-09. The capacity values are **assumed**, by the approver's decision of 2026-11-09, until IR-755 measures them (see [Decision](#decision)). The per-run budget is option A, approved on 2026-11-09. Every limit stays as each deployment's `.env` sets it, and the code refuses to start when one is missing.

Every limit below is required. None has a default in code (ADR-049, ADR-041). The development values were chosen one session at a time; this page puts them in one place and fits them together.

## The mismatch this fixes

Automatic compaction now starts at **200,000** tokens of context (`RUNS_AGENT_COMPACTION`). A run may read only **700,000** input tokens in total (`RUNS_MAX_INPUT_TOKENS`). Every model call resends the whole context, so once a conversation is near the threshold a run gets about 700K ÷ 230K ≈ **3 calls**. An ordinary run can need 7, and a deep run 13. Long conversations therefore end with `allowance_exhausted` before the agent finishes researching.

**How many calls a run can make at most**

| Depth | Gathering steps | Final answer | Repairs | Calls |
|---|---|---|---|---|
| Ordinary | 4 | 1 | 2 | **7** |
| Deep | 10 | 1 | 2 | **13** |

**Largest context per call.** Compaction is checked before each gathering step, so within one run the context can keep growing past 200K, up to the window minus the reserves: 272,000 − 41,500 = **230,500**. The worst cases below use 230K.

**Prices** (`AI_ADMISSION_PRICES`, `openai/gpt-6-luna:floor`): US$0.10 per million input tokens and US$0.50 per million output tokens.

| Depth | Worst-case input | Worst-case output | Worst-case cost |
|---|---|---|---|
| Ordinary | 7 × 230K = 1.61M | 7 × 32K = 224K | 0.161 + 0.112 = **US$0.27** |
| Deep | 13 × 230K = 2.99M | 13 × 32K = 416K | 0.299 + 0.208 = **US$0.51** |

These are ceilings, not what a run usually spends. In development, a plain question read 8K–53K tokens per call. The worst-case output assumes every call fills its 32K cap, which a gathering turn never does.

**Options**

| | A. Raise the run allowance (**approved**) | B. Compact earlier |
|---|---|---|
| Change | `RUNS_MAX_INPUT_TOKENS` 3,000,000; `RUNS_MAX_COST_USD` 0.60; `RUNS_MAX_ATTEMPTS` 20 | `RUNS_AGENT_COMPACTION.threshold_tokens` 100,000; allowance unchanged |
| Gain | Long conversations keep up to 200K of exact earlier text and still finish a deep run | No budget change; each call is cheaper |
| Cost | A worst-case deep run costs up to US$0.60. The US$30 campaign still covers 50 such runs, and many more typical ones | Earlier answers are summarized sooner, so exact details are reread with `recover_turn` more often. A deep run near 130K still runs out (13 × 130K = 1.69M) unless the allowance rises as well |

Only one allowance exists. `RunLimits.allowance()` is the same for both depths, so it has to cover a deep run.

## Every limit

"Proposed" is blank where the development value is proposed unchanged.

### Per run (`ai/runs/config.py`)

| Name | Development | Proposed | Guards |
|---|---|---|---|
| `RUNS_MAX_INPUT_TOKENS` | 700,000 | **3,000,000**, approved | Total input across a run's calls (option A) |
| `RUNS_MAX_OUTPUT_TOKENS` | 100,000 | | Total output. Calls settle to their actual output, which is far below the 32K cap |
| `RUNS_MAX_COST_USD` | 0.35 | **0.60**, approved | One run's spend (option A) |
| `RUNS_MAX_ATTEMPTS` | 14 | **20**, approved | Paid calls per run: 13 for deep, plus up to 2 compaction summaries and transient retries |
| `RUNS_DEADLINE_SECONDS` | 120 | | An ordinary run's wall clock |
| `RUNS_DEEP_DEADLINE_SECONDS` | 600 | | A deep run's wall clock |
| `RUNS_LEASE_SECONDS` | 210 | | How long a worker holds a run before another may take it over |
| `RUNS_MAX_QUEUED` | 200 | 200, assumed | Queue bound before `503 busy` |
| `RUNS_MAX_ACTIVE_PER_READER` | 5 | | Runs a reader may have queued or running |
| `RUNS_MAX_RUNNING_PER_READER` | 5 | | Runs a reader may have running at once |
| `RUNS_WORKER_CONCURRENCY` | 8 | **24** per worker, two workers (IR-1012) | Runs one worker executes at once |
| `RUNS_DEEP_CONCURRENCY` | 4 | **20** per worker (IR-1012) | Deep runs per worker; must stay below the slots. Deep is the default depth, so this caps most runs |
| `RUNS_DB_POOL_SIZE` | 20 | 20 per worker, 8 per gateway process (IR-1012) | Database connections one process holds |
| `RUNS_DB_ACQUIRE_SECONDS` | 10 | 10 (IR-1012) | How long a call waits for a connection before `503 busy` |
| `RUNS_POLL_SECONDS` | 1 | | Worker polling interval when Redis wakeups are off |

### Agent profile (`ai/runs/agent_profile.py`, `ai/infrastructure/agent_config.py`)

| Name | Development | Proposed | Guards |
|---|---|---|---|
| `RUNS_AGENT_MODEL` | `openai/gpt-6-luna:floor` | | The pinned model |
| `RUNS_AGENT_BOUNDS` | ordinary 4 steps / 4 calls, deep 10 / 10, history 6 turns | | Research length per depth |
| `RUNS_AGENT_RESERVES` | answer 16,000, reasoning 16,000, next result 9,000, repair 1,500 | | Room held back in every request |
| `RUNS_AGENT_COMPACTION` | threshold 200,000, summary 3,000, keep 2 exchanges, 2 attempts | | When earlier context is condensed (option B changes the threshold) |
| `AGENT_LLM_CAPACITIES` | 272,000 context, 32,000 output (reasoning inside), 1,000,000 request bytes | | The model's limits as IRIS uses them. OpenRouter lists 1,050,000 context and 128,000 output for `gpt-6-luna` |
| `AI_ADMISSION_MAX_OUTPUT_TOKENS` | 32,000 | | The largest completion cap any one call may reserve |

### Campaign and admission (`ai/admission/limits.py`)

| Name | Development | Proposed | Guards |
|---|---|---|---|
| `AI_ADMISSION_CAMPAIGN` | `ir861-dev-pilot-2026-11` | a production name | Which spending ledger row is charged |
| `AI_ADMISSION_CAMPAIGN_MAX_COST_USD` | 30 (approved for development, IR-861) | needs a production figure | Total spend |
| `AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS` | 10,000 | | Total paid calls |
| `AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS` | 150,000,000 | | At US$0.10/M this is US$15 of input |
| `AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS` | 16,000,000 | | At US$0.50/M this is US$8 of output |
| `AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES` | 2,250 | | Total time calls may hold a slot |
| `AI_ADMISSION_RESERVE_FRACTION` | 0.25 | | The share of the campaign kept back for core work |
| `AI_ADMISSION_LANE_CONCURRENCY` | research 16, chat 4, ingestion 2, overview 2, shadow 1, embedding 4, reranking 4, extraction 2 | **research 48, embedding 16, reranking 8**, the rest unchanged (IR-1012) | Calls in flight per lane |
| `AI_ADMISSION_ACCOUNT_CONCURRENCY` | 24 | **64** (IR-1012) | Calls in flight per vendor account |
| `AI_ADMISSION_PRICES` | luna 0.10/0.50, voyage-context-4 0.12, rerank-3 0.05 (US$/M) | | Luna checked against OpenRouter's Azure endpoint on 2026-11-09: 0.10/0.50 below 272K prompt tokens, doubling above it. Cached input costs 0.01 and is still charged at 0.10 | The prices every reservation is costed at |

### Optional switches (IR-953, off)

| Name | Development | Proposed | Guards |
|---|---|---|---|
| `AGENT_LLM_PROMPT_CACHE` | off | decided in ADR-049's IR-953 amendment | Sends a per-run prompt-cache key |
| `RUNS_QUERY_VECTOR_CACHE` | off | **on**, approved | Reuses a query's embedding within one run |
| `RUNS_AGENT_TOOL_CONCURRENCY` | unset (1) | **4**, assumed | Read-only calls in one tool group fetched at once (IR-1003, approved). 4 matches an ordinary run's tool-call limit. At 8 runs per worker, that is up to 32 extra database connections per worker |

`RUNS_DEPLOYMENT_STAGE` and `RUNS_PROXY_SEND_APPROVAL` are left out: IR-996 deletes them.

## Assumed until measured

The values marked "assumed" control how many readers IRIS serves at once. Nobody has measured that on a real vendor (`eval_pilot_capacity` has never run with `--providers real`). The approver decided to assume them: they are the development values, adopted as they are. IR-755 replaces them with measured ones. Until then they are not a capacity claim.

## Decision

| Date | Decision | By |
|---|---|---|
| 2026-11-09 | Capacity limits are assumed at their development values until IR-755 measures them: `RUNS_MAX_QUEUED`, `RUNS_WORKER_CONCURRENCY`, `RUNS_DEEP_CONCURRENCY`, `AI_ADMISSION_LANE_CONCURRENCY`, `AI_ADMISSION_ACCOUNT_CONCURRENCY`, and the new `RUNS_AGENT_TOOL_CONCURRENCY` at 4 | Jive Tyler I. Revalde, in chat |
| 2026-11-09 | Concurrent tool calls approved (ADR-049, IR-953 amendment, item 4) | Jive Tyler I. Revalde, in chat |
| 2026-11-09 | Option A: `RUNS_MAX_INPUT_TOKENS` 3,000,000, `RUNS_MAX_COST_USD` 0.60, `RUNS_MAX_ATTEMPTS` 20 | Jive Tyler I. Revalde, in chat |
| 2026-11-09 | `RUNS_QUERY_VECTOR_CACHE` on | Jive Tyler I. Revalde, in chat |
| 2026-11-09 | Paid measurement runs wait until IR-1004 is implemented | Jive Tyler I. Revalde, in chat |
| open | A production campaign name and ceiling | Jive Tyler I. Revalde |
