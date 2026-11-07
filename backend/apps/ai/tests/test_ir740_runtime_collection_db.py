"""IR-605 collects the dedicated runtime through its real authenticated routes (IR-740).

Django authenticates the reader and issues the edge grant exactly as nginx's
`auth_request` asks for it; the gateway answers each run with the recording
provider on real PostgreSQL under the restricted runtime login; the IR-605
collector submits, follows and reopens it through `RuntimeSeam`. The run file,
the review packet and the revoked-source denial are then checked on what that
collection actually produced. The recording provider proves the contract and the
transport, never a vendor's behaviour, cost or answer quality.
"""

import json
from functools import partial

import pytest
from rest_framework.test import APIClient

from apps.ai.evaluation.engines import RUNTIME_ENGINE, RUNTIME_TRANSPORT, runtime_identity
from apps.ai.evaluation.replay import RuntimeAttempts, collect_run
from apps.ai.evaluation.review_packets import build_packets
from apps.ai.evaluation.runfile import write_run
from apps.ai.evaluation.runtime_replay import RuntimeSeam, collect_case_runtime
from apps.ai.evaluation.tests.test_conversations import conv
from apps.records.models import Record
from core.enums import PipelineStatus
from . import test_ai_runtime_runs_db as runs_db
from .corpus import make_user
from .test_ai_runtime_admission_db import (PIN as DIRECT_PIN, RESERVES as DIRECT_RESERVES,
                                           admitted, reply as direct_reply)
from .test_ai_runtime_agent_loop_db import agent_service, call, last_result, recording, reply, tools
from .test_ai_runtime_research_db import paper
from .test_runtime_reader_e2e import _assert_public
from ai.agent.executor import AgentExecutor  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]
api = runs_db.api
runtime = runs_db.runtime


def edge_headers(user):
    """What nginx's auth_request subrequest returns, as headers to forward."""
    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/ai/runtime/edge-grant/")
    assert response.status_code == 204
    return {"X-IRIS-Reader-Grant": response["X-IRIS-Reader-Grant"],
            "X-IRIS-Protocol": RUNTIME_TRANSPORT}


def seam_for(client, user):
    # A fresh grant per request, like the edge: the collector holds no credential of its own.
    return RuntimeSeam(client, prefix="/api/v1/ai", headers=lambda: edge_headers(user))


def two_turn_case():
    case = conv("rt1", split="development", topic="water", papers=("Flood sensors",))
    first = dict(case["turns"][0], user="How do these studies sample water?")
    case["turns"] = [first, dict(first, user="What changed that year?")]
    return case


def scripted_provider():
    def cite(payload):
        passages = last_result(payload)["passages"]
        return reply("Both studies sample water: "
                     + " ".join(f"[{p['passage']}]" for p in passages) + ".")

    return recording(
        tools(call("bad", "search")),                        # a malformed call, answered safely
        tools(call("find", "search", query="water")),
        cite,
        tools(call("ask", "ask_clarification", question="Which year do you mean?")))


def corpus(user_email):
    reader = make_user(user_email)
    flood = paper("Flood sensors", {3: [("Methods", "river gauges measure water level hourly")]})
    pond = paper("Pond sampling", {5: [("Methods", "pond water sampled weekly for turbidity")]})
    return reader, flood, pond


