# Formula-heavy paper: 13 GiB VRAM cap

This targeted run used a 35-page, 13.66 MB paper on the RTX 5070 Ti development computer. Every conversion in all three profiles returned the same 35 pages, 597 elements, and 124 formulas, with an identical structural hash. There were no HTTP failures or completeness flags.

| Profile | Measured warm conversion | Difference from starting baseline | Peak container RAM | Peak whole-card GPU increase |
|---|---:|---:|---:|---:|
| 4 CPU / 8 GiB RAM / 8 GiB VRAM, start | 104.450 s | baseline | 5.88 GiB | 5,165 MiB |
| 13 GiB VRAM cap | 102.376 s | −2.0% | 6.14 GiB | 5,572 MiB |
| Baseline, end | 100.717 s | −3.6% | 5.73 GiB | 5,359 MiB |

The 13 GiB setting did not show a credible speedup: its 2.0% difference from the first baseline was smaller than the 3.6% change between the two baselines. The observed whole-card GPU increase was below 6 GiB in every profile, so the 8 GiB baseline tensor cap did not appear binding for this paper. This is one measured warm conversion per profile; the reported p95 is therefore only that same observation. Run more repetitions and papers before changing production limits.

See [manifest.json](manifest.json), [samples.jsonl](samples.jsonl), [resources.jsonl](resources.jsonl), and [summary.csv](summary.csv) for the recorded settings and samples. GPU samples include other processes and cannot isolate Docling's own GPU allocation.
