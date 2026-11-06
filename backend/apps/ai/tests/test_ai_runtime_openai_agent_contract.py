"""The OpenAI-compatible AGENT adapter, without a database or network (IR-860).

Recorded chat-completions responses are replayed through the real adapter
over `httpx.MockTransport`, so the request it would send is captured and
nothing leaves the process.
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.admission import scope  # noqa: E402
from ai.agent.dialect import ChatCompletions  # noqa: E402
from ai.agent.protocol import (  # noqa: E402
    AgentRequest, Pin, StopReason, Text, ToolCall, ToolGroup, ToolResult, User,
)
from ai.infrastructure.openai_adapter import OpenAICompatibleAgentProvider  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402

ENDPOINT = "https://vendor.test/v1"
MODEL = "vendor/model-a"
API_KEY = "sk-test-SECRET-key"
# A declared fixture capacity; no vendor's window is implied.
CAPACITY = {"context_tokens": 128_000, "max_output_tokens": 8_000, "max_reasoning_tokens": None,
            "max_request_bytes": 2_000_000, "min_bytes_per_token": 1.0, "framing_tokens_per_message": 4}
CONFIG = dict(
    AGENT_LLM_ENDPOINT=ENDPOINT, AGENT_LLM_API_KEY=API_KEY,
    AGENT_LLM_MODELS=f"{MODEL},vendor/model-b", AGENT_LLM_CAPABILITIES="tools,parallel_tools,continuation",
    AGENT_LLM_DATA_POLICY="no-training", AGENT_LLM_CAPACITIES=json.dumps({MODEL: CAPACITY}),
)
PIN = Pin(
    model=MODEL, endpoint=ENDPOINT, adapter=OpenAICompatibleAgentProvider.adapter,
    dialect=ChatCompletions.name, prompt_version="agent-research-1", tool_version="research-1",
    public_version=runs_config.PROTOCOL, state_version=runs_config.SCHEMA, data_policy="no-training",
    requires=("tools", "parallel_tools"),
)


def run(coro):
    return asyncio.run(coro)


class Vendor:
    """Recorded responses in order; every request it is sent is kept."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200, json=response)

    @property
    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


def adapter(vendor, **overrides):
    values = SimpleNamespace(**{**CONFIG, **overrides})
    return OpenAICompatibleAgentProvider.from_settings(
        values, http_client=httpx.AsyncClient(transport=httpx.MockTransport(vendor)))


def reply(content=None, finish="stop", tool_calls=None, **message):
    body = {"role": "assistant", "content": content, **message}
    if tool_calls is not None:
        body["tool_calls"] = tool_calls
    return {"id": "chatcmpl-1", "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "message": body, "finish_reason": finish}],
            "usage": {"prompt_tokens": 21, "completion_tokens": 7, "total_tokens": 28}}


def call(id_, name, arguments="{}"):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": arguments}}


def ask(question="What is IRIS?", history=(), pin=PIN, **options):
    return AgentRequest(pin=pin, instructions="Answer.", history=(User(question), *history), **options)


def admitted(coro):
    """Send as `AdmittedAgentProvider` does, inside an admitted attempt."""
    async def attempt():
        with scope.admitted_send():
            return await coro
    return run(attempt())


def test_a_direct_answer_is_a_final_turn_with_reported_usage():
    vendor = Vendor(reply("IRIS is a repository."))
    turn = admitted(adapter(vendor).converse(ask(max_output_tokens=300)))

    assert turn.stop is StopReason.END
    assert turn.items == (Text("IRIS is a repository."),)
    assert (turn.input_tokens, turn.output_tokens) == (21, 7)
    [sent] = vendor.requests
    assert str(sent.url) == f"{ENDPOINT}/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {API_KEY}"
    assert vendor.bodies[0] == {
        "model": MODEL, "max_tokens": 300,
        "messages": [{"role": "system", "content": "Answer."}, {"role": "user", "content": "What is IRIS?"}],
    }


