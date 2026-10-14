"""IR-550: the first fixed-workflow milestone, run and scored end to end.

Snapshot S0's metadata count, topic-match count and presence listing go
through the authenticated `/ai/ask/stream/` boundary with vendors replaced
through the composition root, the `done` events are sanitized as a published
run file would be, and `evaluation.milestone.score` reports on them.

The screening fake decides from S0's own relevance labels, so this proves the
pipeline from submission to report -- denominators, populations, breaches and
standing -- and says nothing about screening quality. No paid provider is
reachable: outbound HTTP fails the test.

Set ``IRIS_PILOT_RUN_OUT`` to a file path to write the sanitized run file.
"""

import json
import os
import time
from pathlib import Path

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.evaluation.http_driver import parse_sse, sanitize_done
from apps.ai.evaluation.milestone import (
    MILESTONE_FAMILIES,
    Observation,
    parse_milestone_set,
    score,
)
from apps.ai.evaluation.runfile import file_digest, git_commit
from apps.ai.inference import InferenceTask
from apps.ai.models import Conversation
from apps.ai.providers.fakes import ScriptedLLM

from .corpus import make_user
from .test_fixed_workflow_baseline_http import (  # noqa: F401 -- fixtures
    BASELINE,
    FIXTURE,
    OracleScreen,
    _root,
    _route,
    corpus,
    no_network,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

LANE = {"metadata_count": "count", "topic_match_count": "count", "presence_listing": "listing"}


def _run_case(case, *, client, conversation, monkeypatch, root):
    _route(monkeypatch, LANE[case["family"]])
    started = time.monotonic()
    with use_composition_root(root):
        response = client.post(reverse("ai-ask-stream"),
                               {"question": case["question"], "conversation_id": conversation.pk},
                               format="json")
        text = b"".join(response.streaming_content).decode()
    elapsed = round((time.monotonic() - started) * 1000)
    events = parse_sse(text)
    return response.status_code, next(data for name, data in events if name == "done"), elapsed


@pytest.fixture
def run(settings, monkeypatch, embedder, corpus, client_for):  # noqa: F811
    settings.AI_RESEARCH_LANE = "on"
    reader = make_user("reader@cit.edu")
    keys = {record.pk: key for key, record in corpus.items()}
    client = client_for(reader)
    observations, published = [], []
    for case in BASELINE["cases"]:
        if case["family"] not in MILESTONE_FAMILIES:
            continue
        root = _root(embedder, ScriptedLLM())
        if "topic" in case:
            screen, real = OracleScreen(case["topic"]), root.llm_for
            monkeypatch.setattr(root, "llm_for",
                                lambda task, real=real, screen=screen:
                                screen if task == InferenceTask.SCREEN else real(task))
        conversation = Conversation.objects.create(user=reader)
        status, done, elapsed = _run_case(case, client=client, conversation=conversation,
                                          monkeypatch=monkeypatch, root=root)
        assert status == 200
        clean = sanitize_done(done, keys=keys)
        observations.append(Observation(case["id"], clean["mode"], clean.get("listing"), elapsed))
        published.append({"case": case["id"], "latency_ms": elapsed, "done": clean})
    return observations, published


def test_s0_scores_with_independent_denominators_and_stays_exploratory(run):
    observations, published = run
    report = score(parse_milestone_set(BASELINE), observations, tier="synthetic")

    assert report["scope"]["scored_cases"] == ["b01", "b02", "b03"]
    assert report["metadata_counts"]["exact"] == report["metadata_counts"]["denominator"] == 1
    assert report["breaches"] == []
    # Oracle screening: every assessed, labelled candidate is decided as labelled.
    assert report["screening"]["precision"]["value"] == 1.0
    assert report["screening"]["recall"]["value"] == 1.0
    # flood-gauges, flood-hazard and flood-warning are owed; flood-draft is invisible.
    for case_id in ("b02", "b03"):
        recall = report["candidate_recall"]["by_case"][case_id]
        assert (recall["numerator"], recall["denominator"]) == (3, 3)
        outside = report["screening"]["by_case"][case_id]["outside_denominators"]
        assert outside["not_assessed"] == 1  # flood-warning, which AI may not read
        assert outside["screener_uncertain"] == 1  # rainfall-note
    assert report["coverage"]["restricted"] == 2
    assert report["topic_counts"]["inconsistent"] == []
    assert report["answer_quality"]["status"] == "not_reviewed"
    assert report["standing"]["evidence"] == "exploratory_inconclusive"
    assert report["standing"]["institutional_quality_claim"] is False

    text = json.dumps(published)
    for leaked in ("Flood Prediction", "Mananga", "reasoning", "probabilities"):
        assert leaked not in text

    out = os.environ.get("IRIS_PILOT_RUN_OUT")
    if out:
        Path(out).write_text(json.dumps(
            {"commit": git_commit(), "set": BASELINE["name"], "set_sha256": file_digest(FIXTURE),
             "snapshot": BASELINE["snapshot"]["id"], "tier": "synthetic",
             "providers": "fake (composition root; screening decides from S0's labels)",
             "runs": published, "report": report}, indent=2) + "\n")
