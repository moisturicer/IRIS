"""IR-598: the conversation set's schema, leakage, coverage and locks. Pure."""

import copy

from apps.ai.evaluation.conversations import (
    FAMILIES,
    check_lock,
    lock_record,
    split_digests,
    validate_set,
)


def conv(cid, family="A01", split="development", topic="floods", papers=("Paper A",),
         **extra):
    base = {
        "id": cid, "family": family, "split": split, "topic": topic,
        "papers": list(papers), "supported_unambiguous": True,
        "turns": [{
            "user": "Compare them", "intended_task": "compare",
            "expected_pair": [papers[0]],
            "required_evidence": [{"title": papers[0], "page": 2, "quote": "q"}],
            "clarification_necessary": False, "acceptable_uncertainty": None,
        }],
    }
    base.update(extra)
    return base


def make_set(conversations, **extra):
    data = {
        "schema_version": 1, "set_id": "s", "label_status": "draft_unreviewed",
        "labelled_by": [], "corpus": {"snapshot_id": "c", "paper_set_sha256": "x"},
        "conversations": conversations,
    }
    data.update(extra)
    return data


def full():
    out = []
    for i, family in enumerate(FAMILIES):
        out.append(conv(f"d{i}", family, "development", f"dev-topic-{i}", (f"Dev {i}",)))
        out.append(conv(f"h{i}", family, "held_out", f"held-topic-{i}", (f"Held {i}",)))
    return out


def test_a_clean_set_has_per_family_counts_and_no_errors():
    report = validate_set(make_set(full()), min_conversations=1)
    assert report["errors"] == []
    assert report["counts"]["development"]["A01"] == 1
    assert report["counts"]["held_out"]["A15"] == 1
    assert report["supported_unambiguous"] == 30
    assert report["coverage_gaps"] == []


def test_duplicate_ids_unknown_family_and_bad_split_are_errors():
    data = make_set([conv("x"), conv("x"), conv("y", "A99"), conv("z", split="test")])
    text = " ".join(validate_set(data, min_conversations=1)["errors"])
    assert "duplicate id x" in text
    assert "unknown family A99" in text
    assert "unknown split" in text


def test_readiness_needs_the_minimum_and_empty_families_are_gaps():
    report = validate_set(make_set([conv("a")]))
    assert any("fewer than 100" in e for e in report["errors"])
    assert "A02" in report["coverage_gaps"]
    assert report["ready"] is False


def test_every_leakage_collision_is_reported():
    data = make_set([
        conv("d", split="development", topic="Floods", papers=("Paper A", "Paper B")),
        conv("h", split="held_out", topic=" floods ", papers=("paper a", "Paper B")),
    ])
    report = validate_set(data, min_conversations=1)
    kinds = {(c["kind"], c["value"]) for c in report["leakage"]}
    assert kinds == {("topic", "floods"), ("paper", "paper a"), ("paper", "paper b")}
    assert report["errors"]


def test_shared_allowed_needs_a_reason_and_is_reported_as_such():
    data = make_set(
        [conv("d", topic="t1", papers=("P",)),
         conv("h", split="held_out", topic="t2", papers=("P",))],
        shared_allowed=[{"kind": "paper", "value": "P", "reason": "only fixture"}])
    report = validate_set(data, min_conversations=1)
    assert report["leakage"] == []
    assert report["allowed_shared"][0]["reason"] == "only fixture"
    data["shared_allowed"][0]["reason"] = ""
    assert any("reason" in e for e in validate_set(data, min_conversations=1)["errors"])


def test_label_status_rules():
    data = make_set([conv("a")], label_status="human_reviewed", labelled_by=[])
    assert any("labelled_by" in e for e in validate_set(data, min_conversations=1)["errors"])
    data["label_status"] = "weird"
    assert any("label_status" in e for e in validate_set(data, min_conversations=1)["errors"])


def test_turn_labels_are_required():
    bad = conv("a")
    del bad["turns"][0]["intended_task"]
    errors = validate_set(make_set([bad]), min_conversations=1)["errors"]
    assert any("intended_task" in e for e in errors)
    empty = conv("b", turns=[])
    assert any("no turns" in e for e in validate_set(make_set([empty]), min_conversations=1)["errors"])


def test_digests_detect_edits_and_moves_and_ignore_order():
    data = make_set(full())
    base = split_digests(data)
    shuffled = copy.deepcopy(data)
    shuffled["conversations"].reverse()
    assert split_digests(shuffled) == base
    edited = copy.deepcopy(data)
    edited["conversations"][1]["turns"][0]["user"] = "changed"
    assert split_digests(edited)["held_out"] != base["held_out"]
    assert split_digests(edited)["development"] == base["development"]
    moved = copy.deepcopy(data)
    moved["conversations"][1]["split"] = "development"
    assert split_digests(moved)["development"] != base["development"]


def test_lock_check_passes_then_fails_after_a_held_out_edit():
    data = make_set(full())
    lock = lock_record(data)
    assert check_lock(data, lock) == []
    data["conversations"][1]["topic"] = "moved"
    assert check_lock(data, lock) == ["held_out"]
    assert check_lock(data, {**lock_record(data), "set_id": "other"}) == ["set_id"]
