# Answer-model comparison (IR-489)

Tier: proxy. Snapshot: `0c0cf40471cc378bc3a28e99fd27d01b1e2f70a60bc5c3e816162d58f8711356`.
No production model is selected. Scores are judge ratings on frozen prompts.

| Model | History target | Answered / planned | Judged | Correctness | Claim support | Citation support | Empty rate | Length rate | Answer + judge cost (known) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| anthropic/claude-haiku-5.5 | 0 | 4 / 4 | 4 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | $0.0000 |
| openai/gpt-6-luna | 0 | 4 / 4 | 4 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | $0.0000 |
| deepseek/deepseek-v4.1-flash | 0 | 4 / 4 | 4 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | $0.0000 |
| openai/gpt-oss-120b | 0 | 4 / 4 | 4 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | $0.0000 |

Missing usage is unknown, never zero. See JSON coverage counts, raw responses, errors and skips.
Neutral repeated history measures padding sensitivity; it cannot establish that useful history improves answers.
Quality columns are conditional on valid judgements. JSON correctness bounds include answer failures as zero and missing judgements as [0,1].
Judge comparisons may reflect judge preference. Human review is required before a production choice.
