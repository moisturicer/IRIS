"""IR-889: recording-provider checks at the paid physical-send boundary."""

import asyncio
import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ai.admission.errors import AdmissionDenied
from ai.admission.guard import ProxyApproval, SendGuard, routing_digest
from ai.admission.limits import Price
from ai.admission.scope import RunBinding, bound
from ai.admission.transport import AdmittedAgentProvider
from ai.agent.dialect import ChatCompletions
from ai.agent.protocol import AgentRequest, ModelTurn, Pin, StopReason, ToolCall, ToolGroup, ToolResult, User
from ai.infrastructure.recording_adapter import RecordingAgentProvider
from ai.domain.ports import TransientProviderError
from ai.research.tools import Source


SOURCE = Source(7, 31, "source-a")
PIN = Pin("scripted-model", "scripted", "recording", ChatCompletions.name,
          "agent-research-1", "research-1", "runs-1", "0004_agent.sql", "no-training")
BINDING = RunBinding(uuid.uuid4(), 1)


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class Connection:
    def __init__(self, *, reader="active", origin="imported_reference", revision="source-a"):
        self.run = {"state": "running", "fence": 1, "overdue": False, "granted": True,
                    "reader": reader, "reader_id": 9, "reader_grant": "grant", "scope_record_id": None}
        self.record = {"id": 7, "origin": origin, "is_ip": False,
                       "is_embargoed": False, "embargo_released_at": datetime.now(timezone.utc),
                       "chunk_set_id": 31, "extraction_hash": revision}

    def transaction(self):
        return Transaction()

    async def fetchrow(self, *_):
        return self.run

    async def fetchval(self, *_):
        return 9

    async def fetch(self, *_):
        return [self.record]

    async def close(self):
        pass


class Ticket:
    timeout_seconds = 1

    def __init__(self):
        self.usage = None

    async def settle(self, usage):
        self.usage = usage


class Ledger:
    dsn = "unused"
    limits = SimpleNamespace(max_output_tokens=100, campaign_key="pilot", prices={})

    def __init__(self):
        self.tickets = []

    async def admit(self, *_):
        ticket = Ticket()
        self.tickets.append(ticket)
        return ticket


def request(source=SOURCE):
    return AgentRequest(PIN, "Research", (
        User("What does the paper say?"),
        ModelTurn((ToolGroup((ToolCall("c1", "search"),)),), StopReason.TOOLS),
        ToolResult("c1", json.dumps({"status": "ok", "passages": [{"text": "Public passage"}]}),
                   frozenset({source})),
    ), max_output_tokens=10)


def approval(provider):
    return ProxyApproval("IR-889", PIN.model, PIN.endpoint, provider.account, "pilot",
                         datetime.now(timezone.utc) + timedelta(hours=1), frozenset({SOURCE}))


