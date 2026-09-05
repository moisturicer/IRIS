"""Idempotency keys (IR-115 G).

A duplicate delivery from Celery must find the key already claimed and
return. Without it, a retry storm during a provider timeout spends the
token budget several times over on identical work.
"""

from apps.ai.ingestion import ingestion_job_key


def test_the_same_inputs_produce_the_same_key():
    args = dict(record_id=7, extraction_hash="e1", strategy_id="s1", space_id=3)

    assert ingestion_job_key(**args) == ingestion_job_key(**args)


def test_the_key_is_stable_across_processes():
    """Pinned digest: a key derived from ``hash()`` would be randomised per
    process, so a duplicate delivery landing on a different worker would
    miss and pay for the work twice."""
    key = ingestion_job_key(
        record_id=7, extraction_hash="e1", strategy_id="s1", space_id=3
    )

    assert key == (
        "23fce3c817f4181caa6b0cec9302773310839c4bda9eff1b57700fb7f9ea8896"
    )


def test_every_component_changes_the_key():
    base = dict(record_id=7, extraction_hash="e1", strategy_id="s1", space_id=3)
    keys = {ingestion_job_key(**base)}
    for field, other in [
        ("record_id", 8),
        ("extraction_hash", "e2"),
        ("strategy_id", "s2"),
        ("space_id", 4),
    ]:
        keys.add(ingestion_job_key(**{**base, field: other}))

    assert len(keys) == 5


def test_components_cannot_bleed_into_one_another():
    """Concatenating the parts without a separator would make
    ("ab", "c") and ("a", "bc") the same job."""
    assert ingestion_job_key(
        record_id=1, extraction_hash="ab", strategy_id="c", space_id=1
    ) != ingestion_job_key(
        record_id=1, extraction_hash="a", strategy_id="bc", space_id=1
    )
