"""A formula is delimited in a chunk's reader-facing content (IR-427).

`text` is what the vector was computed from and must not move, so nothing
here may re-embed a stored chunk.
"""

import pytest

from apps.ai.chunking.context_path import build_context_path_chunker
from apps.ai.chunking.document import (
    FORMULA,
    HEADING,
    PARAGRAPH,
    DocumentElement,
    NormalizedDocument,
)
from apps.ai.chunking.hashing import chunk_text_hash, chunkset_hash
from apps.ai.chunking.registry import build_chunker
from apps.ai.chunking.values import ChunkingOptions

STRATEGIES = ["structural-markdown-v1", "fixed-window"]


def _doc(*elements: DocumentElement) -> NormalizedDocument:
    return NormalizedDocument(title="A Thesis", elements=tuple(elements))


def _with_formula() -> NormalizedDocument:
    return _doc(
        DocumentElement(kind=HEADING, text="3 Method", level=1),
        DocumentElement(kind=PARAGRAPH, text="The loss is"),
        DocumentElement(kind=FORMULA, text=r"L = \sum_i x_i"),
        DocumentElement(kind=PARAGRAPH, text="where x is the input."),
    )


def _without_formula() -> NormalizedDocument:
    return _doc(
        DocumentElement(kind=HEADING, text="3 Method", level=1),
        DocumentElement(kind=PARAGRAPH, text="The loss is"),
        DocumentElement(kind=PARAGRAPH, text=r"L = \sum_i x_i"),
        DocumentElement(kind=PARAGRAPH, text="where x is the input."),
    )


def _chunk(strategy: str, document: NormalizedDocument):
    options = ChunkingOptions(strategy=strategy)
    return build_chunker(options).chunk(document, options)


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_formula_element_arrives_displayed_in_content(strategy):
    (chunk,) = _chunk(strategy, _with_formula()).chunks

    assert "$$\n" + r"L = \sum_i x_i" + "\n$$" in chunk.content


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_text_is_not_delimited(strategy):
    (chunk,) = _chunk(strategy, _with_formula()).chunks

    assert "$" not in chunk.text


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_delimiting_changes_no_hash_so_nothing_is_re_embedded(strategy):
    delimited = _chunk(strategy, _with_formula())
    plain = _chunk(strategy, _without_formula())

    assert delimited.content_hash == plain.content_hash
    assert [chunk_text_hash(c) for c in delimited.chunks] == [
        chunk_text_hash(c) for c in plain.chunks
    ]
    assert delimited.content_hash == chunkset_hash(delimited.chunks)


def test_the_context_path_decorator_keeps_text_undelimited():
    options = ChunkingOptions(strategy="structural-markdown-v1")
    (chunk,) = build_context_path_chunker(options).chunk(_with_formula(), options).chunks

    assert "$" not in chunk.text
    assert "$$" in chunk.content
    assert r"L = \sum_i x_i" in chunk.text


def test_a_formula_already_carrying_delimiters_is_not_wrapped_twice():
    document = _doc(
        DocumentElement(kind=PARAGRAPH, text="Energy is"),
        DocumentElement(kind=FORMULA, text="$$E = mc^2$$"),
    )

    (chunk,) = _chunk("structural-markdown-v1", document).chunks

    assert chunk.content.count("$$") == 2


def test_a_merged_chunk_keeps_its_formula_delimited():
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=40, min_tokens=20)
    document = _doc(
        DocumentElement(kind=HEADING, text="2 Setup", level=1),
        DocumentElement(kind=PARAGRAPH, text="Short."),
        DocumentElement(kind=FORMULA, text="a + b"),
    )

    chunks = build_chunker(options).chunk(document, options).chunks

    assert any("$$\na + b\n$$" in c.content for c in chunks)
    assert all("$" not in c.text for c in chunks)