def test_a_parallel_tool_group_round_trips_in_order_with_its_ids_and_artifact():
    secret = {"signature": "opaque-SECRET-sig"}
    first = Vendor(reply(finish="tool_calls", reasoning_details=secret, tool_calls=[
        call("c-2", "search", '{"q": "b"}'), call("c-1", "outline"),
    ]))
    turn = admitted(adapter(first).converse(ask()))
    assert turn.stop is StopReason.TOOLS
    assert turn.items[0] == ToolGroup((ToolCall("c-2", "search", '{"q": "b"}'), ToolCall("c-1", "outline")))
    assert "SECRET" not in repr(turn)

    follow = Vendor(reply("Done."))
    admitted(adapter(follow).converse(ask(history=(turn, ToolResult("c-2", "two"), ToolResult("c-1", "one")))))
    messages = follow.bodies[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "tool"]
    assert [c["id"] for c in messages[2]["tool_calls"]] == ["c-2", "c-1"]
    assert messages[2]["reasoning_details"] == secret
    assert [m["tool_call_id"] for m in messages[3:]] == ["c-2", "c-1"]


@pytest.mark.parametrize("change", [
    {"model": "vendor/model-b"}, {"prompt_version": "agent-research-2"}, {"tool_version": "research-2"},
])
def test_an_artifact_is_never_forwarded_to_another_model_prompt_or_tool_version(change):
    from ai.agent.protocol import IncompatibleContinuation

    turn = admitted(adapter(Vendor(reply("Hi.", reasoning_details={"s": 1}))).converse(ask()))
    moved = Pin(**{**PIN.as_dict(), "requires": PIN.requires, **change})
    vendor = Vendor(reply("Never sent."))
    with pytest.raises(IncompatibleContinuation):
        admitted(adapter(vendor).converse(ask(pin=moved, history=(turn, User("again")))))
    assert vendor.requests == []


def test_an_unanswered_or_reordered_tool_group_is_refused_before_sending():
    from ai.agent.protocol import BrokenExchange

    turn = admitted(adapter(Vendor(reply(finish="tool_calls", tool_calls=[call("a", "s"), call("b", "s")])))
                    .converse(ask()))
    for results in ((ToolResult("b", "x"), ToolResult("a", "y")), (ToolResult("a", "y"),)):
        vendor = Vendor(reply("Never sent."))
        with pytest.raises(BrokenExchange):
            admitted(adapter(vendor).converse(ask(history=(turn, *results, User("next")))))
        assert vendor.requests == []


@pytest.mark.parametrize("wire, code", [
    (reply("Half an ans", finish="length"), "length"),
    (reply(None, reasoning="private working"), "reasoning_only"),
    (reply(None, reasoning_details={"s": 1}), "reasoning_only"),
    (reply(finish="tool_calls", tool_calls=[call("c-1", "search")]), "tool_only"),
    (reply("x", finish="mystery"), "malformed"),
    (httpx.Response(200, content=b"<html>not json</html>"), "malformed"),
])
def test_a_completion_that_is_not_a_final_answer_is_reported_as_what_it_is(wire, code):
    from ai.agent.protocol import NotFinal, final_answer

    turn = admitted(adapter(Vendor(wire)).converse(ask()))
    with pytest.raises(NotFinal) as refused:
        final_answer(turn)
    assert refused.value.code == code


# --- Admission ---------------------------------------------------------------

def test_outside_an_admitted_attempt_the_adapter_sends_nothing():
    from ai.admission.errors import AdmissionDenied

    vendor = Vendor(reply("Never sent."))
    with pytest.raises(AdmissionDenied) as refused:
        run(adapter(vendor).converse(ask()))
    assert refused.value.reason == "not_admitted"
    assert vendor.requests == []


def test_the_executor_refuses_the_adapter_unwrapped_before_sending():
    from ai.agent.executor import AgentExecutor
    from ai.runs.executor import Unavailable
    from .test_ai_runtime_context_contract import RESERVES

    vendor = Vendor(reply("Never sent."))
    direct = Pin(**{**PIN.as_dict(), "requires": PIN.requires,
                    "prompt_version": "agent-direct-1", "tool_version": "none-1"})
    with pytest.raises(Unavailable) as refused:
        run(AgentExecutor(adapter(vendor), direct, RESERVES).answer("q"))
    assert refused.value.code == "not_admitted"
    assert vendor.requests == []


