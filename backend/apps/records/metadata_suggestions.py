"""Metadata suggestions from a manuscript's Docling structure (IR-406, B1).

The IR-374 frontend redesign spec, §4.5: the Publish dialog offers the
manuscript's own title and abstract, read from the structure the manuscript
extraction already stored. **No LLM and no vendor call** -- this reads one
``PdfExtraction`` row and nothing else, so it costs nothing and raises no
disclosure question (IR-250).

It imports the extraction package's serializer read-only and adds nothing to
``apps/ai`` (spec §4.5).
"""

import os
import re
from typing import Optional

from apps.ai.chunking.document import HEADING, PAGE_FOOTER, PAGE_HEADER, NormalizedDocument
from apps.ai.extraction.serialization import document_from_json
from apps.documents.models import DocumentKind, PdfExtraction

SOURCE = "pdf_structure"

PENDING = "pending"
READY = "ready"
FAILED = "failed"
UNSUPPORTED = "unsupported"

# ``PdfExtraction.STATUS`` in the Publish dialog's vocabulary. A retrying
# extraction reads ``failed`` between attempts (``_run_extraction`` saves the
# failure before Celery retries it); the dialog then shows its neutral line,
# which spec §4.5 accepts, because prefill is assistance.
_STATE_BY_STATUS = {
    "queued": PENDING,
    "running": PENDING,
    "done": READY,
    "failed": FAILED,
}

_ABSTRACT_HEADING = "abstract"

# A page's running head and folio: printed on every page an abstract crosses,
# and never part of what the author wrote.
_PAGE_FURNITURE = frozenset({PAGE_HEADER, PAGE_FOOTER})


def metadata_suggestions(record) -> dict:
    """The payload for ``GET /records/<id>/metadata-suggestions/``.

    ``state`` is the extraction's status in the Publish dialog's terms
    (spec §4.5): ``pending`` while Docling is queued or running, ``ready``
    once the structure is stored (a scanned PDF with no text layer is
    ``ready`` with nulls), ``failed`` when extraction failed, and
    ``unsupported`` when there is no manuscript extraction to read at all.
    Suggestions are only ever read from a ``ready`` structure.
    """
    extraction = PdfExtraction.objects.filter(
        record=record, kind=DocumentKind.MANUSCRIPT
    ).first()
    state = _state(extraction)
    suggestions = {"title": None, "abstract": None}
    if state == READY:
        document = document_from_json(extraction.structure or {})
        suggestions = {
            "title": _title(document, record.abstract_file.name),
            "abstract": _abstract(document),
        }
    return {"state": state, "suggestions": suggestions, "source": SOURCE}


def _state(extraction: Optional[PdfExtraction]) -> str:
    if extraction is None:
        return UNSUPPORTED
    return _STATE_BY_STATUS[extraction.status]


def _title(document: NormalizedDocument, stored_name: str) -> Optional[str]:
    """The structure's title, unless it is only the manuscript's file name.

    Docling falls back to the file name when a PDF names itself nothing (see
    ``normalized_document_from_docling``), and the draft's provisional title
    is the file name too, so offering it would suggest back what is already
    there (spec §4.5).
    """
    title = document.title.strip()
    if not title:
        return None
    basename = os.path.basename(stored_name or "")
    stem = os.path.splitext(basename)[0]
    if _comparable(title) in {_comparable(basename), _comparable(stem)}:
        return None
    return title


def _comparable(name: str) -> str:
    # Storage writes "My Thesis.pdf" as My_Thesis.pdf, so separators and case
    # are not evidence that a title differs from the file name.
    return re.sub(r"[\s_-]+", " ", name).strip().lower()


def _abstract(document: NormalizedDocument) -> Optional[str]:
    """The text of the section headed *Abstract*, up to the next heading.

    ``None`` when the document has no such heading, or the heading has no
    text under it -- a missing suggestion, never an empty one.
    """
    section: Optional[list[str]] = None
    for element in document.elements:
        if element.kind == HEADING:
            if section is not None:
                break
            if _is_abstract_heading(element.text):
                section = []
        elif section is not None and element.kind not in _PAGE_FURNITURE and element.text.strip():
            section.append(element.text.strip())
    return "\n\n".join(section) if section else None


def _is_abstract_heading(text: str) -> bool:
    # "ABSTRACT", "Abstract", "Abstract:" -- case and trailing punctuation are
    # typesetting, not a different section.
    return text.strip().rstrip(".:").strip().lower() == _ABSTRACT_HEADING
