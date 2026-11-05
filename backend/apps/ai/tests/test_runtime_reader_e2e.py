"""A reader's question, end to end, through the path the switch opens (IR-863).

Django authenticates the reader and issues the edge grant exactly as nginx's
`auth_request` asks for it; the gateway answers the run with the recording
provider on restricted-role PostgreSQL; the reader then reopens it. The public
projections are recorded in `frontend/src/test/fixtures/runtimeReader.recorded.json`,
which the Ask IRIS page replays (`RAGChatPage.runtime.test.tsx`), so the browser
half is tested against what this half actually serves.

Regenerate only on a deliberate change to the reader contract, with
`IRIS_WRITE_READER_RECORDING=1`, and say so in the PR.
"""

import json
import os
import re

import pytest
from rest_framework.test import APIClient

from .test_ai_runtime_agent_loop_db import agent_service, call, last_result, recording, reply, tools
from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_research_db import paper
from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]
api = runs_db.api
runtime = runs_db.runtime

RECORDING = runs_db.REPO / "frontend" / "src" / "test" / "fixtures" / "runtimeReader.recorded.json"
#: Every key a reader projection may carry; anything else is a leak.
RUN_KEYS = {
    "protocol", "id", "conversation_id", "state", "question", "base_revision", "version", "turn_id",
    "depth", "awaiting_reader", "created_at", "finished_at", "plan", "context", "sources_available",
    "capabilities", "compaction", "kind",
}
CONVERSATION_KEYS = {"protocol", "id", "revision", "runs", "turns"}
TURN_KEYS = {"id", "run_id", "ordinal", "question", "answer", "kind", "created_at", "citations", "facts"}
CITATION_KEYS = {"record_id", "page", "quote", "revision"}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _edge(user, record=None):
    """What nginx's auth_request subrequest gets back, as headers to forward."""
    client = APIClient()
    client.force_authenticate(user)
    extra = {"HTTP_X_IRIS_RECORD": str(record)} if record else {}
    response = client.get("/api/v1/ai/runtime/edge-grant/", **extra)
    assert response.status_code == 204
    # nginx forwards the grant and fixes the protocol; the browser supplies neither.
    return {"X-IRIS-Reader-Grant": response["X-IRIS-Reader-Grant"], "X-IRIS-Protocol": "runs-reader-1"}


def _assert_public(snapshot):
    """Only allowlisted keys: no reasoning, tool arguments, provider IDs or codes."""
    if "runs" in snapshot:
        assert set(snapshot) == CONVERSATION_KEYS
        for run in snapshot["runs"]:
            _assert_public(run)
        for turn in snapshot["turns"]:
            assert set(turn) == TURN_KEYS
            for citation in turn["citations"]:
                assert set(citation) == CITATION_KEYS
    else:
        assert set(snapshot) == RUN_KEYS
    text = json.dumps(snapshot)
    for private in ("scripted-model", "reasoning", "tool_calls", "arguments", "pinned", "events",
                    "purpose", "end_reason", "reason_code", "provider"):
        assert private not in text


def _normalized(recorded, records):
    """Stable placeholders for what differs run to run: ids, Record pks, times, token counts."""
    names, chunk_sets = {}, {}
    text = UUID.sub(lambda m: names.setdefault(m.group(), f"00000000-0000-4000-8000-{len(names) + 1:012d}"),
                    json.dumps(recorded))
    data = json.loads(text)

    def walk(value):
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if key in ("created_at", "finished_at") and item is not None:
                    item = "2026-11-04T00:00:00+00:00"
                elif key == "record_id":
                    item = records[item]
                elif key == "revision" and isinstance(item, str):
                    # "<chunk set id>:<extraction hash>"; the test's hashes are "e-<record pk>-<n>".
                    item = re.sub(r"^(\d+):e-(\d+)-", lambda m: (
                        f"{chunk_sets.setdefault(m[1], len(chunk_sets) + 1)}:e-{records[int(m[2])]}-"), item)
                elif key == "used_tokens":
                    # Measured from payload bytes, which carry the pks above.
                    assert 0 < item
                    item = 4000
                out[key] = walk(item)
            return out
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    return walk(data)


def test_a_reader_question_is_delivered_reopened_and_recorded_for_the_browser(api, runtime, settings):
    settings.AI_RUNTIME_READER = True
    client, holder = api
    flood = paper("Flood sensors", {3: [("Methods", "river gauges measure water level hourly")]})
    pond = paper("Pond sampling", {5: [("Methods", "pond water sampled weekly for turbidity")]})
    reader = make_user("e2e-reader@cit.edu")

    def cite(payload):
        passages = last_result(payload)["passages"]
        return reply("Both studies sample water: " +
                     " ".join(f"[{p['passage']}]" for p in passages) + ".")

    step = {"id": "compare", "title": "Compare how each study samples water", "status": "done"}
    provider = recording(tools(call("plan", "update_plan", steps=[step]),
                               call("find", "search", query="water")), cite)
    holder["service"] = agent_service(runtime, provider)

    headers = _edge(reader)
    submitted = client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": "e2e-question-1"},
                            json={"question": "How do these studies sample water?"})
    assert submitted.status_code == 201
    live = submitted.json()
    assert live["state"] == "completed"
    followed = client.get(f"/api/v1/ai/runs/{live['id']}", headers=headers).json()
    conversation = f"/api/v1/ai/conversations/{live['conversation_id']}"
    delivered = client.get(conversation, headers=headers).json()
    # A reload asks the edge again; the grant is new, the answer is not.
    reopened = client.get(conversation, headers=_edge(reader)).json()

    assert followed == live
    assert reopened == delivered
    [turn] = delivered["turns"]
    assert turn["kind"] == "answer"
    assert [c["record_id"] for c in turn["citations"]] == [flood.pk, pond.pk]
    assert all(c["quote"] for c in turn["citations"])
    for snapshot in (live, followed, delivered):
        _assert_public(snapshot)

    recorded = _normalized({"live": live, "conversation": delivered}, {flood.pk: 1, pond.pk: 2})
    if os.environ.get("IRIS_WRITE_READER_RECORDING"):
        RECORDING.write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")
    assert json.loads(RECORDING.read_text(encoding="utf-8")) == recorded

