"""Reader progress through the authenticated runtime contract, on PostgreSQL (IR-730)."""

import json

import pytest

from .test_ai_runtime_agent_loop_db import agent_service, call, recording, reply, tools
from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_runs_db import as_reader, session
from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]
PUBLIC = {"X-IRIS-Protocol": "runs-reader-1"}
api = runs_db.api
runtime = runs_db.runtime


def test_actual_plan_and_context_agree_live_reconnected_and_reopened(api, runtime):
    client, holder = api
    grant = session(make_user("reader-progress@cit.edu"))
    headers = {**as_reader(grant), **PUBLIC}
    step = {"id": "compare", "title": "Compare the findings", "status": "in_progress"}
    provider = recording(tools(call("plan-1", "update_plan", steps=[step])), reply("General background."))
    holder["service"] = agent_service(runtime, provider)
    response = client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": "progress-001"},
                           json={"question": "Compare the findings"})
    assert response.status_code == 201
    completed = response.json()
    assert completed["protocol"] == "runs-reader-1"
    assert completed["plan"] == {"revision": 1, "steps": [step]}
    # A final answer does not certify that the agent completed every plan step.
    assert completed["state"] == "completed"
    assert completed["context"]["estimated"] is True
    assert 0 < completed["context"]["used_tokens"] < completed["context"]["capacity_tokens"]
    reconnect = client.get(f"/api/v1/ai/runs/{completed['id']}", headers=headers).json()
    reopened = client.get(f"/api/v1/ai/conversations/{completed['conversation_id']}", headers=headers).json()
    assert reconnect["plan"] == reopened["runs"][0]["plan"] == completed["plan"]
    assert reconnect["context"] == reopened["runs"][0]["context"] == completed["context"]
    public = json.dumps([completed, reconnect, reopened])
    for private in ("scripted-model", "pinned", "events", "tool_calls", "arguments", "purpose", "end_reason"):
        assert private not in public
    assert reopened["turns"][0]["answer"] == "General background."


def test_queued_stop_and_reopen_keep_unknown_context_and_no_invented_plan(api, runtime):
    from ai.runs.dispatch import PollingNotifier

    client, holder = api
    holder["service"] = agent_service(runtime, recording(reply("Background.")))
    holder["service"].notifier = PollingNotifier()
    grant = session(make_user("reader-stop@cit.edu"))
    headers = {**as_reader(grant), **PUBLIC}
    queued = client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": "queued-001"},
                         json={"question": "Explain", "depth": "deep"}).json()
    assert queued["state"] == "queued" and queued["depth"] == "deep"
    assert queued["plan"] is None and queued["context"] is None
    stopped = client.post(f"/api/v1/ai/runs/{queued['id']}/cancel", headers=headers).json()
    assert stopped["state"] == "cancelled"
    reopened = client.get(f"/api/v1/ai/conversations/{queued['conversation_id']}", headers=headers).json()
    assert reopened["runs"][0]["state"] == "cancelled"
    assert reopened["turns"] == []
    assert stopped["capabilities"] == {"manual_compaction": False}
    other = {**PUBLIC, **as_reader(session(make_user("reader-other@cit.edu")))}
    assert client.get(f"/api/v1/ai/runs/{queued['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/ai/runs/{queued['id']}",
                      headers={**headers, "X-IRIS-Protocol": "unknown"}).status_code == 406


