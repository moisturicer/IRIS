# Docling extraction benchmark

Run: 2026-10-10T04:48:52.875744+00:00

Results are specific to this corpus, host, image, and options.

| Profile | Outcome | Clean / measured | Warm median | Warm p95 | Batch papers/min | Peak RAM MiB | Peak GPU MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline-start | completed | 2 / 2 | 24.245 | 24.245 | 2.695 | 2772.99 | 4889 |
| cpu-12 | completed | 2 / 2 | 22.247 | 22.247 | 2.698 | 3036.16 | 4904 |
| cpu-16 | completed | 2 / 2 | 22.251 | 22.251 | 2.693 | 3213.31 | 5003 |
| ram-12 | completed | 2 / 2 | 20.254 | 20.254 | 2.696 | 3144.7 | 5051 |
| ram-14 | completed | 2 / 2 | 22.239 | 22.239 | 2.697 | 3053.57 | 4975 |
| vram-12 | completed | 2 / 2 | 22.235 | 22.235 | 2.695 | 3164.16 | 5162 |
| vram-14 | skipped | 0 / 0 | — | — | — | — | — |
| baseline-end | completed | 2 / 2 | 22.253 | 22.253 | 2.475 | 3201.02 | 4974 |

Failures and completeness differences are in samples.jsonl. GPU memory is the whole-card reading, including other processes. CPU and RAM peaks are sampled, so short spikes may be missed.
Sampling interval: 1.0 s. Client/server timeout: 3600 s.
