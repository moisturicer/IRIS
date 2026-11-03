"""Metadata suggestions from a manuscript's stored structure (IR-406, IR-833).

The Publish dialog offers the manuscript's own title and abstract, and --
only where the PDF labels them -- its authors, keywords and publication year,
read from the structure the manuscript extraction already stored. **No LLM
and no vendor call** -- this reads one ``PdfExtraction`` row and nothing else,
so it costs nothing and raises no disclosure question (IR-250).

Two projections of one reading (IR-830 decision 14):

- ``suggestions`` -- the legacy title/abstract strings, kept while clients move.
- ``fields`` -- one entry per field, ``None`` when nothing was found. An entry
  says where its value came from (``basis``, and ``page``/``region`` only when
  the structure records them), whether Publish may fill it in unasked
  (``auto_apply``: a title or abstract within its field's limit, never anything
  else), and whether it is longer than the field allows (``exceeds_limit``:
  offered whole for the author to shorten, never cut). There is no confidence
  value, because nothing here measures one.

What this never does (decision 15): treat the submitting owner as an author,
or read an origin, adviser, embargo, office route, IP or ethics hint, or a
completion year from the paper. A publication year is only a publication year.

It imports the extraction package's serializer read-only and adds nothing to
``apps/ai``.
"""

import os
import re
from typing import Optional

from django.db import models
from django.utils import timezone

from apps.ai.chunking.document import HEADING, PAGE_FOOTER, PAGE_HEADER, DocumentElement, NormalizedDocument
from apps.ai.extraction.serialization import document_from_json
from apps.documents.models import DocumentKind, PdfExtraction
from apps.documents.phases import ExtractionPhase

SOURCE = "pdf_structure"

# The limits the Record write path enforces, so an offered value that would be
# refused on save says so up front. The abstract's is the Publish form's.
TITLE_LIMIT = 500
ABSTRACT_LIMIT = 5000
AUTHOR_LIMIT = 200
KEYWORD_LIMIT = 100
MAX_KEYWORDS = 30

FIELDS = ("title", "abstract", "authors", "keywords", "publication_year")


class SuggestionState(models.TextChoices):
    """The prefill's state, as the Publish dialog branches on it (spec §4.5).

    The manuscript extraction's status restated for one client -- ingestion
    vocabulary, like ``PdfExtraction.STATUS``, and deliberately not in
    ``core.enums`` (see its "What is not here" note).
    """

    PENDING = "pending", "Pending"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
    UNSUPPORTED = "unsupported", "Unsupported"


class Basis(models.TextChoices):
    """Where in the PDF a value was read from."""

    DOCUMENT_TITLE = "document_title", "The document's title"
    ABSTRACT_SECTION = "abstract_section", "The section labelled Abstract"
    LABELLED_FRONT_MATTER = "labelled_front_matter", "A labelled line before the body"


# Queued or running is still being read; done is readable; anything else --
# ``failed``, or a status added to ``PdfExtraction.STATUS`` later -- is
# treated as a failure, which the dialog shows as its neutral line.
_READING = frozenset({"queued", "running", "retrying"})
_READ = "done"

# A page's running head and folio: printed on every page an abstract crosses,
# and never part of what the author wrote.
_PAGE_FURNITURE = frozenset({PAGE_HEADER, PAGE_FOOTER})

# "Abstract", "ABSTRACT:", "1. Abstract", "I. ABSTRACT", "Abstract—": case,
# numbering and trailing punctuation are typesetting, not a different section.
_NUMBERING = r"(?:(?:\d+|[ivxlc]+)[.)]?\s+)?"
_SEPARATOR = r"\s*[:.—–-]"
# Filipino and Spanish theses head the section in their own language.
_ABSTRACT_WORD = r"(?:abstract|abstrak|buod|resumen)"
_ABSTRACT_HEADING = re.compile(rf"^{_NUMBERING}{_ABSTRACT_WORD}{_SEPARATOR}?\s*$", re.IGNORECASE)
# An abstract run into its first paragraph needs a separator ("Abstract— We
# ...", "Abstract: We ..."), or the label set in capitals ("ABSTRACT We ..."),
# so a sentence that merely begins with the word is not taken for one.
_INLINE_ABSTRACT = (
    re.compile(rf"^{_NUMBERING}{_ABSTRACT_WORD}{_SEPARATOR}\s*(?P<text>\S.*)$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^(?:ABSTRACT|ABSTRAK|BUOD|RESUMEN)\s+(?P<text>\S.*)$", re.DOTALL),
)
# Labels, inline or not, are read only from the first elements of the paper:
# with no headings to stop at, a "Keywords:" or "Abstract:" line deep in the
# body would otherwise pass for front matter.
_FRONT_ELEMENTS = 60

