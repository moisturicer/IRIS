# Docling extraction benchmark

Run: 2026-10-10T05:30:10.624590+00:00

Results are specific to this corpus, host, image, and options.

| Profile | Outcome | Clean / measured | Failed | Incomplete | Changed | Warm median | vs baseline | Warm p95 | Batch papers/min | Peak CPU % | Peak RAM MiB | Peak GPU delta MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline-start | completed | 2 / 2 | 0 | 0 | 0 | 22.251 | +0.0% | 22.251 | 2.475 | 104.71 | 3069.95 | 3165 |
| cpu-only-4 | completed | 0 / 2 | 0 | 0 | 2 | — | — | — | — | 403.38 | 3116.03 | 0 |
| cpu-only-8 | completed | 0 / 2 | 0 | 0 | 2 | — | — | — | — | 762.34 | 2834.43 | 0 |
| baseline-end | completed | 2 / 2 | 0 | 0 | 0 | 26.245 | +17.9% | 26.245 | 2.272 | 117.56 | 3151.87 | 2989 |

Failures and completeness differences are in samples.jsonl. GPU memory is the whole-card reading, including other processes. CPU and RAM peaks are sampled, so short spikes may be missed.
Single-paper, single-repeat runs are pilot measurements; their p95 is not a stable estimate. A limit above observed peak use is nonbinding.
Sampling interval: 1.0 s. Client/server timeout: 3600 s.
