"""Shared paid answer allowance, with real admission rows and fake transports."""

from dataclasses import replace

import pytest

from apps.ai.admission import errors, ledger, scope
from apps.ai.admission.limits import Ceiling
from apps.ai.admission.llm import AdmittedLLMProvider
from apps.ai.models import ProviderReservation
from apps.ai.resilience.llm import FallbackLLMProvider, RetryingLLMProvider

from .support import MeteredAdapter, enforce, network_failure

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]


@pytest.fixture(autouse=True)
def enforced(settings):
    enforce(settings)


def _request(*, answer=False):
    return ledger.Request(
        operation="llm", default_lane="research", account="acct-a",
        models=("dear",) if answer else ("cheap",),
        input_tokens=100 if answer else 50, output_tokens=500 if answer else 10,
        timeout_seconds=1,
    )


def _charge(request):
    ticket = ledger.admit(request)
    # Missing vendor usage conservatively retains every reserved unit.
    ticket.settle(scope.AttemptUsage(sent=True))


@pytest.mark.parametrize("dimension,bound", [
    ("attempts", 3), ("input_tokens", 250), ("output_tokens", 1010),
    ("cost_micros", 15670),
])
def test_research_leaves_answer_and_repair_in_every_shared_dimension(dimension, bound):
    ceiling = replace(Ceiling(100, 100000, 100000, 10000000), **{dimension: bound})
    run = scope.RunScope("ask:answer-reserve", ceiling=ceiling)
    with scope.run(run):
        with scope.answer_allowance(tokens=200, attempts=2):
            _charge(_request())
            with pytest.raises(errors.AdmissionDenied) as denied:
                _charge(_request())
            assert denied.value.reason == errors.ANSWER_RESERVED
        # The denial is deliberately nonsticky; the expensive answer and repair
        # can each use the physical completion cap when research is over.
        _charge(_request(answer=True))
        _charge(_request(answer=True))
    rows = ProviderReservation.objects.using("admission")
    assert rows.count() == 3
    assert all(not row.usage_reported for row in rows)
    assert sum(row.charge_input_tokens for row in rows) == 250
    assert sum(row.charge_output_tokens for row in rows) == 1010
    assert sum(row.charge_cost_micros for row in rows) == 15670


def test_redelivery_retains_shared_charges_and_does_not_recreate_allowance():
    ceiling = Ceiling(3, 100000, 100000, 10000000)
    with scope.run(scope.RunScope("ask:redelivery", ceiling=ceiling)):
        _charge(_request())
    with scope.run(scope.RunScope("ask:redelivery", ceiling=ceiling)):
        with scope.answer_allowance(tokens=200, attempts=2):
            with pytest.raises(errors.AdmissionDenied) as denied:
                _charge(_request())
            assert denied.value.reason == errors.ANSWER_RESERVED
        _charge(_request(answer=True))
        _charge(_request(answer=True))
    assert ProviderReservation.objects.using("admission").count() == 3


def test_actual_exhaustion_remains_sticky_after_reserve_context_ends():
    with scope.run(scope.RunScope("ask:spent", ceiling=Ceiling(1, 100000, 100000, 10000000))):
        _charge(_request())
        with scope.answer_allowance(tokens=200, attempts=2):
            with pytest.raises(errors.AdmissionDenied) as denied:
                _charge(_request())
            assert denied.value.reason == errors.RUN_BUDGET_EXHAUSTED
        with pytest.raises(errors.AdmissionDenied) as denied:
            _charge(_request(answer=True))
        assert denied.value.reason == errors.RUN_BUDGET_EXHAUSTED


def test_each_retry_and_fallback_spends_research_capacity_before_answer_reserve():
    first = MeteredAdapter(fail_after_send=network_failure())
    second = MeteredAdapter(model="dear", fail_after_send=network_failure())
    chain = FallbackLLMProvider([
        RetryingLLMProvider(AdmittedLLMProvider(first), sleep=lambda _: None),
        RetryingLLMProvider(AdmittedLLMProvider(second), sleep=lambda _: None),
    ])
    with scope.run(scope.RunScope("ask:fallback", ceiling=Ceiling(5, 100000, 100000, 10000000))):
        with scope.answer_allowance(tokens=200, attempts=2):
            with pytest.raises(errors.AdmissionDenied) as denied:
                chain.generate("s", "q")
            assert denied.value.reason == errors.ANSWER_RESERVED
        _charge(_request(answer=True))
        _charge(_request(answer=True))
    assert first.sent == 2 and second.sent == 1
    assert ProviderReservation.objects.using("admission").count() == 5


def test_unrelated_runs_do_not_spend_each_others_run_allowance():
    ceiling = Ceiling(3, 100000, 100000, 10000000)
    with scope.run(scope.RunScope("ask:other", ceiling=ceiling)):
        _charge(_request())
    with scope.run(scope.RunScope("ask:new", ceiling=ceiling)):
        with scope.answer_allowance(tokens=200, attempts=2):
            _charge(_request())
    assert ProviderReservation.objects.using("admission").count() == 2


def test_run_stopped_after_admission_is_rechecked_before_send_and_released():
    stopped = False
    run = scope.RunScope("ask:stop-before-send", halted=lambda: stopped)
    with scope.run(run):
        with pytest.raises(errors.AdmissionDenied) as denied:
            with ledger.provider_attempt(_request):
                stopped = True
                scope.mark_sent()
        assert denied.value.reason == errors.RUN_CANCELLED
    (row,) = ProviderReservation.objects.using("admission")
    assert row.state == "released"
    assert not row.sent
    assert row.charge_attempts == row.charge_input_tokens == row.charge_output_tokens == 0
    assert row.charge_cost_micros == 0
