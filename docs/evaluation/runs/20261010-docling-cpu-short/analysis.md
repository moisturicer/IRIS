# CPU-only reference: 5-page paper

This one-paper pilot bracketed two CPU-only profiles with the GPU baseline on the RTX 5070 Ti development computer. Each conversion returned 5 pages, 118 elements, and 9 formulas without an HTTP failure. The CPU-only output had the same content hash at both CPU limits, but that hash differed from the GPU baseline despite matching element counts. The benchmark therefore flagged both CPU-only measured conversions as `structure_changed` and excluded them from clean latency and throughput aggregates. The raw timings below are useful for capacity planning, but the text difference needs inspection before treating CPU and GPU extraction as equivalent.

| Profile | Raw measured warm time | Peak container CPU | Peak container RAM | Measured result |
|---|---:|---:|---:|---|
| GPU baseline, start | 22.251 s | 105% | 3,070 MiB | clean |
| CPU-only, 4 CPU / 6 GiB RAM | 98.280 s | 403% | 3,116 MiB | content hash changed |
| CPU-only, 8 CPU / 12 GiB RAM | 98.341 s | 762% | 2,834 MiB | content hash changed |
| GPU baseline, end | 26.245 s | 118% | 3,152 MiB | clean |

The 8-core limit did not improve the measured warm conversion over the 4-core limit for this paper. The GPU baseline slowed by 17.9% between the start and end of this run, so the numbers should not be used as a stable cross-variant speed ratio. There is only one measured warm pass per profile, making p95 uninformative.

See [manifest.json](manifest.json), [samples.jsonl](samples.jsonl), [resources.jsonl](resources.jsonl), and [summary.csv](summary.csv) for exact settings, structural hashes, and raw evidence. The run contains no PDF bytes or extracted text, so it cannot identify which text changed between CPU and GPU; a controlled content review is needed before explaining that difference.
