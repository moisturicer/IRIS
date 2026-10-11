"""IR-436: visibility and per-record disclosure at the overview HTTP boundary."""

from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import RecordOverview
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from core.enums import PipelineStatus

from .corpus import FLOOD_TEXT, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _get(client, record_id):
    return client.get(reverse("ai-record-overview", args=[record_id]))


def _root(embedder, llm, permits):
    return CompositionRoot(
        embedder=embedder, reranker=ScriptedReranker(),
        llm=llm, permits=permits,
    )


def test_draft_owner_can_read_overview(embedder, space, client_for):
    owner = make_user("overview-owner@cit.edu")
    record = make_record(
        title="Private Flood Draft", text=FLOOD_TEXT, embedder=embedder,
        space=space, status=PipelineStatus.DRAFT, owner=owner,
    )
    llm = ScriptedLLM(reply="The study uses rainfall gauges [p. 4].")

    with use_composition_root(_root(embedder, llm, lambda record: True)):
        response = _get(client_for(owner), record.pk)

    assert response.status_code == 200
    assert response.json()["state"] == "ready"
    assert len(llm.calls) == 1


def test_invisible_cached_record_is_identical_to_missing_and_calls_no_model(
    embedder, space, client_for,
):
    owner = make_user("cached-owner@cit.edu")
    stranger = make_user("cached-stranger@cit.edu")
    record = make_record(
        title="Cached Private Draft", text=FLOOD_TEXT, embedder=embedder,
        space=space, status=PipelineStatus.DRAFT, owner=owner,
    )
    llm = ScriptedLLM(reply="The study uses rainfall gauges [p. 4].")
    with use_composition_root(_root(embedder, llm, lambda record: True)):
        assert _get(client_for(owner), record.pk).json()["state"] == "ready"
    assert RecordOverview.objects.filter(record=record).exists()
    llm.calls.clear()

    with use_composition_root(_root(embedder, llm, lambda record: True)):
        invisible = _get(client_for(stranger), record.pk)
        missing = _get(client_for(stranger), record.pk + 1000000)

    assert invisible.status_code == missing.status_code == 404
    assert invisible.json() == missing.json()
    assert llm.calls == []


def test_disclosure_refusal_precedes_assembly_and_stores_nothing(
    embedder, space, client_for,
):
    reader = make_user("refused-reader@cit.edu")
    record = make_record(
        title="Refused Paper", text=FLOOD_TEXT, embedder=embedder, space=space,
    )
    llm = ScriptedLLM(reply="The study uses rainfall gauges [p. 4].")
    checked = []

    def refuse(candidate):
        checked.append(candidate.pk)
        return False

    with use_composition_root(_root(embedder, llm, refuse)):
        with patch("apps.ai.overview.service.whole_paper", side_effect=AssertionError("assembled")):
            response = _get(client_for(reader), record.pk)

    assert response.status_code == 200
    assert response.json() == {"state": "unavailable", "overview": None}
    assert checked == [record.pk]
    assert llm.calls == []
    assert not RecordOverview.objects.filter(record=record).exists()


def test_disclosure_refusal_hides_cached_overview(
    embedder, space, client_for,
):
    reader = make_user("cache-reader@cit.edu")
    record = make_record(
        title="Later Refused Paper", text=FLOOD_TEXT, embedder=embedder, space=space,
    )
    llm = ScriptedLLM(reply="The study uses rainfall gauges [p. 4].")
    client = client_for(reader)
    with use_composition_root(_root(embedder, llm, lambda record: True)):
        assert _get(client, record.pk).json()["state"] == "ready"
    stored = RecordOverview.objects.get(record=record)
    llm.calls.clear()

    with use_composition_root(_root(embedder, llm, lambda record: False)):
        with patch("apps.ai.overview.service.whole_paper", side_effect=AssertionError("assembled")):
            response = _get(client, record.pk)

    assert response.json() == {"state": "unavailable", "overview": None}
    assert llm.calls == []
    assert RecordOverview.objects.get(record=record).pk == stored.pk


def test_two_readers_share_one_stored_row_and_one_model_call(
    embedder, space, client_for,
):
    first_reader = make_user("first-reader@cit.edu")
    second_reader = make_user("second-reader@cit.edu")
    record = make_record(
        title="Shared Paper", text=FLOOD_TEXT, embedder=embedder, space=space,
    )
    llm = ScriptedLLM(reply="The study uses rainfall gauges [p. 4].")

    with use_composition_root(_root(embedder, llm, lambda record: True)):
        first = _get(client_for(first_reader), record.pk)
        stored = RecordOverview.objects.get(record=record)
        row_id, generated_at = stored.pk, stored.updated_at
        second = _get(client_for(second_reader), record.pk)

    assert first.status_code == second.status_code == 200
    assert first.json()["overview"] == second.json()["overview"]
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert len(llm.calls) == 1
    assert RecordOverview.objects.filter(record=record).count() == 1
    assert RecordOverview.objects.get(record=record).pk == row_id
    assert RecordOverview.objects.get(record=record).updated_at == generated_at
