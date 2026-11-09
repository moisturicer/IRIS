"""One bounded AGENT Conversation through the authenticated routes, on real PostgreSQL (IR-728).

A two-paper question, a follow-up about "the second one" that falls into a
no-progress loop, and Paper Chat, under a restricted runtime login with
Django-issued grants. The recording provider proves the contract, never a
vendor's behaviour; the admitted case shows every attempt's purpose.
"""

import json
import threading
from dataclasses import replace
from datetime import timedelta

import pytest
from django.utils import timezone

from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_runs_db import Drain, as_reader, run, submit
from .test_ai_runtime_research_db import paper, write_source
from ai.admission.ledger import Ledger  # noqa: E402
from ai.admission.guard import ProxyApproval, SendGuard  # noqa: E402
from ai.admission.transport import AdmittedAgentProvider  # noqa: E402
from ai.agent.budget import Bounds  # noqa: E402
from ai.agent.dialect import ChatCompletions  # noqa: E402
from ai.agent.executor import FINAL_NOTE, AgentExecutor  # noqa: E402
from ai.agent.protocol import Pin  # noqa: E402
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402
from ai.runs.service import RunService  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from ai.research.tools import Source  # noqa: E402
from apps.ai.grants import issue  # noqa: E402
from apps.ai.models.chunk import ChunkSet  # noqa: E402
from apps.ai.models.admission import ProviderReservation  # noqa: E402
from apps.records.models import Record  # noqa: E402
from .corpus import make_user  # noqa: E402
from .test_ai_runtime_admission_db import RESERVES as ADMITTED_RESERVES, limits  # noqa: E402
from .test_ai_runtime_context_contract import MILLION, RESERVES  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime
api = runs_db.api

PIN = Pin(
    model="scripted-model", endpoint="scripted", adapter="recording", dialect=ChatCompletions.name,
    prompt_version="agent-research-1", tool_version="research-1", public_version=runs_config.PROTOCOL,
    state_version=runs_config.SCHEMA, data_policy="no-training",
)
# Test bounds only; no production value is implied.
BOUNDS = Bounds(max_steps=6, max_tool_calls=12, max_no_progress=2, final_seconds=5, history_turns=4)
PROFILES = {"ordinary": BOUNDS, "deep": BOUNDS}
LIMITS = runs_config.RunLimits(
    deadline_seconds=120, deep_deadline_seconds=600, lease_seconds=30, max_attempts=2,
    max_input_tokens=1_000_000, max_output_tokens=50_000, max_cost_usd=0.5,
)
FLOOD = "rainfall gauges and river water levels trained a network to forecast floods"
POND = "brackish water ponds were sampled weekly for tilapia growth"


def agent_service(dsn, provider, *, run_limits=LIMITS, **kw):
    cfg = runs_config.RunsConfig(database_url=dsn, executor="deterministic", limits=run_limits,
                                 dispatch=runs_db.DISPATCH)
    executor = AgentExecutor(provider, PIN, kw.pop("reserves", RESERVES), profiles=PROFILES, **kw)
    built = RunService(RunStore(dsn), cfg, executor, Drain())
    built.notifier.service = built
    return built


def call(id_, name, **arguments):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def tools(*calls):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": list(calls)},
                         "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 5}}


def reply(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 60, "completion_tokens": 20}}


def last_result(payload):
    return json.loads(payload["messages"][-1]["content"])


def results(payload):
    return [json.loads(m["content"]) for m in payload["messages"] if m["role"] == "tool"]


def state_message(payload):
    prefix = "[IRIS conversation state] "
    [state] = [json.loads(m["content"][len(prefix):]) for m in payload["messages"]
               if m["role"] == "user" and m["content"].startswith(prefix)]
    return state


def recording(*responses):
    return RecordingAgentProvider(responses=list(responses), capacities={"scripted-model": MILLION})


def models(run_):
    return [e["data"] for e in run_["events"] if e["name"] == "model"]


