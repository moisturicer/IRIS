"""Numbering sources in, parsing markers back out (IR-131).

Pure -- no vendor, no database. This is where a citation's correctness lives,
so it has to be testable without an account.
"""

from apps.ai.answers.citations import (
    GroundedAnswer,
    build_prompt,
    parse_citations,
    unresolved_marker_candidates,
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

    def test_a_mismatched_bracket_pair_is_not_a_citation(self):
        """`[1】` is not a citation style any model produces, and treating it
        as one would mean the pattern accepts shapes nobody writes."""
        text, citations = parse_citations("Yes [1】.", [chunk(1)])
        assert citations == ()
        assert text == "Yes [1】."


class TrailingSuffixMarkerTests:
    """gpt-oss-120b sometimes appends an OpenAI-style file/line-range suffix
    to a lenticular marker -- `【1†L1-L5】` rather than `【1】`.

    Observed live, 2026-09-20, in a manual end-to-end verification session
    against a real corpus (MeshKV, record 54): every citation in an answer
    using this form resolved to nothing -- `citations: []` on the wire -- with
    the raw marker left sitting in the reader's text. The strings below are
    the actual markers the model produced that run, not invented cases.
    """

    def test_a_marker_with_a_line_range_suffix_resolves(self):
        text, citations = parse_citations(
            "TAKV spreads traffic across the mesh【1†L1-L5】.", [chunk(1)]
        )
        assert [c.marker for c in citations] == [1]
        assert "【" not in text and "[1]" in text

    def test_several_suffixed_markers_resolve_in_order(self):
        _, citations = parse_citations(
            "MESHKV achieves a 1.35x speed-up【1†L13-L16】 over SHARED【2†L1-L3】.",
            [chunk(1), chunk(2)],
        )
        assert [c.marker for c in citations] == [1, 2]

    def test_the_ascii_bracket_form_with_a_suffix_also_resolves(self):
        """Only the lenticular form has been observed carrying a suffix, but
        nothing in the prompt tells the model which bracket style gets one --
        tolerating it on all three keeps the alternatives symmetric rather
        than encoding an assumption about which shape appears next."""
        text, citations = parse_citations("Yes [1†L1-L4].", [chunk(1)])
        assert [c.marker for c in citations] == [1]
        assert "[1]" in text

    def test_a_suffixed_marker_out_of_range_is_still_dropped(self):
        text, citations = parse_citations("Yes【7†L1-L2】.", [chunk(1)])
        assert citations == ()
        assert "7" not in text

    def test_existing_plain_markers_are_unaffected(self):
        """The suffix is optional trailing content, not a new marker shape --
        a marker with nothing after the number must parse exactly as before."""
        text, citations = parse_citations("Drying took 3 days【1】.", [chunk(1)])
        assert [c.marker for c in citations] == [1]
        assert "【" not in text and "[1]" in text

    def test_an_unclosed_marker_does_not_eat_the_sentence_after_it(self):
        """The regression this suffix allowance nearly shipped.

        With the suffix excluding only *closing* brackets, an unclosed `【`
        ran across the prose to the next close: `A【1†L1-L5 and more prose
        【2】` resolved to `A[1]`, deleting the model's own words and
        swallowing the genuine second marker. Dropping a citation is this
        module's failure direction; eating a sentence is not.
        """
        text, citations = parse_citations(
            "A【1†L1-L5 and more prose 【2】 end", [chunk(1), chunk(2)]
        )
        assert "and more prose" in text, "the model's words must survive"
        assert [c.marker for c in citations] == [2], "the closed marker resolves"

    def test_a_suffix_cannot_span_a_bracket_of_any_style(self):
        """A suffix stops at the next bracket character, opening or closing,
        of any of the three styles -- so no marker's suffix can reach into
        another marker and consume it.

        The malformed `【1†see [` never closes and resolves to nothing. The
        `[2]` sitting inside it is a well-formed marker in its own right, so
        it does resolve -- which is the safe outcome: the reader keeps every
        word, and the only thing cited is something that genuinely looks like
        a citation.
        """
        text, citations = parse_citations("A【1†see [2]】 end", [chunk(1), chunk(2)])
        assert [c.marker for c in citations] == [2]
        assert "see" in text and "【1†" in text, "nothing is eaten"

    def test_a_suffix_longer_than_the_bound_is_not_a_citation(self):
        """The length bound keeps a pathological input from matching at all
        rather than letting it consume an unbounded run of text."""
        _, citations = parse_citations(f"A【1†{'x' * 200}】 end", [chunk(1)])
        assert citations == ()


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


class UnresolvedMarkerDetectionTests:
    """The loose net that makes the *next* format drift visible.

    Not a resolver and not allowed to become one: it reports what tried to be
    a citation and failed, so a log line can name the new shape instead of a
    person finding it by reading transcripts, which is how the previous two
    were caught.
    """

    def test_a_resolved_marker_is_not_reported_as_unresolved(self):
        """The trap this function is written around: a resolved marker is
        rewritten to canonical `[n]`, which the loose pattern matches happily.
        Matching on spans of the raw answer rather than the cleaned text is
        what stops every healthy answer becoming an alert."""
        assert unresolved_marker_candidates("Yes [1] and also【2】.") == ()

    def test_a_suffixed_marker_now_supported_is_not_reported(self):
        assert unresolved_marker_candidates("TAKV spreads traffic【1†L1-L5】.") == ()

    def test_an_unsupported_bracket_style_is_reported(self):
        """The shape of a future drift: something citation-like that `_MARKER`
        deliberately does not accept."""
        assert unresolved_marker_candidates("Yes (1) and <2>.") == ("(1)", "<2>")

    def test_a_marker_whose_suffix_exceeds_the_bound_is_reported(self):
        """`_MARKER` bounds its suffix at 64 characters, so a longer one stops
        being a citation -- and this is what makes that silent refusal loud."""
        answer = f"Yes【1†{'x' * 200}】."
        candidates = unresolved_marker_candidates(answer)
        assert len(candidates) == 1 and candidates[0].startswith("【1†xxx")

    def test_a_mismatched_bracket_pair_is_reported(self):
        assert unresolved_marker_candidates("Yes [1】.") == ("[1】",)

    def test_ordinary_prose_with_numbers_is_not_reported(self):
        """False positives are affordable here but not free -- a detector that
        fires on every year and every measurement is one nobody reads."""
        prose = "Drying took (3 days) in 2026, at a cost of (2026) pesos, per Table 4."
        assert unresolved_marker_candidates(prose) == ()

    def test_the_leading_digit_limit_is_real(self):
        """Stated in the docstring rather than discovered later: a marker that
        does not lead with its number is invisible to this."""
        assert unresolved_marker_candidates("Yes [ref:1].") == ()
