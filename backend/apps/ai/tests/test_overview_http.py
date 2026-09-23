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
