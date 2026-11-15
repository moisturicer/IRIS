"""Short sections merging with a sibling under the same parent (IR-1147).

With ``sibling_merge_floor`` above 0, a structural passage under that many
tokens folds forward into the next section that shares its parent heading
(3.1 with 3.2, never 3 with 4), up to the target; a short last section merges
back. Off (0) is the default and leaves chunk sets exactly as before.
"""

import re

import pytest
from hypothesis import given, settings, strategies as st

from apps.ai.chunking import ChunkingOptions, build_chunker
from apps.ai.chunking.document import (
    HEADING,
    PARAGRAPH,
    BoundingBox,
    DocumentElement,
    NormalizedDocument,
)
from apps.ai.chunking.tokens import count_tokens

STRUCTURAL = "structural-markdown-v1"
TITLE = "A Thesis"


def box(page, top):
    return BoundingBox(page=page, left=10, top=top, right=200, bottom=top + 20)


def heading(text, level):
    return DocumentElement(kind=HEADING, text=text, level=level)


def para(text, page=1, top=10):
    return DocumentElement(kind=PARAGRAPH, text=text, page=page, bboxes=(box(page, top),))


def figure(caption, description):
    return DocumentElement(kind="image", text=caption, description=description, page=2,
                           bboxes=(box(2, 400),), figure="fig-1", source_label="Image")


def build(*elements):
    return NormalizedDocument(title=TITLE, elements=tuple(elements))


def chunk(document, **overrides):
    options = ChunkingOptions(strategy=STRUCTURAL, **overrides)
    return build_chunker(options).chunk(document, options)


def nested_document():
    """Two chapters of short subsections, one Figure, one long section."""
    long_text = " ".join(f"word{i}" for i in range(260)) + "."
    return build(
        heading("1 Introduction", 1),
        para("The introduction states the problem briefly."),
        heading("2 Method", 1),
        heading("2.1 Data", 2),
        para("Data came from forty theses.", top=40),
        heading("2.2 Coding", 2),
        para("Two readers coded each thesis.", top=70),
        figure("Figure 1: The coding map.", "A map of codes across theses."),
        heading("2.3 Analysis", 2),
        para(long_text, page=2, top=100),
        heading("3 Results", 1),
        heading("3.1 Agreement", 2),
        para("Readers agreed on most codes.", page=3),
        heading("3.2 Disagreement", 2),
        para("They disagreed on scope.", page=3, top=50),
    )


# Hashes of nested_document() under the code before IR-1147. Off must reproduce them.
PINNED_OFF = {
    "default": "1cbc6262fc33a6d272ca9537cbd6d69fb6f529e0438fe1826630d6100dec472e",
    "figure_passages": "c1ed745e7c373d0c111a3dea6a8dcc8d5b735227a28d77fe17fd0239462ac72b",
    "small_target": "218338af6d1e9e8d38fc9d069d617265645235515afb835cfe74f2764ab30e77",
}
_PINNED_OPTIONS = {
    "default": {},
    "figure_passages": {"figure_passages": True},
    "small_target": {"target_tokens": 60, "figure_passages": True},
}


@pytest.mark.parametrize("name", sorted(PINNED_OFF))
def test_off_leaves_chunk_sets_identical_to_before(name):
    result = chunk(nested_document(), **_PINNED_OPTIONS[name])
    assert result.content_hash == PINNED_OFF[name]
    assert chunk(nested_document(), sibling_merge_floor=0, **_PINNED_OPTIONS[name]).chunks == result.chunks


def test_off_is_the_default():
    assert ChunkingOptions().sibling_merge_floor == 0


def test_the_floor_is_validated_and_capped_at_the_target():
    with pytest.raises(ValueError):
        ChunkingOptions(sibling_merge_floor=-1)
    # A deployment that lowers the target must still chunk under the default floor.
    assert ChunkingOptions(target_tokens=300, sibling_merge_floor=450).effective_sibling_merge_floor == 300
    assert ChunkingOptions(max_tokens=30, sibling_merge_floor=450).effective_sibling_merge_floor == 30
    assert ChunkingOptions(sibling_merge_floor=450).effective_sibling_merge_floor == 450


def test_short_sibling_sections_merge_under_their_parent():
    document = build(
        heading("2 Method", 1),
        heading("2.1 Data", 2),
        para("Data came from forty theses.", top=40),
        heading("2.2 Coding", 2),
        para("Two readers coded each thesis.", top=70),
    )
    off = chunk(document).chunks
    on = chunk(document, sibling_merge_floor=200).chunks

    assert [c.section_key[-1] for c in off] == ["2.1 Data", "2.2 Coding"]
    (merged,) = on
    assert merged.section_key == (TITLE, "2 Method")
    assert merged.context_path == (TITLE, "2 Method")
    assert merged.text.startswith(f"{TITLE} > 2 Method\n\n")
    assert "2.1 Data" in merged.content and "2.2 Coding" in merged.content
    assert "forty theses" in merged.content and "coded each thesis" in merged.content
    assert set(merged.bboxes) == {b for c in off for b in c.bboxes}


