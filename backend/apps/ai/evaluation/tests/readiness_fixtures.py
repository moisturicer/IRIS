"""Synthetic inputs for IR-741's release-readiness tests. Pure; no database, no vendor.

Everything here is hand-authored test data. A run labelled ``real`` below is a *fixture
declaring itself real* so the gate's logic can be exercised; it is never measured evidence.
Two families of ten supported development cases give each repetition ten reviewed cases per
family, which is what a counted report needs, and every case has two agreeing human reviews.
"""

import copy

from apps.ai.evaluation.campaign_report import build_report
from apps.ai.evaluation.conversations import lock_record, split_digests
from apps.ai.evaluation.engines import runtime_identity
from apps.ai.evaluation.readiness import canonical_digest

from .test_campaign_report import APPROVED, attempt, row, turn
from .test_conversations import conv, make_set

FAMILIES = ("A01", "A02")
SET = make_set([conv(f"{f}-{i}", f, topic=f"{f}-topic-{i}", papers=(f"{f} paper {i}",))
                for f in FAMILIES for i in range(10)])
SET["label_status"] = "human_reviewed"
SET["corpus"] = {"snapshot_id": "proxy-40", "paper_set_sha256": "c0ffee"}
LOCK = {**lock_record(SET), "locked_at": "2026-10-01T00:00:00+00:00"}
CASES = [c["id"] for c in SET["conversations"]]
ENGINES = {"controller": "controller-v1", "runtime": "ai-runtime-1"}
PROTOCOLS = {"controller": "public-1", "runtime": "runs-reader-1"}
COMMITS = {"controller": "ctl1", "runtime": "rt1"}
SCENARIOS_PASSED = {
    "access_and_recovery": {"kind": "deterministic_provider_contract", "status": "measured",
                            "passed": True, "tests": 40, "failed": 0, "errors": 0, "skipped": 0,
                            "git_commit": "rt1"},
    "durability": {"kind": "postgres_independent_processes_scripted_provider",
                   "status": "measured", "passed": True, "tests": 12, "failed": 0, "errors": 0,
                   "skipped": 0, "git_commit": "rt1"},
    "browser": {"kind": "manual_browser", "status": "measured", "passed": True,
                "operator": "Operator One", "git_commit": "rt1",
                "checks": {name: {"status": "measured", "passed": True,
                                  "evidence_ref": f"shot/{name}.png"}
                           for name in (
                    "live", "reopened", "copied", "exported", "paper_chat", "mobile", "keyboard",
                    "accessible_summary", "ask_notice_before_submit",
                    "paper_notice_before_submit")}},
}


#: Evidence references as the command records them: where each input came from and its digest.
REFS = {name: {"path": f"evidence/{name}.json", "sha256": f"{i:064x}"}
        for i, name in enumerate(("report", "baseline", "scenarios", "workload", "profile",
                                  "measurements", "approvals"), 1)}


def mkrun(arm, run_id, providers="real", attempts=None, cases=None, **manifest):
    rows = [row(cid, next(c["family"] for c in SET["conversations"] if c["id"] == cid),
                conversation_id=f"{run_id}/{cid}",
                turns=[turn(attempts=attempts if attempts is not None
                            else [attempt("llm", 0.01)])]) for cid in (cases or CASES)]
    base = {"run_id": run_id, "timestamp_utc": "2026-10-02T00:00:00+00:00",
            "git_commit": COMMITS[arm], "engine_version": ENGINES[arm],
            "protocol_version": PROTOCOLS[arm], "cache_state": "cold",
            "corpus_snapshot_digest": "c0ffee", "model_ids": {"answer": "m1"},
            "data_policy": "no-training", "limits": {"case_cost_usd": 1.0},
            "set_digests": split_digests(SET), "rubric_version": 1,
            "pricing_per_million_tokens_usd": {"m1": {"input": 1.0, "output": 2.0}}}
    if arm == "runtime":
        base["identity"] = runtime_identity()
    base.update(manifest)
    return {"schema_version": 1, "run_id": run_id, "arm": arm, "providers": providers,
            "manifest": base, "conversations": rows}


def campaign(n=3, providers="real", cases=None, **by_arm):
    return {arm: [mkrun(arm, f"{arm}-{i}", providers=providers, cases=cases,
                        **by_arm.get(arm, {}))
                  for i in range(n)] for arm in ("controller", "runtime")}


