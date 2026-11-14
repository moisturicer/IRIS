"""Unstructured reads of the corpus for IR-1054, before the IR-988 cutover.

Each read replaces the paper's stored extraction, so trial chunk sets
(`apps.ai.trials`) can be built from it with extractor ``unstructured``.
The live chunk set is left alone. Meant for a database copy: on a shared
dev database it would leave live chunks pointing at a replaced read.

Shaping is re-run with IRIS's own PDF evidence (IR-1053, IR-1057).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable, Optional

#: ADR-067's IR-984 amendment: $0.015 a page for hi_res. An estimate only.
USD_PER_PAGE = Decimal("0.015")

ALREADY_READ = "already read by Unstructured"
REFUSED = "disclosure refused"
NO_EXTRACTION = "no manuscript extraction"


@dataclass
class ReadOutcome:
    read: list[int] = field(default_factory=list)
    skipped: dict[int, str] = field(default_factory=dict)
    failed: dict[int, str] = field(default_factory=dict)
    pages: int = 0


def records_in_question_set(path: Path) -> list[int]:
    """The papers a question set's labels and scopes name, by title."""
    from apps.records.models import Record

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    titles = set()
    for question in data.get("questions", data):
        scope = question.get("scope_record")
        if isinstance(scope, str):
            titles.add(scope)
        for label in question.get("expected") or []:
            if isinstance(label, dict) and label.get("record"):
                titles.add(label["record"])
    return sorted(Record.objects.filter(title__in=titles).values_list("pk", flat=True))


def _manuscript_bytes(extraction) -> bytes:
    field_file = extraction.record.abstract_file
    with field_file.storage.open(extraction.source_file or field_file.name, "rb") as source:
        return source.read()


def _evidence(pdf_bytes: bytes) -> dict:
    from apps.documents.pdf_evidence import sandbox

    return sandbox.read_pdf_evidence(pdf_bytes)


def _crop(pdf_bytes: bytes, document) -> list:
    from apps.documents import formulas

    return formulas.crop(pdf_bytes, document)


def _give_revision(extraction) -> None:
    """A corpus-loaded paper has no manuscript revision, which Figures, Formulas
    and their transcription are keyed on: give it one, as an accepted upload would."""
    import uuid

    from apps.documents.models import PdfExtraction
    from apps.records.models import Record

    revision = Record.objects.filter(pk=extraction.record_id).values_list(
        "manuscript_revision", flat=True).first()
    if revision is None:
        revision = uuid.uuid4()
        Record.objects.filter(pk=extraction.record_id).update(manuscript_revision=revision)
    PdfExtraction.objects.filter(pk=extraction.pk).update(source_revision=revision)


def _store_media(extraction, document, raw: dict, pdf_bytes: bytes, crop: Callable) -> tuple[int, int]:
    """Figures and formula crops for the stored read, as extraction stores them (IR-987, IR-1102)."""
    from django.conf import settings

    from apps.ai.extraction.unstructured_client import _figures
    from apps.documents import formulas
    from apps.documents.figures import replace_figures

    _give_revision(extraction)
    extraction.refresh_from_db()
    figures = _figures(raw.get("elements") or [], document,
                       settings.UNSTRUCTURED_MAX_FIGURES, settings.UNSTRUCTURED_MAX_FIGURE_PIXELS)
    replace_figures(extraction, figures)
    formulas.replace_formulas(extraction, crop(pdf_bytes, document))
    return extraction.figures.count(), extraction.formulas.count()


def _store(extraction, extracted, evidence: dict, pdf_bytes: bytes, crop: Callable) -> None:
    from django.utils import timezone

    from apps.ai.extraction import document_to_json, extraction_hash, flatten_for_search
    from apps.ai.extraction.shaping_unstructured import shape_unstructured
    from apps.documents.models import PdfExtraction

    document = shape_unstructured(extracted.raw, evidence or None)
    # update(), not save(): no signal may queue a re-chunk of the live set.
    PdfExtraction.objects.filter(pk=extraction.pk).update(
        extracted_text=flatten_for_search(document),
        structure=document_to_json(document),
        content_hash=extraction_hash(document),
        extractor=extracted.provenance.name,
        extractor_version=extracted.provenance.version,
        extractor_options=dict(extracted.provenance.options),
        raw_result=dict(extracted.raw),
        pdf_evidence=evidence,
        pages_read=extracted.usage.pages if extracted.usage else None,
        credits=extracted.usage.credits if extracted.usage else None,
        completed_at=timezone.now(),
    )
    _store_media(extraction, document, dict(extracted.raw), pdf_bytes, crop)


def store_media(
    record_ids: Iterable[int],
    *,
    load: Callable = _manuscript_bytes,
    crop: Callable = _crop,
) -> dict[int, tuple[int, int]]:
    """``(figures, formulas)`` stored for each paper already read by Unstructured,
    from its stored read and PDF. Nothing is sent to Unstructured."""
    from apps.ai.extraction import document_from_json
    from apps.documents.models import DocumentKind, PdfExtraction

    stored = {}
    for extraction in PdfExtraction.objects.filter(
            record_id__in=list(record_ids), kind=DocumentKind.MANUSCRIPT, extractor="unstructured"):
        document = document_from_json(extraction.structure)
        stored[extraction.record_id] = _store_media(
            extraction, document, extraction.raw_result or {}, load(extraction), crop)
    return stored


def read_records(
    record_ids: Iterable[int],
    *,
    extractor,
    limit: Optional[int] = None,
    load: Callable = _manuscript_bytes,
    evidence: Callable[[bytes], dict] = _evidence,
    crop: Callable = _crop,
    report: Callable[[str], None] = lambda line: None,
) -> ReadOutcome:
    """Read each paper with ``extractor``; at most ``limit`` paid reads."""
    from apps.ai.extraction.gate import permits
    from apps.documents.models import DocumentKind, PdfExtraction

    outcome = ReadOutcome()
    for record_id in record_ids:
        if limit is not None and len(outcome.read) >= limit:
            break
        extraction = (PdfExtraction.objects.select_related("record")
                      .filter(record_id=record_id, kind=DocumentKind.MANUSCRIPT).first())
        if extraction is None:
            outcome.skipped[record_id] = NO_EXTRACTION
            continue
        if extraction.extractor == "unstructured":
            outcome.skipped[record_id] = ALREADY_READ
            continue
        if not permits(extraction.record):
            outcome.skipped[record_id] = REFUSED
            continue
        try:
            pdf_bytes = load(extraction)
            extracted = extractor.extract(
                pdf_bytes, filename=os.path.basename(extraction.source_file or f"{record_id}.pdf"))
        except Exception as exc:  # one bad paper should not sink the run
            outcome.failed[record_id] = f"{type(exc).__name__}: {exc}"
            report(f"  record {record_id}: failed ({type(exc).__name__})")
            continue
        _store(extraction, extracted, evidence(pdf_bytes), pdf_bytes, crop)
        pages = extracted.usage.pages if extracted.usage else 0
        outcome.read.append(record_id)
        outcome.pages += pages
        report(f"  record {record_id}: {pages} pages")
    return outcome


def stored_pages(record_ids: Iterable[int]) -> int:
    """Pages of each paper's active chunk set: the price basis for a dry run."""
    from apps.ai.models.chunk import ChunkSet

    return sum(len(sizes or {}) for sizes in ChunkSet.objects.filter(
        record_id__in=list(record_ids), is_active=True).values_list("page_sizes", flat=True))
