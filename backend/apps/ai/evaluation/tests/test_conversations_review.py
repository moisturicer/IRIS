"""IR-598 review fixes: guards, leakage breadth, locks, drafts, equal conditions, capacity."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.conversation_scoring import (
    TARGET_LABEL,
    ScoringError,
    check_conditions,
    cost_latency,
    score_reviews,
)
from apps.ai.evaluation.conversations import FAMILIES, split_digests, validate_set

from .test_conversation_scoring import data, review, run
from .test_conversations import conv, make_set


def test_a_conversation_without_an_id_is_an_error_not_a_crash():
    bad = conv("x")
    del bad["id"]
    other = conv("h", split="held_out", topic="o", papers=("Z",))
    errors = validate_set(make_set([bad, other]), min_conversations=1)["errors"]
    assert any("without an id" in e for e in errors)


def test_titles_in_pairs_and_evidence_count_towards_leakage():
    d = conv("d", topic="alpha", papers=("Only D",))
    h = conv("h", split="held_out", topic="omega", papers=("Only H",))
    h["turns"][0]["expected_pair"] = ["Only D", "Only H"]

    def kinds():
        report = validate_set(make_set([d, h]), min_conversations=1)
        return {(c["kind"], c["value"]) for c in report["leakage"]}

    assert ("paper", "only d") in kinds()
    h["turns"][0]["expected_pair"] = None
    h["turns"][0]["required_evidence"] = [{"title": "Only D", "page": 1, "quote": "q"}]
    assert ("paper", "only d") in kinds()


def test_topic_near_overlap_is_a_warning_not_an_error():
    d = conv("d", topic="early-universe galaxies and dust", papers=("P1",))
    h = conv("h", split="held_out", papers=("P2",),
             topic="large-scale structure and early-universe cosmology")
    report = validate_set(make_set([d, h]), min_conversations=1)
    assert report["errors"] == []
    (warning,) = report["warnings"]
    assert set(warning["words"]) == {"early", "universe"}
    far = conv("h2", split="held_out", topic="tilapia farming", papers=("P3",))
    assert validate_set(make_set([d, far]), min_conversations=1)["warnings"] == []


def rows(n, **extra):
    return [{"id": str(i), "latency_ms": 5, "cost": 1, "success": True, "cache": "cold", **extra}
            for i in range(n)]


def test_a_row_without_latency_is_counted_apart_and_stays_in_success_denominator():
    mixed = [{"id": "1", "latency_ms": 100, "cost": 1.0, "success": True, "cache": "cold"},
             {"id": "2", "cost": 1.0, "success": False, "cache": "cold"},
             {"id": "3", "latency_ms": None, "cost": 1.0, "success": False, "cache": "cold"}]
    cold = cost_latency(run("current", conversations=mixed))["cold"]
    assert cold["n"] == 3 and cold["no_latency_recorded"] == 2
    assert cold["p50"] == 100 and cold["cost_per_successful_task"] == 3.0


def test_capacity_is_verified_only_when_every_condition_holds():
    assert cost_latency(run("current", conversations=rows(100)))["capacity"] == "verified"
    short = cost_latency(run("current", conversations=rows(99)))
    assert short["capacity"] == "unverified" and "100" in short["capacity_reason"]
    dup = [dict(r, id="1") for r in rows(100)]
    assert cost_latency(run("current", conversations=dup))["capacity"] == "unverified"
    bare = run("current", conversations=rows(100), manifest={"campaign_approval_id": ""})
    assert "approval" in cost_latency(bare)["capacity_reason"]
    warm = cost_latency(run("current", conversations=rows(100, cache="warm")))
    assert warm["capacity"] == "unverified"
    every = cost_latency(run("current", providers="fake", capacity_fit=False,
                                 conversations=[], manifest={"campaign_approval_id": ""}))
    assert every["capacity_reason"].count(";") >= 3


def test_page_support_has_a_target_and_splits_are_reported():
    many = make_set([conv(f"k{i}", "A01", "development" if i % 2 else "held_out",
                          f"t{i}", (f"P{i}",)) for i in range(200)])
    out = score_reviews(many, [review(f"k{i}") for i in range(200)], arm="current")
    assert out["targets"]["page_support"]["label"] == TARGET_LABEL
    assert out["splits"]["development"]["reviewed"] == 100
    assert out["splits"]["held_out"]["task_completion"]["denominator"] == 100


def test_one_run_still_needs_a_complete_manifest_and_matching_set_digests():
    check_conditions({"current": run("current")}, mode="architecture")
    bare = run("current")
    del bare["manifest"]["data_policy"]
    with pytest.raises(ScoringError, match="data_policy"):
        check_conditions({"current": bare}, mode="architecture")
    digests = {"development": "x", "held_out": "y"}
    with pytest.raises(ScoringError, match="set_digests"):
        check_conditions({"current": run("current")}, mode="architecture", set_digests=digests)


def test_rubric_version_and_run_label_must_agree():
    other = {"rubric_version": 2}
    runs = {"current": run("current"), "controller": run("controller", manifest=other)}
    with pytest.raises(ScoringError, match="rubric_version"):
        check_conditions(runs, mode="architecture")
    with pytest.raises(ScoringError, match="label"):
        check_conditions({"mine": run("current")}, mode="architecture")
    with pytest.raises(ScoringError, match="rubric_version"):
        score_reviews(data(), [review("c0")], arm="current", rubric_version=2)


def _write(path, value):
    path.write_text(json.dumps(value))
    return str(path)


def test_a_lock_is_not_written_for_an_invalid_set(tmp_path):
    path = _write(tmp_path / "s.json", make_set([conv("a"), conv("a")]))
    lock = tmp_path / "lock.json"
    with pytest.raises(CommandError):
        call_command("eval_conversations", set=path, validate=True, min_conversations=1,
                     write_lock=str(lock))
    assert not lock.exists()


def _inputs(tmp_path, label_status="human_reviewed", digests=None):
    labelled = ["Ana"] if label_status == "human_reviewed" else []
    set_data = make_set([conv("c0", FAMILIES[0])], label_status=label_status,
                        labelled_by=labelled)
    path = _write(tmp_path / "s.json", set_data)
    lock = str(tmp_path / "lock.json")
    call_command("eval_conversations", set=path, validate=True, min_conversations=1,
                 write_lock=lock)
    mine = run("current", manifest={"set_digests": digests or split_digests(set_data)})
    return (path, lock, _write(tmp_path / "run.json", mine),
            _write(tmp_path / "r.json", [review("c0")]), str(tmp_path / "out"))


def test_score_needs_a_matching_lock(tmp_path):
    path, lock, run_path, rev, out = _inputs(tmp_path)
    args = dict(set=path, score=True, reviews=rev, out=out, runs=[f"current={run_path}"])
    with pytest.raises(CommandError, match="--lock"):
        call_command("eval_conversations", **args)
    call_command("eval_conversations", lock=lock, **args)
    edited = json.loads((tmp_path / "s.json").read_text())
    edited["conversations"][0]["topic"] = "edited"
    _write(tmp_path / "s.json", edited)
    with pytest.raises(CommandError, match="lock"):
        call_command("eval_conversations", lock=lock, **args)


def test_draft_labels_need_allow_draft_and_are_marked(tmp_path):
    path, lock, run_path, rev, out = _inputs(tmp_path, "draft_unreviewed")
    args = dict(set=path, score=True, reviews=rev, out=out, runs=[f"current={run_path}"],
                lock=lock)
    with pytest.raises(CommandError, match="allow-draft"):
        call_command("eval_conversations", **args)
    call_command("eval_conversations", allow_draft=True, **args)
    (written,) = (tmp_path / "out").iterdir()
    assert json.loads(written.read_text())["exploratory_draft_labels"] is True


def test_a_run_made_against_another_set_version_is_refused(tmp_path):
    path, lock, run_path, rev, out = _inputs(
        tmp_path, digests={"development": "x", "held_out": "y"})
    with pytest.raises(CommandError, match="set_digests"):
        call_command("eval_conversations", set=path, score=True, reviews=rev, out=out,
                     runs=[f"current={run_path}"], lock=lock)
