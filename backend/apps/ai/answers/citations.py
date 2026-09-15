"""Numbering sources into a prompt, and parsing the markers back (IR-131).

Pure: no vendor, no database, no clock. This is where the correctness of a
citation lives, so it is the part that must be testable without an account.

Two halves that have to agree:

* **assembly** numbers the retrieved chunks and writes them into the prompt;
* **parsing** maps the markers in the model's reply back to the chunk, record
  and page each one came from.

A marker that does not resolve is **dropped**, never rendered. A citation
pointing at nothing is worse than no citation: it looks like evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from apps.ai.retrieval.ports import RetrievedChunk

#: Inline markers: [1], [2]. Also matches [1, 2] and [1][2], which models
#: produce whether or not the prompt asks for them.
_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

SYSTEM_PROMPT = (
    "You are IRIS, the research assistant for Cebu Institute of Technology - "
    "University.\n"
    "Answer ONLY from the numbered sources below. Cite them inline as [1], [2], "
    "matching the numbers given.\n"
    "If the sources do not contain the answer, say so plainly instead of "
    "guessing.\n"
    "Never invent a title, author, finding or number. Be concise and factual."
)


@dataclass(frozen=True)
class Citation:
    """One resolved citation: what the marker pointed at."""

    marker: int
    chunk_id: int
    record_id: int
    record_title: str
    source_page: int | None


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    citations: tuple[Citation, ...]
    degraded: bool = False

    @property
    def is_grounded(self) -> bool:
        """Whether the answer actually cited anything.

        An uncited answer is not necessarily wrong -- "the sources do not cover
        this" is the correct response to an unanswerable question -- but a
        caller should be able to tell the two apart before presenting it as
        evidence.
        """
        return bool(self.citations)


def build_prompt(question: str, chunks: Sequence[RetrievedChunk]) -> str:
    """The user turn: the question, then the numbered sources.

    Numbered from 1 in the order given, deterministically, because the model is
    told to cite by those numbers and parsing maps them straight back by index.
    A shuffled or reused numbering would silently attach the wrong citation to
    the right sentence.

    Each source carries its context path, so the model can see which section a
    passage came from -- the same trail that disambiguates two theses with an
    identically titled section (IR-112).
    """
    lines = [f"Question: {question}", "", "Sources:"]
    for number, chunk in enumerate(chunks, start=1):
        trail = " > ".join(chunk.context_path) if chunk.context_path else chunk.record_title
        lines.append(f"[{number}] {trail}")
        lines.append(chunk.content)
        lines.append("")
    return "\n".join(lines).strip()


def parse_citations(
    answer: str, chunks: Sequence[RetrievedChunk]
) -> tuple[str, tuple[Citation, ...]]:
    """Resolve the markers in ``answer`` against the chunks it was given.

    Returns the answer text and the citations that resolved, in first-mention
    order and without duplicates -- a model citing [1] four times means one
    source, not four.

    **A marker outside the supplied range is dropped from the text.** Models
    invent [7] when handed four sources, and rendering it would show a reader
    a citation that points at nothing, which reads as evidence. Dropping it
    leaves the sentence, which is still supported by whatever else it cites.
    """
    resolved: list[Citation] = []
    seen: set[int] = set()

    def keep(match: re.Match) -> str:
        numbers = [int(n) for n in match.group(1).replace(" ", "").split(",")]
        valid = [n for n in numbers if 1 <= n <= len(chunks)]
        for number in valid:
            if number in seen:
                continue
            seen.add(number)
            chunk = chunks[number - 1]
            resolved.append(
                Citation(
                    marker=number,
                    chunk_id=chunk.chunk_id,
                    record_id=chunk.record_id,
                    record_title=chunk.record_title,
                    source_page=chunk.source_page,
                )
            )
        if not valid:
            return ""
        return "".join(f"[{n}]" for n in valid)

    cleaned = _MARKER.sub(keep, answer)
    # Dropping a marker can leave a doubled space or a space before a full
    # stop; tidy those rather than shipping the seam.
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned).strip()

    resolved.sort(key=lambda c: c.marker)
    return cleaned, tuple(resolved)
