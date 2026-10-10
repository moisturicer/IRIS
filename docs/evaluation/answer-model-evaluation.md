# Answer-model evaluation — IR-489

Status: offline implementation; paid comparison pending owner approval. No
production model has been selected. This work lives on
`feature/IR-489-answer-model-evaluation`, independently of IR-486.

## Experiment

Capture the final disclosable passages once, after visibility filtering and
source selection. The resulting snapshot stores the exact user prompt,
question, reference answer, source count, tier, code revision and question-set
digest. Each candidate receives the same system and user prompts, twice in
each arm. A capture needs labelled `reference` answers or expected refusals;
the existing retrieval-only proxy labels do not provide those answers.

The candidate maker is recorded separately from the OpenRouter transport.
Opus 5.5 judges OpenAI and DeepSeek candidates; GPT-6 Sol judges Anthropic.
Judge instructions request correctness, claim support, citation support and
reasoning leakage, each with an explanation. Judge replies are strictly
validated; malformed replies remain missing observations. Their raw responses
and usage are retained, so judge failures can be inspected.

Deterministic diagnostics retain empty content, `length` finishes, invalid
citation indices, citation-format drift and `<think>` leakage before citation
normalization. Raw separate reasoning never enters the answer or judge input.
Requests use the recorded build identifier rather than a moving alias.
Reports include actual response model/provider/id, input/output/reasoning token
usage, provider-reported cost and wall-clock latency. Missing usage is unknown,
not zero. Output tokens already include reasoning tokens: do not bill them
twice. Errors and skipped arms have explicit denominators.

History arms target 0, 25k, 50k, 100k and 150k tokens using the repository's
SHA-256-pinned Qwen tokenizer, without the production history margin.
Budget checks apply a fixed 1.15 margin, recorded with the tokenizer hash. A case may provide `history_padding` containing
prior Q/A; otherwise neutral invented exchanges are repeated. The latter is
a padding stress test and cannot establish that useful history helps. Supply
labelled conversation histories for that conclusion. Inputs exceeding the
recorded context window are skipped; the 150k arm cannot fit the 131072-token
control. No production history budget is raised.

## Data controls

`LLM_<TASK>_PROVIDER_ONLY` carries comma-separated OpenRouter provider slugs.
The request sends `provider.only` beside `provider.data_collection: deny`.
Pins are task-specific and never inherited from another task. A pin configured
on Groq refuses startup. OpenRouter answers require a nonempty pin at startup. Other tasks may leave
their pins empty for routing constrained only by the no-training policy.
ZDR is not requested because IR-485 permits retention when training is denied.

An allow-list is only as accurate as the hosting evidence behind its entries.
The example manifest proposes `fireworks/us` for DeepSeek and names the other
providers explicitly. Verify their US/EU hosting before paid runs; a company's
headquarters alone does not prove endpoint location. Base slugs can match
multiple regional variants. The harness sends one model per request and has
no model fallback. Whether the production `models` fallback array preserves
the provider pin remains unverified and is not claimed by request-shape tests.

GPT-6 Luna receives `max_completion_tokens` when a completion cap is supplied.
The control and other candidates receive `max_tokens`. Both caps cover visible
output and reasoning, so empty answers with `length` are possible and measured.

## Commands checked offline

From `backend`, this prints the plan and estimated cost without opening a
vendor client or writing an answer report:

```powershell
python manage.py eval_answers --snapshot apps/ai/evaluation/fixtures/answer_snapshot.json --manifest ../docs/evaluation/answer-model-manifest.json --out ../docs/evaluation/runs/ir489-real.json
python manage.py capture_answer_snapshot --help
```

The capture command accepts `--questions`, `--user`, `--out` and
`--max-sources`; it validates references offline by default. `--live` permits
retrieval calls. Capturing real retrieval spends embedding/reranking credits;
it has not been run in this implementation. Live answering requires `--live`, recorded US/EU hosting evidence for each
provider pin, and a manifest run cap, and refuses an existing output. Each completion is
checkpointed to JSON; a finished run also writes a Markdown comparison.
Synthetic output is recorded in `runs/ir489-offline-answers.json` and `.md`.
It demonstrates the instrument, not candidate quality.

## Prices and proposed paid probe

Checked against the OpenRouter model and endpoint catalogue on 2026-10-10.
The manifest uses uncached prices and maximum recorded context tiers to make
the estimate conservative. All figures are USD per million tokens.

| Model | Input | Output, including reasoning | Proposed provider |
|---|---:|---:|---|
| Haiku 5.5 | 0.50 | 2.50 | anthropic |
| GPT-6 Luna | 0.20 | 0.75 | openai |
| DeepSeek V4.1 Flash | 0.45 | 1.80 | fireworks/us |
| gpt-oss-120b control | 0.15 | 0.60 | groq |
| Opus 5.5 judge | 4.00 | 20.00 | anthropic |
| GPT-6 Sol judge | 4.00 | 15.00 | openai |

The two invented fixture cases, all four candidates, five history arms and
two repeats estimate **$33.86**, including judges and full 4096-token output
caps. Four control completions are skipped for context length. This exceeds
the example manifest's $20 cap, so the command refuses a live run with that
manifest. Local token estimates, provider price changes and failed requests
prevent treating this as an exact invoice ceiling. A corpus comparison needs
a separately captured, labelled snapshot and a new estimate before approval.

During a live run, known billed costs are counted; missing cost falls back
to the recorded price estimate. Calls whose projected cost exceeds the run
cap or $1 per answer/judgement pair are stopped or skipped. No credits were
spent on answer generation or retrieval in this implementation.

## Comparison and remaining evidence

The synthetic comparison exercises correct/unsupported answers, empty content,
truncation, malformed judges, context skips and transport failures through
offline tests. It is not a real model ranking. The paid comparison, regional
hosting verification and human assessment of helpful conversation history
remain outstanding. IR-489's real-run acceptance criterion therefore remains
open. The production model choice belongs to the owner.

Primary references: [provider selection](https://openrouter.ai/docs/guides/routing/provider-selection),
[reasoning budgets](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens),
[parameters](https://openrouter.ai/docs/api_reference/parameters),
[model catalogue](https://openrouter.ai/api/v1/models),
and [usage accounting](https://openrouter.ai/docs/guides/administration/usage-accounting).

## Validation evidence — 2026-10-10

194 relevant tests passed: evaluation instrument, dialect request shapes, LLM
contracts, profiles and startup checks including subprocesses. The copied
local environment initially changed default reasoning, temperature and resolver
settings; those overrides were isolated for the clean run and restored
afterward. Both review axes found issues which were corrected: adapter caching
now keys on the full model specification; requests send recorded build IDs;
citation diagnostics share the production grammar; snapshot capture uses public
retrieval/selection interfaces; missing OpenRouter answer pins fail startup;
live evaluation requires hosting evidence; quality bounds expose missing
judgements and failures; history sizing is independent of deployment settings.

Commands exercised: `eval_answers` offline planning, `capture_answer_snapshot
--help`, the synthetic report writer, and the relevant pytest suite. Real
retrieval capture and paid generation were not executed.