def test_with_admission_limits_unset_a_paid_attempt_refuses_before_any_request():
    from ai.admission.errors import AdmissionDenied
    from ai.admission.ledger import Ledger
    from ai.admission.scope import RunBinding, bound
    from ai.admission.transport import AdmittedAgentProvider
    import uuid

    vendor = Vendor(reply("Never sent."))
    # No DSN is needed: unset limits refuse before the ledger connects.
    transport = AdmittedAgentProvider(adapter(vendor), Ledger("postgresql://unused/none", None))

    async def attempt():
        with bound(RunBinding(uuid.uuid4(), 1)):
            return await transport.converse(ask())

    with pytest.raises(AdmissionDenied) as refused:
        run(attempt())
    assert refused.value.reason == "not_configured"
    assert vendor.requests == []


# --- Failures ----------------------------------------------------------------

@pytest.mark.parametrize("failure", [
    httpx.Response(503, json={"error": {"message": "overloaded"}}),
    httpx.Response(429, json={"error": {"message": "slow down"}}),
    httpx.Response(500, text="oops"),
    httpx.ConnectError("refused"),
    httpx.ReadTimeout("slow"),
])
def test_a_transient_failure_is_one_attempt_surfaced_for_admission_to_settle(failure):
    from ai.domain.ports import TransientProviderError

    vendor = Vendor(failure, reply("A retry nobody asked for."))
    with pytest.raises(TransientProviderError):
        admitted(adapter(vendor).converse(ask()))
    # No retry inside the adapter: admission decides whether another attempt is made.
    assert len(vendor.requests) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_a_vendor_refusal_is_not_retried_and_carries_only_its_status(status):
    from ai.domain.ports import ProviderRejected

    vendor = Vendor(httpx.Response(status, json={"error": {"message": f"bad key {API_KEY}"}}))
    with pytest.raises(ProviderRejected) as refused:
        admitted(adapter(vendor).converse(ask()))
    assert str(refused.value) == f"status {status}"
    assert len(vendor.requests) == 1


def test_the_executor_reports_a_vendor_refusal_as_unavailable():
    from ai.agent.executor import AgentExecutor
    from ai.runs.executor import Unavailable
    from .test_ai_runtime_context_contract import RESERVES

    class Admitted(OpenAICompatibleAgentProvider):
        admitted = True

        async def converse(self, request):
            with scope.admitted_send():
                return await super().converse(request)

    vendor = Vendor(httpx.Response(401, json={}))
    direct = Pin(**{**PIN.as_dict(), "requires": PIN.requires,
                    "prompt_version": "agent-direct-1", "tool_version": "none-1"})
    target = Admitted.from_settings(SimpleNamespace(**CONFIG),
                                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(vendor)))
    with pytest.raises(Unavailable) as refused:
        run(AgentExecutor(target, direct, RESERVES).answer("q"))
    assert refused.value.code == "provider_rejected"


