"""A reader cannot tell "nothing exists" from "it exists and you may not read
it" (IR-460).

The reader-facing response is a function of whether any Passage was kept and
whether the question carried an evidence requirement -- never of *why* nothing
was kept. `empty`, `withheld_all` and `none_relevant` are one case to a reader.

Asserted at the HTTP boundary, on both `/ai/ask/` and `/ai/ask/stream/`, and
field for field: the body is compared whole, so a field added later that
differs between the cases fails here without anyone remembering to list it.

Shape equality is not indistinguishability. Timing differs with gate work and
is not mitigated; see ADR-034 §Security Impact.
"""

import logging
import pathlib
import re

import pytest

from apps.ai.answers.citations import NO_SOURCES
from apps.ai.answers.selection import Selection, SourceSelection
from apps.ai.composition import use_composition_root
from apps.ai.retrieval.diagnostics import (
    NONE_RELEVANT,
    ChunkBuckets,
    RetrievalDiagnostics,
    StageDiagnostics,
)

from .corpus import (
    FLOOD_QUESTION,
    FLOOD_TEXT,
    ask,
    ask_stream,
    make_record,
    make_user,
    root_with,
)
from .test_ask_stream_http import _parse_sse

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

APPS_AI = pathlib.Path(__file__).resolve().parents[1]


def _gate_withholds_everything(monkeypatch):
    """The selection gate refuses whatever retrieval handed it."""
    monkeypatch.setattr(SourceSelection, "disclosable", lambda self, chunks: [])


def _nothing_relevant(monkeypatch):
    """No relevance floor exists yet (IR-396), so this outcome cannot be
    reached for real; it is forced so the boundary is proven for it too."""
    real = SourceSelection.select

    def select(self, result):
        diagnostics = real(self, result).diagnostics
        return Selection(
            passages=(),
            diagnostics=RetrievalDiagnostics(
                outcome=NONE_RELEVANT,
                selection=StageDiagnostics(buckets=ChunkBuckets()),
                recall=diagnostics.recall,
                degraded=diagnostics.degraded,
            ),
        )

    monkeypatch.setattr(SourceSelection, "select", select)


def _nothing(monkeypatch):
    return None


#: outcome -> (corpus holds a readable-looking record, how to arm the case)
CASES = {
    "empty": (False, _nothing),
    "withheld_all": (True, _gate_withholds_everything),
    "none_relevant": (True, _nothing_relevant),
}


@pytest.fixture(autouse=True)
def caplog(caplog):
    """`apps` does not propagate to the root logger (settings.LOGGING), so
    pytest's handler never sees it unless attached there."""
    apps_logger = logging.getLogger("apps")
    apps_logger.addHandler(caplog.handler)
    yield caplog
    apps_logger.removeHandler(caplog.handler)


@pytest.fixture
def stranger():
    return make_user("stranger@cit.edu")


def _observe(call, outcome, embedder, space, client_for, user, monkeypatch, caplog):
    has_record, arm = CASES[outcome]
    if has_record:
        make_record(title="Public Flood Study", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
    arm(monkeypatch)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        with use_composition_root(root_with(embedder=embedder)):
            response = call(client_for(user), FLOOD_QUESTION)
            # A stream runs lazily, so it is read inside the logging window.
            wire = _parse_sse(response) if call is ask_stream else response.json()
    # Not vacuous: the case really produced the outcome it stands for.
    assert f"'outcome': '{outcome}'" in caplog.text
    return response.status_code, wire


@pytest.mark.parametrize("call", [ask, ask_stream], ids=["ask", "ask_stream"])
class TestIndistinguishable:
    def test_empty_is_the_reference_refusal(
        self, call, embedder, space, client_for, stranger, monkeypatch, caplog
    ):
        status, body = _observe(
            call, "empty", embedder, space, client_for, stranger, monkeypatch, caplog
        )
        assert status == 200
        if call is ask:
            assert body["mode"] == "no_results"
            assert body["citations"] == [] and body["sources"] == []
        else:
            done = [data for name, data in body if name == "done"][0]
            assert done["citations"] == [] and done["sources"] == []

    @pytest.mark.parametrize("outcome", ["withheld_all", "none_relevant"])
    def test_each_case_equals_empty_field_for_field(
        self, call, outcome, embedder, space, client_for, stranger, monkeypatch, caplog
    ):
        # Observed in one test so both sides share one database. The empty
        # side is taken first, before any record exists.
        reference = _observe(
            call, "empty", embedder, space, client_for, stranger, monkeypatch, caplog
        )
        observed = _observe(
            call, outcome, embedder, space, client_for, stranger, monkeypatch, caplog
        )
        assert observed == reference


class TestRecordedState:
    def test_a_question_whose_passages_were_all_withheld_is_no_sources(
        self, embedder, space, monkeypatch
    ):
        make_record(title="Public Flood Study", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        _gate_withholds_everything(monkeypatch)
        service = root_with(embedder=embedder).answer_service(max_sources=8)
        answer = service.answer(FLOOD_QUESTION, make_user("a@cit.edu"))
        assert answer.state == NO_SOURCES
        assert answer.sources == ()


class TestNoWithheldCountLeaks:
    def test_no_log_line_carries_a_withheld_count(
        self, embedder, space, client_for, stranger, monkeypatch, caplog
    ):
        make_record(title="Public Flood Study", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        _gate_withholds_everything(monkeypatch)
        with caplog.at_level(logging.DEBUG):
            with use_composition_root(root_with(embedder=embedder)):
                ask(client_for(stranger), FLOOD_QUESTION)
        assert "withheld" not in caplog.text.replace("withheld_all", "")

    def test_no_response_body_carries_a_withheld_count(
        self, embedder, space, client_for, stranger, monkeypatch
    ):
        make_record(title="Public Flood Study", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        _gate_withholds_everything(monkeypatch)
        with use_composition_root(root_with(embedder=embedder)):
            plain = ask(client_for(stranger), FLOOD_QUESTION).content
            streamed = b"".join(
                ask_stream(client_for(stranger), FLOOD_QUESTION).streaming_content
            )
        assert b"withheld" not in plain and b"withheld" not in streamed


class TestNoBranchReadsTheOutcome:
    """Nothing that shapes a reader's response may read why retrieval came back
    empty. The classification lives in these modules and nowhere else."""

    ALLOWED = {
        "retrieval/diagnostics.py",
        "retrieval/reranking.py",
        "answers/selection.py",
    }
    READS = re.compile(r"\.withheld\b|\.outcome\b|\bwithheld_all\b|\bnone_relevant\b")

    def test_only_the_classifying_modules_touch_it(self):
        offenders = []
        for path in APPS_AI.rglob("*.py"):
            relative = path.relative_to(APPS_AI).as_posix()
            if "tests/" in relative or relative in self.ALLOWED:
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if self.READS.search(line):
                    offenders.append(f"{relative}:{number}: {line.strip()}")
        assert offenders == []
