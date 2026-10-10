"""Guard benchmark decisions without starting Docker or spending GPU time."""

import json
from pathlib import Path
import sys

import fitz
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import benchmark_docling as bench  # noqa: E402
from apps.ai.chunking.document import DocumentElement, NormalizedDocument  # noqa: E402


def test_profiles_cover_baseline_upper_limits_and_cpu_reference():
    profiles = bench.default_profiles()
    assert profiles[0].name == "baseline-start"
    assert profiles[-1].name == "baseline-end"
    gpu_cpu_caps = {p.cpus for p in profiles
                    if p.name.startswith("cpu-") and p.variant == "gpu"}
    assert gpu_cpu_caps == {2, 8, 12, 16}
    assert {p.ram_gib for p in profiles if p.name.startswith("ram-")} == {6, 12, 14}
    assert {p.vram_gib for p in profiles if p.name.startswith("vram-")} == {4, 6, 12, 13, 14}
    assert {p.name for p in profiles if p.variant == "cpu"} == {"cpu-only-4", "cpu-only-8"}


@pytest.mark.parametrize(("profile", "reason"), [
    (bench.Profile("too-many-cpus", cpus=17), "CPU"),
    (bench.Profile("too-much-ram", ram_gib=15), "RAM"),
    (bench.Profile("too-much-vram", vram_gib=14), "VRAM"),
])
def test_preflight_skips_unsupported_limits(profile, reason):
    result = bench.skip_reason(profile, logical_cpus=16, docker_ram_gib=15.1,
                               gpu={"free_mib": 12 * 1024})
    assert reason in result


def test_preflight_accepts_upper_profile_with_headroom():
    assert bench.skip_reason(bench.Profile("vram-14", vram_gib=14), logical_cpus=16,
                             docker_ram_gib=15.1,
                             gpu={"free_mib": 15 * 1024}) is None


def test_corpus_records_pages_hash_and_rejects_path_escape(tmp_path):
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(tmp_path / "one.pdf")
    pdf.close()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"one": "one.pdf"}), encoding="utf-8")
    corpus = bench.read_corpus(tmp_path, manifest, None)
    assert corpus["one"]["pages"] == 1
    assert len(corpus["one"]["sha256"]) == 64
    manifest.write_text(json.dumps({"escape": "../one.pdf"}), encoding="utf-8")
    with pytest.raises(ValueError, match="outside corpus"):
        bench.read_corpus(tmp_path, manifest, None)


def test_structural_loss_is_flagged_even_when_request_succeeds():
    original = NormalizedDocument(
        title="x", page_sizes={1: (100, 100), 2: (100, 100)},
        elements=(DocumentElement("paragraph", "body", page=1),
                  DocumentElement("formula", "x=1", page=1),
                  DocumentElement("table_row", "cell", page=2)),
    )
    degraded = NormalizedDocument(
        title="x", page_sizes={1: (100, 100)},
        elements=(DocumentElement("paragraph", "body", page=1),),
    )
    assert bench.completeness_flags(bench.structure_metrics(degraded),
                                    bench.structure_metrics(original)) == [
        "missing_pages", "missing_elements", "missing_formulas",
        "missing_table_rows", "structure_changed"]


def test_changed_text_is_flagged_with_unchanged_element_counts():
    before = NormalizedDocument(title="x", elements=(DocumentElement("formula", "x=1"),))
    after = NormalizedDocument(title="x", elements=(DocumentElement("formula", "x=2"),))
    assert bench.completeness_flags(bench.structure_metrics(after),
                                    bench.structure_metrics(before)) == ["structure_changed"]


def test_incomplete_and_failed_results_do_not_improve_clean_speed():
    rows = [{"phase": "warm", "status": "ok", "seconds": 10, "flags": []},
            {"phase": "warm", "status": "ok", "seconds": 1, "flags": ["missing_formulas"]},
            {"phase": "warm", "status": "failed", "seconds": 1, "flags": []}]
    summary = bench.summarize(rows, [{"cpu_pct": 250, "ram_mib": 5000}], "test")
    assert summary["median_warm_seconds"] == 10
    assert (summary["clean"], summary["incomplete"], summary["failures"]) == (1, 1, 1)
    assert summary["peak_ram_mib"] == 5000


def test_container_uses_profile_limits_and_matching_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(bench, "run", lambda *args, **kwargs: calls.append(args) or "id")
    bench.start_container(
        bench.Profile("high", cpus=16, ram_gib=14, vram_gib=12),
        timeout=3600, gpu_image="iris-docling:gpu", cpu_image="iris-docling:cpu",
    )
    args = calls[0]
    assert args[args.index("--cpus") + 1] == "16"
    assert args[args.index("--memory") + 1] == "14g"
    assert "DOCLING_GPU_MEMORY_GB=12" in args
    assert "DOCLING_SERVE_MAX_SYNC_WAIT=3600" in args


def test_standalone_container_health_is_checked_over_http(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(bench, "container_port", lambda name: 54321)
    monkeypatch.setattr(bench, "run", lambda *args, **kwargs: "true")
    monkeypatch.setattr(bench.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    assert bench.wait_healthy("iris-bench-test") == 54321


def test_sampler_records_gpu_delta_and_container_ram(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "run", lambda *args, **kwargs: "250.0%|2.5GiB / 8GiB")
    monkeypatch.setattr(bench, "gpu_state", lambda: {
        "used_mib": 5300, "utilization_pct": 45,
    })
    sampler = bench.ResourceSampler("test", tmp_path / "resources.jsonl", profile="vram-13",
                                    gpu_baseline_mib=1800)
    monkeypatch.setattr(sampler.stop, "wait", lambda interval: sampler.stop.set())
    sampler._loop()
    assert sampler.rows[0]["ram_mib"] == 2560
    assert sampler.rows[0]["gpu_delta_mib"] == 3500
    assert sampler.rows[0]["cpu_pct"] == 250
    assert sampler.rows[0]["profile"] == "vram-13"


def test_report_serializes_skipped_profiles(tmp_path):
    manifest = {"created_at": "2026-10-10", "sample_interval_seconds": 1,
                "timeout_seconds": 3600,
                "profiles": {"vram-14": {"status": "skipped", "reason": "no headroom"}}}
    bench.write_report(tmp_path, manifest, [bench.summarize([], [], "vram-14")])
    assert "skipped" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")) == manifest
