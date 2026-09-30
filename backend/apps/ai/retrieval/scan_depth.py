"""How deep pgvector's HNSW index scans for a filtered query (IR-440).

The index visits `hnsw.ef_search` rows (pgvector's default is 40) and only then
applies the WHERE clause. A query filtered to a few records therefore returns
at most 40 rows however large its LIMIT, and the reranker's recall limit of 100
was never reached.

`SET LOCAL` semantics via `set_config(..., true)`: the value lasts for the
enclosing transaction only, so it is safe behind PgBouncer in transaction mode
where a session-level SET would leak into another client. It is also accepted
before the pgvector library has loaded in the session, which `SET` is not.
"""

from __future__ import annotations

from contextlib import contextmanager

from django.conf import settings
from django.db import connection, transaction

#: pgvector refuses values outside 1..1000.
MAX_EF_SEARCH = 1000
DEFAULT_EF_SEARCH = 200


def configured_depth() -> int:
    depth = int(getattr(settings, "AI_HNSW_EF_SEARCH", DEFAULT_EF_SEARCH))
    return max(1, min(depth, MAX_EF_SEARCH))


@contextmanager
def scan_depth():
    """Run the vector queries inside the block at the configured scan depth.

    Evaluate querysets inside the block: a lazy one evaluated after it runs at
    pgvector's default.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('hnsw.ef_search', %s, true)",
                [str(configured_depth())],
            )
        yield
