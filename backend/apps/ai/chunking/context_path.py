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


def _words_with_paths(document: NormalizedDocument) -> list[tuple[str, tuple[str, ...]]]:
    """Every word of the document, in order, paired with the heading trail
    active at that word.

    A stack keyed by heading level: a heading at level N replaces every
    entry already at level >= N, then pushes itself — the "3" then "3.2"
    nesting a numbered thesis outline produces. Every word up to the next
    heading inherits the path built so far, with the document title always
    first, so a word with no enclosing heading yet still gets a valid path.
    """
    words_with_paths: list[tuple[str, tuple[str, ...]]] = []
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
        words_with_paths.extend((word, path) for word in words)

    return words_with_paths


def _advance_cursor(
    document_words: list[str], cursor: int, chunk_words: list[str]
) -> int:
    """How far a chunk's content actually moves the cursor through the
    document's word list.

    Not always ``len(chunk_words)``: a strategy is free to repeat content
    verbatim — the structural cascade repeats a table's header row in every
    fragment it splits that table into (IR-111), so a chunk's word count can
    exceed how much *new* document content it actually contains. Repeated
    content is always a prefix of the chunk reproducing words that appeared
    earlier in the document, never a reordering or new material, so the
    genuinely new portion is the chunk's longest *trailing* run of words
    that lines up with the document's next unconsumed words — the greedy
    longest match is what excludes a repeated leading header rather than
    miscounting it as new content.

    For a chunk with no repetition (the common case), the longest such run
    is the whole chunk, so this returns exactly ``len(chunk_words)`` — the
    same as the naive count would have.
    """
    max_length = min(len(chunk_words), len(document_words) - cursor)
    for length in range(max_length, 0, -1):
        if chunk_words[len(chunk_words) - length :] == document_words[cursor : cursor + length]:
            return cursor + length
    return cursor


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

        words_with_paths = _words_with_paths(document)
        document_words = [word for word, _ in words_with_paths]
        last_path = (document.title,)
        cursor = 0
        decorated: list[Chunk] = []

        for chunk in inner_set.chunks:
            path = words_with_paths[cursor][1] if cursor < len(words_with_paths) else last_path
            last_path = path
            cursor = _advance_cursor(document_words, cursor, chunk.content.split())

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
