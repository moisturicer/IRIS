"""The headline test for IR-129, and the reason `Retriever` is a seam at all.

Given a user and a corpus containing chunks they cannot read, retrieval must
never return one -- not ranked lower, not filtered afterwards, **never
returned**. Asserted at the seam across every visibility ground
`Record.objects.visible_to` distinguishes, because a citation that points at a
record the reader cannot open is a confidentiality breach rather than a bug.

Runs against a deterministic fake embedder, so it needs no vendor account. A
security test that only runs where a paid API key is configured is a security
test that does not run.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet, DocumentChunk
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.retrieval.two_stage import TwoStageRetriever
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_ADVISER, ROLE_KTTO, ROLE_STUDENT

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

User = get_user_model()

#: The vector columns are declared at `VECTOR_COLUMN_DIMENSIONS`, so test
#: vectors have to be that wide whatever the fake would rather produce.
DIMENSIONS = VECTOR_COLUMN_DIMENSIONS


@pytest.fixture
def space(db):
    """The active space, not a new one.

    `one_active_embedding_space` is a database constraint: exactly one row may
    be active, which is what stops indexing and querying silently disagreeing.
    A test that created its own would be testing a state production forbids.
    """
    existing = EmbeddingSpace.objects.filter(state="active").first()
    if existing is not None:
        return existing
    return EmbeddingSpace.objects.create(
        model_id="fake-test", dimensions=DIMENSIONS, metric="cosine", state="active"
    )


@pytest.fixture
def embedder():
    return DeterministicEmbeddingProvider(dimensions=DIMENSIONS)


def make_user(email, role_name=None):
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="x", role=role, is_verified=True
    )


def make_record(*, title, status, owner=None, adviser=None, embedder=None, space=None,
                text="sampling procedure for tilapia ponds"):
    """A record with one active chunk set, one chunk and its vector."""
    record = Record.objects.create(title=title, pipeline_status=status, adviser=adviser)
    if owner is not None:
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)

    RecordEmbedding.objects.create(
        record=record,
        embedding=embedder.embed_documents([title])[0],
        model_name="fake-test",
    )
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash="h", strategy_id="s",
        options={}, content_hash="c", is_active=True,
    )
    chunk = DocumentChunk.objects.create(
        chunk_set=chunk_set, record=record, sequence=0, max_sequence=0,
        text=text, content=text, context_path=[title],
        token_count=len(text.split()), text_hash=f"t{record.pk}",
        source_page=1, element_kinds=["paragraph"], bboxes=[],
    )
    ChunkEmbedding.objects.create(
        chunk=chunk, space=space, embedding=embedder.embed_documents([text])[0]
    )
    return record


@pytest.fixture
def retriever(embedder):
    return TwoStageRetriever(embedder=embedder)


class VisibilityTests:
    """Four grounds, per `visible_to`'s docstring, plus the anonymous case."""

    def test_a_stranger_never_receives_another_users_draft(self, retriever, embedder, space):
        author = make_user("author@cit.edu", ROLE_STUDENT)
        make_record(title="Secret Draft", status=PipelineStatus.DRAFT,
                    owner=author, embedder=embedder, space=space)
        stranger = make_user("stranger@cit.edu", ROLE_STUDENT)

        assert retriever.retrieve("sampling procedure", stranger).passages == ()

    def test_an_owner_receives_their_own_draft(self, retriever, embedder, space):
        author = make_user("author@cit.edu", ROLE_STUDENT)
        make_record(title="My Draft", status=PipelineStatus.DRAFT,
                    owner=author, embedder=embedder, space=space)

        results = retriever.retrieve("sampling procedure", author)
        assert [p.record_title for p in results.passages] == ["My Draft"]

    def test_office_staff_receive_everything(self, retriever, embedder, space):
        author = make_user("author@cit.edu", ROLE_STUDENT)
        make_record(title="Someone's Draft", status=PipelineStatus.DRAFT,
                    owner=author, embedder=embedder, space=space)
        ktto = make_user("ktto@cit.edu", ROLE_KTTO)

        assert len(retriever.retrieve("sampling procedure", ktto).passages) == 1

    def test_the_assigned_adviser_receives_the_record_they_advise(
        self, retriever, embedder, space
    ):
        adviser = make_user("adviser@cit.edu", ROLE_ADVISER)
        other_adviser = make_user("other@cit.edu", ROLE_ADVISER)
        author = make_user("author@cit.edu", ROLE_STUDENT)
        make_record(title="Advised Draft", status=PipelineStatus.DRAFT, owner=author,
                    adviser=adviser, embedder=embedder, space=space)

        assert len(retriever.retrieve("sampling procedure", adviser).passages) == 1
        assert retriever.retrieve("sampling procedure", other_adviser).passages == (), (
            "the adviser role alone must grant nothing -- the grant is the FK"
        )

    def test_any_authenticated_user_receives_the_public_catalogue(
        self, retriever, embedder, space
    ):
        author = make_user("author@cit.edu", ROLE_STUDENT)
        make_record(title="Published Work", status=PipelineStatus.PUBLISHED,
                    owner=author, embedder=embedder, space=space)
        reader = make_user("reader@cit.edu", ROLE_STUDENT)

        assert len(retriever.retrieve("sampling procedure", reader).passages) == 1

    def test_an_anonymous_user_receives_nothing(self, retriever, embedder, space):
        from django.contrib.auth.models import AnonymousUser

        author = make_user("author@cit.edu", ROLE_STUDENT)
        make_record(title="Published Work", status=PipelineStatus.PUBLISHED,
                    owner=author, embedder=embedder, space=space)

        assert retriever.retrieve("sampling procedure", AnonymousUser()).passages == ()

    def test_a_readable_record_does_not_leak_its_neighbours(
        self, retriever, embedder, space
    ):
        """The case that catches filtering *after* scoring: a permitted record
        ranking alongside a forbidden one must not carry it along."""
        author = make_user("author@cit.edu", ROLE_STUDENT)
        stranger = make_user("stranger@cit.edu", ROLE_STUDENT)
        make_record(title="Public One", status=PipelineStatus.PUBLISHED,
                    owner=author, embedder=embedder, space=space)
        make_record(title="Private One", status=PipelineStatus.DRAFT,
                    owner=author, embedder=embedder, space=space)

        titles = [
            p.record_title
            for p in retriever.retrieve("sampling", stranger).passages
        ]
        assert titles == ["Public One"]
