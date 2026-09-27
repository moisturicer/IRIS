"""The `answer` task reaches the model its Profile names (IR-378).

Driven through the HTTP boundary, the primary seam for this work: what a
Profile is *for* is which model a reader's question ends up at, and that is
only observable where the request is shaped. No vendor account and no network
-- `openai.OpenAI` is replaced by a recorder, so the assertion is on the
request the adapter built.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.providers.fakes import ScriptedReranker
from apps.ai.resilience.llm import reset_llm_breakers

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, ask, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _clean_breaker_registry():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


class _RecordingVendor:
    """Stands in for `openai.OpenAI`, recording what it was asked for."""

    def __init__(self):
        self.calls: list[dict] = []
        self.credentials: list[tuple] = []

    def __call__(self, *, api_key, base_url=None):
        self.credentials.append((api_key, base_url))
        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self._create))
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content="Rainfall gauges feed the model [1].")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def vendor(monkeypatch):
    recorder = _RecordingVendor()
    import openai

    monkeypatch.setattr(openai, "OpenAI", recorder)
    return recorder


def _root(embedder):
    """A root with fake retrieval and a real, unwrapped LLM seam.

    `llm` is deliberately left unset -- an injected provider bypasses Profile
    resolution, which is the property under test here rather than a property
    to reuse.
    """
    return CompositionRoot(
        embedder=embedder,
        reranker=ScriptedReranker(),
        permits=lambda record: True,
    )


class AnswerTaskTests:
    def test_the_answer_task_reaches_the_model_its_profile_names(
        self, settings, vendor, embedder, space, client_for
    ):
        settings.LLM_ANSWER_MODEL = "the-answer-model"
        settings.LLM_ANSWER_API_KEY = "answer-key"
        settings.LLM_ANSWER_VENDOR = "openrouter"
        settings.LLM_FALLBACK_API_KEY = ""
        # What the flat settings say must not win once the task is configured.
        settings.LLM_MODEL = "the-old-flat-model"

        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(_root(embedder)):
            response = ask(client_for(reader), FLOOD_QUESTION)

        assert response.status_code == 200
        assert response.json()["mode"] == "generative"
        assert [call["model"] for call in vendor.calls] == ["the-answer-model"]
        assert vendor.credentials == [("answer-key", "https://openrouter.ai/api/v1")]

    def test_with_no_new_variables_the_flat_settings_still_answer(
        self, settings, vendor, embedder, space, client_for
    ):
        """The compatibility promise: an existing deployment changes no
        `.env` and reaches the same model it does today."""
        settings.LLM_ANSWER_MODEL = ""
        settings.LLM_ANSWER_API_KEY = ""
        settings.LLM_ANSWER_VENDOR = ""
        settings.LLM_FALLBACK_API_KEY = ""
        settings.LLM_MODEL = "the-old-flat-model"
        settings.LLM_API_KEY = "flat-key"
        settings.LLM_BASE_URL = "https://flat.test/v1"

        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(_root(embedder)):
            ask(client_for(reader), FLOOD_QUESTION)

        assert [call["model"] for call in vendor.calls] == ["the-old-flat-model"]
        assert vendor.credentials == [("flat-key", "https://flat.test/v1")]

    def test_an_injected_fake_bypasses_profile_resolution_entirely(self):
        from apps.ai.providers.fakes import ScriptedLLM

        fake = ScriptedLLM()
        root = CompositionRoot(llm=fake)
        assert root.llm_for(InferenceTask.ANSWER) is fake
        assert root.llm_for("summary") is fake

    def test_asking_for_llm_first_does_not_make_every_task_configured(
        self, settings
    ):
        """`llm()` caches apart from the injection slot `llm_for` reads.

        Sharing one attribute would mean a root that had been asked for
        `llm()` returned the flat provider for *every* task, including an
        unconfigured one that must raise -- the old accessor silently
        answering for tasks nobody configured, which is the opposite of what
        the expand half is for.
        """
        from apps.ai.providers.openai_compatible import LLMUnavailable

        settings.LLM_API_KEY = "k"
        settings.LLM_SUMMARY_MODEL = ""
        root = CompositionRoot()

        root.llm()

        with pytest.raises(LLMUnavailable):
            root.llm_for(InferenceTask.SUMMARY)

    def test_an_unknown_task_name_is_refused_by_the_root(self):
        from apps.ai.inference import UnknownInferenceTask

        with pytest.raises(UnknownInferenceTask):
            CompositionRoot().llm_for("answers")