def test_a_run_of_short_siblings_merges_into_one_passage():
    document = build(
        heading("3 Results", 1),
        *[e for i in range(1, 5) for e in (heading(f"3.{i} Part", 2), para(f"Finding number {i}."))],
    )
    (merged,) = chunk(document, sibling_merge_floor=300).chunks
    assert merged.section_key == (TITLE, "3 Results")
    assert all(f"Finding number {i}." in merged.content for i in range(1, 5))


def test_top_level_sections_never_merge():
    document = build(
        heading("3 Results", 1), para("Short results."),
        heading("4 Discussion", 1), para("Short discussion."),
    )
    chunks = chunk(document, sibling_merge_floor=300).chunks
    assert [c.section_key[-1] for c in chunks] == ["3 Results", "4 Discussion"]


def test_top_level_sections_never_merge_without_a_title():
    document = NormalizedDocument(title="", elements=(
        heading("3 Results", 1), para("Short results."),
        heading("4 Discussion", 1), para("Short discussion."),
    ))
    chunks = chunk(document, sibling_merge_floor=300).chunks
    assert [c.section_key for c in chunks] == [("3 Results",), ("4 Discussion",)]


def test_chapters_under_an_untitled_documents_title_heading_never_merge():
    document = NormalizedDocument(title="", elements=(
        heading("My Paper", 1),
        heading("3 Results", 2), para("Short results."),
        heading("4 Discussion", 2), para("Short discussion."),
    ))
    chunks = chunk(document, sibling_merge_floor=300).chunks
    assert [c.section_key[-1] for c in chunks] == ["3 Results", "4 Discussion"]


def test_merged_subsections_merge_on_with_the_next_section():
    document = build(
        heading("3 Results", 1),
        heading("3.1 Agreement", 2),
        heading("3.1.1 Codes", 3), para("Codes agreed."),
        heading("3.1.2 Scope", 3), para("Scope agreed."),
        heading("3.2 Disagreement", 2), para("Some disagreed."),
    )
    (merged,) = chunk(document, sibling_merge_floor=300).chunks
    assert merged.section_key == (TITLE, "3 Results")
    assert all(t in merged.content for t in ("Codes agreed.", "Scope agreed.", "Some disagreed."))


def test_a_short_last_section_merges_back_into_its_sibling():
    long_text = " ".join(f"word{i}" for i in range(80)) + "."
    document = build(
        heading("3 Results", 1),
        heading("3.1 Agreement", 2), para(long_text),
        heading("3.2 Summary", 2), para("In short, they agreed."),
    )
    (merged,) = chunk(document, sibling_merge_floor=50).chunks
    assert merged.section_key == (TITLE, "3 Results")
    assert merged.content.index("word0") < merged.content.index("In short")


def test_merges_never_cross_a_parent_heading():
    document = build(
        heading("3 Results", 1), heading("3.2 Last", 2), para("End of results."),
        heading("4 Discussion", 1), heading("4.1 First", 2), para("Start of discussion."),
    )
    chunks = chunk(document, sibling_merge_floor=300).chunks
    assert len(chunks) == 2
    assert {c.section_key[1] for c in chunks} == {"3 Results", "4 Discussion"}
    assert all(len({m for m in ("Results", "discussion") if m in c.content}) == 1 for c in chunks)


def test_a_parent_intro_does_not_merge_into_its_first_child():
    document = build(
        heading("2 Method", 1), para("This chapter explains the method."),
        heading("2.1 Data", 2), para("Data came from forty theses."),
    )
    chunks = chunk(document, sibling_merge_floor=300).chunks
    assert [c.section_key[-1] for c in chunks] == ["2 Method", "2.1 Data"]


def test_a_figure_passage_is_never_merged_and_a_merge_passes_over_it():
    document = build(
        heading("2 Method", 1),
        heading("2.1 Data", 2), para("Data came from forty theses."),
        figure("Figure 1: The coding map.", "A map of codes."),
        heading("2.2 Coding", 2), para("Two readers coded each thesis."),
    )
    chunks = chunk(document, figure_passages=True, sibling_merge_floor=300).chunks
    kinds = [c.element_kinds for c in chunks]
    assert kinds.count(frozenset({"image"})) == 1
    (fig,) = [c for c in chunks if c.element_kinds == frozenset({"image"})]
    assert fig.section_key == (TITLE, "2 Method", "2.1 Data")
    assert fig.content == "Figure 1: The coding map."
    (merged,) = [c for c in chunks if c is not fig]
    assert merged.section_key == (TITLE, "2 Method")
    assert "forty theses" in merged.content and "coded each thesis" in merged.content


