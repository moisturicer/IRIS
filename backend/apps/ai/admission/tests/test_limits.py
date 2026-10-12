"""Reading the admission settings: fail closed, refuse a typo (IR-545)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai.admission.limits import (
    NotConfigured,
    REQUIRED_SETTINGS,
    output_cap,
    read_limits,
    verify_admission_configuration,
)

from .support import CAMPAIGN, enforce

pytestmark = pytest.mark.django_required


def test_the_campaign_reads_back_with_its_reserve_held(settings):
    enforce(settings)
    limits = read_limits()
    assert limits.campaign.attempts == 480
    assert limits.campaign.cost_micros == 15_000_000
    assert limits.campaign.active_ms == 3_600_000
    spendable = limits.spendable
    # Core 75%, protected 25% (pilot README §7).
    assert (spendable.attempts, spendable.input_tokens, spendable.output_tokens) == (360, 375_000, 60_000)
    assert spendable.cost_micros == 11_250_000 and spendable.active_ms == 2_700_000

    settings.AI_ADMISSION_RESERVE_RELEASED = True
    assert read_limits().spendable == read_limits().campaign


@pytest.mark.parametrize("name", REQUIRED_SETTINGS)
def test_any_unset_limit_is_not_configured_and_never_defaulted(settings, name):
    enforce(settings, **{name: ""})
    with pytest.raises(NotConfigured, match=name):
        read_limits()
    # Not a startup error: paid work is refused instead (fail closed).
    verify_admission_configuration()


@pytest.mark.parametrize("name, value", [
    ("AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS", "lots"),
    ("AI_ADMISSION_CAMPAIGN_MAX_COST_USD", "-1"),
    ("AI_ADMISSION_RESERVE_FRACTION", "1"),
    ("AI_ADMISSION_LANE_CONCURRENCY", "{chat: 3}"),
    ("AI_ADMISSION_LANE_CONCURRENCY", '{"chat": 0}'),
    ("AI_ADMISSION_PRICES", '{"cheap": {"input": 1}}'),
    ("AI_ADMISSION_PRICES", '{"cheap": {"input": -1, "output": 1}}'),
])
def test_a_malformed_limit_stops_startup(settings, name, value):
    enforce(settings, **{name: value})
    with pytest.raises(ImproperlyConfigured):
        verify_admission_configuration()


def test_an_unknown_mode_stops_startup(settings):
    settings.AI_PROVIDER_ADMISSION = "on"
    with pytest.raises(ImproperlyConfigured):
        verify_admission_configuration()


def test_queued_questions_need_enforcement(settings):
    settings.AI_DURABLE_ASK = True
    settings.AI_PROVIDER_ADMISSION = "off"
    with pytest.raises(ImproperlyConfigured, match="AI_PROVIDER_ADMISSION=enforce"):
        verify_admission_configuration()
    enforce(settings)
    verify_admission_configuration()


def test_the_output_cap_is_sent_only_under_enforcement(settings):
    settings.AI_PROVIDER_ADMISSION = "off"
    settings.AI_ADMISSION_MAX_OUTPUT_TOKENS = CAMPAIGN["AI_ADMISSION_MAX_OUTPUT_TOKENS"]
    assert output_cap() is None
    enforce(settings)
    assert output_cap() == 500


@pytest.mark.parametrize("name, value", [
    ("AI_ADMISSION_CAMPAIGN", "x" * 65),
    ("AI_ADMISSION_LANE_CONCURRENCY", '{"' + "l" * 33 + '": 1}'),
])
def test_a_value_too_long_to_store_stops_startup(settings, name, value):
    enforce(settings, **{name: value})
    with pytest.raises(ImproperlyConfigured):
        verify_admission_configuration()
