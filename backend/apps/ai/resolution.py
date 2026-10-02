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

Resolution runs on every follow-up (ADR-026 §8, amended 2026-10-02, IR-445).
A word check used to skip it when the question held no pronoun, and that
failed into a refusal: "give me a longer explanation" has no topic in it, so
retrieval searched it as typed. What is left of cost control is the first-Turn
skip, the cache, and the separately configured small model; a failed call
falls back to the raw question rather than erroring.

**How much history the prompt holds is not decided here** (IR-449). It was,
as `MAX_HISTORY_TURNS = 6`; it is now a token budget in
`apps.ai.history`, applied once by the caller and shared with the answering
prompt. This module renders the window it is given.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, MutableMapping, Optional, Sequence

from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.resilience.query_cache import normalize_question

if TYPE_CHECKING:
    from apps.ai.models import Turn
    from apps.ai.providers.ports import LLMProvider

logger = logging.getLogger(__name__)

RESOLUTION_SYSTEM_PROMPT = (
    "Rewrite the follow-up question as a standalone question, using the "
    "conversation so far to fill in what it refers to. Keep it a question. "
    "Output only the rewritten question and nothing else -- no preamble, no "
    "quotation marks, no explanation."
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

    ``turns`` is the window as given, rendered whole. **It is not sliced
    here** (IR-449): the verbatim window is a token budget, filled once by
    `apps.ai.history.history_window` and handed to this prompt and the
    answering prompt alike, so neither can disagree with the other about
    how much history there was. This function used to keep its own
    `MAX_HISTORY_TURNS = 6`, which made the bound invisible to the caller
    and unrelated to the size of what it bounded.
    """
    lines = ["Conversation so far:"]
    lines.extend(turn_qa_lines(turns))
    lines.append("")
    lines.append(f"Follow-up question: {question}")
    return "\n".join(lines)


def resolution_cache_key(question: str, turns: Sequence["Turn"]) -> str:
    """Cache key for one (question, history) pair.

    Keyed like a query embedding (``apps.ai.resilience.query_cache``): the
    same follow-up after the same history should cost one model call, not
    one per asker.

    **Computed from the Turns actually used** (IR-449). A token budget makes
    the window variable, so which Turn ids are folded in is now a property
    of this request rather than a fixed six, and this function must be given
    the same window the prompt was built from -- which is why it takes the
    window rather than the Conversation's history and slices it itself.

    A Turn contributes its id *and* the length of its question and answer.
    The id alone was exact while the window was whole Turns; the newest Turn
    can now arrive truncated, and two different truncations of one Turn are
    two different prompts that must not share an answer. Lengths are enough
    to tell them apart and stay cheap -- a Turn's text never changes once
    written, so the same (id, lengths) triple is the same text.
    """
    history = ",".join(
        f"{turn.pk}:{len(turn.question or '')}:{len(turn.answer or '')}"
        for turn in turns
    )
    digest = hashlib.sha256(
        f"{history}\u0000{normalize_question(question)}".encode("utf-8")
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
        no history to resolve against, an empty model reply, and a model call
        that failed. All three take the same fallback (ADR-026): retrieve on
        the raw question.
        """
        if not turns:
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
