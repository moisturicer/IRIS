"""IR-607: locks pin corpus and rubric; A09 and a named label review gate the lock."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.conversations import (
    check_label_review,
    check_lock,
    lock_record,
    split_digests,
    validate_set,
)

from .test_conversations import conv, make_set


def a09(cid, case, split="development"):
    return conv(cid, "A09", split, topic=f"t-{cid}", papers=(f"P-{cid}",), a09_case=case)


def a09_set(cases=("missing_field", "no_match", "outage"), **extra):
    rows = [a09(f"a{i}", c) for i, c in enumerate(cases)]
    rows.append(conv("h", split="held_out", topic="other", papers=("Z",)))
    return make_set(rows, **extra)


def test_a_changed_corpus_snapshot_or_rubric_invalidates_the_lock():
    data = a09_set()
    lock = lock_record(data)
    assert check_lock(data, lock) == []
    moved = dict(data, corpus={"snapshot_id": "c", "paper_set_sha256": "other"})
    assert check_lock(moved, lock) == ["corpus"]
    assert check_lock(dict(data, rubric_version=2), lock) == ["rubric_version"]


def test_a_lock_written_before_corpus_pinning_is_stale():
    data = a09_set()
    old = {k: v for k, v in lock_record(data).items() if k in ("set_id", "development", "held_out")}
    assert "corpus" in check_lock(data, old)


def test_a09_must_keep_three_distinct_outcomes_before_locking():
    assert validate_set(a09_set(), min_conversations=1)["lock_blockers"] == []
    blockers = validate_set(a09_set(("no_match", "no_match")), min_conversations=1)["lock_blockers"]
    assert any("missing_field" in b and "outage" in b for b in blockers)
    unknown = validate_set(a09_set(("missing_field", "no_match", "outage", "typo")),
                           min_conversations=1)
    assert any("typo" in e for e in unknown["errors"])


def _write(path, value):
    path.write_text(json.dumps(value))
    return str(path)


def test_write_lock_refuses_while_a09_is_unbalanced(tmp_path):
    path = _write(tmp_path / "s.json", a09_set(("outage",)))
    lock = tmp_path / "l.json"
    with pytest.raises(CommandError, match="A09"):
        call_command("eval_conversations", set=path, validate=True, min_conversations=1,
                     write_lock=str(lock))
    assert not lock.exists()


def label_review(data, **extra):
    base = {
        "set_id": data["set_id"], "reviewer": "Ana Reyes", "fixture": False,
        "corpus": data["corpus"], "set_digests": split_digests(data),
        "conversations": {c["id"]: {"status": "confirmed", "checks": {
            "category_names": True, "exact_counts": "not_applicable",
            "paper_page_facts": True, "supported_unambiguous": True}}
            for c in data["conversations"]},
    }
    base.update(extra)
    return base


def test_a_label_review_must_cover_every_conversation_by_a_labeller():
    data = a09_set(label_status="human_reviewed", labelled_by=["Ana Reyes"])
    assert check_label_review(data, label_review(data)) == []
    partial = label_review(data)
    partial["conversations"]["a0"]["status"] = "not_reviewed"
    assert any("a0" in p for p in check_label_review(data, partial))
    failed = label_review(data)
    failed["conversations"]["a1"]["checks"]["paper_page_facts"] = False
    assert any("a1" in p and "paper_page_facts" in p for p in check_label_review(data, failed))
    missing = label_review(data)
    del missing["conversations"]["h"]
    assert any("h" in p for p in check_label_review(data, missing))
    assert any("labelled_by" in p for p in check_label_review(
        data, label_review(data, reviewer="Bo")))


def test_a_label_review_of_another_set_version_or_corpus_is_stale():
    data = a09_set(label_status="human_reviewed", labelled_by=["Ana Reyes"])
    review = label_review(data)
    edited = json.loads(json.dumps(data))
    edited["conversations"][0]["turns"][0]["user"] = "Changed question"
    assert any("digest" in p for p in check_label_review(edited, review))
    moved = dict(data, corpus={"snapshot_id": "c2", "paper_set_sha256": "y"})
    assert any("corpus" in p for p in check_label_review(moved, review))


def test_a_supplied_label_review_must_pass_before_the_lock_is_written(tmp_path):
    data = a09_set(label_status="human_reviewed", labelled_by=["Ana Reyes"])
    path = _write(tmp_path / "s.json", data)
    lock = tmp_path / "l.json"
    args = dict(set=path, validate=True, min_conversations=1, write_lock=str(lock))
    stale = label_review(data, set_digests={"development": "x", "held_out": "y"})
    with pytest.raises(CommandError, match="label review"):
        call_command("eval_conversations", label_review=_write(tmp_path / "r0.json", stale),
                     **args)
    call_command("eval_conversations",
                 label_review=_write(tmp_path / "r.json", label_review(data)), **args)
    written = json.loads(lock.read_text())
    assert check_lock(data, written) == [] and written["locked_at"]
    assert written["label_review"]["reviewer"] == "Ana Reyes"
