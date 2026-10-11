# ADR-036: Groq and OpenRouter behind one OpenAI-compatible adapter

## Status

Accepted — 2026-09-15. Decided by the team; recorded here because
`docs/adr/` is the decision authority and no ADR had ever named an inference
vendor. The reasoning is worked through at length in
[`docs/rag_third_party_services_architecture.md`](../rag_third_party_services_architecture.md)
§2, which this ADR records rather than restates.

**Supersedes the de-facto Anthropic implementation.** `apps/ai/services/llm_generator.py`
called Anthropic, chosen in code rather than in a decision record. **Anthropic
is not used.**

**Amended — 2026-09-28 (IR-376).** The rule *"one provider per environment,
selected by configuration"* is **superseded**. It is replaced by **one adapter
per protocol, vendor chosen per Inference task**: see §Amendment below. The
sanctioned vendors are unchanged — Groq and OpenRouter, and no others.

> **Amendment proposed — 2026-10-10 (IR-487). Not accepted.** The Decisions adapter may move from evaluation-only to a reader's path, behind a per-provider approval switch that fails closed. The owner's data-handling rule (no training; retention acceptable; zero data retention not required) is recorded, and OpenRouter provider routing enforces the hosting rule. Drafted by an AI agent; **awaiting approval by Jive Tyler Revalde**. See §Amendment — 2026-10-10 below.

> **Amendment proposed — 2026-10-11 (IR-499). Not accepted.** Three new Inference tasks (`plan`, `screen`, `route`) and a production approval for Jev, **for routing and reader-question screening only**, which supersedes the 2026-10-10 amendment for those two uses. Drafted by an AI agent; awaiting a named approver. See §Amendment — 2026-10-11 below.

**Does not contradict [ADR-008](008-ai-degradation-to-fts.md).** That ADR
rejected *"a secondary LLM provider for failover"* — two providers live at once
for resilience, one covering for the other's outage. Choosing a different
vendor for a different task is not failover: each task has exactly one vendor,
and no vendor covers for another. ADR-008 was amended the same day (2026-09-28,
IR-376) to permit **model fallback inside one vendor account** and to confirm
that cross-vendor failover stays rejected. Its degraded-mode rule is untouched:
when the provider is unavailable the answer is replaced by an explicit
unavailable state and never by a fabricated one.

**Extends [ADR-006](006-minimum-rag-pipeline.md)**, which excluded "multiple
LLM providers" from the MVP without naming the one provider it assumed.

## Context

Three provider stories coexisted in the tree, none of them decided:

| Where | Provider |
|---|---|
| `apps/ai/services/llm_generator.py` | Anthropic — the path that actually ran |
| `requirements/base.txt` | `openai>=1.30`, commented "GPT-4.1-mini LLM inference" |
| `ai/infrastructure/openai_adapter.py` | OpenAI, in the gateway that does not boot |
| IR-131's description | "Groq or OpenRouter" |

Worse, `anthropic` was never declared as a dependency. It is imported inside a
`try`, so the generative path logged *"anthropic SDK not installed; falling
back to extractive synthesis"* and silently degraded in every environment —
the same shape as `REDIS_URL` being set and read by nothing (IR-132) and
`DOCLING_SERVE_MAX_SYNC_WAIT` being unset and binding (IR-249). Configuration
claiming one thing while the code did another.

Choosing a vendor is therefore not the whole problem. The tree also had an
`if/else` provider factory that fell through to a mock adapter on an
unrecognised name, which is the failure mode [ADR-013](013-chunk-level-rag-pipeline.md)'s
chunker registry was explicitly built to avoid.

## Decision

**Adapters key on the wire protocol, not on the vendor.**

OpenAI, Groq, OpenRouter, Together, Fireworks, DeepInfra, vLLM and Ollama all
expose the same chat-completions format. They differ in a base URL, an API key
and a model string. One adapter per vendor would be five near-identical files
that drift; one adapter per *protocol* makes switching vendors a `.env` change
with no new code.

The two sanctioned vendors, and what each is good for:

