"""Heading trails, their budget, and section keys (IR-1050).

Every chunk is embedded with its heading trail in front, e.g.
``Thesis Title > 3 Methodology > 3.2 Sampling``, so the vector knows which
paper and section a passage came from (IR-112). The trail is counted inside
the target size, never added after packing.

Pure apart from counting tokens (see ``tokens``).
"""

from .document import HEADING, DocumentElement
from .text_splitting import grapheme_safe_split
from .tokens import count_tokens
from .values import ChunkingOptions

PATH_SEPARATOR = " > "
TRAIL_JOIN = "\n\n"
_TRUNCATION_MARKER = "..."


class HeadingStack:
    """The open headings at a point in the document, keyed by level."""

    def __init__(self, title: str):
        self._title = title.strip()
        self._stack: list[tuple[int, str]] = []

    def push(self, element: DocumentElement) -> None:
        text = element.text.strip()
        if element.kind != HEADING or not text:
            return
        level = element.level if element.level is not None else 1
        self._stack = [entry for entry in self._stack if entry[0] < level]
        self._stack.append((level, text))

    @property
    def path(self) -> tuple[str, ...]:
        """Title, then the open headings. A first heading repeating the title
        is not repeated."""
        headings = tuple(text for _, text in self._stack)
        if not self._title or (headings and headings[0] == self._title):
            return headings
        return (self._title, *headings)


def truncate_middle(path: tuple[str, ...], max_tokens: int) -> tuple[str, ...]:
    """Keep the title and the nearest section; drop the middle, then words."""
    if not path or count_tokens(PATH_SEPARATOR.join(path)) <= max_tokens:
        return path
    title, nearest = path[0], path[-1]
    if len(path) > 2:
        candidate = (title, _TRUNCATION_MARKER, nearest)
        if count_tokens(PATH_SEPARATOR.join(candidate)) <= max_tokens:
            return candidate
    candidate = (title, nearest)
    if count_tokens(PATH_SEPARATOR.join(candidate)) <= max_tokens:
        return candidate
    return (_leading_words(title, max_tokens),)


def _leading_words(text: str, max_tokens: int) -> str:
    words = text.split()
    if not words:
        return text
    kept = [words[0]]
    for word in words[1:]:
        if count_tokens(" ".join(kept + [word])) > max(max_tokens, 1):
            break
        kept.append(word)
    return " ".join(kept)


def bounded_trail(path: tuple[str, ...], options: ChunkingOptions) -> tuple[str, ...]:
    """``path`` cut to its budget, or no trail when no body would fit beside it.

    The budget is the configured trail size, and never more than a third of
    the target, so most of every chunk stays the author's text.
    """
    target = options.effective_target_tokens
    budget = min(options.context_path_max_tokens, target // 3)
    if budget < 1 or not path:
        return ()
    path = truncate_middle(path, budget)
    if count_tokens(PATH_SEPARATOR.join(path)) > budget:
        label = ""
        for cluster in grapheme_safe_split(path[0], 1):
            if count_tokens(label + cluster) > budget:
                break
            label += cluster
        path = (label,) if label else ()
    if path and trail_cost(path) >= target:
        return ()
    return path


def trail_cost(trail: tuple[str, ...]) -> int:
    """Tokens the trail and its separator take from a chunk's budget.

    Exact: a token never spans the blank line, so the embedded text costs
    this plus the body's own count.
    """
    if not trail:
        return 0
    return count_tokens(PATH_SEPARATOR.join(trail) + TRAIL_JOIN)


def embedded_text(trail: tuple[str, ...], body: str) -> str:
    """What the embedding model sees: the trail, a blank line, the body."""
    prefix = PATH_SEPARATOR.join(trail)
    if prefix and body:
        return f"{prefix}{TRAIL_JOIN}{body}"
    return prefix or body
