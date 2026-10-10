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
    api_key_variables,
    build_profile_llm,
    inference_task,
    model_variables,
    profile_for,
)
from apps.ai.providers.dialects import GROQ, OPENROUTER
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
        """ADR-036 covers vLLM and Ollama as configurations of the same
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


class WhereASettingMayBeSetTests:
    """What a startup refusal names (IR-379). The same inheritance rule
    `profile_for` applies, asked as a question rather than resolved -- so a
    refusal cannot name a variable the task would not have read."""

    def test_answer_may_take_either_the_task_or_the_flat_variable(self, settings):
        settings.LLM_ANSWER_VENDOR = ""

        assert api_key_variables("answer") == ("LLM_ANSWER_API_KEY", "LLM_API_KEY")
        assert model_variables("answer") == ("LLM_ANSWER_MODEL", "LLM_MODEL")

    def test_a_named_vendor_removes_the_inherited_key_but_not_the_model(
        self, settings
    ):
        """Naming a vendor says where a task runs, not that it stopped being
        configured -- so an inherited model at a named vendor with no key of
        its own is still a refusal rather than a task reading as off."""
        settings.LLM_ANSWER_VENDOR = "openrouter"

        assert api_key_variables("answer") == ("LLM_ANSWER_API_KEY",)
        assert model_variables("answer") == ("LLM_ANSWER_MODEL", "LLM_MODEL")

    def test_another_task_has_only_its_own_variables(self):
        assert api_key_variables("summary") == ("LLM_SUMMARY_API_KEY",)
        assert model_variables("summary") == ("LLM_SUMMARY_MODEL",)


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

        # One breaker for the whole list (IR-386), not one per model -- so
        # the fallback sits *under* the breaker rather than each candidate
        # carrying its own.
        assert isinstance(provider, CircuitBreakingLLMProvider)
        fallback = provider._provider  # noqa: SLF001
        assert isinstance(fallback, FallbackLLMProvider)
        # Same account throughout -- a fallback here is a model, not a vendor
        # (ADR-008 §Amendment).
        for candidate in fallback._providers:  # noqa: SLF001
            adapter = candidate._provider  # noqa: SLF001
            assert adapter._base_url == "https://one-vendor.test/v1"  # noqa: SLF001
            assert adapter._api_key == "k"  # noqa: SLF001

    def test_a_task_whose_reasoning_is_hidden_sends_no_reasoning_config(
        self, settings
    ):
        """IR-380: `""` is "send nothing", distinct from `None`, which would
        inherit `LLM_REASONING_EFFORT` from the flat settings."""
        settings.LLM_REASONING_EFFORT = "high"
        settings.LLM_SUMMARY_MODEL = "summary-model"
        settings.LLM_SUMMARY_API_KEY = "k"
        settings.LLM_SUMMARY_REASONING = False

        provider = build_profile_llm(profile_for(InferenceTask.SUMMARY))

        adapter = provider._provider._provider  # noqa: SLF001
        assert adapter._reasoning_effort == ""  # noqa: SLF001

    def test_a_task_whose_reasoning_is_shown_keeps_the_inherited_effort(
        self, settings
    ):
        settings.LLM_REASONING_EFFORT = "high"
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_ANSWER_REASONING = True

        provider = build_profile_llm(profile_for(InferenceTask.ANSWER))

        adapter = provider._provider._provider  # noqa: SLF001
        assert adapter._reasoning_effort is None  # noqa: SLF001
        assert adapter._resolved_reasoning_effort() == "high"  # noqa: SLF001

    def test_summary_builds_on_its_own_model_not_the_answer_one(self, settings):
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_SUMMARY_MODEL = "summary-model"
        settings.LLM_SUMMARY_API_KEY = "k"

        assert build_profile_llm(profile_for(InferenceTask.SUMMARY)).model == (
            "summary-model"
        )
        assert build_profile_llm(profile_for(InferenceTask.ANSWER)).model == (
            "answer-model"
        )

    def test_an_unconfigured_task_raises_rather_than_borrowing_a_model(
        self, settings
    ):
        settings.LLM_SUMMARY_MODEL = ""
        with pytest.raises(LLMUnavailable) as raised:
            build_profile_llm(profile_for(InferenceTask.SUMMARY))
        assert "LLM_SUMMARY_MODEL" in str(raised.value)

    def test_a_task_named_at_openrouter_gets_openrouters_dialect(self, settings):
        """Pointing a task at OpenRouter is configuration alone (IR-384) --
        no adapter, provider, or dialect code changes for it to take effect."""
        settings.LLM_ANSWER_VENDOR = "openrouter"
        settings.LLM_ANSWER_MODEL = "openrouter-model"
        settings.LLM_ANSWER_API_KEY = "k"

        provider = build_profile_llm(profile_for(InferenceTask.ANSWER))

        adapter = provider._provider._provider  # noqa: SLF001
        assert adapter.dialect is OPENROUTER

    def test_two_tasks_at_different_vendors_each_reach_their_own_dialect(
        self, settings
    ):
        settings.LLM_ANSWER_VENDOR = "openrouter"
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_RESOLVE_VENDOR = "groq"
        settings.LLM_RESOLVE_MODEL = "resolve-model"
        settings.LLM_RESOLVE_API_KEY = "k"

        answer_provider = build_profile_llm(profile_for(InferenceTask.ANSWER))
        resolve_provider = build_profile_llm(profile_for(InferenceTask.RESOLVE))

        answer_adapter = answer_provider._provider._provider  # noqa: SLF001
        resolve_adapter = resolve_provider._provider._provider  # noqa: SLF001
        assert answer_adapter.dialect is OPENROUTER
        assert resolve_adapter.dialect is GROQ


class PerTaskCircuitBreakerTests:
    """Each Inference task gets its own breaker, even at the same vendor and
    model (IR-386) -- the scenario the ticket names: a batchy `summary` run
    hitting a rate limit must not stop `answer` from working."""

    def test_two_tasks_at_the_same_vendor_and_model_keep_separate_breakers(
        self, settings
    ):
        settings.LLM_ANSWER_MODEL = "shared-model"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_ANSWER_BASE_URL = "https://one-vendor.test/v1"
        settings.LLM_SUMMARY_MODEL = "shared-model"
        settings.LLM_SUMMARY_API_KEY = "k"
        settings.LLM_SUMMARY_BASE_URL = "https://one-vendor.test/v1"

        answer_provider = build_profile_llm(profile_for(InferenceTask.ANSWER))
        summary_provider = build_profile_llm(profile_for(InferenceTask.SUMMARY))

        assert answer_provider._breaker is not summary_provider._breaker  # noqa: SLF001

    def test_the_same_task_reuses_its_own_breaker_across_calls(self, settings):
        settings.LLM_ANSWER_MODEL = "m"
        settings.LLM_ANSWER_API_KEY = "k"

        first = build_profile_llm(profile_for(InferenceTask.ANSWER))
        second = build_profile_llm(profile_for(InferenceTask.ANSWER))

        assert first._breaker is second._breaker  # noqa: SLF001


class ResolveProfileTests:
    """`resolve` reaches its own model over the flat vendor account (IR-383).

    The task that rewrites a follow-up into a standalone question. Unlike
    `summary` it is not off by default -- resolution has shipped since IR-296
    and a deployment that configures nothing must keep getting it -- so it
    ships a model and inherits the flat account the old `LLM_RESOLUTION_MODEL`
    shared.
    """

    def test_it_ships_a_model_that_exists_at_the_vendor(self, settings):
        """Verified with a real Groq call during IR-383: the previous default,
        `llama-3.1-8b-instant`, 404s."""
        assert profile_for(InferenceTask.RESOLVE).model == "openai/gpt-oss-20b"
        assert settings.LLM_RESOLVE_MODEL == "openai/gpt-oss-20b"

    def test_its_model_is_independent_of_the_answer_one(self, settings):
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_RESOLVE_MODEL = "resolve-model"

        assert profile_for(InferenceTask.RESOLVE).model == "resolve-model"
        assert profile_for(InferenceTask.ANSWER).model == "answer-model"

    def test_it_inherits_the_flat_vendor_account_but_never_the_flat_model(
        self, settings
    ):
        settings.LLM_BASE_URL = "https://one-vendor.test/v1"
        settings.LLM_API_KEY = "flat-key"
        settings.LLM_MODEL = "flat-model"
        settings.LLM_RESOLVE_MODEL = "resolve-model"

        profile = profile_for(InferenceTask.RESOLVE)

        assert profile.base_url == "https://one-vendor.test/v1"
        assert profile.api_key == "flat-key"
        assert profile.model == "resolve-model"
        assert model_variables("resolve") == ("LLM_RESOLVE_MODEL",)
        assert api_key_variables("resolve") == (
            "LLM_RESOLVE_API_KEY",
            "LLM_API_KEY",
        )

    def test_naming_a_vendor_stops_it_carrying_the_flat_key_there(self, settings):
        settings.LLM_RESOLVE_VENDOR = "openrouter"
        settings.LLM_API_KEY = "groq-key"

        profile = profile_for(InferenceTask.RESOLVE)

        assert profile.vendor is Vendor.OPENROUTER
        assert profile.api_key == ""
        assert api_key_variables("resolve") == ("LLM_RESOLVE_API_KEY",)

    def test_it_sends_no_reasoning_configuration(self, settings):
        settings.LLM_REASONING_EFFORT = "high"
        settings.LLM_RESOLVE_API_KEY = "k"

        provider = build_profile_llm(profile_for(InferenceTask.RESOLVE))

        adapter = provider._provider._provider  # noqa: SLF001
        assert adapter._reasoning_effort == ""  # noqa: SLF001


class ProviderPinTests:
    """IR-489: an allow-list of OpenRouter providers, per task."""

    def test_a_task_reads_its_own_pin(self, settings):
        settings.LLM_ANSWER_PROVIDER_ONLY = "together, fireworks"

        assert profile_for(InferenceTask.ANSWER).provider_only == (
            "together",
            "fireworks",
        )

    def test_no_pin_is_an_empty_tuple(self, settings):
        settings.LLM_SUMMARY_PROVIDER_ONLY = ""

        assert profile_for(InferenceTask.SUMMARY).provider_only == ()

    def test_a_pin_is_not_inherited_by_another_task(self, settings):
        settings.LLM_ANSWER_PROVIDER_ONLY = "together"
        settings.LLM_RESOLVE_PROVIDER_ONLY = ""

        assert profile_for(InferenceTask.RESOLVE).provider_only == ()

    def test_the_pin_reaches_the_adapter_a_task_is_built_with(self, settings):
        settings.LLM_ANSWER_VENDOR = "openrouter"
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_ANSWER_PROVIDER_ONLY = "together"

        provider = build_profile_llm(profile_for(InferenceTask.ANSWER))

        adapter = provider._provider._provider  # noqa: SLF001
        assert adapter.dialect.request_extras("")["extra_body"]["provider"] == {
            "data_collection": "deny",
            "only": ["together"],
        }

