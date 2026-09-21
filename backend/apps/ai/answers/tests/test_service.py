"""Composing a grounded answer (IR-131).

Failure is injected through the ports, never by mocking a call sequence: what
matters is what a reader ends up with, not which method ran in what order.
"""

import logging

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.answers.citations import SYSTEM_PROMPT
from apps.ai.answers.service import (
    NO_ANSWER_HINT,
    UNAVAILABLE_TEXT,
    GroundedAnswerService,
)
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
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
        assert system == SYSTEM_PROMPT
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
