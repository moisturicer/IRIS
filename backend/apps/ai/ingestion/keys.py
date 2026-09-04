"""The idempotency key a chunk-and-embed job is claimed under.

Keyed on the record, the extraction, the strategy and the embedding space,
because those four are exactly what determine the output: change any one and
the vectors are different; change none and re-running is waste. A duplicate
delivery from the queue finds the key already claimed and returns.

``hashlib`` rather than the built-in ``hash()``, which is randomised per
process — a key that differed between workers would miss on every duplicate
that happened to land elsewhere, which is precisely the case this exists to
catch.

Pure: no Django, no I/O, no clock, no randomness.
"""

import hashlib

# Unicode Information Separator One, for the same reason chunkset_hash uses
# it: without a separator, ("ab", "c") and ("a", "bc") would be one job.
_SEPARATOR = "\x1f"


def ingestion_job_key(
    *, record_id: int, extraction_hash: str, strategy_id: str, space_id: int
) -> str:
    """A deterministic SHA-256 hex digest over the four identifying parts."""
    payload = _SEPARATOR.join(
        ["ingest-v1", str(record_id), extraction_hash, strategy_id, str(space_id)]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
