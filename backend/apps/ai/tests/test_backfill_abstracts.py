"""IR-703: a record with no abstract takes one from its own manuscript."""
from io import StringIO

import pytest
from django.core.management import call_command

from apps.ai.abstracts import abstract_from
from apps.ai.models import ChunkSet, DocumentChunk
from apps.records.models import Record

ABSTRACT = ("We study flood prediction from river gauges. A sequence model forecasts water "
            "levels six hours ahead and beats the persistence baseline on every station. "
            "Errors grow with lead time but stay under ten centimetres. ")


def test_a_section_headed_abstract_is_taken_whole():
    chunks = [(["Flood"], "Flood Forecasting Jane Doe University"),
              (["Flood", "Abstract"], "Abstract " + ABSTRACT),
              (["Flood", "1. Introduction"], "1. Introduction Floods are costly.")]
    assert abstract_from(chunks) == ABSTRACT.strip()


def test_an_inline_abstract_drops_its_keywords():
    chunks = [(["Flood"], "Flood Forecasting Jane Doe ABSTRACT " + ABSTRACT
               + "Index Terms-flood, forecasting")]
    assert abstract_from(chunks) == ABSTRACT.strip()


def test_a_dated_front_matter_abstract_ends_at_its_last_full_sentence():
    chunks = [(["Flood"], "Flood Forecasting Jane Doe (Dated: May 1, 2026) " + ABSTRACT
               + "The model is cut off mid")]
    assert abstract_from(chunks) == ABSTRACT.strip()


def test_no_recognisable_abstract_gives_none():
    assert abstract_from([(["Flood"], "Flood Forecasting. Chapter one begins here.")]) is None
    assert abstract_from([(["Flood", "Abstract"], "Abstract Too short.")]) is None


@pytest.mark.db_required
@pytest.mark.django_db
def test_backfill_fills_only_empty_abstracts_and_dry_run_writes_nothing(settings):
    settings.DEBUG = True
    empty = Record.objects.create(title="Flood", abstract="")
    kept = Record.objects.create(title="Kept", abstract="Written by the author.")
    for record in (empty, kept):
        chunk_set = ChunkSet.objects.create(record=record, extraction_hash="e", strategy_id="s",
                                            options={}, content_hash=f"c{record.pk}", is_active=True)
        DocumentChunk.objects.create(chunk_set=chunk_set, record=record, sequence=0, max_sequence=0,
                                     text="Abstract " + ABSTRACT, content="Abstract " + ABSTRACT,
                                     context_path=[record.title, "Abstract"], token_count=30,
                                     text_hash=f"t{record.pk}", source_page=1)

    call_command("backfill_abstracts", "--dry-run", stdout=StringIO())
    assert Record.objects.get(pk=empty.pk).abstract == ""

    out = StringIO()
    call_command("backfill_abstracts", stdout=out)
    assert Record.objects.get(pk=empty.pk).abstract == ABSTRACT.strip()
    assert Record.objects.get(pk=kept.pk).abstract == "Written by the author."
    assert "1 abstract(s) written" in out.getvalue()


@pytest.mark.db_required
@pytest.mark.django_db
def test_backfill_can_be_limited_to_named_classifications(settings):
    from apps.records.models import Classification

    settings.DEBUG = True
    other = Record.objects.create(title="Other", abstract="",
                                  classification=Classification.objects.create(name="other"))
    chunk_set = ChunkSet.objects.create(record=other, extraction_hash="e", strategy_id="s",
                                        options={}, content_hash="c", is_active=True)
    DocumentChunk.objects.create(chunk_set=chunk_set, record=other, sequence=0, max_sequence=0,
                                 text="Abstract " + ABSTRACT, content="Abstract " + ABSTRACT,
                                 context_path=["Other", "Abstract"], token_count=30,
                                 text_hash="t", source_page=1)
    call_command("backfill_abstracts", "--classification", "proxy", stdout=StringIO())
    assert Record.objects.get(pk=other.pk).abstract == ""
