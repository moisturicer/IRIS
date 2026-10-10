# Docling extraction benchmark

Run: 2026-10-10T05:04:37.173103+00:00

Results are specific to this corpus, host, image, and options.

| Profile | Outcome | Clean / measured | Failed | Incomplete | Warm median | vs baseline | Warm p95 | Batch papers/min | Peak CPU % | Peak RAM MiB | Peak GPU delta MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline-start | completed | 2 / 2 | 0 | 0 | 104.45 | +0.0% | 104.45 | 0.623 | 228.61 | 6019.07 | 5165 |
| vram-13 | completed | 2 / 2 | 0 | 0 | 102.376 | -2.0% | 102.376 | 0.605 | 244.08 | 6288.38 | 5572 |
| baseline-end | completed | 2 / 2 | 0 | 0 | 100.717 | -3.6% | 100.717 | 0.586 | 266.77 | 5868.54 | 5359 |

Failures and completeness differences are in samples.jsonl. GPU memory is the whole-card reading, including other processes. CPU and RAM peaks are sampled, so short spikes may be missed.
Sampling interval: 1.0 s. Client/server timeout: 3600 s.
