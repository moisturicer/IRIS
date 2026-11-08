"""IR-607, IR-721: a reviewer's packet holds no text, and shows only what that reviewer may read."""

import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.review_packets import build_packets
from apps.ai.models import ChunkSet
from apps.ai.tests.corpus import FLOOD_TEXT, make_record, make_user
from apps.ai.tests.test_ai_runtime_research_db import write_source
from apps.records.models import Record
from core.enums import PipelineStatus

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

#: Every piece of text a run holds for the two conversations below.
TEXT = ("What does it find?", "Open finding", "Hidden finding", "Public Flood Study",
        "Secret Draft Title", "quoted")


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
                 out=str(scene["out"]), stdout=io.StringIO())
    return json.loads(scene["out"].read_text())


def show(scene, email, name="Ana Reyes", packet=None):
    """Render the packet for `email` now: the only place its text appears."""
    out = io.StringIO()
    call_command("eval_review_packets", show=str(packet or scene["out"]), run=scene["run"],
                 reviewer=email, reviewer_name=name, stdout=out)
    return {c["conversation"]: c for c in json.loads(out.getvalue())}


def reopen(scene, email, name="Ana Reyes"):
    path = scene["out"].parent / "reopened.json"
    call_command("eval_review_packets", reopen=str(scene["out"]), reviewer=email,
                 reviewer_name=name, out=str(path), stdout=io.StringIO())
    return json.loads(path.read_text())


def packets_of(bundle):
    return {p["conversation"]: p for p in bundle["packets"]}


def assert_no_text(blob):
    for text in TEXT:
        assert text not in blob, text


# --- A packet holds no text --------------------------------------------------

def test_a_packet_file_holds_no_text_only_ids_pages_and_a_blank_review(scene):
    make_user("ir607-reviewer@cit.edu")
    bundle = build(scene, "ir607-reviewer@cit.edu")
    assert_no_text(json.dumps(bundle))
    d01 = packets_of(bundle)["D01"]
    (shown,) = d01["turns"]
    assert shown["withheld"] is False
    assert shown["citations"] == [{"marker": 1, "record_id": scene["public"].pk, "page": 3}]
    assert d01["authorized_record_ids"] == [scene["public"].pk]
    assert bundle["run_sha256"] and "not stored" in bundle["text"]
    for private in ("diagnostics", "physical_attempts", "saved_turn", "reopened_transcript",
                    "research_runs"):
        assert private not in json.dumps(bundle)
    review = d01["review"]
    assert review["status"] == "not_reviewed" and review["reviewer"] == "Ana Reyes"
    assert review["task_completion"] is None and review["access_breach"] is None


def test_the_reviewer_reads_the_turns_only_by_rendering_them(scene):
    make_user("ir607-reviewer@cit.edu")
    build(scene, "ir607-reviewer@cit.edu")
    rendered = show(scene, "ir607-reviewer@cit.edu")
    (shown,) = rendered["D01"]["turns"]
    assert shown["question"] == "What does it find?" and shown["answer"] == "Open finding [1]."
    assert shown["citations"] == [{"marker": 1, "record_id": scene["public"].pk,
                                   "record_title": "Public Flood Study", "page": 3,
                                   "text": "Open finding quoted"}]
    # The draft the reviewer cannot read renders nothing, and leaves nothing on disk.
    assert rendered["D02"]["turns"] == [{"number": 1, "withheld": True}]
    assert "Hidden finding" not in json.dumps(rendered)
    assert_no_text(scene["out"].read_text())


def test_the_owner_may_review_their_own_draft(scene):
    bundle = build(scene, "ir607-owner@cit.edu", name="Owner")
    assert packets_of(bundle)["D02"]["authorized_record_ids"] == [scene["private"].pk]
    assert show(scene, "ir607-owner@cit.edu", "Owner")["D02"]["turns"][0]["answer"] == \
        "Hidden finding [1]."


def test_rendering_refuses_a_run_file_other_than_the_one_the_packet_pins(scene):
    build(scene, "ir607-owner@cit.edu", name="Owner")
    run = json.loads(open(scene["run"]).read())
    run["conversations"][0]["turns"][0]["public_answer"]["answer"] = "Swapped text"
    open(scene["run"], "w").write(json.dumps(run))
    with pytest.raises(CommandError, match="not the one this packet was built from"):
        show(scene, "ir607-owner@cit.edu", "Owner")


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


def test_an_unknown_reviewer_and_missing_arguments_are_refused(scene, tmp_path):
    with pytest.raises(CommandError, match="no user"):
        build(scene, "nobody@cit.edu")
    build(scene, "ir607-owner@cit.edu", name="Owner")
    with pytest.raises(CommandError, match="one of --run, --reopen or --show"):
        call_command("eval_review_packets", reviewer="ir607-owner@cit.edu", reviewer_name="O")
    with pytest.raises(CommandError, match="reviewer name"):
        call_command("eval_review_packets", reopen=str(scene["out"]),
                     reviewer="ir607-owner@cit.edu", out=str(tmp_path / "x.json"))
    with pytest.raises(CommandError, match="--lock applies to --run"):
        call_command("eval_review_packets", reopen=str(scene["out"]), reviewer="ir607-owner@cit.edu",
                     reviewer_name="Owner", lock=str(tmp_path / "lock.json"),
                     out=str(tmp_path / "x.json"))
    with pytest.raises(CommandError, match="--show needs --run"):
        call_command("eval_review_packets", show=str(scene["out"]), reviewer="ir607-owner@cit.edu",
                     reviewer_name="Owner")


