"""Between the two chat views and the answer service (IR-466, ADR-035 §6).

Dispatches default-off research routes, records the Turn and its decision,
then hands it to the evidence shadow.
Only the chat views use this, so the AI Overview -- the answer service's third
caller -- never reaches an evidence decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

from apps.ai.admission import scope as admission_scope
from apps.ai.answers.events import Done, RetrievalStarted
from apps.ai.routing.chat import RoutedChat, RoutingDecided
from apps.ai.composition import composition_root
from apps.ai.conversations import record_turn
from apps.ai.evidence.shadow import shadow_turn
from apps.ai.models import Conversation


@dataclass(frozen=True)
class ChatQuestion:
    """One parsed, validated `/ask/`-shaped request (IR-326)."""

    conversation: Optional[Conversation]
    question: str
    effective_question: str
    resolved_question: Optional[str]
    history: list
    widened: bool
    scope_record: object
    route_override: Optional[str] = None
    override_turn_id: Optional[int] = None


class ChatOrchestrator:
    def __init__(self, asked: ChatQuestion, *, max_sources: int) -> None:
        self._asked = asked
        self._root = composition_root()
        self._routing = RoutedChat(asked, root=self._root, max_sources=max_sources)
        self._max_sources = max_sources
        self._turn_id = None
        # Per-run provider caps sum over this. A queued question's own run,
        # opened around it by its worker, takes precedence (IR-545).
        self._run = admission_scope.new_run()

    @property
    def _service(self):
        return self._root.answer_service(
            max_sources=self._max_sources, record=self._asked.scope_record
        )

    @property
    def metadata(self):
        metadata = self._routing.metadata
        return {**metadata, "turn_id": self._turn_id} if metadata and self._turn_id else metadata

    def answer(self, user):
        with admission_scope.workload("chat"), admission_scope.run(self._run):
            return self._answer(user)

    def answer_stream(self, user) -> Iterator:
        """The service's events, each step charged to this question's run
        and to the chat lane unless a research lane says otherwise (IR-545)."""
        return admission_scope.stepwise(
            self._answer_stream(user),
            lambda: admission_scope.workload("chat"),
            lambda: admission_scope.run(self._run),
        )

    def _answer(self, user):
        asked = self._asked
        routed = self._routing.answer(user)
        answer = routed if routed is not None else self._service.answer(
            asked.effective_question,
            user,
            conversation=asked.conversation,
            history=asked.history,
        )
        self._shadow(self._record(answer))
        return answer

    def _answer_stream(self, user) -> Iterator:
        """The service's events; the Turn is recorded before `Done` passes
        on, and shadowed only after the reader has it."""
        asked = self._asked
        self._routing.decide(user)
        if self._routing.decision is not None:
            yield RoutingDecided(self._routing.decision)
        if self._routing.nonpassage:
            yield RetrievalStarted()
            answer = yield from self._routing.events(user)
            turn = self._record(answer)
            try:
                yield Done(answer)
            finally:
                self._shadow(turn)
            return
        for event in self._service.answer_stream(
            asked.effective_question,
            user,
            conversation=asked.conversation,
            history=asked.history,
            on_interrupted=self._record_partial,
        ):
            if not isinstance(event, Done):
                yield event
                continue
            turn = self._record(event.answer)
            try:
                yield event
            finally:
                self._shadow(turn)

    def _record_partial(self, answer) -> None:
        self._shadow(self._record(answer))

    def _record(self, answer):
        asked = self._asked
        if asked.conversation is None:
            # A one-off question stores nothing, so there is nothing to shadow.
            return None
        turn = record_turn(
            asked.conversation,
            asked.question,
            answer,
            asked.resolved_question,
            asked.widened,
            routing=self._routing.decision,
            listing=self._routing.listing,
            research=self._routing.research,
            guard=self._record_guard(answer),
        )
        self._turn_id = turn.pk
        return turn

    def _record_guard(self, answer):
        """What the Turn's write happens inside. Nothing here; a queued run
        fences itself with it (IR-544, `apps.ai.durable`)."""
        return None

    def _shadow(self, turn) -> None:
        if turn is not None:
            shadow_turn(
                turn,
                history=self._asked.history,
                record_scoped=self._asked.scope_record is not None,
            )
