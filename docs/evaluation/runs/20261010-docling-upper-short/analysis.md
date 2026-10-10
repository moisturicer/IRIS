# Upper-limit pilot: 5-page paper

This was a one-paper, one-warm-repeat pilot on the RTX 5070 Ti development computer. Every completed profile extracted the same 5 pages and 118 elements; there were no failed or incomplete measured conversions. The baseline's warm conversion was 24.245 s at the start and 22.253 s at the end, an 8.2% drift. With one warm observation per profile, a p95 is not informative.

| Profile | Warm conversion | Difference from starting baseline | Peak container RAM |
|---|---:|---:|---:|
| 4 CPU / 8 GiB RAM / 8 GiB VRAM, start | 24.245 s | baseline | 2.71 GiB |
| 12 CPU | 22.247 s | −8.2% | 2.96 GiB |
| 16 CPU | 22.251 s | −8.2% | 3.14 GiB |
| 12 GiB RAM | 20.254 s | −16.5% | 3.07 GiB |
| 14 GiB RAM | 22.239 s | −8.3% | 2.98 GiB |
| 12 GiB VRAM | 22.235 s | −8.3% | 3.09 GiB |
| 14 GiB VRAM | skipped | insufficient free VRAM for cap plus CUDA context | — |
| Baseline, end | 22.253 s | −8.2% | 3.13 GiB |

The higher CPU, RAM and VRAM limits produced no credible speedup for this small paper. The apparent improvements are on the scale of baseline drift, and sampled CPU use never reached even 1.3 cores. Actual container RAM stayed below 3.2 GiB, so the 8 GiB baseline limit was not binding. The 14 GiB VRAM cap could not be safely tried while desktop programs occupied the remaining card memory. These are observations for this paper and run, not general sizing conclusions; the formula-heavy and CPU-only runs provide different workloads.

See [manifest.json](manifest.json), [samples.jsonl](samples.jsonl), [resources.jsonl](resources.jsonl), and [summary.csv](summary.csv) for raw evidence and exact settings. GPU samples measure the whole card, including other programs.
