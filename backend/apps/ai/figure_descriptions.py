"""Describing a Manuscript's Figures for retrieval only (IR-852, ADR-056 §10).

A description is appended to its Figure chunk's embedded ``text`` and never
to ``content``, so no reader sees it and no citation quotes it.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from django.db import transaction

logger = logging.getLogger(__name__)

SYSTEM = (
    "You describe one figure from a research paper so a search index can find it. "
    "Say what kind of figure it is and what it shows. For a chart or table, list its "
    "axes, series and the values you can read. Write plain sentences only. Do not "
    "guess at anything the image does not show."
)


def describe_figures(extraction_id: int, source_revision) -> int:
    """Describe each undescribed Figure of the current read; returns how many.
    Nothing is sent while the Profile is unset or the gate refuses the Record."""
    from apps.ai.composition import composition_root
    from apps.ai.providers.openai_compatible import LLMUnavailable
    from apps.ai.admission.errors import AdmissionDenied
    from apps.documents.models import ExtractionFigure, PdfExtraction
    from apps.records.models import Record

    extraction = PdfExtraction.objects.filter(pk=extraction_id, record__isnull=False).first()
    if extraction is None or str(extraction.source_revision) != str(source_revision):
        return 0
    root = composition_root()
    describer = root.figure_describer()
    if describer is None:
        return 0
    written = 0
    pending = ExtractionFigure.objects.filter(
        extraction=extraction, source_revision=extraction.source_revision, description="",
    )
    for figure in pending:
        # Read fresh before each send: a withdrawn consent stops the rest.
        record = Record.objects.filter(pk=extraction.record_id, is_deleted=False).first()
        if record is None or record.manuscript_revision != figure.source_revision \
                or not root.vendor_permits()(record):
            return written
        with figure.image.open("rb") as image:
            data = image.read()
        try:
            text = describer.describe_image(SYSTEM, _prompt(figure), data, figure.media_type).strip()
        except (LLMUnavailable, AdmissionDenied) as error:
            logger.warning("Figure %s was not described: %s", figure.pk, type(error).__name__)
            continue
        # Written only while the Figure is still the current read's.
        written += ExtractionFigure.objects.filter(
            pk=figure.pk, source_revision=figure.source_revision, description="",
        ).update(description=text)
    if written:
        _queue_rechunk(extraction.pk, str(extraction.source_revision))
    return written


def _prompt(figure) -> str:
    caption = figure.caption.strip()
    return f"Its printed caption: {caption}" if caption else "It has no printed caption."


def _queue_rechunk(extraction_id: int, source_revision: str) -> None:
    from apps.ai.tasks import chunk_extraction

    transaction.on_commit(lambda: chunk_extraction.delay(extraction_id, source_revision, force=True))


def with_descriptions(document, extraction):
    """``document`` with each stored description on its Figure element."""
    from apps.documents.models import ExtractionFigure

    described = dict(ExtractionFigure.objects.filter(
        extraction_id=extraction.pk, source_revision=extraction.source_revision,
    ).exclude(description="").values_list("name", "description"))
    if not described:
        return document
    return replace(document, elements=tuple(
        replace(e, description=described[e.figure]) if e.kind == "image" and e.figure in described else e
        for e in document.elements
    ))
