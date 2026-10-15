"""IR-594: the controller's composer validates, repairs once, then keeps
only supported parts (ADR-042, spec §5). No database, no vendor."""
import pytest

from apps.ai.answers.citations import GENERATED, NO_SOURCES, UNAVAILABLE
from apps.ai.controller.compose import (
    ANSWER, EVIDENCE, GENERAL, AnswerComposer, ReadyToCompose, UNSUPPORTED_TEXT,
)
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.retrieval.ports import RetrievedChunk

FLOOD = RetrievedChunk(chunk_id=1, record_id=10, record_title="Flood Prediction",
                       content="The LSTM reached 92.4% accuracy on 30 gauges.",
                       context_path=(), source_page=3, score=1.0)
POND = RetrievedChunk(chunk_id=2, record_id=20, record_title="Tilapia Ponds",
                      content="Survival was 81% in brackish ponds.",
                      context_path=(), source_page=5, score=1.0)


class Writer:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, system, user):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class Root:
    def __init__(self, writer):
        self.writer = writer

    def llm_for(self, task, **kw):
        return self.writer


def ready(live=None, **fields):
    values = dict(question="How well do these models do?", resolved_question=None,
                  intent=ANSWER, basis=EVIDENCE, passages=(FLOOD, POND), repair_attempts=1)
    if live is not None:
        values["current"] = lambda sources: live
    values.update(fields)
    return ReadyToCompose(**values)


def compose(writer, **fields):
    return AnswerComposer(Root(writer)).compose(ready(**fields))


def test_a_valid_draft_is_delivered_once_without_its_bindings():
    writer = Writer("The LSTM reached 92.4% accuracy [1].\n```bindings\n"
                    '{"facts": [{"value": 92.4, "metric": "accuracy", "source": 1}],'
                    ' "summary": "Only one paper reports accuracy, so no ranking follows."}\n```')
    answer = compose(writer)
    assert answer.state == GENERATED and len(writer.calls) == 1
    assert answer.text == "The LSTM reached 92.4% accuracy [1]."
    assert [c.record_id for c in answer.citations] == [10]
    assert answer.reasoning_summary == "Only one paper reports accuracy, so no ranking follows."
    assert answer.validation == ()


def test_one_repair_receives_actionable_feedback_and_replaces_the_draft():
    writer = Writer("The LSTM reached 97% accuracy [1].",
                    "The LSTM reached 92.4% accuracy [1].")
    answer = compose(writer)
    assert len(writer.calls) == 2
    feedback = writer.calls[1][1]
    assert "97% accuracy" in feedback and "number" in feedback
    assert answer.text == "The LSTM reached 92.4% accuracy [1]."
    assert answer.validation == ("repaired",)


def test_a_failed_repair_keeps_only_the_supported_sentences_and_never_retries_again():
    bad = "The LSTM reached 97% accuracy [1]. Survival was 81% in ponds [2]."
    writer = Writer(bad, bad, "never sent")
    answer = compose(writer)
    assert len(writer.calls) == 2
    assert answer.state == GENERATED and answer.degraded
    assert "97%" not in answer.text and "Survival was 81% in ponds [2]." in answer.text
    assert "left out" in answer.text
    assert [c.record_id for c in answer.citations] == [20]
    assert answer.reasoning_summary == ""
    assert "unsupported_number" in answer.validation


def test_nothing_supported_is_an_honest_unavailable_state_with_the_sources():
    writer = Writer("It reached 97% accuracy [1].", "It reached 99% accuracy [1].")
    answer = compose(writer)
    assert answer.state == UNAVAILABLE and answer.text == UNSUPPORTED_TEXT
    assert answer.citations == () and answer.sources == (FLOOD, POND)


def test_a_withdrawn_source_is_fenced_without_a_repair():
    writer = Writer("The LSTM reached 92.4% accuracy [1]. Survival was 81% [2].", "never sent")
    answer = compose(writer, live={2})
    assert len(writer.calls) == 1
    assert "92.4" not in answer.text and "Survival was 81% [2]." in answer.text
    assert answer.sources == (POND,)
    assert all(c.record_id == 20 for c in answer.citations)


def test_no_repair_is_spent_when_none_was_reserved():
    writer = Writer("It reached 97% accuracy [1]. Survival was 81% [2].", "never sent")
    answer = compose(writer, repair_attempts=0)
    assert len(writer.calls) == 1 and "97%" not in answer.text


@pytest.mark.parametrize("reply", [LLMUnavailable("down"), "<think>pondering</think>", "  "])
def test_a_model_failure_or_a_reasoning_only_reply_is_unavailable_with_sources(reply):
    answer = compose(Writer(reply))
    assert answer.state == UNAVAILABLE and answer.citations == ()
    assert answer.sources == (FLOOD, POND)


def test_a_repair_outage_keeps_the_supported_parts_of_the_draft():
    writer = Writer("It reached 97% accuracy [1]. Survival was 81% [2].", LLMUnavailable("down"))
    answer = compose(writer)
    assert answer.state == GENERATED and answer.text.startswith("Survival was 81% [2].")


def test_a_two_paper_table_is_allowed_and_tool_talk_is_forbidden_by_the_policy():
    table = ("| Paper | Result |\n|---|---|\n| Flood Prediction | 92.4% accuracy [1] |\n"
             "| Tilapia Ponds | 81% survival [2] |")
    writer = Writer(table)
    answer = compose(writer)
    assert answer.text == table
    system = writer.calls[0][0]
    assert "two or more papers" in system and "three or more" not in system
    assert "Never describe your tools" in system


def test_an_evidence_question_with_nothing_gathered_calls_no_model():
    writer = Writer()
    answer = compose(writer, passages=())
    assert answer.state == NO_SOURCES and writer.calls == []


def test_a_general_explanation_is_composed_without_sources():
    writer = Writer("A confusion matrix tabulates right and wrong guesses.")
    answer = compose(writer, passages=(), basis=GENERAL)
    assert answer.state == GENERATED and "general background" in writer.calls[0][0]
