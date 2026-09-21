# ADR-028: Ask IRIS is a pipeline, not a tool-calling agent

## Status

**Accepted** — 2026-09-19.

**Does not supersede anything.** It records a decision *not* to adopt an architecture, so that it is not re-proposed without new evidence.

**Constrains [ADR-026](026-conversational-retrieval-and-memory.md) and [ADR-027](027-corpus-level-questions.md)**, both of which specify explicit mechanisms — question resolution, routing, conditional decomposition — that a tool-calling agent would have replaced.

## Context

Ask IRIS is a pipeline. The caller decides what to retrieve, applies the disclosure gate, assembles a numbered prompt, and parses citations back against the list it supplied. `LLMProvider` is deliberately `generate(system, user) -> str` — text in, text out.

The obvious modern alternative is to expose retrieval as tools — *search passages*, *get landscape* — and let the model decide which to call, with what arguments, and whether to call again. That would collapse three mechanisms specified across ADR-026 and ADR-027 into one: routing becomes tool choice, ADR-026's **Resolved question** becomes the tool's argument, and sub-query decomposition becomes repeated calls.

The consolidation is genuine and appealing. **It was proposed, researched, and rejected**; this ADR records why, because it is the kind of proposal that recurs.

### What the evidence showed

| Finding | Source |
|---|---|
| Agentic pipelines achieve **substantially better answer accuracy** than non-agentic ones on document QA | agentic-vs-pipeline RAG comparisons |
| …but at the cost of **lower page-localisation precision** — agentic rephrasing "retrieves relevant but different pages" | same |
| **"The largest performance gains come from improving retrieval, not from changing the LLM or adding agentic mechanisms"** | same |
| Roughly **10× cost and +5s latency** for the same job | same |
| Tool-calling accuracy on BFCL-v2: **77.30%** (Llama-3.3-70B), 76.63% (Qwen3-Coder-30B), 55.14% (a tool-specialised 2.5B), **12.03%** (OLMo-3-7B) | BFCL-v2 results |
| Agentic RAG **compounds** indirect prompt-injection exposure: "each iterative retrieval step offers new opportunities to encounter injected content" | SoK on agentic RAG security |
| "Agentic systems don't fail less — they just fail in harder-to-debug ways" | same |
| `openai/gpt-oss-120b`, the configured model, **does not support parallel tool use** | Groq tool-use documentation |

## Decision

**Ask IRIS stays a pipeline. Retrieval is not exposed to the model as tools, and the model does not decide what to fetch.**

`LLMProvider` stays `generate(system, user) -> str`. The answer module keeps control of what reaches the prompt.

Four reasons, in order of weight.

### 1. The measured trade spends exactly what IRIS is built to provide

The agentic gain is answer accuracy; the agentic cost is page precision. IRIS has spent IR-89 A–H, IR-107, IR-113 and IR-245 producing regions and page coordinates, and IR-284 and [ADR-025](025-figures-and-formulas-in-extraction.md) exist so a reader lands on the page that supports a claim.

Buying fluency by giving up page precision is the wrong trade **in this product specifically**. In a system for IP disclosures, "sounded confident, pointed at the wrong page" is worse than a plainer answer that cites correctly.

### 2. Retrieval is the bottleneck, and IRIS's retrieval does not work

The evidence is explicit that gains come from improving retrieval rather than from adding agentic orchestration. Ask IRIS currently ranks whole Records by keyword match over titles and abstracts, and no chunk vector has ever been computed. An agentic loop over that would be a control loop driving a module that returns nothing useful.

### 3. A tool-calling router is less accurate than the deterministic one it would replace

Best measured tool-calling accuracy is ~77% — roughly one call in four wrong. Matching the word "trending" is exact on the phrasings it covers. ADR-027's routing is patterns first, then a classifier, then a **visible and overridable** decision; replacing that with tool choice trades an exact mechanism for a probabilistic one.

