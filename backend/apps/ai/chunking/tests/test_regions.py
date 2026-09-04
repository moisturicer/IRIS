"""Citation regions: the provenance half of IR-113.

These are their own group because they are what makes a citation
*verifiable* rather than merely named. A retrieved passage that cannot be
pointed at in the source PDF is exactly the failure mode ADR-013 was written
to remove, and a region that is silently dropped somewhere between the
extractor and the chunk is indistinguishable from one that was never there.

Every test here runs against every registered strategy, because carrying
provenance is part of being a chunker, not a property of one strategy.

Pure: no Django, no database, no network, no clock.
"""

import pytest

from apps.ai.chunking import (
    BoundingBox,
    ChunkingOptions,
    DocumentElement,
    NormalizedDocument,
    build_chunker,
    chunkset_hash,
    registered_strategies,
)
from apps.ai.chunking.document import HEADING, PARAGRAPH
from apps.ai.chunking.normalizer import normalize
from apps.ai.extraction.docling_mapping import normalized_document_from_docling

ALL_STRATEGIES = sorted(registered_strategies())


@pytest.fixture(params=ALL_STRATEGIES)
def strategy_id(request):
    return request.param


def box(page: int, top: float = 100.0, *, height: float = 20.0) -> BoundingBox:
    """A plain, non-degenerate rect on ``page``, top-left origin."""
    return BoundingBox(page=page, left=72.0, top=top, right=540.0, bottom=top + height)


def para(text: str, page: int, top: float = 100.0) -> DocumentElement:
    return DocumentElement(kind=PARAGRAPH, text=text, page=page, bboxes=(box(page, top),))


def build(*elements: DocumentElement, **page_sizes) -> NormalizedDocument:
    return NormalizedDocument(
        title="A Thesis",
        elements=tuple(elements),
        page_sizes=page_sizes.get("page_sizes", {}),
    )


def chunk_document(document, strategy_id, **kwargs):
    options = ChunkingOptions(strategy=strategy_id, **kwargs)
    return build_chunker(options).chunk(document, options)


# --------------------------------------------------------------------------
# Every chunk is locatable
# --------------------------------------------------------------------------


def test_every_chunk_carries_at_least_one_region(strategy_id):
    document = build(
        DocumentElement(
            kind=HEADING, text="3 Methodology", level=1, page=4, bboxes=(box(4, 80.0),)
        ),
        para("Ponds were sampled weekly across the dry season.", 4, 110.0),
        para("Dissolved oxygen was logged at dawn and at dusk.", 4, 140.0),
        para("Salinity readings were taken from three depths.", 5, 90.0),
    )

    result = chunk_document(document, strategy_id, max_tokens=20)

    assert result.chunks
    for chunk in result.chunks:
        assert chunk.bboxes, f"chunk {chunk.sequence} has no region to highlight"


def test_a_chunk_assembled_from_n_elements_carries_n_regions(strategy_id):
    """The chunk holds one region per source element rather than one box
    swallowing the whitespace between them."""
    elements = [
        para("Alpha one.", 1, 100.0),
        para("Beta two.", 1, 130.0),
        para("Gamma three.", 1, 160.0),
    ]
    document = build(*elements)

    # A ceiling large enough that all three elements land in one chunk.
    result = chunk_document(document, strategy_id, max_tokens=512)

    assert len(result.chunks) == 1
    assert len(result.chunks[0].bboxes) == 3
    assert list(result.chunks[0].bboxes) == [e.bbox for e in elements]


def test_a_chunk_spanning_a_page_break_carries_regions_on_more_than_one_page(
    strategy_id,
):
    document = build(
        para("The final paragraph of page seven.", 7, 700.0),
        para("The first paragraph of page eight.", 8, 90.0),
    )

    result = chunk_document(document, strategy_id, max_tokens=512)

    assert len(result.chunks) == 1
    pages = {b.page for b in result.chunks[0].bboxes}
    assert pages == {7, 8}


def test_a_bottom_left_extractor_rect_reaches_the_chunk_in_top_left_points(strategy_id):
    """The whole path, not just the mapping: an extractor emitting
    bottom-left origin rects must produce chunks whose regions are top-left,
    because top-left is what the PDF viewer draws in.

    Asserting `top < bottom` on a fixture built top-left would be a
    tautology — it has to start life bottom-left for the test to mean
    anything. The conversion itself is tested in the mapping's own suite;
    what this covers is that nothing between there and the chunk undoes it.
    """
    docling = {
        "name": "thesis.pdf",
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": "Ponds were sampled weekly.",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 72.0,
                            "t": 692.0,
                            "r": 540.0,
                            "b": 662.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ],
            }
        ],
        "tables": [],
        "pictures": [],
        "groups": [],
        "pages": {"1": {"size": {"width": 612.0, "height": 792.0}}},
    }
    document = normalized_document_from_docling(docling)

    result = chunk_document(document, strategy_id, max_tokens=512)

    (region,) = result.chunks[0].bboxes
    assert (region.top, region.bottom) == (100.0, 130.0)
    assert region.top < region.bottom


def test_a_repeated_element_contributes_one_region_not_several(strategy_id):
    """A hard-split element yields several fragments in one chunk; the region
    it occupies is still one rectangle, not the same box repeated."""
    element = para("one two three four five six seven eight nine ten", 1, 100.0)
    document = build(element)

    result = chunk_document(document, strategy_id, max_tokens=512)

    assert len(result.chunks) == 1
    assert list(result.chunks[0].bboxes) == [element.bbox]


# --------------------------------------------------------------------------
# Degenerate rectangles
# --------------------------------------------------------------------------


def test_a_zero_area_rectangle_is_flagged_degenerate():
    assert BoundingBox(page=1, left=10.0, top=10.0, right=10.0, bottom=10.0).is_degenerate