def test_a_passage_at_or_over_the_floor_does_not_merge():
    first = "Data came from forty theses in four colleges."
    document = build(
        heading("2 Method", 1),
        heading("2.1 Data", 2), para(first),
        heading("2.2 Coding", 2), para("Two readers coded each thesis."),
    )
    floor = min(count_tokens(c.content) for c in chunk(document).chunks)
    assert len(chunk(document, sibling_merge_floor=floor).chunks) == 2
    assert len(chunk(document, sibling_merge_floor=floor + 1).chunks) == 1


def test_a_merge_that_would_pass_the_target_is_skipped():
    long_text = " ".join(f"word{i}" for i in range(50)) + "."
    document = build(
        heading("2 Method", 1),
        heading("2.1 Data", 2), para("Short."),
        heading("2.2 Coding", 2), para(long_text),
    )
    target = chunk(document, context_path_max_tokens=0).chunks[1].token_count + 1
    chunks = chunk(document, context_path_max_tokens=0, target_tokens=target, sibling_merge_floor=50).chunks
    assert [c.section_key[-1] for c in chunks] == ["2.1 Data", "2.2 Coding"]
    assert all(c.token_count <= target for c in chunks)


def test_the_nested_document_merges_only_siblings():
    chunks = chunk(nested_document(), figure_passages=True, sibling_merge_floor=300).chunks
    keys = [c.section_key for c in chunks]
    assert (TITLE, "1 Introduction") in keys
    assert (TITLE, "3 Results") in keys
    fig = [c for c in chunks if c.element_kinds == frozenset({"image"})]
    assert fig and fig[0].section_key == (TITLE, "2 Method", "2.2 Coding")


# -- the strategy contract with the option on ---------------------------------

_word = st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=10)
_paragraph = st.lists(_word, min_size=1, max_size=40).map(" ".join)
_section = st.tuples(st.integers(1, 3), st.lists(_paragraph, min_size=0, max_size=3), st.booleans())
_sections = st.lists(_section, min_size=1, max_size=8)


def _tagged_document(sections):
    """Section ``i`` holds words ``S<i>Q...`` and optionally a Figure ``F<i>``."""
    elements = []
    for index, (level, paragraphs, has_figure) in enumerate(sections):
        elements.append(heading(f"H{index} head", level))
        elements.extend(
            para(" ".join(f"S{index}Q{w}" for w in p.split()), top=10 + i) for i, p in enumerate(paragraphs)
        )
        if has_figure:
            elements.append(figure(f"F{index} caption", f"F{index} description"))
    return build(*elements)


def _section_keys(document):
    keys, stack = {}, []
    for element in document.elements:
        if element.kind == HEADING:
            stack = [(lvl, t) for lvl, t in stack if lvl < element.level] + [(element.level, element.text)]
            index = int(element.text[1:].split()[0])
            keys[index] = (TITLE, *(t for _, t in stack))
    return keys


@settings(max_examples=60, deadline=None)
@given(sections=_sections, target=st.integers(20, 80), floor=st.integers(1, 80), figures=st.booleans())
def test_property_contract_holds_with_the_option_on(sections, target, floor, figures):
    document = _tagged_document(sections)
    floor = min(floor, target)
    result = chunk(document, target_tokens=target, max_tokens=target + 40,
                   sibling_merge_floor=floor, figure_passages=figures)
    keys = _section_keys(document)

    assert [c.sequence for c in result.chunks] == list(range(len(result.chunks)))
    assert result == chunk(document, target_tokens=target, max_tokens=target + 40,
                           sibling_merge_floor=floor, figure_passages=figures)
    for c in result.chunks:
        assert c.text.strip()
        assert c.token_count == count_tokens(c.text) <= target + 40
        if c.element_kinds != frozenset({"image"}):
            assert c.token_count <= target
        tags = {int(m.group(1)) for m in re.finditer(r"S(\d+)Q", c.content)}
        for tag in tags:
            # The passage's key is a prefix of every section it holds.
            assert keys[tag][: len(c.section_key)] == c.section_key
        if len(tags) > 1:
            # Merged: sections strictly under one parent heading, never the title alone.
            assert len(c.section_key) >= 2
            assert all(len(keys[t]) > len(c.section_key) for t in tags)
        if figures and c.element_kinds == frozenset({"image"}):
            (fig_tag,) = {int(m.group(1)) for m in re.finditer(r"F(\d+)", c.text)}
            assert c.section_key == keys[fig_tag]

    body = " ".join(c.content for c in result.chunks)
    for index, (_, paragraphs, _) in enumerate(sections):
        for p in paragraphs:
            for w in p.split():
                assert f"S{index}Q{w}" in body


@settings(max_examples=40, deadline=None)
@given(sections=_sections)
def test_property_boxes_cover_every_element(sections):
    document = _tagged_document(sections)
    result = chunk(document, target_tokens=80, sibling_merge_floor=80, figure_passages=True)
    covered = {b for c in result.chunks for b in c.bboxes}
    for element in document.elements:
        if element.kind == PARAGRAPH:
            assert set(element.bboxes) <= covered
