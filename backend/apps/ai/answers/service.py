"""Generating a cited text from passages (IR-131), for the AI Overview.

Django's chat answer service went with its answer path in IR-957; what stays
is the one-call generation the Overview and paper briefs share.

**The disclosure gate runs before the prompt is built, never over the answer.**
An LLM call always leaves the deployment -- unlike a reranker, there is no
local variant -- so every passage in the prompt is content sent to a vendor.
Filtering afterwards would mean it had already gone (ADR-015, IR-127).

**A vendor failure is never a fabricated answer.** ADR-008: when the provider
is unavailable the answer is replaced by an explicit unavailable state. The
sources are still returned, because retrieval worked -- a reader gets passages
to read themselves instead of a sentence nobody wrote.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional, Sequence

from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.providers.ports import LLMProvider
from apps.ai.retrieval.ports import RetrievedChunk

if TYPE_CHECKING:
    pass

from apps.ai.providers.dialects import DEFAULT_DIALECT, VendorDialect

from .citations import (
    SYSTEM_PROMPT,
    images_in,
    parse_citations,
    unresolved_marker_candidates,
)
from .reasoning import without_leaked_reasoning

logger = logging.getLogger(__name__)

#: What a reader is told when the provider is down. Deliberately plain, and
#: deliberately not phrased as an answer.
UNAVAILABLE_TEXT = (
    "The answering model is unavailable right now, so this has not been "
    "answered. The sources found for the question are listed below and can be "
    "read directly."
)

#: What the model is told to say when the sources do not cover the question --
#: asserted by a test, so the instruction and the expectation cannot drift.
NO_ANSWER_HINT = "the sources do not"


def model_that_answered(llm: LLMProvider) -> Optional[str]:
    """``last_model_used`` first: it names the fallback that actually ran."""
    return getattr(llm, "last_model_used", None) or getattr(llm, "model", None)


def generate_cited(
    llm: LLMProvider,
    user_prompt: str,
    sources: Sequence[RetrievedChunk],
    *,
    system: str = SYSTEM_PROMPT,
    parse: Callable = parse_citations,
) -> Optional[tuple[str, tuple]]:
    """One non-streaming completion, cited against ``sources``.

    ``None`` when the model was unreachable or wrote nothing (ADR-008).
    ``system`` and ``parse`` let the overview cite pages (IR-434).
    """
    try:
        raw = llm.generate(system=system, user=user_prompt)
    except (LLMUnavailable, CircuitOpen) as exc:
        logger.warning("answer generation unavailable: %s", exc)
        return None

    raw = without_leaked_reasoning(raw)
    if _produced_nothing(raw):
        logger.warning("answer generation produced no text")
        return None

    text, citations = parse(raw, sources)
    _warn_if_citations_went_missing(raw, text, citations)
    _warn_if_images_were_stripped(raw)
    return text, citations


def _produced_nothing(raw: str | Sequence[str]) -> bool:
    """Whether the model wrote no answer at all (IR-377) -- one whole
    reply, or a stream's accumulated parts.

    One predicate for both paths, because the two disagreeing is the bug:
    `generate()` raising on an empty message while a stream of pure
    reasoning was saved as a Turn whose answer was blank -- a reply that
    looked real and was not there. Reasoning does not count as text here,
    and neither does `<think>`-leaked reasoning: `ThinkTagFilter` has
    already taken both out of the buffer this reads.
    """
    return not "".join(raw).strip()


def _parse(
    raw_parts: Sequence[str],
    sources: Sequence[RetrievedChunk],
    dialect: VendorDialect = DEFAULT_DIALECT,
) -> tuple[str, str, tuple]:
    """Join and citation-parse a stream's text, once. Shared by a clean
    completion and `_partial_answer` (IR-328), so the two never drift.

    The dialect normalises the vendor's marker variants first (IR-382) --
    here rather than on each delta, because a marker split across two deltas
    would be normalised as two fragments and match neither.
    """
    raw = dialect.normalize_citation_markers("".join(raw_parts))
    text, citations = parse_citations(raw, sources)
    return raw, text, citations


def _warn_if_images_were_stripped(raw: str) -> None:
    """Log when the model wrote an image; stripping is otherwise silent."""
    images = images_in(raw)
    if images:
        logger.warning(
            "answer contained %d image(s), which were stripped -- IRIS supplies "
            "no image addresses, so these were invented: %s",
            len(images),
            list(images[:5]),
        )


def _warn_if_citations_went_missing(raw: str, text: str, citations: Sequence) -> None:
    """Say something when an answer that should have cited did not.

    **Why this exists.** Twice now the model has drifted to a marker format the
    parser did not recognise -- `【1】`, then `【1†L1-L5】` -- and both times the
    symptom was identical and silent: a fluent answer, zero citations, the raw
    marker sitting in the reader's text, and nothing anywhere saying so. Both
    were found by a person reading a transcript by hand. There will be a third
    format; this is so it costs a log line rather than another afternoon.

    **The trigger is the unambiguous half.** The model was handed numbered
    sources and told to cite them, it wrote a real answer, and not one citation
    resolved. The one honest reason for that is the answer saying the sources
    do not cover the question, which the prompt explicitly asks for and
    `NO_ANSWER_HINT` already names -- so that case is excluded rather than
    alerted on.

    **The candidates are only the diagnostic half**, consulted after the
    anomaly is already established. `unresolved_marker_candidates` is
    deliberately loose and will sometimes point at ordinary prose; that is
    affordable here precisely because it never decides anything on its own, and
    when it is right it hands over the exact new format to support.
    """
    if citations or NO_ANSWER_HINT in text.lower():
        return

    candidates = unresolved_marker_candidates(raw)
    if candidates:
        logger.warning(
            "answer cited nothing, but %d citation-shaped marker(s) did not "
            "parse -- the model may have drifted to an unsupported format: %s",
            len(candidates),
            list(candidates[:5]),
        )
    else:
        logger.warning(
            "answer cited nothing and no citation-shaped markers were found, "
            "though sources were supplied and the answer does not decline"
        )
