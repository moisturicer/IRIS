"""Conversation state and bounded context for follow-ups (IR-592, spec §4).

What the reader was shown, in the order shown, and what they chose from it.
Stored as record ids under the Conversation; every read rechecks visibility,
so a revoked paper keeps its position and resolves to nothing.

Only a delivered (`generated`) Turn advances the state, inside the same
transaction that writes it, so a fenced or rolled-back attempt changes
nothing. A commit made against an older revision does not apply its
references: it keeps the newer choices and clears the displayed order.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Iterable, Optional

from django.conf import settings

from apps.ai.answers.citations import GENERATED
from apps.ai.history import (
    HISTORY_CANDIDATE_LIMIT,
    estimate_tokens,
    history_window,
    readable_turns,
)
from apps.ai.models import ChunkSet, Conversation, ConversationState, Turn, TurnCitation
from apps.records.models import Record

logger = logging.getLogger(__name__)

RECORDED = ConversationState.RECORDED
CONFLICT = ConversationState.CONFLICT
#: No state row yet: rebuilt from stored Turns, never written by a read.
RECONSTRUCTED = "reconstructed"

DEFAULT_EARLIER_TOKEN_BUDGET = 500


def _ids(values: Iterable) -> tuple:
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True)
class ContextState:
    """One revision's value. Transitions return a new value."""

    topic: str = ""
    filters: dict = field(default_factory=dict)
    #: Displayed order. A slot is ``None`` once its paper is unreadable.
    presented: tuple = ()
    selected: tuple = ()
    excluded: tuple = ()
    pending_clarification: Optional[dict] = None
    request: str = ""
    retrieval_query: str = ""

    def asked(self, request: str, retrieval_query: str = "") -> "ContextState":
        return replace(self, request=request, retrieval_query=retrieval_query or "")

    def with_topic(self, topic: str, filters: Optional[dict] = None) -> "ContextState":
        topic = topic.strip()
        if topic.casefold() == self.topic.casefold():
            return replace(self, topic=topic, filters=self.filters if filters is None else filters)
        return replace(
            self, topic=topic, filters=filters or {}, selected=(), excluded=(),
            pending_clarification=None,
        )

    def presenting(self, record_ids: Iterable[int]) -> "ContextState":
        return replace(self, presented=_ids(record_ids), pending_clarification=None)

    def selecting(self, record_ids: Iterable[int]) -> "ContextState":
        chosen = _ids(record_ids)
        shown = {pk for pk in self.presented if pk is not None} | set(self.selected)
        if not chosen or not set(chosen) <= shown:
            raise ValueError("selection_not_shown")
        return replace(self, selected=chosen)

    def selecting_ordinals(self, *ordinals: int) -> "ContextState":
        chosen = []
        for n in ordinals:
            pk = self.presented[n - 1] if 1 <= n <= len(self.presented) else None
            if pk is None:
                raise ValueError("ordinal_unresolved")
            chosen.append(pk)
        return self.selecting(chosen)

    def excluding(self, record_ids: Iterable[int]) -> "ContextState":
        return replace(self, excluded=_ids((*self.excluded, *record_ids)))

    def find_another(self) -> "ContextState":
        return self.excluding(pk for pk in self.presented if pk is not None)

    def clarifying(self, question: str, options: Iterable[int] = ()) -> "ContextState":
        return replace(
            self, pending_clarification={"question": question, "options": list(_ids(options))}
        )

    def record_ids(self) -> set:
        options = (self.pending_clarification or {}).get("options", [])
        return {pk for pk in (*self.presented, *self.selected, *self.excluded, *options)
                if pk is not None}


@dataclass(frozen=True)
class Snapshot:
    """A reader's view of the state at one revision, revocation applied."""

    revision: int
    basis: str
    state: ContextState
    answer_turn_id: Optional[int] = None
    #: Readable papers whose active source changed since the commit.
    stale_sources: frozenset = frozenset()

    def ordinal(self, n: int) -> Optional[int]:
        """The ``n``th paper shown (1-based), or ``None``. Never a candidate
        that was retrieved and not displayed."""
        presented = self.state.presented
        return presented[n - 1] if 1 <= n <= len(presented) else None


