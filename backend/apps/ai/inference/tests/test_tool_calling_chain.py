"""Every provider on the `answer` chain carries the tool-calling port (IR-465).

The whole reason `ToolCallingLLM` is abstract: the retrying, circuit-breaking,
fallback and completion-logging providers each implement the existing methods
explicitly, so a defaulted new method would be bypassed by all of them. This
walks the chain a real `CompositionRoot` builds for the `answer` task, rather
than a list somebody remembered to keep up to date, so a fifth decorator added
later is covered the day it appears.

No vendor account and no network: `openai.OpenAI` is replaced by a recorder.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from apps.ai.composition import CompositionRoot
from apps.ai.inference import (
    CompletionLoggingLLMProvider,
    InferenceTask,
    build_profile_llm,
    profile_for,
)
from apps.ai.inference.completions import LOGGER_NAME
from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter
from apps.ai.providers.tool_calling import ToolCallingLLM, ToolDefinition
from apps.ai.resilience.llm import (
    CircuitBreakingLLMProvider,
    FallbackLLMProvider,
    RetryingLLMProvider,
    reset_llm_breakers,
)

pytestmark = pytest.mark.django_required

TOOLS = (ToolDefinition(name="search_corpus", description="Search."),)


@pytest.fixture(autouse=True)
def _clean_breakers():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


@pytest.fixture
def vendor(monkeypatch):
    import openai

    calls: list[dict] = []

    def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(
            content="HYPOTHETICAL-ANSWER",
            reasoning="SECRET-REASONING",
            tool_calls=None,
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)

    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kw: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    return calls


def _configure(settings, fallbacks: str = "") -> None:
    settings.LLM_ANSWER_VENDOR = "groq"
    settings.LLM_ANSWER_API_KEY = "key"
    settings.LLM_ANSWER_MODEL = "first"
    settings.LLM_ANSWER_FALLBACK_MODELS = fallbacks


def _chain(provider) -> list:
    """Every provider from the outside in, descending through whichever
    attribute a decorator holds its inner provider(s) in."""
    found = [provider]
    inner = getattr(provider, "_provider", None)
    if inner is not None:
        found += _chain(inner)
    for member in getattr(provider, "_providers", []):
        found += _chain(member)
    return found


@pytest.mark.parametrize("fallbacks", ["", "second,third"], ids=["single", "fallback-list"])
def test_every_provider_on_the_answer_chain_implements_the_port(settings, fallbacks):
    _configure(settings, fallbacks)

    root = CompositionRoot()
    chain = _chain(root.llm_for(InferenceTask.ANSWER))

    types = {type(p) for p in chain}
    assert {CompletionLoggingLLMProvider, CircuitBreakingLLMProvider} <= types
    assert RetryingLLMProvider in types and OpenAICompatibleAdapter in types
    if fallbacks:
        assert FallbackLLMProvider in types

    for provider in chain:
        cls = type(provider)
        assert isinstance(provider, ToolCallingLLM), cls.__name__
        assert "complete_with_tools" in vars(cls), (
            f"{cls.__name__} inherits complete_with_tools instead of "
            "implementing it"
        )


def test_the_chain_carries_a_decision_end_to_end(settings, vendor):
    _configure(settings, "second")

    completion = (
        CompositionRoot()
        .llm_for(InferenceTask.ANSWER)
        .complete_with_tools("system", "user", TOOLS, timeout_seconds=9)
    )

    assert completion.text == "HYPOTHETICAL-ANSWER"
    (sent,) = vendor
    assert sent["tools"][0]["function"]["name"] == "search_corpus"
    assert sent["timeout"] == 9
    assert sent["model"] == "first"


def test_the_built_profile_chain_is_the_one_checked(settings):
    """`llm_for` wraps `build_profile_llm`'s return value; both are walked so
    the test cannot pass on a chain production does not use."""
    _configure(settings, "second")
    assert all(
        isinstance(p, ToolCallingLLM)
        for p in _chain(build_profile_llm(profile_for(InferenceTask.ANSWER)))
    )


def test_the_completion_record_names_the_model_and_never_the_text(
    settings, vendor, caplog
):
    _configure(settings)
    logging.getLogger("apps").propagate = True
    try:
        caplog.set_level(logging.DEBUG)
        CompositionRoot().llm_for(InferenceTask.ANSWER).complete_with_tools(
            "a system prompt", "a user question", TOOLS
        )
    finally:
        logging.getLogger("apps").propagate = False

    # pytest 9 also attaches caplog's handler to the non-propagating `apps`
    # logger, so one emitted record can be captured twice; judge the distinct
    # messages, not the capture count.
    records = [r for r in caplog.records if r.name == LOGGER_NAME]
    assert records
    assert len({r.getMessage() for r in records}) == 1
    assert all(r.model == "first" and r.reasoning_present is True for r in records)

    everything = caplog.text
    for secret in ("HYPOTHETICAL-ANSWER", "SECRET-REASONING", "a user question"):
        assert secret not in everything