def export(seam, case, tmp_path, **kw):
    run = collect_run(
        seam, [case], set_id="s", set_digests={"development": "d", "held_out": "h"},
        corpus={"paper_set_sha256": "p", "snapshot_id": "ir740-db"},
        model_ids={"agent": "scripted-model"}, limits={"case_attempts": 4},
        data_policy="deterministic-fake-local", cache="cold", arm="runtime",
        engine_version=RUNTIME_ENGINE, protocol=RUNTIME_TRANSPORT, identity=runtime_identity(),
        runtime={"depth": "deep", "declared_by": "operator"},
        case_collector=partial(collect_case_runtime, depth="deep"), **kw)
    path = write_run(tmp_path, "IR-740-db", run)
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_collector_follows_the_real_routes_and_exports_the_same_projection_it_reopened(
        api, runtime, settings, tmp_path):
    settings.AI_RUNTIME_READER = True
    client, holder = api
    reader, flood, pond = corpus("ir740-collect@cit.edu")
    holder["service"] = agent_service(runtime, scripted_provider())

    run = export(seam_for(client, reader), two_turn_case(), tmp_path)

    manifest = run["manifest"]
    assert (run["arm"], manifest["engine_version"], manifest["protocol_version"]) == (
        "runtime", "ai-runtime-1", "runs-reader-1")
    assert manifest["controller_version"] is None and run["evidence"]["kind"] == "contract"
    [row] = run["conversations"]
    assert row["status"] == "complete" and row["conversation_id"]
    first, second = row["turns"]

    # The answer, its citations and their order are the runtime's, unchanged in the export.
    assert first["outcome"] == "answered"
    cited = [c["record_id"] for c in first["saved_turn"]["citations"]]
    assert sorted(cited) == sorted([flood.pk, pond.pk])
    assert first["citation_record_ids"] == cited
    assert [c["record_id"] for c in first["public_answer"]["citations"]] == cited
    assert all(c["text"] for c in first["public_answer"]["citations"])
    assert (second["outcome"], second["public_answer"]["kind"]) == ("answered", "clarification")
    assert second["public_answer"]["answer"] == "Which year do you mean?"
    assert second["citation_record_ids"] == []

    # Live, reopened, replayed (a reload with a new grant) and exported agree and stay allowlisted.
    replayed = client.get(f"/api/v1/ai/conversations/{row['conversation_id']}",
                          headers=edge_headers(reader)).json()
    assert replayed["turns"] == row["reopened_transcript"]
    assert replayed["turns"][0]["citations"] == first["saved_turn"]["citations"]
    _assert_public(replayed)
    for turn in row["turns"]:
        for event in turn["public_events"]:
            _assert_public(event["data"])
    assert row["turns"][-1]["public_events"][-1]["data"]["state"] == "completed"

    # The review packet shows the reviewer what the reader saw, in the same order.
    packet = build_packets(run, reviewer="Rev One", readable={flood.pk, pond.pk})["packets"][0]
    assert [c["record_id"] for c in packet["turns"][0]["citations"]] == cited
    assert packet["turns"][0]["withheld"] is False
    assert packet["authorized_record_ids"] == sorted(cited)


def test_a_source_made_unreadable_after_collection_is_denied_in_reopen_export_and_packet(
        api, runtime, settings, tmp_path):
    settings.AI_RUNTIME_READER = True
    client, holder = api
    reader, flood, pond = corpus("ir740-denial@cit.edu")
    holder["service"] = agent_service(runtime, scripted_provider())
    seam = seam_for(client, reader)
    run = export(seam, two_turn_case(), tmp_path)
    [row] = run["conversations"]
    before = json.dumps(row["turns"][0]["public_answer"])
    assert "gauges" in before

    Record.objects.filter(pk=flood.pk).update(pipeline_status=PipelineStatus.DRAFT)

    # A fresh reopen, and so any re-export, no longer carries the answer or its quotations.
    reopened = seam.reopen(row["conversation_id"]).json()
    first = reopened["turns"][0]
    assert first["citations"] == [] and "gauges" not in json.dumps(reopened)
    assert "unavailable" in first["answer"]
    assert reopened["runs"][0]["sources_available"] is False

    # The export made earlier is still denied to a reviewer who can no longer read the paper.
    readable = set(Record.objects.visible_to(reader).values_list("pk", flat=True))
    assert flood.pk not in readable and pond.pk in readable
    packet = build_packets(run, reviewer="Rev One", readable=readable)["packets"][0]
    assert packet["turns"][0]["withheld"] is True and "answer" not in packet["turns"][0]
    assert packet["turns"][0]["citations"] == []
    assert packet["authorized_record_ids"] == []
    assert "gauges" not in json.dumps(packet)

    # Collecting again after the revocation exports no answer text: the turn is a failure.
    holder["service"] = agent_service(runtime, scripted_provider())
    again = export(seam, two_turn_case(), tmp_path)["conversations"][0]
    assert "gauges" not in json.dumps(again["turns"][0]["public_answer"])


@pytest.mark.django_db(transaction=True, databases=["default", "admission"])
def test_physical_attempts_are_read_from_the_runtime_ledger_by_run(api, runtime, settings):
    settings.AI_RUNTIME_READER = True
    client, holder = api
    reader = make_user("ir740-ledger@cit.edu")
    _, transport = admitted(runtime, direct_reply("A direct answer.", 9, 3))
    holder["service"] = runs_db.service(
        runtime, AgentExecutor(transport, DIRECT_PIN, DIRECT_RESERVES))
    case = conv("rt2", split="development")

    row = collect_case_runtime(seam_for(client, reader), case, attempts=RuntimeAttempts("ir725-test"))

    [turn] = row["turns"]
    assert turn["outcome"] == "answered"
    [attempt] = turn["physical_attempts"]
    assert (attempt["owner"], attempt["purpose"], attempt["purpose_version"]) == (
        "ai", "answer", "agent-direct-1")
    assert attempt["run_key"].startswith("airun:") and attempt["model"] == "scripted-model"
    assert attempt["state"] == "settled" and attempt["usage_reported"] is True
    assert 0 < attempt["cost_usd"] <= attempt["reserved_cost_usd"]
    assert turn["usage_status"] == "reported" and row["physical_attempts"] == 1
    assert row["cost"] == pytest.approx(attempt["cost_usd"])
