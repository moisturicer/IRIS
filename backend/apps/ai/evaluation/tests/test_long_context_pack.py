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
    baseline = load(BASELINE / "conversation_set_v1.json")
    proxy = {q["id"]: q for q in load(PACK.parent / "proxy_starter.json")["questions"]}
    assert data["corpus"]["paper_set_sha256"] == baseline["corpus"]["paper_set_sha256"]
    assert data["corpus"]["snapshot_id"] == baseline["corpus"]["snapshot_id"]
    report = validate_set(data, min_conversations=70)
    assert report["errors"] == []
    assert report["lock_blockers"] == ["L01", "L02"]
    assert report["reportable_counts"]["L01"] == 0
    assert report["reportable_counts"]["L02"] == 0
    assert report["ready"] is False
    assert report["label_status"] == "draft_unreviewed"
    assert len(data["families"]) == 7
    assert Counter(c["family"] for c in data["conversations"]) == {
        family: 10 for family in data["families"]
    }
    for case in data["conversations"]:
        assert case["source_state"] == "proxy_reference_needs_recheck"
        for turn in case["turns"]:
            for evidence in turn["required_evidence"]:
                source = sources[evidence["title"]]
                assert source["split"] == case["split"]
                assert source["page"] == evidence["page"]
                assert source["quote"] == evidence["quote"]
                assert any(expected == {"record": evidence["title"],
                                        "page": evidence["page"],
                                        "quote": evidence["quote"]}
                           for expected in proxy[source["question_id"]]["expected"])


def test_local_pdf_audit_confirms_pages_but_not_late_evidence():
    sources = load(PACK / "sources.json")
    report = load(PACK / "local_pdf_audit.json")
    assert report["sources_sha256"] == hashlib.sha256(
        json.dumps(sources, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    audit = report["sources"]
    assert {row["title"] for row in audit} == {row["title"] for row in sources}
    assert all(row["status"] == "pdf_found" and row["quote_on_labelled_pdf_page"]
               for row in audit)
    assert all(row["labelled_page"] <= 4 for row in audit)
    assert max(row["page_count"] for row in audit) == 73


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
    with pytest.raises(CommandError, match="not locked: L01; L02"):
        call_command("eval_conversations", set=str(PACK / "conversation_set_v1.json"),
                     validate=True, min_conversations=70,
                     write_lock=str(tmp_path / "lock.json"))
    with pytest.raises(CommandError, match="unreportable families L01, L02"):
        call_command("eval_conversations", set=str(PACK / "conversation_set_v1.json"),
                     score=True, counted=True)
