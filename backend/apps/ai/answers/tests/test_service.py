"""Composing a grounded answer (IR-131).

Failure is injected through the ports, never by mocking a call sequence: what
matters is what a reader ends up with, not which method ran in what order.
"""

import logging

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.answers.citations import DEFAULT_RESPONSE_STYLE, SYSTEM_PROMPT, system_prompt_for
from apps.ai.answers.events import (
    CitationsResolved,
    Done,
    GenerationStarted,
    ReasoningDelta,
    RetrievalFinished,
    RetrievalStarted,
    TextDelta,
)
from apps.ai.answers.service import (
    NO_ANSWER_HINT,
    UNAVAILABLE_TEXT,
    GroundedAnswerService,
)
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider, StreamDelta
from apps.ai.retrieval.ports import RetrievalResult, RetrievedChunk, Retriever
from apps.records.models import Record
from core.enums import PipelineStatus
from core.permissions import ROLE_STUDENT

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

User = get_user_model()


class _FixedRetriever(Retriever):
    def __init__(self, chunks, degraded=False):
        self._result = RetrievalResult(passages=tuple(chunks), degraded=degraded)

    def retrieve(self, question, user, limit=20):
        return self._result


class _BrokenLLM(LLMProvider):
    def generate(self, system, user):
        raise LLMUnavailable("429 rate limited")


class _RecordingLLM(LLMProvider):
    def __init__(self, reply="Yes [1]."):
        self.reply = reply
        self.prompts = []

    def generate(self, system, user):
        self.prompts.append((system, user))
        return self.reply


@pytest.fixture
def reader(db):
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=ROLE_STUDENT)[0]
    return User.objects.create_user(
        email="reader@cit.edu", password="x", role=role, is_verified=True
    )


def make_record(title, *, is_ip=False, consented=True):
    return Record.objects.create(
        title=title,
        pipeline_status=PipelineStatus.PUBLISHED,
        is_ip=is_ip,
        dpa_accepted_at=timezone.now() if consented else None,
    )


def chunk_for(record, content="weekly pond sampling", n=1):
    return RetrievedChunk(
        chunk_id=100 + n, record_id=record.pk, record_title=record.title,
        content=content, context_path=(record.title,), source_page=3, score=1.0,
    )


class AnsweringTests:
    def test_an_answer_carries_its_citations(self, reader):
        record = make_record("Tilapia Study")
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]),
            _RecordingLLM("Sampling was weekly [1]."),
            permits=lambda r: True,
        )

        answer = service.answer("how often was sampling?", reader)

        assert answer.is_grounded
        assert answer.citations[0].record_title == "Tilapia Study"
        assert answer.citations[0].source_page == 3

    def test_the_system_prompt_is_sent_separately_from_the_sources(self, reader):
        record = make_record("Thesis")
        llm = _RecordingLLM()
        GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        ).answer("q?", reader)

        system, user = llm.prompts[0]
        assert system == system_prompt_for(DEFAULT_RESPONSE_STYLE)
        assert "weekly pond sampling" in user

    def test_the_model_is_told_to_say_when_it_does_not_know(self):
        """Asserted against the prompt itself, so the instruction and the
        behaviour a caller expects cannot drift apart."""
        assert NO_ANSWER_HINT in SYSTEM_PROMPT.lower()

    def test_a_hallucinated_marker_never_reaches_the_reader(self, reader):
        record = make_record("Thesis")
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]),
            _RecordingLLM("Yes [4]."),
            permits=lambda r: True,
        )

        answer = service.answer("q?", reader)
        assert "[4]" not in answer.text
        assert answer.citations == ()


class DisclosureGateTests:
    def test_refused_content_never_reaches_the_prompt(self, reader):
        """An LLM call always leaves the deployment -- there is no local
        variant -- so every passage in the prompt is content sent to a vendor.
        """
        record = make_record("IP Work", is_ip=True)
        llm = _RecordingLLM()
        GroundedAnswerService(_FixedRetriever([chunk_for(record, "a secret")]), llm).answer(
            "q?", reader
        )

        sent = " ".join(user for _, user in llm.prompts)
        assert "a secret" not in sent

    def test_with_nothing_disclosable_it_says_so_rather_than_asking_the_model(
        self, reader
    ):
        record = make_record("IP Work", is_ip=True)
        llm = _RecordingLLM()
        answer = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm
        ).answer("q?", reader)

        assert llm.prompts == [], "the model was asked to answer from nothing"
        assert "No readable sources" in answer.text
        assert answer.citations == ()


