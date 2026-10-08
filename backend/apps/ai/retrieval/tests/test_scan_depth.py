"""`scan_depth` restores `hnsw.ef_search` rather than leaking it (IR-469).

`transaction.atomic()` is only a savepoint inside the outer transaction every
`django_db` test already runs in, so `set_config(..., true)` outlives the
`with scan_depth():` block unless something puts the prior value back.
`apps/ai/index_health.py::_planner` hit the identical leak for planner flags
(IR-442); this is the same fix applied to `scan_depth`.
"""

import pytest
from django.db import connection

from apps.ai.retrieval.scan_depth import scan_depth

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _current_ef_search() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('hnsw.ef_search', true)")
        return cursor.fetchone()[0] or "40"


def test_the_setting_does_not_outlive_the_block(settings):
    settings.AI_HNSW_EF_SEARCH = 777
    before = _current_ef_search()

    with scan_depth():
        assert _current_ef_search() == "777"

    assert _current_ef_search() == before


def test_it_is_restored_even_when_the_block_raises(settings):
    settings.AI_HNSW_EF_SEARCH = 777
    before = _current_ef_search()

    with pytest.raises(RuntimeError):
        with scan_depth():
            raise RuntimeError("boom")

    assert _current_ef_search() == before


def test_a_later_block_is_not_affected_by_an_earlier_ones_depth(settings):
    """Two unrelated callers in the same transaction must each get the
    depth configured for them, not whatever the previous caller left."""
    settings.AI_HNSW_EF_SEARCH = 777
    with scan_depth():
        pass

    settings.AI_HNSW_EF_SEARCH = 55
    with scan_depth():
        assert _current_ef_search() == "55"
