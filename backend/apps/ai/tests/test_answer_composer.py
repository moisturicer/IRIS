"""IR-594: the controller's composer validates, repairs once, then keeps
only supported parts (ADR-042, spec §5). No database, no vendor."""
import logging

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


@pytest.fixture
def composer_logs(caplog):
    """`apps` does not propagate, so the handler goes on this logger itself."""
    logger = logging.getLogger("apps.ai.controller.compose")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="apps.ai.controller.compose")
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def _limit_for(*sources):
    """The admission estimate of a prompt holding exactly ``sources``."""
    from apps.ai.admission.ledger import estimate_tokens
    from apps.ai.controller.compose import _prompt
    return estimate_tokens(*_prompt(ready(), sources))


def test_over_the_input_limit_the_top_ranked_sources_that_fit_are_kept(settings, composer_logs):
    """IR-703: a prompt over the limit kept 0 sources and silently answered nothing."""
    settings.AI_PROVIDER_ADMISSION = "enforce"
    writer = Writer("The LSTM reached 92.4% accuracy [1].")
    answer = compose(writer, answer_input_limit=_limit_for(FLOOD))
    assert answer.state == GENERATED and len(writer.calls) == 1
    assert "Flood Prediction" in writer.calls[0][1] and "Tilapia" not in writer.calls[0][1]
    assert "kept 1 of 2" in composer_logs.text


def test_when_no_source_fits_the_answer_is_unavailable_and_says_why(settings, composer_logs):
    settings.AI_PROVIDER_ADMISSION = "enforce"
    writer = Writer("never sent")
    answer = compose(writer, answer_input_limit=10)
    assert answer.state == UNAVAILABLE and writer.calls == []
    assert "kept 0 of 2" in composer_logs.text


def test_without_enforcement_every_source_is_sent(settings):
    settings.AI_PROVIDER_ADMISSION = "off"
    writer = Writer("Both [1] [2].")
    compose(writer, answer_input_limit=10)
    assert "Tilapia" in writer.calls[0][1]


def test_startup_refuses_an_answer_limit_that_cannot_hold_one_full_read(settings):
    from django.core.exceptions import ImproperlyConfigured

    from apps.ai.controller.budget import verify_controller_configuration
    settings.AI_PROVIDER_ADMISSION = "enforce"
    settings.AI_RESEARCH_READ_TOKEN_CAP = 3000
    settings.AI_CONTROLLER_ANSWER_RESERVE_TOKENS = 4000
    with pytest.raises(ImproperlyConfigured, match="AI_CONTROLLER_ANSWER_RESERVE_TOKENS"):
        verify_controller_configuration()
    settings.AI_CONTROLLER_ANSWER_RESERVE_TOKENS = 24000
    verify_controller_configuration()
    settings.AI_PROVIDER_ADMISSION = "off"
    settings.AI_CONTROLLER_ANSWER_RESERVE_TOKENS = 4000
    verify_controller_configuration()
