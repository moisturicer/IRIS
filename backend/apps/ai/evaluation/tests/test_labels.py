"""The label format, and the property it exists for (IR-133 / IR-394).

No database and no vendor: a label is matched against text, so the whole format
is testable with a fixture and an assertion. The re-chunking test is the reason
the format is a quote rather than a chunk id, and it is the one test here that
would fail if that choice were reversed.
"""

import pytest

from apps.ai.chunking import build_chunker
from apps.ai.chunking.tests.fixtures.prose_document import prose_document
from apps.ai.chunking.values import ChunkingOptions
from apps.ai.evaluation.labels import (
    Label,
    QuestionSetError,
    normalize,
    parse_question_set,
)


class _Passage:
    """The `RetrievedChunk` fields a label reads, and nothing else."""

    def __init__(self, record_id, record_title, content, source_page=None):
        self.record_id = record_id
        self.record_title = record_title
        self.content = content
        self.source_page = source_page


QUOTE = "the document stopped moving and nobody noticed that it had"


# -- normalization ------------------------------------------------------------


def test_a_line_break_inside_a_quote_still_matches():
    label = Label(record="A paper", quote="rainfall gauge data to predict flooding")
    passage = _Passage(1, "A paper", "we used rainfall gauge\n  data to predict\nflooding here")
    assert label.matches(passage)


def test_case_and_curly_quotes_do_not_decide_a_match():
    label = Label(record="A paper", quote="the reviewer's own clearance")
    passage = _Passage(1, "a paper", "THE REVIEWER’S OWN CLEARANCE was preserved")
    assert label.matches(passage)


def test_normalization_stops_short_of_dropping_punctuation():
    assert normalize("A  b,\tc") == "a b, c"


def test_a_quote_from_another_record_is_not_a_hit():
    label = Label(record="Paper A", quote="rainfall gauge data to predict flooding")
    passage = _Passage(2, "Paper B", "rainfall gauge data to predict flooding")
    assert not label.matches(passage)


def test_a_record_id_label_matches_by_id():
    label = Label(record=7, quote="rainfall gauge data to predict flooding")
    assert label.matches(_Passage(7, "Whatever the title is", "rainfall gauge data to predict flooding"))
    assert not label.matches(_Passage(8, "Whatever the title is", "rainfall gauge data to predict flooding"))


# -- the loader refuses a set that would score noise --------------------------


def _set(**question):
    return {"name": "t", "questions": [{"id": "q1", **question}]}


def test_a_short_quote_is_refused():
    with pytest.raises(QuestionSetError, match="too short"):
        parse_question_set(
            _set(question="what?", expected=[{"record": "A", "quote": "neural nets"}])
        )


def test_a_quote_long_enough_to_straddle_a_boundary_is_refused():
    with pytest.raises(QuestionSetError, match="straddle"):
        parse_question_set(
            _set(
                question="what?",
                expected=[{"record": "A", "quote": " ".join(["word"] * 40)}],
            )
        )


def test_an_unfilled_template_slot_is_refused():
    with pytest.raises(QuestionSetError, match="no question text"):
        parse_question_set(
            _set(question="TODO", expected=[{"record": "A", "quote": "a" * 30}])
        )


def test_a_question_with_no_expected_passage_is_refused():
    with pytest.raises(QuestionSetError, match="at least one expected"):
        parse_question_set(_set(question="what?", expected=[]))


def test_duplicate_question_ids_are_refused():
    with pytest.raises(QuestionSetError, match="duplicate id"):
        parse_question_set(
            {
                "name": "t",
                "questions": [
                    {
                        "id": "q1",
                        "question": "one",
                        "expected": [{"record": "A", "quote": QUOTE}],
                    },
                    {
                        "id": "q1",
                        "question": "two",
                        "expected": [{"record": "A", "quote": QUOTE}],
                    },
                ],
            }
        )


def test_a_valid_set_parses_into_values():
    question_set = parse_question_set(
        {
            "name": "proxy-starter",
            "corpus": "docs/corpus",
            "questions": [
                {
                    "id": "q1",
                    "question": "how did the submission stop?",
                    "expected": [{"record": "A paper", "page": 3, "quote": QUOTE}],
                }
            ],
        }
    )
    assert len(question_set) == 1
    assert question_set.label_count == 1
    assert question_set.questions[0].expected[0].page == 3


# -- the reason the format is a quote -----------------------------------------


def _chunk_at(max_tokens: int):
    options = ChunkingOptions(max_tokens=max_tokens)
    return build_chunker(options).chunk(prose_document(), options)


@pytest.mark.parametrize("max_tokens", [200, 400, 700])
def test_a_label_survives_rechunking_at_any_ceiling(max_tokens):
    """The whole reason a label is a quote and not a chunk id (ADR-023).

    Re-chunking replaces every chunk id, so a chunk-id label would be
    destroyed by the very comparison the harness exists to make. A quote is
    found in whichever chunk ends up holding it.
    """
    label = Label(record=1, quote=QUOTE)
    chunks = _chunk_at(max_tokens).chunks
    holding = [c for c in chunks if label.found_in(c.content)]
    assert len(holding) == 1, (
        f"at max_tokens={max_tokens} the quote is in {len(holding)} chunks; "
        f"a label must land in exactly one"
    )


def test_the_ceilings_in_that_test_really_do_rechunk_the_document():
    """Guards the test above from passing for the wrong reason: if every
    ceiling produced the same chunks, surviving re-chunking would be vacuous.
    """
    counts = {n: len(_chunk_at(n).chunks) for n in (200, 400, 700)}
    assert len(set(counts.values())) == 3, counts


# -- labelling in progress ----------------------------------------------------


def _template(filled: bool):
    return {
        "name": "template",
        "questions": [
            {"id": "done", "question": "how did the submission stop?",
             "expected": [{"record": "A paper", "quote": QUOTE}]},
            {"id": "todo", "question": "TODO",
             "expected": [{"record": "B paper", "quote": "TODO"}]},
        ] if filled else [
            {"id": "todo", "question": "TODO",
             "expected": [{"record": "B paper", "quote": "TODO"}]},
        ],
    }


def test_an_unfilled_slot_is_refused_by_default():
    with pytest.raises(QuestionSetError, match="no question text"):
        parse_question_set(_template(filled=True))


def test_drop_incomplete_measures_what_is_labelled_and_names_the_rest():
    question_set = parse_question_set(_template(filled=True), drop_incomplete=True)
    assert [q.id for q in question_set.questions] == ["done"]
    assert question_set.skipped == ("todo",)


def test_a_set_with_nothing_labelled_yet_is_refused_even_then():
    with pytest.raises(QuestionSetError, match="no labelled question survived"):
        parse_question_set(_template(filled=False), drop_incomplete=True)
