"""Degradation survives the whole decorator stack (IR-279).

ADR-008 promises that when the vendor is unreachable, Ask IRIS answers from
full-text search **and tells the reader it did**. That promise did not hold.
The flag rode on a ``list`` subclass; ``RerankingRetriever`` built an ordinary
list from those results, and the subclass — with the flag on it — was gone
before anything downstream could read it. The answer service's check was
therefore false whenever a decorator sat in the stack, which is always.

So the test that matters is not "the degrading retriever sets a flag". It is
**"a vendor failure injected at the bottom is still visible at the top"**,
asserted through the real chain rather than on one link of it.

The second half of this module is the guard against it happening again: every
decorator in the package is enumerated and required to carry the flag, and a
new decorator that is not enumerated fails the test rather than silently
joining the stack.

**What that guard does not cover, stated rather than assumed.** It sees
``Retriever`` subclasses defined under `apps/ai/retrieval/`. A decorator
defined in another package, or one that implements the port by duck-typing
rather than by subclassing, is invisible to it. It catches the realistic
case — someone adds a decorator next to the two that exist — and no more.
"""

import importlib
import inspect
import pkgutil
from typing import Optional

import pytest
from django.contrib.auth import get_user_model

import apps.ai.retrieval as retrieval_package
from apps.ai.models.chunk import ChunkSet, DocumentChunk
from apps.ai.providers.noop import NoOpReranker
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.retrieval.degraded import DegradableRetriever, FullTextRetriever
from apps.ai.retrieval.ports import (
    FULL_TEXT,
    VECTOR,
    RetrievalResult,
    RetrievedChunk,
    Retriever,
)
from apps.ai.retrieval.reranking import RerankingRetriever
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_STUDENT

User = get_user_model()

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def a_chunk(chunk_id: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        record_id=1,
        record_title="A Thesis",
        content="weekly pond sampling",
        context_path=("A Thesis",),
        source_page=1,
        score=1.0,
    )


class _Failing(Retriever):
    """A vendor that is out. The failure is injected through the port rather
    than by patching a call, because what is under test is the result."""

    def retrieve(self, question, user, limit=20):
        raise CircuitOpen("the vendor is out")


class _Fixed(Retriever):
    def __init__(self, result: RetrievalResult):
        self._result = result

    def retrieve(self, question, user, limit=20):
        return self._result


_DEGRADED_FALLBACK = RetrievalResult(
    passages=(a_chunk(),), degraded=True, mode=FULL_TEXT
)


def full_stack(inner: Retriever, fallback: Retriever = None) -> Retriever:
    """The stack as it is composed today: reranking wrapped around
    degradation. Reranking is the decorator that dropped the flag, so a test
    that stops below it tests nothing.

    Note what this ordering means and what this ticket does not change: the
    reranker sits *outside* the degradable wrapper, so a reranking vendor
    outage propagates as an exception rather than degrading, even though the
    ticket's framing says "the embedding **or reranking** vendor". Whether
    the composition root should wrap the other way is IR-283's to decide.
    """
    return RerankingRetriever(
        DegradableRetriever(inner, fallback=fallback or _Fixed(_DEGRADED_FALLBACK)),
        reranker=NoOpReranker(),
        policy_enabled=False,
    )


@pytest.fixture
def reader():
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=ROLE_STUDENT)[0]
    return User.objects.create_user(
        email="reader@cit.edu", password="x", role=role, is_verified=True
    )


def make_record(title, owner, texts):
    record = Record.objects.create(title=title, pipeline_status=PipelineStatus.PUBLISHED)
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash="h", strategy_id="s",
        options={}, content_hash=f"c{record.pk}", is_active=True,
    )
    for i, text in enumerate(texts):
        DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=i,
            max_sequence=len(texts) - 1, text=text, content=text,
            context_path=[title], token_count=len(text.split()),
            text_hash=f"h{record.pk}{i}", source_page=1,
            element_kinds=["paragraph"], bboxes=[],
        )
    return record


# ---------------------------------------------------------------------------
# The promise ADR-008 makes
# ---------------------------------------------------------------------------


def test_a_vendor_failure_at_the_bottom_is_still_marked_degraded_at_the_top(reader):
    """The whole chain, the real fallback, real rows. Nothing is faked below
    the seam except the outage itself."""
    make_record("A Thesis", reader, ["weekly pond sampling"])

    result = full_stack(_Failing(), fallback=FullTextRetriever()).retrieve(
        "sampling", reader
    )

    assert result.degraded is True, (
        "a decorator dropped the degraded flag; the reader is being told the "
        "vendor was healthy when it was not"
    )
    assert [p.content for p in result.passages] == ["weekly pond sampling"]
    assert result.mode == FULL_TEXT


