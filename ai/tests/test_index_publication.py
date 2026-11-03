"""IR-751: indexing worker behavior at the resumable publication boundary."""

import pytest


def test_indexing_rejects_unconfigured_bounds_before_connecting():
    from ai.ingestion.indexing import Bounds

    with pytest.raises(ValueError):
        Bounds(
            lease_seconds=0,
            timeout_seconds=10,
            max_attempts=3,
            max_input_tokens=1000,
            max_cost_usd=1,
        )