_LABELS = {
    "authors": re.compile(rf"^(?:authors?|written by|researchers?|proponents?){_SEPARATOR}\s*(?P<text>\S.*)$", re.IGNORECASE | re.DOTALL),
    "keywords": re.compile(rf"^(?:key\s?words?|index terms){_SEPARATOR}\s*(?P<text>\S.*)$", re.IGNORECASE | re.DOTALL),
    "publication_year": re.compile(
        rf"^(?:publication year|year of publication|year published|date published|publication date|published){_SEPARATOR}\s*(?P<text>\S.*)$",
        re.IGNORECASE | re.DOTALL,
    ),
}
_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")
# Affiliation and correspondence marks a typesetter hangs on a name: "Cruz1,2",
# "Cruz*", "Cruz†".
_NAME_MARKS = re.compile(r"[\d*†‡§,]+$")


def suggestions_payload(record) -> dict:
    """The payload for ``GET /records/<id>/metadata-suggestions/``.

    ``state`` is ``pending`` while the extraction is queued, running or
    retrying, ``ready`` once a structure is stored, ``failed`` when extraction
    failed, and ``unsupported`` when there is nothing to read at all. Values
    are only ever read from a ``ready`` structure, and a ready one may offer
    none.

    Every value is bound to the currently accepted source revision (IR-830).
    """
    extraction = PdfExtraction.objects.filter(
        record=record, kind=DocumentKind.MANUSCRIPT,
        source_revision=record.manuscript_revision,
    ).first()
    state = _state(extraction)
    fields = dict.fromkeys(FIELDS)
    if state == SuggestionState.READY:
        fields = read_fields(document_from_json(extraction.structure or {}), record.abstract_file.name)
    return {
        "state": state.value,
        "suggestions": {name: fields[name]["value"] if fields[name] else None for name in ("title", "abstract")},
        "fields": fields,
        "source": SOURCE,
        "manuscript_revision": str(record.manuscript_revision) if record.manuscript_revision else None,
        "phase": extraction.phase if extraction else "unsupported",
        "retryable": bool(extraction and extraction.status == "failed"),
        "message": extraction.reader_message if extraction else None,
    }


def read_fields(document: NormalizedDocument, stored_name: str) -> dict:
    """Every field this structure supports, ``None`` for the rest."""
    elements = [e for e in document.elements if e.kind not in _PAGE_FURNITURE]
    fields = dict.fromkeys(FIELDS)
    fields["title"] = _title(document, elements, stored_name)
    fields["abstract"] = _abstract(elements)
    for name, value in _front_matter(document, elements).items():
        fields[name] = value
    return fields


def _state(extraction: Optional[PdfExtraction]) -> SuggestionState:
    # A read held for consent or release is not coming: the author types (IR-850).
    if extraction is None or extraction.phase == ExtractionPhase.AWAITING_DISCLOSURE:
        return SuggestionState.UNSUPPORTED
    if extraction.status in _READING:
        return SuggestionState.PENDING
    if extraction.status == _READ:
        return SuggestionState.READY
    return SuggestionState.FAILED


def _entry(value, basis: Basis, element: Optional[DocumentElement], *, auto: bool, exceeds: bool) -> dict:
    bbox = element.bboxes[0] if element is not None and element.bboxes else None
    return {
        "value": value,
        "source": SOURCE,
        "basis": basis.value,
        "page": element.page if element is not None else None,
        "region": (
            {"page": bbox.page, "left": bbox.left, "top": bbox.top, "right": bbox.right, "bottom": bbox.bottom}
            if bbox is not None else None
        ),
        "auto_apply": auto and not exceeds,
        "exceeds_limit": exceeds,
    }


def _title(document: NormalizedDocument, elements, stored_name: str) -> Optional[dict]:
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
    where = next((e for e in elements if e.kind == HEADING and e.text.strip() == title), None)
    return _entry(title, Basis.DOCUMENT_TITLE, where, auto=True, exceeds=len(title) > TITLE_LIMIT)


def _comparable(name: str) -> str:
    # Storage writes "My Thesis.pdf" as My_Thesis.pdf, so separators and case
    # are not evidence that a title differs from the file name.
    return re.sub(r"[\s_-]+", " ", name).strip().lower()


