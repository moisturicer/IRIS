"""`CompositionRoot.llm()` is resilience-wrapped by default (IR-321).

No vendor account: `OpenAICompatibleAdapter` only reaches the network inside
`generate()`, so building the stack and inspecting its shape needs no key.
"""

from __future__ import annotations

import pytest

from apps.ai.composition import CompositionRoot
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.resilience.llm import (
    CircuitBreakingLLMProvider,
    FallbackLLMProvider,
    reset_llm_breakers,
)

pytestmark = pytest.mark.django_required


@pytest.fixture(autouse=True)
def _clean_breaker_registry():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


@pytest.fixture(autouse=True)
def _no_fallback_by_default(settings):
    settings.LLM_FALLBACK_API_KEY = ""


class DefaultWiringTests:
    def test_the_default_llm_is_wrapped_in_resilience(self, settings):
        settings.LLM_API_KEY = "k"
        provider = CompositionRoot().llm()
        assert isinstance(provider, CircuitBreakingLLMProvider)

    def test_an_injected_llm_bypasses_all_of_it(self):
        """The primary test seam for the whole query lane -- every fake-driven
        test in `test_ask_http.py` relies on `CompositionRoot(llm=...)`
        being used exactly as given, with no wrapping to work around."""
        fake = ScriptedLLM()
        assert CompositionRoot(llm=fake).llm() is fake

    def test_a_configured_fallback_composes_a_second_provider(self, settings):
        settings.LLM_API_KEY = "k1"
        settings.LLM_FALLBACK_API_KEY = "k2"
        provider = CompositionRoot().llm()
        assert isinstance(provider, FallbackLLMProvider)


class BreakerPersistenceTests:
    def test_circuit_state_survives_a_fresh_composition_root(self, settings):
        """`composition_root()` returns a brand-new `CompositionRoot()` on
        every call when nothing is installed (see its own docstring) -- a
        per-instance breaker would reset every request and could never trip.
        Two independently built roots for the same configuration must share
        one breaker."""
        settings.LLM_API_KEY = "k"
        settings.LLM_BASE_URL = "https://example.test/v1"
        settings.LLM_MODEL = "m"

        first = CompositionRoot().llm()
        second = CompositionRoot().llm()

        # Private attribute access is the only way to observe this from
        # outside the module; `apps/ai/resilience/tests/test_llm.py` asserts
        # the same property directly against `breaker_for`.
        assert first._breaker is second._breaker  # noqa: SLF001
