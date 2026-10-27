"""IR-595: nested blobs, run reasons, capacity and latest_run go through allowlists."""
import json

import pytest
from django.urls import reverse

from apps.ai import public
from apps.ai.models import AskRun, DocumentChunk, AskRunEvent, Conversation, Turn
from apps.ai.models.queued import FAILED

from .corpus import FLOOD_TEXT, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

PUBLIC = "public-1"
SECRETS = ("model_calls", "prompt_tokens_estimated", "stage_ms", "cache_hits", "weights-v7",
           "source_versions", "content_hash", "trace_id", "internal_note", "\"method\":", "\"version\":")


def chunk_of(record):
    return DocumentChunk.objects.filter(record=record).values_list("pk", flat=True).first()


def listing_blob(record_id, chunk_id=1):
    return {
        "completeness": "partial", "wording": "Screened 1 candidate paper.",
        "records": [{"record_id": record_id, "title": "T", "trace_id": "x"}],
        "candidates": [{"record_id": record_id, "title": "T", "state": "included",
                        "quote": "gauge data",
                        "source": {"field": "passage", "page": 4, "chunk_id": chunk_id, "trace_id": "x"}}],
        "coverage": {"limit": 20, "selected": 1, "included": 1, "excluded": 0, "uncertain": 0,
                     "unassessed": 0, "more_available": False, "search_degraded": False,
                     "changed": False, "internal_note": "x"},
        "topic_count": {"criterion": "flood", "method": "weights-v7", "version": "v1",
                        "basis": "b", "matches": 1, "assessed": 1, "excluded": 0, "uncertain": 0,
                        "unassessed": 0, "selected": 1, "limit": 20, "more_available": False},
        "observed": {"model_calls": 3, "prompt_tokens_estimated": 900, "cache_hits": 1,
                     "stage_ms": {"screen": 40}},
    }


def comparison_blob():
    return {
        "records": [{"record_id": 1, "title": "T", "trace_id": "x"}],
        "rows": [{"dimension": "method", "label": "Method", "internal_note": "x", "cells": [
            {"record_id": 1, "state": "reported", "internal_note": "x", "values": [
                {"value": "CNN", "citations": [
                    {"page": 4, "quote": "q", "chunk_id": 9, "marker": 1, "content_hash": "h"}]}]}]}],
        "coverage": [{"record_id": 1, "title": "T", "state": "read_fully", "reason": "detail_unavailable"}],
        "removed_claims": 0, "source_versions": [{"content_hash": "h"}],
    }


def test_nested_blobs_are_projected_through_allowlists():
    body = {"answer": "A", "mode": "generative", "listing": listing_blob(1),
            "comparison": comparison_blob(),
            "sources": [{"id": 1, "title": "T", "score": 0.5, "internal_note": "x"}],
            "citations": [{"marker": 1, "record_id": 1, "chunk_id": 2, "trace_id": "x"}]}
    for shaped in (public.project_done(body), public.project_turn(body)):
        published = json.dumps(shaped)
        assert not any(secret in published for secret in SECRETS)
        assert shaped["listing"]["candidates"][0]["source"] == {
            "field": "passage", "page": 4, "chunk_id": 1}
        assert shaped["listing"]["topic_count"]["criterion"] == "flood"
        assert shaped["comparison"]["rows"][0]["cells"][0]["values"][0]["citations"][0]["quote"] == "q"
        assert shaped["comparison"]["coverage"] == [
            {"record_id": 1, "title": "T", "state": "read_fully"}]


def test_a_reopened_listing_turn_carries_no_observed_figures_or_method(client_for, embedder, space):
    reader = make_user("listing@cit.edu")
    record = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    Turn.objects.create(conversation=conversation, question="List flood papers", answer="x",
                        state="generated", listing=listing_blob(record.pk, chunk_of(record)))
    client = client_for(reader)
    url = reverse("ai-conversation-detail", args=[conversation.pk])

    legacy = json.dumps(client.get(url).json())
    shown = json.dumps(client.get(url, {"protocol": PUBLIC}).json())

    assert "model_calls" in legacy
    # The code-owned wording names the method as prose; only fields are withheld.
    assert not any(s in shown for s in SECRETS if s != "weights-v7")
    assert "1 match among" in shown


def test_run_reasons_are_kept_only_from_the_fixed_codes():
    kept = public.StreamProjector().feed("run_failed", {"run_id": "r", "state": "failed", "reason": "no_answer"})
    odd = public.StreamProjector().feed("run_failed", {"run_id": "r", "state": "failed", "reason": "Traceback: boom"})
    assert kept[0][1]["reason"] == "no_answer"
    assert "reason" not in odd[0][1]


def test_capacity_limiting_is_a_detail_free_waiting_signal():
    frames = public.StreamProjector(public.THINKING).feed(
        "capacity_limited", {"status": "busy", "reasons": ["campaign_ceiling"]})
    assert frames == [("activity", public.activity(public.WAITING))]


def test_latest_run_is_allowlisted_under_the_public_protocol(client_for):
    reader = make_user("latest@cit.edu")
    conversation = Conversation.objects.create(user=reader)
    run = AskRun.objects.create(
        user=reader, conversation=conversation, state=FAILED, end_reason="Traceback: boom",
        request={"question": "Q?", "secret": "s"}, deadline_at="2030-01-01T00:00:00Z")
    AskRunEvent.objects.create(run=run, sequence=1, name="run_queued", data={})
    client = client_for(reader)
    url = reverse("ai-conversation-detail", args=[conversation.pk])

    shown = client.get(url, {"protocol": PUBLIC}).json()["latest_run"]

    assert set(shown) <= {"id", "state", "end_reason", "question", "retry_of", "last_sequence"}
    assert shown["id"] == str(run.pk) and shown["state"] == FAILED
    assert "end_reason" not in shown
    assert "Traceback" not in json.dumps(shown)
