"""IR-542: what Ask IRIS returns today for the fixed-workflow pilot families.

The baseline the later workflow tickets (IR-543, IR-546, IR-547) are measured
against. Every case is read from `evaluation/fixtures/fixed_workflow_baseline.json`
and driven through the authenticated HTTP boundary, the SSE `done` event and
the reopened conversation, with vendors replaced through the composition
root. Each case pins `baseline` (today's behaviour), not `contract` (the
target); when a workflow ticket changes an outcome it changes the fixture's
`baseline` deliberately, and the diff is the evidence.

The screening fake decides from the fixture's human relevance labels, so these
assert plumbing, populations and coverage wording -- never screening quality.
No paid provider is reachable: outbound HTTP fails the test.
"""

import json
from pathlib import Path

import httpx
import pytest
from django.urls import reverse

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import Conversation
from apps.ai.providers.decisions import ScriptedDecisionModel
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.routing.router import LANES
from apps.records.models import Record
from core.enums import PUBLICLY_VISIBLE_STATUSES, PipelineStatus

from .corpus import _BrokenLLM, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

FIXTURE = (Path(__file__).resolve().parents[1]
           / "evaluation" / "fixtures" / "fixed_workflow_baseline.json")
BASELINE = json.loads(FIXTURE.read_text())
ENDPOINTS = ["ai-ask", "ai-ask-stream"]

RUNS = [
    pytest.param(case, run, id=f"{case['id']}-{case['family']}-{run['lane']}")
    for case in BASELINE["cases"] for run in case["baseline"]
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("IR-542 baseline reached the network; no paid provider call is allowed")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture
def corpus(embedder, space):
    """Snapshot S0: the fixture's records, keyed as the fixture keys them."""
    other = make_user("other@cit.edu")
    records = {}
    for row in BASELINE["records"]:
        records[row["key"]] = make_record(
            title=row["title"], text=row["text"], embedder=embedder, space=space,
            status=PipelineStatus(row["state"]),
            owner=other if row["owner"] == "other" else None,
        )
    return records


def _refused_titles():
    return {r["title"] for r in BASELINE["records"] if r["disclosure"] == "refused"}


def _root(embedder, llm):
    refused = _refused_titles()
    return CompositionRoot(
        embedder=embedder, reranker=ScriptedReranker(), llm=llm,
        permits=lambda record: record.title not in refused,
    )


class OracleScreen(LLMProvider):
    """Screens from the fixture's human labels: include, exclude or unassessed."""

    def __init__(self, topic):
        by_title = {r["title"]: r["key"] for r in BASELINE["records"]}
        labels = BASELINE["relevance"][topic]["labels"]
        self.decide = {title: labels[key] for title, key in by_title.items()}

    def generate(self, system, user):
        rows = []
        for paper in json.loads(user)["records"]:
            label = self.decide[paper["title"]]
            if label == "uncertain":
                rows.append({"record": paper["record"], "decision": "uncertain", "quote": ""})
            else:
                rows.append({"record": paper["record"], "quote": paper["title"],
                             "decision": "include" if label == "relevant" else "exclude"})
        return json.dumps({"decisions": rows})


class DownScreen(LLMProvider):
    def generate(self, system, user):
        raise LLMUnavailable("503 screening model unavailable")


def _route(monkeypatch, lane):
    probabilities = {name: 0.01 for name in LANES}
    probabilities[lane] = 0.95
    probabilities["injection"] = 0.01
    jev = ScriptedDecisionModel(probabilities)
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers",
                        lambda **kwargs: (jev, None))


def _post(client, endpoint, question, **options):
    response = client.post(reverse(endpoint), {"question": question, **options}, format="json")
    assert response.status_code == 200
    if endpoint == "ai-ask":
        return response.json()
    events = []
    for block in b"".join(response.streaming_content).decode().split("\n\n"):
        if block:
            name, data = block.split("\n", 1)
            events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return next(data for name, data in events if name == "done")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("case,run", RUNS)
