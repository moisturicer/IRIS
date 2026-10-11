"""The overview cites pages, not chunk numbers (IR-434).

The whole paper is in the prompt, so a chunk number means nothing to a
reader; a page does. A page citation resolves to that page and to every chunk
on it. Chat citations are untouched: they stay chunk-level (IR-284).
"""

from __future__ import annotations

import re
from itertools import groupby
from typing import Sequence

from apps.ai.answers.citations import (
    PRESENTATION_RULES,
    Citation,
    normalize_math,
    strip_images,
    tidy_dropped_markers,
)
from apps.ai.citation_markers import MARKER, PAGE_MARKER, pages_in
from apps.ai.retrieval.ports import RetrievedChunk

GROUNDING_RULES = (
    "You are IRIS, the research assistant for Cebu Institute of Technology - "
    "University.\n"
    "Answer ONLY from the paper below, which is given page by page. Cite the "
    "page a statement comes from inline as [p. 3], using the page numbers "
    "given.\n"
    "Write a citation as a square bracket, p., the page number, and a closing "
    "square bracket, with nothing else inside: [p. 3] or [p. 12]. Do not add "
    "line references, file names, or any other characters inside the "
    "brackets, and do not use any other bracket style.\n"
    "If the paper does not say something, do not say it. Never invent a "
    "title, author, finding or number. Be concise and factual."
)

SYSTEM_PROMPT = GROUNDING_RULES + "\n" + PRESENTATION_RULES

# A bare `[3]` is read as page 3 too: the prompt offers no other number to cite.
_ANY_MARKER = re.compile(
    PAGE_MARKER.pattern + "|" + MARKER.pattern, re.IGNORECASE
)


def build_page_prompt(question: str, chunks: Sequence[RetrievedChunk]) -> str:
    """The question, then the paper in document order under `[p. N]` labels."""
    lines = [f"Question: {question}", "", "Paper:"]
    for page, run in groupby(chunks, key=lambda chunk: chunk.source_page):
        lines.append("")
        lines.append(f"[p. {page}]" if page is not None else "Unpaged passage, not citable:")
        for chunk in run:
            if chunk.context_path:
                lines.append(f"({' > '.join(chunk.context_path)})")
            lines.append(chunk.content)
    return "\n".join(lines).strip()


def _by_page(chunks: Sequence[RetrievedChunk]) -> dict[int, list[RetrievedChunk]]:
    pages: dict[int, list[RetrievedChunk]] = {}
    for chunk in chunks:
        if chunk.source_page is not None:
            pages.setdefault(chunk.source_page, []).append(chunk)
    return pages


def _page_citation(page: int, on_page: list[RetrievedChunk]) -> Citation:
    first = on_page[0]
    return Citation(
        marker=page,
        chunk_id=first.chunk_id,
        record_id=first.record_id,
        record_title=first.record_title,
        source_page=page,
        text="\n\n".join(chunk.content for chunk in on_page),
        context_path=tuple(first.context_path or ()),
        regions=tuple(region for chunk in on_page for region in chunk.regions or ()),
    )


def parse_page_citations(
    answer: str, chunks: Sequence[RetrievedChunk]
) -> tuple[str, tuple[Citation, ...]]:
    """Resolve page markers to page citations, rewritten as canonical `[n]`.

    A page no chunk sits on is dropped, as an out-of-range chunk marker is.
    """
    answer = normalize_math(strip_images(answer))
    pages = _by_page(chunks)
    resolved: dict[int, Citation] = {}

    def keep(match: re.Match) -> str:
        valid = [page for page in pages_in(match) if page in pages]
        for page in valid:
            if page not in resolved:
                resolved[page] = _page_citation(page, pages[page])
        return "".join(f"[{page}]" for page in dict.fromkeys(valid))

    cleaned = tidy_dropped_markers(_ANY_MARKER.sub(keep, answer))
    return cleaned, tuple(resolved[page] for page in sorted(resolved))
