"""Reservations against real Postgres, through the `admission` alias (IR-545).

Transactional: a reservation commits on its own connection, which is the
property under test, so these tests cannot run inside a rolled-back one.
"""

import time

import pytest
from django.db import OperationalError
from django.db.models import Sum

from apps.ai.admission import errors, ledger, scope
from apps.ai.admission.llm import AdmittedLLMProvider
from apps.ai.models import ProviderCampaign, ProviderReservation
from apps.ai.models.admission import ABANDONED, OPEN, RELEASED, SETTLED
from apps.ai.providers.deadline import model_call_deadline
from apps.ai.providers.tool_calling import SystemMessage, ToolDefinition, UserMessage
from apps.ai.resilience.llm import FallbackLLMProvider, RetryingLLMProvider

from .support import MeteredAdapter, enforce, network_failure

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]


@pytest.fixture(autouse=True)
def enforced(settings):
    enforce(settings)
    return settings


def _campaign():
    return ProviderCampaign.objects.using("admission").get(key="test-campaign")


def _reservations(**filters):
    return ProviderReservation.objects.using("admission").filter(**filters)


def _assert_totals_match_rows():
    """The campaign row is the sum of its reservations' charges."""
    campaign = _campaign()
    sums = _reservations(campaign=campaign).aggregate(
        a=Sum("charge_attempts"), i=Sum("charge_input_tokens"), o=Sum("charge_output_tokens"),
        c=Sum("charge_cost_micros"), m=Sum("charge_active_ms"),
    )
    assert (
        campaign.charged_attempts, campaign.charged_input_tokens, campaign.charged_output_tokens,
        campaign.charged_cost_micros, campaign.charged_active_ms,
    ) == (sums["a"] or 0, sums["i"] or 0, sums["o"] or 0, sums["c"] or 0, sums["m"] or 0)


def _request(**overrides):
    fields = dict(
        operation="llm", default_lane="chat", account="acct-a", models=("cheap",),
        input_tokens=100, output_tokens=50, timeout_seconds=10.0,
    )
    fields.update(overrides)
    return ledger.Request(**fields)


# -- reserve, then settle -----------------------------------------------------


def test_an_attempt_is_reserved_at_its_worst_case_then_settled_to_reported_usage():
    provider = AdmittedLLMProvider(MeteredAdapter(usage=(120, 30)))
    assert provider.generate("system", "question") == "Rainfall gauges feed the model [1]."

    (row,) = _reservations()
    # Bytes plus overhead bound the input; the cap bounds the output.
    assert row.reserved_input_tokens == len("system") + len("question") + 16
    assert row.reserved_output_tokens == 500
    assert row.reserved_cost_micros == row.reserved_input_tokens * 1 + 500 * 2
    assert row.reserved_active_ms == 15_000, "timeout 10 s plus 5 s grace"
    assert (row.state, row.sent, row.usage_reported) == (SETTLED, True, True)
    assert (row.charge_input_tokens, row.charge_output_tokens, row.charge_cost_micros) == (120, 30, 180)
    assert row.lane == "chat" and row.operation == "llm" and row.run_key == ""
    _assert_totals_match_rows()


def test_unknown_usage_is_charged_at_its_reservation_never_zero():
    provider = AdmittedLLMProvider(MeteredAdapter(usage=None))
    provider.generate("system", "question")
    (row,) = _reservations()
    assert row.usage_reported is False
    assert row.charge_input_tokens == row.reserved_input_tokens
    assert row.charge_output_tokens == row.reserved_output_tokens
    assert row.charge_cost_micros == row.reserved_cost_micros
    _assert_totals_match_rows()


def test_an_attempt_that_never_sent_is_released_and_costs_nothing():
    provider = AdmittedLLMProvider(MeteredAdapter(fail_before_send=network_failure()))
    with pytest.raises(Exception):
        provider.generate("system", "question")
    (row,) = _reservations()
    assert row.state == RELEASED and row.charge_attempts == 0 and row.charge_cost_micros == 0
    _assert_totals_match_rows()