def test_a_two_paper_question_then_the_second_one_through_a_bounded_no_progress_loop(api, runtime):
    client, holder = api
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    pond = paper("Pond sampling", {2: [("Methods", POND)]})
    grant = issue.reader_session_grant(make_user("agent-loop@cit.edu")).token

    def both(payload):
        found = {p["paper"]: p for p in last_result(payload)["passages"]}
        titles = {p["paper"]: p["title"] for p in last_result(payload)["papers"]}
        cited = " and ".join(f"«{titles[h]}» [{p['passage']}]" for h, p in found.items())
        return reply(f"{cited} both study water.")

    first = recording(tools(call("s", "search", query="water")), both)
    holder["service"] = agent_service(runtime, first)
    asked = submit(client, grant, "agent-loop-1", "Which papers study water?").json()
    assert asked["state"] == "completed"
    reopened = client.get(f"/api/v1/ai/conversations/{asked['conversation_id']}", headers=as_reader(grant)).json()
    [turn] = reopened["turns"]
    assert turn["kind"] == "answer" and "[1]" in turn["answer"] and "[2]" in turn["answer"]
    shown = [c["record_id"] for c in turn["citations"]]
    assert sorted(shown) == sorted([flood.pk, pond.pk])

    def second_one(payload):
        state = state_message(payload)
        [entry] = [s for s in state["shown"] if s["position"] == 2]
        return tools(call("f", "update_focus", selected=[entry["paper"]]),
                     call("r", "read_page", paper=entry["paper"], page=4 if entry["title"] == "Flood forecasting" else 2))

    def same_page_again(payload):
        page = next(r for r in results(payload) if "passages" in r)
        return tools(call(f"again-{len(payload['messages'])}", "open_passage",
                          passage=page["passages"][0]["passage"]))

    def answer_second(payload):
        assert payload["tool_choice"] == "none" and payload["tools"]
        assert payload["messages"][-1] == {"role": "user", "content": FINAL_NOTE}
        page = next(r for r in results(payload) if "passages" in r)
        return reply(f"It is described on that page [{page['passages'][0]['passage']}].")

    follow = recording(second_one, same_page_again, same_page_again, answer_second)
    holder["service"] = agent_service(runtime, follow)
    question = "Tell me about the second one."
    answered = submit(client, grant, "agent-loop-2", question,
                      conversation_id=asked["conversation_id"], base_revision=1).json()
    assert answered["state"] == "completed", answered

    second = shown[1]
    reopened = client.get(f"/api/v1/ai/conversations/{asked['conversation_id']}", headers=as_reader(grant)).json()
    assert [c["record_id"] for c in reopened["turns"][1]["citations"]] == [second]
    # Bounded: three gathering turns, the last two finding nothing new, then one final turn.
    assert [m["phase"] for m in models(answered)] == ["gather", "gather", "gather", "final"]
    # One writer: every attempt is the agent's, all under the same instructions and tools.
    assert {m["purpose"] for m in models(answered)} == {"agent"}
    assert len(follow.requests) == len(models(answered))
    assert len({json.dumps([r["messages"][0], r["tools"]]) for r in follow.requests}) == 1
    # The reader's words reach every request unchanged, after the earlier Turn.
    for payload in follow.requests:
        users = [m["content"] for m in payload["messages"] if m["role"] == "user"]
        assert users[0] == "Which papers study water?" and question in users

    # The selection and the new shown order survive into the next Turn.
    third = recording(reply("Noted."))
    holder["service"] = agent_service(runtime, third)
    assert submit(client, grant, "agent-loop-3", "Thanks.", conversation_id=asked["conversation_id"],
                  base_revision=2).json()["state"] == "completed"
    state = state_message(third.requests[0])
    [entry] = state["shown"]
    assert state["selected"] == [entry["paper"]]


def test_paper_chat_stays_on_its_record_whatever_the_model_asks(api, runtime):
    client, holder = api
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    pond = paper("Pond sampling", {2: [("Methods", POND)]})
    grant = issue.reader_session_grant(make_user("agent-paper-chat@cit.edu"), flood.pk).token

    def cite(payload):
        passage = last_result(payload)["passages"][0]
        return reply(f"It forecasts floods [{passage['passage']}].")

    provider = recording(
        tools(call("w", "search", query="water", scope_record_id=pond.pk)),
        tools(call("s", "search", query="water")),
        cite,
    )
    holder["service"] = agent_service(runtime, provider)
    run_ = submit(client, grant, "agent-paper-chat", "What does this paper study?").json()
    assert run_["state"] == "completed"
    assert last_result(provider.requests[1]) == {"error": "invalid_arguments"}
    found = last_result(provider.requests[2])
    assert [p["title"] for p in found["papers"]] == ["Flood forecasting"]
    reopened = client.get(f"/api/v1/ai/conversations/{run_['conversation_id']}", headers=as_reader(grant)).json()
    assert [c["record_id"] for c in reopened["turns"][0]["citations"]] == [flood.pk]


