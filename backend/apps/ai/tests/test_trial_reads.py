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
def test_a_dry_run_sends_nothing_and_prices_the_pages(capsys):
    record = _record("Priced")
    call_command("trial_read_unstructured", "--record", str(record.pk), "--dry-run")
    out = capsys.readouterr().out
    assert "would read 1 paper" in out
    assert PdfExtraction.objects.get(record=record).extractor == "docling"
