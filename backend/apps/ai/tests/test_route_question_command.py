"""The demonstrator uses the same router as future reader integration."""

import io
import json

import pytest
from django.core.management import call_command

from apps.ai.providers.decisions import ScriptedDecisionModel
from apps.ai.routing.configuration import configured_providers
from apps.ai.routing.router import LANES

pytestmark = pytest.mark.django_required


def test_command_prints_decision_probabilities_and_stage(monkeypatch):
    values = {lane: 0.02 for lane in LANES}
    values.update(count=0.96, injection=0.01)
    monkeypatch.setattr(
        "apps.ai.management.commands.route_question.configured_providers",
        lambda: (ScriptedDecisionModel(values), None),
    )
    output = io.StringIO()
    call_command("route_question", "How many papers about aquaponics?", stdout=output)
    decision = json.loads(output.getvalue())
    assert decision["lane"] == "count"
    assert decision["stage"] == "fixed"
    assert decision["probabilities"]["count"] == 0.96


def test_jev_off_configures_only_the_backup(settings):
    settings.AI_JEV_ROUTING_ENABLED = False
    settings.AI_ROUTE_GROQ_APPROVED = True
    settings.LLM_ROUTE_VENDOR = "groq"
    settings.LLM_ROUTE_MODEL = "route-model"
    settings.LLM_ROUTE_API_KEY = "test-key"
    jev, backup = configured_providers()
    assert jev is None
    assert backup is not None


def test_unapproved_groq_backup_fails_closed(settings):
    settings.AI_JEV_ROUTING_ENABLED = False
    settings.AI_ROUTE_GROQ_APPROVED = False
    settings.LLM_ROUTE_VENDOR = "groq"
    settings.LLM_ROUTE_MODEL = "route-model"
    settings.LLM_ROUTE_API_KEY = "test-key"
    assert configured_providers() == (None, None)