def test_a_draft_that_fails_both_repairs_is_delivered_whole_and_marked(api, runtime):
    """Never refused over a check: the citation that names nothing is removed, the claim is qualified."""
    client, holder = api
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    grant = issue.reader_session_grant(make_user("agent-invalid@cit.edu")).token
    invalid = reply("It forecast 912 floods [P00000000000000000009].")
    provider = recording(tools(call("s", "search", query="water")), invalid, invalid, invalid)
    holder["service"] = agent_service(runtime, provider)
    run_ = submit(client, grant, "agent-invalid", "How many floods?").json()
    assert run_["state"] == "completed"
    assert [m["phase"] for m in models(run_)] == ["gather", "gather", "repair", "repair"]
    reopened = client.get(f"/api/v1/ai/conversations/{run_['conversation_id']}", headers=as_reader(grant)).json()
    [turn] = reopened["turns"]
    assert turn["answer"] == "It forecast 912 floods. (the sources read do not establish this)"
    assert turn["citations"] == []


# --- One repair (IR-729) -------------------------------------------------------

VALIDATION_CODES = ("unknown_citation", "excluded_citation", "unsupported_number", "unknown_title",
                    "completeness_overclaim")


def passage_of(payload):
    return last_result(payload)["passages"][0]["passage"]


def test_a_bad_page_and_a_wrong_count_are_corrected_once_and_reopen_as_delivered(api, runtime):
    client, holder = api
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    grant = issue.reader_session_grant(make_user("agent-repair@cit.edu")).token
    drafts = {}

    def bad(payload):
        drafts["handle"] = passage_of(payload)
        return reply(f"On page 9 rainfall gauges forecast 912 floods [{drafts['handle']}].")

    def corrected(payload):
        note = payload["messages"][-1]["content"]
        assert "912" in note and not any(code in note for code in VALIDATION_CODES)
        assert payload["tool_choice"] == "none"
        return reply(f"On page 4 rainfall gauges and river levels forecast floods [{drafts['handle']}].")

    provider = recording(tools(call("s", "search", query="floods")), bad, corrected)
    holder["service"] = agent_service(runtime, provider)
    live = submit(client, grant, "agent-repair", "How were floods forecast?").json()
    assert live["state"] == "completed", live
    assert [m["phase"] for m in models(live)] == ["gather", "gather", "repair"]

    reopened = client.get(f"/api/v1/ai/conversations/{live['conversation_id']}", headers=as_reader(grant))
    [turn] = reopened.json()["turns"]
    assert turn["answer"] == "On page 4 rainfall gauges and river levels forecast floods [1]."
    [citation] = turn["citations"]
    assert (citation["record_id"], citation["page"]) == (flood.pk, 4)
    status = client.get(f"/api/v1/ai/runs/{live['id']}", headers=as_reader(grant))
    # The refused draft and the validation codes are in neither the run nor the history.
    # "912 floods", not "912": bare digits can occur inside a random run id or timestamp.
    for body in (json.dumps(live), reopened.text, status.text):
        assert "912 floods" not in body and "page 9" not in body
        assert not any(code in body for code in VALIDATION_CODES)


def test_a_source_replaced_during_the_repair_fences_delivery(api, runtime):
    client, holder = api
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    grant = issue.reader_session_grant(make_user("agent-repair-revoked@cit.edu")).token
    drafts = {}

    def bad(payload):
        drafts["handle"] = passage_of(payload)
        return reply(f"Rainfall gauges forecast 912 floods [{drafts['handle']}].")

    def replace_then_correct(payload):
        # The paper's source changes while the repair is being written; Django owns that write.
        worker = threading.Thread(target=write_source, args=(flood, {4: [("Methods", "revised")]}, "2"))
        worker.start()
        worker.join()
        return reply(f"Rainfall gauges forecast floods [{drafts['handle']}].")

    holder["service"] = agent_service(runtime, recording(
        tools(call("s", "search", query="floods")), bad, replace_then_correct))
    run_ = submit(client, grant, "agent-repair-revoked", "How were floods forecast?").json()
    assert (run_["state"], run_["end_reason"]) == ("failed", "unavailable")
    reopened = client.get(f"/api/v1/ai/conversations/{run_['conversation_id']}", headers=as_reader(grant)).json()
    assert reopened["turns"] == []


