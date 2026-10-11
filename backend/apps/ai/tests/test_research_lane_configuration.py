import pytest
from django.core.exceptions import ImproperlyConfigured
from apps.ai.routing.chat import verify_research_configuration

pytestmark = pytest.mark.django_required


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize("value", ["off", "staff", "on"])
def test_valid_switch_in_development_and_production(settings, value, debug):
    # IR-504 lifts IR-515's development-only restriction.
    settings.DEBUG = debug
    settings.AI_RESEARCH_LANE = value
    verify_research_configuration()


@pytest.mark.parametrize("value", ["enabled", "", "readers"])
def test_invalid_switch_refuses(settings, value):
    settings.AI_RESEARCH_LANE = value
    with pytest.raises(ImproperlyConfigured):
        verify_research_configuration()
