"""IR-753: inspect the draft pack without model output or a provider."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.conversations import check_lock, validate_set


PACK = Path(__file__).resolve().parents[5] / "docs/evaluation/long-context-draft"
BASELINE = Path(__file__).resolve().parents[5] / "docs/evaluation/general-tools"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_draft_has_ten_distinct_cases_per_family_and_bound_sources():
    data = load(PACK / "conversation_set_v1.json")
    source_rows = load(PACK / "sources.json")
    sources = {s["title"]: s for s in source_rows}
    assert data["corpus"]["paper_set_sha256"] == hashlib.sha256(
        json.dumps(source_rows, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    report = validate_set(data, min_conversations=70)
    assert report["errors"] == []
    assert report["lock_blockers"] == []
    assert report["label_status"] == "draft_unreviewed"
    assert len(data["families"]) == 7
    assert Counter(c["family"] for c in data["conversations"]) == {
        family: 10 for family in data["families"]
    }
    for case in data["conversations"]:
        assert case["source_state"] == "synthetic_planned_unverified"
        for turn in case["turns"]:
            for evidence in turn["required_evidence"]:
                source = sources[evidence["title"]]
                assert source["split"] == case["split"]
                assert source["planted_fact"] == {
                    "page": evidence["page"], "quote": evidence["quote"]
                }


def test_seven_case_family_cannot_be_frozen_and_baseline_lock_still_matches():
    data = load(PACK / "conversation_set_v1.json")
    short = [case for case in data["conversations"] if case["family"] != "L01"]
    short += [case for case in data["conversations"]
              if case["family"] == "L01"][:7]
    assert "L01" in validate_set({**data, "conversations": short},
                                  min_conversations=0)["lock_blockers"]
    baseline = load(BASELINE / "conversation_set_v1.json")
    lock = load(BASELINE / "conversation_set_v1.lock.json")
    assert check_lock(baseline, lock) == []


def test_unreviewed_planned_pack_cannot_write_a_freeze_lock(tmp_path):
    with pytest.raises(CommandError, match="human-reviewed labels"):
        call_command("eval_conversations", set=str(PACK / "conversation_set_v1.json"),
                     validate=True, min_conversations=70,
                     write_lock=str(tmp_path / "lock.json"))
