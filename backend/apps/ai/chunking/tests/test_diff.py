"""Incremental re-chunking, at the level where it is decidable (IR-115 G).

A re-chunk is a diff, not a rewrite. These tests pin the classification
that decides how much of the token budget a re-chunk costs: everything
matched by ``text_hash`` is a vector that does not have to be bought again.
"""

from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash, diff_chunk_sets


def _chunk(text: str, sequence: int) -> Chunk:
    return Chunk(
        text=text,
        content=text,
        context_path=("Doc",),
        sequence=sequence,
        token_count=len(text.split()),
    )


def _set(*texts: str) -> ChunkSet:
    chunks = tuple(_chunk(t, i) for i, t in enumerate(texts))
    return ChunkSet(
        chunks=chunks,
        strategy_id="fixed-window",
        options=ChunkingOptions(),
        content_hash=chunkset_hash(chunks),
    )


def test_an_identical_chunk_set_is_a_no_op():
    previous = _set("alpha", "beta", "gamma")

    diff = diff_chunk_sets(previous=previous, incoming=_set("alpha", "beta", "gamma"))

    assert diff.unchanged is True
    assert diff.to_embed == ()
    assert diff.reused == ()
    assert diff.removed_hashes == ()


def test_one_edited_paragraph_embeds_only_that_paragraph():
    previous = _set("alpha", "beta", "gamma")

    diff = diff_chunk_sets(previous=previous, incoming=_set("alpha", "BETA", "gamma"))

    assert diff.unchanged is False
    assert tuple(c.sequence for c in diff.to_embed) == (1,)
    assert tuple(c.sequence for c in diff.reused) == (0, 2)


def test_a_chunk_that_leaves_the_document_is_reported_as_removed():
    previous = _set("alpha", "beta")

    diff = diff_chunk_sets(previous=previous, incoming=_set("alpha"))

    assert diff.removed_hashes == (_text_hash("beta"),)


def test_a_chunk_that_only_moves_keeps_its_vector():
    """Sequence is part of the *set* hash but not of a chunk's text hash: a
    paragraph that shifts down by one because something was inserted above
    it is the same string, and re-embedding it would buy nothing."""
    previous = _set("alpha", "beta")

    diff = diff_chunk_sets(previous=previous, incoming=_set("new", "alpha", "beta"))

    assert tuple(c.text for c in diff.to_embed) == ("new",)
    assert tuple(c.text for c in diff.reused) == ("alpha", "beta")
    assert diff.removed_hashes == ()


def test_a_duplicated_chunk_reuses_the_same_vector_twice():
    """Two chunks with identical text share one hash. Both must be marked
    reusable — treating the second as new would spend budget on a vector
    the first already paid for."""
    previous = _set("alpha")

    diff = diff_chunk_sets(previous=previous, incoming=_set("alpha", "alpha"))

    assert tuple(c.sequence for c in diff.reused) == (0, 1)
    assert diff.to_embed == ()


def test_diffing_against_nothing_embeds_everything():
    diff = diff_chunk_sets(previous=None, incoming=_set("alpha", "beta"))

    assert diff.unchanged is False
    assert tuple(c.text for c in diff.to_embed) == ("alpha", "beta")
    assert diff.reused == ()


def test_an_emptied_document_removes_every_chunk():
    previous = _set("alpha", "beta")

    diff = diff_chunk_sets(previous=previous, incoming=_set())

    assert diff.unchanged is False
    assert diff.to_embed == ()
    assert set(diff.removed_hashes) == {_text_hash("alpha"), _text_hash("beta")}


def _text_hash(text: str) -> str:
    from apps.ai.chunking import chunk_text_hash

    return chunk_text_hash(_chunk(text, 0))
