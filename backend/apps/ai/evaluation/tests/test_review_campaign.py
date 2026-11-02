"""IR-607: scoring at the run-file boundary with the committed review fixtures.

Expected numbers are counted by hand from fixtures/review/, not recomputed.
"""

import json
import shutil
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "review"


@pytest.fixture
def files(tmp_path):
    for name in ("set.json", "label_review.json", "run.json", "reviews.json", "packets.json"):
        shutil.copy(FIXTURES / name, tmp_path / name)
    lock = tmp_path / "lock.json"
    call_command("eval_conversations", set=str(tmp_path / "set.json"), validate=True,
                 min_conversations=1, write_lock=str(lock),
                 label_review=str(tmp_path / "label_review.json"))
    return tmp_path


def score(files, **extra):
    args = dict(set=str(files / "set.json"), score=True, lock=str(files / "lock.json"),
                runs=[f"controller={files / 'run.json'}"], reviews=str(files / "reviews.json"),
                label_review=str(files / "label_review.json"),
                packets=[str(files / "packets.json")], out=str(files / "out"))
    args.update(extra)
    shutil.rmtree(files / "out", ignore_errors=True)
    call_command("eval_conversations", **args)
    (written,) = (files / "out").iterdir()
    return json.loads(written.read_text())


def edit(path, change):
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def test_partial_unsupported_wrong_page_and_disagreement_are_scored_apart(files):
    out = score(files)
    scores = out["arms"]["controller"]["scores"]
    overall = scores["overall"]
    assert overall["reviewed"] == 6
    assert (overall["task_completion"]["numerator"], overall["task_completion"]["denominator"]) == (3, 4)
    assert overall["partial"]["numerator"] == 1
    assert (overall["claim_support"]["numerator"], overall["claim_support"]["denominator"]) == (5, 6)
    assert overall["citation_support"]["numerator"] == 6
    assert (overall["page_support"]["numerator"], overall["page_support"]["denominator"]) == (5, 6)
    assert scores["not_reviewed"] == ["R06"]
    assert scores["double_reviewed"] == 3
    r05 = scores["review_audit"]["R05"]
    assert r05["resolution"] == "adjudicated" and r05["adjudicated_by"] == "Fixture Adjudicator"
    assert [r["task_completion"] for r in r05["records"]] == ["yes", "no", "no"]


def test_diagnostic_stages_are_reported_beside_and_never_inside_verdicts(files):
    out = score(files)
    stages = out["arms"]["controller"]["diagnostics"]
    assert stages["stages"] == {"answered": 5, "candidates_then_no_results": 1,
                                "provider_failure": 1}
    assert stages["by_family"]["A09"]["candidates_then_no_results"] == 1
    assert "never overrides" in stages["note"]
    assert out["arms"]["controller"]["scores"]["review_audit"]["R05"]["resolution"] == "adjudicated"


def test_a_fixture_is_never_counted_and_counted_mode_refuses_it(files):
    out = score(files)
    assert out["counted"] is False
    reasons = " ".join(out["not_counted_reasons"])
    assert "fixture" in reasons and "fake" in reasons
    with pytest.raises(CommandError, match="fixture"):
        score(files, counted=True)


def test_counted_mode_needs_a_label_review_and_review_packets(files):
    with pytest.raises(CommandError, match="label review"):
        score(files, counted=True, label_review=None)
    with pytest.raises(CommandError, match="packets"):
        score(files, counted=True, packets=[])


def test_single_reviews_and_another_corpus_keep_a_score_uncounted(files):
    reasons = " ".join(score(files)["not_counted_reasons"])
    assert "3 conversations have one review, not two (R03, R04, R07)" in reasons
    edit(files / "run.json",
         lambda run: run["manifest"].update(corpus_snapshot_digest="another"))
    assert "corpus" in " ".join(score(files)["not_counted_reasons"])


def test_a_label_review_edited_after_locking_is_refused(files):
    edit(files / "label_review.json", lambda value: value.update(note="edited"))
    with pytest.raises(CommandError, match="recorded in the lock"):
        score(files)


def test_draft_labels_are_refused_for_a_counted_run(files):
    def to_draft(value):
        value["label_status"] = "draft_unreviewed"
        value["labelled_by"] = []

    edit(files / "set.json", to_draft)
    call_command("eval_conversations", set=str(files / "set.json"), validate=True,
                 min_conversations=1, write_lock=str(files / "lock.json"))
    with pytest.raises(CommandError, match="draft"):
        score(files, counted=True, allow_draft=True, label_review=None)


def test_review_evidence_outside_the_reviewers_packet_is_refused(files):
    edit(files / "reviews.json", lambda rows: rows[4]["claims"][0].update(record_id=999))
    with pytest.raises(CommandError, match="not authorized"):
        score(files)


def test_a_reviewer_without_a_packet_is_refused(files):
    edit(files / "packets.json", lambda bundles: bundles.pop(2))
    with pytest.raises(CommandError, match="packet"):
        score(files)


def held_out_review(rows):
    rows.append({"conversation": "H01", "arm": "controller", "reviewer": "Fixture Reviewer A",
                 "reviewer_kind": "human", "rubric_version": 1, "status": "reviewed",
                 "task_completion": "yes", "pair_usefulness": "na", "claims": [],
                 "unnecessary_clarification": False, "presentation_leak": False,
                 "access_breach": False, "no_answer": False})


def test_held_out_output_is_scored_only_after_prompts_and_rubric_froze(files):
    edit(files / "reviews.json", held_out_review)
    # The fixture run is stamped before this test's lock was written.
    with pytest.raises(CommandError, match="froze"):
        score(files, packets=[])
    edit(files / "run.json",
         lambda run: run["manifest"].update(timestamp_utc="2999-01-01T00:00:00+00:00"))
    out = score(files, packets=[])
    assert out["arms"]["controller"]["scores"]["splits"]["held_out"]["reviewed"] == 1