def test_credentials_payloads_and_artifacts_never_reach_the_logs(caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    secret = {"signature": "opaque-SECRET-sig"}
    vendor = Vendor(reply("Answer-TEXT.", reasoning_details=secret), httpx.Response(503, text="down"))
    target = adapter(vendor)
    turn = admitted(target.converse(ask("Question-TEXT")))
    with pytest.raises(Exception):
        admitted(target.converse(ask("Question-TEXT", history=(turn, User("again")))))
    logged = "\n".join(r.getMessage() for r in caplog.records) + repr(target.config)
    for marker in (API_KEY, "SECRET", "Question-TEXT", "Answer-TEXT"):
        assert marker not in logged


# --- Pin and declared capacity -----------------------------------------------

@pytest.mark.parametrize("change", [
    {"model": "vendor/unlisted"}, {"endpoint": "https://elsewhere.test/v1"}, {"adapter": "recording"},
    {"dialect": "responses-1"}, {"data_policy": "vendor-default"}, {"requires": ("native_compaction",)},
])
def test_a_pin_the_configuration_does_not_serve_is_not_accepted_and_sends_nothing(change):
    from ai.domain.ports import UnsupportedCapability

    pin = Pin(**{**PIN.as_dict(), "requires": PIN.requires, **change})
    vendor = Vendor(reply("Never sent."))
    target = adapter(vendor)
    assert not target.accepts(pin)
    assert target.capacity(pin) is None
    with pytest.raises(UnsupportedCapability):
        admitted(target.converse(ask(pin=pin)))
    assert vendor.requests == []


def test_the_pinned_research_dialect_is_served_with_its_declared_capacity():
    from ai.agent.context import Capacity

    target = adapter(Vendor())
    assert target.accepts(PIN)
    assert target.capacity(PIN) == Capacity(**CAPACITY)


def test_a_listed_model_without_declared_capacity_is_capacity_unknown():
    from ai.agent.context import CAPACITY_UNKNOWN, FittedAgentProvider, OverCapacity
    from .test_ai_runtime_context_contract import RESERVES

    pin = Pin(**{**PIN.as_dict(), "requires": PIN.requires, "model": "vendor/model-b"})
    vendor = Vendor(reply("Never sent."))
    target = adapter(vendor)
    assert target.accepts(pin) and target.capacity(pin) is None
    with pytest.raises(OverCapacity) as refused:
        admitted(FittedAgentProvider(target, RESERVES).converse(ask(pin=pin)))
    assert refused.value.code == CAPACITY_UNKNOWN
    assert vendor.requests == []


# --- Configuration, read at start --------------------------------------------

def read(**overrides):
    from ai.infrastructure import agent_config
    return agent_config.read(SimpleNamespace(**{**CONFIG, **overrides}))


@pytest.mark.parametrize("name", [
    "AGENT_LLM_ENDPOINT", "AGENT_LLM_API_KEY", "AGENT_LLM_MODELS", "AGENT_LLM_CAPABILITIES",
    "AGENT_LLM_DATA_POLICY", "AGENT_LLM_CAPACITIES",
])
def test_every_declaration_is_required_and_its_absence_is_named(name):
    from ai.admission.limits import NotConfigured

    with pytest.raises(NotConfigured) as missing:
        read(**{name: ""})
    assert name in str(missing.value)
    assert API_KEY not in str(missing.value)


@pytest.mark.parametrize("capacities", [
    {MODEL: {k: v for k, v in CAPACITY.items() if k != "max_reasoning_tokens"}},
    {MODEL: {**CAPACITY, "guessed_by_vendor": 1}},
    {MODEL: {**CAPACITY, "context_tokens": 0}},
    {MODEL: {**CAPACITY, "max_output_tokens": "lots"}},
    {"vendor/unlisted": CAPACITY},
    [CAPACITY],
])
def test_a_partial_inferred_or_unlisted_capacity_refuses_to_start(capacities):
    from ai.admission.limits import NotConfigured

    with pytest.raises(NotConfigured):
        read(AGENT_LLM_CAPACITIES=json.dumps(capacities))


def test_an_endpoint_that_is_not_a_url_refuses_to_start():
    from ai.admission.limits import NotConfigured

    with pytest.raises(NotConfigured):
        read(AGENT_LLM_ENDPOINT="vendor.test/v1")


def test_no_capacity_is_assumed_for_a_well_known_model_name():
    config = read(AGENT_LLM_MODELS="gpt-4o-mini", AGENT_LLM_CAPACITIES="{}")
    assert config.capacities == {}


def test_the_legacy_generate_response_adapter_is_unchanged(monkeypatch):
    from ai.domain.ports import UnsupportedCapability
    from ai.infrastructure import openai_adapter

    monkeypatch.setattr(openai_adapter.settings, "OPENAI_API_KEY", "sk-test-not-used")
    legacy = openai_adapter.OpenAILLMProvider()
    assert callable(legacy.generate_response)
    assert not legacy.accepts(PIN)
    with pytest.raises(UnsupportedCapability):
        run(legacy.converse(ask()))
