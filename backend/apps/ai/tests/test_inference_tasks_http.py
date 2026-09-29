"""The `answer` task reaches the model its Profile names (IR-378).

Driven through the HTTP boundary, the primary seam for this work: what a
Profile is *for* is which model a reader's question ends up at, and that is
only observable where the request is shaped. No vendor account and no network
-- `openai.OpenAI` is replaced by a recorder, so the assertion is on the
request the adapter built.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.inference.completions import LOGGER_NAME as COMPLETION_LOGGER
from apps.ai.providers.fakes import ScriptedReranker
from apps.ai.resilience.llm import reset_llm_breakers

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, ask, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _clean_breaker_registry():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


@pytest.fixture
def completion_logs(caplog):
    """`caplog`, actually wired to the completion logger (IR-387).

    `apps` sets `propagate: False` in `config/settings/base.py`, so records
    never reach the root logger `caplog` attaches to by default -- see
    `apps/ai/answers/tests/test_service.py`'s `service_logs` fixture for the
    same fix on the same problem. A caller reads `caplog.records` as usual
    once the test body has run; this only wires the handler up.
    """
    logger = logging.getLogger(COMPLETION_LOGGER)
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger=COMPLETION_LOGGER)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


class _RecordingVendor:
    """Stands in for `openai.OpenAI`, recording what it was asked for."""

    def __call__(self, *, api_key, base_url=None):
        self.credentials.append((api_key, base_url))
        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self._create))
        )

    def __init__(self, failing=None):
        self.calls: list[dict] = []
        self.credentials: list[tuple] = []
        self._failing = failing or {}

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        failure = self._failing.get(kwargs["model"])
        if failure is not None:
            raise failure
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


class ExhaustingTheFallbackListTests:
    """IR-385: what a reader sees when every model on the account fails."""

    def test_the_answer_is_unavailable_and_the_sources_are_still_returned(
        self, settings, monkeypatch, embedder, space, client_for
    ):
        """ADR-008's rule survives the fallback list: no model, no answer,
        and retrieval's passages are still handed over so a reader can read
        them themselves. Nothing is tried at a second vendor -- there is no
        longer one to try."""
        import openai

        rate_limited = RuntimeError("rate limit exceeded")
        vendor = _RecordingVendor(
            failing={"first-model": rate_limited, "second-model": rate_limited}
        )
        monkeypatch.setattr(openai, "OpenAI", vendor)

        settings.LLM_ANSWER_MODEL = "first-model"
        settings.LLM_ANSWER_FALLBACK_MODELS = "second-model"
        settings.LLM_ANSWER_API_KEY = "one-account-key"

        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        with use_composition_root(_root(embedder)):
            body = ask(client_for(reader), FLOOD_QUESTION).json()

        assert body["answer"] is None
        assert body["mode"] == "unavailable"
        assert [source["id"] for source in body["sources"]] == [flood.pk]
        assert [call["model"] for call in vendor.calls] == [
            "first-model",
            "second-model",
        ]
        assert set(vendor.credentials) == {
            ("one-account-key", "https://api.groq.com/openai/v1")
        }


class CompletionLoggingWiredThroughLlmForTests:
    """IR-387: `llm_for` is the one seam every production caller reaches a
    task's model through, so wiring the completion logger there (rather than
    into `build_profile_llm` itself, which existing tests assert returns a
    bare `FallbackLLMProvider`) means the whole HTTP path gets one record per
    call for free."""

    def test_a_real_answer_call_emits_a_completion_record(
        self, completion_logs, settings, vendor, embedder, space, client_for
    ):
        settings.LLM_ANSWER_MODEL = "the-answer-model"
        settings.LLM_ANSWER_API_KEY = "answer-key"
        settings.LLM_ANSWER_VENDOR = "groq"

        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(_root(embedder)):
            ask(client_for(reader), FLOOD_QUESTION)

        records = [
            r for r in completion_logs.records if r.name == COMPLETION_LOGGER
        ]
        assert len(records) == 1
        assert records[0].inference_task == "answer"
        assert records[0].vendor == "groq"
        assert records[0].model == "the-answer-model"
        assert records[0].fallback_fired is False
        assert records[0].error_kind is None

    def test_a_fallback_that_fires_is_named_in_the_record(
        self, completion_logs, settings, monkeypatch, embedder, space, client_for
    ):
        """The record's `model` is the one that actually answered, not the
        one configured first -- the same guarantee `last_model_used` gives
        `answers/service.py` (IR-385)."""
        import openai

        rate_limited = RuntimeError("rate limit exceeded")
        vendor = _RecordingVendor(failing={"first-model": rate_limited})
        monkeypatch.setattr(openai, "OpenAI", vendor)

        settings.LLM_ANSWER_MODEL = "first-model"
        settings.LLM_ANSWER_FALLBACK_MODELS = "second-model"
        settings.LLM_ANSWER_API_KEY = "one-account-key"

        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(_root(embedder)):
            ask(client_for(reader), FLOOD_QUESTION)

        records = [
            r for r in completion_logs.records if r.name == COMPLETION_LOGGER
        ]
        assert len(records) == 1
        assert records[0].model == "second-model"
        assert records[0].fallback_fired is True
