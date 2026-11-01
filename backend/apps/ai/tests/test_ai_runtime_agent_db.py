"""A direct question through the pinned AGENT contract, on real PostgreSQL (IR-727).

The gateway's authenticated run routes, a restricted runtime login and the
recording provider; no network transport exists.
"""

import json
import logging

import pytest

# First: it puts the repository root on sys.path.
from .test_ai_runtime_runs_db import (  # noqa: F401  (fixtures)
    LIMITS, api, as_reader, runtime, service, session, submit,
)
from ai.agent.dialect import ChatCompletions  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.protocol import Pin  # noqa: E402
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from .corpus import make_user  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

PIN = Pin(
    model="scripted-model", endpoint="scripted", adapter="recording", dialect=ChatCompletions.name,
    prompt_version="agent-direct-1", tool_version="none-1", public_version="runs-1",
    state_version="0001_runs.sql", data_policy="no-training", requires=("continuation",),
)
SECRET = "opaque-SECRET-payload"


def reply(content, **message):
    return {"choices": [{"message": {"role": "assistant", "content": content, **message},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3}}


def recording(*responses):
    return RecordingAgentProvider(responses=list(responses), capabilities=("continuation",))


def use_agent(holder, runtime_dsn, provider, pin=PIN):
    holder["service"] = service(runtime_dsn, AgentExecutor(provider, pin))


def test_a_direct_question_completes_and_reopens_with_its_pin(api, runtime):
    client, holder = api
    provider = recording(reply("IRIS keeps CIT-U research."))
    use_agent(holder, runtime, provider)
    grant = session(make_user("agent-direct@cit.edu"))
    question = "What does IRIS keep?"

    run_ = submit(client, grant, "agent-direct-1", question).json()
    assert run_["state"] == "completed"
    assert run_["pinned"]["agent"] == PIN.as_dict()
    assert run_["pinned"]["executor"] == "agent"
    assert provider.requests[0]["messages"][-1] == {"role": "user", "content": question}

    body = client.get(f"/api/v1/ai/conversations/{run_['conversation_id']}",
                      headers=as_reader(grant)).json()
    [turn] = body["turns"]
    assert turn["question"] == question
    assert turn["answer"] == "IRIS keeps CIT-U research."
    assert turn["pinned"] == run_["pinned"]


def test_an_unsupported_pin_ends_unavailable_with_no_turn(api, runtime):
    client, holder = api
    provider = recording(reply("Never sent."))
    smaller = Pin(**{**PIN.as_dict(), "requires": PIN.requires, "model": "smaller-model"})
    use_agent(holder, runtime, provider, smaller)
    grant = session(make_user("agent-unsupported@cit.edu"))

    run_ = submit(client, grant, "agent-unsupported", "Anything?").json()
    assert (run_["state"], run_["end_reason"]) == ("failed", "unavailable")
    assert provider.requests == []
    body = client.get(f"/api/v1/ai/conversations/{run_['conversation_id']}",
                      headers=as_reader(grant)).json()
    assert body["revision"] == 0 and body["turns"] == []


def test_a_run_is_never_continued_under_another_pin(runtime):
    reader = make_user("agent-repinned@cit.edu")
    admitted_by = service(runtime, AgentExecutor(recording(), PIN))
    row, _ = asyncio_run(admitted_by.store.admit(
        session(reader), key="agent-repinned", question="Q?", conversation_id=None,
        base_revision=None, deadline_seconds=LIMITS.deadline_seconds,
        allowance=LIMITS.allowance(), pinned=admitted_by.pinned(),
    ))
    upgraded = Pin(**{**PIN.as_dict(), "requires": PIN.requires, "prompt_version": "agent-direct-2"})
    provider = recording(reply("Would be the wrong interpretation."))
    worker = service(runtime, AgentExecutor(provider, upgraded))
    asyncio_run(worker.execute(row["id"]))
    status = asyncio_run(RunStore(runtime).status(session(reader), row["id"]))
    assert (status["state"], status["end_reason"]) == ("failed", "unavailable")
    assert status["pinned"]["agent"] == PIN.as_dict()
    assert provider.requests == []


def test_no_opaque_payload_reaches_the_projection_transcript_or_logs(api, runtime, caplog):
    client, holder = api
    use_agent(holder, runtime, recording(
        reply("A plain answer.", reasoning="private working", reasoning_details={"sig": SECRET}),
    ))
    grant = session(make_user("agent-opaque@cit.edu"))
    caplog.set_level(logging.DEBUG)

    run_ = submit(client, grant, "agent-opaque", "Explain.").json()
    assert run_["state"] == "completed"
    reopened = client.get(f"/api/v1/ai/conversations/{run_['conversation_id']}",
                          headers=as_reader(grant)).json()
    status = client.get(f"/api/v1/ai/runs/{run_['id']}", headers=as_reader(grant)).json()
    for public in (run_, reopened, status):
        text = json.dumps(public)
        assert SECRET not in text and "private working" not in text
    assert SECRET not in caplog.text and "private working" not in caplog.text


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