def test_a_healthy_vendor_is_not_marked_degraded():
    healthy = _Fixed(RetrievalResult(passages=(a_chunk(),), mode=VECTOR))

    result = full_stack(healthy).retrieve("sampling", None)

    assert result.degraded is False


def test_the_mode_and_space_a_retriever_reported_survive_the_stack():
    """The value has room for retrieval mode and the active space so later
    evaluation work can tell the two paths apart. Room is worth nothing if a
    decorator drops it, so it is carried by the same rule as the flag."""
    healthy = _Fixed(
        RetrievalResult(passages=(a_chunk(),), mode=VECTOR, embedding_space_id=7)
    )

    result = full_stack(healthy).retrieve("sampling", None)

    assert (result.mode, result.embedding_space_id) == (VECTOR, 7)


# ---------------------------------------------------------------------------
# The guard: no future decorator drops it by accident
# ---------------------------------------------------------------------------

#: Every decorator in the package, as a factory taking the retriever it wraps.
#: A decorator missing from here fails `test_every_decorator_is_covered`.
DECORATORS = {
    "DegradableRetriever": lambda inner: DegradableRetriever(inner),
    "RerankingRetriever": lambda inner: RerankingRetriever(
        inner, reranker=NoOpReranker(), policy_enabled=False
    ),
}

#: Retrievers that are sources rather than decorators — they query the
#: database and originate a result instead of passing one along. Membership
#: is not taken on trust: `test_nothing_in_sources_is_really_a_decorator`
#: checks it, so "add it to SOURCES" cannot be used to silence the guard.
SOURCES = {"FullTextRetriever", "TwoStageRetriever"}

#: What a decorator calls the retriever it wraps. Used to tell a source from
#: a decorator by its constructor rather than by where someone filed it.
_WRAPPED_PARAMETERS = {"inner", "primary", "retriever", "wrapped"}


def retriever_classes() -> dict:
    """Every concrete ``Retriever`` defined in the retrieval package.

    ``walk_packages`` rather than ``iter_modules``: a decorator added in a
    subpackage would be invisible to the non-recursive walk.
    """
    found = {}
    for info in pkgutil.walk_packages(
        retrieval_package.__path__, prefix=f"{retrieval_package.__name__}."
    ):
        if ".tests" in info.name:
            continue
        module = importlib.import_module(info.name)
        for name, obj in vars(module).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, Retriever)
                and obj is not Retriever
                and obj.__module__ == module.__name__
            ):
                found[name] = obj
    return found


def wrapped_parameter(cls) -> Optional[str]:
    """The constructor parameter naming the retriever ``cls`` wraps, if any."""
    parameters = inspect.signature(cls.__init__).parameters
    return next((p for p in parameters if p in _WRAPPED_PARAMETERS), None)


def test_every_decorator_is_covered_by_the_contract_below():
    """The point of the enumeration: adding a decorator without adding it here
    fails, rather than quietly joining a stack nobody tests."""
    unaccounted = set(retriever_classes()) - set(DECORATORS) - SOURCES
    assert not unaccounted, (
        f"{sorted(unaccounted)} is a Retriever this module does not classify. "
        "Add it to DECORATORS (and it must carry the degraded flag) or to "
        "SOURCES if it originates results."
    )


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_nothing_in_sources_is_really_a_decorator(name):
    """Without this, the guard above has a one-word escape hatch: filing a new
    decorator under `SOURCES` would silence it while asserting nothing about
    the flag. A source originates a result, so it takes no retriever to wrap.
    """
    cls = retriever_classes()[name]
    assert wrapped_parameter(cls) is None, (
        f"{name} takes a retriever to wrap, so it is a decorator and must "
        "carry the degraded flag. Move it to DECORATORS."
    )


@pytest.mark.parametrize("name", sorted(DECORATORS))
def test_each_decorator_carries_the_degraded_flag_forward(name):
    decorated = DECORATORS[name](_Fixed(_DEGRADED_FALLBACK))

    assert decorated.retrieve("sampling", None).degraded is True, (
        f"{name} dropped the degraded flag"
    )


@pytest.mark.parametrize("name", sorted(DECORATORS))
def test_each_decorator_leaves_a_healthy_result_undegraded(name):
    healthy = _Fixed(RetrievalResult(passages=(a_chunk(),)))

    assert DECORATORS[name](healthy).retrieve("sampling", None).degraded is False