ANSWER = {
        "choices": [{"message": {"role": "assistant", "content": "Public answer."},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }


def send(monkeypatch, *, connection=None, approval_enabled=True, stage="development", entry=None,
         responses=None, retries=0, approval_change=None):
    provider = RecordingAgentProvider(responses=responses or [ANSWER])
    ledger = Ledger()
    selected = approval(provider) if approval_enabled else None
    if selected is not None and approval_change is not None:
        selected = approval_change(selected)
    guard = SendGuard("unused", selected, stage=stage)
    transport = AdmittedAgentProvider(provider, ledger, guard=guard, retries=retries)

    async def connect(*_):
        return connection or Connection()

    monkeypatch.setattr("ai.admission.guard.asyncpg.connect", connect)
    with bound(BINDING):
        try:
            turn = asyncio.run(transport.converse(entry or request()))
            reason = None
        except AdmissionDenied as denied:
            turn, reason = None, denied.reason
    return provider, ledger.tickets, turn, reason


def test_approved_proxy_payload_reaches_the_recording_provider(monkeypatch):
    provider, tickets, turn, reason = send(monkeypatch)
    assert reason is None and turn.text == "Public answer."
    assert turn.dependencies == {SOURCE}
    assert provider.requests[0]["messages"][-1]["content"].find("Public passage") >= 0
    assert tickets[0].usage.sent


@pytest.mark.parametrize("connection,reason", [
    (Connection(revision="source-b"), "source_unavailable"),
    (Connection(origin="institutional"), "source_unavailable"),
    (Connection(reader="inactive"), "access_revoked"),
])
def test_changed_withheld_or_revoked_source_sends_nothing(monkeypatch, connection, reason):
    provider, tickets, turn, refused = send(monkeypatch, connection=connection)
    assert turn is None and refused == reason
    assert provider.requests == []
    assert not tickets[0].usage.sent


def test_missing_approval_or_development_stage_sends_nothing(monkeypatch):
    for options in ({"approval_enabled": False}, {"stage": "production"}):
        provider, tickets, turn, reason = send(monkeypatch, **options)
        assert turn is None and reason == "source_unavailable"
        assert provider.requests == [] and not tickets[0].usage.sent


@pytest.mark.parametrize("change", [
    lambda item: replace(item, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)),
    lambda item: replace(item, account="another-account"),
    lambda item: replace(item, campaign="another-campaign"),
    lambda item: replace(item, model="another-model"),
])
def test_expired_or_mismatched_approval_sends_nothing(monkeypatch, change):
    provider, tickets, turn, reason = send(monkeypatch, approval_change=change)
    assert turn is None and reason == "source_unavailable"
    assert provider.requests == [] and not tickets[0].usage.sent


def test_operator_manifest_requires_exact_fields_and_source_revision():
    provider = RecordingAgentProvider(responses=[ANSWER])
    selected = approval(provider)
    raw = json.dumps({
        "approval_id": selected.approval_id, "model": selected.model,
        "endpoint": selected.endpoint, "account": selected.account,
        "campaign": selected.campaign, "expires_at": selected.expires_at.isoformat(),
        "sources": [{"record_id": 7, "chunk_set_id": 31, "extraction_hash": "source-a"}],
    })
    assert ProxyApproval.from_json(raw) == selected
    assert ProxyApproval.from_json(raw.replace("source-a", "")) is None
    assert ProxyApproval.from_json(raw.replace('"sources"', '"other"')) is None


def test_changed_source_blocks_a_retry_after_one_physical_send(monkeypatch):
    connection = Connection()

    def fail_then_replace(_):
        connection.record["extraction_hash"] = "source-b"
        return TransientProviderError("vendor unavailable")

    provider, tickets, turn, reason = send(
        monkeypatch, connection=connection, responses=[fail_then_replace, ANSWER], retries=1)
    assert turn is None and reason == "source_unavailable"
    assert len(provider.requests) == 1
    assert [ticket.usage.sent for ticket in tickets] == [True, False]


def test_unverified_prior_answer_and_untagged_paper_text_are_refused(monkeypatch):
    stale = AgentRequest(PIN, "Research", (
        ModelTurn((ToolGroup((ToolCall("c1", "search"),)),), StopReason.TOOLS),
        ToolResult("c1", "paper text without source"),
    ))
    provider, tickets, _, reason = send(monkeypatch, entry=stale)
    assert reason == "source_unavailable"
    assert provider.requests == [] and not tickets[0].usage.sent

    prior = AgentRequest(PIN, "Research", (
        ModelTurn((ToolGroup((ToolCall("c1", "search"),)),), StopReason.TOOLS),
        ToolResult("c1", '{"status":"ok"}', frozenset()),
        ModelTurn((), StopReason.END, unverified_provenance=True),
    ))
    provider, tickets, _, reason = send(monkeypatch, entry=prior)
    assert reason == "source_unavailable"
    assert provider.requests == [] and not tickets[0].usage.sent


def test_neutral_withheld_marker_can_continue_without_source_details(monkeypatch):
    neutral = AgentRequest(PIN, "Research", (
        ModelTurn((ToolGroup((ToolCall("c1", "search"),)),), StopReason.TOOLS),
        ToolResult("c1", '{"withheld":"exceeds_context","coverage":"none"}',
                   control_only=True),
    ))
    provider, tickets, turn, reason = send(monkeypatch, approval_enabled=False, entry=neutral)
    assert reason is None and turn.text == "Public answer."
    assert provider.requests[-1]["messages"][-1]["content"] == neutral.history[-1].content
    assert tickets[0].usage.sent


def test_real_adapter_remains_closed_without_vendor_account_evidence(monkeypatch):
    real_pin = replace(PIN, adapter="openai-compatible")
    provider, tickets, turn, reason = send(monkeypatch, entry=replace(request(), pin=real_pin))
    assert turn is None and reason == "source_unavailable"
    assert provider.requests == [] and not tickets[0].usage.sent


ROUTING = {"only": ["azure/us"], "allow_fallbacks": False, "data_collection": "deny",
           "zdr": True, "require_parameters": True,
           "max_price": {"prompt": 0.22, "completion": 0.825}}
REAL_PIN = replace(PIN, adapter="openai-compatible", endpoint="https://openrouter.ai/api/v1",
                   model="openai/gpt-6-luna:floor")


def test_real_proxy_requires_account_evidence_routing_and_covering_price(monkeypatch):
    conn = Connection()

    async def connect(*_):
        return conn

    monkeypatch.setattr("ai.admission.guard.asyncpg.connect", connect)
    approval = ProxyApproval("IR-889", REAL_PIN.model, REAL_PIN.endpoint, "account", "pilot",
                             datetime.now(timezone.utc) + timedelta(hours=1), frozenset({SOURCE}),
                             "https://citiris.atlassian.net/browse/IR-827", routing_digest(ROUTING))
    guard = SendGuard("unused", approval, stage="development")

    def check(**overrides):
        options = {"account": "account", "campaign": "pilot", "routing": ROUTING,
                   "price": Price(0.22, 0.825), **overrides}
        return asyncio.run(guard.check(BINDING, REAL_PIN, request().history, **options))

    check()
    asyncio.run(guard.check(BINDING, REAL_PIN, (), account="account", campaign="pilot",
                            routing=ROUTING, price=Price(0.22, 0.825)))
    with pytest.raises(AdmissionDenied):
        asyncio.run(SendGuard("unused", stage="development").check(
            BINDING, REAL_PIN, (), account="account", campaign="pilot",
            routing=ROUTING, price=Price(0.22, 0.825)))
    for options in ({"routing": {**ROUTING, "zdr": False}},
                    {"price": Price(0.05, 0.25)}, {"account": "other"}):
        with pytest.raises(AdmissionDenied):
            check(**options)
    conn.record["is_embargoed"] = True
    conn.record["embargo_released_at"] = None
    with pytest.raises(AdmissionDenied):
        check()
