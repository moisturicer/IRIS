"""Related institutional works, on record vectors (IR-285, ADR-029 §5, §7).

`GET /records/<id>/similar/` used to rank with record-level PostgreSQL
full-text search through `publicly_visible()` — the second, narrower
visibility rule the rest of this work spent three tickets removing. It was the
last caller of the module IR-285 deletes.

So these are two assertions in one file, deliberately: that similarity means
what ADR-029 says it means, and that it is governed by the **same** predicate
as every other retrieval result. The second is the one that matters, and it is
asserted at the HTTP boundary, because that is where a leak would be visible.

Runs against a deterministic fake embedder — no vendor account, for the reason
`retrieval/tests/test_visibility.py` states: a security test that only runs
where a paid key is configured is a security test that does not run.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.tests.corpus import seed_record_vector
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.similarity import similar_records
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_STUDENT

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

User = get_user_model()

DIMENSIONS = VECTOR_COLUMN_DIMENSIONS


@pytest.fixture
def space(db):
    existing = EmbeddingSpace.objects.filter(state="active").first()
    if existing is not None:
        return existing
    return EmbeddingSpace.objects.create(
        model_id="fake-test", dimensions=DIMENSIONS, metric="cosine", state="active"
    )


@pytest.fixture
def embedder():
    return DeterministicEmbeddingProvider(dimensions=DIMENSIONS)


def make_user(email, role_name=ROLE_STUDENT):
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="x", role=role, is_verified=True
    )


def make_record(*, title, abstract, embedder, status=PipelineStatus.PUBLISHED,
                owner=None, embedded=True):
    """A record and, unless a test says otherwise, its summary vector.

    `embedded=False` is the state of any paper the disclosure gate has refused,
    which includes every paper with no embargo answer (ADR-052).
    """
    record = Record.objects.create(
        title=title, abstract=abstract, pipeline_status=status
    )
    if owner is not None:
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    if embedded:
        seed_record_vector(
            record=record,
            embedding=embedder.embed_documents([f"{title}. {abstract}"])[0],
            model_name="fake-test",
        )
    return record


class SimilarRecordsTests:
    def test_the_closest_record_by_meaning_ranks_first(self, embedder, space):
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction with neural networks",
            abstract="rainfall gauge data convolutional network catchment",
            embedder=embedder,
        )
        near = make_record(
            title="Rainfall gauge networks for catchment flooding",
            abstract="convolutional network rainfall catchment prediction",
            embedder=embedder,
        )
        make_record(
            title="Tilapia pond stocking",
            abstract="brackish water fingerling sampling aquaculture",
            embedder=embedder,
        )

        ranked = similar_records(seed, reader, limit=3)

        assert [m.record.pk for m in ranked][0] == near.pk

    def test_a_record_is_never_similar_to_itself(self, embedder, space):
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall", embedder=embedder
        )
        make_record(title="Flood prediction", abstract="rainfall", embedder=embedder)

        ranked = similar_records(seed, reader, limit=5)

        # A record seeded with its own text matches itself perfectly, which
        # would fill the panel with the paper the reader is already reading.
        assert seed.pk not in [m.record.pk for m in ranked]

    def test_a_record_the_reader_may_not_open_is_never_returned(
        self, embedder, space
    ):
        """The point of the migration. The old path used `publicly_visible()`,
        a second and narrower rule; this uses the one every other retrieval
        result is governed by."""
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall catchment", embedder=embedder
        )
        hidden = make_record(
            title="Flood prediction draft",
            abstract="rainfall catchment",
            status=PipelineStatus.DRAFT,
            owner=author,
            embedder=embedder,
        )

        assert hidden.pk not in [m.record.pk for m in similar_records(seed, stranger)]
        # ...and the owner, who may read it, does get it — which is what makes
        # the assertion above about permission rather than about emptiness.
        assert hidden.pk in [m.record.pk for m in similar_records(seed, author)]

    def test_nothing_comes_back_when_the_seed_has_no_vector(self, embedder, space):
        """The state of a record the disclosure gate has refused: it has no
        vector, so this endpoint is empty rather than wrong."""
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction",
            abstract="rainfall",
            embedder=embedder,
            embedded=False,
        )
        make_record(title="Rainfall", abstract="catchment", embedder=embedder)

        assert similar_records(seed, reader) == []

    def test_a_vector_from_another_model_is_never_compared(self, embedder, space):
        """Two models' vectors are not comparable, and a cosine between them
        is a number rather than an error — ordinary-looking rankings that mean
        nothing. Mid-rollout is exactly when both exist."""
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall catchment", embedder=embedder
        )
        other = make_record(
            title="Rainfall catchment",
            abstract="rainfall catchment",
            embedder=embedder,
            embedded=False,
        )
        seed_record_vector(
            record=other,
            embedding=embedder.embed_documents(["rainfall catchment"])[0],
            model_name="some-older-model",
            keyed=False,
        )

        assert similar_records(seed, reader) == []

    def test_the_caller_decides_how_many(self, embedder, space):
        reader = make_user("reader@cit.edu")
        seed = make_record(title="Flood", abstract="rainfall", embedder=embedder)
        for n in range(4):
            make_record(title=f"Rainfall {n}", abstract="catchment", embedder=embedder)

        assert len(similar_records(seed, reader, limit=2)) == 2


class SimilarEndpointTests:
    def test_the_endpoint_returns_record_cards(self, embedder, space):
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall catchment", embedder=embedder
        )
        near = make_record(
            title="Rainfall catchment study",
            abstract="rainfall catchment",
            embedder=embedder,
        )

        client = APIClient()
        client.force_authenticate(user=reader)
        response = client.get(reverse("record-similar", args=[seed.pk]))

        assert response.status_code == 200
        results = response.json()["results"]
        assert [r["id"] for r in results] == [near.pk]
        assert results[0]["title"] == "Rainfall catchment study"
        assert "score" in results[0]

    def test_the_endpoint_never_names_a_record_the_reader_may_not_open(
        self, embedder, space
    ):
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall catchment", embedder=embedder
        )
        make_record(
            title="Secret rainfall catchment draft",
            abstract="rainfall catchment",
            status=PipelineStatus.DRAFT,
            owner=author,
            embedder=embedder,
        )

        client = APIClient()
        client.force_authenticate(user=stranger)
        response = client.get(reverse("record-similar", args=[seed.pk]))

        assert response.json()["results"] == []

    # -- IR-568: the endpoint says why a list is empty --------------------------
    #
    # The reader sees only the *seed's own* coverage (it is a Record they can
    # already open) and never why a candidate is missing (IR-460).

    def _get(self, reader, seed):
        client = APIClient()
        client.force_authenticate(user=reader)
        return client.get(reverse("record-similar", args=[seed.pk]))

    def test_a_list_with_matches_is_ready(self, embedder, space):
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall catchment", embedder=embedder
        )
        make_record(
            title="Rainfall catchment study", abstract="rainfall catchment", embedder=embedder
        )

        response = self._get(reader, seed)

        assert response.status_code == 200
        assert response.json()["state"] == "ready"
        assert len(response.json()["results"]) == 1

    def test_an_indexed_seed_with_no_neighbour_is_no_matches(self, embedder, space):
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall catchment", embedder=embedder
        )

        response = self._get(reader, seed)

        assert response.status_code == 200
        assert response.json() == {"state": "no_matches", "results": []}

    def test_hidden_candidates_and_no_candidates_answer_identically(self, embedder, space):
        """IR-460: "no matches" never tells a reader whether something close
        exists and is withheld. Whole bodies are compared, so a field added
        later that differs between the two cases fails here."""
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall catchment", embedder=embedder
        )

        without_hidden = self._get(stranger, seed)

        for n in range(3):
            make_record(
                title=f"Rainfall catchment draft {n}",
                abstract="rainfall catchment",
                status=PipelineStatus.DRAFT,
                owner=author,
                embedder=embedder,
            )
        with_hidden = self._get(stranger, seed)

        assert without_hidden.status_code == with_hidden.status_code == 200
        assert with_hidden.json() == without_hidden.json()
        assert with_hidden.json() == {"state": "no_matches", "results": []}
        # The author, who may read the drafts, does see them: the equality
        # above is about permission, not about the drafts being absent.
        assert self._get(author, seed).json()["state"] == "ready"

    def test_a_seed_with_no_vector_is_not_indexed(self, embedder, space):
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall", embedder=embedder, embedded=False
        )
        make_record(title="Rainfall", abstract="catchment", embedder=embedder)

        response = self._get(reader, seed)

        assert response.status_code == 200
        assert response.json() == {"state": "not_indexed", "results": []}

    def test_a_seed_vector_from_another_model_is_incompatible(self, embedder, space):
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall", embedder=embedder, embedded=False
        )
        seed_record_vector(
            record=seed,
            embedding=embedder.embed_documents(["rainfall"])[0],
            model_name="some-older-model",
            keyed=False,
        )
        make_record(title="Rainfall", abstract="catchment", embedder=embedder)

        response = self._get(reader, seed)

        assert response.status_code == 200
        assert response.json() == {"state": "incompatible", "results": []}

    def test_a_failure_while_comparing_is_a_temporary_failure(
        self, embedder, space, monkeypatch
    ):
        reader = make_user("reader@cit.edu")
        seed = make_record(
            title="Flood prediction", abstract="rainfall catchment", embedder=embedder
        )

        def broken(*args, **kwargs):
            raise RuntimeError("vector index unavailable")

        monkeypatch.setattr("apps.ai.similarity._nearest", broken)

        response = self._get(reader, seed)

        assert response.status_code == 503
        # No detail of the failure reaches the reader.
        assert response.json() == {"state": "unavailable", "results": []}

    def test_a_record_the_reader_cannot_open_is_still_a_404(self, embedder, space):
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        draft = make_record(
            title="Private draft",
            abstract="rainfall",
            status=PipelineStatus.DRAFT,
            owner=author,
            embedder=embedder,
            embedded=False,
        )

        # The seed's coverage is stated only for a Record the reader can open.
        assert self._get(stranger, draft).status_code == 404
