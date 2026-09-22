"""How the retrieval stack is assembled (IR-283).

Everything Ask IRIS needs was written and tested before this module existed --
two-stage retrieval, reranking, the disclosure gate, degradation, grounded
answers -- and none of it was reachable, because nothing constructed it. This
is the one place that wiring is expressed, and the HTTP layer asks it for a
retriever rather than building one.

**The stack, outermost first.** Degradation wraps reranking wraps two-stage
retrieval. The order is the point:

* ``DegradableRetriever`` outermost, so a vendor outage anywhere beneath it
  falls back to full-text search and says so;
* ``RerankingRetriever`` in the middle, so the disclosure gate runs on
  candidates *before* any of them is sent to a reranker, and so trimming to
  the caller's limit happens after precision has been improved;
* ``TwoStageRetriever`` innermost, where ``visible_to(user)`` narrows the
  candidate set before anything is scored. That is the security property, and
  it stays a property of one place.

**Overridable, and that is a requirement rather than a convenience.** The
primary test seam for this work is the HTTP boundary driven with the
deterministic provider fakes; without a root a test can replace, there is no
way to reach the views with a fake vendor, and the security assertions would
have to be made a layer lower than the layer that can actually leak.

**The default root answers nothing today, and that is the gate working.**
``permits`` defaults to ``disclosure_permits``, which refuses every record
because ``Record`` carries no embargo field and an undetermined embargo is
treated as an embargo (IR-250). So a live deployment returns "no readable
sources" to every question until that lands. Said here rather than left to be
discovered, because every test in ``test_ask_http.py`` opens the gate to
assert anything at all, and a reader of those tests could otherwise conclude
the shipped configuration answers questions. Nothing here works around it: the
way around a fail-closed gate is to supply the missing fact.

**What is deliberately not wired here yet.** The resilience decorators
(``apps/ai/resilience/``) are function-level helpers rather than provider
decorators, and the query-vector cache needs an ``EmbeddingSpace`` id at
construction time -- which would make building a root fail on a deployment
that has not indexed yet. Both belong here when they have a provider-shaped
form; saying so beats implying this is already the resilient path.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Optional

from apps.ai.answers.service import GroundedAnswerService
from apps.ai.providers.ports import EmbeddingProvider, LLMProvider, Reranker
from apps.ai.retrieval.degraded import DegradableRetriever, FullTextRetriever
from apps.ai.retrieval.ports import Retriever
from apps.ai.retrieval.reranking import RerankingRetriever, disclosure_permits
from apps.ai.retrieval.two_stage import TwoStageRetriever
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.resilience.rate_limit import RateLimited
from apps.records.models import Record

if TYPE_CHECKING:
    from apps.ai.memory import ConversationMemory
    from apps.ai.resolution import QuestionResolver


def _vendor_failures() -> tuple[type[BaseException], ...]:
    """What counts as "the vendor is unavailable", and so degrades.

    ``DegradableRetriever``'s own default is the circuit breaker and the rate
    limiter -- the two failures it can name without importing an adapter.
    ``VoyageError`` is the third case its docstring names and could not list,
    because the retrieval package does not depend on a vendor adapter and
    should not start. Naming it *here* is what a composition root is for: this
    module already knows which adapter is in the stack.

    Still a closed list. A ``TypeError`` from our own query is not an outage,
    and degrading on it would hide a defect behind slightly worse answers.
    """
    from apps.ai.providers.voyage import VoyageError

    return (CircuitOpen, RateLimited, VoyageError)


class CompositionRoot:
    """The assembled query lane.

    Every collaborator is optional and built lazily. Lazily because
    ``VoyageEmbeddingProvider`` reads settings in its constructor and
    ``OpenAICompatibleAdapter`` demands a key when it builds a client: a root
    that constructed them eagerly could not be built at all on a machine with
    no vendor account, which is every machine the test suite runs on.
    """

    def __init__(
        self,
        embedder: Optional[EmbeddingProvider] = None,
        reranker: Optional[Reranker] = None,
        llm: Optional[LLMProvider] = None,
        resolver: Optional["QuestionResolver"] = None,
        memory: Optional["ConversationMemory"] = None,
        permits: Callable[[Record], bool] = disclosure_permits,
        policy_enabled: bool = True,
    ) -> None:
        self._embedder = embedder
        self._reranker = reranker
        self._llm = llm
        self._resolver = resolver
        self._memory = memory
        self._permits = permits
        self._policy_enabled = policy_enabled

    # -- the vendor seams ---------------------------------------------------

    def embedder(self) -> EmbeddingProvider:
        if self._embedder is None:
            from apps.ai.indexing import build_embedding_provider

            # The same builder the indexing path uses, not a second one:
            # a query embedded by a different adapter than the corpus was is
            # the silent-disagreement failure ``EmbeddingSpace`` exists to
            # prevent, and two builders is how that starts.
            self._embedder = build_embedding_provider()
        return self._embedder

    def reranker(self) -> Reranker:
        if self._reranker is None:
            from apps.ai.providers.voyage import VoyageReranker

            self._reranker = VoyageReranker()
        return self._reranker

    def llm(self) -> LLMProvider:
        if self._llm is None:
            from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

            self._llm = OpenAICompatibleAdapter()
        return self._llm

    def resolver(self) -> Optional["QuestionResolver"]:
        """The follow-up rewriter, or ``None`` when resolution is switched off.

        Independently switchable (ADR-026 Decision 8, IR-296) behind
        ``AI_QUESTION_RESOLUTION_ENABLED`` -- a caller treats ``None`` as
        "skip resolution entirely", which is what makes retrieval quality
        with and without it measurable under ADR-023. An injected resolver
        (a test's ``QuestionResolver`` over a ``ScriptedLLM``) is used
        verbatim and bypasses the setting, the same shape every other vendor
        seam on this root uses.

        Built with the default Django cache rather than deferred like the
        query-vector cache: resolution caching needs no ``EmbeddingSpace``
        id, so there is no equivalent reason to leave it unwired.
        """
        if self._resolver is None:
            from django.conf import settings

            if not getattr(settings, "AI_QUESTION_RESOLUTION_ENABLED", True):
                return None

            from django.core.cache import cache

            from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter
            from apps.ai.resolution import QuestionResolver

            self._resolver = QuestionResolver(
                llm=OpenAICompatibleAdapter(
                    model=getattr(settings, "LLM_RESOLUTION_MODEL", None) or None
                ),
                cache=cache,
            )
        return self._resolver

    def memory(self) -> Optional["ConversationMemory"]:
        """The conversation-memory recaller, or ``None`` when off.

        Same switch shape as ``resolver()`` (``AI_CONVERSATION_MEMORY_ENABLED``,
        IR-297), but this collaborator calls no vendor, so there is no key to
        be missing.
        """
        if self._memory is None:
            from django.conf import settings

            if not getattr(settings, "AI_CONVERSATION_MEMORY_ENABLED", True):
                return None

            from apps.ai.memory import ConversationMemory

            self._memory = ConversationMemory()
        return self._memory

    def generation_configured(self) -> bool:
        """Whether a model would actually answer, without calling one.

        The root's question to answer rather than the view's, and not the
        port's: ``LLMProvider`` transports a prompt and nothing else, and
        adding "are you configured?" to it would oblige every fake to answer
        a question about a vendor account it does not have.

        A root holding an injected provider is configured by construction. The
        default one asks the adapter, which is the only thing that knows which
        setting configures it -- reading ``LLM_API_KEY`` here would be a second
        copy of that knowledge, and the copy is what goes stale.
        """
        from apps.ai.providers.openai_compatible import is_configured

        if self._llm is not None:
            return True
        return is_configured()

    # -- the stack ----------------------------------------------------------

    def retriever(self, record: Optional[Record] = None) -> Retriever:
        """The stack, optionally narrowed to one Record for this call (IR-298).

        ``record`` is a call-time argument, not a root-level setting: two
        requests through the same root can each ask for a differently-scoped
        retriever, which is what lets Paper Chat stay scoped by default and
        Ask IRIS stay unscoped, from one root. The `Retriever` port itself
        carries no such parameter -- see `TwoStageRetriever`'s docstring.
        """
        return DegradableRetriever(
            RerankingRetriever(
                TwoStageRetriever(self.embedder(), record=record),
                reranker=self.reranker(),
                policy_enabled=self._policy_enabled,
                permits=self._permits,
            ),
            fallback=FullTextRetriever(record=record),
            degrade_on=_vendor_failures(),
        )

    def answer_service(
        self, max_sources: int, record: Optional[Record] = None
    ) -> GroundedAnswerService:
        return GroundedAnswerService(
            retriever=self.retriever(record=record),
            llm=self.llm(),
            permits=self._permits,
            policy_enabled=self._policy_enabled,
            max_sources=max_sources,
            memory=self.memory(),
        )


#: The installed root, or ``None`` for the default one. Module state rather
#: than a setting: what a test needs to replace is an object holding fakes,
#: and a dotted path in settings cannot carry one.
_installed: Optional[CompositionRoot] = None


def composition_root() -> CompositionRoot:
    """The root callers should use. A function, so an override is seen.

    A view holding a module-level instance would capture whichever root
    existed at import time, which is the one thing an override must not have
    to work around.
    """
    return _installed if _installed is not None else CompositionRoot()


def composition_root_installed() -> bool:
    """Whether something has replaced the default root.

    Asked by anything that would install one *only if nobody else has* — the
    development bypass (IR-317) does, so a process that reaches
    ``AppConfig.ready()`` twice cannot reinstall a permissive root over a root
    a caller deliberately set.
    """
    return _installed is not None


def install_composition_root(root: Optional[CompositionRoot]) -> None:
    """Replace the root. ``None`` restores the default."""
    global _installed
    _installed = root


@contextmanager
def use_composition_root(root: CompositionRoot):
    """Install ``root`` for the duration of the block.

    A context manager rather than a fixture so it is usable from a management
    command or a shell session as well as a test, and so a failure inside the
    block cannot leave a fake wired into the process.
    """
    previous = _installed
    install_composition_root(root)
    try:
        yield root
    finally:
        install_composition_root(previous)
