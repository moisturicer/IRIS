# AI-runtime paid research: development decision (IR-889)

**Decision owner and approver:** Jive Tyler I. Revalde, AI runtime owner.  
**Date:** 2026-11-05 (Asia/Manila).  
**Recorded by:** AI assistant, on the owner's explicit instruction in chat to create the ticket, name him as approver, implement the approval, and open a PR. This entry is not an independent signature or code review.

## Decision

Approve a **development-only, bounded paid research pilot** for Ask IRIS's AI runtime, using the $30 campaign and per-run limits approved in [IR-861](development-limits.md). Start with a small smoke run on the reviewed 40-paper public proxy corpus, then collect the frozen, human-reviewed evaluation under IR-755. **Selected endpoint and model:** OpenRouter, `openai/gpt-6-luna:floor`, as the owner directed on 2026-11-05. The `:floor` suffix selects price-first routing and admits flex endpoints; it is the same base Luna model, not a separate model release. The prior `openai/gpt-oss-120b` selection and its cost projections are superseded for this pilot. Other models need their own capacity, price and provider-policy declaration before a send.

The literal `openai/gpt-6-luna:floor` string must match in `RUNS_AGENT_MODEL`, `AGENT_LLM_MODELS`, `AGENT_LLM_CAPACITIES` and `AI_ADMISSION_PRICES`. [OpenRouter's model API](https://openrouter.ai/api/v1/models/openai/gpt-6-luna/endpoints) currently lists a 1,050,000-token context and 128,000 maximum completion tokens for the underlying model. Those are provider listings, not a verified byte-capacity declaration for this adapter. The runtime needs a price bound on eligible endpoints and a provider data-policy check; the `:floor` suffix alone guarantees neither. Keep the $30 campaign and existing per-run caps, and re-estimate question and campaign costs from the first paid smoke rather than reusing the OSS estimates.

This decision permits implementation and, once the conditions below are met, actual development sends. It does not authorize a production deployment, reader cutover, broader model or vendor, a larger campaign, or sending a paper that fails its current disclosure policy.

## Conditions checked at each physical send

1. The run, reader grant, scope, deadline, source revision, and shared spending allowance are current.
2. Every Record-dependent part of the outgoing payload passes the canonical consent, IP and embargo disclosure check. Unknown facts refuse. The Contact person's stored AI answer from IR-791 must be the consent source before real institutional papers are sent.
3. IR-827 links the owner's earlier Voyage confirmation and records the no-training and retention settings on the actual OpenRouter account and eligible endpoints. The owner reconfirmed on 2026-11-05 that Voyage was confirmed long ago; do not ask for a second Voyage approval. The original dated account-specific record was not found in the repository or Jira, so it still needs linking. A configuration label alone is not evidence of the OpenRouter account setting.
4. Tool results and all text derived from them carry source dependencies through retries, repair, compaction and resume. A dependency that fails removes its dependent content or refuses the send; the guard cannot simply be disabled.

**Current state (2026-11-07):** conditions 1 and 4 are implemented for public proxy and synthetic papers. Condition 3 is recorded for OpenRouter ([IR-827 evidence](https://citiris.atlassian.net/browse/IR-827?focusedCommentId=11157)); the Voyage link is still missing. Condition 2 holds for proxy papers only: institutional papers stay refused until IR-791. Paid development sends have run; see the smoke results below.

## Luna declaration — amendment, 2026-11-07

**Approved for development only by Jive Tyler I. Revalde, 2026-11-07.** Entered by an AI agent on his instruction in chat; not an independent signature.

**Account evidence.** OpenRouter organization *Hackarambolas*, workspace **IRIS**, key `iris`. As first observed on 2026-11-07 (recorded on IR-827), ZDR was required for all models, OpenAI first-party endpoints were disabled, and every training and publishing toggle was off. Later that day the owner had the account-wide ZDR requirement turned off and the IRIS workspace guardrail changed to allow Safety Retention. The training and publishing toggles stay off. Safety Retention is not an option for Luna: OpenRouter offers it only for Google and "all other models", and Luna is in the OpenAI group. Luna sends therefore still go only to zero-retention endpoints, enforced per request by `zdr: true` in the routing below and checked by the send guard. The account setting is no longer what enforces it.

**Account limits (set by the owner, 2026-11-07).** The `iris` key's limit was lowered from $50 to the approved $30, and the IRIS workspace's monthly budget was raised from $3 to $30.

**Routing (`AGENT_LLM_ROUTING`).** Global Azure at Luna's base price, zero-retention. The 2026-11-07 smoke showed that `amazon-bedrock/global` is not a zero-retention endpoint for Luna: OpenRouter refused every request with `zdr: true`, failing at "Filter by Data Policy". `azure` accepted the adapter's `max_tokens` and tools. `max_price` excludes the dearer `azure/us` and `azure/eu`.

```json
{"only":["azure"],"allow_fallbacks":false,"data_collection":"deny","zdr":true,"require_parameters":true,"max_price":{"prompt":0.1,"completion":0.5}}
```

Routing digest (`ai.admission.guard.routing_digest`): `e601031fde08362611a9d69b332e9a49dd770246878b6a89544ee32e50b5cad5`.

**Price (`AI_ADMISSION_PRICES`).** `"openai/gpt-6-luna:floor": {"input": 0.1, "output": 0.5}` US$ per million tokens: the endpoint's price for prompts under 272,000 tokens. The capacity below keeps every request under that size, so the long-prompt price ($0.20 / $0.75) can't apply. Listing read from OpenRouter's endpoints API on 2026-11-07.

*Superseded the same day:* `amazon-bedrock/global` (not zero-retention for Luna), and before it `amazon-bedrock/us-east-1` + `azure/us` at $0.22 / $0.825. Those regional endpoints cost 10% more, and that price assumed the long-prompt tier, which the capacity cap already rules out.

**Capacity (`AGENT_LLM_CAPACITIES`).** Conservative, not measured:

```json
{"openai/gpt-6-luna:floor":{"context_tokens":272000,"max_output_tokens":8000,"max_reasoning_tokens":null,"max_request_bytes":1000000,"min_bytes_per_token":1.0,"framing_tokens_per_message":8}}
```

272,000 keeps a request below the long-prompt tier (listed context: 1,050,000). 8,000 matches `AI_ADMISSION_MAX_OUTPUT_TOKENS`, and reasoning counts as output. A byte floor of 1.0 bounds any tokenizer.

**Local configuration (done 2026-11-07).** The signer entered the `iris` key in `ai/.env` (`AGENT_LLM_API_KEY`), and its digest is the approval's `account`. `RUNS_PROXY_SEND_APPROVAL` names the exact revisions of the 40 proxy papers and expires 2026-11-21 23:59 +08. Both are local `ai/.env` values and are never committed.

**First paid smoke, 2026-11-07.** One ordinary-depth proxy question (`proxy_starter.json` q01), asked as `student@cit.edu`, ran on run `70843937`. It completed `answered` in 92 s and cited the expected paper. It used 4 attempts, all settled with reported usage: 34,083 input and 1,128 output tokens, charged **US$0.0040**. Earlier attempts the same day sent nothing (local configuration was not loaded), and one sent request was refused by OpenRouter's data-policy filter with no reported usage. That request is charged at its reservation, US$0.0047.

**Twenty-question smoke, 2026-11-07.** Twenty `proxy_starter.json` questions were asked at deep depth, one at a time: 8 mechanism, 3 exact-term, 3 near-duplicate, 3 cross-paper and 3 off-corpus. Together they used 56 attempts, 425,544 input and 7,080 output tokens, charged **US$0.0461** (about $0.0023 a question).

* 13 of 20 answered. Every answered in-corpus question cited its expected paper (12 of 12).
* 6 in-corpus questions ended `unavailable` because the guard refused the whole send: their search results included an institutional Record. Commit `4cc0bf14` now drops sources the approval does not cover from tool results instead. After that change q03 answered and cited its expected paper.
* Of the 3 off-corpus questions, which the set expects to decline, q55 and q56 ended `unavailable` and **q66 answered**. Answer quality needs the IR-755 human review; this smoke does not measure it.

**Ledger total, 2026-11-07:** 82 sent attempts on `openai/gpt-6-luna:floor`, **US$0.0868** charged (US$0.0821 settled at reported usage, plus the refused request's US$0.0047 reservation). Recomputing at the declared price gives the same figure to within per-attempt rounding, which only rounds up. Reconciling against OpenRouter's own activity for the `iris` key is still to be recorded.

**Latency.** The 20-question batch took a median of 53 s and at most 140 s. Most of that came from a local Windows artifact: each database connection to `localhost` waited about 2 s on an IPv6 fallback. With `127.0.0.1`, one ordinary question took 25 s instead of 72 s, and model calls (about 4.6 s each) became about 92% of the time. Production containers reach PostgreSQL by service name and should not pay that delay. Production latency has not been measured.

## Fastest useful sequence

1. Land IR-889's runtime dependency tracking, send-time check and price/data-policy-bound OpenRouter routing; record the OpenRouter account setting in IR-827, link the existing Voyage evidence, and land IR-791's consent source.
2. Apply IR-861's development values in the isolated development deployment, enable the agent executor and reader route there, and run a few proxy questions. Inspect payloads, charges, refusals and answer quality before using the rest of the campaign.
3. Freeze and review the cases required by IR-753, then run the measured collection under IR-755. The former 756-turn estimate used OSS and must be recalculated from a Luna smoke run; select a predeclared set that fits the remaining $30 campaign or obtain a new budget decision.
