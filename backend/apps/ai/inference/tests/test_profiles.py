"""The closed task set and the Profiles it resolves to (IR-378).

No vendor account: a Profile is settings read into a value object, and
building the provider it describes only reaches the network inside
``generate()``.
"""

from __future__ import annotations

import pytest

from apps.ai.inference import (
    DataPolicy,
    InferenceTask,
    UnknownInferenceTask,
    UnknownVendor,
    Vendor,
    build_profile_llm,
    inference_task,
    profile_for,
)
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


@pytest.fixture(autouse=True)
def _no_cross_vendor_fallback(settings):
    settings.LLM_FALLBACK_API_KEY = ""


class ClosedTaskSetTests:
    def test_the_set_is_exactly_four_named_tasks(self):
        assert [task.value for task in InferenceTask] == [
            "answer",
            "resolve",
            "summary",
            "describe_figure",
        ]

    def test_a_name_outside_the_set_is_an_error_not_a_default(self):
        with pytest.raises(UnknownInferenceTask) as raised:
            inference_task("anwser")
        # The message names the set, so a typo is diagnosable from the failure.
        assert "answer" in str(raised.value)

    def test_a_task_passes_through_unchanged(self):
        assert inference_task(InferenceTask.ANSWER) is InferenceTask.ANSWER

    def test_describe_figure_is_declared_and_off(self, settings):
        """Reserved, not implemented: its spec reverses ADR-025's
        no-image-leaves-the-deployment clause and is not this ticket."""
        settings.LLM_DESCRIBE_FIGURE_MODEL = ""
        assert profile_for(InferenceTask.DESCRIBE_FIGURE).is_configured is False


