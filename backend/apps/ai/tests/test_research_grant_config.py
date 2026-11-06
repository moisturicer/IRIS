"""Research-grant settings fail closed at startup (IR-717)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai.grants.config import verify_grant_configuration
from .grant_support import KEY_A, enable_grants


def test_off_by_default_needs_nothing(settings):
    settings.AI_RESEARCH_GRANTS = False
    settings.AI_RESEARCH_GRANT_KEYS = ""
    verify_grant_configuration()


def test_a_complete_configuration_starts(settings):
    enable_grants(settings)
    verify_grant_configuration()


@pytest.mark.parametrize("name,value,message", [
    ("AI_RESEARCH_GRANT_KEYS", "", "AI_RESEARCH_GRANT_KEYS is required"),
    ("AI_RESEARCH_GRANT_KEYS", "k1:c2hvcnQ", "at least 32 bytes"),
    ("AI_RESEARCH_GRANT_KEYS", f"bad kid!:{KEY_A}", "kid:base64url-secret"),
    ("AI_RESEARCH_GRANT_ACTIVE_KEY", "", "AI_RESEARCH_GRANT_ACTIVE_KEY is required"),
    ("AI_RESEARCH_GRANT_ACTIVE_KEY", "k7", "must name a key"),
    ("AI_RESEARCH_GRANT_AUDIENCE", " ", "AI_RESEARCH_GRANT_AUDIENCE is required"),
    ("AI_RESEARCH_GRANT_DEPLOYMENT", "", "AI_RESEARCH_GRANT_DEPLOYMENT is required"),
    ("AI_RESEARCH_GRANT_TTL_SECONDS", 3600, "AI_RESEARCH_GRANT_TTL_SECONDS"),
])
def test_enabled_with_a_missing_or_bad_value_refuses_to_start(settings, name, value, message):
    enable_grants(settings)
    setattr(settings, name, value)
    with pytest.raises(ImproperlyConfigured, match=message):
        verify_grant_configuration()


def test_django_startup_runs_the_check(settings):
    from django.apps import apps

    enable_grants(settings)
    settings.AI_RESEARCH_GRANT_KEYS = ""
    # Production startup also requires LlamaParse (IR-843).
    for name, value in {"LLAMAPARSE_API_KEY": "llx-test", "LLAMAPARSE_VERSION": "2026-09-28"}.items():
        setattr(settings, name, value)
    with pytest.raises(ImproperlyConfigured, match="AI_RESEARCH_GRANT_KEYS is required"):
        apps.get_app_config("ai").ready()
