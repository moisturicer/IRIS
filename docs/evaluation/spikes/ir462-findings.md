# IR-462 finding: native tool call vs structured route label

Spike under IR-456 (the evidence decision). Throwaway code; the deliverable is this note. Run 2026-10-06 against the configured model, `openai/gpt-oss-120b` on Groq, temperature 0.5, buffered (never streamed).

Raw per-call data: `ir462_runs.json`. Questions: `ir462_questions.json` (44, 22 need passages, 22 do not; one labeller). Re-derive every figure with `python scripts/spikes/ir462_report.py docs/evaluation/spikes/ir462_runs.json`.

This compares **how the model is asked**. The agreed design stays a union of a deterministic detector and a model decision.

## Recommendation

**Go on the structured route protocol. No-go on native tool calling, for now.**

The measurement does not separate the two on reliability or accuracy, so the choice falls to cost. Tool calling needs the provider port widened to carry tools and tool turns, which ADR-028 rejected because it weakens the `system`/`user` separation. The route label needs no port change and is about 0.2 s faster. Nothing measured here pays for the wider port.

Revisit tool calling only if the shadow pilot shows the route label's missed searches (below) are costing real answers that the deterministic detector does not already catch.

## Results (3 runs x 44 questions per configuration)

"Parsed accuracy" excludes calls lost to Groq rate limiting (see caveats); "all" counts them as wrong.

| Mechanism | Reasoning | Run 1 / 2 / 3 accuracy (all) | Run 1 / 2 / 3 (parsed) | Missed search | Over-search | Latency mean / p95 |
|---|---|---|---|---|---|---|
| route | medium (configured) | .909 / .932 / .932 | .952 / .976 / .976 | 6/66 | 4/66 | 0.51 / 0.66 s |
| route | low | .864 / .909 / .909 | .950 / .952 / .952 | 7/66 | 7/66 | 0.46 / 0.66 s |
| tool | medium (configured) | .932 / .909 / .955 | 1.0 / 1.0 / 1.0 | 3/66 | 6/66 | 0.72 / 1.62 s |
| tool | low | .886 / .909 / .932 | 1.0 / .976 / 1.0 | 5/66 | 7/66 | 0.65 / 1.45 s |

Missed search = a question that needed passages routed to "answer" (the costly error: an ungrounded reply). Over-search = a pointless retrieval.

Read with care: 44 questions, so one question is 2.3 points, and the gap between mechanisms is a handful of questions. Tool calling looks slightly better on missed searches (3 vs 6 of 66) and route slightly better on speed. Neither difference is established. Both sit far above the ~77% tool-calling figure ADR-028 cited.

Decisions flipped between runs on 6-11 of 44 questions in every configuration, so one run proves nothing, as the ticket expected. `s02` ("what does the training loop do with a problem the model has not managed to solve yet?") was routed to "answer" in all three route runs: a mechanism question phrased with no repository vocabulary. That is the case the deterministic detector cannot catch either.

## Failure modes (counted, per configuration of 132 calls)

| Mode | tool | route |
|---|---|---|
| Malformed output / bad JSON arguments | 0 | 0 |
| Arguments supplied against the no-argument schema | **62 of 63 search calls (medium), 62 of 62 (low)** | n/a |
| Several tool calls | 0 | n/a |
| Empty completion | 0 | 0 |
| Text and tool call together | 0 | 0 |
| Label wrapped in extra text | n/a | 0 |
| Wrong tool name | 0 | 0 |
| Timeout (30 s) | 0 | 0 |
| Vendor rate limit (HTTP 429, six retries exhausted) | 9 medium, 11 low | 6 medium, 8 low |

- **Arguments against a no-argument schema is not an edge case, it is the norm.** Every search call carried a model-written `query`, for example `{"query":"earlier work not knowing exactly where the trade-off frontier sits"}`. The decision stayed readable, so it is harmless if the parser ignores the argument, and it is a free record of what the model thought it was looking for. A parser that rejects it would fail nearly every search.
- Nothing else occurred in 528 calls, so the fallback for those modes is untested rather than needed. 0 observed is not "cannot happen" at this sample size.

## Reasoning setting

Reasoning did not materially move latency or tool-call reliability. Dropping from medium to low saved about 0.05 s (route) and 0.07 s (tool) on a half-second call, and mean reasoning tokens fell from ~50 to ~10. Accuracy was 1-3 points lower at low, which is within the noise above. `gpt-oss` has no "off", so low was the floor tested.

**Statement:** reuse the existing answer task unchanged. No per-call reasoning override is justified by this data, and no new Inference task is needed.

## Caveats

- **34 of 528 calls (6.4%) were lost to Groq 429s** after six backoff retries, with four workers in parallel. That is the account's rate limit, not model behaviour, but it means each run has 39-42 of 44 usable results. A production decision call must handle a rate limit as a normal outcome.
- One labeller, 44 questions; `edge` labels are arguable. The questions are synthetic, not drawn from real users.
- Prompts were written once and not tuned for either mechanism. A tuned route prompt may close the missed-search gap.
- Parallel tool use is unsupported on this model (per ADR-028); irrelevant for one no-argument tool.

## Follow-ups

- The route-label default does not need IR-465 (provider carries a tool-calling decision). That ticket should be re-scoped or deferred by whoever owns IR-456.
- Missed searches on vocabulary-free mechanism questions (`s02`) are the thing to watch in the shadow pilot.
