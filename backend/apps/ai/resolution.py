"""``Q:``/``A:`` lines for a stored Turn window (IR-296, IR-297).

Question resolution itself went with Django's answer path in IR-957; the line
format stays because personal-data export and citation prompts share it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from apps.ai.models import Turn


def turn_qa_lines(turns: Sequence["Turn"]) -> list[str]:
    """``Q:``/``A:`` lines, one Turn each, in order. Shared with
    ``apps.ai.answers.citations.build_prompt`` (IR-297)."""
    lines: list[str] = []
    for turn in turns:
        lines.append(f"Q: {turn.question}")
        if turn.answer:
            lines.append(f"A: {turn.answer}")
    return lines
