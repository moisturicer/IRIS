"""The OpenAI-compatible AGENT adapter through admission, on real PostgreSQL (IR-860).

IR-860's demonstration: recorded vendor responses -- a direct answer, a
parallel tool group and a truncated completion -- replayed through
`AdmittedAgentProvider` with the real ledger and guard, then one admission
limit unset and the next attempt refused with no outbound request.
"""

import json
from types import SimpleNamespace

import httpx
import pytest

from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_admission_db import ADMISSION, RESERVES, claimed, limits, run
from .test_ai_runtime_openai_agent_contract import MODEL, PIN, Vendor, adapter, ask, call, reply
from .test_ai_runtime_runs_db import service, session
from .corpus import make_user  # noqa: E402
from ai.admission.ledger import Ledger  # noqa: E402
from ai.admission.report import run_report  # noqa: E402
from ai.admission.scope import bound  # noqa: E402
from ai.admission.transport import AdmittedAgentProvider  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.protocol import Pin, StopReason, ToolCall, ToolGroup  # noqa: E402
from ai.domain.ports import TransientProviderError  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from apps.ai.models.admission import ProviderReservation

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime

# Test prices for the fixture model only; no vendor's price is implied.
PRICED = dict(AI_ADMISSION_PRICES=json.dumps({MODEL: {"input": 1.0, "output": 2.0}}))
DIRECT = Pin(**{**PIN.as_dict(), "requires": PIN.requires,
                "prompt_version": "agent-direct-1", "tool_version": "none-1"})


def transport(dsn, vendor, *, retries=0, **overrides):
    return AdmittedAgentProvider(adapter(vendor), Ledger(dsn, limits(**{**PRICED, **overrides})),
                                 retries=retries)


def attempt(dsn, admitted, email, key, request):
    """One `converse` as a worker holding a claimed run makes it."""
    binding = claimed(dsn, email, key)

    async def send():
        with bound(binding):
            return await admitted.converse(request)

    return binding, run(send())


def test_a_direct_answer_completes_a_run_and_settles_to_reported_usage(runtime):
    vendor = Vendor(reply("IRIS is a repository."))
    built = service(runtime, AgentExecutor(transport(runtime, vendor), DIRECT, RESERVES))
    grant = session(make_user("ir860-direct@cit.edu"))
    run_, _ = run(built.submit(grant, key="ir860-direct-01", question="What is IRIS?",
                               conversation_id=None, base_revision=None))
    status = run(RunStore(runtime).status(grant, run_["id"]))

    assert status["state"] == "completed"
    [reservation] = ProviderReservation.objects.all()
    assert (reservation.state, reservation.sent, reservation.usage_reported) == ("settled", True, True)
    assert (reservation.charge_input_tokens, reservation.charge_output_tokens) == (21, 7)
    # 21 x US$1/M + 7 x US$2/M = 35 micro-dollars.
    assert reservation.charge_cost_micros == 35
    assert reservation.model == MODEL
    # The cap reserved is the cap the vendor was sent.
    assert vendor.bodies[0]["max_tokens"] == 100 == reservation.reserved_output_tokens


def test_a_parallel_tool_group_comes_back_whole_through_admission(runtime):
    vendor = Vendor(reply(finish="tool_calls", tool_calls=[call("c-2", "search"), call("c-1", "outline")]))
    binding, turn = attempt(runtime, transport(runtime, vendor), "ir860-tools@cit.edu", "ir860-tools-01",
                            ask(max_output_tokens=100))

    assert turn.stop is StopReason.TOOLS
    assert turn.items == (ToolGroup((ToolCall("c-2", "search"), ToolCall("c-1", "outline"))),)
    [settled] = run(run_report(runtime, binding.run_id))["attempts"]
    assert (settled["state"], settled["usage_reported"]) == ("settled", True)


def test_a_truncated_completion_is_settled_and_reported_as_length(runtime):
    vendor = Vendor(reply("Half an ans", finish="length"))
    binding, turn = attempt(runtime, transport(runtime, vendor), "ir860-length@cit.edu", "ir860-length-1",
                            ask(max_output_tokens=100))

    assert turn.stop is StopReason.LENGTH
    [settled] = run(run_report(runtime, binding.run_id))["attempts"]
    assert settled["state"] == "settled"


def test_a_transient_failure_is_a_settled_attempt_and_the_retry_is_another(runtime):
    vendor = Vendor(httpx.Response(503, text="down"), reply("Second time."))
    binding, turn = attempt(runtime, transport(runtime, vendor, retries=1), "ir860-retry@cit.edu",
                            "ir860-retry-001", ask(max_output_tokens=100))

    assert turn.text == "Second time."
    failed, answered = run(run_report(runtime, binding.run_id))["attempts"]
    # The failed send reported nothing, so it stays charged at its reservation.
    assert (failed["state"], failed["sent"], failed["usage_reported"]) == ("settled", True, False)
    assert failed["charge_cost_micros"] == failed["reserved_cost_micros"] > 0
    assert (answered["charge_input_tokens"], answered["charge_output_tokens"]) == (21, 7)
    assert len(vendor.requests) == 2


def test_without_retries_a_transient_failure_ends_the_attempt(runtime):
    vendor = Vendor(httpx.Response(503, text="down"))
    with pytest.raises(TransientProviderError):
        attempt(runtime, transport(runtime, vendor), "ir860-once@cit.edu", "ir860-once-001",
                ask(max_output_tokens=100))
    assert len(vendor.requests) == 1


@pytest.mark.parametrize("n, unset", list(enumerate(["AI_ADMISSION_PRICES", "AI_ADMISSION_CAMPAIGN_MAX_COST_USD"])))
def test_with_one_admission_limit_unset_the_next_attempt_sends_nothing(runtime, n, unset):
    from ai.admission.errors import AdmissionDenied

    vendor = Vendor(reply("Never sent."))
    values = SimpleNamespace(**{**ADMISSION, **PRICED, unset: ""})
    admitted = AdmittedAgentProvider(adapter(vendor), Ledger.from_settings(runtime, values))
    with pytest.raises(AdmissionDenied) as refused:
        attempt(runtime, admitted, f"ir860-unset-{n}@cit.edu", f"ir860-unset-0{n}",
                ask(max_output_tokens=100))
    assert refused.value.reason == "not_configured"
    assert vendor.requests == []
    assert not ProviderReservation.objects.exists()


def test_an_unpriced_configured_model_is_refused_unsent(runtime):
    from ai.admission.errors import AdmissionDenied

    vendor = Vendor(reply("Never sent."))
    admitted = transport(runtime, vendor, AI_ADMISSION_PRICES=json.dumps({"other": {"input": 1, "output": 1}}))
    with pytest.raises(AdmissionDenied) as refused:
        attempt(runtime, admitted, "ir860-unpriced@cit.edu", "ir860-unpriced", ask(max_output_tokens=100))
    assert refused.value.reason == "unpriced_model"
    assert vendor.requests == []