def _from_row(row: ConversationState) -> ContextState:
    return ContextState(
        topic=row.topic, filters=row.filters or {}, presented=tuple(row.presented),
        selected=tuple(row.selected), excluded=tuple(row.excluded),
        pending_clarification=row.pending_clarification, request=row.request,
        retrieval_query=row.retrieval_query,
    )


def derive(previous: ContextState, turn: Turn, *, cited: Iterable[int],
           listing=None, comparison=None) -> ContextState:
    """The next state for a Turn whose caller named none.

    A listing or comparison fixes the displayed order. An answer citing only
    papers already shown (simplify, explain) keeps it; one citing anything
    else clears it, because its order was never established.
    """
    state = previous.asked(turn.question, turn.resolved_question)
    if listing:
        return state.presenting(row["record_id"] for row in listing.get("records", []))
    versions = (comparison or {}).get("source_versions") or []
    if versions:
        pair = [row["record_id"] for row in versions]
        return state.presenting(pair).selecting(pair)
    shown = {pk for pk in previous.presented if pk is not None}
    if not set(cited) <= shown:
        return state.presenting(())
    return state


def _cited_by_turn(turn_ids) -> dict:
    cited = defaultdict(list)
    for turn_id, record_id in (TurnCitation.objects.filter(turn_id__in=turn_ids)
                               .order_by("marker", "id").values_list("turn_id", "record_id")):
        cited[turn_id].append(record_id)
    return cited


def reconstruct(conversation: Conversation, *, before: Optional[int] = None) -> ContextState:
    """State folded from delivered Turns written before IR-592.

    Topic is never guessed, and a passage answer's citations establish no
    order, so ambiguous history stays unresolved.
    """
    turns = conversation.turns.filter(state=GENERATED)
    if before is not None:
        turns = turns.filter(pk__lt=before)
    turns = list(turns.only("pk", "question", "resolved_question", "listing", "comparison"))
    cited = _cited_by_turn([turn.pk for turn in turns])
    state = ContextState()
    for turn in turns:
        state = derive(state, turn, cited=cited[turn.pk], listing=turn.listing,
                       comparison=turn.comparison)
    return state


def current_revision(conversation: Optional[Conversation]) -> Optional[int]:
    """The revision a new question builds on, read before its first model call."""
    if conversation is None:
        return None
    return (ConversationState.objects.filter(conversation=conversation)
            .values_list("revision", flat=True).first()) or 0


def _versions(record_ids) -> dict:
    return {
        record_id: content_hash
        for record_id, content_hash in ChunkSet.objects.filter(
            record_id__in=record_ids, is_active=True
        ).values_list("record_id", "content_hash")
    }


def commit(conversation: Conversation, turn: Turn, *, context: Optional[ContextState] = None,
           expected_revision: Optional[int] = None, cited: Iterable[int] = (),
           listing=None, comparison=None) -> Optional[int]:
    """Advance the state for ``turn``. Call inside the Turn's transaction.

    Returns the new revision, or ``None`` for an undelivered Turn.
    """
    if turn.state != GENERATED:
        return None
    Conversation.objects.select_for_update().filter(pk=conversation.pk).first()
    row = ConversationState.objects.filter(conversation=conversation).first()
    if row is None:
        row = ConversationState(conversation=conversation)
        base = reconstruct(conversation, before=turn.pk)
    else:
        base = _from_row(row)

    if expected_revision is not None and expected_revision != row.revision:
        logger.warning(
            "conversation=%s turn=%s built on revision %s, now %s; not applying its references",
            conversation.pk, turn.pk, expected_revision, row.revision,
        )
        new, basis = replace(base, presented=(), pending_clarification=None), CONFLICT
    elif context is not None:
        new, basis = context, RECORDED
    else:
        new = derive(base, turn, cited=cited, listing=listing, comparison=comparison)
        basis = RECORDED
    new = new.asked(turn.question, turn.resolved_question)

    row.revision += 1
    row.basis = basis
    row.answer_turn = turn
    row.request, row.retrieval_query = new.request, new.retrieval_query
    row.topic = new.topic[:200]
    row.filters = dict(new.filters)
    row.presented, row.selected, row.excluded = (
        list(new.presented), list(new.selected), list(new.excluded)
    )
    row.pending_clarification = new.pending_clarification
    shown = [pk for pk in (*new.presented, *new.selected) if pk is not None]
    row.source_versions = {str(pk): version for pk, version in _versions(shown).items()}
    row.save()
    Turn.objects.filter(pk=turn.pk).update(context_revision=row.revision)
    turn.context_revision = row.revision
    return row.revision


