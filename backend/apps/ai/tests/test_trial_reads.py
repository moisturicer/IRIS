"""Unstructured reads for IR-1054's strategy comparison, on a database copy."""

import json
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from apps.ai.extraction import ExtractedDocument, Provenance, Usage
from apps.ai.extraction.shaping_unstructured import shape_unstructured
from apps.ai.models.chunk import ChunkSet
from apps.ai.trial_reads import read_records, records_in_question_set
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record
from core.enums import PipelineStatus

FIXTURE = (Path(__file__).resolve().parents[1] / "extraction" / "tests" / "fixtures"
           / "unstructured_platform" / "numbered_headings" / "result.json")


class FakeUnstructured:
    leaves_campus = True

    def __init__(self, pages=2):
        self.sent = []
        self.pages = pages

    def extract(self, pdf_bytes, *, filename):
        self.sent.append(filename)
        raw = {"elements": json.loads(FIXTURE.read_text(encoding="utf-8"))}
        return ExtractedDocument(
            document=shape_unstructured(raw),
            provenance=Provenance(name="unstructured", version="v0"),
            usage=Usage(pages=self.pages), raw=raw,
        )


def _record(title, *, released=True, extractor="docling"):
    record = Record.objects.create(
        title=title, abstract="An abstract.", is_ip=False, ai_consent=released,
        pipeline_status=PipelineStatus.PUBLISHED, is_embargoed=False,
        embargo_released_at=timezone.now(),
    )
    PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, status="done", extractor=extractor,
        structure={"version": 1, "elements": []}, content_hash=f"old-{title}",
    )
    ChunkSet.objects.create(record=record, extraction_hash=f"old-{title}", strategy_id="s",
                            options={}, content_hash="live", is_active=True)
    return record


def _read(ids, extractor, **kwargs):
    kwargs.setdefault("crop", lambda pdf, document: [])
    return read_records(ids, extractor=extractor, load=lambda e: b"%PDF-", evidence=lambda b: {},
                        **kwargs)


@pytest.mark.django_db
def test_a_read_replaces_the_stored_extraction_and_leaves_the_live_set_alone():
    record = _record("Paper")
    extractor = FakeUnstructured(pages=7)
    outcome = _read([record.pk], extractor)
    row = PdfExtraction.objects.get(record=record)
    assert row.extractor == "unstructured" and row.pages_read == 7
    assert row.structure["elements"] and row.raw_result["elements"]
    assert row.content_hash != "old-Paper"
    assert outcome.pages == 7 and outcome.read == [record.pk]
    assert ChunkSet.objects.get(record=record, is_active=True).content_hash == "live"


@pytest.mark.django_db
def test_a_paper_already_read_by_unstructured_is_not_paid_for_twice():
    record = _record("Done", extractor="unstructured")
    extractor = FakeUnstructured()
    outcome = _read([record.pk], extractor)
    assert extractor.sent == [] and outcome.pages == 0
    assert outcome.skipped == {record.pk: "already read by Unstructured"}


@pytest.mark.django_db
def test_a_paper_the_disclosure_gate_refuses_is_never_sent():
    record = _record("Held", released=False)
    extractor = FakeUnstructured()
    outcome = _read([record.pk], extractor)
    assert extractor.sent == []
    assert outcome.skipped == {record.pk: "disclosure refused"}
    assert PdfExtraction.objects.get(record=record).extractor == "docling"


@pytest.mark.django_db
def test_a_limit_stops_after_that_many_paid_reads():
    records = [_record(f"P{i}") for i in range(3)]
    extractor = FakeUnstructured()
    outcome = _read([r.pk for r in records], extractor, limit=2)
    assert len(extractor.sent) == 2 and outcome.read == [records[0].pk, records[1].pk]


@pytest.mark.django_db
def test_a_question_set_names_the_papers_its_labels_and_scopes_point_at(tmp_path):
    a, b, _ = _record("Alpha"), _record("Beta"), _record("Gamma")
    path = tmp_path / "set.json"
    path.write_text(json.dumps({"questions": [
        {"id": "q1", "expected": [{"record": "Alpha", "page": 1, "quote": "x"}]},
        {"id": "q2", "scope_record": "Beta", "expected": []},
    ]}), encoding="utf-8")
    assert records_in_question_set(path) == sorted([a.pk, b.pk])


