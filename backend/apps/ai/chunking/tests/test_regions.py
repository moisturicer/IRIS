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
