"""The reader's token meter: provider-reported totals only, no split and no cost (IR-957)."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.runs import public  # noqa: E402

BASE = {k: None for k in ("id", "conversation_id", "state", "base_revision", "version", "turn_id",
                          "depth", "awaiting_reader", "created_at", "finished_at")}
USED = {"calls": 3, "input_tokens": 41_000, "output_tokens": 2_500, "cost_usd": 0.02,
        "last_input_tokens": 18_000}


def snapshot(**kw):
    return {**BASE, "question": "Which water papers?", "pinned": {},
            "events": [{"sequence": 1, "name": "context",
                        "data": {"used_tokens": 99_999, "capacity_tokens": 272_000}}], **kw}


def test_usage_is_the_reported_total_with_no_split_or_cost():
    shown = public.run(snapshot(usage=USED), reserved_tokens=8_000, compacts_at_tokens=180_000)["usage"]
    assert shown == {"calls": 3, "total_tokens": 43_500, "context_tokens": 18_000,
                     "capacity_tokens": 272_000, "reserved_tokens": 8_000, "compacts_at_tokens": 180_000}


def test_the_context_is_the_reported_prompt_never_the_byte_estimate():
    shown = public.run(snapshot(usage=USED))["usage"]
    assert shown["context_tokens"] == 18_000
    assert shown["compacts_at_tokens"] is None


def test_no_reported_usage_shows_no_meter():
    assert public.run(snapshot(usage=None))["usage"] is None


def test_every_run_of_a_conversation_carries_the_compaction_threshold():
    shown = public.conversation({"id": "c", "revision": 1, "runs": [snapshot(usage=USED)], "turns": []},
                                compacts_at_tokens=180_000)
    assert shown["runs"][0]["usage"]["compacts_at_tokens"] == 180_000