| Vendor | Why |
|---|---|
| **Groq** | Free tier, generous limits, and genuinely fast — latency is its selling point |
| **OpenRouter** | One key across dozens of models; a `:free` lane at no cost and pass-through pricing on the paid one |

*Originally this table bound Groq to development and OpenRouter to production —
one provider per environment. The §Amendment below replaces that binding; the
vendors and their reasons are unchanged.*

`OpenAICompatibleAdapter` is the only `LLMProvider` adapter IRIS needs. It
takes `base_url`, `api_key` and `model`, and `openai>=1.30` — already declared
— is its client.

**An unrecognised configuration raises.** No silent fall-through to a mock or
a local adapter: a typo in a model or base URL must fail loudly, for the same
reason the chunker registry refuses an unknown strategy id.

## Amendment — 2026-09-28 (IR-376): the vendor is chosen per task, not per environment

**What this supersedes.** The original text said *"This is one provider per
environment, selected by configuration"* and bound Groq to development and
OpenRouter to production. That sentence and that binding are superseded. The
rule is now:

> **One adapter per protocol. The vendor and model are chosen per Inference
> task.**

So `resolve` may sit on Groq while `answer` uses OpenRouter, in the same
deployment, at the same time.

**Why.** The environment binding assumed every generative call in IRIS is the
same kind of call. It is not. IRIS has distinct Inference tasks with different
shapes — a short, latency-critical rewrite of a follow-up question is not the
same work as synthesising a cited answer over a dozen passages, and the model
that is right for one is wrong for the other. Latency matters most where a
person is waiting on a step they did not ask for; quality matters most on the
output they read. Binding both to one vendor forces a single compromise on
both, and the only way to tune one was to retune the other.

Nothing about the adapter changes, which is the point of keying on the protocol
rather than the vendor: a per-task vendor is a per-task `base_url`, `api_key`
and `model`, resolved from configuration, through the same
`OpenAICompatibleAdapter`. No new adapter, no new dependency, no new wire
format.

**What is still refused.**

* **No vendor outside Groq and OpenRouter.** Per-task choice selects among the
  sanctioned pair. It is not an opening for a third account.
* **No cross-vendor failover.** A task's vendor is its vendor. When that vendor
  is down, the task degrades per ADR-008 — it does not silently re-run against
  the other one. Two vendors being configured for two *different* tasks does
  not make either a standby for the other.
* **No silent fall-through.** An unrecognised task, vendor, base URL or model
  still raises. Per-task configuration multiplies the number of things that can
  be mistyped, which makes the original loud-failure rule more important, not
  less.
* **The disclosure gate is unchanged.** It decides what may reach any vendor,
  per task or not.

**Consequence.** Configuration grows from one provider triple to one per task,
and a deployment that configures none of them must still start and degrade
honestly rather than boot into a broken generative path. The task set itself is
closed and defined outside this ADR — see IR-375 (*Spec: Inference tasks and
Profiles*) and IR-378 (*C · Profile and the closed Inference task set*).

## Amendment — 2026-10-08 (IR-482): an evaluation-only Decisions adapter

OpenRouter also serves a **Decisions API** (`POST https://openrouter.ai/api/alpha/decisions`)
that answers a typed question about a state with a probability and no text.
It is not the chat endpoint, so `OpenAICompatibleAdapter` cannot reach it, and
it generates nothing, so it does not fit `LLMProvider` or the closed Inference
task set above. This amendment permits one narrow exception:

* **A separate adapter**, `apps/ai/providers/openrouter_decisions.py`, behind a
  small `DecisionModel` port that returns a probability. It reuses only the
  OpenRouter key an Inference task already holds; no new setting.
* **Pinned to `typesafe/jev-1.13`.** The `~typesafe/jev-latest` alias is
  refused at construction, so a run is reproducible. The dated build the vendor
  actually served is recorded in each run file.
* **Evaluation only.** `manage.py eval_evidence --decision-mode jev-noul` is the
  sole caller. Nothing on a reader's path, the shadow pilot or the answer path
  constructs it, and it adds no Inference task.
* **The endpoint is alpha** (the path says so) and may change without notice.
* **Retention, training and rate-limit terms are unverified.** OpenRouter's
  docs state none for this endpoint. Live runs are therefore limited to the
  public arXiv proxy question set, and every run file says the terms are
  unverified. Reader questions, private documents and sensitive school data are
  out of scope until the terms are recorded here.
