import pytest
from django.core.exceptions import ImproperlyConfigured
from apps.ai.routing.chat import verify_research_configuration

pytestmark = pytest.mark.django_required


@pytest.mark.parametrize("value", ["off", "on"])
def test_valid_development_switch(settings, value):
    settings.DEBUG = True
    settings.AI_RESEARCH_LANE = value
    verify_research_configuration()


@pytest.mark.parametrize("value,debug", [("enabled", True), ("", True), ("on", False)])
def test_invalid_or_production_switch_refuses(settings, value, debug):
    settings.DEBUG = debug
    settings.AI_RESEARCH_LANE = value
    with pytest.raises(ImproperlyConfigured):
        verify_research_configuration()
