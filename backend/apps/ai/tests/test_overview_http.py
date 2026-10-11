"""GET /api/v1/ai/records/<id>/overview/ (IR-334).

`PaperAiOverview` used to fire `/ai/ask/` on every mount -- a paid vendor
call on every page view, for an answer that cannot change until the record is
re-chunked. This is the endpoint that replaced it, and the tests pin down the
one property that motivated it: the vendor is called once, not once per view.
"""

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.models import ChunkSet, RecordOverview
from apps.ai.providers.fakes import ScriptedLLM
from core.enums import PipelineStatus

from .corpus import FLOOD_TEXT, make_record, make_user, root_with

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _overview(client, record_id):
    return client.get(reverse("ai-record-overview", args=[record_id]))


class GeneratedOnceAndCachedTests:
    def test_two_reads_produce_one_vendor_call(self, embedder, space, client_for):
        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        llm = ScriptedLLM(reply="A methodology summary [1].")
        client = client_for(reader)

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            first = _overview(client, record.pk)
            second = _overview(client, record.pk)

        assert first.status_code == second.status_code == 200
        assert len(llm.calls) == 1
        assert first.json()["overview"]["text"] == second.json()["overview"]["text"]

    def test_a_row_is_persisted_after_the_first_read(self, embedder, space, client_for):
        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )

        with use_composition_root(root_with(embedder=embedder)):
            _overview(client_for(reader), record.pk)

        assert RecordOverview.objects.filter(record=record).exists()

    def test_the_second_read_reports_it_came_from_cache(self, embedder, space, client_for):
        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        client = client_for(reader)

        with use_composition_root(root_with(embedder=embedder)):
            first = _overview(client, record.pk)
            second = _overview(client, record.pk)

        assert first.json()["cached"] is False
        assert second.json()["cached"] is True


class InvalidationTests:
    def test_re_chunking_the_record_invalidates_the_cached_row(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        llm = ScriptedLLM(reply="First summary [1].")
        client = client_for(reader)

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            _overview(client, record.pk)

        # A re-chunk: the active set's hash changes underneath the cached row.
        ChunkSet.objects.filter(record=record, is_active=True).update(
            content_hash="a-new-hash-after-rechunking"
        )

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            _overview(client, record.pk)

        assert len(llm.calls) == 2

    def test_a_record_with_no_chunk_set_reports_not_indexed(
        self, embedder, space, client_for
    ):
        from apps.records.models import Record

        reader = make_user("reader@cit.edu")
        record = Record.objects.create(
            title="Unextracted", abstract="No chunks yet.",
            pipeline_status=PipelineStatus.PUBLISHED,
        )

        with use_composition_root(root_with(embedder=embedder)):
            response = _overview(client_for(reader), record.pk)

        assert response.json() == {"state": "not_indexed", "overview": None}


class UnavailableIsNeverCachedTests:
    def test_an_unavailable_model_is_not_stored(self, embedder, space, client_for):
        from apps.ai.tests.corpus import _BrokenLLM

        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )

        with use_composition_root(root_with(embedder=embedder, llm=_BrokenLLM())):
            response = _overview(client_for(reader), record.pk)

        assert response.json()["state"] == "unavailable"
        assert not RecordOverview.objects.filter(record=record).exists()

    def test_the_next_view_tries_again_once_the_model_is_back(
        self, embedder, space, client_for
    ):
        from apps.ai.tests.corpus import _BrokenLLM

        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        client = client_for(reader)

        with use_composition_root(root_with(embedder=embedder, llm=_BrokenLLM())):
            _overview(client, record.pk)

        with use_composition_root(root_with(embedder=embedder)):
            response = _overview(client, record.pk)

        assert response.json()["state"] == "ready"


