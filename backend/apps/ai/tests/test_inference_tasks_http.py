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

from apps.ai.composition import CompositionRoot
from apps.ai.inference import InferenceTask
from apps.ai.inference.completions import LOGGER_NAME as COMPLETION_LOGGER
from apps.ai.providers.fakes import ScriptedReranker
from apps.ai.resilience.llm import reset_llm_breakers


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
    logged under it never reach the root logger caplog captures at by
    default.

    This toggles `apps`'s own propagation back on for the test rather than
    attaching `caplog.handler` directly to the completion logger (the older
    fixture shape `apps/ai/answers/tests/test_service.py`'s `service_logs`
    uses): pytest 9 changed `caplog` to auto-attach its handler to every
    *non-propagating* logger it finds -- `apps` included -- specifically to
    fix this exact problem, so a manual attachment here would
    double-deliver every record under pytest 9 while still being required
    for pytest 8, which has no such fix. Restoring propagation instead
    works unchanged on both: the record reaches root -- where caplog
    always attaches -- exactly once either way. A caller reads
    `caplog.records` as usual once the test body has run.
    """
    apps_logger = logging.getLogger("apps")
    original_propagate = apps_logger.propagate
    apps_logger.propagate = True
    caplog.set_level(logging.INFO, logger=COMPLETION_LOGGER)
    try:
        yield caplog
    finally:
        apps_logger.propagate = original_propagate


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
    def test_an_injected_fake_bypasses_profile_resolution_entirely(self):
        from apps.ai.providers.fakes import ScriptedLLM

        fake = ScriptedLLM()
        root = CompositionRoot(llm=fake)
        assert root.llm_for(InferenceTask.ANSWER) is fake
        assert root.llm_for("summary") is fake

    def test_asking_for_one_task_first_does_not_make_another_configured(
        self, settings
    ):
        """Each task's provider is cached under its own key in
        `_task_llms` -- resolving `answer` first must not make an
        unconfigured `summary` raise anything other than its own refusal.
        """
        from apps.ai.providers.openai_compatible import LLMUnavailable

        settings.LLM_API_KEY = "k"
        settings.LLM_SUMMARY_MODEL = ""
        root = CompositionRoot()

        root.llm_for(InferenceTask.ANSWER)

        with pytest.raises(LLMUnavailable):
            root.llm_for(InferenceTask.SUMMARY)

    def test_an_unknown_task_name_is_refused_by_the_root(self):
        from apps.ai.inference import UnknownInferenceTask

        with pytest.raises(UnknownInferenceTask):
            CompositionRoot().llm_for("answers")

