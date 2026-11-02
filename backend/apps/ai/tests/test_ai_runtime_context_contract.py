"""The complete outgoing request against verified model capacity (IR-732, ADR-049 §17).

Through the recording provider: the serialized payload is what is measured
and what is sent. A deterministic provider proves the contract, never a
vendor's real capacity.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent.context import Capacity, FittedAgentProvider, OverCapacity, Reserves  # noqa: E402
from ai.agent.dialect import ChatCompletions  # noqa: E402
from ai.agent.protocol import AgentRequest, Pin, ToolSpec, User  # noqa: E402
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402

PIN = Pin(
    model="scripted-model", endpoint="scripted", adapter="recording", dialect=ChatCompletions.name,
    prompt_version="agent-direct-1", tool_version="none-1", public_version=runs_config.PROTOCOL,
    state_version=runs_config.SCHEMA, data_policy="no-training",
)
# Fixture capacities only; neither describes a real vendor.
SMALL = Capacity(context_tokens=2_000, max_output_tokens=400, max_reasoning_tokens=None,
                 max_request_bytes=256_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)
MILLION = Capacity(context_tokens=1_000_000, max_output_tokens=32_000, max_reasoning_tokens=None,
                   max_request_bytes=8_000_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)
RESERVES = Reserves(output_tokens=200, reasoning_tokens=100, next_result_tokens=300, repair_tokens=100)


def run(coro):
    return asyncio.run(coro)


def reply(content="An answer."):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3}}


def recording(*responses, capacity=SMALL, **options):
    capacities = {} if capacity is None else {"scripted-model": capacity}
    return RecordingAgentProvider(responses=list(responses) or [reply()], capacities=capacities, **options)


def ask(question="What is IRIS?", history=(), tools=()):
    return AgentRequest(pin=PIN, instructions="Answer.", history=(User(question), *history), tools=tools)


def sent_bytes(payload):
    return len(json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8"))


def test_a_request_that_fits_is_sent_and_its_status_measures_the_sent_payload():
    target = recording()
    fitted = FittedAgentProvider(target, RESERVES)
    run(fitted.converse(ask()))
    [payload] = target.requests
    [status] = fitted.statuses
    assert status.outcome == "fits"
    assert status.estimated is True
    assert status.request_bytes == sent_bytes(payload)
    # The output cap sent covers the answer and reasoning counted inside it.
    assert payload["max_tokens"] == 300


def refused(fitted, request):
    with pytest.raises(OverCapacity) as caught:
        run(fitted.converse(request))
    return caught.value


def test_unknown_capacity_refuses_before_sending_and_never_assumes_a_million():
    target = recording(capacity=None)
    fitted = FittedAgentProvider(target, RESERVES)
    assert refused(fitted, ask()).code == "capacity_unknown"
    assert target.requests == []
    assert fitted.statuses[-1].context_tokens == 0


# Large fixtures: a ~30 KB tool schema, a ~40 KB history and a ~20 KB opaque artifact.
SCHEMA = ToolSpec("search", "Search. " + "s" * 30_000)
OPAQUE_SECRET = "OPAQUE-SECRET-" + "o" * 20_000


def large_history():
    from ai.agent.protocol import ModelTurn, Opaque, StopReason, Text
    earlier = ModelTurn(items=(Text("e" * 20_000),
                               Opaque(binding=PIN.binding(), field="reasoning_details",
                                      payload={"signature": OPAQUE_SECRET})),
                        stop=StopReason.END)
    return (earlier, User("h" * 20_000))


def test_large_schema_history_and_opaque_fixtures_refuse_small_capacity_and_fit_a_million():
    request = ask(history=large_history(), tools=(SCHEMA,))

    small = recording(capacity=SMALL)
    small_fitted = FittedAgentProvider(small, RESERVES)
    assert refused(small_fitted, request).code == "context_exhausted"
    assert small.requests == []

    large = recording(capacity=MILLION)
    large_fitted = FittedAgentProvider(large, RESERVES)
    run(large_fitted.converse(request))
    [payload] = large.requests
    [status] = large_fitted.statuses
    assert status.outcome == "fits"
    assert status.request_bytes == sent_bytes(payload)
    assert status.request_bytes > 90_000
    # Nothing was clipped: the full schema, history and artifact went out.
    assert payload["tools"][0]["function"]["description"] == SCHEMA.description
    assert payload["messages"][2]["reasoning_details"] == {"signature": OPAQUE_SECRET}
    assert payload["messages"][1]["content"] == "What is IRIS?"
    assert payload["messages"][3]["content"] == "h" * 20_000


def test_each_part_of_the_payload_is_counted_and_framing_is_the_rest():
    request = ask(history=large_history(), tools=(SCHEMA,))
    fitted = FittedAgentProvider(recording(capacity=MILLION), RESERVES)
    run(fitted.converse(request))
    [status] = fitted.statuses
    assert status.tools_bytes > 30_000
    assert status.opaque_bytes > 20_000
    assert status.history_bytes > 40_000
    assert status.instructions_bytes == len('"Answer."')
    parts = (status.instructions_bytes + status.tools_bytes + status.history_bytes
             + status.evidence_bytes + status.opaque_bytes)
    assert status.framing_bytes > 0
    assert parts + status.framing_bytes == status.request_bytes
    # Four messages, four framing tokens each, on a one-byte-per-token floor.
    assert status.occupancy_tokens == status.request_bytes + 4 * 4


def test_opaque_size_is_accounted_but_its_content_never_reaches_the_status():
    request = ask(history=large_history())
    fitted = FittedAgentProvider(recording(capacity=SMALL), RESERVES)
    caught = refused(fitted, request)
    assert caught.status.opaque_bytes > 20_000
    assert "OPAQUE-SECRET" not in repr(caught.status)
    assert "OPAQUE-SECRET" not in json.dumps(caught.status.as_dict())
    assert "OPAQUE-SECRET" not in str(caught)


def test_a_pin_over_capacity_is_refused_and_no_smaller_or_larger_model_is_tried():
    pin = Pin(**{**PIN.as_dict(), "requires": (), "model": "small-model"})
    target = RecordingAgentProvider(
        responses=[reply()], models=("small-model", "large-model"),
        capacities={"small-model": SMALL, "large-model": MILLION},
    )
    request = AgentRequest(pin=pin, instructions="Answer.", history=(User("x" * 5_000),))
    fitted = FittedAgentProvider(target, RESERVES)
    assert refused(fitted, request).code == "context_exhausted"
    assert target.requests == []


def test_the_byte_limit_binds_even_when_the_token_window_would_not():
    tight = Capacity(context_tokens=1_000_000, max_output_tokens=32_000, max_reasoning_tokens=None,
                     max_request_bytes=10_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)
    target = recording(capacity=tight)
    caught = refused(FittedAgentProvider(target, RESERVES), ask("q" * 12_000))
    assert caught.code == "request_bytes_exceeded"
    assert caught.status.request_bytes > caught.status.max_request_bytes == 10_000
    assert target.requests == []


def test_reserves_are_held_back_before_any_history_is_admitted():
    # 2,000-token window: 700 reserved leaves under 1,300 for the request itself.
    fits = ask("q" * 1_100)
    over = ask("q" * 1_250)
    assert run(FittedAgentProvider(recording(), RESERVES).converse(fits))
    target = recording()
    caught = refused(FittedAgentProvider(target, RESERVES), over)
    assert caught.code == "context_exhausted"
    assert caught.status.reserved_tokens == 700
    assert caught.status.occupancy_tokens + 700 > 2_000
    assert target.requests == []


@pytest.mark.parametrize("reserves, capacity, code", [
    (Reserves(output_tokens=300, reasoning_tokens=200, next_result_tokens=0, repair_tokens=0),
     SMALL, "reserve_exceeds_output"),
    (Reserves(output_tokens=300, reasoning_tokens=0, next_result_tokens=1_500, repair_tokens=300),
     SMALL, "reserve_exceeds_context"),
    (Reserves(output_tokens=300, reasoning_tokens=900, next_result_tokens=0, repair_tokens=0),
     Capacity(context_tokens=2_000, max_output_tokens=400, max_reasoning_tokens=800,
              max_request_bytes=64_000, min_bytes_per_token=1.0, framing_tokens_per_message=4),
     "reserve_exceeds_output"),
])
def test_reserves_the_model_cannot_honour_are_refused(reserves, capacity, code):
    target = recording(capacity=capacity)
    assert refused(FittedAgentProvider(target, reserves), ask()).code == code
    assert target.requests == []


def test_separately_budgeted_reasoning_is_not_added_to_the_output_cap():
    separate = Capacity(context_tokens=2_000, max_output_tokens=400, max_reasoning_tokens=800,
                        max_request_bytes=64_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)
    target = recording(capacity=separate)
    run(FittedAgentProvider(target, RESERVES).converse(ask()))
    assert target.requests[0]["max_tokens"] == 200


def test_a_denser_tokenizer_floor_lowers_the_estimate_and_says_it_is_one():
    dense = Capacity(context_tokens=2_000, max_output_tokens=400, max_reasoning_tokens=None,
                     max_request_bytes=64_000, min_bytes_per_token=4.0, framing_tokens_per_message=0)
    fitted = FittedAgentProvider(recording(capacity=dense), RESERVES)
    run(fitted.converse(ask("q" * 4_000)))
    [status] = fitted.statuses
    assert status.estimated is True
    assert status.occupancy_tokens == -(-status.request_bytes // 4)


def test_capacity_and_reserves_refuse_missing_or_nonsense_values():
    with pytest.raises(TypeError):
        Capacity(context_tokens=1_000_000)
    with pytest.raises(ValueError):
        Capacity(context_tokens=0, max_output_tokens=1, max_reasoning_tokens=None,
                 max_request_bytes=1, min_bytes_per_token=1.0, framing_tokens_per_message=0)
    with pytest.raises(ValueError):
        Reserves(output_tokens=0, reasoning_tokens=0, next_result_tokens=0, repair_tokens=0)


# --- Tool results admitted into the window -------------------------------------

def tool_turn(*ids):
    from ai.agent.protocol import ModelTurn, StopReason, ToolCall, ToolGroup
    return ModelTurn(items=(ToolGroup(tuple(ToolCall(i, "search") for i in ids)),), stop=StopReason.TOOLS)


def test_an_oversized_tool_result_is_withheld_explicitly_and_the_group_stays_whole():
    from ai.agent.protocol import ToolResult

    target = recording(reply("Done."))
    fitted = FittedAgentProvider(target, RESERVES)
    request = ask(history=(tool_turn("c-1", "c-2", "c-3"),))
    results = [ToolResult("c-1", "small one"), ToolResult("c-2", "BIG-" + "x" * 50_000),
               ToolResult("c-3", "small three")]
    packed, status = fitted.pack(request, results)
    assert status.outcome == "fits"
    assert status.withheld_results == 1
    assert [r.call_id for r in packed.history[2:]] == ["c-1", "c-2", "c-3"]
    assert packed.history[2].content == "small one"
    assert packed.history[4].content == "small three"
    marker = json.loads(packed.history[3].content)
    assert marker == {"withheld": "exceeds_context", "bytes": 50_004, "coverage": "none"}

    run(fitted.converse(packed))
    [payload] = target.requests
    assert "BIG-" not in json.dumps(payload)
    assert [m.get("tool_call_id") for m in payload["messages"][-3:]] == ["c-1", "c-2", "c-3"]


def test_results_that_fit_are_admitted_unchanged_and_counted_as_evidence():
    from ai.agent.protocol import ToolResult

    fitted = FittedAgentProvider(recording(capacity=MILLION), RESERVES)
    big = "y" * 50_000
    packed, status = fitted.pack(ask(history=(tool_turn("c-1"),)), [ToolResult("c-1", big)])
    assert packed.history[-1].content == big
    assert status.withheld_results == 0
    assert status.evidence_bytes == len(json.dumps(big))


@pytest.mark.parametrize("compaction, code", [(False, "context_exhausted"), (True, "compaction_required")])
def test_when_not_even_the_markers_fit_the_group_is_refused_or_compaction_requested(compaction, code):
    from ai.agent.protocol import ToolResult

    target = recording()
    fitted = FittedAgentProvider(target, RESERVES, compaction=compaction)
    crowded = ask("q" * 1_150, history=(tool_turn(*[f"c-{n}" for n in range(8)]),))
    with pytest.raises(OverCapacity) as caught:
        fitted.pack(crowded, [ToolResult(f"c-{n}", "z" * 10_000) for n in range(8)])
    assert caught.value.code == code
    assert target.requests == []


def test_an_incomplete_or_reordered_group_is_never_packed():
    from ai.agent.protocol import BrokenExchange, ToolResult

    fitted = FittedAgentProvider(recording(capacity=MILLION), RESERVES)
    request = ask(history=(tool_turn("c-1", "c-2"),))
    for results in ([ToolResult("c-1", "a")], [ToolResult("c-2", "b"), ToolResult("c-1", "a")]):
        with pytest.raises(BrokenExchange):
            fitted.pack(request, results)


# --- The AGENT executor --------------------------------------------------------

def test_the_executor_sends_a_question_that_fits_and_keeps_its_capacity_status():
    from ai.agent.executor import AgentExecutor

    target = recording(reply("IRIS is a repository."))
    executor = AgentExecutor(target, PIN, RESERVES)
    result = run(executor.answer("What is IRIS?"))
    assert result.answer == "IRIS is a repository."
    [payload] = target.requests
    assert executor.capacity_status.outcome == "fits"
    assert executor.capacity_status.request_bytes == sent_bytes(payload)


@pytest.mark.parametrize("capacity, question, code", [
    (None, "q", "capacity_unknown"),
    (SMALL, "q" * 5_000, "context_exhausted"),
])
def test_the_executor_refuses_over_capacity_as_unavailable_before_transport(capacity, question, code, caplog):
    from ai.agent.executor import AgentExecutor
    from ai.runs.executor import Unavailable

    target = recording(capacity=capacity)
    executor = AgentExecutor(target, PIN, RESERVES)
    with caplog.at_level("INFO", logger="ai.agent.context"):
        with pytest.raises(Unavailable) as caught:
            run(executor.answer(question))
    assert caught.value.code == code
    assert target.requests == []
    assert executor.capacity_status.outcome == code
    # Operators get numbers, never the question.
    assert code in caplog.text and "qqqq" not in caplog.text


def test_a_large_early_result_is_withheld_when_keeping_it_would_leave_no_room_for_the_rest():
    from ai.agent.protocol import ToolResult

    window = Capacity(context_tokens=2_700, max_output_tokens=400, max_reasoning_tokens=None,
                      max_request_bytes=256_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)
    fitted = FittedAgentProvider(recording(capacity=window), RESERVES)
    # 2,000 tokens of room: the first result fits alone (~1,800) but not with five markers (~2,470).
    request = ask(history=(tool_turn(*[f"c-{n}" for n in range(6)]),))
    results = [ToolResult("c-0", "a" * 1_000)] + [ToolResult(f"c-{n}", "b" * 5_000) for n in range(1, 6)]
    packed, status = fitted.pack(request, results)
    assert status.outcome == "fits"
    assert [r.call_id for r in packed.history[2:]] == [f"c-{n}" for n in range(6)]
    assert status.withheld_results == 6
