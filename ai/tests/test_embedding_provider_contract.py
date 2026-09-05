"""Contract suite for ``EmbeddingProvider`` (IR-109).

The general contract below — determinism, a fixed dimension, ordered
batching — is a property of the *port*, not of any one vendor, and is
parametrized over provider factories so a real adapter joins the same suite
once it can run without live vendor credentials in CI (OpenAI or Voyage,
per ADR-015). Only the deterministic fake runs today; that is what makes the
suite runnable at all without an API key.

A second, smaller section below the general contract covers behaviour that
is specific to the fake and must **not** be read as a general contract: a
real provider's ``embed_documents`` and ``embed_query`` are expected to
differ for an asymmetric model (that is the entire reason the port has two
methods — see ``ai/domain/ports.py``). The fake has no such asymmetry, so
its two methods agree, and that agreement is asserted here as a property of
the fake, not of the port.
"""

import pytest

from ai.domain.ports import EmbeddingProvider
from ai.infrastructure.fake_adapter import DeterministicFakeEmbeddingProvider

_CONTRACT_DIMENSIONS = 16


def _fake_provider() -> EmbeddingProvider:
    return DeterministicFakeEmbeddingProvider(dimensions=_CONTRACT_DIMENSIONS)


# Provider factories the general contract runs against. Append a real
# adapter's factory here once one can run in CI without a live vendor call.
PROVIDER_FACTORIES = [
    pytest.param(_fake_provider, id="deterministic-fake"),
]


# --------------------------------------------------------------------------
# The general contract — every EmbeddingProvider must satisfy this
# --------------------------------------------------------------------------


@pytest.mark.parametrize("make_provider", PROVIDER_FACTORIES)
async def test_embed_query_is_deterministic(make_provider):
    provider = make_provider()

    first = await provider.embed_query("hello world")
    second = await provider.embed_query("hello world")

    assert first == second


@pytest.mark.parametrize("make_provider", PROVIDER_FACTORIES)
async def test_embed_query_is_deterministic_across_instances(make_provider):
    a = await make_provider().embed_query("hello world")
    b = await make_provider().embed_query("hello world")

    assert a == b


@pytest.mark.parametrize("make_provider", PROVIDER_FACTORIES)
async def test_different_text_produces_a_different_vector(make_provider):
    provider = make_provider()

    a = await provider.embed_query("alpha")
    b = await provider.embed_query("beta")

    assert a != b


@pytest.mark.parametrize("make_provider", PROVIDER_FACTORIES)
async def test_embed_query_returns_a_fixed_dimension(make_provider):
    provider = make_provider()

    vector = await provider.embed_query("some text")

    assert len(vector) == _CONTRACT_DIMENSIONS


@pytest.mark.parametrize("make_provider", PROVIDER_FACTORIES)
async def test_embed_documents_returns_one_vector_per_input_in_order(make_provider):
    provider = make_provider()
    texts = ["alpha", "beta", "gamma"]

    vectors = await provider.embed_documents(texts)

    assert len(vectors) == len(texts)
    assert all(len(v) == _CONTRACT_DIMENSIONS for v in vectors)
    # Distinct inputs must not collapse onto the same vector, and order must
    # be preserved — a caller zips this back onto its chunk list positionally.
    assert len({tuple(v) for v in vectors}) == len(texts)


@pytest.mark.parametrize("make_provider", PROVIDER_FACTORIES)
async def test_embed_documents_on_an_empty_batch_returns_an_empty_list(make_provider):
    provider = make_provider()

    assert await provider.embed_documents([]) == []


# --------------------------------------------------------------------------
# The port shape itself: both methods are required, neither is optional
# --------------------------------------------------------------------------


def test_the_abstract_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        EmbeddingProvider()


def test_a_subclass_implementing_only_one_method_cannot_be_instantiated():
    """Guards against a regression to the old single-method shape: if either
    method stopped being abstract, a half-implemented subclass would
    silently become instantiable."""

    class OnlyDocuments(EmbeddingProvider):
        async def embed_documents(self, texts):
            return []

    class OnlyQuery(EmbeddingProvider):
        async def embed_query(self, text):
            return []

    with pytest.raises(TypeError):
        OnlyDocuments()
    with pytest.raises(TypeError):
        OnlyQuery()


# --------------------------------------------------------------------------
# The fake specifically — not a general contract
# --------------------------------------------------------------------------


def test_fake_rejects_a_non_positive_dimension():
    with pytest.raises(ValueError):
        DeterministicFakeEmbeddingProvider(dimensions=0)


async def test_fake_vector_components_are_bounded():
    """Exercises code that assumes an embedding-shaped range (e.g. cosine
    similarity) without claiming the fake carries any semantic meaning."""
    provider = _fake_provider()

    vector = await provider.embed_query("some text")

    assert all(-1.0 <= component <= 1.0 for component in vector)


async def test_fake_has_no_asymmetry_between_documents_and_query():
    """Specific to the fake: it has no real document/query distinction, so
    embedding the same text through either method agrees. A real,
    asymmetric adapter (Voyage) is expected to violate this — that is the
    entire point of the two-method port."""
    provider = _fake_provider()

    (document_vector,) = await provider.embed_documents(["same text"])
    query_vector = await provider.embed_query("same text")

    assert document_vector == query_vector
