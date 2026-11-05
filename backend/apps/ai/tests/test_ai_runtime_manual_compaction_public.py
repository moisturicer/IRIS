"""What a reader sees of a manual compaction (IR-754, ADR-049 §19, §21).

The allowlisted projection alone, with no database: live, reconnected and
reopened views are all `public.run`, so one shape has to say what happened.
"""

import json

from ai.runs import public

BASE = {k: None for k in ("id", "conversation_id", "state", "base_revision", "version", "turn_id",
                          "depth", "awaiting_reader", "created_at", "finished_at")}


def snapshot(**kw):
    return {**BASE, "question": "Which water papers?", "events": [], **kw}


def event(name, **data):
    return {"name": name, "data": data}


def test_an_ordinary_run_is_an_ask_and_a_compaction_run_says_so():
    assert public.run(snapshot())["kind"] == "ask"
    assert public.run(snapshot(pinned={"executor": "agent"}))["kind"] == "ask"
    compact = public.run(snapshot(question=None, pinned={"kind": "compact", "executor": "agent"}))
    assert compact["kind"] == "compact"
    # It asks nothing, so there is no question to show and none to invent.
    assert compact["question"] == ""


def test_an_unknown_kind_is_never_published():
    assert public.run(snapshot(pinned={"kind": "something-new"}))["kind"] == "ask"


def test_the_pin_itself_is_not_published():
    text = json.dumps(public.run(snapshot(pinned={"kind": "compact", "executor": "agent", "bounds": {"x": 1}})))
    assert "executor" not in text and "bounds" not in text and "pinned" not in text


def test_manual_compaction_is_offered_only_where_the_service_can_do_it():
    assert public.run(snapshot())["capabilities"] == {"manual_compaction": False}
    assert public.run(snapshot(), manual_compaction=True)["capabilities"] == {"manual_compaction": True}


def test_the_conversation_carries_the_same_capability_on_every_run():
    runs = [snapshot(id="a", sources_available=True), snapshot(id="b", sources_available=True)]
    shown = public.conversation({"id": "c", "revision": 2, "runs": runs, "turns": []}, manual_compaction=True)
    assert [r["capabilities"] for r in shown["runs"]] == [{"manual_compaction": True}] * 2
    off = public.conversation({"id": "c", "revision": 2, "runs": runs, "turns": []})
    assert [r["capabilities"] for r in off["runs"]] == [{"manual_compaction": False}] * 2


def test_a_compaction_a_restarted_worker_journals_again_counts_once():
    shown = public.progress([
        event("compaction", outcome="compacted", revision=2, turns=3, exchanges=0),
        event("compaction", outcome="compacted", revision=2, turns=0, exchanges=0),
    ])["compaction"]
    assert shown == {"compactions": 1, "turns_compacted": 3, "last": "compacted"}


def test_nothing_older_to_condense_is_a_kept_outcome_with_no_counts():
    shown = public.progress([event("compaction", outcome="kept", reason="nothing_to_compact")])["compaction"]
    # The reason is the operator's; the reader's view carries the outcome and counts only.
    assert shown == {"compactions": 0, "turns_compacted": 0, "last": "kept"}