* **Removal or deferral.** If Jev is not selected for the evidence decision, or
  the terms cannot be verified, delete the adapter, the port and the mode. They
  are additive and nothing else depends on them. The ADR-035 detector stays an
  independent safeguard throughout: a probability can never override it.

## Amendment — 2026-10-10 (IR-487): a production decision adapter, behind an approval switch

**Status: Proposed, not accepted.** Drafted by an AI agent from
[proposal 12](../architecture-review/12-jev-first-evidence-routing-proposal.md)
§8 and the owner decisions on IR-485 (2026-10-10). **Approver: Jive Tyler
Revalde.** Until a person accepts it, the IR-482 amendment above stands, and the
adapter stays evaluation-only.

**Evidence, and what is exploratory.** Jev's latency and behaviour come from
four proxy-set runs (`20261008-110112`, `-110304`, `-110450`, `-110632`):
0.89–0.93 s mean, and 0 failures in 113 × 4 calls (proposal 12 §13 and §5.3).
That is one labeller and arXiv questions, so it is exploratory. **The
endpoint's rate limit and its behaviour under reader traffic are not measured.**
The vendor facts below are read from published policies, not from contracts.

**What this supersedes.** The IR-482 bullet *"Evaluation only. … Nothing on a
reader's path, the shadow pilot or the answer path constructs it"*. Also
ADR-035 §2's *"ADR-036 is not amended"*, which assumed the decision would reuse
the `answer` task with no other adapter.

**The rule.**

