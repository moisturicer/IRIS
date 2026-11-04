# AI-runtime paid research: development decision (IR-889)

**Decision owner and approver:** Jive Tyler I. Revalde, AI runtime owner.  
**Date:** 2026-11-05 (Asia/Manila).  
**Recorded by:** AI assistant, on the owner's explicit instruction in chat to create the ticket, name him as approver, implement the approval, and open a PR. This entry is not an independent signature or code review.

## Decision

Approve a **development-only, bounded paid research pilot** for Ask IRIS's AI runtime, using the $30 campaign and per-run limits approved in [IR-861](development-limits.md). Start with a small smoke run on the reviewed 40-paper public proxy corpus, then collect the frozen, human-reviewed evaluation under IR-755. The approved endpoint for this pilot is OpenRouter with the existing `openai/gpt-oss-120b` pin because IR-861 prices it; stronger models require their own configured capacity, price, and provider policy before a send.

This decision permits implementation and, once the conditions below are met, actual development sends. It does not authorize a production deployment, reader cutover, broader model or vendor, a larger campaign, or sending a paper that fails its current disclosure policy.

## Conditions checked at each physical send

1. The run, reader grant, scope, deadline, source revision, and shared spending allowance are current.
2. Every Record-dependent part of the outgoing payload passes the canonical consent, IP and embargo disclosure check. Unknown facts refuse. The Contact person's stored AI answer from IR-791 must be the consent source before real institutional papers are sent.
3. IR-827 records the no-training and retention settings on the actual provider account and endpoint. A configuration label alone is not evidence of the account setting.
4. Tool results and all text derived from them carry source dependencies through retries, repair, compaction and resume. A dependency that fails removes its dependent content or refuses the send; the guard cannot simply be disabled.

**Current state:** conditions 2–4 are not yet fulfilled in the AI runtime. Its `SendGuard` continues to refuse tool-result evidence. The approval is a decision to enable the pilot when the code and evidence make it safe, not a claim that paid research is running today.

## Fastest useful sequence

1. Land IR-889's runtime dependency tracking and send-time check; record IR-827's actual account settings and land IR-791's consent source.
2. Apply IR-861's development values in the isolated development deployment, enable the agent executor and reader route there, and run a few proxy questions. Inspect payloads, charges, refusals and answer quality before using the rest of the campaign.
3. Freeze and review the cases required by IR-753, then run the measured collection under IR-755. A 756-turn full campaign is outside the present $30 ceiling; select a smaller predeclared set or obtain a new budget decision.
