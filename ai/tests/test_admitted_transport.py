"""The admitted transport sends a request whole, with no send-time check (IR-996)."""

import asyncio
import json
import uuid
from types import SimpleNamespace

from ai.admission.scope import RunBinding, bound
from ai.admission.transport import AdmittedAgentProvider
from ai.agent.dialect import ChatCompletions
from ai.agent.protocol import AgentRequest, ModelTurn, Pin, StopReason, ToolCall, ToolGroup, ToolResult, User
from ai.infrastructure.recording_adapter import RecordingAgentProvider
from ai.research.tools import Source

SOURCE = Source(7, 31, "source-a")
PIN = Pin("scripted-model", "scripted", "recording", ChatCompletions.name,
          "agent-research-1", "research-1", "runs-1", "0004_agent.sql", "")
ANSWER = {"choices": [{"message": {"role": "assistant", "content": "Answer."}, "finish_reason": "stop"}],
          "usage": {"prompt_tokens": 10, "completion_tokens": 3}}
TEXT = "Unpublished institutional passage."


class Ticket:
    timeout_seconds = 1
    usage = None

    async def settle(self, usage):
        self.usage = usage


class Ledger:
    dsn = "unused"
    limits = SimpleNamespace(max_output_tokens=100, campaign_key="pilot", prices={})

    def __init__(self):
        self.tickets = []

    async def admit(self, *_):
        self.tickets.append(Ticket())
        return self.tickets[-1]


def request(*history):
    return AgentRequest(PIN, "Research", history, max_output_tokens=10)


def send(entry):
    provider = RecordingAgentProvider(responses=[ANSWER], data_policies=("",))
    ledger = Ledger()
    with bound(RunBinding(uuid.uuid4(), 1)):
        turn = asyncio.run(AdmittedAgentProvider(provider, ledger).converse(entry))
    return provider, ledger.tickets, turn


def test_paper_text_is_sent_unchanged_with_no_approval_and_no_data_policy():
    entry = request(User("What does it say?"),
                    ModelTurn((ToolGroup((ToolCall("c1", "search"),)),), StopReason.TOOLS),
                    ToolResult("c1", json.dumps({"status": "ok", "passages": [{"text": TEXT}]}),
                               frozenset({SOURCE})))
    provider, tickets, turn = send(entry)
    assert TEXT in json.dumps(provider.requests[-1]["messages"])
    assert turn.text == "Answer." and turn.dependencies == {SOURCE}
    assert tickets[0].usage.sent


def test_a_result_naming_no_source_and_an_unlabelled_answer_are_sent_too():
    entry = request(User("Earlier?"), ModelTurn((), StopReason.END, unverified_provenance=True),
                    User("And now?"),
                    ModelTurn((ToolGroup((ToolCall("c1", "search"),)),), StopReason.TOOLS),
                    ToolResult("c1", json.dumps({"status": "ok", "text": TEXT})))
    provider, tickets, turn = send(entry)
    assert TEXT in json.dumps(provider.requests[-1]["messages"])
    assert tickets[0].usage.sent