def test_baseline_outcome_through_http_sse_and_replay(
    case, run, endpoint, settings, monkeypatch, embedder, corpus, client_for
):
    reader = make_user("reader@cit.edu")
    keys = {record.pk: key for key, record in corpus.items()}
    titles = {key: record.title for key, record in corpus.items()}

    settings.AI_RESEARCH_LANE = "off" if run["lane"] == "off" else "on"
    if run["lane"] != "off":
        _route(monkeypatch, run["lane"])
    root = _root(embedder, _BrokenLLM() if case.get("failure") == "answer_model_down"
                 else ScriptedLLM())
    if "topic" in case:
        screen = (DownScreen() if case.get("failure") == "screening_model_down"
                  else OracleScreen(case["topic"]))
        real = root.llm_for
        monkeypatch.setattr(root, "llm_for",
                            lambda task: screen if task == InferenceTask.SCREEN else real(task))

    scope = corpus[case["scope_record"]] if "scope_record" in case else None
    conversation = Conversation.objects.create(user=reader, record=scope)
    client = client_for(reader)
    with use_composition_root(root):
        body = _post(client, endpoint, case["question"], conversation_id=conversation.pk)

    expect = run["expect"]
    if "routing_lane" in expect:
        assert body["routing"]["lane"] == expect["routing_lane"]
    else:
        assert "routing" not in body
    if "mode" in expect:
        assert body["mode"] == expect["mode"]
    if expect.get("answer_is_null"):
        assert body["answer"] is None
    if "answer_contains" in expect:
        # A non-answer (nothing assessed, none found) says so in `message`, not `answer`.
        assert expect["answer_contains"] in (body["answer"] or body["message"])

    listing = expect["listing"]
    if listing is None:
        assert "listing" not in body
    else:
        assert body["listing"]["completeness"] == listing["completeness"]
        returned = [keys[row["record_id"]] for row in body["listing"]["records"]]
        assert len(returned) == len(set(returned)), "a Record was listed twice"
        if "record_keys" in listing:
            assert sorted(returned) == sorted(listing["record_keys"])
        if "record_keys_within" in listing:
            assert set(returned) <= set(listing["record_keys_within"])
        if "candidates" in listing:
            # IR-546: every candidate in exactly one state; a restricted Record is
            # counted as unassessed and never named.
            rows = body["listing"]["candidates"]
            assert len({row["record_id"] for row in rows}) == len(rows) <= 20
            by_state = {state: sorted(keys[row["record_id"]] for row in rows
                                      if row["state"] == state and not row.get("restricted"))
                        for state in ("included", "excluded", "uncertain")}
            expected = listing["candidates"]
            assert by_state == {"included": sorted(expected["included_keys"]),
                                "excluded": sorted(expected["excluded_keys"]),
                                "uncertain": sorted(expected["uncertain_keys"])}
            assert sorted(keys[row["record_id"]] for row in rows if row.get("restricted")) == sorted(
                expected["restricted_keys"])
            assert all("title" not in row for row in rows if row.get("restricted"))

    cited = {keys[c["record_id"]] for c in body["citations"]}
    if "citations_within" in expect:
        assert cited <= set(expect["citations_within"])
    if "citation" in expect:
        label = expect["citation"]
        assert any(keys[c["record_id"]] == label["record"] and c["page"] == label["page"]
                   and label["quote"] in c["text"] for c in body["citations"])
    sources = {keys[s["id"]] for s in body.get("sources", ())}
    if "sources_within" in expect:
        assert sources <= set(expect["sources_within"])
    if expect.get("sources_nonempty"):
        assert sources

    wire = json.dumps(body)
    for key in expect.get("never_mentions", ()):
        assert titles[key] not in wire, f"{key} reached the response"

    turn, = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"]
    if listing is None:
        assert "listing" not in turn or not turn["listing"]
    else:
        assert turn["listing"] == body["listing"]


def test_snapshot_populations_match_the_database_predicate(corpus):
    """Metadata count population and AI eligibility, computed from the real
    visibility predicate at S0 rather than trusted from the fixture."""
    reader = make_user("reader@cit.edu")
    keys = {record.pk: key for key, record in corpus.items()}
    visible = (Record.objects.visible_to(reader)
               .filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES))
    population = {keys[pk] for pk in visible.values_list("pk", flat=True).distinct()}
    refused = _refused_titles()
    eligible = {keys[r.pk] for r in visible if r.title not in refused}

    expected = BASELINE["populations"]
    assert population == set(expected["metadata_count"]["record_keys"])
    assert eligible == set(expected["ai_assessment_eligible"]["record_keys"])
    assert visible.values("pk").distinct().count() == len(population)
