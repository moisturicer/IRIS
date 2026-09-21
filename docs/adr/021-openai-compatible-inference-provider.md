# ADR-021: Groq and OpenRouter behind one OpenAI-compatible adapter

## Status

Accepted — 2026-09-15. Decided by the team; recorded here because
`docs/adr/` is the decision authority and no ADR had ever named an inference
vendor. The reasoning is worked through at length in
[`docs/rag_third_party_services_architecture.md`](../rag_third_party_services_architecture.md)
§2, which this ADR records rather than restates.

**Supersedes the de-facto Anthropic implementation.** `apps/ai/services/llm_generator.py`
called Anthropic, chosen in code rather than in a decision record. **Anthropic
is not used.**

**Does not contradict [ADR-008](008-ai-degradation-to-fts.md).** That ADR
rejected *"a secondary LLM provider for failover"* — two providers live at once
for resilience. This is one provider per environment, selected by
configuration. ADR-008's degraded-mode rule is untouched: when the provider is
unavailable the answer is replaced by an explicit unavailable state and never
by a fabricated one.

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

| Environment | Provider | Why |
|---|---|---|
| **Development** | **Groq** | Free tier, generous limits, and genuinely fast — latency is its selling point |
| **Production** | **OpenRouter** | One key across dozens of models; a `:free` lane at no cost and pass-through pricing on the paid one |

`OpenAICompatibleAdapter` is the only `LLMProvider` adapter IRIS needs. It
takes `base_url`, `api_key` and `model`, and `openai>=1.30` — already declared
— is its client.

**An unrecognised configuration raises.** No silent fall-through to a mock or
a local adapter: a typo in a model or base URL must fail loudly, for the same
reason the chunker registry refuses an unknown strategy id.

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