class _NamedLLM(LLMProvider):
    """A provider that reports which model it is, like the real adapter's
    `.model` property -- what `GroundedAnswerService` reads by default."""

    def __init__(self, model, reply="Yes [1]."):
        self.model = model
        self._reply = reply

    def generate(self, system, user):
        return self._reply


class _FallbackStandIn(LLMProvider):
    """Mimics `FallbackLLMProvider.last_model_used` without wrapping real
    providers -- what `GroundedAnswerService` must prefer over `.model`,
    since a fallback can answer with a different model than the one
    configured first (IR-321)."""

    model = "configured-first"

    def __init__(self, answered_with, reply="Yes [1]."):
        self.last_model_used = answered_with
        self._reply = reply

    def generate(self, system, user):
        return self._reply


class ModelRecordingTests:
    def test_the_answering_model_is_recorded(self, reader):
        record = make_record("Thesis")
        answer = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]),
            _NamedLLM("groq/openai-gpt-oss-120b"),
            permits=lambda r: True,
        ).answer("q?", reader)

        assert answer.model == "groq/openai-gpt-oss-120b"

    def test_a_fallback_providers_last_model_used_wins_over_model(self, reader):
        """ADR-023's recall measurement assumes one model per run; reporting
        the configured-first model here would hide that a fallback answered
        instead -- the exact confound IR-321 exists to prevent."""
        record = make_record("Thesis")
        answer = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]),
            _FallbackStandIn(answered_with="openrouter/some-model"),
            permits=lambda r: True,
        ).answer("q?", reader)

        assert answer.model == "openrouter/some-model"

    def test_no_model_is_recorded_when_none_was_reached(self, reader):
        record = make_record("Thesis")
        answer = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), _BrokenLLM(), permits=lambda r: True
        ).answer("q?", reader)

        assert answer.model is None


class VendorFailureTests:
    def test_an_unavailable_model_never_produces_a_fabricated_answer(self, reader):
        """ADR-008: the answer is replaced by an explicit unavailable state."""
        record = make_record("Thesis")
        answer = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), _BrokenLLM(), permits=lambda r: True
        ).answer("q?", reader)

        assert answer.text == UNAVAILABLE_TEXT
        assert answer.degraded is True
        assert answer.citations == ()

    def test_degraded_retrieval_is_carried_through_to_the_answer(self, reader):
        """A reader should be able to tell that the passages behind an answer
        came from keyword search rather than semantic retrieval."""
        record = make_record("Thesis")
        answer = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)], degraded=True),
            _RecordingLLM("Yes [1]."),
            permits=lambda r: True,
        ).answer("q?", reader)

        assert answer.degraded is True
        assert answer.is_grounded


#: `apps` sets `propagate: False` in `config/settings/base.py`, so records
#: never reach the root logger `caplog` attaches to by default. Setting the
#: level alone does not fix it -- the handler has to go on this module's own
#: logger, or every assertion below passes vacuously against an empty string.
_SERVICE_LOGGER = "apps.ai.answers.service"


@pytest.fixture
def service_logs(caplog):
    """`caplog`, actually wired to the logger under test."""
    logger = logging.getLogger(_SERVICE_LOGGER)
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger=_SERVICE_LOGGER)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


