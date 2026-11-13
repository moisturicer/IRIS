"""Chunker consolidation (IR-1050): the production strategy under the contract,
the trail inside the budget, a target with a safety ceiling, and section keys.

Pure: no Django, no database.
"""

import ast
import re
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from apps.ai.chunking import (
    Chunk,
    ChunkingOptions,
    DocumentElement,
    NormalizedDocument,
    build_chunker,
    chunkset_hash,
    registered_strategies,
)
from apps.ai.chunking.document import HEADING, PARAGRAPH
from apps.ai.chunking.tokens import count_tokens

LABELED = "labeled-structure-v1"
STRUCTURAL = "structural-markdown-v1"
ALL_STRATEGIES = sorted(registered_strategies())

_word = st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=10)
_paragraph = st.lists(_word, min_size=1, max_size=50).map(" ".join)
_heading = st.lists(_word, min_size=1, max_size=8).map(" ".join)
_section = st.tuples(_heading, st.integers(1, 3), st.lists(_paragraph, min_size=0, max_size=4))
_sections = st.lists(_section, min_size=1, max_size=6)


def _document(sections, title="A Thesis With A Fairly Long Title") -> NormalizedDocument:
    elements = []
    for heading, level, paragraphs in sections:
        elements.append(DocumentElement(kind=HEADING, text=heading, level=level))
        elements.extend(DocumentElement(kind=PARAGRAPH, text=p) for p in paragraphs)
    return NormalizedDocument(title=title, elements=tuple(elements))


def _chunk(document, **options):
    opts = ChunkingOptions(**options)
    return build_chunker(opts).chunk(document, opts)


def test_the_production_strategy_is_registered():
    assert LABELED in ALL_STRATEGIES


def test_the_pipeline_chooses_labeled_through_the_registry():
    from apps.ai.ingestion.pipeline import build_chunk_set

    document = replace(
        _document([("1 Intro", 1, ["alpha beta"])]), structure_is_authoritative=True
    )
    assert build_chunk_set(document, ChunkingOptions()).strategy_id == LABELED


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
@settings(max_examples=40, deadline=None)
@given(sections=_sections, target=st.integers(6, 40), slack=st.integers(0, 30))
def test_property_no_embedded_text_exceeds_the_safety_ceiling(strategy, sections, target, slack):
    result = _chunk(
        _document(sections), strategy=strategy, target_tokens=target, max_tokens=target + slack
    )
    for chunk in result.chunks:
        assert chunk.token_count == count_tokens(chunk.text)
        assert chunk.token_count <= target + slack


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
@settings(max_examples=40, deadline=None)
@given(sections=_sections, target=st.integers(6, 40))
def test_property_prose_with_its_trail_stays_within_the_target(strategy, sections, target):
    """Prose is always splittable, so the trail never pushes it past the target."""
    result = _chunk(_document(sections), strategy=strategy, target_tokens=target, max_tokens=2000)
    for chunk in result.chunks:
        assert chunk.token_count <= target, chunk.text


def test_the_trail_is_counted_inside_the_target():
    paragraph = " ".join(f"word{i}" for i in range(400)) + "."
    document = _document([("3 Methodology", 1, [paragraph])])
    for strategy in (STRUCTURAL, LABELED):
        result = _chunk(document, strategy=strategy, target_tokens=60, max_tokens=60)
        assert len(result.chunks) > 1
        for chunk in result.chunks:
            assert chunk.text.startswith(" > ".join(chunk.context_path))
            assert chunk.token_count <= 60


@pytest.mark.parametrize("strategy", [STRUCTURAL, LABELED])
@settings(max_examples=40, deadline=None)
@given(sections=_sections)
def test_property_every_chunk_holds_one_sections_content(strategy, sections):
    # Distinct body words per section, so a chunk's content names its section.
    tagged = [
        (f"H{index} {heading}", level, [" ".join(f"S{index}Q{w}" for w in p.split()) for p in paragraphs])
        for index, (heading, level, paragraphs) in enumerate(sections)
    ]
    document = _document(tagged)
    result = _chunk(document, strategy=strategy, target_tokens=30, max_tokens=60)
    for chunk in result.chunks:
        assert chunk.section_key
        sections_in_body = {m.group(1) for m in re.finditer(r"S(\d+)Q", chunk.content)}
        assert len(sections_in_body) <= 1
        if sections_in_body:
            assert chunk.section_key[-1].startswith(f"H{sections_in_body.pop()} ")


