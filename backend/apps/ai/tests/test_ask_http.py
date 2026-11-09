"""Ask IRIS through the HTTP boundary (IR-283).

The primary seam for this work, and deliberately the highest one available:
what a caller observes is a *response*, so that is what these assert. Which
passages come back, whether one the asker may not read is ever among them,
what the citation carries, and whether the response admits to degrading.

Driven with the deterministic provider fakes, injected through the composition
root. No vendor account, no network — which is the point: these include the
security assertions, and a security test that only runs where a paid API key
is configured is a security test that does not run.

The corpus builders live in `corpus.py` and the fixtures in `conftest.py`, so
the conversation suite drives the same ones (IR-295).
"""

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from core.enums import PipelineStatus

from .corpus import (
    DIMENSIONS,
    FLOOD_TEXT,
    make_record,
    make_user,
    root_with,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _raise_404():
    raise RuntimeError("404 - the model does not exist or you do not have access to it.")


# -- what the interface is told before anyone asks anything -------------------


class StatusTests:
    def test_status_reports_the_active_space_and_that_generation_is_configured(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = client_for(reader).get(reverse("ai-status")).json()

        assert body["embedding_space"]["id"] == space.pk
        assert body["embedding_space"]["model_id"] == space.model_id
        assert body["embedding_space"]["dimensions"] == DIMENSIONS
        assert body["generative"] is True
        assert body["indexed_records"] == 1
        assert "retrieval" not in body, "the hardcoded mode string is gone"

    def test_status_counts_only_records_the_asker_may_read(
        self, embedder, space, client_for
    ):
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        make_record(title="Hidden Draft", text=FLOOD_TEXT, owner=author,
                    status=PipelineStatus.DRAFT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = client_for(stranger).get(reverse("ai-status")).json()

        assert body["indexed_records"] == 0

    def test_status_is_not_generative_once_the_configured_vendor_has_tripped_the_breaker(
        self, settings, client_for
    ):
        """IR-252: a key that is present but pointed at a vendor that keeps
        404ing must not be reported as `generative: true` -- that is exactly
        the shape of the original bug (a withdrawn model id, a key that
        looked fine). `is_configured()` only ever asked "is there a key
        string", so this drives the real (non-injected) composition root,
        trips the breaker IR-321 already keeps for that provider the same way
        `CircuitBreakingLLMProvider` would after five real failures, and
        checks that `/status/` notices."""
        from apps.ai.composition import CompositionRoot
        from apps.ai.inference import InferenceTask
        from apps.ai.resilience.circuit import CircuitState
        from apps.ai.resilience.llm import reset_llm_breakers

        settings.LLM_API_KEY = "present-but-wrong"
        settings.LLM_BASE_URL = "https://example.test/v1"
        settings.LLM_MODEL = "a-withdrawn-model"

        reset_llm_breakers()
        try:
            # Same registry key `generation_configured()` will look up, via
            # the same path `test_composition_llm.py` uses to reach a
            # breaker: building the real (non-fake) provider stack, which
            # reaches no network until `generate()` is called. `answer`
            # inherits the flat settings above, so this is the same provider
            # `generation_configured()` checks. One level in: `llm_for` wraps
            # the resilient provider in `CompletionLoggingLLMProvider`
            # (IR-387), the completion-record decorator, not the breaker.
            breaker = CompositionRoot().llm_for(InferenceTask.ANSWER)._provider._breaker  # noqa: SLF001
            for _ in range(5):
                with pytest.raises(RuntimeError):
                    breaker.call(_raise_404)
            assert breaker.state is CircuitState.OPEN

            reader = make_user("reader@cit.edu")
            with use_composition_root(CompositionRoot()):
                body = client_for(reader).get(reverse("ai-status")).json()

            assert body["generative"] is False
        finally:
            reset_llm_breakers()


class CompositionRootTests:
    def test_the_default_root_is_restored_after_an_override(self, embedder):
        from apps.ai.composition import composition_root

        with use_composition_root(root_with(embedder=embedder)) as fake:
            assert composition_root() is fake

        # Back to a root that is not the fake, so the next caller gets the
        # real adapters rather than whichever fake a test left behind.
        assert composition_root() is not fake

    def test_an_override_is_undone_even_when_the_block_raises(self, embedder):
        from apps.ai.composition import composition_root

        fake = root_with(embedder=embedder)
        with pytest.raises(RuntimeError):
            with use_composition_root(fake):
                raise RuntimeError("boom")

        assert composition_root() is not fake
