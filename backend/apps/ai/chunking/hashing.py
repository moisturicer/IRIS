"""Content-addressed hashing of a chunk set.

Why a hash and not an ``updated_at``? An idempotent re-run of the pipeline on
identical input bumps a timestamp without any semantic change. A content hash
is the only signal that survives that, and it is what makes re-chunking
incremental instead of a full re-embed.

Pure: no I/O, no clock, no randomness. ``hashlib`` rather than the built-in
``hash()``, because the latter is randomised per process and would produce a
digest that changes between runs.
"""

import hashlib
import json
from typing import Iterable

from .values import Chunk

# Unicode Information Separator One. Placed between chunks so that two
# adjacent chunks cannot concatenate to the same digest as one chunk holding
# the joined text: ["ab", "c"] and ["a", "bc"] must differ.
_SEPARATOR = b"\x1f"

# What the hash covers. PINNED — changing this list re-flips every stored
# chunk set exactly once, which is a deliberate release event and never a
# silent migration.
#
# Hashed:   text, sequence, context_path
# Excluded: token_count  (moves when a tokenizer is upgraded)
#           source_page, element_kinds, bboxes  (display metadata; a coordinate
#           shift from an extractor upgrade changes no meaning)
_HASHED_FIELDS = ("text", "sequence", "context_path")


def chunkset_hash(chunks: Iterable[Chunk]) -> str:
    """Return a deterministic SHA-256 hex digest over ``chunks``."""
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(_SEPARATOR)
        digest.update(
            json.dumps(
                {
                    "t": chunk.text,
                    "s": chunk.sequence,
                    "p": list(chunk.context_path),
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    return digest.hexdigest()


def chunk_text_hash(chunk: Chunk) -> str:
    """Per-chunk digest, so re-chunking can diff and re-embed only what moved."""
    return hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
