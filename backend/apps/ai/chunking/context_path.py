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

Pure except for one read: counting a token means loading the vendored
``voyage-context-4`` vocabulary once per process (see ``tokens``). No Django,
no database, no network, no clock, no randomness.
"""

from dataclasses import replace
from typing import Optional

from .document import HEADING, NormalizedDocument
from .hashing import chunkset_hash
from .numbering import outline_depths
from .ports import Chunker
from .registry import build_chunker
from .tokens import count_tokens
from .values import Chunk, ChunkingOptions, ChunkSet

_TRUNCATION_MARKER = "..."
_PATH_SEPARATOR = " > "


def _words_with_paths(
    document: NormalizedDocument,
) -> list[tuple[str, tuple[str, ...], bool]]:
    """Every word of the document, in order, paired with the heading trail
    active at that word.

    A stack keyed by heading level: a heading at level N replaces every
    entry already at level >= N, then pushes itself — the "3" then "3.2"
    nesting a numbered thesis outline produces. Every word up to the next
    heading inherits the path built so far, with the document title always
    first, so a word with no enclosing heading yet still gets a valid path.

    The depths the headings' own numbering claims are read in one pass up
    front (IR-314), because an ambiguous single letter can only be resolved
    against the sequence it sits in — see `numbering.py`.
    """
    elements = [element for element in document.elements if element.text.split()]
    heading_positions = [
        position
        for position, element in enumerate(elements)
        if element.kind == HEADING
    ]
    # Keyed by position rather than zipped alongside, so the depths cannot
    # drift out of step with the headings they were derived from.
    claimed_depths = dict(
        zip(
            heading_positions,
            outline_depths([elements[p].text for p in heading_positions]),
        )
    )

    words_with_paths: list[tuple[str, tuple[str, ...], bool]] = []
    # (level, text, numbered) — `numbered` is what lets an unnumbered heading
    # be placed relative to the outline rather than on top of it.
    stack: list[tuple[int, str, bool]] = []

    for position, element in enumerate(elements):
        is_heading = element.kind == HEADING
        if is_heading:
            depth = claimed_depths[position]
            level = _effective_level(element, stack, depth)
            stack = [entry for entry in stack if entry[0] < level]
            stack.append((level, element.text.strip(), depth is not None))
        path = (document.title,) + tuple(text for _, text, _ in stack)
        words_with_paths.extend(
            (word, path, is_heading) for word in element.text.split()
        )

    return words_with_paths


def _effective_level(
    element, stack: list[tuple[int, str, bool]], claimed_depth: Optional[int]
) -> int:
    """The level at which a heading should sit in the outline.

    A **numbered** heading sits at the depth its own numbering claims, as a
    floor rather than a ceiling: a heading the extractor has genuinely
    resolved as deeper keeps that. The numbering is the outline — Docling
    reports level 1 for every heading it finds (IR-242), so without this a
    document collapses to a depth-1 trail.

    An **unnumbered** heading is placed one level *below* the deepest numbered
    entry currently open, rather than at whatever level the extractor guessed
    (IR-248). Docling promotes a great deal to `section_header` that carries no
    number — 61 of 92 headings on a real SRS: `Assumptions`, `Dependencies`,
    `Backup Strategy`, and lead-in fragments like `IRIS shall NOT:`. At level 1
    each of those evicted the numbered section it actually belongs to, so the
    subsections that followed were trailed to a bullet-list lead-in instead of
    to `1. Introduction`.

    **The trade-off, stated rather than buried:** a genuinely top-level
    unnumbered section that follows numbered ones — an appendix such as
    `A Contributions` after `8 Conclusion` — is now nested under that last
    numbered section instead of beside it. Nothing distinguishes the two cases
    from the heading alone. The exchange is deliberate: it costs a wrong parent
    on a handful of trailing sections and buys a correct parent for the 61,
    and in both cases the heading itself is still the nearest entry in its own
    trail. Telling them apart needs the document's numbering *sequence*.
    IR-314 now reads that sequence — `numbering.py` uses it to resolve a
    letter that is also a roman numeral — but it reads it only to classify
    each heading, not to judge whether an unnumbered one is really a peer of
    the sections around it. That judgement is still open, and this rule
    should be revisited when it is made.
    """
    declared = element.level if element.level is not None else 1
    if claimed_depth is not None:
        return max(declared, claimed_depth)

    deepest_numbered = max(
        (level for level, _, numbered in stack if numbered), default=0
    )
    if deepest_numbered == 0:
        # No numbered outline open — front matter, or a document that numbers
        # nothing. Behaves exactly as before.
        return declared
    return max(declared, deepest_numbered + 1)


def _path_for_span(
    words_with_paths: list[tuple[str, tuple[str, ...], bool]],
    start: int,
    end: int,
    fallback: tuple[str, ...],
) -> tuple[str, ...]:
    """The trail to label a chunk spanning ``words_with_paths[start:end]``.

    The trail of the chunk's **first word that is not part of a heading** --
    its first actual content -- because that is what the chunk is *about*.

    Neither endpoint alone survives both strategies. Taking the first word's
    trail loses the child heading when the structural cascade folds a
    heading-only section forward (IR-241), handing the merged chunk its
    parent's path. Taking the last word's trail breaks the fixed-window
    baseline, which knows nothing about headings and happily ends a window on
    one: a window of Introduction prose that happens to close on the
    "2 Methods" heading would be labelled Methods. Both are chunks that span a
    heading, and the first-content rule is right for both.

    A chunk that is *only* headings has no content word to ask, so it keeps
    the trail of its own last heading -- which is its own position in the
    outline.
    """
    span = words_with_paths[start:end]
    if not span:
        if start < len(words_with_paths):
            return words_with_paths[start][1]
        return fallback

    for _, path, is_heading in span:
        if not is_heading:
            return path
    return span[-1][1]


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

    return (_truncate_to_budget(title, max_tokens),)


def _truncate_to_budget(text: str, max_tokens: int) -> str:
    """Keep the longest leading run of whole words that fits ``max_tokens``.

    Word-counted truncation would only be a budget under the old word-as-token
    unit (IR-287); against a real tokenizer it can still overrun, and this
    function is the place the "never exceeds the budget" guarantee bottoms
    out. At least one word is always kept -- an empty context path loses the
    chunk's provenance entirely, which is worse than one word over.
    """
    words = text.split()
    if not words:
        return text
    kept = [words[0]]
    for word in words[1:]:
        candidate = kept + [word]
        if count_tokens(" ".join(candidate)) > max(max_tokens, 1):
            break
        kept = candidate
    return " ".join(kept)


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
        document_words = [word for word, _, _ in words_with_paths]
        last_path = (document.title,)
        cursor = 0
        decorated: list[Chunk] = []

        for chunk in inner_set.chunks:
            start = cursor
            cursor = _advance_cursor(document_words, cursor, chunk.content.split())
            path = _path_for_span(words_with_paths, start, cursor, last_path)
            last_path = path

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
