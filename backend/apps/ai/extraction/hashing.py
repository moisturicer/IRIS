"""Content-addressed hashing of an extraction.

``ChunkSet.extraction_hash`` ties a chunking to the extraction it was derived
from. Without it, "are these chunks still valid?" is answered by a timestamp,
and an idempotent re-run of ingestion on an unchanged PDF looks like a change.

**This hash covers regions; ``chunkset_hash`` deliberately does not.** The two
answer different questions and the difference is not an inconsistency.
``chunkset_hash`` identifies the *meaning* of a chunking, so a coordinate
shift from an extractor upgrade must not re-flip it. This one identifies *an
extraction* — and an extractor upgrade that moves every bounding box has to
invalidate the chunk sets built on the old ones, or citations keep pointing
at coordinates the document no longer has.

Pure: no I/O, no clock, no randomness. ``hashlib`` rather than ``hash()``,
which is randomised per process and would produce a digest that changes
between runs.
"""

import hashlib
import json

from apps.ai.chunking.document import NormalizedDocument

from .serialization import document_to_json


def extraction_hash(document: NormalizedDocument) -> str:
    """Return a deterministic SHA-256 hex digest over ``document``.

    Computed over the same serialized form that is persisted, so two
    documents hash alike exactly when they store alike — there is no second
    definition of "the same extraction" to drift from this one.
    """
    payload = json.dumps(
        document_to_json(document),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