class ProfileResolutionTests:
    def test_a_profile_carries_everything_a_task_needs(self, settings):
        settings.LLM_ANSWER_VENDOR = "openrouter"
        settings.LLM_ANSWER_MODEL = "primary-model"
        settings.LLM_ANSWER_FALLBACK_MODELS = "second-model, third-model"
        settings.LLM_ANSWER_API_KEY = "answer-key"
        settings.LLM_ANSWER_BASE_URL = ""
        settings.LLM_ANSWER_REASONING = True

        profile = profile_for("answer")

        assert profile.vendor is Vendor.OPENROUTER
        assert profile.model == "primary-model"
        assert profile.fallback_models == ("second-model", "third-model")
        assert profile.api_key == "answer-key"
        assert profile.base_url == "https://openrouter.ai/api/v1"
        assert profile.reasoning_visible is True
        assert profile.data_policy is DataPolicy.NO_TRAINING

    def test_the_answer_profile_defaults_to_todays_flat_settings(self, settings):
        """A deployment that sets no new variable behaves identically."""
        settings.LLM_ANSWER_MODEL = ""
        settings.LLM_ANSWER_API_KEY = ""
        settings.LLM_ANSWER_BASE_URL = ""
        settings.LLM_BASE_URL = "https://flat.test/v1"
        settings.LLM_API_KEY = "flat-key"
        settings.LLM_MODEL = "flat-model"

        profile = profile_for(InferenceTask.ANSWER)

        assert (profile.model, profile.api_key) == ("flat-model", "flat-key")
        assert profile.base_url == "https://flat.test/v1"

    def test_another_task_does_not_inherit_the_answer_model(self, settings):
        """Off, rather than silently answering with the answer model --
        which is how a Groq-only developer runs IRIS with one key."""
        settings.LLM_MODEL = "flat-model"
        settings.LLM_SUMMARY_MODEL = ""

        assert profile_for(InferenceTask.SUMMARY).is_configured is False

    def test_two_tasks_can_sit_on_different_vendors(self, settings):
        settings.LLM_ANSWER_VENDOR = "openrouter"
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_RESOLVE_VENDOR = "groq"
        settings.LLM_RESOLVE_MODEL = "resolve-model"

        assert profile_for("answer").base_url == "https://openrouter.ai/api/v1"
        assert profile_for("resolve").base_url == "https://api.groq.com/openai/v1"

    def test_a_named_vendor_stops_the_flat_key_being_inherited(self, settings):
        """The flat settings describe one vendor. Inheriting half of them is
        how a request reaches OpenRouter authenticated for Groq."""
        settings.LLM_ANSWER_VENDOR = "openrouter"
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_ANSWER_API_KEY = ""
        settings.LLM_API_KEY = "the-groq-key"

        profile = profile_for(InferenceTask.ANSWER)

        assert profile.base_url == "https://openrouter.ai/api/v1"
        assert profile.api_key == ""

    def test_an_inherited_base_url_decides_the_vendor_it_points_at(
        self, settings
    ):
        """IR-382 selects a vendor dialect on this field, so a Profile whose
        `vendor` disagreed with its own `base_url` would send one vendor's
        request shape to the other."""
        settings.LLM_ANSWER_VENDOR = ""
        settings.LLM_ANSWER_BASE_URL = ""
        settings.LLM_BASE_URL = "https://openrouter.ai/api/v1"

        assert profile_for(InferenceTask.ANSWER).vendor is Vendor.OPENROUTER

    def test_a_self_hosted_base_url_is_not_refused(self, settings):
        """ADR-021 covers vLLM and Ollama as configurations of the same
        adapter, so an unrecognised URL is not a mistake to raise on -- only
        a *named* vendor outside the pair is."""
        settings.LLM_ANSWER_VENDOR = ""
        settings.LLM_ANSWER_BASE_URL = "http://localhost:8000/v1"

        profile = profile_for(InferenceTask.ANSWER)

        assert profile.base_url == "http://localhost:8000/v1"
        assert profile.vendor is Vendor.GROQ

    def test_an_unsanctioned_vendor_is_refused(self, settings):
        settings.LLM_ANSWER_VENDOR = "anthropic"
        with pytest.raises(UnknownVendor):
            profile_for(InferenceTask.ANSWER)

    def test_reasoning_visibility_is_per_task(self, settings):
        """Set explicitly rather than read off the shipped defaults: a
        developer's own `backend/.env` can override any of these, and a test
        that a local `.env` can flip asserts the environment, not the code."""
        settings.LLM_ANSWER_REASONING = True
        settings.LLM_RESOLVE_REASONING = False
        settings.LLM_SUMMARY_REASONING = False

        assert profile_for(InferenceTask.ANSWER).reasoning_visible is True
        assert profile_for(InferenceTask.RESOLVE).reasoning_visible is False
        assert profile_for(InferenceTask.SUMMARY).reasoning_visible is False


class BuildingTheProviderTests:
    def test_one_model_builds_the_same_resilient_provider_as_before(self, settings):
        settings.LLM_ANSWER_MODEL = "only-model"
        settings.LLM_ANSWER_API_KEY = "k"

        provider = build_profile_llm(profile_for(InferenceTask.ANSWER))

        assert isinstance(provider, CircuitBreakingLLMProvider)
        assert provider.model == "only-model"

    def test_a_fallback_list_walks_models_at_the_same_vendor(self, settings):
        settings.LLM_ANSWER_MODEL = "first"
        settings.LLM_ANSWER_FALLBACK_MODELS = "second"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_ANSWER_BASE_URL = "https://one-vendor.test/v1"

        provider = build_profile_llm(profile_for(InferenceTask.ANSWER))

        assert isinstance(provider, FallbackLLMProvider)
        # Same account throughout -- a fallback here is a model, not a vendor
        # (ADR-008 §Amendment).
        for candidate in provider._providers:  # noqa: SLF001
            adapter = candidate._provider._provider  # noqa: SLF001
            assert adapter._base_url == "https://one-vendor.test/v1"  # noqa: SLF001
            assert adapter._api_key == "k"  # noqa: SLF001

    def test_an_unconfigured_task_raises_rather_than_borrowing_a_model(
        self, settings
    ):
        settings.LLM_SUMMARY_MODEL = ""
        with pytest.raises(LLMUnavailable) as raised:
            build_profile_llm(profile_for(InferenceTask.SUMMARY))
        assert "LLM_SUMMARY_MODEL" in str(raised.value)
