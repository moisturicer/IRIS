"""Normalize-then-chunk over the five thesis shapes (IR-116 H).

These assert the properties the acceptance criteria name for the fixture
documents — a sane chunk count, no empty chunk, every chunk traceable to a
page — plus the two things the pipeline adds over the chunker alone: the
normalizer actually runs before the chunker, and the context path is applied.

Pure. No Django, no database: ``build_chunk_set`` takes a document and
options and returns a chunk set, which is the whole reason the domain was
kept free of Django in A through G.
"""

import unicodedata

import pytest

from apps.ai.chunking import ChunkingOptions
from apps.ai.ingestion.pipeline import build_chunk_set

from .thesis_fixtures import (
    ALL_FIXTURES,
    BIBLIOGRAPHY_THESIS,
    MIXED_LANGUAGE_THESIS,
    SCANNED_THESIS,
    TABLE_HEAVY_THESIS,
    TEXT_LAYER_THESIS,
)

OPTIONS = ChunkingOptions(max_tokens=512, exclude_sections=("References",))


# A bracket, not a golden number: the point is that a shape does not explode
# into hundreds of fragments, and that the fixtures which *should* split do.
# One chunk is the correct answer for four of these at a 512-token ceiling —
# they are each a few hundred tokens after normalization — so a floor of 1 is
# honest rather than lax. A count outside the bracket is a signal to look.
SANE_RANGES = {
    "text_layer": (3, 20),
    "scanned": (1, 10),
    "table_heavy": (1, 20),
    "bibliography": (1, 10),
    "mixed_language": (1, 10),
}


@pytest.fixture(params=sorted(ALL_FIXTURES))
def fixture_name(request):
    return request.param


@pytest.fixture
def chunk_set(fixture_name):
    return build_chunk_set(ALL_FIXTURES[fixture_name], OPTIONS)


# ---------------------------------------------------------------------------
# Properties every fixture shape must hold
# ---------------------------------------------------------------------------


def test_the_chunk_count_lands_in_a_sane_range(fixture_name, chunk_set):
    low, high = SANE_RANGES[fixture_name]
    assert low <= len(chunk_set.chunks) <= high


def test_no_chunk_is_empty(chunk_set):
    assert chunk_set.chunks
    assert all(chunk.content.strip() for chunk in chunk_set.chunks)
    assert all(chunk.text.strip() for chunk in chunk_set.chunks)


def test_every_chunk_maps_back_to_a_page_of_the_document(fixture_name, chunk_set):
    """The citation chain starts here: a chunk with no page cannot be
    highlighted, and a page outside the document's own page sizes cannot be
    converted to a percentage of the page at render time."""
    document = ALL_FIXTURES[fixture_name]
    for chunk in chunk_set.chunks:
        assert chunk.source_page is not None
        assert chunk.source_page in document.page_sizes


def test_every_chunk_carries_at_least_one_region(chunk_set):
    for chunk in chunk_set.chunks:
        assert chunk.bboxes


def test_no_chunk_exceeds_the_token_ceiling(chunk_set):
    assert all(chunk.token_count <= OPTIONS.max_tokens for chunk in chunk_set.chunks)


def test_every_chunk_is_prefixed_with_its_context_path(chunk_set):
    for chunk in chunk_set.chunks:
        assert chunk.context_path
        assert chunk.text.startswith(" > ".join(chunk.context_path))


def test_the_sequence_numbers_are_dense_and_ascending(chunk_set):
    assert [c.sequence for c in chunk_set.chunks] == list(range(len(chunk_set.chunks)))


def test_the_same_document_always_produces_the_same_chunk_set(fixture_name):
    document = ALL_FIXTURES[fixture_name]

    first = build_chunk_set(document, OPTIONS)
    second = build_chunk_set(document, OPTIONS)

    assert first.content_hash == second.content_hash
    assert first.chunks == second.chunks


def test_the_page_sizes_are_carried_onto_the_chunk_set(fixture_name, chunk_set):
    """Converting a region to a percentage of the page needs the page size,
    and it is a property of the extraction rather than of any one chunk."""
    assert chunk_set.page_sizes == ALL_FIXTURES[fixture_name].page_sizes


# ---------------------------------------------------------------------------
# The normalizer runs — these fail if the pipeline chunks the raw document
# ---------------------------------------------------------------------------


def test_a_scanned_thesis_has_its_running_headers_and_footers_dropped():
    chunk_set = build_chunk_set(SCANNED_THESIS, OPTIONS)

    body = " ".join(chunk.content for chunk in chunk_set.chunks)
    assert "WATER QUALITY MONITORING" not in body
    assert "Cebu Institute of Technology" not in body


def test_a_scanned_thesis_has_its_stranded_page_numbers_dropped():
    chunk_set = build_chunk_set(SCANNED_THESIS, OPTIONS)

    contents = [chunk.content for chunk in chunk_set.chunks]
    assert not any(content.strip() in ("14", "xiv") for content in contents)


def test_a_word_hyphenated_across_a_page_break_is_rejoined():
    chunk_set = build_chunk_set(SCANNED_THESIS, OPTIONS)

    body = " ".join(chunk.content for chunk in chunk_set.chunks)
    assert "methodology" in body
    assert "method- ology" not in body


def test_the_bibliography_is_excluded_when_the_options_say_so():
    chunk_set = build_chunk_set(BIBLIOGRAPHY_THESIS, OPTIONS)

    body = " ".join(chunk.content for chunk in chunk_set.chunks)
    assert "Philippine Journal of Fisheries" not in body
    assert "Weekly sampling proved sufficient" in body


def test_the_bibliography_is_chunked_when_the_options_do_not_exclude_it():
    """Section exclusion is a value in ``ChunkingOptions``, not a hardcoded
    rule — this is the pair that keeps it that way."""
    chunk_set = build_chunk_set(
        BIBLIOGRAPHY_THESIS, ChunkingOptions(max_tokens=512)
    )

    body = " ".join(chunk.content for chunk in chunk_set.chunks)
    assert "Philippine Journal of Fisheries" in body


# ---------------------------------------------------------------------------
# Shape-specific structural rules
# ---------------------------------------------------------------------------


def test_a_long_table_repeats_its_header_row_in_every_fragment():
    chunk_set = build_chunk_set(TABLE_HEAVY_THESIS, ChunkingOptions(max_tokens=60))

    table_chunks = [c for c in chunk_set.chunks if "| S" in c.content]
    assert len(table_chunks) > 1
    assert all("Mean weight (g)" in chunk.content for chunk in table_chunks)


def test_a_chunk_never_begins_on_a_combining_mark():
    """A split inside a grapheme cluster renders as mojibake, which is what a
    reader of a Cebuano thesis would see in a citation."""
    chunk_set = build_chunk_set(MIXED_LANGUAGE_THESIS, ChunkingOptions(max_tokens=30))

    for chunk in chunk_set.chunks:
        assert unicodedata.combining(chunk.content[0]) == 0


def test_the_methodology_section_is_reachable_at_passage_level():
    """User story 1, stated as an assertion: the body of the thesis is
    retrievable, and it carries the section it came from."""
    chunk_set = build_chunk_set(TEXT_LAYER_THESIS, OPTIONS)

    sampling = [c for c in chunk_set.chunks if "Van Dorn bottle" in c.content]
    assert len(sampling) == 1
    assert "3.2 Sampling Procedure" in sampling[0].context_path
