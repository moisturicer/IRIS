"""Structural with citable Figures and transcribed formulas (IR-1054).

``figure_passages`` lifts each Figure out of the text flow into a passage of
its own, so a Figure never cuts a paragraph short. A transcribed formula
stays in its paragraph, shown as LaTeX and embedded per ``index_formulas``.
"""

from apps.ai.chunking.document import (
    FORMULA,
    HEADING,
    PARAGRAPH,
    BoundingBox,
    DocumentElement,
    NormalizedDocument,
)
from apps.ai.chunking.strategies.structural import STRATEGY_ID, StructuralCascadeChunker
from apps.ai.chunking.values import ChunkingOptions

BOX = BoundingBox(page=2, left=10, top=20, right=200, bottom=300)


def build(*elements):
    return NormalizedDocument(title="A Thesis", elements=tuple(elements))


def chunk(document, **overrides):
    overrides.setdefault("context_path_max_tokens", 0)
    return StructuralCascadeChunker().chunk(document, ChunkingOptions(strategy=STRATEGY_ID, **overrides))


def figure(caption="", description="", name="fig-1"):
    return DocumentElement(kind="image", text=caption, description=description, page=2,
                           bboxes=(BOX,), figure=name, source_label="Image")


def formula(latex, description="", name="eq-1"):
    return DocumentElement(kind=FORMULA, text=latex, description=description, page=2,
                           source_label="Formula", figure=name)


def paragraphs():
    return (DocumentElement(kind=HEADING, text="3 Method", level=1),
            DocumentElement(kind=PARAGRAPH, text="The short paragraph before.", page=2))


def test_a_figure_does_not_split_its_section_and_gets_a_passage_of_its_own():
    document = build(*paragraphs(),
                     figure(description="A block diagram of the tiling."),
                     DocumentElement(kind=PARAGRAPH, text="The paragraph after.", page=2))
    chunks = chunk(document, figure_passages=True).chunks

    prose = [c for c in chunks if "image" not in c.element_kinds]
    figures = [c for c in chunks if "image" in c.element_kinds]
    assert len(prose) == 1
    assert "short paragraph before" in prose[0].content and "paragraph after" in prose[0].content
    assert len(figures) == 1 and figures[0].element_kinds == frozenset({"image"})


def test_a_figure_passage_embeds_caption_and_description_and_shows_only_the_caption():
    (passage,) = [c for c in chunk(build(*paragraphs(), figure("Figure 4: Tiles.", "Tiles merge globally.")),
                                   figure_passages=True).chunks if "image" in c.element_kinds]
    assert "Figure 4: Tiles." in passage.text and "Tiles merge globally." in passage.text
    assert passage.content == "Figure 4: Tiles."
    assert passage.bboxes == (BOX,) and passage.source_page == 2


def test_an_uncaptioned_described_figure_is_a_passage_with_nothing_shown():
    (passage,) = [c for c in chunk(build(*paragraphs(), figure(description="A scatter plot.")),
                                   figure_passages=True).chunks if "image" in c.element_kinds]
    assert "A scatter plot." in passage.text and passage.content == ""


def test_a_figure_with_neither_caption_nor_description_is_skipped():
    chunks = chunk(build(*paragraphs(), figure()), figure_passages=True).chunks
    assert all("image" not in c.element_kinds for c in chunks)


def test_an_untranscribed_formula_crop_is_never_a_figure_passage():
    crop = DocumentElement(kind="image", text="", description="", page=2, source_label="Formula",
                           figure="eq-9", bboxes=(BOX,))
    chunks = chunk(build(*paragraphs(), crop), figure_passages=True).chunks
    assert all("image" not in c.element_kinds for c in chunks)


def test_off_a_figure_stays_in_the_text_flow_as_today():
    chunks = chunk(build(*paragraphs(), figure("Figure 4: Tiles.", "Tiles merge globally."))).chunks
    assert len(chunks) == 1 and "Figure 4: Tiles." in chunks[0].content
    assert "Tiles merge globally." not in chunks[0].text


def test_a_transcribed_formula_is_shown_as_latex_and_embedded_with_its_description_when_indexed():
    document = build(*paragraphs(), formula("E = mc^2", "Energy equals mass times c squared."))
    (passage,) = chunk(document, index_formulas=True).chunks
    assert "$$\nE = mc^2\n$$" in passage.content
    assert "E = mc^2" in passage.text and "Energy equals mass" in passage.text
    assert "Energy equals mass" in passage.keyword_text


def test_a_transcribed_formula_is_shown_but_not_embedded_when_not_indexed():
    document = build(*paragraphs(), formula("E = mc^2", "Energy equals mass times c squared."))
    (passage,) = chunk(document, index_formulas=False).chunks
    assert "$$\nE = mc^2\n$$" in passage.content
    assert "mc^2" not in passage.text and "Energy" not in passage.text
    assert "mc^2" not in passage.keyword_text
