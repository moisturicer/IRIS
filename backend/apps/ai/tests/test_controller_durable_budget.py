"""Worker redelivery retains declared bounds and pre-work spend (IR-597)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ai import durable
from apps.ai.controller.budget import ControllerBudget
from apps.ai.controller.durable_budget import bind, declare, pinned, prepare_request, restore
from apps.ai.models import AskRun, Conversation
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.research.budget import BudgetExhausted, Spend

from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture
def run(budget):
    reader = make_user("budget-redelivery@cit.edu")
    conversation = Conversation.objects.create(user=reader)
    return AskRun.objects.create(user=reader, conversation=conversation,
                                 deadline_at=timezone.now() + timedelta(seconds=120),
                                 request={"controller_budget": declare()})


def spend_for(attempt, *, protected=0):
    with bind(attempt):
        bounds = pinned("controller", ControllerBudget.from_settings, ControllerBudget)
        return restore(Spend(bounds.run_budget()), protected_tokens=protected)


@pytest.mark.parametrize("counter,limit,charge", [
    ("rounds", "max_outer_rounds", lambda spend: spend.begin_round()),
    ("tool_calls", "max_tool_calls", lambda spend: spend.charge_call(subtask=False)),
    ("prompt_tokens", "max_prompt_tokens", lambda spend: spend.charge_prompt_tokens(100)),
])
def test_redelivery_does_not_refund_prework_charges(run, counter, limit, charge):
    state = run.request["controller_budget"]
    state["controller"]["max_rounds"] = 1
    state["controller"]["max_tool_calls"] = 1
    state["research"]["max_prompt_tokens"] = 100
    run.save(update_fields=["request"])
    first = durable.claim(run.pk)
    charge(spend_for(first))
    # A crash after the charge but before any remote work is conservative.
    second = durable.claim(run.pk)
    resumed = spend_for(second)
    with pytest.raises(BudgetExhausted, match=limit):
        charge(resumed)
    run.refresh_from_db()
    assert run.request["controller_budget"]["spent"][counter] >= 1


def test_redelivery_uses_submitted_bounds_even_when_settings_are_unset(run, settings):
    original = run.request["controller_budget"]
    settings.AI_CONTROLLER_MAX_ROUNDS = None
    settings.AI_RESEARCH_MAX_PROMPT_TOKENS = 1
    spend = spend_for(durable.claim(run.pk))
    assert spend._budget.max_outer_rounds == original["controller"]["max_rounds"]
    assert spend._budget.max_prompt_tokens == original["research"]["max_prompt_tokens"]


def test_superseded_attempt_cannot_change_budget_or_call_provider(run):
    first = durable.claim(run.pk)
    spend = spend_for(first)
    durable.claim(run.pk)
    provider = ScriptedLLM(reply="never sent")
    with pytest.raises(durable.StaleAttempt):
        spend.charge_prompt_tokens(10)
        provider.generate(system="system", user="question")
    assert provider.calls == []
    run.refresh_from_db()
    assert "spent" not in run.request["controller_budget"]


def test_research_cannot_spend_answer_allowance_but_answer_can(run):
    run.request["controller_budget"]["research"]["max_prompt_tokens"] = 100
    run.save(update_fields=["request"])
    first = durable.claim(run.pk)
    spend = spend_for(first, protected=40)
    spend.charge_prompt_tokens(60)
    provider = ScriptedLLM(reply="never sent")
    with pytest.raises(BudgetExhausted, match="answer_reserve"):
        spend.charge_prompt_tokens(1)
        provider.generate(system="system", user="question")
    assert provider.calls == []
    second = durable.claim(run.pk)
    resumed = spend_for(second, protected=40)
    assert resumed.prompt_tokens == 60
    resumed.charge_prompt_tokens(40, answer=True)
    run.refresh_from_db()
    assert run.request["controller_budget"]["spent"]["prompt_tokens"] == 100


def test_original_deadline_fences_budget_writes(run):
    spend = spend_for(durable.claim(run.pk))
    AskRun.objects.filter(pk=run.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(durable.StaleAttempt):
        spend.begin_round()
    run.refresh_from_db()
    assert "spent" not in run.request["controller_budget"]


def test_explicit_retry_retains_declared_bounds_but_gets_fresh_spend(run, settings):
    from apps.ai.controller.versions import CONTROLLER_ENGINE, pin

    run.request["pin"] = pin(CONTROLLER_ENGINE)
    run.save(update_fields=["request"])
    spend_for(durable.claim(run.pk)).begin_round()
    run.refresh_from_db()
    settings.AI_CONTROLLER_MAX_ROUNDS = None
    copied = prepare_request(run.request, retry=True)
    assert copied["controller_budget"]["controller"] == run.request["controller_budget"]["controller"]
    assert "spent" not in copied["controller_budget"]
    assert run.request["controller_budget"]["spent"]["rounds"] == 1


def test_redelivery_keeps_research_wall_clock_from_original_submission(run):
    run.request["controller_budget"]["research"]["wall_clock_seconds"] = 1
    run.save(update_fields=["request"])
    AskRun.objects.filter(pk=run.pk).update(created_at=timezone.now() - timedelta(seconds=2))
    spend = spend_for(durable.claim(run.pk))
    with pytest.raises(BudgetExhausted, match="wall_clock_seconds"):
        spend.begin_round()


def test_durable_prompt_charges_cannot_refund_a_reservation(run):
    spend = spend_for(durable.claim(run.pk))
    spend.charge_prompt_tokens(10)
    with pytest.raises(ValueError, match="nonnegative"):
        spend.charge_prompt_tokens(-1)
    run.refresh_from_db()
    assert run.request["controller_budget"]["spent"]["prompt_tokens"] == 10


@pytest.mark.parametrize("name,value", [
    ("AI_CONTROLLER_REPAIR_ATTEMPTS", -1), ("AI_CONTROLLER_REPAIR_ATTEMPTS", 2),
    ("AI_CONTROLLER_ANSWER_RESERVE_TOKENS", 0),
    ("AI_CONTROLLER_ANSWER_RESERVE_SECONDS", float("nan")),
])
def test_invalid_answer_allowance_never_declares_a_run(budget, settings, name, value):
    from apps.ai.controller.budget import ControllerBudget, NotConfigured

    setattr(settings, name, value)
    with pytest.raises(NotConfigured):
        ControllerBudget.from_settings()


def test_queued_controller_keeps_declared_admission_ceiling(budget, settings):
    from apps.ai.admission.tests.support import enforce
    from apps.ai.controller.versions import CONTROLLER_ENGINE, pin
    from apps.ai.admission.limits import Ceiling

    enforce(settings, AI_ADMISSION_RUN_MAX_ATTEMPTS="7")
    payload = prepare_request({"pin": pin(CONTROLLER_ENGINE)})
    settings.AI_ADMISSION_RUN_MAX_ATTEMPTS = "700"
    assert Ceiling(**payload["admission_ceiling"]).attempts == 7
    assert prepare_request(payload, retry=True)["admission_ceiling"] == payload["admission_ceiling"]
