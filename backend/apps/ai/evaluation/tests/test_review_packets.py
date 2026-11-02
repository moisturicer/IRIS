"""IR-607: a reviewer's packet holds only what that reviewer may read."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.tests.corpus import FLOOD_TEXT, make_record, make_user
from core.enums import PipelineStatus

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def turn(record, text):
    return {"number": 1, "question": "What does it find?", "outcome": "answered",
            "public_answer": {"answer": f"{text} [1].", "citations": [{
                "marker": 1, "record_id": record.pk, "record_title": record.title,
                "page": 3, "text": f"{text} quoted", "chunk_id": 1}],
                "sources": [{"id": record.pk, "title": record.title}]},
            "citation_record_ids": [record.pk], "source_ids": [record.pk],
            "saved_turn": {"id": 9, "question": "What does it find?"},
            "reopened_transcript": [{"id": 9}], "physical_attempts": [{"id": 1}],
            "diagnostics": {"stage": "answered", "research_runs": []}}


@pytest.fixture
def scene(embedder, space, tmp_path):
    owner = make_user("ir607-owner@cit.edu")
    public = make_record(title="Public Flood Study", text=FLOOD_TEXT, embedder=embedder,
                         space=space)
    private = make_record(title="Secret Draft Title", text=FLOOD_TEXT, embedder=embedder,
                          space=space, status=PipelineStatus.DRAFT, owner=owner)
    run = {"run_id": "run-1", "arm": "controller", "manifest": {"rubric_version": 1},
           "conversations": [
               {"id": "D01", "family": "A01", "split": "development",
                "turns": [turn(public, "Open finding")]},
               {"id": "D02", "family": "A08", "split": "development",
                "turns": [turn(private, "Hidden finding")]}]}
    path = tmp_path / "run.json"
    path.write_text(json.dumps(run))
    return {"run": str(path), "out": tmp_path / "packets.json", "public": public,
            "private": private, "owner": owner}


def build(scene, email, name="Ana Reyes"):
    call_command("eval_review_packets", run=scene["run"], reviewer=email, reviewer_name=name,
                 out=str(scene["out"]))
    return json.loads(scene["out"].read_text())


def test_a_reviewer_sees_the_answer_and_citations_they_may_read(scene):
    make_user("ir607-reviewer@cit.edu")
    bundle = build(scene, "ir607-reviewer@cit.edu")
    assert (bundle["reviewer"], bundle["run_id"], bundle["arm"]) == ("Ana Reyes", "run-1",
                                                                     "controller")
    d01 = {p["conversation"]: p for p in bundle["packets"]}["D01"]
    (shown,) = d01["turns"]
    assert shown["answer"] == "Open finding [1]."
    assert shown["citations"] == [{"marker": 1, "record_id": scene["public"].pk,
                                   "record_title": "Public Flood Study", "page": 3,
                                   "text": "Open finding quoted"}]
    assert d01["authorized_record_ids"] == [scene["public"].pk]


def test_a_source_the_reviewer_cannot_read_is_withheld_with_the_answer(scene):
    make_user("ir607-reviewer2@cit.edu")
    bundle = build(scene, "ir607-reviewer2@cit.edu")
    blob = json.dumps(bundle)
    assert "Secret Draft Title" not in blob and "Hidden finding" not in blob
    d02 = {p["conversation"]: p for p in bundle["packets"]}["D02"]
    assert d02["turns"][0]["answer"] is None and d02["turns"][0]["withheld"] is True
    assert d02["authorized_record_ids"] == []


def test_the_owner_may_review_their_own_draft(scene):
    bundle = build(scene, "ir607-owner@cit.edu", name="Owner")
    d02 = {p["conversation"]: p for p in bundle["packets"]}["D02"]
    assert d02["turns"][0]["answer"] == "Hidden finding [1]."
    assert d02["authorized_record_ids"] == [scene["private"].pk]


def test_packets_hold_no_diagnostics_history_or_usage_and_a_blank_template(scene):
    make_user("ir607-reviewer3@cit.edu")
    bundle = build(scene, "ir607-reviewer3@cit.edu")
    blob = json.dumps(bundle)
    for private in ("diagnostics", "physical_attempts", "saved_turn", "reopened_transcript",
                    "research_runs"):
        assert private not in blob
    template = {p["conversation"]: p for p in bundle["packets"]}["D01"]["review"]
    assert template["status"] == "not_reviewed" and template["reviewer"] == "Ana Reyes"
    assert template["reviewer_kind"] == "human" and template["rubric_version"] == 1
    assert template["task_completion"] is None and template["access_breach"] is None


def test_held_out_output_is_not_packaged_before_the_lock_froze(scene, tmp_path):
    make_user("ir607-reviewer4@cit.edu")
    run = json.loads(open(scene["run"]).read())
    run["conversations"][0]["split"] = "held_out"
    run["manifest"]["timestamp_utc"] = "2026-10-01T00:00:00+00:00"
    open(scene["run"], "w").write(json.dumps(run))
    with pytest.raises(CommandError, match="held-out"):
        build(scene, "ir607-reviewer4@cit.edu")
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"locked_at": "2026-10-02T00:00:00+00:00"}))
    with pytest.raises(CommandError, match="held-out"):
        call_command("eval_review_packets", run=scene["run"], reviewer="ir607-reviewer4@cit.edu",
                     reviewer_name="Ana", out=str(scene["out"]), lock=str(lock))
    lock.write_text(json.dumps({"locked_at": "2026-09-30T00:00:00+00:00"}))
    call_command("eval_review_packets", run=scene["run"], reviewer="ir607-reviewer4@cit.edu",
                 reviewer_name="Ana", out=str(scene["out"]), lock=str(lock))


def test_an_unknown_reviewer_is_refused(scene):
    with pytest.raises(CommandError, match="no user"):
        build(scene, "nobody@cit.edu")
