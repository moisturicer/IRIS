"""A deterministic fake embedder.

Not a mock: it does not record calls or return canned values. It is a real,
if useless-for-retrieval, implementation of ``EmbeddingProvider`` — it hashes
text to a stable vector, so the same text always produces the same vector,
in-process and across processes, without a network call or an API key.

This is what lets the port's contract suite run in CI and on a laptop with
no vendor credentials: the contract (determinism, dimension, batch ordering)
is a property of the port, not of any one vendor, and should be checkable
without paying a vendor to check it.
"""

import hashlib
import struct
from typing import List

from ai.domain.ports import EmbeddingProvider

DEFAULT_DIMENSIONS = 1024  # voyage-context-4's default (ADR-015), so a fake
                           # swapped in for a real adapter in a test needs no
                           # EmbeddingSpace dimension change to match it.


class DeterministicFakeEmbeddingProvider(EmbeddingProvider):
    """Hashes text to a unit-ish vector of ``dimensions`` floats.

    The hash is seeded per output component (``sha256(f"{text}:{i}")``) so
    the vector has ``dimensions`` independent-looking values rather than one
    hash digest tiled to length — tiling would make every chunk of 32 bytes
    identical and defeat any test that checks the vector is not degenerate.

    Each component is mapped into ``[-1.0, 1.0]`` so the shape resembles a
    real embedding closely enough to exercise code that assumes that range
    (e.g. cosine similarity), without claiming to carry any semantic meaning.
    """

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS):
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1")
        self.dimensions = dimensions

    def _hash_to_vector(self, text: str) -> List[float]:
        vector = []
        for i in range(self.dimensions):
            digest = hashlib.sha256(f"{text}\x1f{i}".encode("utf-8")).digest()
            # Take the first 8 bytes as an unsigned int, normalise to [-1, 1].
            (as_int,) = struct.unpack(">Q", digest[:8])
            vector.append((as_int / 0xFFFFFFFFFFFFFFFF) * 2.0 - 1.0)
        return vector

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_to_vector(text) for text in texts]

    async def embed_query(self, text: str) -> List[float]:
        return self._hash_to_vector(text)
