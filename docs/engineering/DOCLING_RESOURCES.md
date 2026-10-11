# Docling resources

What the Docling container runs, what it needs, and what was measured.
For repeatable CPU/RAM/VRAM sweeps and raw timing data, see
[DOCLING_BENCHMARK.md](DOCLING_BENCHMARK.md).
docling-serve 1.36.0; formula, code and figure-classification stages on; OCR,
picture description and chart extraction off; tables always `accurate`.

## How it is deployed

`docling/compose.yml` defines two variants of one service. `docker-compose.yml`
and `docker-compose.prod.yml` pick one with `DOCLING_VARIANT` from the repo-root
`.env`.

| | `docling-gpu` (default) | `docling-cpu` |
|---|---|---|
| Base image | `docling-serve-cu128:v1.36.0` | `docling-serve-cpu:v1.36.0` |
| Image size | 18.6 GB | 8.7 GB |
| Chosen when | `nvidia-smi` sees a GPU | it does not |

**Why a script picks the variant.** Compose cannot make a GPU reservation
conditional: on a host without the NVIDIA runtime, any reservation stops the
container from being created (checked: a request for count 0 still fails). So
`python scripts/setup_env.py` looks for a GPU once and writes `DOCLING_VARIANT`.
After adding or removing a GPU, run `python scripts/setup_env.py --refresh-gpu`
and rebuild. The CPU variant is also what a GPU variant becomes if the GPU is
not exposed to the container: it logs `no GPU visible, running on CPU` and runs.

Both images are built from `docling/Dockerfile`, pinned. `:latest` once dropped
the `default` CodeFormula preset and failed every extraction.

## Settings (all in `.env`, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `DOCLING_VARIANT` | `docling-gpu` | written by `setup_env.py` |
| `DOCLING_GPU_MEMORY_GB` | `8` | VRAM cap for the server process; `0` = no cap |
| `DOCLING_WORKERS` | `1` | docling workers (see below: leave at 1) |
| `DOCLING_CPUS` | `4` | container CPU limit |
| `DOCLING_MEMORY` | `8g` (GPU), `6g` (CPU) | container RAM limit |
| `DOCLING_CPU_THREADS` | `2` (GPU), `4` (CPU) | torch threads |
| `DOCLING_MAX_SYNC_WAIT` | `900` | keep equal to `DOCLING_TIMEOUT_SECONDS` |

**The VRAM cap.** Docker cannot limit VRAM, and docling-serve has no setting for
it. `docling/iris_gpu_cap.py` sets a per-process limit when the server starts.
It limits tensor memory; the CUDA context adds about 0.5 GB on top. Do not set it
below about 4 GB: at 3 GB the formula model has no room (32 of 33 formulas were
skipped, and logged).

## Measured, GPU variant (RTX 5070 Ti, 8 GB cap, 4 CPUs)

| Test | Result |
|---|---|
| One 18-page paper, 33 formulas, 12 figures, through IRIS's extractor | 70 s cold, all 33 formulas as LaTeX |
| 14 papers submitted at once, one worker | 309 s, **2.7 papers/min**, no failures |
| Peak RAM | 5.5 GB (2.9 GB idle after a conversion) |
| Peak CPU | 280% of 4 cores |
| Peak VRAM | about 4.2 GB above idle, under the 8 GB cap |

Earlier CPU-variant numbers (4 CPUs, 6 GB, same options, without the formula
patches): 5 / 8 / 18-page papers in 219 s / 42 s / 220 s at 2.8-3.6 GB RAM.

**A GPU is not required.** The CPU variant finished every test paper in under
four minutes. The GPU makes a long paper about 3x faster.

## Concurrency: what was tried

The GPU does the formula work, so it is the bottleneck, not the number of
workers.

| Configuration (8 papers at once, 8 GB cap) | Papers/min | Notes |
|---|---|---|
| **1 worker** | **2.8** | clean |
| 2 workers | 2.3 | |
| 3 workers | 2.0 | |
| 4 workers | 1.8 | 3 formula batches lost to out-of-memory |
| 2 containers, 1 worker each, 4 GB cap each | about 4.2 | one test, papers split by hand |
| 2 server processes in one container | 2.9 | 16 formulas skipped; one process died on the next run |

- **Workers are threads in one process**, so more of them contend rather than
  overlap. One worker is the default and the only setting without a failure.
- **Two separate containers did better (about 1.5x)** but only in one run with a
  hand-picked split; it needs a load balancer in front, which IRIS does not have.
  `iris_gpu_cap.py` already divides the cap by `UVICORN_WORKERS` for anyone who
  tries it, but multiple server processes in one container were not reliable here.
- The extraction worker runs two tasks at once (`--concurrency=2`). That is
  enough to keep the one docling worker fed while the other task parses.
- A local, gitignored `docker-compose.override.yml` may change extraction
  concurrency and timeout. Check the effective Compose configuration before
  comparing runs; the benchmark uses isolated containers with recorded limits.

## What the image patches (and why)

`docling/patch_docling.py` edits docling at build time and fails the build if a
docling upgrade moves what it edits.

1. **Formula generation capped at 768 tokens** (docling hardcodes 2048). One
   malformed formula held a whole batch for minutes.
2. **Formula batch of 16** (docling hardcodes 5). 32 crashed the CUDA context
   once, so do not go higher.
3. **A batch that runs out of GPU memory is split and retried.** Unpatched,
   docling logs the error and returns every formula in the batch empty, so
   papers lose equations with no failure. Now only a formula that cannot fit
   alone is lost, and it is logged as `Formula skipped`.
4. **The VRAM cap** is hooked into `create_app`, so it runs in every server
   process.

A formula longer than 768 tokens is truncated. None was seen in the test papers.

## Trade-offs made to stay small

- Figure descriptions and chart data are off (0.7-7.5 GB models each, and the
  mapper has nowhere to store them).
- Figure classification runs but IRIS discards the result: `docling_mapping.py`
  keeps only a picture's caption. It costs about 8 s a paper until the mapper
  stores it.
- Code enrichment is on and shares the formula model; no test paper contained
  code, so its cost is unmeasured.
- OCR is off. A scanned PDF with no text layer extracts nothing; set
  `DOCLING_DO_OCR=true` for a deployment that accepts scans.
- Tables are always accurate; there is no setting to change it.

## Further optimizations, in order of expected payoff

1. **Serve CodeFormula from a separate vLLM container** and point docling's
   formula stage at it (`code_formula_custom_config`, API engine). vLLM batches
   across requests, so concurrency would finally be free instead of contended,
   and docling would hold no formula model itself. Untested.
2. **Two docling containers behind a small proxy** if one GPU's throughput is
   not enough; about 1.5x in the one test.
3. **Hold the one worker warm.** The first request after a start loads the
   models; restarting per paper multiplies every time above.
4. **Smaller formula batches (8)** if a card has under 6 GB free; untested.
5. **Reduce `DOCLING_CPU_THREADS`** if the 4 cores are shared; CPU variant time
   scales roughly with threads.
