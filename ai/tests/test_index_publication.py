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


def test_embedding_transport_shares_trimmed_credential_account_identity():
    from ai.ingestion.embeddings import VoyageContextEmbeddings

    provider = VoyageContextEmbeddings(
        " abc ", model="voyage-context-4", dimensions=1024, data_policy="no-training"
    )
    assert provider.account == "ba7816bf8f01cfea414140de5dae2223"
    with pytest.raises(ValueError):
        VoyageContextEmbeddings(
            " ", model="voyage-context-4", dimensions=1024, data_policy="no-training"
        )
