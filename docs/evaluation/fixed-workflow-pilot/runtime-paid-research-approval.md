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

**Current state (2026-11-07):** conditions 1 and 4 are implemented for public proxy and synthetic papers. Condition 3 is recorded for OpenRouter ([IR-827 evidence](https://citiris.atlassian.net/browse/IR-827?focusedCommentId=11157)); the Voyage link is still missing. Condition 2 holds for proxy papers only: institutional papers stay refused until IR-791. No paid send has run yet.

## Luna declaration — amendment, 2026-11-07

**Approved for development only by Jive Tyler I. Revalde, 2026-11-07.** Entered by an AI agent on his instruction in chat; not an independent signature.

**Account evidence.** OpenRouter organization *Hackarambolas*. ZDR is required for all models, OpenAI first-party endpoints are disabled, and every training and publishing toggle is off, as observed 2026-11-07 and recorded on IR-827.

**Routing (`AGENT_LLM_ROUTING`).** Two endpoints at the same listed price. `amazon-bedrock/us-east-1` accepts the adapter's `max_tokens`; `azure/us` lists only `max_completion_tokens` and may be skipped under `require_parameters`.

```json
{"only":["amazon-bedrock/us-east-1","azure/us"],"allow_fallbacks":false,"data_collection":"deny","zdr":true,"require_parameters":true,"max_price":{"prompt":0.22,"completion":0.825}}
```

Routing digest (`ai.admission.guard.routing_digest`): `4f7c200d54c9388dc4bb4da0a6c4b57b33bc01860c9d4814458e3fa2dee163fd`.

**Price (`AI_ADMISSION_PRICES`).** `"openai/gpt-6-luna:floor": {"input": 0.22, "output": 0.825}` US$ per million tokens. This is both endpoints' long-prompt tier (base $0.11 / $0.55), so the ledger never charges below what a request can cost. Listings read from OpenRouter's endpoints API on 2026-11-07.

**Capacity (`AGENT_LLM_CAPACITIES`).** Conservative, not measured:

```json
{"openai/gpt-6-luna:floor":{"context_tokens":272000,"max_output_tokens":8000,"max_reasoning_tokens":null,"max_request_bytes":1000000,"min_bytes_per_token":1.0,"framing_tokens_per_message":8}}
```

272,000 keeps a request below the long-prompt tier (listed context: 1,050,000). 8,000 matches `AI_ADMISSION_MAX_OUTPUT_TOKENS`, and reasoning counts as output. A byte floor of 1.0 bounds any tokenizer.

**Still required before the first paid send:**

* An OpenRouter API key for IRIS, created by the signer with a credit limit of at most US$30. Its digest goes into the approval's `account`.
* `RUNS_PROXY_SEND_APPROVAL` naming the exact proxy sources, with an expiry.

Both are local `ai/.env` values and are never committed.

## Fastest useful sequence

1. Land IR-889's runtime dependency tracking, send-time check and price/data-policy-bound OpenRouter routing; record the OpenRouter account setting in IR-827, link the existing Voyage evidence, and land IR-791's consent source.
2. Apply IR-861's development values in the isolated development deployment, enable the agent executor and reader route there, and run a few proxy questions. Inspect payloads, charges, refusals and answer quality before using the rest of the campaign.
3. Freeze and review the cases required by IR-753, then run the measured collection under IR-755. The former 756-turn estimate used OSS and must be recalculated from a Luna smoke run; select a predeclared set that fits the remaining $30 campaign or obtain a new budget decision.