def test_section_key_is_the_full_heading_path_even_when_the_trail_is_cut():
    document = _document(
        [("1 Chapter With A Long Name", 1, []), ("1.1 Section", 2, []), ("1.1.1 Deep", 3, ["alpha beta"])]
    )
    for strategy in (STRUCTURAL, LABELED):
        chunk = _chunk(document, strategy=strategy, target_tokens=200, context_path_max_tokens=12).chunks[-1]
        assert chunk.section_key == (
            "A Thesis With A Fairly Long Title",
            "1 Chapter With A Long Name",
            "1.1 Section",
            "1.1.1 Deep",
        )
        assert len(chunk.context_path) < len(chunk.section_key)


def test_section_key_is_not_hashed():
    a = Chunk(text="x", content="x", context_path=("T",), sequence=0, token_count=1, section_key=("T", "1"))
    b = replace(a, section_key=("T", "2"))
    assert chunkset_hash([a]) == chunkset_hash([b])


def test_labeled_folds_a_heading_only_section_forward():
    document = _document([("3 Methodology", 1, []), ("3.2 Sampling", 2, ["Samples were collected weekly."])])
    chunks = _chunk(document, strategy=LABELED, target_tokens=200).chunks
    assert len(chunks) == 1
    assert "3 Methodology" in chunks[0].content
    assert chunks[0].section_key[-1] == "3.2 Sampling"


def test_labeled_merges_short_chunks_within_a_section():
    table = DocumentElement(kind="table", text="a | b\n1 | 2", rows=(("a", "b"), ("1", "2")))
    document = NormalizedDocument(
        title="T",
        elements=(
            DocumentElement(kind=HEADING, text="1 Results", level=1),
            DocumentElement(kind=PARAGRAPH, text="Short."),
            table,
        ),
    )
    merged = _chunk(document, strategy=LABELED, target_tokens=200)
    unmerged = _chunk(document, strategy=LABELED, target_tokens=200, merge_short_siblings=False)
    assert len(merged.chunks) == 1
    assert len(unmerged.chunks) == 2


def test_labeled_keeps_a_figure_whole_up_to_the_ceiling_and_splits_past_it():
    description = " ".join(f"detail{i}" for i in range(80))
    figure = DocumentElement(kind="image", text="Figure 1.", description=description)
    document = NormalizedDocument(title="T", elements=(figure,))
    size = count_tokens(f"T\n\nFigure 1.\n{description}")

    whole = _chunk(document, strategy=LABELED, target_tokens=20, max_tokens=size + 10)
    assert len(whole.chunks) == 1 and whole.chunks[0].token_count > 20

    split = _chunk(document, strategy=LABELED, target_tokens=20, max_tokens=size // 2)
    assert len(split.chunks) > 1
    assert all(c.token_count <= size // 2 for c in split.chunks)


def test_target_and_ceiling_defaults():
    options = ChunkingOptions()
    assert (options.effective_target_tokens, options.max_tokens) == (700, 2000)
    assert ChunkingOptions(max_tokens=20).effective_target_tokens == 20
    assert ChunkingOptions(max_tokens=2000, target_tokens=300).effective_target_tokens == 300
    with pytest.raises(ValueError):
        ChunkingOptions(max_tokens=100, target_tokens=200)


def test_unread_options_are_gone():
    fields = ChunkingOptions.__dataclass_fields__
    assert "overlap_tokens" not in fields
    assert "repeat_table_header" not in fields


def test_no_strategy_imports_a_private_name_from_another_module():
    for path in (Path(__file__).parents[1] / "strategies").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                private = [alias.name for alias in node.names if alias.name.startswith("_")]
                assert not private, f"{path.name} imports {private} from {node.module}"
