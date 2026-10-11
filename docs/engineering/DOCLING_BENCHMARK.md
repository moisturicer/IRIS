# Repeatable Docling extraction benchmark

This is an opt-in resource experiment for [IR-495](https://citiris.atlassian.net/browse/IR-495). It runs isolated Docling containers and calls IRIS's real `DoclingExtractor`. It never updates records or publishes Celery tasks. Do not run it in CI.

## Prepare

Install Python 3.12+ with `httpx`, `psutil`, and `PyMuPDF` available. Build the pinned images from this repository:

```powershell
docker build -t iris-docling:gpu --build-arg DOCLING_BASE=quay.io/docling-project/docling-serve-cu128:v1.36.0 -f docling/Dockerfile docling
docker build -t iris-docling:cpu --build-arg DOCLING_BASE=quay.io/docling-project/docling-serve-cpu:v1.36.0 -f docling/Dockerfile docling
```

Create a private corpus directory with PDFs and `manifest.json`:

```json
{
  "short": "short.pdf",
  "medium": "medium.pdf",
  "long": "long.pdf",
  "formula": "formula.pdf",
  "tables": "tables.pdf"
}
```

Choose born-digital PDFs for the default OCR-off series. An OCR-on scanned series needs a separate run and comparison. Keep PDFs outside Git; the result files contain hashes and structural counts, not paper text.

The normal IRIS Docling service consumes GPU memory. Before a GPU sweep, confirm the extraction Redis queue, Celery active/reserved tasks, and database `PdfExtraction` queued/running rows are empty. Pause the local extraction worker and Docling service, then restore their previous state after the sweep. The benchmark runner never stops application services itself. Other GPU programs also reduce usable VRAM; the preflight marks an unsupported cap as skipped.

## Run

From the repository root:

```powershell
python scripts/benchmark_docling.py --corpus C:\path\to\private-corpus --manifest C:\path\to\private-corpus\manifest.json
```

The default profiles bracket a one-factor sweep with baseline runs: CPU caps 2/4/8/12/16, RAM limits 6/8/12/14 GiB, GPU tensor caps 4/6/8/12/13/14 GiB, and two CPU-only references. The 13 GiB cap is a practical upper step when desktop GPU use leaves too little room for 14 GiB plus CUDA context. One Docling worker is used throughout. Defaults run two warm repeats per paper and a batch with two requests in flight. The first conversion is reported separately as cold; the next is an unscored warm-up. Client and server timeouts both default to 3600 seconds.

Use `--profile NAME` and `--paper LABEL` repeatedly for a shorter sweep; `--repeats`, `--concurrency`, `--timeout`, and `--output` are configurable. The benchmark does not silently reduce settings. It records skipped profiles with reasons. For example:

```powershell
python scripts/benchmark_docling.py --corpus C:\path\to\private-corpus --manifest C:\path\to\private-corpus\manifest.json --paper short --profile baseline-start --profile cpu-16 --profile ram-14 --profile vram-14 --profile baseline-end --repeats 1 --output docs/evaluation/runs/my-docling-run
```

The output directory must not already exist. It contains:

- `manifest.json`: corpus hashes, page counts, machine limits, settings, and each profile's outcome.
- `samples.jsonl`: per-conversion latency, structural counts, success, failure class, and completeness flags.
- `resources.jsonl`: time-stamped CPU, RAM, and whole-card GPU samples.
- `summary.csv` and `report.md`: clean latency, throughput, and sampled peaks by profile.

Compare results only for the same corpus, image, extractor options, and concurrency. A profile that loses formulas or pages cannot count as a clean speedup. GPU memory readings include other processes, and sampled peaks may miss brief spikes. Docker's RAM ceiling is the relevant preflight value under WSL2: Windows can report little free RAM while Docker still has its reserved memory available.

## Recorded pilots

- [Upper-limit short-paper run](../evaluation/runs/20261010-docling-upper-short/analysis.md): 12/16 CPU, 12/14 GiB RAM, and 12 GiB VRAM caps, bracketed by baseline. The 14 GiB VRAM setting was skipped because this computer lacked enough free VRAM for its cap and CUDA context.
- [Formula-heavy 13 GiB VRAM run](../evaluation/runs/20261010-docling-formula-vram/analysis.md): a 35-page paper with 124 formulas, all retained. The 13 GiB cap showed no credible latency gain over the 8 GiB baseline in this one-repeat pilot.
- [CPU-only short-paper run](../evaluation/runs/20261010-docling-cpu-short/analysis.md): 4-core and 8-core CPU references bracketed by GPU baseline. Counts matched, but a different content hash kept the CPU timings out of clean comparisons.

These targeted runs exercise the higher limits and the measurement path. The default command above is the full five-paper sweep for a longer analysis, and should be run with more repeats before changing deployment defaults.