def test_a_failure_after_sending_keeps_the_reserved_charge():
    provider = AdmittedLLMProvider(MeteredAdapter(fail_after_send=network_failure()))
    with pytest.raises(Exception):
        provider.generate("system", "question")
    (row,) = _reservations()
    assert row.state == SETTLED and row.charge_attempts == 1
    assert row.charge_cost_micros == row.reserved_cost_micros, "billing unknown, so worst case"


def test_a_fallback_list_is_reserved_at_its_dearest_model():
    provider = AdmittedLLMProvider(MeteredAdapter(model="cheap", fallback_models=("dear",), usage=None))
    provider.generate("s", "q")
    (row,) = _reservations()
    # The vendor may answer with either; "dear" is 3/15 against "cheap"'s 1/2.
    assert row.reserved_cost_micros == row.reserved_input_tokens * 3 + 500 * 15


def test_a_retry_and_each_fallback_model_are_attempts_of_their_own(settings):
    flaky = MeteredAdapter(model="cheap", fail_after_send=network_failure())
    second = MeteredAdapter(model="dear", fail_after_send=network_failure())
    chain = FallbackLLMProvider([
        RetryingLLMProvider(AdmittedLLMProvider(flaky), sleep=lambda _: None),
        RetryingLLMProvider(AdmittedLLMProvider(second), sleep=lambda _: None),
    ])
    with pytest.raises(Exception):
        chain.generate("s", "q")
    assert flaky.sent == 2 and second.sent == 2
    assert _reservations(state=SETTLED).count() == 4
    assert _campaign().charged_attempts == 4


def test_tool_calls_are_admitted_like_completions():
    provider = AdmittedLLMProvider(MeteredAdapter())
    provider.converse_with_tools(
        [SystemMessage("s"), UserMessage("q")], [ToolDefinition("search_corpus", "Search.")]
    )
    (row,) = _reservations()
    assert row.state == SETTLED and row.reserved_input_tokens > len("sq")


# -- refusals -----------------------------------------------------------------


@pytest.mark.parametrize("override, reason", [
    ({"AI_ADMISSION_PRICES": '{"dear": {"input": 3, "output": 15}}'}, errors.UNPRICED_MODEL),
    ({"AI_ADMISSION_LANE_CONCURRENCY": '{"research": 3}'}, errors.LANE_NOT_CONFIGURED),
    ({"AI_ADMISSION_CAMPAIGN_MAX_COST_USD": ""}, errors.NOT_CONFIGURED),
])
def test_a_refusal_sends_nothing(settings, override, reason):
    enforce(settings, **override)
    adapter = MeteredAdapter()
    with pytest.raises(errors.AdmissionDenied) as refused:
        AdmittedLLMProvider(adapter).generate("s", "q")
    assert refused.value.reason == reason
    assert adapter.sent == 0
    assert not _reservations().exists()


def test_an_uncapped_completion_is_refused():
    adapter = MeteredAdapter(max_tokens=None)
    with pytest.raises(errors.AdmissionDenied) as refused:
        AdmittedLLMProvider(adapter).generate("s", "q")
    assert refused.value.reason == errors.UNBOUNDED_OUTPUT and adapter.sent == 0


def test_a_denial_is_neither_retried_nor_failed_over_nor_counted_against_a_circuit(settings):
    enforce(settings, AI_ADMISSION_PRICES='{"other": {"input": 1, "output": 1}}')
    first, second = MeteredAdapter(model="cheap"), MeteredAdapter(model="dear")
    chain = FallbackLLMProvider([
        RetryingLLMProvider(AdmittedLLMProvider(first), sleep=lambda _: None),
        RetryingLLMProvider(AdmittedLLMProvider(second), sleep=lambda _: None),
    ])
    with pytest.raises(errors.AdmissionDenied):
        chain.generate("s", "q")
    assert first.sent == second.sent == 0
    assert errors.AdmissionDenied("x").counts_against_circuit is False


