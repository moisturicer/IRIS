"""Same-vendor model fallback, and the absence of a cross-vendor one (IR-385).

One deprecated model id must not be able to take Ask IRIS down, which is how
the `resolve` path broke. A Profile carries an ordered list of models **at one
vendor**, and who walks it depends on the vendor: IRIS loops for Groq, which
has no native multi-model field, and delegates to OpenRouter, which resolves
the list itself in one request.

No vendor account and no network: `openai.OpenAI` is replaced by a recorder,
so every assertion here is about the requests the adapter built and the
credentials it built them with.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.ai.inference import InferenceTask, build_profile_llm, profile_for
from apps.ai.providers.openai_compatible import LLMUnavailable
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


class _RecordingVendor:
    """Stands in for `openai.OpenAI`, failing whichever models it is told to.

    `credentials` is what makes a cross-vendor switch observable: a second
    vendor is a second `(api_key, base_url)` pair, whatever model string
    accompanies it.
    """

    def __init__(self, failing: dict[str, Exception] | None = None):
        self.calls: list[dict] = []
        self.credentials: list[tuple] = []
        self._failing = failing or {}

    def __call__(self, *, api_key, base_url=None):
        self.credentials.append((api_key, base_url))
        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self._create))
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        failure = self._failing.get(kwargs["model"])
        if failure is not None:
            raise failure
        message = SimpleNamespace(content="An answer.")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    @property
    def models_called(self) -> list[str]:
        return [call["model"] for call in self.calls]


def _vendor(monkeypatch, failing=None) -> _RecordingVendor:
    import openai

    recorder = _RecordingVendor(failing)
    monkeypatch.setattr(openai, "OpenAI", recorder)
    return recorder


def _answer_llm(settings, vendor_name: str, models: str, fallbacks: str):
    settings.LLM_ANSWER_VENDOR = vendor_name
    settings.LLM_ANSWER_API_KEY = "one-account-key"
    settings.LLM_ANSWER_MODEL = models
    settings.LLM_ANSWER_FALLBACK_MODELS = fallbacks
    return build_profile_llm(profile_for(InferenceTask.ANSWER))


def _rate_limited() -> Exception:
    return RuntimeError("rate limit exceeded")


class GroqWalksTheListItselfTests:
    """Groq has no native fallback field, so IRIS moves down the list."""

    def test_a_switchable_failure_moves_to_the_next_model(
        self, settings, monkeypatch
    ):
        vendor = _vendor(monkeypatch, failing={"first": _rate_limited()})
        llm = _answer_llm(settings, "groq", "first", "second,third")

        assert llm.generate(system="s", user="u") == "An answer."
        assert vendor.models_called == ["first", "second"]

    def test_the_model_that_answered_is_discoverable_by_the_caller(
        self, settings, monkeypatch
    ):
        """ADR-023's recall measurement assumes one model per run; a silent
        switch mid-run is exactly the confound it cannot survive unnoticed."""
        _vendor(monkeypatch, failing={"first": _rate_limited()})
        llm = _answer_llm(settings, "groq", "first", "second")

        llm.generate(system="s", user="u")

        # One breaker for the whole list sits above it now (IR-386), so the
        # `FallbackLLMProvider` that actually walked the models is one level
        # down.
        assert isinstance(llm, CircuitBreakingLLMProvider)
        fallback = llm._provider  # noqa: SLF001
        assert isinstance(fallback, FallbackLLMProvider)
        assert fallback.last_model_used == "second"
        assert llm.model == "second"

    def test_a_failure_another_model_cannot_fix_stops_the_walk(
        self, settings, monkeypatch
    ):
        """A bad key is still a bad key on the next model, so spending the
        rest of the list on it buys nothing and hides the real fault -- the
        no-silent-fall-through rule ADR-021 states."""
        vendor = _vendor(
            monkeypatch, failing={"first": RuntimeError("unauthorized")}
        )
        llm = _answer_llm(settings, "groq", "first", "second,third")

        with pytest.raises(LLMUnavailable):
            llm.generate(system="s", user="u")

        assert vendor.models_called == ["first"]

    def test_exhausting_the_list_fails_rather_than_reaching_a_second_vendor(
        self, settings, monkeypatch
    ):
        """The acceptance criterion cross-vendor failover was deleted for:
        every model at the account fails, and nothing else is tried. The
        answer path turns this into the explicit unavailable state with the
        sources still returned (ADR-008)."""
        settings.LLM_FALLBACK_BASE_URL = "https://a-second-vendor.test/v1"
        settings.LLM_FALLBACK_API_KEY = "a-second-account-key"
        settings.LLM_FALLBACK_MODEL = "a-second-vendors-model"
        vendor = _vendor(
            monkeypatch,
            failing={
                "first": _rate_limited(),
                "second": _rate_limited(),
            },
        )
        llm = _answer_llm(settings, "groq", "first", "second")

        with pytest.raises(LLMUnavailable):
            llm.generate(system="s", user="u")

        assert vendor.models_called == ["first", "second"]
        assert set(vendor.credentials) == {
            ("one-account-key", "https://api.groq.com/openai/v1")
        }

    def test_last_attempted_model_names_the_last_one_tried_through_the_breaker(
        self, settings, monkeypatch
    ):
        """IR-387's completion record reads `last_attempted_model` off
        whatever `build_profile_llm` returns -- which is the outer
        `CircuitBreakingLLMProvider` since IR-386, not the
        `FallbackLLMProvider` underneath it. `last_model_used` alone would
        report `None` here (it is set only on success), and the model that
        answered fell back to `providers[0]` -- "first" -- which would
        blame the wrong model for a failure "second" actually raised."""
        _vendor(
            monkeypatch,
            failing={"first": _rate_limited(), "second": _rate_limited()},
        )
        llm = _answer_llm(settings, "groq", "first", "second")

        with pytest.raises(LLMUnavailable):
            llm.generate(system="s", user="u")

        assert isinstance(llm, CircuitBreakingLLMProvider)
        assert llm.last_attempted_model == "second"
        assert llm.last_model_used is None


class OpenRouterResolvesTheListItselfTests:
    """OpenRouter reads the whole list from one request, so IRIS does not
    loop -- a second request would ask for a fallback already performed."""

    def test_the_list_travels_as_one_request(self, settings, monkeypatch):
        vendor = _vendor(monkeypatch)
        llm = _answer_llm(settings, "openrouter", "first", "second,third")

        llm.generate(system="s", user="u")

        assert vendor.models_called == ["first"]
        assert vendor.calls[0]["extra_body"]["models"] == [
            "first",
            "second",
            "third",
        ]

    def test_no_second_provider_is_composed_for_it(self, settings, monkeypatch):
        _vendor(monkeypatch)
        llm = _answer_llm(settings, "openrouter", "first", "second,third")

        assert not isinstance(llm, FallbackLLMProvider)

    def test_a_task_with_no_fallbacks_sends_no_model_list(
        self, settings, monkeypatch
    ):
        """`models` is the fallback field, not a restatement of `model`."""
        vendor = _vendor(monkeypatch)
        llm = _answer_llm(settings, "openrouter", "only", "")

        llm.generate(system="s", user="u")

        assert "models" not in vendor.calls[0]["extra_body"]


class TheCrossVendorPathIsDeletedNotDisabledTests:
    def test_the_second_vendor_config_no_longer_exists(self):
        """IR-321 shipped `cross_vendor_fallback_config()`; ADR-008 rejects
        a second vendor by name, so it is gone rather than left unreachable
        behind an unset key."""
        import apps.ai.resilience.llm as resilience

        assert not hasattr(resilience, "cross_vendor_fallback_config")

    def test_the_flat_settings_describe_exactly_one_account(self, settings):
        from apps.ai.resilience.llm import _configured_providers

        settings.LLM_FALLBACK_API_KEY = "a-second-account-key"

        assert len(_configured_providers()) == 1
