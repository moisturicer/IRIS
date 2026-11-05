# Development-pilot limits — decision record (IR-861)

**Status: APPROVED for development only, by Jive Tyler I. Revalde, 2026-11-04.** An AI agent entered the values, the approver, the date and the signature on Jive Tyler I. Revalde's explicit instruction in chat. The decision is that person's, and the entry is not an independent signature or a code review. A later change needs its own approval by a named person.

**AI-runtime model amendment, 2026-11-05 (IR-889): use `openai/gpt-6-luna:floor`, not the OSS model in the original tables below.** The original OSS price and question-count estimates are historical; do not copy them into a Luna deployment. The $30 campaign and other numeric caps remain. [The amendment](runtime-paid-research-approval.md) names the new model and its conditions. A Luna price/capacity declaration and bounded OpenRouter routing still have to be completed before paid sends.

Authority: [ADR-041](../../adr/041-shared-provider-admission.md) (shared provider admission) and ADR-049 (AI-owned runs). Gates this record answers: [pilot README §6](README.md#6-pilot-metrics-and-gates-ac-7) — per-stage/per-run values, queue sizing and shared quotas. The proposed campaign in [§7](README.md#7-campaign-budget-and-deferred-scope-ac-8) is a starting point only.

## Scope

- **Development only.** The values apply to development deployments and their databases.
- **Production stays unapproved.** No production value is set or implied by this record. A production value needs its own record.
- **Not approved by this record:** any endpoint or vendor (README §5), data transmission or retention, deployment, a traffic switch, or a live campaign beyond the ceiling recorded below.
- **Where values go.** Into the deployment's own `backend/.env` and `ai/.env`, never into the repository. `backend/.env.example` and `ai/.env.example` keep every key with no real value.

## Approval

| | |
|---|---|
| Approver (name) | Jive Tyler I. Revalde |
| Role (budget owner) | Approver, and set the amount below. No other budget owner is named |
| Budget owner's stated amount (US$) | 30 |
| Date approved | 2026-11-04 |
| Valid until / review date | Review after the smoke test. No end date set |

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
| `AI_ADMISSION_PRICES` | US$ per million tokens per model. **An unpriced model is refused**, so this also lists the models allowed to spend | `{"openai/gpt-oss-120b":{"input":0.35,"output":0.95},"voyage-context-4":{"input":0.12,"output":0},"rerank-3":{"input":0.05,"output":0}}` | JSON `{"model": {"input": n, "output": n}}` |

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
| `RUNS_MAX_COST_USD` | **Per-run cap**: one run's spend allowance | `0.35` | positive number |
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
| `AI_RESEARCH_GRANT_TTL_SECONDS` | How long a reader's grant lasts. Set in `backend/.env`. A running run reads under its stored grant, which a reader's reconnect renews (IR-880), so a deep run outlasts this only while the reader keeps polling; a reader who stops ends it at its next read. A grant more than 5 minutes old at submission can still leave a queued run waiting for its reader | `900` | integer, 30-900 |

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

**Provider (decided 2026-11-04): OpenRouter, not Groq.** `AGENT_LLM_ENDPOINT` is `https://openrouter.ai/api/v1` and the model stays `openai/gpt-oss-120b`.

**Prices checked 2026-11-04.** The AGENT adapter (`ai/infrastructure/openai_adapter.py`) sends OpenRouter no provider list and no `data_collection` setting, so the router may choose any provider it lists for the model. Listed prices run from US$0.022 to US$0.35 input and US$0.083 to US$0.95 output per million tokens. The ledger charges reported tokens at the price recorded here, so that price must not be below what a request can cost: the record uses the highest of each, US$0.35 and US$0.95. A provider allowlist on the OpenRouter key would allow a lower price, through a new approval. Voyage's price page lists `voyage-context-4` at US$0.12 and `rerank-3` at US$0.05 per million tokens, with the first 200 million tokens free; the record ignores the free tier.

**All cost figures are estimates.** No paid AGENT call has run. They assume a 3k-token prompt, 6k tokens per tool result and 1.5k output tokens per call. At the recorded price a typical deep question (8 calls) is charged about US$0.079, and the most one run can spend is about US$0.34, which is why `RUNS_MAX_COST_USD` is `0.35`. The real bill may be lower than the ledger shows.

**What US$30 covers.** US$22.50 is spendable with the reserve held: about 286 typical deep questions, or about 381 if the reserve is released. A full evaluation of 756 turns (about US$59 at this price) does not fit either way. Run a smoke test of about 20 deep questions first (about US$1.60, at most US$6.80) and replace these estimates.

**Before sending anything to OpenRouter:**

- Require no-training on the OpenRouter key or account (a guardrail or privacy setting). The adapter does not ask for it per request, and `AGENT_LLM_DATA_POLICY` may say `no-training` only once this is confirmed.
- Set the key's credit limit to the approved amount, so OpenRouter stops spending if the estimates are wrong.
- `AI_ADMISSION_PRICES` holds the AGENT model and Voyage only. With `AI_PROVIDER_ADMISSION=enforce`, any other chat model a deployment configures is refused until it is priced in a new approval.

**This approval alone does not enable paid research.** [IR-889's development decision](runtime-paid-research-approval.md) selects `openai/gpt-6-luna:floor` for the AI runtime on 2026-11-05, superseding the OSS model, price row and estimates above for that runtime. The $30 campaign and other numeric caps remain unchanged. The literal suffixed model needs a declared capacity and price before admission; the price must bound every eligible routed endpoint, including long-prompt price overrides. `:floor` sorts by price but does not impose a maximum. Reprice the pilot from a paid Luna smoke; the OSS estimates of roughly 286 questions and US$59 for 756 turns do not apply to Luna. `ai/admission/guard.py` still refuses Record evidence until IR-889's source-aware guard and the decision's OpenRouter and per-Record conditions are met.

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
| `provider_campaign` with every value set | Exit 0: `campaign ir861-dev-pilot-2026-11`, `nothing charged yet` | AI agent, for Jive Tyler I. Revalde | 2026-11-04 |
| `provider_campaign` with one value removed | Exit 1: names `AI_ADMISSION_CAMPAIGN_MAX_COST_USD` | AI agent, for Jive Tyler I. Revalde | 2026-11-04 |

Run on the local development database with the values set for that process only, not written to `.env`. That run also set `AI_CONTROLLER_ANSWER_RESERVE_TOKENS=5223`, because the local `.env`'s 4000 fails Django's startup check. It is not a limit in this record.

## Signature

> I, Jive Tyler I. Revalde, approve the values above for **development only** in the IR-861 pilot, within a budget of US$30. This does not approve any production value, endpoint, data transmission, deployment or campaign beyond the ceiling in §1. Date: 2026-11-04.
>
> Entered by an AI agent on Jive Tyler I. Revalde's instruction in chat.
