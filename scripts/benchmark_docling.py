"""Opt-in Docling resource benchmark. Never run from CI.

Requires Docker, httpx, psutil, PyMuPDF, and the pinned iris-docling images. The corpus
manifest is a JSON object mapping short labels to PDF paths relative to --corpus.
Results contain hashes and structural counts, never extracted text.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import fitz
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from apps.ai.extraction.docling_client import DoclingExtractor  # noqa: E402


@dataclass(frozen=True)
class Profile:
    name: str
    variant: str = "gpu"
    cpus: int = 4
    ram_gib: int = 8
    vram_gib: int | None = 8


def default_profiles() -> list[Profile]:
    baseline = Profile("baseline-start")
    profiles = [baseline]
    profiles += [Profile(f"cpu-{n}", cpus=n) for n in (2, 8, 12, 16)]
    profiles += [Profile(f"ram-{n}", ram_gib=n) for n in (6, 12, 14)]
    profiles += [Profile(f"vram-{n}", vram_gib=n) for n in (4, 6, 12, 13, 14)]
    profiles += [
        Profile("cpu-only-4", "cpu", 4, 6, None),
        Profile("cpu-only-8", "cpu", 8, 12, None),
        Profile("baseline-end"),
    ]
    return profiles


def run(*args: str, timeout: int = 60, check: bool = True) -> str:
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, check=False
    )
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {result.stderr.strip()[:300]}")
    return result.stdout.strip()


def gpu_state() -> dict | None:
    try:
        line = run(
            "nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits", timeout=10
        ).splitlines()[0]
        name, total, free, used, utilization = (part.strip() for part in line.split(","))
        return {
            "name": name, "total_mib": int(total), "free_mib": int(free),
            "used_mib": int(used), "utilization_pct": int(utilization),
        }
    except (OSError, IndexError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        return None


def docker_memory_gib() -> float:
    return int(run("docker", "info", "--format", "{{.MemTotal}}")) / 1024**3


def skip_reason(profile: Profile, *, logical_cpus: int, docker_ram_gib: float,
                gpu: dict | None) -> str | None:
    if profile.cpus > logical_cpus:
        return "CPU limit exceeds host logical CPUs"
    # Leave room for Docker, PostgreSQL, Redis, and the host. A limit is only
    # useful if the machine could actually supply it during this run.
    if profile.ram_gib > docker_ram_gib - 1:
        return "RAM limit leaves under 1 GiB for other Docker services"
    # Windows reports WSL2's reserved memory as unavailable host RAM even when
    # Docker has that memory free internally. The Docker ceiling is authoritative.
    if profile.variant == "gpu":
        if gpu is None:
            return "NVIDIA GPU unavailable"
        if profile.vram_gib is None or profile.vram_gib < 4:
            return "GPU tensor cap must be at least 4 GiB"
        if profile.vram_gib * 1024 + 512 > gpu["free_mib"]:
            return "GPU tensor cap plus CUDA context exceeds currently free VRAM"
    return None


def read_corpus(root: Path, manifest_path: Path, only: set[str] | None) -> dict[str, dict]:
    selected = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(selected, dict) or not selected:
        raise ValueError("corpus manifest must map labels to relative PDF paths")
    corpus: dict[str, dict] = {}
    for label, relative in selected.items():
        if only and label not in only:
            continue
        if not isinstance(label, str) or not re.fullmatch(r"[a-z0-9_-]+", label):
            raise ValueError(f"invalid corpus label: {label!r}")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError(f"{label}: expected a relative path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"{label}: PDF path is outside corpus or missing")
        if path.suffix.lower() != ".pdf" or path.stat().st_size > 50 * 1024**2:
            raise ValueError(f"{label}: expected a PDF no larger than 50 MiB")
        data = path.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise ValueError(f"{label}: file has no PDF signature")
        try:
            with fitz.open(stream=data, filetype="pdf") as pdf:
                pages = pdf.page_count
        except Exception as exc:
            raise ValueError(f"{label}: unreadable PDF") from exc
        if not 1 <= pages <= 200:
            raise ValueError(f"{label}: expected 1–200 pages, found {pages}")
        corpus[label] = {
            "path": path, "relative_path": relative,
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "pages": pages,
        }
    if not corpus:
        raise ValueError("no selected PDFs in corpus manifest")
    return corpus


def structure_metrics(document) -> dict:
    counts: dict[str, int] = {}
    digest = hashlib.sha256()
    for element in document.elements:
        counts[element.kind] = counts.get(element.kind, 0) + 1
        digest.update(
            json.dumps([element.kind, element.page, element.text],
                       ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    return {
        "pages": len(document.page_sizes),
        "elements": len(document.elements),
        "kinds": counts,
        "structure_sha256": digest.hexdigest(),
    }


def completeness_flags(metrics: dict, reference: dict | None) -> list[str]:
    if reference is None:
        return []
    flags = []
    if metrics["pages"] < reference["pages"]:
        flags.append("missing_pages")
    if metrics["elements"] < reference["elements"]:
        flags.append("missing_elements")
    for kind, flag in (("formula", "missing_formulas"), ("table_row", "missing_table_rows")):
        if metrics["kinds"].get(kind, 0) < reference["kinds"].get(kind, 0):
            flags.append(flag)
    if metrics["structure_sha256"] != reference["structure_sha256"]:
        flags.append("structure_changed")
    return flags


def extract_one(label: str, item: dict, url: str, timeout: int) -> dict:
    started = time.perf_counter()
    result = {"paper": label, "status": "failed", "seconds": None}
    try:
        extracted = DoclingExtractor(url, timeout=timeout).extract(
            item["path"].read_bytes(), filename=f"{label}.pdf"
        )
        result.update(status="ok", http_status=200,
                      metrics=structure_metrics(extracted.document))
    except Exception as exc:
        # No PDF bytes, extracted text, or absolute paths in errors.
        message = str(exc).lower()
        if "timed out" in message or "timeout" in message:
            category = "timeout"
        elif "returned 5" in message or "unreachable" in message:
            category = "service"
        elif "rejected" in message:
            category = "rejected"
        else:
            category = type(exc).__name__
        code = re.search(r"(?:returned |\()(\d{3})(?:\)| at)", message)
        result.update(status="failed", error=category,
                      http_status=int(code.group(1)) if code else None)
    result["seconds"] = round(time.perf_counter() - started, 3)
    return result


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")


class ResourceSampler:
    def __init__(self, container: str, path: Path, profile: str = "",
                 interval: float = 1.0,
                 gpu_baseline_mib: int | None = None):
        self.container = container
        self.profile = profile
        self.path = path
        self.interval = interval
        self.gpu_baseline_mib = gpu_baseline_mib
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.rows: list[dict] = []

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=self.interval + 10)

    def _loop(self):
        while not self.stop.is_set():
            row = {"at": datetime.now(timezone.utc).isoformat(),
                   "profile": self.profile, "container": self.container}
            try:
                stats = run("docker", "stats", "--no-stream", "--format",
                            "{{.CPUPerc}}|{{.MemUsage}}", self.container, timeout=15)
                cpu, mem = stats.split("|")
                row["cpu_pct"] = float(cpu.strip().rstrip("%"))
                amount, unit = re.match(r"([\d.]+)([A-Za-z]+)", mem.strip()).groups()
                row["ram_mib"] = round(float(amount) * {
                    "B": 1 / 1024**2, "KiB": 1 / 1024, "MiB": 1,
                    "GiB": 1024, "kB": 1 / 1024, "MB": 1, "GB": 1024,
                }[unit], 2)
                gpu = gpu_state()
                if gpu:
                    row["gpu_used_mib"] = gpu["used_mib"]
                    row["gpu_pct"] = gpu["utilization_pct"]
                    if self.gpu_baseline_mib is not None:
                        row["gpu_delta_mib"] = gpu["used_mib"] - self.gpu_baseline_mib
            except (OSError, RuntimeError, ValueError, AttributeError, subprocess.TimeoutExpired):
                row["sample_error"] = True
            self.rows.append(row)
            append_jsonl(self.path, row)
            self.stop.wait(self.interval)


def container_port(name: str) -> int:
    address = run("docker", "port", name, "5001/tcp")
    return int(address.rsplit(":", 1)[1])


def wait_healthy(name: str, limit: int = 180) -> int:
    deadline = time.monotonic() + limit
    port = container_port(name)
    while time.monotonic() < deadline:
        state = run("docker", "inspect", "--format", "{{.State.Running}}", name)
        if state != "true":
            raise RuntimeError("Docling container exited before becoming healthy")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                if response.status == 200:
                    return port
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise TimeoutError("Docling did not become healthy")


def start_container(profile: Profile, *, timeout: int, gpu_image: str, cpu_image: str) -> str:
    name = f"iris-bench-{uuid.uuid4().hex[:12]}"
    args = ["docker", "run", "-d", "--rm", "--name", name,
            "--cpus", str(profile.cpus), "--memory", f"{profile.ram_gib}g",
            "-p", "127.0.0.1::5001",
            "-e", "DOCLING_SERVE_ENG_LOC_NUM_WORKERS=1",
            "-e", "DOCLING_SERVE_OPTIONS_CACHE_SIZE=1",
            "-e", "DOCLING_SERVE_MAX_NUM_PAGES=200",
            "-e", "DOCLING_SERVE_MAX_FILE_SIZE=52428800",
            "-e", f"DOCLING_SERVE_MAX_SYNC_WAIT={timeout}",
            "-e", f"OMP_NUM_THREADS={2 if profile.variant == 'gpu' else 4}"]
    if profile.variant == "gpu":
        args += ["--gpus", "all", "-e", f"DOCLING_GPU_MEMORY_GB={profile.vram_gib}"]
    args.append(gpu_image if profile.variant == "gpu" else cpu_image)
    run(*args, timeout=60)
    return name


def stop_container(name: str) -> None:
    run("docker", "rm", "-f", name, timeout=30, check=False)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.9999))], 3)


def summarize(rows: list[dict], resources: list[dict], profile: str) -> dict:
    measured = [r for r in rows if r["phase"] in ("warm", "batch")]
    clean = [r for r in measured if r["status"] == "ok" and not r.get("flags")]
    latencies = [r["seconds"] for r in clean if r["phase"] == "warm"]
    batches = [r for r in clean if r["phase"] == "batch"]
    batch_times = [r["batch_wall_seconds"] for r in measured if r["phase"] == "batch"]
    return {
        "profile": profile, "measured": len(measured), "clean": len(clean),
        "failures": sum(r["status"] != "ok" for r in measured),
        "incomplete": sum(any(flag.startswith("missing_") for flag in r.get("flags", []))
                          for r in measured),
        "changed": sum("structure_changed" in r.get("flags", []) for r in measured),
        "median_warm_seconds": round(statistics.median(latencies), 3) if latencies else None,
        "p95_warm_seconds": percentile(latencies, .95),
        "batch_papers_per_min": round(len(batches) * 60 / max(batch_times), 3)
        if batches and batch_times and max(batch_times) else None,
        "peak_cpu_pct": max((r.get("cpu_pct", 0) for r in resources), default=None),
        "peak_ram_mib": max((r.get("ram_mib", 0) for r in resources), default=None),
        "peak_gpu_used_mib": max((r.get("gpu_used_mib", 0) for r in resources), default=None),
        "peak_gpu_delta_mib": max((r.get("gpu_delta_mib", 0) for r in resources), default=None),
    }


def write_report(output: Path, manifest: dict, summaries: list[dict]) -> None:
    fields = list(summaries[0]) if summaries else ["profile"]
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summaries)
    baseline = next((s["median_warm_seconds"] for s in summaries
                     if s["profile"] == "baseline-start"), None)
    lines = ["# Docling extraction benchmark", "",
             f"Run: {manifest['created_at']}", "",
             "Results are specific to this corpus, host, image, and options.", "",
             "| Profile | Outcome | Clean / measured | Failed | Incomplete | Changed | "
             "Warm median | vs baseline | Warm p95 | Batch papers/min | "
             "Peak CPU % | Peak RAM MiB | Peak GPU delta MiB |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in summaries:
        status = manifest["profiles"].get(row["profile"], {}).get("status", "unknown")

        def fmt(value):
            return "—" if value is None else str(value)
        change = (f"{(row['median_warm_seconds'] / baseline - 1) * 100:+.1f}%"
                  if baseline and row["median_warm_seconds"] is not None else "—")
        lines.append(
            f"| {row['profile']} | {status} | {row['clean']} / {row['measured']} | "
            f"{row['failures']} | {row['incomplete']} | {row['changed']} | "
            f"{fmt(row['median_warm_seconds'])} | {change} | {fmt(row['p95_warm_seconds'])} | "
            f"{fmt(row['batch_papers_per_min'])} | {fmt(row['peak_cpu_pct'])} | "
            f"{fmt(row['peak_ram_mib'])} | {fmt(row['peak_gpu_delta_mib'])} |"
        )
    lines += ["", "Failures and completeness differences are in samples.jsonl. "
              "GPU memory is the whole-card reading, including other processes. "
              "CPU and RAM peaks are sampled, so short spikes may be missed.",
              "Single-paper, single-repeat runs are pilot measurements; their p95 "
              "is not a stable estimate. A limit above observed peak use is nonbinding.",
              f"Sampling interval: {manifest['sample_interval_seconds']} s. "
              f"Client/server timeout: {manifest['timeout_seconds']} s."]
    for name, outcome in manifest["profiles"].items():
        if outcome["status"] in ("skipped", "failed"):
            lines.append(f"{name}: {outcome['status']} — {outcome.get('reason', 'see manifest')}.")
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def benchmark_profile(
    profile: Profile, *, corpus: dict, output: Path, reference: dict,
    repeats: int, concurrency: int, timeout: int, gpu_image: str,
    cpu_image: str,
) -> tuple[list[dict], list[dict], dict]:
    before_gpu = gpu_state() if profile.variant == "gpu" else None
    container = start_container(profile, timeout=timeout, gpu_image=gpu_image, cpu_image=cpu_image)
    rows: list[dict] = []
    try:
        port = wait_healthy(container)
        url = f"http://127.0.0.1:{port}"
        with ResourceSampler(
            container, output / "resources.jsonl", profile=profile.name,
            gpu_baseline_mib=before_gpu["used_mib"] if before_gpu else None,
        ) as sampler:
            first_label = next(iter(corpus))
            for phase in ("cold", "warmup"):
                row = extract_one(first_label, corpus[first_label], url, timeout)
                row.update(profile=profile.name, phase=phase)
                rows.append(row)
                append_jsonl(output / "samples.jsonl", row)
            for repeat in range(repeats):
                labels = list(corpus)
                if repeat % 2:
                    labels.reverse()
                for label in labels:
                    row = extract_one(label, corpus[label], url, timeout)
                    row.update(profile=profile.name, phase="warm", repeat=repeat)
                    row["flags"] = (
                        completeness_flags(row["metrics"], reference.get(label))
                        if row["status"] == "ok" else []
                    )
                    rows.append(row)
                    append_jsonl(output / "samples.jsonl", row)
            batch_start = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(extract_one, label, item, url, timeout): label
                           for label, item in corpus.items()}
                batch_rows = [
                    future.result() for future in concurrent.futures.as_completed(futures)
                ]
            batch_wall = round(time.perf_counter() - batch_start, 3)
            for row in batch_rows:
                row.update(profile=profile.name, phase="batch", batch_wall_seconds=batch_wall)
                row["flags"] = (
                    completeness_flags(row["metrics"], reference.get(row["paper"]))
                    if row["status"] == "ok" else []
                )
                rows.append(row)
                append_jsonl(output / "samples.jsonl", row)
        state = run("docker", "inspect", "--format",
                    "{{.State.OOMKilled}}|{{.RestartCount}}", container, check=False)
        effective = json.loads(run("docker", "inspect", "--format",
                                   "{{json .HostConfig}}", container))
        metadata = {"status": "completed", "container": container,
                    "oom_or_restarts": state,
                    "image_id": run("docker", "inspect", "--format", "{{.Image}}", container),
                    "effective_limits": {
                        "nano_cpus": effective.get("NanoCpus"),
                        "memory_bytes": effective.get("Memory"),
                        "device_requests": effective.get("DeviceRequests"),
                    }}
        return rows, sampler.rows, metadata
    finally:
        stop_container(container)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--paper", action="append", help="Select a corpus label; repeatable")
    parser.add_argument("--profile", action="append", help="Select a profile name; repeatable")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--max-minutes", type=float, default=0,
                        help="Stop before starting a profile after this many minutes (0=no limit)")
    parser.add_argument("--gpu-image", default="iris-docling:gpu")
    parser.add_argument("--cpu-image", default="iris-docling:cpu")
    args = parser.parse_args(argv)
    if (args.repeats < 1 or args.concurrency < 1 or args.timeout < 30
            or args.max_minutes < 0):
        parser.error("repeats/concurrency must be positive; timeout must be at least 30 seconds")
    corpus = read_corpus(args.corpus, args.manifest, set(args.paper) if args.paper else None)
    profiles = default_profiles()
    if args.profile:
        selected = set(args.profile)
        unknown = selected - {p.name for p in profiles}
        if unknown:
            parser.error(f"unknown profile(s): {sorted(unknown)}")
        profiles = [p for p in profiles if p.name in selected]
    output = args.output or Path("docs/evaluation/runs") / (
        "docling-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    output.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(output).free < 1024**3:
        raise RuntimeError("less than 1 GiB free in benchmark output volume")
    gpu = gpu_state()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus": {label: {key: value for key, value in item.items() if key != "path"}
                   for label, item in corpus.items()},
        "host": {
            "logical_cpus": os.cpu_count(),
            "ram_gib": round(psutil.virtual_memory().total / 1024**3, 2),
            "docker_ram_gib": round(docker_memory_gib(), 2),
            "gpu": gpu,
            "docker_version": run("docker", "version", "--format", "{{.Server.Version}}"),
        },
        "images": {"gpu": args.gpu_image, "cpu": args.cpu_image},
        "profiles": {}, "sample_interval_seconds": 1.0,
        "timeout_seconds": args.timeout, "repeats": args.repeats,
        "concurrency": args.concurrency,
    }
    summaries: list[dict] = []
    reference: dict = {}
    run_started = time.monotonic()
    try:
        for profile in profiles:
            if args.max_minutes and (time.monotonic() - run_started) / 60 >= args.max_minutes:
                manifest["profiles"][profile.name] = {
                    "status": "skipped", "reason": "total time budget reached",
                    "limits": asdict(profile),
                }
                summaries.append(summarize([], [], profile.name))
                write_report(output, manifest, summaries)
                continue
            current_gpu = gpu_state()
            reason = skip_reason(
                profile, logical_cpus=os.cpu_count() or 1,
                docker_ram_gib=docker_memory_gib(),
                gpu=current_gpu,
            )
            if reason:
                print(f"{profile.name}: skipped ({reason})", flush=True)
                manifest["profiles"][profile.name] = {
                    "status": "skipped", "reason": reason,
                    "limits": asdict(profile),
                }
                summaries.append(summarize([], [], profile.name))
                write_report(output, manifest, summaries)
                continue
            print(f"{profile.name}: starting", flush=True)
            try:
                rows, resources, outcome = benchmark_profile(
                    profile, corpus=corpus, output=output, reference=reference,
                    repeats=args.repeats, concurrency=args.concurrency,
                    timeout=args.timeout, gpu_image=args.gpu_image,
                    cpu_image=args.cpu_image,
                )
                if profile.name == "baseline-start":
                    reference = {r["paper"]: r["metrics"] for r in rows
                                 if r["phase"] == "warm" and r["status"] == "ok"}
                manifest["profiles"][profile.name] = {**outcome, "limits": asdict(profile)}
                summaries.append(summarize(rows, resources, profile.name))
                print(f"{profile.name}: {outcome['status']}", flush=True)
            except Exception as exc:
                print(f"{profile.name}: {exc}", file=sys.stderr, flush=True)
                manifest["profiles"][profile.name] = {
                    "status": "failed", "reason": type(exc).__name__,
                    "limits": asdict(profile),
                }
                summaries.append(summarize([], [], profile.name))
                print(f"{profile.name}: failed ({type(exc).__name__})", flush=True)
            write_report(output, manifest, summaries)
    finally:
        write_report(output, manifest, summaries)
    print(output.resolve())
    all_ok = all(p["status"] in ("completed", "skipped")
                 for p in manifest["profiles"].values())
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