def _abstract(elements) -> Optional[dict]:
    """The section labelled *Abstract*, up to the next heading or label.

    The label may stand alone as a heading, be numbered, or run into the first
    paragraph. Its paragraphs are kept apart, and a *Keywords* line, which
    follows an abstract more often than a heading does, ends it too. ``None``
    when there is no such section, or it holds no text -- a missing
    suggestion, never an empty one.
    """
    section: Optional[list[str]] = None
    start: Optional[DocumentElement] = None
    for index, element in enumerate(elements):
        text = element.text.strip()
        if section is None:
            if element.kind == HEADING and _ABSTRACT_HEADING.match(text):
                section, start = [], element
            elif index < _FRONT_ELEMENTS and (match := _inline_abstract(text)):
                section, start = [match.group("text").strip()], element
            continue
        # A bilingual thesis heads one abstract twice ("Buod", then "Abstract").
        if not section and element.kind == HEADING and _ABSTRACT_HEADING.match(text):
            start = element
            continue
        if element.kind == HEADING or _labelled(text):
            break
        if text:
            section.append(text)
    if not section:
        return None
    text = "\n\n".join(section)
    return _entry(text, Basis.ABSTRACT_SECTION, start, auto=True, exceeds=len(text) > ABSTRACT_LIMIT)


def _inline_abstract(text: str) -> Optional[re.Match]:
    return next((m for m in (p.match(text) for p in _INLINE_ABSTRACT) if m), None)


def _labelled(text: str) -> Optional[tuple[str, str]]:
    for name, pattern in _LABELS.items():
        if match := pattern.match(text):
            return name, match.group("text").strip()
    return None


def _front_matter(document: NormalizedDocument, elements) -> dict:
    """Authors, keywords and publication year, from labelled lines only.

    Read up to the first heading of the body -- the first that is neither the
    title nor an abstract -- and no further than the front elements, since a
    "Keywords:" line in a later chapter labels something else. A label read twice is ambiguous and offers
    nothing, as does any value that does not parse cleanly.
    """
    title = document.title.strip()
    found: dict[str, list[tuple[str, DocumentElement]]] = {}
    for element in elements[:_FRONT_ELEMENTS]:
        text = element.text.strip()
        if element.kind == HEADING and text != title and not _ABSTRACT_HEADING.match(text) and not _labelled(text):
            break
        if label := _labelled(text):
            found.setdefault(label[0], []).append((label[1], element))

    parsers = {"authors": _authors, "keywords": _keywords, "publication_year": _publication_year}
    out = {}
    for name, readings in found.items():
        if len(readings) != 1:
            continue
        text, element = readings[0]
        parsed = parsers[name](text)
        if parsed is not None:
            value, exceeds = parsed
            out[name] = _entry(value, Basis.LABELLED_FRONT_MATTER, element, auto=False, exceeds=exceeds)
    return out


def _authors(text: str) -> Optional[tuple[list[str], bool]]:
    """Names in the order printed, or ``None`` when the list is ambiguous.

    Semicolons separate names when there are any; otherwise commas and a final
    "and"/"&" do. A piece of one word ("Cruz, Juan") could be half a name
    written surname first, so such a list offers nothing rather than a guess.
    """
    text = " ".join(text.split())
    pieces = text.split(";") if ";" in text else re.split(r",|\s+and\s+|\s*&\s*", text)
    names = []
    for piece in pieces:
        name = _NAME_MARKS.sub("", piece.strip()).strip()
        if not name:
            continue
        if len(name.split()) < 2:
            return None
        if name not in names:
            names.append(name)
    if not names:
        return None
    return names, any(len(name) > AUTHOR_LIMIT for name in names)


def _keywords(text: str) -> Optional[tuple[list[str], bool]]:
    text = " ".join(text.split())
    pieces = text.split(";") if ";" in text else text.split(",")
    keywords = []
    for piece in pieces:
        keyword = piece.strip().rstrip(".").strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    if not keywords:
        return None
    return keywords, len(keywords) > MAX_KEYWORDS or any(len(k) > KEYWORD_LIMIT for k in keywords)


def _publication_year(text: str) -> Optional[tuple[int, bool]]:
    """One year, or nothing: two different years are ambiguous."""
    latest = timezone.now().year + 1
    years = {int(y) for y in _YEAR.findall(text) if 1000 <= int(y) <= latest}
    if len(years) != 1:
        return None
    return years.pop(), False