def test_an_inverted_rectangle_is_flagged_degenerate():
    assert BoundingBox(page=1, left=100.0, top=50.0, right=20.0, bottom=80.0).is_degenerate


def test_an_ordinary_rectangle_is_not_degenerate():
    assert not box(1).is_degenerate


def test_a_degenerate_region_is_carried_through_rather_than_dropped(strategy_id):
    """It is kept so the chunk still reports which page it came from — the
    sentinel marking is what stops it being drawn (see the repository's
    serialization), not deletion."""
    degenerate = BoundingBox(page=3, left=72.0, top=100.0, right=72.0, bottom=100.0)
    document = build(
        DocumentElement(kind=PARAGRAPH, text="A scanned line.", page=3, bboxes=(degenerate,))
    )

    result = chunk_document(document, strategy_id, max_tokens=512)

    assert result.chunks[0].bboxes == (degenerate,)


# --------------------------------------------------------------------------
# Element kinds
# --------------------------------------------------------------------------


def test_element_kinds_are_recorded_on_each_chunk(strategy_id):
    document = build(
        DocumentElement(
            kind=HEADING, text="4 Results", level=1, page=9, bboxes=(box(9, 80.0),)
        ),
        para("Yields rose in every treated pond.", 9, 110.0),
    )

    result = chunk_document(document, strategy_id, max_tokens=512)

    assert result.chunks[0].element_kinds == frozenset({HEADING, PARAGRAPH})


# --------------------------------------------------------------------------
# Coordinates must not invalidate vectors
# --------------------------------------------------------------------------


def test_the_content_hash_is_unchanged_when_only_coordinates_change(strategy_id):
    """An extractor upgrade that shifts a rect by a fraction of a point
    changes no meaning. If it changed the hash it would mark the whole corpus
    stale and trigger a full re-embed."""
    text = "Ponds were sampled weekly across the dry season."
    original = build(para(text, 4, 110.0))
    shifted = build(
        DocumentElement(
            kind=PARAGRAPH,
            text=text,
            page=4,
            bboxes=(BoundingBox(page=4, left=72.4, top=110.3, right=539.7, bottom=130.1),),
        )
    )

    first = chunk_document(original, strategy_id, max_tokens=512)
    second = chunk_document(shifted, strategy_id, max_tokens=512)

    assert first.content_hash == second.content_hash
    assert first.chunks[0].bboxes != second.chunks[0].bboxes


def test_the_content_hash_is_unchanged_when_only_page_numbers_change(strategy_id):
    """Repagination is the same class of change as a coordinate shift."""
    text = "Dissolved oxygen was logged at dawn."
    first = chunk_document(build(para(text, 1, 100.0)), strategy_id, max_tokens=512)
    second = chunk_document(build(para(text, 12, 100.0)), strategy_id, max_tokens=512)

    assert first.content_hash == second.content_hash


def test_chunkset_hash_ignores_regions_directly():
    """Stated against the hash function itself, so the exclusion cannot be
    lost by a strategy that happens not to populate regions."""
    from apps.ai.chunking import Chunk

    bare = Chunk(text="Some text.", content="Some text.", context_path=("A",), sequence=0, token_count=2)
    located = Chunk(
        text="Some text.",
        content="Some text.",
        context_path=("A",),
        sequence=0,
        token_count=2,
        source_page=7,
        element_kinds=frozenset({PARAGRAPH}),
        bboxes=(box(7),),
    )

    assert chunkset_hash([bare]) == chunkset_hash([located])


# --------------------------------------------------------------------------
# Regions survive normalization
# --------------------------------------------------------------------------


def test_a_hyphenated_rejoin_across_a_page_break_keeps_both_regions():
    """The rejoined element is one element assembled from two, so it carries
    both rectangles. Keeping only the first would silently truncate the
    highlight at the page boundary — the exact evidence a reviewer needs."""
    document = build(
        DocumentElement(kind=PARAGRAPH, text="a mixed-method-", page=7, bboxes=(box(7, 700.0),)),
        DocumentElement(kind=PARAGRAPH, text="ology was used.", page=8, bboxes=(box(8, 90.0),)),
    )

    result = normalize(document, ChunkingOptions())

    assert len(result.elements) == 1
    assert {b.page for b in result.elements[0].bboxes} == {7, 8}
    # `bbox` remains the first region, so `page` and the rect agree.
    assert result.elements[0].bbox == box(7, 700.0)


def test_a_chunk_of_a_rejoined_element_still_spans_both_pages(strategy_id):
    document = build(
        DocumentElement(kind=PARAGRAPH, text="a mixed-method-", page=7, bboxes=(box(7, 700.0),)),
        DocumentElement(kind=PARAGRAPH, text="ology was used.", page=8, bboxes=(box(8, 90.0),)),
    )
    options = ChunkingOptions(strategy=strategy_id, max_tokens=512)

    normalized = normalize(document, options)
    result = build_chunker(options).chunk(normalized, options)

    pages = {b.page for chunk in result.chunks for b in chunk.bboxes}
    assert pages == {7, 8}


def test_page_sizes_are_stored_once_per_chunk_set_not_on_every_chunk(strategy_id):
    """Converting a region to a percentage of the page needs the page size,
    which is a property of the extraction and not of any one chunk."""
    document = NormalizedDocument(
        title="A Thesis",
        elements=(para("One.", 1, 100.0), para("Two.", 2, 100.0)),
        page_sizes={1: (612.0, 792.0), 2: (612.0, 792.0)},
    )

    result = chunk_document(document, strategy_id, max_tokens=512)

    assert result.page_sizes == {1: (612.0, 792.0), 2: (612.0, 792.0)}
    for chunk in result.chunks:
        assert not hasattr(chunk, "page_sizes")
