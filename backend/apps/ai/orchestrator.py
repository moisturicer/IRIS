"""Between the two chat views and the answer service (IR-466, ADR-035 §6).

Answers as before, records the Turn, then hands it to the evidence shadow.
Only the chat views use this, so the AI Overview -- the answer service's third
caller -- never reaches an evidence decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

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


class ChatOrchestrator:
    def __init__(self, asked: ChatQuestion, *, max_sources: int) -> None:
        self._asked = asked
        self._routing = RoutedChat(asked, max_sources=max_sources)
        self._max_sources = max_sources

    @property
    def _service(self):
        return composition_root().answer_service(
            max_sources=self._max_sources, record=self._asked.scope_record
        )

    @property
    def metadata(self):
        return self._routing.metadata

    def answer(self, user):
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

    def answer_stream(self, user) -> Iterator:
        """The service's events; the Turn is recorded before `Done` passes
        on, and shadowed only after the reader has it."""
        asked = self._asked
        self._routing.decide(user)
        if self._routing.decision is not None:
            yield RoutingDecided(self._routing.decision)
        if self._routing.nonpassage:
            yield RetrievalStarted()
            answer = self._routing.answer(user)
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
        return record_turn(
            asked.conversation,
            asked.question,
            answer,
            asked.resolved_question,
            asked.widened,
            routing=self._routing.decision,
            listing=self._routing.listing,
        )

    def _shadow(self, turn) -> None:
        if turn is not None:
            shadow_turn(
                turn,
                history=self._asked.history,
                record_scoped=self._asked.scope_record is not None,
            )
