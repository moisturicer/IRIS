"""HNSW scan depth for filtered vector queries (IR-440).

pgvector scans `hnsw.ef_search` rows (default 40), then applies the WHERE
clause, so a filtered query returns at most 40 rows whatever its LIMIT.

`set_config(..., true)` is transaction-local, so it is safe behind PgBouncer
transaction mode, and it works before the pgvector library has loaded.
"""

from __future__ import annotations

from contextlib import contextmanager

from django.conf import settings
from django.db import connection, transaction

#: pgvector accepts 1..1000.
MAX_EF_SEARCH = 1000


def configured_depth() -> int:
    return max(1, min(int(settings.AI_HNSW_EF_SEARCH), MAX_EF_SEARCH))


@contextmanager
def scan_depth():
    """Run vector queries at the configured depth.

    Evaluate querysets inside the block; a lazy one run later uses 40. Inside
    an outer transaction the depth lasts until that transaction ends.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('hnsw.ef_search', %s, true)",
                [str(configured_depth())],
            )
        yield
