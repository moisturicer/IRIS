"""Resolving a follow-up into a standalone question before retrieval (IR-296, ADR-026).

"what about its limitations?" has no subject on its own -- retrieval finds
every paper's future-work section. When a Conversation has history, a small
model call rewrites the question into one that stands alone, and retrieval
runs on the rewrite, not on what was typed.

A module, not a port (IR-294 Testing Decisions: "No new seams. Resolution
is a module, not a port: one implementation is a hypothetical seam..."):
resolution has one implementation, and it is fully exercisable through HTTP
with a fake model beneath it -- exactly what a hypothetical second
implementation would be buying nothing for. It still composes around the
retriever the way ADR-026 Decision 5 asks of every enhancement technique --
a swappable collaborator on `CompositionRoot`, switched off independently of
the others -- without being a second `Reranker`-shaped ABC no second adapter
would ever implement.

**Two guards keep most Turns free of this cost** (ADR-026 Decision 8):
``has_back_reference`` decides without a model call whether resolution could
possibly matter, and a failed model call falls back to the raw question
rather than erroring. Both are cost guarantees, not correctness ones, and
both fail soft in the direction of "answer with what was typed".
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING, MutableMapping, Optional, Sequence

from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.resilience.query_cache import normalize_question

if TYPE_CHECKING:
    from apps.ai.models import Turn
    from apps.ai.providers.ports import LLMProvider

logger = logging.getLogger(__name__)

#: How many of the conversation's most recent Turns go into the resolution
#: prompt. Bounded rather than the whole history, for the same reason the
#: answering prompt only takes recent Turns verbatim (ADR-026 Decision 6):
#: reaching further back than this is memory's job (IR-297), not
#: resolution's.
MAX_HISTORY_TURNS = 6

#: The cheap word check that decides whether resolution runs at all. Not an
#: attempt at grammatical correctness -- a false positive costs one
#: avoidable model call, a false negative costs nothing new (the question
#: retrieves on its own text, exactly as it would with no resolution at all)
#: -- so the list is deliberately short and deliberately loose.
_BACK_REFERENCE_WORDS = frozenset(
    {
        "it", "its", "it's", "this", "that", "these", "those",
        "they", "them", "their", "theirs",
        "he", "him", "his", "she", "her", "hers",
    }
)

_WORD = re.compile(r"[a-z']+")

RESOLUTION_SYSTEM_PROMPT = (
    "Rewrite the follow-up question as a standalone question, using the "
    "conversation so far to fill in what it refers to. Keep it a question. "
    "Output only the rewritten question and nothing else -- no preamble, no "
    "quotation marks, no explanation."
)


def has_back_reference(question: str) -> bool:
    """Whether ``question`` contains a word that could refer back to something.

    Decided by vocabulary, not a model call -- that is the whole point. A
    missed back-reference is a soft failure: the question retrieves on its
    own text, exactly as it would with no resolution at all.
    """
    return any(
        word in _BACK_REFERENCE_WORDS for word in _WORD.findall(question.lower())
    )


def turn_qa_lines(turns: Sequence["Turn"]) -> list[str]:
    """``Q:``/``A:`` lines, one Turn each, in order. Shared with
    ``apps.ai.answers.citations.build_prompt`` (IR-297)."""
    lines: list[str] = []
    for turn in turns:
        lines.append(f"Q: {turn.question}")
        if turn.answer:
            lines.append(f"A: {turn.answer}")
    return lines


def build_resolution_prompt(question: str, turns: Sequence["Turn"]) -> str:
    """The user turn: the recent conversation, then the question to resolve.

    Only the most recent ``MAX_HISTORY_TURNS`` -- see the module docstring.
    """
    recent = list(turns)[-MAX_HISTORY_TURNS:]
    lines = ["Conversation so far:"]
    lines.extend(turn_qa_lines(recent))
    lines.append("")
    lines.append(f"Follow-up question: {question}")
    return "\n".join(lines)


def resolution_cache_key(question: str, turns: Sequence["Turn"]) -> str:
    """Cache key for one (question, history) pair.

    Keyed like a query embedding (``apps.ai.resilience.query_cache``): the
    same follow-up after the same history should cost one model call, not
    one per asker. History is folded in by Turn id rather than by text --
    cheaper to hash and just as exact, since a Turn's question and answer
    never change once written.
    """
    recent = list(turns)[-MAX_HISTORY_TURNS:]
    history_ids = ",".join(str(turn.pk) for turn in recent)
    digest = hashlib.sha256(
        f"{history_ids}\u0000{normalize_question(question)}".encode("utf-8")
    ).hexdigest()
    return f"iris:qres:{digest}"


class QuestionResolver:
    """Rewrites a follow-up into a standalone question, guarded and cached.

    Holds the two collaborators the guards need: the small model
    (independently configured, ADR-026 Decision 8) and the cache. Not a
    port -- see the module docstring.
    """

    def __init__(
        self,
        llm: "LLMProvider",
        cache: Optional[MutableMapping] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self._llm = llm
        self._cache = cache
        self._ttl = ttl_seconds

    def resolve(self, question: str, turns: Sequence["Turn"]) -> Optional[str]:
        """The standalone question, or ``None`` to mean "use ``question`` as is".

        ``None`` covers three cases the caller does not need to tell apart:
        no history to resolve against, no back-reference to resolve, and a
        model call that failed. All three take the same fallback (ADR-026):
        retrieve on the raw question, exactly as today.
        """
        if not turns or not has_back_reference(question):
            return None

        key = resolution_cache_key(question, turns) if self._cache is not None else None
        if key is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        try:
            raw = self._llm.generate(
                system=RESOLUTION_SYSTEM_PROMPT,
                user=build_resolution_prompt(question, turns),
            )
        except LLMUnavailable as exc:
            logger.warning("question resolution unavailable: %s", exc)
            return None

        resolved = raw.strip()
        if not resolved:
            return None

        if key is not None:
            # Django's cache API takes a timeout; a plain mapping does not.
            # Support both so tests can pass a dict without a shim.
            try:
                self._cache.set(key, resolved, self._ttl)  # type: ignore[attr-defined]
            except (AttributeError, TypeError):
                self._cache[key] = resolved
        return resolved
