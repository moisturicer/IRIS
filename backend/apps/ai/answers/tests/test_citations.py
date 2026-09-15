"""Numbering sources in, parsing markers back out (IR-131).

Pure -- no vendor, no database. This is where a citation's correctness lives,
so it has to be testable without an account.
"""

from apps.ai.answers.citations import (
    GroundedAnswer,
    build_prompt,
    parse_citations,
)
from apps.ai.retrieval.ports import RetrievedChunk


def chunk(n, content="a passage", page=1, title="A Thesis", path=("A Thesis", "3 Method")):
    return RetrievedChunk(
        chunk_id=100 + n, record_id=n, record_title=title, content=content,
        context_path=path, source_page=page, score=1.0,
    )


class PromptAssemblyTests:
    def test_sources_are_numbered_from_one_in_order(self):
        prompt = build_prompt("q?", [chunk(1, "alpha"), chunk(2, "beta")])
        assert "[1]" in prompt and "[2]" in prompt
        assert prompt.index("[1]") < prompt.index("[2]")

    def test_the_numbering_is_deterministic(self):
        chunks = [chunk(1, "alpha"), chunk(2, "beta")]
        assert build_prompt("q?", chunks) == build_prompt("q?", chunks)

    def test_the_question_is_present(self):
        assert "weekly pond sampling" in build_prompt("weekly pond sampling", [chunk(1)])

    def test_each_source_carries_its_context_path(self):
        """So the model can see which section a passage came from -- the same
        trail that tells two identically titled sections apart (IR-112)."""
        prompt = build_prompt("q?", [chunk(1, path=("Thesis", "3 Method", "3.2 Sampling"))])
        assert "Thesis > 3 Method > 3.2 Sampling" in prompt

    def test_a_chunk_with_no_context_path_falls_back_to_its_record_title(self):
        prompt = build_prompt("q?", [chunk(1, title="Tilapia Study", path=())])
        assert "Tilapia Study" in prompt

    def test_no_sources_still_produces_a_usable_prompt(self):
        prompt = build_prompt("q?", [])
        assert "q?" in prompt


class CitationParsingTests:
    def test_a_marker_resolves_to_its_chunk_record_and_page(self):
        chunks = [chunk(1, page=7, title="Tilapia Study")]
        _, citations = parse_citations("Yes [1].", chunks)

        assert len(citations) == 1
        assert citations[0].chunk_id == 101
        assert citations[0].record_id == 1
        assert citations[0].record_title == "Tilapia Study"
        assert citations[0].source_page == 7

    def test_several_markers_resolve_in_order(self):
        chunks = [chunk(1), chunk(2), chunk(3)]
        _, citations = parse_citations("First [1], then [3].", chunks)
        assert [c.marker for c in citations] == [1, 3]

    def test_a_repeated_marker_is_one_citation(self):
        """A model citing [1] four times means one source, not four."""
        _, citations = parse_citations("A [1]. B [1]. C [1].", [chunk(1)])
        assert len(citations) == 1

    def test_a_grouped_marker_resolves_to_each_source(self):
        chunks = [chunk(1), chunk(2)]
        _, citations = parse_citations("Both agree [1, 2].", chunks)
        assert [c.marker for c in citations] == [1, 2]

    def test_an_answer_with_no_markers_resolves_nothing(self):
        text, citations = parse_citations("The sources do not cover this.", [chunk(1)])
        assert citations == ()
        assert text == "The sources do not cover this."


class HallucinatedMarkerTests:
    """Models invent [7] when handed four sources. Rendering it shows a reader
    a citation that points at nothing, which reads as evidence."""

    def test_a_marker_beyond_the_supplied_sources_is_dropped_from_the_text(self):
        text, citations = parse_citations("Yes [7].", [chunk(1)])
        assert "[7]" not in text
        assert citations == ()

    def test_the_sentence_survives_the_dropped_marker(self):
        text, _ = parse_citations("Sampling was weekly [7].", [chunk(1)])
        assert "Sampling was weekly" in text

    def test_a_valid_marker_beside_an_invalid_one_is_kept(self):
        text, citations = parse_citations("Both [1, 9].", [chunk(1)])
        assert [c.marker for c in citations] == [1]
        assert "[1]" in text and "9" not in text

    def test_zero_is_not_a_valid_marker(self):
        _, citations = parse_citations("Yes [0].", [chunk(1)])
        assert citations == ()

    def test_dropping_a_marker_does_not_leave_a_space_before_the_full_stop(self):
        text, _ = parse_citations("Sampling was weekly [7].", [chunk(1)])
        assert " ." not in text
        assert text.endswith("weekly.")


class NonAsciiMarkerTests:
    """A model is not bound by the bracket the prompt asks for.

    gpt-oss-120b, the configured default, cites with the CJK lenticular form.
    Against an ASCII-only pattern that resolved to nothing: no citations, and
    the raw marker left in the text where a reader would see it.
    """

    def test_a_lenticular_marker_resolves(self):
        text, citations = parse_citations("Drying took 3 days【1】.", [chunk(1)])
        assert [c.marker for c in citations] == [1]
        assert "【" not in text and "[1]" in text

    def test_a_fullwidth_marker_resolves(self):
        _, citations = parse_citations("Yes［1］.", [chunk(1)])
        assert [c.marker for c in citations] == [1]

    def test_a_lenticular_marker_out_of_range_is_still_dropped(self):
        text, citations = parse_citations("Yes【7】.", [chunk(1)])
        assert citations == ()
        assert "7" not in text

    def test_mixed_bracket_styles_in_one_answer_both_resolve(self):
        _, citations = parse_citations("A [1] and B【2】.", [chunk(1), chunk(2)])
        assert [c.marker for c in citations] == [1, 2]


class GroundedAnswerTests:
    def test_an_answer_with_citations_is_grounded(self):
        answer = GroundedAnswer(text="Yes [1].", citations=(object(),))
        assert answer.is_grounded is True

    def test_an_uncited_answer_is_not_grounded(self):
        """Not necessarily wrong -- "the sources do not cover this" is the
        right response to an unanswerable question -- but a caller should be
        able to tell before presenting it as evidence."""
        answer = GroundedAnswer(text="The sources do not cover this.", citations=())
        assert answer.is_grounded is False
