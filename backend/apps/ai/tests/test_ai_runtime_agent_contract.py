"""The pinned AGENT provider contract, without a database (IR-727, ADR-049 §13, §14, §20).

Everything goes through the recording provider and the chat-completions
dialect: wire responses in, typed turns out, outgoing payloads recorded.
"""

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent.dialect import ChatCompletions  # noqa: E402
from ai.agent.protocol import (  # noqa: E402
    AgentRequest, Pin, StopReason, ToolCall, ToolGroup, ToolResult, User,
)
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402

PIN = Pin(
    model="scripted-model", endpoint="scripted", adapter="recording", dialect=ChatCompletions.name,
    prompt_version="agent-direct-1", tool_version="none-1", public_version="runs-1",
    state_version="0001_runs.sql", data_policy="no-training", requires=("tools", "continuation"),
)


def run(coro):
    return asyncio.run(coro)


def provider(*responses, **overrides):
    options = dict(endpoint="scripted", models=("scripted-model",),
                   capabilities=("tools", "parallel_tools", "continuation"))
    return RecordingAgentProvider(responses=list(responses), **{**options, **overrides})


def reply(content=None, finish="stop", tool_calls=None, **message):
    body = {"role": "assistant", "content": content, **message}
    if tool_calls is not None:
        body["tool_calls"] = tool_calls
    return {"choices": [{"message": body, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4}}


def call(id_, name, arguments="{}"):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": arguments}}


def ask(question="What is IRIS?", history=()):
    return AgentRequest(pin=PIN, instructions="Answer.", history=(User(question), *history))


def test_a_parallel_tool_group_keeps_every_call_in_order_with_its_id():
    wire = reply(finish="tool_calls", tool_calls=[
        call("c-2", "search", '{"q": "b"}'), call("c-1", "search", '{"q": "a"}'), call("c-3", "outline"),
    ])
    turn = run(provider(wire).converse(ask()))
    assert turn.stop is StopReason.TOOLS
    assert turn.items == (ToolGroup((
        ToolCall("c-2", "search", '{"q": "b"}'), ToolCall("c-1", "search", '{"q": "a"}'),
        ToolCall("c-3", "outline", "{}"),
    )),)


def test_a_history_round_trips_parallel_results_and_a_compatible_artifact_unchanged():
    secret = {"signature": "opaque-SECRET-sig"}
    wire = reply(finish="tool_calls", reasoning_details=secret,
                 tool_calls=[call("c-2", "search"), call("c-1", "outline")])
    turn = run(provider(wire).converse(ask()))
    assert "SECRET" not in repr(turn)

    follow = provider(reply("Done."))
    run(follow.converse(ask(history=(turn, ToolResult("c-2", "two"), ToolResult("c-1", "one")))))
    messages = follow.requests[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "tool"]
    assert [c["id"] for c in messages[2]["tool_calls"]] == ["c-2", "c-1"]
    assert messages[2]["reasoning_details"] == secret
    assert [m["tool_call_id"] for m in messages[3:]] == ["c-2", "c-1"]


def test_an_artifact_is_never_forwarded_to_another_endpoint_or_model():
    from ai.agent.protocol import IncompatibleContinuation

    turn = run(provider(reply("Hi.", reasoning_details={"s": 1})).converse(ask()))
    other = Pin(**{**PIN.as_dict(), "requires": PIN.requires, "model": "other-model"})
    elsewhere = provider(reply("x"), models=("other-model",))
    with pytest.raises(IncompatibleContinuation):
        run(elsewhere.converse(AgentRequest(pin=other, instructions="Answer.",
                                            history=(User("q"), turn, User("again")))))
    assert elsewhere.requests == []


def test_an_unanswered_or_reordered_tool_group_is_refused_before_sending():
    from ai.agent.protocol import BrokenExchange

    turn = run(provider(reply(finish="tool_calls", tool_calls=[call("a", "s"), call("b", "s")]))
               .converse(ask()))
    for results in ((ToolResult("b", "x"), ToolResult("a", "y")), (ToolResult("a", "y"),)):
        target = provider(reply("x"))
        with pytest.raises(BrokenExchange):
            run(target.converse(ask(history=(turn, *results, User("next")))))
        assert target.requests == []


# --- The AGENT executor ------------------------------------------------------

def agent(target, pin=PIN):
    from ai.agent.executor import AgentExecutor
    return AgentExecutor(target, pin)


def test_the_original_question_reaches_the_model_unchanged_and_its_answer_is_final():
    target = provider(reply("IRIS is a repository."))
    question = "  What is IRIS, in one line?  "
    result = run(agent(target).answer(question))
    assert result.answer == "IRIS is a repository."
    assert result.reported_units == 15
    [payload] = target.requests
    assert payload["model"] == "scripted-model"
    assert payload["messages"][-1] == {"role": "user", "content": question}
    assert "tools" not in payload


@pytest.mark.parametrize("wire, code", [
    (reply("Half an ans", finish="length"), "length"),
    (reply(None, reasoning="private working"), "reasoning_only"),
    (reply(finish="tool_calls", tool_calls=[call("c-1", "search")]), "tool_only"),
    (reply("x", finish="tool_calls", tool_calls=[call("c-1", "s"), call("c-1", "s")]), "malformed"),
    ({"choices": []}, "malformed"),
    (reply("x", finish="mystery"), "malformed"),
])
def test_output_that_is_not_a_completed_answer_is_unavailable(wire, code):
    from ai.runs.executor import Unavailable

    with pytest.raises(Unavailable) as refused:
        run(agent(provider(wire)).answer("q"))
    assert refused.value.code == code


@pytest.mark.parametrize("change", [
    {"model": "smaller-model"}, {"endpoint": "elsewhere"}, {"dialect": "responses-1"},
    {"requires": ("tools", "native_compaction")}, {"prompt_version": "agent-direct-0"},
    {"tool_version": "local-9"}, {"public_version": "public-9"}, {"state_version": "9999.sql"},
])
def test_an_unsupported_pin_is_unavailable_and_sends_nothing(change):
    from ai.runs.executor import Unavailable

    pin = Pin(**{**PIN.as_dict(), "requires": PIN.requires, **change})
    target = provider(reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        run(agent(target, pin).answer("q"))
    assert refused.value.code == "unsupported_pin"
    assert target.requests == []


def test_existing_adapters_keep_working_and_refuse_agent_turns(monkeypatch):
    from ai.domain.ports import UnsupportedCapability
    from ai.infrastructure import openai_adapter
    from ai.runs.executor import Unavailable

    monkeypatch.setattr(openai_adapter.settings, "OPENAI_API_KEY", "sk-test-not-used")
    legacy = openai_adapter.OpenAILLMProvider()
    assert callable(legacy.generate_response)
    with pytest.raises(UnsupportedCapability):
        run(legacy.converse(ask()))
    with pytest.raises(Unavailable):
        run(agent(legacy).answer("q"))


@pytest.mark.parametrize("change", [
    {"prompt_version": "agent-direct-2"}, {"tool_version": "local-2"}, {"dialect": "responses-1"},
])
def test_an_artifact_is_not_forwarded_across_a_prompt_tool_or_dialect_change(change):
    from ai.agent.protocol import IncompatibleContinuation, check_history

    turn = run(provider(reply("Hi.", reasoning_details={"s": 1})).converse(ask()))
    moved = Pin(**{**PIN.as_dict(), "requires": PIN.requires, **change})
    with pytest.raises(IncompatibleContinuation):
        check_history(AgentRequest(pin=moved, instructions="Answer.",
                                   history=(User("q"), turn, User("again"))))


@pytest.mark.parametrize("change", [{"adapter": "openai"}, {"data_policy": "vendor-default"}])
def test_an_adapter_or_data_policy_the_provider_does_not_have_is_unavailable(change):
    from ai.runs.executor import Unavailable

    pin = Pin(**{**PIN.as_dict(), "requires": PIN.requires, **change})
    target = provider(reply("Never sent."))
    with pytest.raises(Unavailable):
        run(agent(target, pin).answer("q"))
    assert target.requests == []


def test_an_artifact_without_answer_text_is_reasoning_only():
    from ai.runs.executor import Unavailable

    with pytest.raises(Unavailable) as refused:
        run(agent(provider(reply(None, reasoning_details={"s": 1}))).answer("q"))
    assert refused.value.code == "reasoning_only"