class DriftTelemetryTests:
    """The alarm for the *next* citation-format drift.

    Two formats have now slipped past the parser, and both were found by a
    person reading output by hand. The cost of that is an unknown number of
    uncited answers between the drift and the day somebody notices. These
    assert the log line exists, and -- more important -- that it stays quiet
    when nothing is wrong, since an alarm that cries wolf is one that gets
    muted and then ignored.
    """

    def test_an_answer_citing_nothing_with_unparsed_markers_warns(self, reader, service_logs):
        record = make_record("Thesis")
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]),
            # The shape a future drift takes: citation-like, unsupported.
            _RecordingLLM("Sampling was weekly (1) and monthly <2>."),
            permits=lambda r: True,
        )

        answer = service.answer("how often?", reader)

        assert not answer.is_grounded
        assert "may have drifted to an unsupported format" in service_logs.text
        assert "(1)" in service_logs.text, "the unparsed shape is named, not just counted"

    def test_a_declining_answer_does_not_warn(self, reader, service_logs):
        """The one honest reason to cite nothing. The prompt explicitly asks
        for this, so alerting on it would train whoever reads the logs to stop
        reading them."""
        record = make_record("Thesis")
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]),
            _RecordingLLM("The sources do not cover this question."),
            permits=lambda r: True,
        )

        answer = service.answer("unrelated?", reader)

        assert not answer.is_grounded
        assert service_logs.text == ""

    def test_a_properly_cited_answer_does_not_warn(self, reader, service_logs):
        record = make_record("Thesis")
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]),
            _RecordingLLM("Sampling was weekly [1]."),
            permits=lambda r: True,
        )

        answer = service.answer("how often?", reader)

        assert answer.is_grounded
        assert service_logs.text == ""

    def test_an_answer_citing_nothing_with_no_markers_at_all_still_warns(
        self, reader, service_logs
    ):
        """Quieter than the drift case -- no shape to name -- but still worth
        saying: the model was handed sources, told to cite them, wrote an
        answer, declined nothing, and cited nothing."""
        record = make_record("Thesis")
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]),
            _RecordingLLM("Sampling happened regularly throughout the year."),
            permits=lambda r: True,
        )

        service.answer("how often?", reader)

        assert "no citation-shaped markers were found" in service_logs.text


class _StreamingLLM(LLMProvider):
    """A vendor that streams a scripted sequence of deltas rather than
    answering all at once -- `answer_stream`'s equivalent of `_RecordingLLM`.
    """

    def __init__(self, deltas):
        self._deltas = deltas
        self.prompts: list[tuple[str, str]] = []

    def generate(self, system, user):
        self.prompts.append((system, user))
        return "".join(delta.text for delta in self._deltas)

    def stream(self, system, user):
        self.prompts.append((system, user))
        yield from self._deltas


class _BreaksMidStream(LLMProvider):
    """A vendor that answers, then fails partway through -- so a caller
    reading `answer_stream` can see the deltas already sent are not
    discarded, only the `Done` they end in changes."""

    def generate(self, system, user):
        raise LLMUnavailable("429 rate limited")

    def stream(self, system, user):
        yield StreamDelta(text="partial ")
        raise LLMUnavailable("429 rate limited")


class StreamingTests:
    """`answer_stream` (IR-326): the same steps `answer` takes, narrated as
    they happen, ending in the identical `GroundedAnswer` on its `Done`."""

    def test_events_are_yielded_in_order_with_a_grounded_answer(self, reader):
        record = make_record("Tilapia Study")
        llm = _StreamingLLM(
            [StreamDelta(text="Sampling was "), StreamDelta(text="weekly [1].")]
        )
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        events = list(service.answer_stream("how often?", reader))

        assert [type(e) for e in events] == [
            RetrievalStarted,
            RetrievalFinished,
            GenerationStarted,
            TextDelta,
            TextDelta,
            CitationsResolved,
            Done,
        ]
        assert [e.text for e in events if isinstance(e, TextDelta)] == [
            "Sampling was ",
            "weekly [1].",
        ]
        finished = events[1]
        assert finished.passage_count == 1
        assert finished.record_count == 1
        assert finished.degraded is False

        done = events[-1]
        assert done.answer.is_grounded
        assert done.answer.text == "Sampling was weekly [1]."
        assert done.answer.citations[0].record_title == "Tilapia Study"
        # Identical to what `answer()` would have produced from the same
        # script joined into one string -- the streaming path adds
        # narration, not a second answer.
        assert done.answer.text == service.answer("how often?", reader).text

    def test_nothing_disclosable_skips_straight_to_done(self, reader):
        record = make_record("IP Work", is_ip=True)
        llm = _StreamingLLM([StreamDelta(text="should never be asked for")])
        service = GroundedAnswerService(_FixedRetriever([chunk_for(record)]), llm)

        events = list(service.answer_stream("q?", reader))

        assert [type(e) for e in events] == [RetrievalStarted, RetrievalFinished, Done]
        assert llm.prompts == [], "the model was asked to answer from nothing"
        assert "No readable sources" in events[-1].answer.text

    def test_a_vendor_failure_mid_stream_ends_in_an_unavailable_done(self, reader):
        record = make_record("Thesis")
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), _BreaksMidStream(), permits=lambda r: True
        )

        events = list(service.answer_stream("q?", reader))

        assert [type(e) for e in events] == [
            RetrievalStarted,
            RetrievalFinished,
            GenerationStarted,
            TextDelta,
            Done,
        ]
        done = events[-1]
        assert done.answer.text == UNAVAILABLE_TEXT
        assert done.answer.degraded is True
        # ADR-008: retrieval worked, so the sources travel with the failure.
        assert done.answer.sources
        assert done.answer.citations == ()


