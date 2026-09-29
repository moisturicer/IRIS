"""`CompositionRoot.resolver()` reaches the `resolve` Inference task (IR-383).

The wiring, not the rewriting: what model resolution ends up calling, and
what happens when that task is not configured. The rewriting itself is
`test_resolution.py`, and the reader-visible behaviour is
`test_resolution_http.py`.
"""

from __future__ import annotations

import pytest

from apps.ai.composition import CompositionRoot

pytestmark = pytest.mark.django_required


@pytest.fixture(autouse=True)
def _resolution_on(settings):
    settings.AI_QUESTION_RESOLUTION_ENABLED = True


def _adapter(resolver):
    """The OpenAI-compatible adapter under the completion-logging and
    resilience wrapping (IR-387 adds the outermost layer)."""
    return resolver._llm._provider._provider._provider  # noqa: SLF001


class ResolverModelTests:
    def test_it_calls_the_resolve_model_not_the_answer_one(self, settings):
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_RESOLVE_MODEL = "resolve-model"
        settings.LLM_RESOLVE_API_KEY = "k"

        resolver = CompositionRoot().resolver()

        assert _adapter(resolver)._model == "resolve-model"  # noqa: SLF001

    def test_the_shipped_default_is_a_model_that_exists_at_the_vendor(self):
        """Verified with a real Groq call during IR-383. The previous
        default, `llama-3.1-8b-instant`, was withdrawn and 404s, which made
        every follow-up fail."""
        resolver = CompositionRoot().resolver()

        assert _adapter(resolver)._model == "openai/gpt-oss-20b"  # noqa: SLF001

    def test_it_sends_no_reasoning_configuration(self, settings):
        settings.LLM_REASONING_EFFORT = "high"

        resolver = CompositionRoot().resolver()

        assert _adapter(resolver)._reasoning_effort == ""  # noqa: SLF001


class ResolverSwitchTests:
    def test_switching_resolution_off_skips_it_entirely(self, settings):
        settings.AI_QUESTION_RESOLUTION_ENABLED = False

        assert CompositionRoot().resolver() is None

    def test_an_unconfigured_resolve_task_degrades_rather_than_raising(
        self, settings
    ):
        """No rewriter is what the caller already treats as "search with the
        question as typed" -- the same fallback a dead model takes."""
        settings.LLM_RESOLVE_MODEL = ""

        assert CompositionRoot().resolver() is None
