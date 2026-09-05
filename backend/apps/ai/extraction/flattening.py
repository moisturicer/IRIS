"""The flattened string full-text search indexes.

Derived from the structured document rather than returned alongside it. The
old extraction chain returned one string and nothing else; now that structure
is the primary output, deriving the string from it is what keeps
``PdfExtraction.extracted_text`` and ``PdfExtraction.structure`` describing
the same document forever, instead of only until someone changes one path.

The cleaning rules are carried over unchanged from the ``_clean_text`` helper
that lived in ``apps.documents.tasks``, deliberately: ``Record.search_vector``
is a working GIN index over text shaped by these rules, and changing them
here would silently change search behaviour under cover of an extraction
ticket.

Note what this does **not** touch: ``DocumentElement.text``. That is what
gets embedded, and these rules would strip characters out of a vector's input
for the benefit of a text index that is not its consumer.

Pure: no Django, no I/O, no clock.
"""

import re

from apps.ai.chunking.document import NormalizedDocument

# Lines shorter than this are page furniture — a folio, a rule, a stray
# glyph — not content worth indexing.
_MIN_LINE_LENGTH = 3

_PAGE_NUMBER_LINE = re.compile(r"\d+")
_NON_INDEXABLE = re.compile(r"[^\w\s.,;:!?()\-\'\"/]")
_WHITESPACE_RUN = re.compile(r"\s+")


def flatten_for_search(document: NormalizedDocument) -> str:
    """Return the document as one cleaned line of text, for FTS indexing."""
    return clean_text("\n".join(element.text for element in document.elements))


def clean_text(raw: str) -> str:
    """Normalise raw text for storage and FTS indexing.

    Drops sub-three-character and pure-digit lines, strips characters the
    text index has no use for, and collapses whitespace.
    """
    kept = []
    for line in raw.splitlines():
        stripped = line.strip()
        if len(stripped) < _MIN_LINE_LENGTH:
            continue
        if _PAGE_NUMBER_LINE.fullmatch(stripped):
            continue
        kept.append(stripped)

    text = _NON_INDEXABLE.sub(" ", " ".join(kept))
    return _WHITESPACE_RUN.sub(" ", text).strip()
