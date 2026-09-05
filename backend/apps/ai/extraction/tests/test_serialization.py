"""Round-tripping the structured document through JSON (IR-107).

``PdfExtraction.structure`` is the chunker's input. If a document does not
survive the trip through ``jsonb`` intact, chunking runs on something other
than what was extracted — and nothing downstream would notice.
"""

import json

from apps.ai.chunking.document import (
    HEADING,
    PARAGRAPH,
    TABLE_ROW,
    BoundingBox,
    DocumentElement,
    NormalizedDocument,
)
from apps.ai.extraction.hashing import extraction_hash
from apps.ai.extraction.serialization import (
    FORMAT_VERSION,
    document_from_json,
    document_to_json,
)


def _document() -> NormalizedDocument:
    return NormalizedDocument(
        title="Optimization of Tilapia Feed Conversion",
        elements=(
            DocumentElement(kind=HEADING, text="3 Methodology", level=2, page=12),
            DocumentElement(
                kind=PARAGRAPH,
                text="Samples were collected weekly from twelve ponds.",
                page=12,
                bboxes=(BoundingBox(page=12, left=72.0, top=310.5, right=540.0, bottom=352.1),),
            ),
            DocumentElement(kind=TABLE_ROW, text="| Tilapia | 412 g |"),
        ),
        page_sizes={12: (612.0, 792.0)},
    )


def test_a_document_survives_the_round_trip_unchanged():
    document = _document()

    assert document_from_json(document_to_json(document)) == document


def test_page_sizes_come_back_keyed_by_int():
    """JSON object keys are strings. Without the conversion every page lookup
    downstream misses silently."""
    restored = document_from_json(document_to_json(_document()))

    assert restored.page_sizes == {12: (612.0, 792.0)}


def test_the_serialized_form_is_json_encodable():
    encoded = json.dumps(document_to_json(_document()))

    assert document_from_json(json.loads(encoded)) == _document()


def test_absent_optional_fields_are_omitted_rather_than_written_as_null():
    payload = document_to_json(
        NormalizedDocument(title="t", elements=(DocumentElement(kind=PARAGRAPH, text="x"),))
    )

    (element,) = payload["elements"]
    assert element == {"kind": PARAGRAPH, "text": "x"}


def test_the_format_version_is_recorded():
    assert document_to_json(_document())["version"] == FORMAT_VERSION


def test_an_empty_document_round_trips():
    empty = NormalizedDocument(title="")

    assert document_from_json(document_to_json(empty)) == empty


def test_an_unknown_kind_round_trips_untouched():
    document = NormalizedDocument(
        title="t", elements=(DocumentElement(kind="page_footer", text="Page 12"),)
    )

    assert document_from_json(document_to_json(document)) == document


# ---------------------------------------------------------------------------
# The extraction hash
# ---------------------------------------------------------------------------


def test_the_extraction_hash_is_stable_across_calls():
    assert extraction_hash(_document()) == extraction_hash(_document())


def test_changed_text_changes_the_extraction_hash():
    other = NormalizedDocument(
        title=_document().title,
        elements=_document().elements[:-1],
        page_sizes=_document().page_sizes,
    )

    assert extraction_hash(other) != extraction_hash(_document())


def test_a_moved_region_changes_the_extraction_hash():
    """Unlike ``chunkset_hash``, this one covers coordinates: an extractor
    upgrade that moves every box has to invalidate chunk sets built on the
    old ones, or citations point at coordinates the document no longer has.
    """
    original = _document()
    shifted = NormalizedDocument(
        title=original.title,
        elements=tuple(
            DocumentElement(
                kind=e.kind,
                text=e.text,
                level=e.level,
                page=e.page,
                bboxes=tuple(
                    BoundingBox(
                        page=b.page,
                        left=b.left + 1.0,
                        top=b.top,
                        right=b.right,
                        bottom=b.bottom,
                    )
                    for b in e.bboxes
                ),
            )
            for e in original.elements
        ),
        page_sizes=original.page_sizes,
    )

    assert extraction_hash(shifted) != extraction_hash(original)


def test_the_extraction_hash_is_a_sha256_digest():
    digest = extraction_hash(_document())

    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