def test_lane_concurrency_counts_attempts_in_flight(settings):
    enforce(settings, AI_ADMISSION_LANE_CONCURRENCY='{"research": 2, "chat": 8}')
    with scope.workload("research"):
        held = [ledger.admit(_request()), ledger.admit(_request())]
        with pytest.raises(errors.AdmissionDenied) as refused:
            ledger.admit(_request())
        assert refused.value.reason == errors.LANE_BUSY
        # Another lane is unaffected.
    ledger.admit(_request())
    held[0].settle(scope.AttemptUsage(sent=True, input_tokens=1, output_tokens=1))
    with scope.workload("research"):
        ledger.admit(_request())


def test_one_account_cannot_bypass_its_limit_through_another_lane(settings):
    enforce(settings, AI_ADMISSION_ACCOUNT_CONCURRENCY="2")
    with scope.workload("research"):
        ledger.admit(_request(account="shared"))
    with scope.workload("ingestion"):
        ledger.admit(_request(account="shared"))
    with pytest.raises(errors.AdmissionDenied) as refused:
        ledger.admit(_request(account="shared"))
    assert refused.value.reason == errors.ACCOUNT_BUSY
    ledger.admit(_request(account="another"))


def test_the_protected_reserve_holds_until_released(settings):
    enforce(settings, AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS="4", AI_ADMISSION_RUN_MAX_ATTEMPTS="100")
    for _ in range(3):  # 75% of 4
        ledger.admit(_request()).settle(scope.AttemptUsage(sent=True, input_tokens=1, output_tokens=1))
    with pytest.raises(errors.AdmissionDenied) as refused:
        ledger.admit(_request())
    assert refused.value.reason == errors.CAMPAIGN_EXHAUSTED

    settings.AI_ADMISSION_RESERVE_RELEASED = True
    ledger.admit(_request())
    with pytest.raises(errors.AdmissionDenied):
        ledger.admit(_request())


def test_a_run_stops_at_its_cap_and_asks_no_more(settings):
    enforce(settings, AI_ADMISSION_RUN_MAX_ATTEMPTS="2")
    with scope.run(scope.new_run("ask:one")) as run:
        for _ in range(2):
            ledger.admit(_request()).settle(scope.AttemptUsage(sent=True, input_tokens=1, output_tokens=1))
        with pytest.raises(errors.AdmissionDenied) as refused:
            ledger.admit(_request())
        assert refused.value.reason == errors.RUN_BUDGET_EXHAUSTED
        rows = _reservations().count()
        with pytest.raises(errors.AdmissionDenied):
            ledger.admit(_request())
        assert _reservations().count() == rows, "a sticky denial is not asked again"
        assert run.denials == [errors.RUN_BUDGET_EXHAUSTED]
    with scope.run(scope.new_run("ask:two")):
        ledger.admit(_request())


