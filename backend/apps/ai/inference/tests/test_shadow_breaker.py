"""Shadow decisions trip their own breaker, never the reader's (IR-466).

The decision reuses the `answer` task's Profile unchanged (ADR-035 §2), but is
built under a separate circuit-breaker key, so a run of shadow failures cannot
open the breaker a reader's answer depends on.
"""

from types import SimpleNamespace

import pytest

from apps.ai.composition import CompositionRoot
from apps.ai.evidence.model_decision import ModelEvidenceDecision
from apps.ai.evidence.shadow import SHADOW_BREAKER_KEY
from apps.ai.inference import InferenceTask, build_profile_llm, profile_for
from apps.ai.providers.fakes import ScriptedToolCallingLLM
from apps.ai.resilience.circuit import CircuitState
from apps.ai.resilience.llm import breaker_for, reset_llm_breakers

pytestmark = pytest.mark.django_required


@pytest.fixture(autouse=True)
def _clean_breakers():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


def _configure(settings):
    settings.LLM_ANSWER_VENDOR = "groq"
    settings.LLM_ANSWER_API_KEY = "key"
    settings.LLM_ANSWER_MODEL = "first"


def test_a_profile_can_be_built_under_another_breaker_key(settings):
    _configure(settings)

    provider = build_profile_llm(
        profile_for(InferenceTask.ANSWER), breaker_key=SHADOW_BREAKER_KEY
    )

    assert provider._breaker is breaker_for(SHADOW_BREAKER_KEY)
    assert provider._breaker is not breaker_for(InferenceTask.ANSWER.breaker_key)


def test_the_default_key_is_still_the_task_key(settings):
    _configure(settings)

    provider = build_profile_llm(profile_for(InferenceTask.ANSWER))

    assert provider._breaker is breaker_for(InferenceTask.ANSWER.breaker_key)


def test_shadow_failures_leave_the_answer_breaker_closed(settings, monkeypatch):
    import openai

    _configure(settings)
    monkeypatch.setattr("apps.ai.resilience.retry.time.sleep", lambda seconds: None)

    def down(**kwargs):
        raise ConnectionError("vendor down")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=down)))
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: client)

    decider = CompositionRoot().shadow_decider()
    for _ in range(6):
        decider.decide("is the sky blue?")

    assert breaker_for(SHADOW_BREAKER_KEY).state is CircuitState.OPEN
    answer = breaker_for(InferenceTask.ANSWER.breaker_key)
    assert answer.state is CircuitState.CLOSED and answer.failures == 0


def test_an_injected_shadow_llm_is_used_verbatim():
    llm = ScriptedToolCallingLLM([ScriptedToolCallingLLM.calling()])

    decider = CompositionRoot(shadow_llm=llm).shadow_decider()

    assert isinstance(decider, ModelEvidenceDecision)
    decider.decide("q")
    assert len(llm.tool_requests) == 1


def test_no_shadow_decider_when_the_answer_task_has_no_model(settings):
    settings.LLM_ANSWER_MODEL = ""
    settings.LLM_MODEL = ""

    assert CompositionRoot().shadow_decider() is None
