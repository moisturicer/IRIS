"""`CompositionRoot.llm_for(task)` is resilience-wrapped by default (IR-321,
IR-388).

No vendor account: `OpenAICompatibleAdapter` only reaches the network inside
`generate()`, so building the stack and inspecting its shape needs no key.
"""

from __future__ import annotations

import pytest

from apps.ai.composition import CompositionRoot
from apps.ai.inference import InferenceTask
from apps.ai.inference.completions import CompletionLoggingLLMProvider
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.resilience.llm import CircuitBreakingLLMProvider, reset_llm_breakers

pytestmark = pytest.mark.django_required


@pytest.fixture(autouse=True)
def _clean_breaker_registry():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


class DefaultWiringTests:
    def test_a_task_llm_is_wrapped_in_resilience(self, settings):
        settings.LLM_API_KEY = "k"
        provider = CompositionRoot().llm_for(InferenceTask.ANSWER)
        # `llm_for` wraps the resilient provider in `CompletionLoggingLLMProvider`
        # (IR-387) -- the completion-record decorator, not a second layer of
        # resilience -- so the breaker/retry stack is one level in.
        assert isinstance(provider, CompletionLoggingLLMProvider)
        assert isinstance(provider._provider, CircuitBreakingLLMProvider)  # noqa: SLF001

    def test_an_injected_llm_bypasses_all_of_it(self):
        """The primary test seam for the whole query lane -- every fake-driven
        test in `test_ask_http.py` relies on `CompositionRoot(llm=...)`
        being used exactly as given, with no wrapping to work around."""
        fake = ScriptedLLM()
        assert CompositionRoot(llm=fake).llm_for(InferenceTask.ANSWER) is fake

    def test_the_flat_settings_can_no_longer_configure_a_second_vendor(
        self, settings
    ):
        """IR-385 deleted `LLM_FALLBACK_*`. Setting it configures nothing --
        `manage.py check` refuses startup instead (`inference/tests/
        test_startup.py`), so there is no live seam left for it to reach."""
        settings.LLM_API_KEY = "k1"

        provider = CompositionRoot().llm_for(InferenceTask.ANSWER)

        assert isinstance(provider._provider, CircuitBreakingLLMProvider)  # noqa: SLF001


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

        first = CompositionRoot().llm_for(InferenceTask.ANSWER)
        second = CompositionRoot().llm_for(InferenceTask.ANSWER)

        # Private attribute access is the only way to observe this from
        # outside the module; `apps/ai/resilience/tests/test_llm.py` asserts
        # the same property directly against `breaker_for`.
        assert first._provider._breaker is second._provider._breaker  # noqa: SLF001