def verdict(arm, cid, run_id, reviewer, **extra):
    base = {"conversation": cid, "arm": arm, "run_id": run_id, "reviewer": reviewer,
            "reviewer_kind": "human", "rubric_version": 1, "status": "reviewed",
            "task_completion": "yes", "pair_usefulness": "useful",
            "claims": [{"record_id": 1, "supported": True, "citation_correct": True,
                        "page_correct": True}],
            "unnecessary_clarification": False, "presentation_leak": False,
            "access_breach": False, "no_answer": False}
    base.update(extra)
    return base


def reviews(changes=None, skip=(), single=()):
    """Two agreeing human reviews for every case of every repetition of both arms.

    ``changes``: {(arm, repetition, case): {field: value}} applied to both reviewers.
    """
    changes = changes or {}
    out = []
    for arm in ("controller", "runtime"):
        for i in range(3):
            for cid in CASES:
                if (arm, i, cid) in skip:
                    continue
                extra = changes.get((arm, i, cid), {})
                for reviewer in ("Ana", "Ben"):
                    if reviewer == "Ben" and (arm, i, cid) in single:
                        continue
                    out.append(verdict(arm, cid, f"{arm}-{i}", reviewer, **extra))
    return out


def campaign_report(runs=None, revs=None, *, scenarios=SCENARIOS_PASSED, counted=True,
                    min_examples=10, approvals=APPROVED):
    return build_report(SET, LOCK, runs if runs is not None else campaign(),
                        revs if revs is not None else reviews(), mode="architecture",
                        approvals=approvals, scenarios=scenarios, min_examples=min_examples,
                        counted=counted)


def frozen(report_):
    """A baseline report as it would be preserved on disk."""
    return copy.deepcopy(report_)


# --- workload, profile and load measurements (all synthetic) ------------------------------

WORKLOAD = {
    "declared_at": "2026-10-20T00:00:00+00:00", "declared_by": "Owner Name",
    "mix": {"ordinary": 40, "deep": 10, "ingestion": 5}, "concurrency": 8,
    "cache_state": "cold", "corpus_snapshot_digest": "c0ffee",
    "model_ids": {"answer": "m1"}, "data_policy": "no-training",
}
#: Every operational cap is stated; none is a default and none is an approved production value.
CAPS = {"deadline_seconds": 60, "deep_deadline_seconds": 600, "max_attempts": 4,
        "max_input_tokens": 100000, "max_output_tokens": 4000, "max_cost_usd": 1.0,
        "max_queued": 50, "deep_concurrency": 2, "worker_concurrency": 6,
        "campaign_cost_usd": 100.0}
PROFILE = {
    "authorized_by": "Owner Name", "reference": "PROFILE-1", "date": "2026-10-20",
    "latency": {"ordinary_p95_ms": 2000, "deep_p95_ms": 40000},
    "cost": {"cost_per_successful_task_usd": 0.02},
    "resources": {"memory_mb": 1024, "connections": 50, "lock_wait_ms": 200},
    "caps": CAPS,
}


def sample(cls, i, *, outcome="success", cost=0.01, usage_reported=True, **extra):
    base = {"class": cls, "outcome": outcome, "queue_ms": 100 + i,
            "total_ms": (1000 + 10 * i) if cls == "ordinary" else (20000 + 1000 * i),
            "tool_ms": 50 + i, "model_ms": 600 + i, "cost_usd": cost,
            "usage_reported": usage_reported}
    base.update(extra)
    return base


def measurements(workload=WORKLOAD, **over):
    """40 ordinary (the slowest three failed), 10 deep and 5 ingestion samples.

    Hand-worked: ordinary p95 is the 38th of 40 total times = 1370 ms (a failed request, so
    dropping failures would report 1350); deep p95 is the 10th of 10 = 29000 ms. Spend is
    40 x $0.01 + 10 x $0.05 = $0.90 over 47 successes.
    """
    samples = ([sample("ordinary", i, outcome="failed" if i >= 37 else "success")
                for i in range(40)]
               + [sample("deep", i, cost=0.05) for i in range(10)]
               + [sample("ingestion", i, cost=0.002, total_ms=5000) for i in range(5)])
    base = {"schema_version": "workload-measurement-1", "run_id": "load-1", "providers": "real",
            "environment": {"database": "postgresql", "workers": "independent_processes"},
            "started_at": "2026-10-21T00:00:00+00:00", "concurrency": 8,
            "workload_sha256": canonical_digest(workload), "samples": samples,
            "resources": {"peak_memory_mb": 900, "peak_connections": 40, "lock_waits": 3,
                          "max_lock_wait_ms": 120}}
    base.update(over)
    return base