def test_a_store_failure_refuses_new_paid_work(monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("the database went away")

    monkeypatch.setattr(ledger, "_reserve", broken)
    adapter = MeteredAdapter()
    with pytest.raises(errors.AdmissionDenied) as refused:
        AdmittedLLMProvider(adapter).generate("s", "q")
    assert refused.value.reason == errors.STORE_UNAVAILABLE and adapter.sent == 0


def test_a_store_failure_while_settling_leaves_the_reservation_charged(monkeypatch):
    monkeypatch.setattr(ledger.Ticket, "_settle", lambda self, usage: (_ for _ in ()).throw(
        OperationalError("gone")
    ))
    AdmittedLLMProvider(MeteredAdapter()).generate("s", "q")
    (row,) = _reservations()
    assert row.state == OPEN and row.charge_cost_micros == row.reserved_cost_micros


# -- deadlines, leases, streams ------------------------------------------------


def test_the_lease_never_outlasts_the_run_deadline_less_grace():
    adapter = MeteredAdapter(timeout=30.0)
    with model_call_deadline(4.0):
        AdmittedLLMProvider(adapter).generate("s", "q")
    assert adapter.timeouts and adapter.timeouts[0] <= 4.0
    (row,) = _reservations()
    assert row.reserved_active_ms <= 9_000, "4 s left plus 5 s grace, not 30 s"


def test_a_closed_stream_is_settled_and_frees_its_slot(settings):
    enforce(settings, AI_ADMISSION_LANE_CONCURRENCY='{"chat": 1}')
    stream = AdmittedLLMProvider(MeteredAdapter(deltas=("a", "b", "c"))).stream("s", "q")
    assert next(stream).text == "a"
    assert _reservations(state=OPEN).count() == 1
    stream.close()  # the reader left
    (row,) = _reservations()
    assert row.state == SETTLED and row.usage_reported is False
    assert row.charge_cost_micros == row.reserved_cost_micros, "in-flight billing unknown"
    AdmittedLLMProvider(MeteredAdapter()).generate("s", "q")


def test_a_finished_stream_settles_to_the_usage_it_reported():
    stream = AdmittedLLMProvider(MeteredAdapter(stream_usage=(40, 9))).stream("s", "q")
    assert "".join(delta.text for delta in stream) == "Rainfall gauges feed the model [1]."
    (row,) = _reservations()
    assert (row.charge_input_tokens, row.charge_output_tokens, row.usage_reported) == (40, 9, True)


def test_a_long_stream_renews_its_lease():
    clock = iter(range(0, 1000, 10)).__next__
    provider = AdmittedLLMProvider(MeteredAdapter(deltas=("a", "b", "c")), clock=clock)
    list(provider.stream("s", "q"))
    (row,) = _reservations()
    assert row.reserved_active_ms > 15_000, "each renewal extends the reserved time"
    _assert_totals_match_rows()


def test_a_dead_workers_lease_ends_frees_its_slot_and_keeps_its_charge(settings):
    enforce(settings, AI_ADMISSION_LANE_CONCURRENCY='{"chat": 1}', AI_ADMISSION_LEASE_GRACE_SECONDS="0")
    orphan = ledger.admit(_request(timeout_seconds=0.3))  # never settled: the worker died
    with pytest.raises(errors.AdmissionDenied) as refused:
        ledger.admit(_request())
    assert refused.value.reason == errors.LANE_BUSY, "the lease still covers the remote call"

    time.sleep(0.4)
    ledger.admit(_request())
    row = _reservations().get(pk=orphan.pk)
    assert row.state == ABANDONED and row.charge_cost_micros == row.reserved_cost_micros
    with pytest.raises(errors.AdmissionLost):
        orphan.renew()
    _assert_totals_match_rows()


def test_the_campaign_command_reports_spend_against_both_ceilings():
    from io import StringIO

    from django.core.management import call_command

    held = ledger.admit(_request())
    out = StringIO()
    call_command("provider_campaign", stdout=out)
    text = out.getvalue()
    assert "campaign test-campaign" in text and "protected reserve 25%, held" in text
    assert "attempts" in text and "360.00" in text and "480.00" in text
    assert "in flight: chat 1/8" in text
    held.settle(scope.AttemptUsage(sent=False))


def test_a_refusal_tied_to_one_model_does_not_stop_the_rest_of_the_run(settings):
    # Review finding: an unpriced rerank must not block the answer after it.
    with scope.run(scope.new_run("ask:mixed")) as run:
        with pytest.raises(errors.AdmissionDenied):
            ledger.admit(_request(models=("rerank-unpriced",)))
        ledger.admit(_request())
    assert run.denials == [errors.UNPRICED_MODEL]


def test_with_admission_off_the_request_is_never_built(settings):
    settings.AI_PROVIDER_ADMISSION = "off"

    def describe():
        raise AssertionError("built with admission off")

    with ledger.provider_attempt(describe) as ticket:
        assert ticket is None


def test_one_key_through_two_endpoints_is_one_account():
    from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

    chat = OpenAICompatibleAdapter(base_url="https://openrouter.ai/api/v1/", api_key="k1", model="m")
    assert chat.account == ledger.account_for("k1") == ledger.account_for(" k1 ")
    assert ledger.account_for("k2") != chat.account