def test_reader_refuses_operator_echo_and_withholds_revoked_evidence(api, runtime):
    from .test_ai_runtime_research_db import paper
    from .test_ai_runtime_agent_loop_db import last_result
    from apps.records.models import PipelineStatus

    client, holder = api
    grant = session(make_user("reader-revoked@cit.edu"))
    headers = {**as_reader(grant), **PUBLIC}
    assert client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": "no-echo-1"},
                       json={"question": "Explain"}).status_code == 503
    source = paper("Private methods", {1: [("Methods", "water sampling secret method")]})
    def cite(payload):
        passage = last_result(payload)["passages"][0]
        return reply(f"Water sampling secret method [{passage['passage']}].")
    provider = recording(tools(call("plan", "update_plan", steps=[{
        "id": "read", "title": "Read the secret method", "status": "done",
    }]), call("find", "search", query="water")), cite)
    holder["service"] = agent_service(runtime, provider)
    completed = client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": "revoked-1"},
                            json={"question": "Find methods"}).json()
    path = f"/api/v1/ai/conversations/{completed['conversation_id']}"
    assert "secret method" in client.get(path, headers=headers).text
    source.pipeline_status = PipelineStatus.DRAFT
    source.save(update_fields=["pipeline_status"])
    hidden = client.get(path, headers=headers).json()
    assert hidden["runs"][0]["sources_available"] is False
    assert hidden["runs"][0]["plan"] is None
    assert hidden["turns"][0]["citations"] == []
    assert "secret method" not in json.dumps(hidden)
    assert "no longer readable" in hidden["turns"][0]["answer"]


def test_queued_multi_paper_loop_exposes_actual_live_tasks_before_delivery(api, runtime):
    import os
    import threading
    from pathlib import Path
    from ai.runs.dispatch import PollingNotifier
    from .test_ai_runtime_runs_db import run
    from .test_ai_runtime_research_db import paper
    from .test_ai_runtime_agent_loop_db import last_result

    client, holder = api
    paper("Flood sensors", {1: [("Methods", "water sampling sensors") ]})
    paper("Pond sampling", {2: [("Methods", "water sampling ponds") ]})
    grant = session(make_user("reader-live@cit.edu"))
    headers = {**as_reader(grant), **PUBLIC}
    reached, release = threading.Event(), threading.Event()
    def draft(payload):
        reached.set()
        if not release.wait(20):
            raise RuntimeError("reader did not release fixture provider")
        passages = last_result(payload)["passages"]
        return reply("Both discuss water " + " ".join(f"[{p['passage']}]" for p in passages) + ".")
    step = {"id": "compare", "title": "Compare water studies", "status": "in_progress"}
    provider = recording(tools(call("plan", "update_plan", steps=[step]),
                               call("find", "search", query="water")), draft)
    service = agent_service(runtime, provider)
    service.notifier = PollingNotifier()
    holder["service"] = service
    queued = client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": "live-001"},
                         json={"question": "Compare water studies"}).json()
    assert queued["state"] == "queued" and queued["plan"] is None
    worker = threading.Thread(target=lambda: run(service.run_next()), daemon=True)
    worker.start()
    try:
        assert reached.wait(10)
        live = client.get(f"/api/v1/ai/runs/{queued['id']}", headers=headers).json()
        assert live["state"] == "running" and live["plan"] == {"revision": 1, "steps": [step]}
        reopened = client.get(f"/api/v1/ai/conversations/{queued['conversation_id']}", headers=headers).json()
        assert reopened["runs"][0]["plan"] == live["plan"] and reopened["turns"] == []
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive()
    completed = client.get(f"/api/v1/ai/runs/{queued['id']}", headers=headers).json()
    assert completed["state"] == "completed"
    final = client.get(f"/api/v1/ai/conversations/{queued['conversation_id']}", headers=headers).json()
    assert len(final["turns"][0]["citations"]) == 2
    deep = client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": "live-002"},
                       json={"question": "Compare more thoroughly", "depth": "deep",
                             "conversation_id": final["id"], "base_revision": final["revision"]}).json()
    assert deep["state"] == "queued" and deep["depth"] == "deep"
    stopped = client.post(f"/api/v1/ai/runs/{deep['id']}/cancel", headers=headers).json()
    assert stopped["state"] == "cancelled"
    after_stop = client.get(f"/api/v1/ai/conversations/{final['id']}", headers=headers).json()
    if os.environ.get("IR730_CAPTURE_READER"):
        Path("/tmp/ir730-reader-recording.json").write_text(json.dumps({
            "queued": queued, "live": live, "completed": completed, "conversation": final,
            "deep": deep, "stopped": stopped, "after_stop": after_stop,
        }))
