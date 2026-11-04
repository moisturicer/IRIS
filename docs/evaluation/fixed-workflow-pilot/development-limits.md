# Development-pilot limits — decision record (IR-861)

**Status: PROPOSED. Nothing here is approved until the signature below is complete.** An agent prepared this record and, on Jive Tyler I. Revalde's instruction (2026-11-04), copied in the values below. **A named person must review, sign and date them.** An agent must not fill in the approver, the date or the signature (CLAUDE.md, "What AI does not decide").

Authority: [ADR-041](../../adr/041-shared-provider-admission.md) (shared provider admission) and ADR-049 (AI-owned runs). Gates this record answers: [pilot README §6](README.md#6-pilot-metrics-and-gates-ac-7) — per-stage/per-run values, queue sizing and shared quotas. The proposed campaign in [§7](README.md#7-campaign-budget-and-deferred-scope-ac-8) is a starting point only.

## Scope

- **Development only.** The values apply to development deployments and their databases.
- **Production stays unapproved.** No production value is set or implied by this record. A production value needs its own record.
- **Not approved by this record:** any endpoint or vendor (README §5), data transmission or retention, deployment, a traffic switch, or a live campaign beyond the ceiling recorded below.
- **Where values go.** Into the deployment's own `backend/.env` and `ai/.env`, never into the repository. `backend/.env.example` and `ai/.env.example` keep every key with no real value.

## Approval

| | |
|---|---|
| Approver (name) | |
| Role (budget owner) | |
| Budget owner's stated amount (US$) | |
| Date approved | |
| Valid until / review date | |

## 1. Campaign ceiling — total spend (both runtimes share one ledger)

Read by Django (`backend/apps/ai/admission/limits.py`) and the AI runtime (`ai/admission/limits.py`). Both must carry the **same** values: they charge one campaign row. The ceiling and reserve must fit the budget owner's stated amount above.

| Setting | What it bounds | Value | Format |
|---|---|---|---|
| `AI_ADMISSION_CAMPAIGN` | The campaign's name; every charge is recorded against it | `ir861-dev-pilot-2026-11` | text, ≤ 64 chars |
| `AI_ADMISSION_CAMPAIGN_MAX_COST_USD` | **Total spend** in US$, retries and fallbacks included | `30` | positive number |
| `AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS` | Total paid vendor calls | `10000` | positive integer |
| `AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS` | Total tokens sent | `150000000` | positive integer |
| `AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS` | Total tokens generated | `16000000` | positive integer |
| `AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES` | Total time vendor calls may be in flight | `2250` | positive number |
| `AI_ADMISSION_RESERVE_FRACTION` | Share of every ceiling held back as a **protected reserve** | `0.25` | between 0 and 1, exclusive |
| `AI_ADMISSION_RESERVE_RELEASED` | Whether the reserve may be spent. Only the budget owner releases it | `False` | boolean |

## 2. Per-call cap and prices

| Setting | What it bounds | Value | Format |
|---|---|---|---|
| `AI_ADMISSION_MAX_OUTPUT_TOKENS` | The completion cap every chat-model request carries, and is reserved at | `8000` | positive integer |
| `AI_ADMISSION_PRICES` | US$ per million tokens per model. **An unpriced model is refused**, so this also lists the models allowed to spend | `{"openai/gpt-oss-120b":{"input":0.15,"output":0.60}}` | JSON `{"model": {"input": n, "output": n}}` |

## 3. Concurrency — calls in flight at once

| Setting | What it bounds | Value | Format |
|---|---|---|---|
| `AI_ADMISSION_LANE_CONCURRENCY` | Calls in flight per lane. **A lane left out is refused.** Lanes: `chat`, `research`, `ingestion`, `overview`, `shadow`, `embedding`, `reranking`, `extraction`. AI runs use `research` | `{"research":4,"chat":4,"ingestion":2,"overview":2,"shadow":1,"embedding":4,"reranking":4,"extraction":2}` | JSON `{"lane": n}` |
| `AI_ADMISSION_ACCOUNT_CONCURRENCY` | Calls in flight on any one vendor account, whatever the lane | `6` | positive integer |

## 4. Django's queue and per-run caps (queued Ask IRIS questions)

Django only. The AI runtime does not read these: its per-run ceiling is the run's own allowance (§5).

| Setting | What it bounds | Value | Format |
|---|---|---|---|
| `AI_ADMISSION_RUN_MAX_COST_USD` | **Per-run cap**: spend for one queued question | `0.06` | positive number |
| `AI_ADMISSION_RUN_MAX_ATTEMPTS` | Per-run cap: paid calls for one question | `8` | positive integer |
| `AI_ADMISSION_RUN_MAX_INPUT_TOKENS` | Per-run cap: tokens sent | `200000` | positive integer |
| `AI_ADMISSION_RUN_MAX_OUTPUT_TOKENS` | Per-run cap: tokens generated | `40000` | positive integer |
| `AI_ADMISSION_QUEUE_DEPTH` | **Queue depth**: unfinished queued questions across everyone (beyond it: `503 busy`) | `20` | positive integer |
| `AI_ADMISSION_QUEUE_PER_USER` | Unfinished queued questions per asker | `3` | positive integer |

## 5. AI runtime runs (`ai/runs/config.py`)

Every one is required; while any is unset, every run submission is refused.

| Setting | What it bounds | Value | Format |
|---|---|---|---|
| `RUNS_MAX_COST_USD` | **Per-run cap**: one run's spend allowance | `0.20` | positive number |
| `RUNS_MAX_ATTEMPTS` | Per-run cap: paid calls in one run | `14` | positive integer |
| `RUNS_MAX_INPUT_TOKENS` | Per-run cap: tokens sent | `700000` | positive integer |
| `RUNS_MAX_OUTPUT_TOKENS` | Per-run cap: tokens generated | `100000` | positive integer |
| `RUNS_DEADLINE_SECONDS` | How long an ordinary run may take | `120` | positive integer |
| `RUNS_DEEP_DEADLINE_SECONDS` | How long a deep run may take | `600` | positive integer |
| `RUNS_LEASE_SECONDS` | How long a worker holds a run before another may reclaim it | `210` | positive integer |
| `RUNS_MAX_QUEUED` | **Queue depth**: active runs across every reader (beyond it: `503 busy`) | `10` | positive integer |
| `RUNS_MAX_ACTIVE_PER_READER` | Active runs per reader | `3` | positive integer |
| `RUNS_MAX_RUNNING_PER_READER` | Runs executing at once per reader | `1` | positive integer |
| `RUNS_WORKER_CONCURRENCY` | **Concurrency**: run slots per worker process | `4` | positive integer |
| `RUNS_DEEP_CONCURRENCY` | Deep runs at once; **must be below** `RUNS_WORKER_CONCURRENCY` | `2` | positive integer |
| `RUNS_POLL_SECONDS` | How often an idle worker checks the queue. Not a spend limit | `2` | positive number |
| `AI_RESEARCH_GRANT_TTL_SECONDS` | How long a reader's grant lasts. Set in `backend/.env`. A run stops when its grant expires until IR-880 renews it mid-run, so this must outlast the deep deadline. A grant more than 5 minutes old at submission can still end a deep run early | `900` | integer, 30-900 |

## 6. AGENT runs (only with `RUNS_EXECUTOR=agent`, `ai/runs/agent_profile.py`)

| Setting | What it bounds | Value | Format |
|---|---|---|---|
| `RUNS_EXECUTOR` | Which executor new runs are pinned to. `deterministic` spends nothing | `agent` | `deterministic` or `agent` |
| `RUNS_AGENT_MODEL` | The model AGENT runs use. Must appear in `AGENT_LLM_MODELS`, `AGENT_LLM_CAPACITIES` and `AI_ADMISSION_PRICES` | `openai/gpt-oss-120b` | model name |
| `RUNS_AGENT_BOUNDS` | Per depth: research turns (`max_steps`), tool calls (`max_tool_calls`), turns without progress (`max_no_progress`), seconds held for the final answer (`final_seconds`), earlier turns carried (`history_turns`) | `{"ordinary":{"max_steps":4,"max_tool_calls":4,"max_no_progress":2,"final_seconds":30,"history_turns":6},"deep":{"max_steps":10,"max_tool_calls":10,"max_no_progress":3,"final_seconds":60,"history_turns":6}}` | JSON `{"ordinary": {...}, "deep": {...}}` |
| `RUNS_AGENT_RESERVES` | Tokens held back before evidence is admitted: `output_tokens`, `reasoning_tokens`, `next_result_tokens`, `repair_tokens` | `{"output_tokens":4000,"reasoning_tokens":4000,"next_result_tokens":9000,"repair_tokens":1500}` | JSON object |

`RUNS_EXECUTOR=agent` also needs every `AGENT_LLM_*` setting (`ai/.env.example`). Those describe the endpoint and the model's declared capacity, not spending limits, so they are out of this record's scope. `AGENT_LLM_DATA_POLICY` must be `no-training` and still needs the vendor-terms approval in README §5.

## How these values were chosen

Decision (2026-11-04): a US$30 ceiling, with each value that changed for deep-by-default research set midway between the first proposal and the deep calculation.

| Setting | First proposal | Deep calculation | Value |
|---|---|---|---|
| Campaign cost (US$) | 20 | 50 | **30**, as chosen (the exact midpoint is 35) |
| Campaign input tokens | 60000000 | 240000000 | 150000000 |
| Campaign output tokens | 8000000 | 24000000 | 16000000 |
| Campaign attempts | 6000 | 14000 | 10000 |
| Campaign active minutes | 1500 | 3000 | 2250 |
| `RUNS_DEEP_CONCURRENCY` | 1 | 3 | 2 |
| `RUNS_LEASE_SECONDS` | 180 | 240 | 210 |
| `RUNS_MAX_QUEUED` | 20 | 12 | **10, not the midpoint.** With 2 deep slots and about 2 minutes per run, the last of 16 would wait about 14 minutes and expire at the 10-minute deadline |

**All cost figures are estimates.** No paid AGENT call has run. They assume a 3k-token prompt, 6k tokens per tool result, 1.5k output tokens per call and Groq's listed US$0.15 / US$0.60 per million tokens (checked 2026-11-04). A typical deep question is taken as 8 calls and about US$0.036; the most one run can spend is about US$0.165.

**What US$30 covers.** US$22.50 is spendable with the reserve held, and input tokens run out first, at about 585 typical deep questions. A full evaluation of 756 turns (about US$27) does not fit unless the budget owner releases the reserve for it. Run a smoke test of about 20 deep questions first and replace these estimates.

**Still open before this can be signed:**

- `AI_ADMISSION_PRICES` needs `voyage-context-4` and `rerank-3` from Voyage's price page, because an unpriced model is refused.
- `AI_ADMISSION_ACCOUNT_CONCURRENCY` and the deep concurrency need checking against the Groq account's rate limit.

**Signing does not enable paid research.** `ai/admission/guard.py` still refuses Record evidence until the disclosure decision in ADR-049 is made, and Groq's no-training terms are unconfirmed.

## Not decided here

- **Extraction pricing** (`AI_ADMISSION_EXTRACTION_*`, `AI_ADMISSION_METADATA_CREDITS_PER_PAGE`). These are optional: unset, they refuse only off-campus PDF reads and Publish suggestions. Record them separately if wanted.
- **`AI_ADMISSION_LEASE_GRACE_SECONDS`** is a timing allowance with a default (15), not a spending limit.

## Check after applying (IR-861 demonstration)

On a development database, with the values above in `backend/.env` and `AI_PROVIDER_ADMISSION=enforce`:

```bash
python manage.py provider_campaign
```

Expected: `campaign <name>` then `nothing charged yet`. Then remove one required value and run it again. Expected: it names that setting and exits non-zero.

| Check | Result | Run by | Date |
|---|---|---|---|
| `provider_campaign` with every value set | | | |
| `provider_campaign` with one value removed | | | |

## Signature

> I, [name], approve the values above for **development only** in the IR-861 pilot, within a budget of US$[amount]. This does not approve any production value, endpoint, data transmission, deployment or campaign beyond the ceiling in §1. Date: [ ].
