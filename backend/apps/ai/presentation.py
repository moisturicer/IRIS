"""The shapes the AI surface puts on the wire (IR-283, IR-284, IR-285).

Two of them reach a reader, and they are not alternatives:

* a **Passage** -- a quoted span of a record's text with the page it sits on,
  which is what lets a reader check a claim without reading the paper;
* a **record card** -- title, authors, year, classification, which is what the
  interface already renders beside an answer.

Both, because each answers a question the other cannot. A card alone sends a
reader hunting through a PDF for the sentence; a passage alone gives them a
quote with no idea whose work it is. Keeping them in one response is also what
spares the interface a fetch per citation, which is what it does today.

The card also serves a path with no passages in it at all —
``GET /records/<id>/similar/``, which ranks whole records (IR-285). That is
why ``record_card`` is a function of its own rather than a loop body inside
``record_sources``: two builders for one card is how one of them quietly stops
sending ``authors`` and only one screen notices.

**The record lookup is keyed on ids retrieval already permitted.** It does not
re-derive visibility and must not: `TwoStageRetriever` narrowed the candidate
set with `visible_to(user)` before anything was scored, and a second predicate
here would be the drift ADR-014 rejected. Fetching a record by an id that
survived that filter is a join, not a decision.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from apps.ai.answers.citations import NO_SOURCES, PARTIAL, UNAVAILABLE, Citation
from apps.ai.retrieval.ports import RetrievedChunk
from apps.records.models import Record


def passage(chunk: RetrievedChunk) -> dict:
    """One retrieved passage, in the shape a reader's citation is built from.

    ``page`` rather than ``source_page``: the wire is read by people, and
    ``CONTEXT.md`` names the concept "the page it came from". The internal
    field keeps its name, because inside retrieval it distinguishes a chunk's
    source page from any other page a caller might mean.

    ``text`` is the chunk's ``content`` -- what a citation shows a reader --
    and never the ``text`` a vector was computed from, which is normalized and
    is not quite what the paper says.
    """
    return {
        "chunk_id": chunk.chunk_id,
        "record_id": chunk.record_id,
        "record_title": chunk.record_title,
        "page": chunk.source_page,
        "text": chunk.content,
        "context_path": list(chunk.context_path or ()),
        "score": round(float(chunk.score), 4),
    }


def citation(resolved: Citation) -> dict:
    """One resolved citation: a passage, plus the marker it was cited by.

    The marker matters on the wire and nowhere else: it is how a reader maps
    "[2]" in a sentence to the quote that supports it, so dropping it would
    leave the numbers in the answer text pointing at nothing.

    No ``score``. A citation is what the model used, not what ranked well, and
    showing a relevance number beside a quote invites a reader to read it as
    confidence in the claim.
    """
    return {
        "marker": resolved.marker,
        "chunk_id": resolved.chunk_id,
        "record_id": resolved.record_id,
        "record_title": resolved.record_title,
        "page": resolved.source_page,
        "text": resolved.text,
        "context_path": list(resolved.context_path or ()),
    }


def _ranked_record_ids(passages: Sequence[RetrievedChunk]) -> list[int]:
    """The records behind ``passages``, best passage first, no duplicates.

    Retrieval returns passages in rank order, so first appearance *is* the
    record's rank: a record whose best passage came third outranks one whose
    best came ninth. Deduplicating any other way would reorder the answer's
    evidence against the ranking that produced it.
    """
    seen: list[int] = []
    for passage in passages:
        if passage.record_id not in seen:
            seen.append(passage.record_id)
    return seen


def record_sources(passages: Sequence[RetrievedChunk]) -> list[dict]:
    """Record cards for the passages retrieved, in rank order.

    ``score`` is the best score among that record's passages, because that is
    the passage the ranking actually put it there for; averaging would let a
    long record with one excellent passage sink below a short mediocre one.

    A record that vanished between retrieval and rendering is skipped rather
    than rendered hollow -- a card with no title reads as a broken result,
    and a deleted record is not a result at all.
    """
    ordered_ids = _ranked_record_ids(passages)
    best_score = {}
    for passage in passages:
        current = best_score.get(passage.record_id)
        if current is None or passage.score > current:
            best_score[passage.record_id] = passage.score

    records = (
        Record.objects.filter(pk__in=ordered_ids)
        .select_related("classification")
        .prefetch_related("authors")
        .in_bulk()
    )

    cards = []
    for record_id in ordered_ids:
        record = records.get(record_id)
        if record is None:
            continue
        cards.append(record_card(record, best_score.get(record_id, 0.0)))
    return cards


def record_card(record: Record, score: float) -> dict:
    """One record, in the shape the interface renders beside an answer.

    Shared by the answer path and by related works (`apps/ai/similarity.py`),
    because they render the same card: two builders would let one of them
    quietly stop sending `authors` and only one screen would notice.
    """
    return {
        "id": record.id,
        "title": record.title,
        "abstract": (record.abstract or "").strip(),
        "authors": ", ".join(a.name for a in record.authors.all())
        or "Institutional Author",
        "year": record.year_accomplished,
        "classification": (
            record.classification.name if record.classification_id else None
        ),
        "score": round(float(score), 4),
    }


def citations(resolved: Iterable[Citation]) -> list[dict]:
    """The citations the answer actually made, in marker order.

    Distinct from ``record_sources``: the sources are everything the model was
    shown, and these are what it used. A reader checking a claim wants the
    second; a reader browsing what IRIS read wants the first, and collapsing
    them would quietly present unread sources as evidence.

    Not deduplicated by record, unlike the record ids this replaced. Two
    passages from one paper are two pieces of evidence -- possibly from two
    different pages -- and merging them to one record id was exactly the
    flattening IR-284 exists to undo.
    """
    return [citation(item) for item in resolved]


# -- how an answer came out ----------------------------------------------------
#
# Moved here from `views/chatbot.py` by IR-295, because a Conversation replays
# stored Turns and has to reach exactly the same `answer`/`message`/`mode`
# shape a live ask produced. Two copies of that mapping is how a reopened
# transcript starts presenting "no model was reachable" as an answer.

#: What the wire calls each answer state. The API's own names, mapped from the
#: domain's rather than shared with them: `GroundedAnswer.state` is what the
#: service decided, and this is what a client has been told to expect.
GENERATIVE_MODE = "generative"
NO_RESULTS_MODE = "no_results"
UNAVAILABLE_MODE = "unavailable"
#: A stored Turn whose stream never reached `Done` (IR-328) -- the text is
#: whatever arrived before the cutoff, not a complete answer, so a reopened
#: transcript must say so rather than replaying it as `generative`.
PARTIAL_MODE = "partial"

_WIRE_MODE = {
    NO_SOURCES: NO_RESULTS_MODE,
    UNAVAILABLE: UNAVAILABLE_MODE,
    PARTIAL: PARTIAL_MODE,
}

NO_RESULTS_MESSAGE = (
    "No readable sources in the CIT-U repository matched that question. Try "
    "different keywords, or browse Discover to see what is available."
)


def answer_mode(state: str) -> str:
    return _WIRE_MODE.get(state, GENERATIVE_MODE)


def answer_body(mode: str, text: str) -> dict:
    """The ``answer``/``message`` pair for one answer state.

    ``answer`` is a written answer or it is null. The two non-answers --
    nothing found, and no model reachable -- say so in ``message``, so a
    client rendering ``answer`` can never present an apology as a finding.

    ``text`` is whatever the service produced: the answer in the generative
    case, and the explanation in the unavailable one. The no-results wording
    is this layer's, not the service's, because it points a reader at Discover
    and the domain has no business knowing that screen exists.

    A partial answer takes the generative branch too -- ``text`` is shown,
    truncated as it is, rather than hidden, because some of it did arrive
    and hiding it entirely would throw away more than the cutoff already
    did. ``mode`` is what tells a client to render it as unfinished.
    """
    if mode in (GENERATIVE_MODE, PARTIAL_MODE):
        return {"answer": text, "message": None}
    if mode == NO_RESULTS_MODE:
        return {"answer": None, "message": NO_RESULTS_MESSAGE}
    return {"answer": None, "message": text}