**This also settles the small-model question.** Small models do classification well — it is narrow. Tool selection plus argument composition is reasoning, and it collapses: 12.03% for a 7B model. A small model is the wrong lever for tool calling specifically.

### 4. It would make the contribution unmeasurable

[ADR-023](023-retrieval-quality-evaluation.md) measures retrieval quality **with and without each technique**. Once routing, resolution and decomposition collapse into one model decision, there is nothing left to switch off and compare. The architecture that is easiest to describe becomes the hardest to evaluate — and RAG is thesis-critical.

It also weakens two protections. `LLMProvider`'s split `system`/`user` arguments exist so retrieved passages do not look like something the asker said, "which is how a prompt injection sitting in an uploaded document ends up outranking the system prompt." Tool calling needs a message list and tool-result turns, weakening that separation at the moment the research says agentic retrieval *compounds* injection exposure. And ADR-027's "the Lens computes, the model reports" moves from enforced by prompt assembly to merely requested in an instruction.

### What is kept from the idea

Tool calling's transferable benefit is that **the tool's argument is a visible record of what the system decided to look for**. IRIS already has that, twice, without the architecture: ADR-026's Resolved question is stored and shown, and ADR-027's routing decision is shown and overridable.

## Alternatives Considered

**Full agentic loop.** Rejected on all four grounds above.

**Tool calling for routing only**, keeping the pipeline. Rejected as the worst of both: it pays the full cost of widening the port and weakening the injection separation, to buy a ~77%-accurate router, while keeping every mechanism the full version would have removed.

**Tool calling with a small model**, to limit cost. Rejected — this is where small models are weakest, not strongest.

**Switching to a model with parallel tool use** (`llama-3.3-70b-versatile`, `qwen3.6-27b`) to recover the "call two tools at once" argument. Not pursued: it makes the proposal possible rather than advisable, and none of reasons 1, 2 or 4 change.

## Decision Rationale

The honest summary is that tool calling is **feasible and not especially complex** — this is not a rejection on difficulty. It is a rejection on fit. Every reason above is specific to IRIS: what it is for, what state its retrieval is in, and what it must be able to measure.

## Consequences

- ADR-026's Resolved question and ADR-027's routing stay as explicit, separately switchable mechanisms, and IR-296 stands as written.
- `LLMProvider` stays narrow; prompt assembly stays in the domain where it is testable without a vendor.
- More mechanisms to build than the agentic version would need. That cost is accepted in exchange for each being independently testable and switchable.
- Multi-hop questions are served by ADR-026's conditional decomposition rather than by a model calling a tool twice — weaker, and bounded.

## Revisit when

**All three hold:**

1. IR-283 is live, so retrieval is genuinely chunk-level.
2. ADR-023's recall harness exists and has run against a real corpus (IR-278).
3. A measured comparison on **that corpus** shows an agentic loop beating the pipeline — and specifically shows whether the page-precision loss appears in this data or not.

That is a measurement, not an argument, and it is the only thing that should overturn this.

One fact worth carrying forward so it is not rediscovered expensively: **parallel tool use requires a different model.** `gpt-oss-120b` cannot do it.

## MVP Impact

None. Records a decision not to change course.

## SaaS Impact

None.

## Security Impact

Positive. Keeps the `system`/`user` separation that resists prompt injection from uploaded documents, and avoids the compounded injection exposure of iterative agentic retrieval. Note that IRIS's tools would have been read-only and visibility-filtered, so the blast radius was bounded — this is a decision about erosion of a protection, not about an open hole.

## Deployment Impact

None.

## Research Impact

Keeping the techniques separable is what makes ADR-023's per-technique comparison possible, which is the difference between a measurable contribution and a list of features. Recording a researched decision *not* to adopt a popular architecture, with the evidence, is itself defensible engineering practice.

## Related Requirements

FR-M4 — stable label only, per the frozen-SRS rule.

## Related Tasks

IR-283, IR-284 (the retrieval and citation work this protects), IR-296 (question resolution, which an agent would have replaced), IR-278 and ADR-023 (the corpus and harness that gate any revisit).
