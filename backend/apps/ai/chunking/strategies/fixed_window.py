"""The simplest strategy that satisfies the contract.

The evaluation baseline (ADR-067 decision 12), never the production strategy.
It packs elements into windows under the target size and hard-splits any
single element that will not fit. It knows nothing about tables or lists,
and its windows may cross a heading.

A window is labelled with the trail of its first piece that is not a heading
(what the chunk is about), or of its last heading when it holds only
headings. The trail is counted inside the target (IR-1050).
"""

from ..assembly import Draft, body_budget, finalize
from ..document import DocumentElement, NormalizedDocument
from ..outline import HeadingStack, bounded_trail, embedded_text
from ..packing import JOIN, reader_content
from ..regions import regions_for
from ..registry import register_chunker
from ..text_splitting import grapheme_safe_split, split_into_token_groups
from ..tokens import count_tokens
from ..values import ChunkingOptions, ChunkSet

STRATEGY_ID = "fixed-window"

# (text, element, trail, section key)
_Piece = tuple[str, DocumentElement, tuple[str, ...], tuple[str, ...]]


@register_chunker(STRATEGY_ID)
class FixedWindowChunker:
    """Packs consecutive elements into windows under the target size."""

    def chunk(
        self, document: NormalizedDocument, options: ChunkingOptions
    ) -> ChunkSet:
        target = options.effective_target_tokens
        windows: list[list[_Piece]] = []
        current: list[_Piece] = []
        for piece in _pieces(document, options):
            if current and not _window_fits(current + [piece], target):
                windows.append(current)
                current = []
            current.append(piece)
        if current:
            windows.append(current)
        return finalize(
            [_draft(window) for window in windows],
            strategy_id=STRATEGY_ID,
            options=options,
            page_sizes=document.page_sizes,
        )


def _pieces(document: NormalizedDocument, options: ChunkingOptions) -> list[_Piece]:
    """Every element broken down until each piece fits beside its own trail."""
    stack = HeadingStack(document.title)
    pieces: list[_Piece] = []
    for element in document.elements:
        stack.push(element)
        key = stack.path
        trail = bounded_trail(key, options)
        budget = body_budget(trail, options)
        for group in split_into_token_groups(element.text, budget):
            if count_tokens(group) <= budget:
                pieces.append((group, element, trail, key))
                continue
            # A token is never shorter than a character, so this fits.
            for fragment in grapheme_safe_split(group, max_chars=budget):
                pieces.append((fragment, element, trail, key))
    return pieces


def _label(window: list[_Piece]) -> _Piece:
    for piece in window:
        if not piece[1].is_heading:
            return piece
    return window[-1]


def _window_fits(window: list[_Piece], target: int) -> bool:
    _, _, trail, _ = _label(window)
    body = JOIN.join(text for text, *_ in window)
    return count_tokens(embedded_text(trail, body)) <= target


def _draft(window: list[_Piece]) -> Draft:
    _, _, trail, key = _label(window)
    elements = [element for _, element, *_ in window]
    pages = [e.page for e in elements if e.page is not None]
    return Draft(
        body=JOIN.join(text for text, *_ in window),
        content=reader_content([(text, element) for text, element, *_ in window]),
        trail=trail,
        section_key=key,
        source_page=pages[0] if pages else None,
        element_kinds=frozenset(e.kind for e in elements),
        bboxes=regions_for(elements),
    )
