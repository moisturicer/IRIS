"""IR-740: the deterministic end-to-end smoke through IR-605's own commands.

Collect a fake-provider runtime Conversation, build its review packet, score the
reviewed packet, rescore the committed baseline fixture with the same scorer, and
refuse an unequal-budget comparison. A scripted seam stands in for the runtime's
routes, so this proves transport and contracts only: not model quality, capacity or
cost. `apps/ai/tests/test_ir740_runtime_collection_db.py` repeats the collection
against the real routes on restricted-role PostgreSQL.
"""

import copy
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.review_packets import build_packets

from .test_conversations import conv, make_set
from .test_review_campaign import files, score  # noqa: F401  (the committed baseline fixture)
from .test_runtime_replay import Seam
from apps.ai.evaluation.conversations import lock_record


@pytest.fixture
def collected(tmp_path, monkeypatch):
    seam = Seam()
    monkeypatch.setattr(
        "apps.ai.management.commands.eval_replay_conversations.runtime_seam",
        lambda url, token: seam)
    monkeypatch.setenv("IRIS_EVAL_TOKEN", "jwt")
    data = make_set([conv("d1", split="development")])
    set_path, lock_path = tmp_path / "set.json", tmp_path / "lock.json"
    set_path.write_text(json.dumps(data))
    lock_path.write_text(json.dumps(lock_record(data)))
    call_command("eval_replay_conversations", set=str(set_path), lock=str(lock_path),
                 case=["d1"], smoke=True, runtime_url="https://edge.example",
                 out=str(tmp_path / "runs"))
    [path] = (tmp_path / "runs").iterdir()
    return {"dir": tmp_path, "set": set_path, "lock": lock_path, "run_path": path,
            "run": json.loads(path.read_text())}


def reviewed(template):
    return {**template, "status": "reviewed", "task_completion": "yes",
            "pair_usefulness": "useful", "unnecessary_clarification": False,
            "access_breach": False, "presentation_leak": False, "no_answer": False,
            "claims": [{"record_id": 7, "supported": True, "citation_correct": True,
                        "page_correct": True}],
            "evidence_record_ids": [7]}


def test_collect_package_review_and_score_a_runtime_conversation(collected):
    run, tmp = collected["run"], collected["dir"]
    assert run["arm"] == "runtime" and run["evidence"]["kind"] == "contract"
    bundle = build_packets(run, reviewer="Rev One", readable={5, 7})
    packet = bundle["packets"][0]
    assert packet["authorized_record_ids"] == [5, 7]
    assert packet["turns"][0]["withheld"] is False
    reviews, packets = tmp / "reviews.json", tmp / "packets.json"
    reviews.write_text(json.dumps([reviewed(packet["review"])]))
    packets.write_text(json.dumps(bundle))
    call_command("eval_conversations", set=str(collected["set"]), score=True,
                 lock=str(collected["lock"]), runs=[f"runtime={collected['run_path']}"],
                 reviews=str(reviews), packets=[str(packets)], allow_draft=True,
                 out=str(tmp / "scored"))
    [written] = (tmp / "scored").iterdir()
    scored = json.loads(written.read_text())
    overall = scored["arms"]["runtime"]["scores"]["overall"]
    assert (overall["task_completion"]["numerator"],
            overall["task_completion"]["denominator"]) == (1, 1)
    assert scored["counted"] is False
    assert any("fake providers" in r for r in scored["not_counted_reasons"])


def test_the_baseline_fixture_still_rescores_to_the_hand_counted_numbers(files):  # noqa: F811
    scores = score(files)["arms"]["controller"]["scores"]["overall"]
    assert scores["reviewed"] == 6
    assert (scores["task_completion"]["numerator"], scores["task_completion"]["denominator"]) == (3, 4)
    assert (scores["claim_support"]["numerator"], scores["claim_support"]["denominator"]) == (5, 6)


def test_a_runtime_run_cannot_be_compared_with_a_controller_run_at_a_different_budget(collected):
    tmp = collected["dir"]
    baseline = copy.deepcopy(collected["run"])
    baseline.update(arm="controller", run_id="baseline-run")
    baseline["manifest"].update(
        run_id="baseline-run", engine_version="controller-v1", protocol_version="public-1",
        limits={**baseline["manifest"]["limits"], "case_attempts": 99})
    baseline_path = tmp / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))
    reviews = tmp / "none.json"
    reviews.write_text("[]")
    with pytest.raises(CommandError, match="limits differ"):
        call_command("eval_conversations", set=str(collected["set"]), score=True,
                     lock=str(collected["lock"]), allow_draft=True, reviews=str(reviews),
                     runs=[f"runtime={collected['run_path']}", f"controller={baseline_path}"],
                     out=str(tmp / "refused"))
    # The same pair at equal budgets is comparable: the refusal names the budget, nothing else.
    baseline["manifest"]["limits"] = collected["run"]["manifest"]["limits"]
    baseline_path.write_text(json.dumps(baseline))
    call_command("eval_conversations", set=str(collected["set"]), score=True,
                 lock=str(collected["lock"]), allow_draft=True, reviews=str(reviews),
                 runs=[f"runtime={collected['run_path']}", f"controller={baseline_path}"],
                 out=str(tmp / "matched"))