class InterruptedStreamTests:
    """A stream that ends before its own `Done` (IR-328), cause-agnostic --
    distinct from `_BreaksMidStream` above, whose `LLMUnavailable` already
    ends in an honest `done`."""

    def test_an_unexpected_vendor_error_calls_on_interrupted_with_a_partial_answer(
        self, reader
    ):
        record = make_record("Thesis")

        class _CrashesMidStream(LLMProvider):
            def generate(self, system, user):
                raise LLMUnavailable("429 rate limited")

            def stream(self, system, user):
                yield StreamDelta(text="Sampling was weekly [1]. ")
                raise RuntimeError("connection reset")

        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), _CrashesMidStream(), permits=lambda r: True
        )

        captured = []
        events = []
        with pytest.raises(RuntimeError):
            for event in service.answer_stream(
                "how often?", reader, on_interrupted=captured.append
            ):
                events.append(event)

        assert [type(e) for e in events] == [
            RetrievalStarted, RetrievalFinished, GenerationStarted, TextDelta,
        ]
        assert len(captured) == 1
        partial = captured[0]
        assert partial.state == "partial"
        assert partial.degraded is True
        assert partial.text == "Sampling was weekly [1]."
        assert partial.citations[0].record_id == record.pk

    def test_on_interrupted_is_never_called_on_a_clean_completion(self, reader):
        record = make_record("Tilapia Study")
        llm = _StreamingLLM([StreamDelta(text="Sampling was weekly [1].")])
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        captured = []
        list(
            service.answer_stream("how often?", reader, on_interrupted=captured.append)
        )

        assert captured == []

    def test_on_interrupted_is_never_called_on_an_unavailable_done(self, reader):
        """Already an honest, complete `done` -- not a truncated answer."""
        record = make_record("Thesis")
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), _BreaksMidStream(), permits=lambda r: True
        )

        captured = []
        list(
            service.answer_stream("q?", reader, on_interrupted=captured.append)
        )

        assert captured == []

    def test_a_caller_closing_the_generator_early_also_counts(self, reader):
        """A disconnect surfaces as `GeneratorExit`, not an exception."""
        record = make_record("Thesis")
        llm = _StreamingLLM(
            [StreamDelta(text="Sampling was "), StreamDelta(text="weekly [1].")]
        )
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        captured = []
        gen = service.answer_stream(
            "how often?", reader, on_interrupted=captured.append
        )
        for event in gen:
            if isinstance(event, TextDelta):
                break
        gen.close()

        assert len(captured) == 1
        assert captured[0].state == "partial"
        assert captured[0].text == "Sampling was"


