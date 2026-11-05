"""What a reconnecting reader is replayed of a run's journal (IR-726, ADR-049 §2, §21).

The allowlisted projection alone, with no database: the cursor is a position in
the journal, the replay is ordered and safe, and nothing private rides along.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.runs import public  # noqa: E402

BASE = {k: None for k in ("id", "conversation_id", "state", "base_revision", "version", "turn_id",
                          "depth", "awaiting_reader", "created_at", "finished_at")}
STEP = {"id": "compare", "title": "Compare the findings", "status": "in_progress"}


def snapshot(events, **kw):
    return {**BASE, "question": "Which water papers?", "pinned": {},
            "events": [{"sequence": n, "name": name, "data": data}
                       for n, (name, data) in enumerate(events, start=1)], **kw}


JOURNAL = [
    ("admitted", {}),
    ("started", {"attempt": 1}),
    ("tool", {"name": "search", "sources": ["1:abc"], "arguments": {"q": "private query"}}),
    ("plan", {"revision": 1, "steps": [STEP]}),
    ("model", {"phase": "final", "model": "scripted-model", "reasoning": "private working"}),
    ("context", {"used_tokens": 10, "capacity_tokens": 100}),
    ("completed", {"reason": "answered"}),
]


def test_a_reader_with_no_cursor_gets_none_and_a_cursor_at_the_end_of_what_it_may_see():
    shown = public.run(snapshot(JOURNAL))
    assert "journal" not in shown
    # Seven operator events, five the reader may see: the cursor counts only those.
    assert shown["cursor"] == 5


def test_a_cursor_replays_only_what_came_after_it_in_order():
    after_start = public.run(snapshot(JOURNAL), after=2)
    assert [e["position"] for e in after_start["journal"]] == [3, 4, 5]
    assert [e["name"] for e in after_start["journal"]] == ["plan", "context", "completed"]
    assert after_start["cursor"] == 5
    # Reconnecting at the end replays nothing and keeps the position.
    caught_up = public.run(snapshot(JOURNAL), after=5)
    assert caught_up["journal"] == [] and caught_up["cursor"] == 5


def test_a_position_says_nothing_of_the_operators_events_between_two_entries():
    quiet = [("admitted", {}), ("started", {}), ("completed", {})]
    busy = [("admitted", {}), ("started", {}), *[("tool", {"name": "search"})] * 40, ("completed", {})]
    assert public.run(snapshot(quiet), after=0)["journal"] == public.run(snapshot(busy), after=0)["journal"]
    assert public.run(snapshot(quiet))["cursor"] == public.run(snapshot(busy))["cursor"] == 3


def test_the_full_replay_carries_validated_progress_and_lifecycle_names_alone():
    full = public.run(snapshot(JOURNAL), after=0)
    assert full["journal"] == [
        {"position": 1, "name": "admitted"},
        {"position": 2, "name": "started"},
        {"position": 3, "name": "plan", "revision": 1, "steps": [STEP]},
        {"position": 4, "name": "context", "estimated": True, "used_tokens": 10, "capacity_tokens": 100},
        {"position": 5, "name": "completed"},
    ]
    text = json.dumps(full)
    for private in ("private query", "private working", "scripted-model", "1:abc", "answered", "attempt", "tool"):
        assert private not in text


def test_replay_and_folded_progress_agree_wherever_the_reader_reconnects():
    whole = public.run(snapshot(JOURNAL))
    partial = public.run(snapshot(JOURNAL), after=4)
    # The folded plan and context are the run's, not the slice's.
    assert partial["plan"] == whole["plan"] == {"revision": 1, "steps": [STEP]}
    assert partial["context"] == whole["context"]


def test_an_invalid_progress_event_is_not_replayed():
    bad = snapshot([("plan", {"revision": 0, "steps": []}), ("context", {"used_tokens": 9, "capacity_tokens": 1}),
                    ("compaction", {"outcome": "mystery"})])
    assert public.run(bad, after=0)["journal"] == []
    assert public.run(bad, after=0)["cursor"] == 0


def test_a_compaction_replays_its_outcome_and_count_but_never_a_reason_or_revision():
    shown = public.run(snapshot([("compaction", {"outcome": "compacted", "revision": 4, "turns": 3,
                                                  "reason": "nothing_to_compact"})]), after=0)
    assert shown["journal"] == [{"position": 1, "name": "compaction", "outcome": "compacted", "turns": 3}]


def test_a_run_whose_sources_are_gone_replays_nothing():
    shown = public.run(snapshot(JOURNAL, sources_available=False), after=0)
    assert shown["journal"] == [] and shown["cursor"] == 0
    assert shown["plan"] is None


def test_the_retry_link_is_published_both_ways_and_nothing_else_about_it():
    shown = public.run(snapshot([], retry_of="run-1", retried_by="run-3"))
    assert (shown["retry_of"], shown["retried_by"]) == ("run-1", "run-3")
    plain = public.run(snapshot([]))
    assert (plain["retry_of"], plain["retried_by"]) == (None, None)
