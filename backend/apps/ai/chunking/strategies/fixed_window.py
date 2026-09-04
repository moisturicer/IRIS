"""The simplest strategy that satisfies the contract.

This exists to prove the shape end to end — port, registry, value objects,
hash — before the structure-aware cascade replaces it as the default. It is
kept afterwards, not deleted: it is the baseline the cascade is measured
against on the eval set, and if structural chunking does not beat it, that is
a finding worth having.

It packs elements into windows under the token ceiling and hard-splits any
single element that will not fit. It knows nothing about headings, tables or
lists; that is the whole point.
"""

from ..document import NormalizedDocument
from ..hashing import chunkset_hash
from ..packing import Piece, pack_pieces
from ..registry import register_chunker
from ..tokens import count_tokens
from ..values import Chunk, ChunkingOptions, ChunkSet

STRATEGY_ID = "fixed-window"


@register_chunker(STRATEGY_ID)
class FixedWindowChunker:
    """Packs consecutive elements into windows under ``max_tokens``."""

    def chunk(
        self, document: NormalizedDocument, options: ChunkingOptions
    ) -> ChunkSet:
        pieces = self._split_to_fitting_pieces(document, options.max_tokens)
        windows = pack_pieces(pieces, options.max_tokens)
        chunks = self._to_chunks(windows, document)

        return ChunkSet(
            chunks=chunks,
            strategy_id=STRATEGY_ID,
            options=options,
            content_hash=chunkset_hash(chunks),
        )

    # -- steps -------------------------------------------------------------

    def _split_to_fitting_pieces(
        self, document: NormalizedDocument, max_tokens: int
    ) -> list[Piece]:
        """Break every element down until each piece fits the ceiling.

        Returns (text, element) pairs so each piece still knows where it came
        from — which is what lets page and region data travel with it later.
        """
        pieces: list[Piece] = []
        for element in document.elements:
            words = element.text.split()
            if not words:
                continue
            if len(words) <= max_tokens:
                pieces.append((" ".join(words), element))
                continue
            for start in range(0, len(words), max_tokens):
                pieces.append((" ".join(words[start : start + max_tokens]), element))
        return pieces

    def _to_chunks(
        self, windows: list[list[Piece]], document: NormalizedDocument
    ) -> tuple[Chunk, ...]:
        chunks: list[Chunk] = []
        for sequence, window in enumerate(windows):
            content = " ".join(text for text, _ in window)
            elements = [element for _, element in window]
            pages = [e.page for e in elements if getattr(e, "page", None) is not None]
            bboxes = tuple(
                e.bbox for e in elements if getattr(e, "bbox", None) is not None
            )
            chunks.append(
                Chunk(
                    # The context path is applied by a decorator, not here, so
                    # text equals content at this layer.
                    text=content,
                    content=content,
                    context_path=(),
                    sequence=sequence,
                    token_count=count_tokens(content),
                    source_page=pages[0] if pages else None,
                    element_kinds=frozenset(e.kind for e in elements),
                    bboxes=bboxes,
                )
            )
        return tuple(chunks)