class ReasoningTests:
    """Reasoning is a structurally distinct channel throughout
    `answer_stream` (IR-327) -- both the vendor's own dedicated
    `StreamDelta.reasoning` field, and the defensive `<think>...</think>`
    split for the known behaviour where reasoning leaks into `.text`
    instead (reported against gpt-oss-120b on Groq).
    """

    def test_reasoning_deltas_are_distinct_from_text_deltas(self, reader):
        record = make_record("Tilapia Study")
        llm = _StreamingLLM(
            [
                StreamDelta(reasoning="Let me check the sources. "),
                StreamDelta(text="Sampling was "),
                StreamDelta(reasoning="Looks consistent."),
                StreamDelta(text="weekly [1]."),
            ]
        )
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        events = list(service.answer_stream("how often?", reader))

        assert [type(e) for e in events] == [
            RetrievalStarted,
            RetrievalFinished,
            GenerationStarted,
            ReasoningDelta,
            TextDelta,
            ReasoningDelta,
            TextDelta,
            CitationsResolved,
            Done,
        ]
        reasoning_texts = [e.text for e in events if isinstance(e, ReasoningDelta)]
        assert reasoning_texts == ["Let me check the sources. ", "Looks consistent."]
        text_texts = [e.text for e in events if isinstance(e, TextDelta)]
        assert text_texts == ["Sampling was ", "weekly [1]."]

    def test_reasoning_is_never_concatenated_into_the_stored_answer(self, reader):
        record = make_record("Tilapia Study")
        llm = _StreamingLLM(
            [
                StreamDelta(reasoning="internal monologue"),
                StreamDelta(text="Sampling was weekly [1]."),
            ]
        )
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        done = list(service.answer_stream("how often?", reader))[-1]

        assert done.answer.text == "Sampling was weekly [1]."
        assert "internal monologue" not in done.answer.text

    def test_had_reasoning_flag_is_false_when_no_reasoning_arrived(self, reader):
        record = make_record("Tilapia Study")
        llm = _StreamingLLM([StreamDelta(text="Sampling was weekly [1].")])
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        done = list(service.answer_stream("how often?", reader))[-1]

        assert done.answer.had_reasoning is False

    def test_had_reasoning_flag_is_true_when_reasoning_arrived(self, reader):
        record = make_record("Tilapia Study")
        llm = _StreamingLLM(
            [
                StreamDelta(reasoning="thinking"),
                StreamDelta(text="Sampling was weekly [1]."),
            ]
        )
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        done = list(service.answer_stream("how often?", reader))[-1]

        assert done.answer.had_reasoning is True

    def test_had_reasoning_survives_a_vendor_failure_after_reasoning_arrived(self, reader):
        """Reasoning that genuinely streamed before the model failed is still
        a fact worth recording, even though the answer itself becomes the
        unavailable-state text."""
        record = make_record("Thesis")

        class _ReasonsThenBreaks(LLMProvider):
            def generate(self, system, user):
                raise LLMUnavailable("429 rate limited")

            def stream(self, system, user):
                yield StreamDelta(reasoning="thinking it over")
                raise LLMUnavailable("429 rate limited")

        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), _ReasonsThenBreaks(), permits=lambda r: True
        )

        done = list(service.answer_stream("q?", reader))[-1]

        assert done.answer.text == UNAVAILABLE_TEXT
        assert done.answer.had_reasoning is True

    def test_reasoning_leaked_into_the_text_channel_is_redirected(self, reader):
        """The defensive case (IR-327): gpt-oss-120b on Groq is known to emit
        reasoning inside `<think>` tags in `.text` even when configured
        hidden. It must arrive as `ReasoningDelta`, not `TextDelta`, and
        never reach the stored answer."""
        record = make_record("Tilapia Study")
        llm = _StreamingLLM(
            [
                StreamDelta(text="<think>the model's inner monologue</think>"),
                StreamDelta(text="Sampling was weekly [1]."),
            ]
        )
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        events = list(service.answer_stream("how often?", reader))

        text_deltas = [e.text for e in events if isinstance(e, TextDelta)]
        reasoning_deltas = [e.text for e in events if isinstance(e, ReasoningDelta)]
        assert "".join(text_deltas) == "Sampling was weekly [1]."
        assert "".join(reasoning_deltas) == "the model's inner monologue"

        done = events[-1]
        assert done.answer.text == "Sampling was weekly [1]."
        assert done.answer.had_reasoning is True
        assert done.answer.is_grounded

    def test_a_leaked_think_block_split_across_chunks_is_still_caught(self, reader):
        """The boundary case a naive per-chunk string check would miss: the
        vendor is free to split `<think>` across two deltas."""
        record = make_record("Tilapia Study")
        llm = _StreamingLLM(
            [
                StreamDelta(text="<thi"),
                StreamDelta(text="nk>secret</think>Sampling was weekly [1]."),
            ]
        )
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        done = list(service.answer_stream("how often?", reader))[-1]

        assert done.answer.text == "Sampling was weekly [1]."
        assert done.answer.had_reasoning is True

    def test_a_citation_shaped_marker_hidden_in_leaked_reasoning_is_never_parsed(self, reader):
        """Reasoning content is never scanned for citation markers -- a
        marker-shaped string the model happened to think out loud must not
        resolve into a citation the reader never actually saw cited."""
        record = make_record("Tilapia Study")
        llm = _StreamingLLM(
            [
                StreamDelta(
                    text="<think>maybe cite [1] here, or [2]?</think>"
                    "Sampling was weekly [1]."
                ),
            ]
        )
        service = GroundedAnswerService(
            _FixedRetriever([chunk_for(record)]), llm, permits=lambda r: True
        )

        done = list(service.answer_stream("how often?", reader))[-1]

        assert done.answer.text == "Sampling was weekly [1]."
        assert len(done.answer.citations) == 1
        assert done.answer.citations[0].marker == 1