# --- Access is judged again at every opening (IR-721) ------------------------

def test_a_packet_rendered_after_its_source_was_revoked_withholds_the_turn(scene):
    make_user("ir721-reviewer@cit.edu")
    build(scene, "ir721-reviewer@cit.edu")
    assert show(scene, "ir721-reviewer@cit.edu")["D01"]["turns"][0]["withheld"] is False

    Record.objects.filter(pk=scene["public"].pk).update(pipeline_status=PipelineStatus.DRAFT)

    rendered = show(scene, "ir721-reviewer@cit.edu")
    assert rendered["D01"]["turns"] == [{"number": 1, "withheld": True}]
    assert_no_text(json.dumps(rendered))
    again = packets_of(reopen(scene, "ir721-reviewer@cit.edu"))["D01"]
    assert again["turns"][0]["withheld"] is True and again["authorized_record_ids"] == []


def test_a_copied_packet_is_not_a_capability_for_records_its_new_holder_cannot_read(scene):
    build(scene, "ir607-owner@cit.edu", name="Owner")
    make_user("ir721-copied@cit.edu")
    rendered = show(scene, "ir721-copied@cit.edu", "Copied")
    assert rendered["D02"]["turns"] == [{"number": 1, "withheld": True}]
    assert "Hidden finding" not in json.dumps(rendered)
    assert rendered["D01"]["turns"][0]["answer"] == "Open finding [1]."
    # Blanking the packet's references does not unlock a turn: a turn with no recorded
    # revisions is never rendered.
    bundle = json.loads(scene["out"].read_text())
    for t in packets_of(bundle)["D02"]["turns"]:
        t.update(record_ids=[], citations=[], revisions={})
    edited = scene["out"].parent / "edited.json"
    edited.write_text(json.dumps(bundle))
    forged = show(scene, "ir721-copied@cit.edu", "Copied", packet=edited)
    assert "Hidden finding" not in json.dumps(forged)


def test_a_withheld_turn_is_never_restored(scene):
    make_user("ir721-restore@cit.edu")
    build(scene, "ir721-restore@cit.edu")
    Record.objects.filter(pk=scene["public"].pk).update(pipeline_status=PipelineStatus.DRAFT)
    scene["out"].write_text(json.dumps(reopen(scene, "ir721-restore@cit.edu")))

    Record.objects.filter(pk=scene["public"].pk).update(pipeline_status=PipelineStatus.PUBLISHED)
    assert show(scene, "ir721-restore@cit.edu")["D01"]["turns"] == [{"number": 1, "withheld": True}]


def test_a_replaced_source_withholds_the_turn(scene):
    make_user("ir721-replaced@cit.edu")
    bundle = build(scene, "ir721-replaced@cit.edu")
    active = ChunkSet.objects.get(record=scene["public"], is_active=True)
    assert packets_of(bundle)["D01"]["turns"][0]["revisions"] == {str(scene["public"].pk): active.pk}

    write_source(scene["public"], {1: [("Methods", "a rewritten paragraph")]}, "2")
    assert show(scene, "ir721-replaced@cit.edu")["D01"]["turns"] == [{"number": 1, "withheld": True}]


def test_a_source_read_without_a_citation_is_a_dependency_too(scene):
    run = json.loads(open(scene["run"]).read())
    uncited = run["conversations"][0]["turns"][0]
    uncited["public_answer"]["citations"] = []
    uncited["citation_record_ids"] = []
    uncited["public_answer"]["answer"] = "Secret Draft Title says nothing cited."
    uncited["source_ids"] = [scene["private"].pk]
    open(scene["run"], "w").write(json.dumps(run))
    make_user("ir721-uncited@cit.edu")
    build(scene, "ir721-uncited@cit.edu")
    assert show(scene, "ir721-uncited@cit.edu")["D01"]["turns"] == [{"number": 1, "withheld": True}]
    owned = packets_of(build(scene, "ir607-owner@cit.edu", name="Owner"))["D01"]
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

    Record.objects.filter(pk=scene["private"].pk).update(is_deleted=True)
    own = packets_of(reopen(scene, "ir607-owner@cit.edu", name="Owner"))
    assert own["D02"]["review"]["status"] == "reviewed"
    assert own["D02"]["review"]["claims"] == [] and own["D02"]["review"]["evidence_record_ids"] == []


def test_build_packets_alone_keeps_no_text():
    run = {"run_id": "r", "arm": "runtime", "manifest": {"rubric_version": 1}, "conversations": [
        {"id": "C", "family": "A01", "turns": [{
            "number": 1, "question": "Q text", "outcome": "answered",
            "public_answer": {"answer": "A text", "citations": [
                {"marker": 1, "record_id": 5, "record_title": "T text", "page": 2, "text": "X"}]},
            "citation_record_ids": [5], "source_ids": [5]}]}]}
    blob = json.dumps(build_packets(run, reviewer="R", readable={5}, revisions={5: 1}))
    for text in ("Q text", "A text", "T text", '"X"'):
        assert text not in blob
