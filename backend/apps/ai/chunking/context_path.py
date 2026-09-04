"""The context-path decorator (IR-112).

Every chunk is prefixed with its heading trail before it is embedded. Take a
real chunk with the prefix removed:

    "Samples were collected weekly from twelve ponds across three barangays."

Embedded alone, that passage is about sampling. It is not about tilapia, not
about feed conversion, not about methodology, and not about the thesis it
came from, because none of those words appear in it. With the prefix —
``Thesis Title > 3 Methodology > 3.2 Sampling Procedure`` — the vector
carries the document's identity and the section's role, which is what
disambiguates it from the hundreds of other theses with a section also
titled "3.2 Sampling Procedure".

Built as a decorator around any ``Chunker``, not folded into one, because
prefixing is orthogonal to how a document is split: it applies unchanged to
the fixed-window baseline (IR-110) and the structural cascade (IR-111), and
to whatever strategy is registered after them.

Pure: no Django, no I/O, no clock, no randomness.
"""

from dataclasses import replace

from .document import HEADING, NormalizedDocument
from .hashing import chunkset_hash
from .ports import Chunker
from .registry import build_chunker
from .tokens import count_tokens
from .values import Chunk, ChunkingOptions, ChunkSet

_TRUNCATION_MARKER = "..."
_PATH_SEPARATOR = " > "


def _heading_path_by_word(document: NormalizedDocument) -> list[tuple[str, ...]]:
    """The heading trail active at each word of the document, in order.

    A stack keyed by heading level: a heading at level N replaces every
    entry already at level >= N, then pushes itself — the "3" then "3.2"
    nesting a numbered thesis outline produces. Every word up to the next
    heading inherits the path built so far, with the document title always
    first, so a word with no enclosing heading yet still gets a valid path.

    Every registered strategy preserves word order exactly (IR-110's
    no-content-loss property), so indexing this list by a running word count
    over a strategy's *output* lands on the same word as this same index
    into the *input* — which is what lets the decorator attribute a path to
    a chunk without knowing anything about how that chunk was produced.
    """
    path_by_word: list[tuple[str, ...]] = []
    stack: list[tuple[int, str]] = []

    for element in document.elements:
        words = element.text.split()
        if not words:
            continue
        if element.kind == HEADING:
            level = element.level if element.level is not None else 1
            stack = [(lv, text) for lv, text in stack if lv < level]
            stack.append((level, element.text.strip()))
        path = (document.title,) + tuple(text for _, text in stack)
        path_by_word.extend([path] * len(words))

    return path_by_word


def _truncate_middle(path: tuple[str, ...], max_tokens: int) -> tuple[str, ...]:
    """Keep the document title and the nearest section; drop the middle.

    The intermediate hierarchy rarely earns its tokens — what disambiguates
    a chunk is which document it is from and which section it is in right
    now, not the chapters in between. The budget is a hard guarantee, so a
    title that alone exceeds it is itself word-truncated as a last resort:
    the path must never exceed ``max_tokens``, whatever it costs to get
    there.
    """
    if not path:
        return path
    if count_tokens(_PATH_SEPARATOR.join(path)) <= max_tokens:
        return path

    title, nearest = path[0], path[-1]
    candidate = (title, _TRUNCATION_MARKER, nearest) if len(path) > 2 else (title, nearest)
    if count_tokens(_PATH_SEPARATOR.join(candidate)) <= max_tokens:
        return candidate

    candidate = (title, nearest)
    if count_tokens(_PATH_SEPARATOR.join(candidate)) <= max_tokens:
        return candidate

    words = title.split()
    return (" ".join(words[: max(max_tokens, 1)]),)


class ContextPathChunker:
    """Wraps a ``Chunker``, prefixing every chunk it produces with its
    heading trail.

    Never inspects how the wrapped chunker split the document — only what it
    produced, and where each word of the *document* originated. That is what
    lets it compose with any strategy unchanged.
    """

    def __init__(self, inner: Chunker):
        self._inner = inner

    def chunk(
        self, document: NormalizedDocument, options: ChunkingOptions
    ) -> ChunkSet:
        inner_set = self._inner.chunk(document, options)
        if not inner_set.chunks:
            return inner_set

        path_by_word = _heading_path_by_word(document)
        last_path = (document.title,)
        cursor = 0
        decorated: list[Chunk] = []

        for chunk in inner_set.chunks:
            path = path_by_word[cursor] if cursor < len(path_by_word) else last_path
            last_path = path
            cursor += count_tokens(chunk.content)

            path = _truncate_middle(path, options.context_path_max_tokens)
            prefix = _PATH_SEPARATOR.join(path)
            text = f"{prefix}\n\n{chunk.content}" if prefix else chunk.content
            decorated.append(replace(chunk, text=text, context_path=path))

        decorated_tuple = tuple(decorated)
        return replace(
            inner_set,
            chunks=decorated_tuple,
            content_hash=chunkset_hash(decorated_tuple),
        )


def build_context_path_chunker(options: ChunkingOptions) -> Chunker:
    """Build the strategy named by ``options`` and wrap it with the
    context-path decorator.

    This is the composition every caller outside this package should use —
    ``build_chunker`` alone returns chunks with no heading trail, which is
    not what should ever be embedded.
    """
    return ContextPathChunker(build_chunker(options))
