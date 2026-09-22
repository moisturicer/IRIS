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
from typing import TYPE_CHECKING, Optional, Sequence

from apps.ai.resolution import turn_qa_lines
from apps.ai.retrieval.ports import RetrievedChunk

if TYPE_CHECKING:
    from apps.ai.models import Turn

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
#:
#: `_SUFFIX` tolerates trailing content between the number and the close --
#: observed live, 2026-09-20: gpt-oss-120b sometimes appends an OpenAI-style
#: file/line-range suffix to a lenticular marker, `【1†L1-L5】` rather than
#: `【1】`. Against the pattern with no suffix allowance, every citation in an
#: answer using that form resolved to nothing: zero citations, and the raw
#: marker left sitting in the text a reader sees.
#:
#: **Every bracket character is excluded, opening as well as closing, and the
#: length is bounded.** Excluding only the closing brackets is the obvious
#: version and it is wrong: on an unclosed marker the suffix runs straight
#: across the prose to the next close, so
#: `A【1†L1-L5 and more prose 【2】` resolved to `A[1]` -- the model's own
#: words deleted from what the reader sees, and the genuine `【2】` swallowed.
#: Dropping a citation is this module's stated failure direction; eating a
#: sentence is not. A real suffix is under ten characters (`†L13-L16`), so 64
#: is generous even for a filename-bearing variant while keeping the damage
#: from any pathological input bounded.
_NUMBERS = r"\d+(?:\s*,\s*\d+)*"
_SUFFIX = r"[^\[\]【】［］]{0,64}"
_MARKER = re.compile(
    rf"\[\s*({_NUMBERS})\s*{_SUFFIX}\]"
    rf"|【\s*({_NUMBERS})\s*{_SUFFIX}】"
    rf"|［\s*({_NUMBERS})\s*{_SUFFIX}］"
)

#: **This instruction is noise reduction, not enforcement.** It already said
#: "cite as [1], [2]" when the model emitted `【1】` (IR-131), and again when it
#: emitted `【1†L1-L5】` (2026-09-20). A prompt is a nudge; the model's trained
#: habits win often enough that the parser below, and the telemetry in
#: `answers/service.py`, are what actually hold the line. Tightening the
#: wording here is worth a little -- it costs nothing and may lower the rate --
#: but it is never grounds for narrowing `_MARKER` back down.
SYSTEM_PROMPT = (
    "You are IRIS, the research assistant for Cebu Institute of Technology - "
    "University.\n"
    "Answer ONLY from the numbered sources below. Cite them inline as [1], [2], "
    "matching the numbers given.\n"
    "Write a citation as a square bracket, the source number, and a closing "
    "square bracket, with nothing else inside: [1] or [2]. Do not add page or "
    "line references, file names, or any other characters inside the brackets, "
    "and do not use any other bracket style.\n"
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

    #: The vector used to search the corpus, and its space (IR-297) -- so
    #: `record_turn` can store it as the Turn's memory vector at no extra cost.
    query_vector: Optional[Sequence[float]] = None
    embedding_space_id: Optional[int] = None

    #: Which model actually produced ``text`` (IR-321) -- ``None`` whenever no
    #: model was reached at all (``NO_SOURCES``, ``UNAVAILABLE``). Read off
    #: the `LLMProvider` after a successful call rather than assumed from
    #: configuration, because `FallbackLLMProvider` can answer with a
    #: different model than the one configured first -- a silent switch is
    #: exactly the confound ADR-023's recall measurement cannot survive
    #: undetected.
    model: Optional[str] = None

    @property
    def is_grounded(self) -> bool:
        """Whether the answer actually cited anything.

        An uncited answer is not necessarily wrong -- "the sources do not cover
        this" is the correct response to an unanswerable question -- but a
        caller should be able to tell the two apart before presenting it as
        evidence.
        """
        return bool(self.citations)


def build_prompt(
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence["Turn"] = (),
    recalled: Sequence["Turn"] = (),
) -> str:
    """The user turn: the conversation so far, the question, then the
    numbered sources.

    ``history`` is the Conversation's recent Turns, verbatim. ``recalled``
    is what memory found further back (IR-297) -- included in full, never
    summarised.

    Numbered from 1 in the order given, deterministically, because the model is
    told to cite by those numbers and parsing maps them straight back by index.
    A shuffled or reused numbering would silently attach the wrong citation to
    the right sentence.

    Each source carries its context path, so the model can see which section a
    passage came from -- the same trail that disambiguates two theses with an
    identically titled section (IR-112).
    """
    lines: list[str] = []
    if history or recalled:
        lines.append("Conversation so far:")
        lines.extend(turn_qa_lines(history))
        if recalled:
            lines.append("")
            lines.append("Relevant earlier in this conversation:")
            lines.extend(turn_qa_lines(recalled))
        lines.append("")

    lines.append(f"Question: {question}")
    lines.append("")
    lines.append("Sources:")
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


#: A **deliberately loose** net for things that look like a citation attempt.
#:
#: This is not a second resolver and must never become one. `_MARKER` decides
#: what is a citation; this decides what *tried* to be one and failed, so a
#: format the model drifts to next is visible in a log line instead of waiting
#: for someone to read a transcript by hand -- which is how both previous
#: drifts were actually caught.
#:
#: Wider than `_MARKER` on purpose: any common opening bracket, a small number,
#: optionally a separator and a run of anything, any common closing bracket.
#: Mismatched pairs match here and not there, which is the point.
#:
#: **Two limits, stated rather than discovered.** The number must lead, so
#: `[ref:1]` is invisible to this; and a bare parenthesised number `(1)` will
#: match, so prose can trip it. Both are tolerable because this never fires on
#: its own -- `answers/service.py` only consults it once a genuine anomaly is
#: already established, where a false positive costs a noisy log line and a
#: false negative costs nothing that was not already lost.
#: Two details learned by getting them wrong first, both worth keeping:
#:
#: The run after the separator excludes **opening** brackets as well as
#: closing ones. With only closers excluded, `Yes (1) and <2>.` matched once,
#: as `(1) and <2>` -- one marker's suffix reaching across the prose to
#: swallow the next, which is the same mistake `_SUFFIX` above was corrected
#: for. A suffix must not be able to reach past where the next marker starts.
#:
#: The bound is far looser than `_SUFFIX`'s 64 **on purpose**. A marker whose
#: suffix is too long for `_MARKER` is precisely a case this needs to report,
#: so a bound at or below the strict one would go blind exactly where it is
#: most needed.
_POSSIBLE_MARKER = re.compile(
    r"[\[\(【［<]\s*\d{1,3}(?:[^\s\w][^\[\]\(\)【】［］<>\n]{0,400})?[\]\)】］>]"
)


def unresolved_marker_candidates(answer: str) -> tuple[str, ...]:
    """Citation-shaped substrings of ``answer`` that ``_MARKER`` did not match.

    Pure, like everything else here: it reports, it does not log and it does
    not decide anything. The caller owns what to do about a non-empty result.

    Overlap with a real match is computed by span rather than by re-matching
    the cleaned text, because a resolved marker is rewritten to canonical
    ``[n]`` -- which this pattern would happily match again and report as a
    failure, turning every healthy answer into an alert.
    """
    resolved_spans = [m.span() for m in _MARKER.finditer(answer)]

    def overlaps_a_resolved_marker(start: int, end: int) -> bool:
        return any(start < r_end and r_start < end for r_start, r_end in resolved_spans)

    return tuple(
        m.group(0)
        for m in _POSSIBLE_MARKER.finditer(answer)
        if not overlaps_a_resolved_marker(*m.span())
    )