class SummaryRunsAsItsOwnInferenceTaskTests:
    """IR-380: the overview stops borrowing the answer path's model.

    Driven through the endpoint rather than at `overview_for`, because the
    property that matters is which model a page view actually reaches.
    """

    @pytest.fixture
    def built_configs(self, monkeypatch):
        """The `LLMProviderConfig`s each `build_profile_llm` call produced.

        A root with no injected provider resolves a Profile for real; only the
        last step -- wrapping the configs in adapters that would open a socket
        -- is replaced.
        """
        from apps.ai.inference import providers as inference_providers

        captured = []

        def _capture(configs, breaker_key):
            captured.extend(configs)
            return ScriptedLLM(reply="A methodology summary [1].")

        monkeypatch.setattr(
            inference_providers, "build_task_llm", _capture
        )
        return captured

    def _profiled_root(self, embedder):
        from apps.ai.composition import CompositionRoot
        from apps.ai.providers.fakes import ScriptedReranker

        return CompositionRoot(
            embedder=embedder,
            reranker=ScriptedReranker(),
            permits=lambda record: True,
        )

    def test_the_overview_reaches_the_summary_model_not_the_answer_one(
        self, embedder, space, client_for, settings, built_configs
    ):
        settings.LLM_ANSWER_MODEL = "answer-model"
        settings.LLM_ANSWER_API_KEY = "k"
        settings.LLM_SUMMARY_MODEL = "summary-model"
        settings.LLM_SUMMARY_API_KEY = "k"

        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )

        with use_composition_root(self._profiled_root(embedder)):
            response = _overview(client_for(make_user("reader@cit.edu")), record.pk)

        assert response.status_code == 200
        assert [config.model for config in built_configs] == ["summary-model"]

    def test_the_summary_request_carries_no_reasoning_configuration(
        self, embedder, space, client_for, settings, built_configs
    ):
        settings.LLM_SUMMARY_MODEL = "summary-model"
        settings.LLM_SUMMARY_API_KEY = "k"
        settings.LLM_SUMMARY_REASONING = False
        settings.LLM_REASONING_EFFORT = "high"

        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )

        with use_composition_root(self._profiled_root(embedder)):
            _overview(client_for(make_user("reader@cit.edu")), record.pk)

        assert [config.reasoning_effort for config in built_configs] == [""]

    def test_an_unconfigured_summary_task_is_unavailable_not_an_error(
        self, embedder, space, client_for, settings, built_configs
    ):
        """No `LLM_SUMMARY_MODEL` switches the overview off, rather than
        falling through to the answer model (ADR-036's no-silent-fall-through
        rule). The same state an outage produces, and stored no more than it.

        `answer` is left configured and its provider would have answered
        happily, so a summary that borrowed it would read `ready` here."""
        settings.LLM_MODEL = "flat-model"
        settings.LLM_API_KEY = "k"
        settings.LLM_SUMMARY_MODEL = ""

        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )

        with use_composition_root(self._profiled_root(embedder)):
            response = _overview(client_for(make_user("reader@cit.edu")), record.pk)

        assert response.status_code == 200
        assert response.json()["state"] == "unavailable"
        assert built_configs == []
        assert not RecordOverview.objects.filter(record=record).exists()


class OversizedPaperTests:
    """IR-432: a paper over the token ceiling says so and costs nothing."""

    def _shrink_ceiling(self, record, settings):
        from django.db.models import Sum

        total = ChunkSet.objects.get(record=record, is_active=True).chunks.aggregate(
            t=Sum("token_count")
        )["t"]
        assert total > 1
        return total

    def test_a_paper_over_the_ceiling_is_unavailable_with_a_reason_and_no_call(
        self, embedder, space, client_for, settings
    ):
        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        settings.AI_OVERVIEW_TOKEN_CEILING = self._shrink_ceiling(record, settings) - 1
        llm = ScriptedLLM(reply="A methodology summary [1].")

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            body = _overview(client_for(reader), record.pk).json()

        assert body["state"] == "unavailable"
        assert body["overview"] is None
        assert body["reason"] == "too_large"
        assert llm.calls == []
        assert not RecordOverview.objects.filter(record=record).exists()

    def test_a_paper_at_the_ceiling_is_still_summarised(
        self, embedder, space, client_for, settings
    ):
        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        settings.AI_OVERVIEW_TOKEN_CEILING = self._shrink_ceiling(record, settings)

        with use_composition_root(root_with(embedder=embedder)):
            body = _overview(client_for(reader), record.pk).json()

        assert body["state"] == "ready"

    def test_zero_disables_the_ceiling(self, embedder, space, client_for, settings):
        reader = make_user("reader@cit.edu")
        record = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        settings.AI_OVERVIEW_TOKEN_CEILING = 0

        with use_composition_root(root_with(embedder=embedder)):
            body = _overview(client_for(reader), record.pk).json()

        assert body["state"] == "ready"


class VisibilityTests:
    def test_a_reader_without_access_gets_404(self, embedder, space, client_for):
        owner = make_user("owner@cit.edu")
        stranger = make_user("stranger@cit.edu")
        record = make_record(
            title="Private Draft", text=FLOOD_TEXT, embedder=embedder, space=space,
            status=PipelineStatus.DRAFT, owner=owner,
        )

        with use_composition_root(root_with(embedder=embedder)):
            response = _overview(client_for(stranger), record.pk)

        assert response.status_code == 404