def _with_figure_and_formula(raw):
    from apps.ai.extraction.tests.test_unstructured_figures import image, png

    formula = {"type": "Formula", "element_id": "eq-1", "text": "x = y",
               "metadata": {"page_number": 1, "coordinates": {
                   "points": [[250, 500], [250, 600], [1000, 600], [1000, 500]],
                   "layout_width": 2125, "layout_height": 2750, "system": "PixelSpace"}}}
    elements = list(raw["elements"])
    elements[3:3] = [image("fig-1", png()), formula]
    return {"elements": elements}


class FakeUnstructuredWithMedia(FakeUnstructured):
    def extract(self, pdf_bytes, *, filename):
        read = super().extract(pdf_bytes, filename=filename)
        raw = _with_figure_and_formula(read.raw)
        return ExtractedDocument(document=shape_unstructured(raw), provenance=read.provenance,
                                 usage=read.usage, raw=raw)


def _crop(pdf_bytes, document):
    from apps.documents import formulas
    from apps.ai.extraction.tests.test_unstructured_figures import png

    return [(target, png()) for target in formulas.targets(document)]


@pytest.mark.django_db
def test_a_read_stores_its_figures_and_formula_crops():
    record = _record("Pictured")
    _read([record.pk], FakeUnstructuredWithMedia(), crop=_crop)
    row = PdfExtraction.objects.get(record=record)
    assert list(row.figures.values_list("name", flat=True)) == ["fig-1"]
    assert list(row.formulas.values_list("name", flat=True)) == ["eq-1"]
    record.refresh_from_db()
    assert record.manuscript_revision is not None
    assert row.source_revision == record.manuscript_revision
    assert {f.source_revision for f in [*row.figures.all(), *row.formulas.all()]} == {row.source_revision}


@pytest.mark.django_db
def test_a_stored_read_gets_its_figures_and_formulas_without_a_second_read():
    from apps.ai.trial_reads import store_media

    record = _record("Stored")
    _read([record.pk], FakeUnstructuredWithMedia(), crop=lambda pdf, document: [])
    row = PdfExtraction.objects.get(record=record)
    row.figures.all().delete()
    stored = store_media([record.pk], load=lambda e: b"%PDF-", crop=_crop)
    assert stored == {record.pk: (1, 1)}
    assert row.figures.count() == 1 and row.formulas.count() == 1


@pytest.mark.django_db
def test_media_is_stored_only_for_unstructured_reads():
    from apps.ai.trial_reads import store_media

    record = _record("Docling")
    assert store_media([record.pk], load=lambda e: b"%PDF-", crop=_crop) == {}


@pytest.mark.django_db
def test_the_command_refuses_without_the_replace_flag():
    with pytest.raises(CommandError, match="--replace-stored-read"):
        call_command("trial_read_unstructured", "--record", "1")


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_the_command_refuses_outside_development():
    with pytest.raises(CommandError, match="DEBUG"):
        call_command("trial_read_unstructured", "--record", "1", "--replace-stored-read")


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_store_media_sends_nothing_and_reports_each_paper(capsys, monkeypatch):
    import apps.ai.trial_reads as trial_reads

    monkeypatch.setattr(trial_reads, "store_media", lambda ids: {ids[0]: (2, 3)})
    monkeypatch.setattr("apps.ai.extraction.selection.unstructured_extractor",
                        lambda: pytest.fail("store-media must not build a reader"))
    call_command("trial_read_unstructured", "--record", "7", "--store-media", "--replace-stored-read")
    assert "record 7: 2 figure(s), 3 formula crop(s)" in capsys.readouterr().out


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_a_dry_run_sends_nothing_and_prices_the_pages(capsys):
    record = _record("Priced")
    call_command("trial_read_unstructured", "--record", str(record.pk), "--dry-run")
    out = capsys.readouterr().out
    assert "would read 1 paper" in out
    assert PdfExtraction.objects.get(record=record).extractor == "docling"
