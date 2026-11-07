"""IR-607: a reviewer's packet holds only what that reviewer may read."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.models import ChunkSet
from apps.ai.tests.corpus import FLOOD_TEXT, make_record, make_user
from apps.ai.tests.test_ai_runtime_research_db import write_source
from apps.records.models import Record
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


# --- A packet opened again after access changed (IR-721) ---------------------

def reopen(scene, email, name="Ana Reyes"):
    """Open a written packet again as `email`, who is the account that must still be allowed."""
    path = scene["out"].parent / "reopened.json"
    call_command("eval_review_packets", reopen=str(scene["out"]), reviewer=email,
                 reviewer_name=name, out=str(path))
    return json.loads(path.read_text())


def turns_of(bundle):
    return {p["conversation"]: p for p in bundle["packets"]}


def test_a_packet_reopened_after_its_source_was_revoked_withholds_the_turn(scene):
    make_user("ir721-reviewer@cit.edu")
    first = build(scene, "ir721-reviewer@cit.edu")
    assert turns_of(first)["D01"]["turns"][0]["answer"] == "Open finding [1]."

    # The public paper is pulled back to a draft after the packet was written.
    Record.objects.filter(pk=scene["public"].pk).update(pipeline_status=PipelineStatus.DRAFT)

    again = reopen(scene, "ir721-reviewer@cit.edu")
    d01 = turns_of(again)["D01"]
    assert d01["turns"][0]["withheld"] is True and d01["turns"][0]["answer"] is None
    assert d01["turns"][0]["citations"] == [] and d01["authorized_record_ids"] == []
    blob = json.dumps(again)
    assert "Open finding" not in blob and "Public Flood Study" not in blob
    # The same reviewer keeps their blank review and the run; the withheld turn keeps no question,
    # since a question can name what was removed.
    assert d01["review"] == turns_of(first)["D01"]["review"]
    assert d01["turns"][0]["question"] is None
    assert (again["run_id"], again["arm"], again["reviewer"]) == ("run-1", "controller", "Ana Reyes")
    # The packet that was written is not edited in place.
    assert "Open finding" in scene["out"].read_text()


def test_a_copied_packet_is_not_a_capability_for_records_its_new_holder_cannot_read(scene):
    first = build(scene, "ir607-owner@cit.edu", name="Owner")
    assert turns_of(first)["D02"]["turns"][0]["answer"] == "Hidden finding [1]."

    # The file is handed to another account: opening it is judged by that account's access.
    make_user("ir721-copied@cit.edu")
    copied = reopen(scene, "ir721-copied@cit.edu", name="Copied")
    blob = json.dumps(copied)
    assert "Hidden finding" not in blob and "Secret Draft Title" not in blob
    d02 = turns_of(copied)["D02"]
    assert d02["turns"][0]["withheld"] is True and d02["authorized_record_ids"] == []
    # What the new holder may read stays readable.
    assert turns_of(copied)["D01"]["turns"][0]["answer"] == "Open finding [1]."

    # The owner, opening it themselves, keeps their own draft.
    assert turns_of(reopen(scene, "ir607-owner@cit.edu", name="Owner"))["D02"]["turns"][0]["answer"] == "Hidden finding [1]."


def test_a_reopened_packet_never_restores_a_withheld_turn(scene):
    make_user("ir721-restore@cit.edu")
    build(scene, "ir721-restore@cit.edu")
    Record.objects.filter(pk=scene["public"].pk).update(pipeline_status=PipelineStatus.DRAFT)
    scene["out"].write_text(json.dumps(reopen(scene, "ir721-restore@cit.edu")))

    # Access returns; the withheld text is gone from the file and does not come back from it.
    Record.objects.filter(pk=scene["public"].pk).update(pipeline_status=PipelineStatus.PUBLISHED)
    again = turns_of(reopen(scene, "ir721-restore@cit.edu"))["D01"]
    assert again["turns"][0]["withheld"] is True and again["turns"][0]["answer"] is None
    assert again["authorized_record_ids"] == []


def test_opening_a_packet_needs_a_known_reviewer_and_a_source(scene):
    build(scene, "ir607-owner@cit.edu", name="Owner")
    with pytest.raises(CommandError, match="no user"):
        reopen(scene, "nobody@cit.edu", name="Owner")
    with pytest.raises(CommandError, match="--run or --reopen"):
        call_command("eval_review_packets", reviewer="ir607-owner@cit.edu",
                     out=str(scene["out"].parent / "none.json"))


def test_a_packet_reopened_after_its_source_was_replaced_withholds_the_turn(scene):
    make_user("ir721-replaced@cit.edu")
    first = build(scene, "ir721-replaced@cit.edu")
    d01 = turns_of(first)["D01"]["turns"][0]
    active = ChunkSet.objects.get(record=scene["public"], is_active=True)
    assert d01["revisions"] == {str(scene["public"].pk): active.pk}

    # Still readable, but its manuscript was replaced: the quoted revision is gone.
    write_source(scene["public"], {1: [("Methods", "a rewritten paragraph")]}, "2")
    again = turns_of(reopen(scene, "ir721-replaced@cit.edu"))["D01"]
    assert again["turns"][0]["withheld"] is True and again["authorized_record_ids"] == []
    assert "Open finding" not in json.dumps(again)


def test_a_source_read_without_a_citation_is_a_dependency_too(scene):
    run = json.loads(open(scene["run"]).read())
    uncited = run["conversations"][0]["turns"][0]
    uncited["public_answer"]["citations"] = []
    uncited["citation_record_ids"] = []
    uncited["public_answer"]["answer"] = "Secret Draft Title says nothing cited."
    uncited["source_ids"] = [scene["private"].pk]
    open(scene["run"], "w").write(json.dumps(run))
    make_user("ir721-uncited@cit.edu")
    d01 = turns_of(build(scene, "ir721-uncited@cit.edu"))["D01"]
    assert d01["turns"][0]["withheld"] is True
    assert "Secret Draft Title" not in json.dumps(d01)
    # The owner, who may read it, sees it and is authorized for it.
    owned = turns_of(build(scene, "ir607-owner@cit.edu", name="Owner"))["D01"]
    assert owned["turns"][0]["withheld"] is False
    assert owned["authorized_record_ids"] == [scene["private"].pk]


def test_another_reviewers_review_never_passes_to_a_new_holder(scene):
    first = build(scene, "ir607-owner@cit.edu", name="Owner")
    for packet in first["packets"]:
        packet["review"].update(status="reviewed", task_completion="yes",
                                claims=[{"record_id": scene["private"].pk, "supported": True}],
                                evidence_record_ids=[scene["private"].pk])
    scene["out"].write_text(json.dumps(first))

    make_user("ir721-holder@cit.edu")
    copied = reopen(scene, "ir721-holder@cit.edu", name="Holder")
    assert copied["reviewer"] == "Holder"
    for packet in copied["packets"]:
        review = packet["review"]
        assert review["reviewer"] == "Holder" and review["status"] == "not_reviewed"
        assert review["claims"] == [] and review["evidence_record_ids"] == []

    # The same reviewer keeps their own work, but only on what is still shown.
    Record.objects.filter(pk=scene["private"].pk).update(is_deleted=True)
    own = turns_of(reopen(scene, "ir607-owner@cit.edu", name="Owner"))
    assert own["D02"]["review"]["status"] == "reviewed"
    assert own["D02"]["review"]["claims"] == [] and own["D02"]["review"]["evidence_record_ids"] == []


def test_reopen_needs_a_reviewer_name_and_takes_no_lock(scene, tmp_path):
    build(scene, "ir607-owner@cit.edu", name="Owner")
    with pytest.raises(CommandError, match="reviewer name"):
        call_command("eval_review_packets", reopen=str(scene["out"]),
                     reviewer="ir607-owner@cit.edu", out=str(tmp_path / "x.json"))
    with pytest.raises(CommandError, match="--lock applies to --run"):
        call_command("eval_review_packets", reopen=str(scene["out"]), reviewer="ir607-owner@cit.edu",
                     reviewer_name="Owner", lock=str(tmp_path / "lock.json"),
                     out=str(tmp_path / "x.json"))
