"""What the reranker reads for each candidate (IR-1125, ADR-033 §5).

A chunk has two texts: ``embedded`` (trail, words, and a Figure's AI-written
description), which vector search reads, and ``content`` (only what the paper
printed), which readers see. An uncaptioned Figure has blank ``content``, so
reading only ``content`` makes it uncitable. Each mode is one IR-1125 arm.

Pure: no Django, no database, no vendor.
"""

from __future__ import annotations

from apps.ai.chunking.outline import PATH_SEPARATOR, TRAIL_JOIN

TODAY = "today"
EMBEDDED = "embedded"
DESCRIBED = "described"
FALLBACK = "fallback"

#: In IR-1125's arm order: today, A, B, C.
READS = (TODAY, EMBEDDED, DESCRIBED, FALLBACK)
ARM_LABELS = {TODAY: "today", EMBEDDED: "A", DESCRIBED: "B", FALLBACK: "C"}

#: How arm B marks text no author wrote.
AI_LABEL = "AI-written description:"

FIGURE = "image"


def _body(passage) -> str:
    """The embedded text without its section trail."""
    text = passage.embedded or ""
    trail = PATH_SEPARATOR.join(passage.context_path or ())
    prefix = f"{trail}{TRAIL_JOIN}" if trail else ""
    if prefix and text.startswith(prefix):
        return text[len(prefix):]
    return "" if text == trail else text


def is_figure(passage) -> bool:
    return tuple(passage.element_kinds or ()) == (FIGURE,)


def ai_description(passage) -> str:
    """A lone Figure chunk's description, recovered from its embedded text.

    Empty for any other chunk, or when the body does not begin with the shown
    text: then nothing can be told apart from what the paper printed.
    """
    if not is_figure(passage):
        return ""
    body = _body(passage).strip()
    shown = (passage.content or "").strip()
    if not body.startswith(shown):
        return ""
    return body[len(shown):].strip()


def reranker_text(passage, reads: str) -> str:
    """The text ``passage`` is reranked by under ``reads``; blank drops it."""
    shown = passage.content or ""
    if reads == TODAY:
        return shown
    if reads == EMBEDDED:
        return passage.embedded or shown
    if reads == FALLBACK:
        return shown if shown.strip() else (passage.embedded or "")
    if reads == DESCRIBED:
        description = ai_description(passage)
        if not description:
            return shown
        labelled = f"{AI_LABEL} {description}"
        return f"{shown.strip()}\n\n{labelled}" if shown.strip() else labelled
    raise ValueError(f"reranker reads one of {', '.join(READS)}, not {reads!r}")


def changes_expected(passage, reads: str) -> bool:
    """Whether ``reads`` is meant to differ from today on ``passage``.

    Decision rule 4: an arm that differs where this says it should not is a
    defect, not a result. Arm A is meant to change every chunk.
    """
    if reads == TODAY:
        return False
    if reads == EMBEDDED:
        return True
    if reads == FALLBACK:
        return not (passage.content or "").strip()
    return bool(ai_description(passage))
