"""The chunk keyword index: the trigger that maintains it, and its backfill
(IR-393, ADR-033 §2).

A trigger rather than a signal, because bulk insert and the atomic ChunkSet
swap never call `save()`. A trigger rather than a generated column, because
adding one rewrites the table under an ACCESS EXCLUSIVE lock.
"""

from __future__ import annotations

from django.db import connection

TABLE = "ai_documentchunk"
# Named, not inherited from the server's default_text_search_config, so the
# trigger, the query and Record's index cannot drift apart.
CONFIG = "english"
FUNCTION = "ai_documentchunk_search_vector"
TRIGGER = "ai_documentchunk_search_vector_trg"

# Migration 0015's trigger, over `content` alone. Kept as 0015 ran it.
CREATE_TRIGGER_SQL = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('{CONFIG}', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER {TRIGGER}
BEFORE INSERT OR UPDATE OF content ON {TABLE}
FOR EACH ROW EXECUTE FUNCTION {FUNCTION}();
"""

# The current trigger (IR-1102): `keyword_text` where a chunk sets one.
INDEXED = "COALESCE(keyword_text, content, '')"
CREATE_KEYWORD_TEXT_TRIGGER_SQL = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('{CONFIG}', COALESCE(NEW.keyword_text, NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS {TRIGGER} ON {TABLE};
CREATE TRIGGER {TRIGGER}
BEFORE INSERT OR UPDATE OF content, keyword_text ON {TABLE}
FOR EACH ROW EXECUTE FUNCTION {FUNCTION}();
"""

DROP_TRIGGER_SQL = f"""
DROP TRIGGER IF EXISTS {TRIGGER} ON {TABLE};
DROP FUNCTION IF EXISTS {FUNCTION}();
"""

# Only rows the trigger never saw, recomputed per batch rather than
# checkpointed -- that is what makes a run idempotent and resumable.
_BACKFILL_BATCH_SQL = f"""
UPDATE {TABLE}
   SET search_vector = to_tsvector('{CONFIG}', COALESCE(content, ''))
 WHERE id IN (
     SELECT id FROM {TABLE} WHERE search_vector IS NULL LIMIT %s
 )
"""
_KEYWORD_TEXT_BACKFILL_BATCH_SQL = _BACKFILL_BATCH_SQL.replace("COALESCE(content, '')", INDEXED)

DEFAULT_BATCH_SIZE = 1000


def chunks_awaiting_backfill() -> int:
    """How many chunks still have no keyword index."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE search_vector IS NULL")
        return cursor.fetchone()[0]


def backfill_chunk_keyword_index(
    *, batch_size: int = DEFAULT_BATCH_SIZE, limit: int = 0, on_batch=None,
    keyword_text: bool = False,
) -> int:
    """Fill the keyword index for chunks that have none. Returns the count.

    `limit` of 0 means the whole table. `on_batch` receives the running total.
    `keyword_text` reads that column first; off only for migration 0015,
    which ran before it existed.
    """
    sql = _KEYWORD_TEXT_BACKFILL_BATCH_SQL if keyword_text else _BACKFILL_BATCH_SQL
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    filled = 0
    with connection.cursor() as cursor:
        while True:
            size = batch_size
            if limit:
                size = min(size, limit - filled)
                if size < 1:
                    break
            cursor.execute(sql, [size])
            if not cursor.rowcount:
                break
            filled += cursor.rowcount
            if on_batch is not None:
                on_batch(filled)
    return filled