def _visible(user, record_ids) -> set:
    if not record_ids:
        return set()
    return set(Record.objects.visible_to(user).filter(pk__in=record_ids)
               .values_list("pk", flat=True))


def snapshot(conversation: Conversation, user) -> Snapshot:
    """The state as ``user`` may see it now. Reads never write."""
    row = ConversationState.objects.filter(conversation=conversation).first()
    if row is None:
        state, revision, basis, answer_turn_id, versions = (
            reconstruct(conversation), 0, RECONSTRUCTED, None, {}
        )
    else:
        state, revision, basis, answer_turn_id, versions = (
            _from_row(row), row.revision, row.basis, row.answer_turn_id, row.source_versions
        )

    visible = _visible(user, state.record_ids())
    pending = state.pending_clarification
    if pending is not None:
        pending = {**pending, "options": [pk for pk in pending.get("options", []) if pk in visible]}
    state = replace(
        state,
        presented=tuple(pk if pk in visible else None for pk in state.presented),
        selected=tuple(pk for pk in state.selected if pk in visible),
        excluded=tuple(pk for pk in state.excluded if pk in visible),
        pending_clarification=pending,
    )
    stale = frozenset()
    if versions:
        shown = {pk for pk in (*state.presented, *state.selected) if pk is not None}
        current = _versions(shown)
        stale = frozenset(pk for pk in shown
                          if str(pk) in versions and versions[str(pk)] != current.get(pk))
    return Snapshot(revision, basis, state, answer_turn_id, stale)


def reissue_handles(run, snap: Snapshot) -> dict:
    """This run's handles for the state's papers; positions kept, and an
    unreadable or undisclosable paper gets ``None`` rather than a handle."""
    from apps.ai.research.tools.common import collect_record, disclosable

    allowed = disclosable(run.ctx, snap.state.record_ids())

    def handle(pk):
        return collect_record(run.ledger, allowed[pk]).handle if pk in allowed else None

    def handles(ids):
        return [h for h in (handle(pk) for pk in ids) if h]

    pending = snap.state.pending_clarification
    return {
        "presented": [handle(pk) for pk in snap.state.presented],
        "selected": handles(snap.state.selected),
        "excluded": handles(snap.state.excluded),
        "pending_clarification": None if pending is None else {
            "question": pending["question"], "options": handles(pending.get("options", [])),
        },
    }


@dataclass(frozen=True)
class EarlierTurn:
    """A lossy line for a Turn older than the verbatim window, with what it
    depended on, so revocation can drop it."""

    turn_id: int
    question: str
    depends_on: tuple


@dataclass(frozen=True)
class ConversationContext:
    request: str
    retrieval_query: str
    snapshot: Snapshot
    recent: tuple
    earlier: tuple


def _earlier_budget() -> int:
    return int(getattr(settings, "AI_HISTORY_EARLIER_TOKEN_BUDGET", DEFAULT_EARLIER_TOKEN_BUDGET))


def conversation_context(conversation: Conversation, user, request: str,
                         retrieval_query: str = "") -> ConversationContext:
    """Bounded context for the next question: the request as typed, the
    state, the verbatim window, then older questions newest-first until the
    earlier budget runs out. Rebuilt per call from what is readable now."""
    candidates = list(
        conversation.turns.in_model_history().order_by("-id")[:HISTORY_CANDIDATE_LIMIT]
    )[::-1]
    readable = readable_turns(candidates, user)
    recent = history_window(readable)
    first_recent = recent[0].pk if recent else None
    older = [t for t in readable if first_recent is None or t.pk < first_recent]
    cited = _cited_by_turn([t.pk for t in older])

    earlier, spent, budget = [], 0, _earlier_budget()
    for turn in reversed(older):
        cost = estimate_tokens(turn.question)
        if spent + cost > budget:
            break
        earlier.append(EarlierTurn(turn.pk, turn.question, _ids(cited[turn.pk])))
        spent += cost
    return ConversationContext(
        request=request, retrieval_query=retrieval_query or "",
        snapshot=snapshot(conversation, user), recent=tuple(recent),
        earlier=tuple(reversed(earlier)),
    )
