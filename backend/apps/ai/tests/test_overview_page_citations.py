"""An overview citation names a page; a chat citation still names a chunk (IR-434)."""

import pytest

from apps.ai.answers.citations import parse_citations
from apps.ai.citation_markers import MARKER, PAGE_MARKER, pages_in
from apps.ai.composition import use_composition_root
from apps.ai.overview import overview_for
from apps.ai.overview.pages import build_page_prompt, parse_page_citations
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.regions import Region
from apps.ai.models import DocumentChunk
from apps.ai.retrieval.ports import RetrievedChunk

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, ask, make_record, make_user, root_with
from .test_overview_whole_paper import _root as _overview_root
from .test_overview_whole_paper import paper  # noqa: F401 -- a fixture


def _chunk(chunk_id, page, content, regions=()):
    return RetrievedChunk(
        chunk_id=chunk_id, record_id=7, record_title="Flood Prediction",
        content=content, context_path=("Flood Prediction", f"Part {chunk_id}"),
        source_page=page, score=0.0, regions=regions,
    )


def _region(page):
    return Region(page=page, left=0.1, top=0.1, right=0.9, bottom=0.2)


PAPER = (
    _chunk(11, 1, "OBJECTIVE flood forecasting", (_region(1),)),
    _chunk(12, 3, "METHOD a convolutional network", (_region(3),)),
    _chunk(13, 3, "DATA ten years of rainfall", (_region(3),)),
    _chunk(14, None, "UNPAGED a caption with no page"),
    _chunk(15, 5, "FINDING accuracy improved"),
)


class PageGrammarTests:
    @pytest.mark.parametrize("marker, pages", [
        ("[p. 3]", [3]),
        ("[p.3]", [3]),
        ("[p3]", [3]),
        ("[P. 3]", [3]),
        ("[page 3]", [3]),
        ("[pp. 3, 5]", [3, 5]),
        ("[pp. 3-5]", [3, 4, 5]),
        ("[pages 3–4, 9]", [3, 4, 9]),
        ("[pp. 3-400]", [3]),
        ("【p. 3】", [3]),
        ("［p. 3］", [3]),
        ("【p. 3†L1-L5】", [3]),
    ])
    def test_the_page_form_names_its_pages(self, marker, pages):
        assert pages_in(PAGE_MARKER.search(marker)) == pages

    @pytest.mark.parametrize("marker", ["[1]", "【1】", "［1］", "[1, 2]", "【1†L1-L5】"])
    def test_every_existing_chunk_form_still_matches(self, marker):
        assert MARKER.search(marker) is not None

    def test_the_chunk_grammar_does_not_read_a_page_marker(self):
        assert MARKER.search("[p. 3]") is None

    def test_a_page_marker_cannot_reach_across_prose(self):
        text = "A【p. 3†L1 and more prose 【p. 5】"
        assert [pages_in(m) for m in PAGE_MARKER.finditer(text)] == [[5]]


class PagePromptTests:
    def test_sources_are_labelled_by_page_in_document_order(self):
        prompt = build_page_prompt("Summarise.", PAPER)

        labels = [prompt.index(label) for label in ("[p. 1]", "[p. 3]", "[p. 5]")]
        assert labels == sorted(labels)
        assert prompt.count("[p. 3]") == 1
        assert prompt.index("METHOD") < prompt.index("DATA") < prompt.index("[p. 5]")

    def test_a_chunk_with_no_page_is_still_in_the_prompt(self):
        assert "UNPAGED" in build_page_prompt("Summarise.", PAPER)

    def test_no_chunk_number_is_offered_to_cite(self):
        prompt = build_page_prompt("Summarise.", PAPER)
        assert "[1]" not in prompt and "[2]" not in prompt


class PageCitationTests:
    def test_a_page_marker_resolves_to_a_citation_carrying_that_page(self):
        text, (citation,) = parse_page_citations("It used a CNN [p. 3].", PAPER)

        assert citation.source_page == 3
        assert citation.marker == 3
        assert text == "It used a CNN [3]."

    def test_the_citation_carries_every_chunk_on_that_page(self):
        _, (citation,) = parse_page_citations("It used a CNN [p. 3].", PAPER)

        assert citation.chunk_id == 12
        assert "METHOD" in citation.text and "DATA" in citation.text
        assert citation.regions == (_region(3), _region(3))

    def test_an_out_of_range_page_marker_is_dropped(self):
        text, citations = parse_page_citations("A claim [p. 40].", PAPER)

        assert citations == ()
        assert text == "A claim."

    def test_a_page_with_no_chunk_on_it_is_dropped(self):
        assert parse_page_citations("A claim [p. 2].", PAPER)[1] == ()

    def test_a_bare_marker_names_a_page_because_no_other_number_was_offered(self):
        _, (citation,) = parse_page_citations("Accuracy improved 【5】.", PAPER)
        assert citation.source_page == 5

    def test_one_page_cited_twice_is_one_citation(self):
        text, citations = parse_page_citations("A [p. 3]. B [p. 3, 5].", PAPER)

        assert [c.source_page for c in citations] == [3, 5]
        assert text == "A [3]. B [3][5]."


class ChatParserTests:
    def test_the_chat_parser_does_not_resolve_a_page_marker(self):
        _, citations = parse_citations("A claim [p. 3].", PAPER)
        assert citations == ()

    def test_two_chunks_on_one_page_stay_two_chat_citations(self):
        _, citations = parse_citations("A [2]. B [3].", PAPER)
        assert [c.chunk_id for c in citations] == [12, 13]


# -- through the service and the chat boundary --------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class OverviewPageCitationTests:
    def test_the_stored_overview_cites_a_page(self, paper):
        llm = ScriptedLLM(reply="The gauge network is sparse [p. 9].")

        with use_composition_root(_overview_root(llm)):
            result = overview_for(paper)

        [citation] = result["overview"]["citations"]
        assert citation["page"] == 9
        assert citation["chunk_id"] == paper.chunks[2].pk
        assert result["overview"]["text"] == "The gauge network is sparse [9]."

    def test_the_overview_is_asked_to_cite_pages(self, paper):
        llm = ScriptedLLM(reply="An account [p. 1].")

        with use_composition_root(_overview_root(llm)):
            overview_for(paper)

        [(system, user)] = llm.calls
        assert "[p. 3]" in system
        assert "[p. 9]" in user


@pytest.mark.db_required
@pytest.mark.django_db
class ChatStaysChunkLevelTests:
    def test_a_chat_citation_names_a_chunk_and_its_quoted_passage(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = ask(client_for(reader), FLOOD_QUESTION).json()

        citation, = body["citations"]
        assert citation["marker"] == 1
        assert citation["chunk_id"] == DocumentChunk.objects.get(record=flood).pk
        assert citation["page"] == 4
        assert citation["text"] == FLOOD_TEXT
