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
#:
#: The bracket class is wider than the prompt asks for because a model is not
#: bound by it. gpt-oss-120b, the configured default, answers with the CJK
#: lenticular form -- `【1】` -- and against an ASCII-only pattern every
#: citation silently failed to resolve: zero citations, `is_grounded` false,
#: and the raw marker left sitting in the rendered text. Fullwidth brackets
#: appear for the same reason. `keep` re-emits `[n]`, so whatever comes in,
#: what a reader sees is canonical.
#:
#: Three balanced alternatives rather than one wide opening class and one wide
#: closing class: the cheap version also matches `[1】` and `【1]`, which no
#: model produces and which a reader would have to squint at to call a
#: citation. Each branch captures the digits, so exactly one group is ever
#: populated -- `keep` takes whichever that is.
_NUMBERS = r"\d+(?:\s*,\s*\d+)*"
_MARKER = re.compile(
    rf"\[\s*({_NUMBERS})\s*\]"
    rf"|【\s*({_NUMBERS})\s*】"
    rf"|［\s*({_NUMBERS})\s*］"
)

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
    """One resolved citation: what the marker pointed at.

    Carries the **quoted text** as well as the ids (IR-284). A citation whose
    whole content is a record id asks a reader to go and find the sentence
    themselves in a fifty-page PDF, which is the verifiability chunk-level
    retrieval was built for and did not deliver. The text is already in hand
    here -- it is the chunk that was put in the prompt -- so resolving it
    later would be a second query and a second chance to resolve it wrongly.

    ``text`` is the chunk's ``content``, never its ``text``: ``content`` is
    the reader-facing form, and ``text`` is what the vector was computed from.
    Quoting the latter would show a reader a normalized string that is not
    quite what the paper says.
    """

    marker: int
    chunk_id: int
    record_id: int
    record_title: str
    source_page: int | None
    text: str
    context_path: tuple[str, ...]


#: What produced this answer. Strings rather than an enum for the reason
#: `apps/ai/retrieval/ports.py` gives for its retrieval modes: this crosses
#: into an API response and a log line, where a name is what is wanted.
#:
#: The distinction the wire needs and the text cannot carry. A caller must be
#: able to tell "a model wrote this" from "no model was reachable" and from
#: "nothing was found", and comparing the text against a constant to find out
#: is a coupling that breaks the first time the wording is improved.
GENERATED = "generated"
NO_SOURCES = "no_sources"
UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    citations: tuple[Citation, ...]
    degraded: bool = False
    state: str = GENERATED

    #: The passages the answer was grounded in -- every one that went into
    #: the prompt, not only the ones the model cited. Carried on the answer
    #: because ADR-008 requires that a vendor failure still returns sources:
    #: retrieval worked, so a reader gets passages to read themselves rather
    #: than a sentence nobody wrote. An answer that dropped them would leave
    #: the caller nothing to show.
    sources: tuple[RetrievedChunk, ...] = ()

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
        # Exactly one alternative in `_MARKER` matched, so exactly one group is
        # non-None; which bracket style it came from does not matter past here.
        digits = next(g for g in match.groups() if g is not None)
        numbers = [int(n) for n in digits.replace(" ", "").split(",")]
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
                    text=chunk.content,
                    context_path=tuple(chunk.context_path or ()),
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
