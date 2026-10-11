# IR-495 · Reproducible extraction resource benchmark

Date: 2026-10-10
Issue: https://citiris.atlassian.net/browse/IR-495
Status: Approved, including higher-limit profiles and an initial run.

## Purpose and scope

Measure Docling extraction across CPU, container RAM, and GPU memory limits on a fixed PDF set. Preserve latency, throughput, resource use, failures, and extraction completeness for future capacity decisions. This is an opt-in development benchmark, not a CI performance threshold. It must leave the application database and Redis queues untouched. The operator may pause the local extraction worker and Docling service for GPU runs, after confirming the queue and active work are empty, and must restore their original state after the run.

## Approach

Build a standalone Python runner under `scripts/`. For each profile it starts an isolated Docling container from the repository's pinned image, calls `/v1/convert/file` with the same options as `DoclingExtractor`, samples resource use, and writes raw and summarized results. An optional IRIS task smoke check runs separately from profile timing.

Alternatives considered:

- A full CPU × RAM × VRAM grid measures interactions, but greatly increases run time and makes thermal drift harder to interpret. The default varies one limit at a time; an explicit profile file can later define a full grid.
- Mocked extraction unit tests are fast and belong in CI, but cannot measure actual Docling or CUDA behavior. Use mocks to verify the runner's control and reporting logic.

## Corpus and profiles

The operator provides a directory and a manifest naming five PDFs: short prose, medium prose, long paper, formula-heavy paper, and table-heavy paper. Paths are relative to the directory. An optional scanned PDF is a separate OCR-on series and is never mixed with the OCR-off comparison. Preflight checks PDF type and Docling's 50 MB / 200-page limits, then records SHA-256, byte size, and page count. No paper content or extracted text appears in results.

The GPU baseline uses one Docling worker, two concurrent client requests for throughput, 4 CPUs, 8 GiB RAM, an 8 GiB GPU tensor-memory cap, 2 torch threads, OCR off, accurate tables, and the current formula, code, and picture-classification options. Profiles change one resource from this baseline:

| Factor | Limits |
|---|---|
| CPUs | 2, 4, 8, 12, 16 |
| Container RAM | 6, 8, 12, 14 GiB |
| GPU tensor memory | 4, 6, 8, 12, 13, 14 GiB |
| CPU-only reference | 4 CPUs / 6 GiB and 8 CPUs / 12 GiB |

The 4 GiB GPU case is a stress case: skipped formulas or failure cannot count as a clean speedup. This computer exposes 16 logical CPUs, about 15 GiB to Docker, and a 16 GiB RTX 5070 Ti. The 14 GiB RAM and VRAM profiles are upper-bound stress cases and run only when preflight confirms headroom for Docker, CUDA context, and other active services. Preflight records logical CPUs, host and Docker RAM ceilings, GPU model and free/total VRAM, Docker version, image ID, and effective limits. It marks unsupported profiles skipped with a reason. Uncapped VRAM is excluded by default.

## Run protocol and measurements

Run profiles serially in isolated containers. Wait for health, time one cold conversion, perform one unscored warm-up, then convert each selected PDF twice as a warm series, reversing order for the second pass. Measure per-paper latency and a separate batch with two requests in flight for throughput. Repeat the baseline at the end to expose drift. Repeats, concurrency, profile selection, timeouts, and total time budget are configurable. Default client and server conversion timeouts are both 3600 seconds for dense papers.

For each conversion record wall time, outcome and HTTP status, extracted page and element counts by type, and a hash of normalized structure. Compare counts with that paper's clean baseline and flag missing pages, elements, formulas, or tables. Failures, timeouts, restarts, and formula losses remain visible and are excluded from clean throughput. A failed profile is recorded and the runner continues with the next safe one.

Sample Docker CPU percentage and RAM use and, where available, `nvidia-smi` GPU memory and utilization at a fixed interval. Record peaks, the raw resource time series, sample interval, pre-run GPU baseline, and container exit/OOM state. Whole-card GPU use includes other processes and cannot isolate Docling's allocation. A single `docker stats` snapshot is not called a peak.

## Artifacts

Write a timestamped directory under `docs/evaluation/runs/` or a chosen output path: `manifest.json` for corpus hashes, host/image/config and methodology; `samples.jsonl` for per-paper conversions; `resources.jsonl` for sampled usage; `summary.csv` for profile aggregates; and `report.md` for median/p95 latency, throughput, failures, completeness, peaks, comparisons, and caveats. Exclude raw PDFs, extracted text, credentials, and private absolute paths. The first run on this computer records each profile as completed, skipped, or failed with a reason.

## Verification and safety

Automated tests fake Docker, process, and HTTP seams to check profile validation, limit propagation, baseline bracketing, sampling aggregation, failure classification, completeness flags, and stable serialization. A manual smoke run checks one PDF against the pinned GPU image. The optional IRIS task smoke confirms the application path but stays out of Docling profile measurements.

Benchmark containers bind only to localhost on an ephemeral port, use unique names, and are removed in `finally` even after interruption. The operator records and restores the prior state of any paused local services; the runner does not control the application stack. It changes no production defaults. Findings apply to this corpus, machine, image, and option set; they do not establish universal sizing or OCR quality.