* **A decision provider is constructed on a reader's path, in shadow or in
  `on`, only when its own approval setting is on.** There is one switch per
  provider (Jev via OpenRouter Decisions, and the LLM route label's vendor). It
  defaults off. When it is off, the decision **fails closed to evidence**, sends
  nothing to that vendor and records the skip. The setting's name is IR-490's to
  choose. **This amendment proposes no key.**
* **An approval is a person's act, recorded in ADR-035 §11's per-vendor table.**
  It is never inferred from a configured API key.
* **Pinning is unchanged.** `typesafe/jev-1.13` stays pinned and the
  `~typesafe/jev-latest` alias is still refused. A served build that differs
  from the pin is a failure, and it routes to evidence.
* **Still not an Inference task.** The Decisions adapter generates no text and
  stays outside the closed task set. The LLM route label is a `generate` call:
  it runs on the `answer` Profile today. Whether it gets its own task is open
  and is not decided here.
* **The endpoint is still alpha.** A shape change is a malformed reply, and it
  routes to evidence. The rate limit is unstated.

**Data handling. This replaces "unverified" with what is recorded.** The
owner's rule (IR-485 #2, 2026-10-10): **retention is acceptable provided no model
trains on the data**.

* **`provider.zdr` is not required.** `provider.data_collection: "deny"` already
  excludes providers that train on inputs, and it is sufficient under the rule.
  The chat dialect sends it today (`providers/dialects.py`).
* **Hosting.** Endpoints must be hosted in the US or the EU, and no endpoint may
  be hosted in China. China-origin models served from US or EU hosts are
  acceptable (IR-485 #6). This excludes DeepSeek's first-party endpoint. Where a
  task's model is offered by a China-hosted provider, **the request pins
  providers through OpenRouter's provider-routing object** (an allow-list or
  ignore-list of providers) so that OpenRouter cannot route there. The exact
  fields, and whether fallbacks respect them, are **unverified**. They are
  checked in IR-489 before any answer request depends on them.
* **Recorded facts.**

  | Party | Recorded | Source |
  |---|---|---|
  | TypeSafe | No training or fine-tuning on input. No disclosure except to service providers. Retention unspecified. US-hosted. **Accepted by the owner.** | typesafe.ai privacy policy, updated 2025-11-19, read 2026-10-08 |
  | OpenRouter | Does not train on inputs or outputs. Cannot control training by the model providers behind it. Retention "as long as reasonably necessary", with no period. May re-identify stored inputs for debugging. A data-processing agreement is available | openrouter.ai/privacy, updated 2026-08-31, read 2026-10-10 |

* **Still unverified:** OpenRouter's retention period. Whether the Decisions
  endpoint honours a `provider` object; the adapter deliberately sends only
  `model`, `state` and `questions`. TypeSafe's sub-processors. Groq's own
  no-training terms, which stop mattering once IRIS migrates its tasks to
  OpenRouter (owner direction, IR-485). **No data-processing agreement has been
  requested.**

**Groq stays a sanctioned vendor** until a person removes it. The migration to
OpenRouter is a direction, not a decision recorded in this file.

**Recorded contradiction.** The IR-482 amendment above was written by an agent.
Its ticket asked for a reviewed amendment, and no review is recorded in this
file. **Owner: Jive Tyler Revalde.** Accepting this amendment does not
retroactively review that one.

## Amendment — 2026-10-11 (IR-499): three Inference tasks, and Jev approved for routing and screening

**Status: Proposed, not accepted.** Drafted by an AI agent. The decision is in [ADR-038](038-bounded-research-lane-for-ask-iris.md) §8 and §9. Until a person accepts it, the amendments above stand.

* **The closed task set grows from four to seven:** `answer`, `resolve`, `summary`, `describe_figure` plus `plan` (the research planner, which needs the tool-calling port), `screen` (per-record include or exclude judgements) and `route` (the LLM backup to Jev's routing). Each gets a Profile as the 2026-09-28 amendment requires. `route` **inherits `resolve`'s model by default**. `plan` and `screen` models are chosen by IR-502 and IR-501. A task with no configured model reports unavailable.
* **This supersedes the 2026-10-10 (IR-487) amendment for two uses only:** Jev, reached through OpenRouter's Decisions API, is approved for **routing and for screening the reader's question**. Its other proposed use, the evidence decision, stays Proposed and is not decided here.
* **The rule is unchanged:** an approval is a person's act and is never inferred from an API key. The approval switch **defaults to off**, and when it is off or Jev fails, routing falls to the `route` backup. `typesafe/jev-1.13` stays pinned and the `~typesafe/jev-latest` alias stays refused.
* **Recorded terms:** no training or fine-tuning on input (accepted by the owner on IR-485), retention unstated, US-hosted, alpha endpoint with an unmeasured rate limit.
* **The `route` backup's vendor must meet the same no-training rule.** Groq has no terms recorded in the repository and is not approved for it.
* **The Decisions adapter stays outside the Inference task set,** because it writes no text.

## Consequences

**Good.** Switching Groq to OpenRouter, or either to a self-hosted vLLM, is
configuration. The second real adapter is what finally validates the
`LLMProvider` port — until now there was one real implementation and one
placeholder returning `f"Mock response from LocalLLMProvider"`, so nothing had
ever proven the port was the right shape.

**Cost.** Development is free on Groq's tier. Production on OpenRouter's
`:free` lane is also free, with a paid lane available without re-integrating.

**Accepted risk.** Open-weight models on Groq are not frontier models, and
answer quality will differ from a hosted frontier model. That is a
measurement, not a guess: IR-133's harness compares configurations, and the
comparison is a `.env` change because of this ADR.

**Unchanged.** The disclosure gate ([ADR-015](015-voyage-embedding-and-reranking.md),
IR-127) still decides what may reach any of these vendors. Protocol
compatibility makes vendors interchangeable; it does not make transmission
permissible.

## Alternatives Considered

**Anthropic, as the code already did.** Rejected. Not recorded in any ADR, not
declared as a dependency, and not what the team wants. A vendor chosen by an
import statement is not a decision.

**One adapter per vendor.** Rejected. Five files with one real difference
between them, which drift, and each of which needs its own tests for behaviour
the protocol already guarantees.

**Keeping OpenAI directly.** Not rejected — it is covered. The OpenAI SDK
pointed at OpenAI's own base URL is one configuration of the same adapter.

## Related

`docs/rag_third_party_services_architecture.md` §2 · IR-131 (E · Grounded
answers with citations) · ADR-008 (degradation, unchanged) · ADR-015 (the
disclosure gate that governs transmission)