def test_every_admitted_attempt_records_the_agent_purpose_and_no_other_writer(runtime):
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    admission = limits()
    provider = RecordingAgentProvider(responses=[tools(call("s", "search", query="water")), reply("Never sent.")],
                                      capacities={"scripted-model": MILLION})
    transport = AdmittedAgentProvider(provider, Ledger(runtime, admission), purpose="agent")
    built = agent_service(runtime, transport, reserves=ADMITTED_RESERVES,
                          price=admission.prices["scripted-model"])
    grant = issue.reader_session_grant(make_user("agent-admitted@cit.edu")).token
    queued, _ = run(built.submit(grant, key="agent-admitted", question="Which papers study water?",
                                 conversation_id=None, base_revision=None))
    status = run(RunStore(runtime).status(grant, queued["id"]))

    # The guard withholds Record evidence from a paid provider (IR-725). Since IR-995 the
    # withheld search reaches the model as a bare status and the run answers without it.
    assert (status["state"], status["end_reason"]) == ("completed", "answered")
    assert len(provider.requests) == 2
    shown = json.dumps(provider.requests[1]["messages"])
    assert FLOOD not in shown and '\\"reason\\": \\"withheld\\"' in shown
    reservations = list(ProviderReservation.objects.order_by("id"))
    assert [(r.owner, r.purpose, r.purpose_version) for r in reservations] == [
        ("ai", "agent", "agent-research-1")] * len(reservations)
    assert [r.sent for r in reservations] == [True, True]


def test_approved_proxy_can_be_searched_read_and_answered_by_admitted_agent(runtime):
    proxy = paper("Public proxy", {4: [("Methods", "Water levels forecast floods.")]})
    Record.objects.filter(pk=proxy.pk).update(
        origin=Record.Origin.IMPORTED_REFERENCE, is_embargoed=False,
        embargo_released_at=timezone.now())
    chunk_set = ChunkSet.objects.get(record=proxy, is_active=True)
    source = Source(proxy.pk, chunk_set.pk, chunk_set.extraction_hash)

    def open_hit(payload):
        passage = last_result(payload)["passages"][0]
        return tools(call("o", "open_passage", passage=passage["passage"]))

    def cite(payload):
        passage = last_result(payload)["passages"][0]
        return reply(f"«Public proxy» reports that water levels forecast floods [{passage['passage']}].")

    provider = recording(tools(call("s", "search", query="water")), open_hit, cite)
    admission = limits()
    approval = ProxyApproval("IR-889", PIN.model, PIN.endpoint, provider.account,
                             admission.campaign_key, timezone.now() + timedelta(hours=1),
                             frozenset({source}))
    transport = AdmittedAgentProvider(provider, Ledger(runtime, admission),
                                      guard=SendGuard(runtime, approval, stage="development"),
                                      purpose="agent")
    built = agent_service(runtime, transport, run_limits=replace(LIMITS, max_attempts=3),
                          reserves=ADMITTED_RESERVES, price=admission.prices["scripted-model"])
    grant = issue.reader_session_grant(make_user("agent-proxy@cit.edu")).token
    queued, _ = run(built.submit(grant, key="agent-proxy-allowed",
                                 question="What do public papers say about water?",
                                 conversation_id=None, base_revision=None))
    status = run(RunStore(runtime).status(grant, queued["id"]))
    assert status["state"] == "completed", status
    assert len(provider.requests) == 3
    assert all(reservation.sent for reservation in ProviderReservation.objects.all())
    reopened = run(RunStore(runtime).reopen(grant, status["conversation_id"]))
    assert [citation["record_id"] for citation in reopened["turns"][0]["citations"]] == [proxy.pk]
