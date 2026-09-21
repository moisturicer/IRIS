"""
IR-264: Proposals leave Discover and Ask IRIS.

ADR-021 §13 narrows `PUBLICLY_VISIBLE_STATUSES` to `(PUBLISHED,)`. Before this
change it also held `approved` and `completed`, and only a Proposal ever reaches
those two -- so every approved or completed Proposal was part of the public
catalogue: listed in Discover, openable by any account, and retrievable and
citable by Ask IRIS.

**One predicate, so every surface is asserted.** The change is to the single
visibility predicate (CLAUDE.md: "one predicate used everywhere, including RAG
retrieval"), not a Discover-only filter. A Discover-only filter would still let
an unrelated user open a Proposal by id and let Ask IRIS cite it, so each of
those is checked here through its own endpoint rather than inferred from the
Record list.

**Deletion is decoupled, not narrowed.** `perform_destroy` and the
`REQUEST_DELETE` edges used to branch on the public set. Narrowing it alone
would let an owner soft-delete an approved Proposal with no review; they branch
on `DELETE_REVIEW_STATUSES` instead, so deletion behaves exactly as before.

**Seam: the API** -- the records, Ask IRIS and dashboard endpoints.

**Fixtures carry real chunks and vectors (added when this test met IR-283's
chunk-based retrieval on merge).** Ask IRIS answers from indexed chunks now,
not from a record's title and abstract by full-text search, so a record with
no chunk set is invisible to every retrieval path regardless of who may read
it -- that would make the assertions below true for the wrong reason. Every
fixture, **including both Proposals**, gets a record vector and one chunk
with its own vector, so what is actually being tested is the *visibility*
predicate keeping a chunked, embedded Proposal out -- not merely that an
unindexed one was never a candidate. The disclosure gate is opened for these
requests (`root_with`, below): `Record` carries no embargo field yet
(IR-250), so the real gate refuses every record and these tests would pass
vacuously against an empty response otherwise. The gate's own refusal is
exercised in `apps/ai/policy/tests/`.
"""

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet, DocumentChunk
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import (
    DeterministicEmbeddingProvider,
    ScriptedLLM,
    ScriptedReranker,
)
from apps.accounts.models import Role, User
from apps.records.models import DeleteRequest, Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RoleName

RECORDS = "/api/v1/records/"
AI_SEARCH = "/api/v1/ai/search/"
AI_ASK = "/api/v1/ai/ask/"
AI_STATUS = "/api/v1/ai/status/"
DASHBOARD_STATS = "/api/v1/dashboard/stats/"

#: A word only these fixtures use, so Ask IRIS retrieval matches all three and
#: nothing seeded, and a result's absence is about visibility, not ranking.
MARKER = "Zyphorin"


def root_with(embedder):
    """A composition root whose vendors are fakes and whose disclosure gate
    allows -- see the module docstring's note on why the gate is opened.
    """
    return CompositionRoot(
        embedder=embedder,
        reranker=ScriptedReranker(),
        llm=ScriptedLLM(),
        permits=lambda record: True,
    )


def _user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class ProposalVisibilityTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("vis-owner@cit.edu", RoleName.STUDENT)
        cls.stranger = _user("vis-stranger@cit.edu", RoleName.STUDENT)
        cls.adviser = _user("vis-adviser@cit.edu", RoleName.ADVISER)
        cls.other_adviser = _user("vis-other-adviser@cit.edu", RoleName.ADVISER)
        cls.itso = _user("vis-itso@cit.edu", RoleName.ITSO)
        cls.rdco = _user("vis-rdco@cit.edu", RoleName.RDCO)

        cls.embedder = DeterministicEmbeddingProvider(dimensions=VECTOR_COLUMN_DIMENSIONS)
        cls.space = EmbeddingSpace.objects.filter(state="active").first()
        if cls.space is None:
            cls.space = EmbeddingSpace.objects.create(
                model_id="fake-test",
                dimensions=VECTOR_COLUMN_DIMENSIONS,
                metric="cosine",
                state="active",
            )

        cls.approved_proposal = cls.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.APPROVED, "approved proposal"
        )
        cls.completed_proposal = cls.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.COMPLETED, "completed proposal"
        )
        cls.published_thesis = cls.make_record(
            RecordTypeName.THESIS_RESEARCH, PipelineStatus.PUBLISHED, "published thesis"
        )
        cls.proposals = (cls.approved_proposal, cls.completed_proposal)

    @classmethod
    def make_record(cls, type_name, pipeline_status, label):
        """A record IRIS can actually retrieve from (IR-283): a record
        vector for stage 1, and one chunk with its own vector for stage 2.
        Every fixture is indexed identically -- Proposals included -- so the
        Ask IRIS tests below prove the visibility predicate keeps a Proposal
        out, rather than merely observing that an unindexed one was never a
        candidate."""
        text = f"{MARKER} sensor networks for upland farms, {label}."
        record = Record.objects.create(
            title=f"{MARKER} {label}",
            abstract=text,
            record_type=RecordType.objects.get(name=type_name),
            added_by=cls.owner,
            adviser=cls.adviser,
            pipeline_status=pipeline_status,
        )
        RecordOwner.objects.create(record=record, user=cls.owner, is_primary=True)

        RecordEmbedding.objects.create(
            record=record,
            embedding=cls.embedder.embed_documents([f"{record.title}. {text}"])[0],
            model_name=cls.space.model_id,
        )
        chunk_set = ChunkSet.objects.create(
            record=record, extraction_hash=f"e{record.pk}", strategy_id="s",
            options={}, content_hash=f"c{record.pk}", is_active=True,
        )
        chunk = DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=0, max_sequence=0,
            text=text, content=text, context_path=[record.title],
            token_count=len(text.split()), text_hash=f"t{record.pk}",
            source_page=1, element_kinds=["paragraph"], bboxes=[],
        )
        ChunkEmbedding.objects.create(
            chunk=chunk, space=cls.space, embedding=cls.embedder.embed_documents([text])[0]
        )
        return record

    def setUp(self):
        # Ask IRIS is throttled per user through the cache; a full-suite run
        # must not carry another module's requests into this one's budget.
        cache.clear()

    def as_user(self, user):
        self.client.force_authenticate(user)

    def listed_ids(self, user):
        self.as_user(user)
        response = self.client.get(RECORDS, {"page_size": 100, "search": MARKER})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["id"] for row in response.data["results"]}

    def detail_status(self, user, record):
        self.as_user(user)
        return self.client.get(f"{RECORDS}{record.pk}/").status_code

    # --- Discover and record detail -------------------------------------------

    def test_an_unrelated_user_does_not_see_proposals_in_discover(self):
        listed = self.listed_ids(self.stranger)
        self.assertNotIn(self.approved_proposal.pk, listed)
        self.assertNotIn(self.completed_proposal.pk, listed)

    def test_an_unrelated_user_opening_a_proposal_gets_404(self):
        for proposal in self.proposals:
            with self.subTest(status=proposal.pipeline_status):
                self.assertEqual(
                    self.detail_status(self.stranger, proposal),
                    status.HTTP_404_NOT_FOUND,
                )

    def test_an_unassigned_adviser_opening_a_proposal_gets_404(self):
        # The Adviser role alone grants nothing; only the `adviser` FK does.
        for proposal in self.proposals:
            with self.subTest(status=proposal.pipeline_status):
                self.assertEqual(
                    self.detail_status(self.other_adviser, proposal),
                    status.HTTP_404_NOT_FOUND,
                )

    def test_the_owner_adviser_and_offices_can_still_open_proposals(self):
        for label, user in (
            ("owner", self.owner),
            ("assigned adviser", self.adviser),
            ("ITSO", self.itso),
            ("RDCO", self.rdco),
        ):
            for proposal in self.proposals:
                with self.subTest(user=label, status=proposal.pipeline_status):
                    self.assertEqual(
                        self.detail_status(user, proposal), status.HTTP_200_OK
                    )

    def test_a_published_thesis_is_unaffected(self):
        self.assertIn(self.published_thesis.pk, self.listed_ids(self.stranger))
        self.assertEqual(
            self.detail_status(self.stranger, self.published_thesis),
            status.HTTP_200_OK,
        )

    # --- Ask IRIS --------------------------------------------------------------

    def test_ask_iris_search_never_returns_a_proposal(self):
        self.as_user(self.stranger)
        with use_composition_root(root_with(self.embedder)):
            response = self.client.post(
                AI_SEARCH, {"query": MARKER, "top_k": 20}, format="json"
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # `results` is passages, not records (IR-284): several can come from
        # one paper, so this reads the record each passage belongs to.
        returned = {row["record_id"] for row in response.data["results"]}
        self.assertIn(self.published_thesis.pk, returned)
        self.assertNotIn(self.approved_proposal.pk, returned)
        self.assertNotIn(self.completed_proposal.pk, returned)

    def test_ask_iris_ask_never_cites_a_proposal_to_a_stranger(self):
        # A stranger owns neither Proposal and neither is published, so under
        # `visible_to(user)` -- the one predicate retrieval now applies
        # (IR-283/285) -- both are simply not candidates.
        cache.clear()
        self.as_user(self.stranger)
        with use_composition_root(root_with(self.embedder)):
            response = self.client.post(
                AI_ASK, {"question": f"What is known about {MARKER}?", "top_k": 20},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # A citation is an object carrying the record it belongs to, the
        # page, and the quote (IR-284) -- not a bare id.
        cited = {c["record_id"] for c in response.data["citations"]}
        sourced = {s["id"] for s in response.data["sources"]}
        self.assertIn(self.published_thesis.pk, cited)
        for proposal in self.proposals:
            self.assertNotIn(proposal.pk, cited)
            self.assertNotIn(proposal.pk, sourced)

    def test_ask_iris_still_answers_the_owner_from_their_own_proposal(self):
        # Not the mirror of the stranger case above. `test_an_owner_receives_
        # their_own_draft` (apps/ai/retrieval/tests/test_visibility.py) is an
        # established security property: retrieval is `visible_to(user)`
        # everywhere (CLAUDE.md's "one predicate used everywhere, including
        # RAG retrieval"), and an owner's own Proposal is visible to them by
        # that same rule. IR-264 narrowed who else can find a Proposal, not
        # what its owner can. This only pins that the owner's own question
        # still gets an answer at all -- which record it draws on is theirs
        # to have retrievable, not this test's concern.
        cache.clear()
        self.as_user(self.owner)
        with use_composition_root(root_with(self.embedder)):
            response = self.client.post(
                AI_ASK, {"question": f"What is known about {MARKER}?", "top_k": 20},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["citations"], "the owner's own question found nothing")

    def test_similar_records_never_suggest_a_proposal(self):
        # The paper view's "similar" list reuses Ask IRIS retrieval. Every
        # fixture shares MARKER, so both Proposals would rank as matches for the
        # thesis if they were still in the catalogue.
        self.as_user(self.stranger)
        response = self.client.get(f"{RECORDS}{self.published_thesis.pk}/similar/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        suggested = {row["id"] for row in response.data["results"]}
        for proposal in self.proposals:
            self.assertNotIn(proposal.pk, suggested)

    def test_ask_iris_status_count_excludes_proposals(self):
        self.as_user(self.stranger)
        response = self.client.get(AI_STATUS)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            response.data["indexed_records"],
            Record.objects.filter(pipeline_status=PipelineStatus.PUBLISHED).count(),
        )

    # --- deletion is decoupled from visibility --------------------------------

    def test_deleting_an_approved_or_completed_proposal_raises_a_delete_request(self):
        for proposal in self.proposals:
            with self.subTest(status=proposal.pipeline_status):
                previous = proposal.pipeline_status
                self.as_user(self.owner)
                response = self.client.delete(f"{RECORDS}{proposal.pk}/")
                self.assertEqual(
                    response.status_code, status.HTTP_204_NO_CONTENT, response.data
                )

                proposal.refresh_from_db()
                self.assertEqual(proposal.pipeline_status, PipelineStatus.PENDING_DELETE)
                self.assertFalse(proposal.is_deleted, "deleted without RDCO review")
                request = DeleteRequest.objects.get(record=proposal)
                self.assertEqual(request.previous_pipeline_status, previous)

    # --- the owner's own dashboard --------------------------------------------

    def test_the_owners_dashboard_still_counts_their_approved_proposals(self):
        # `approved_mine` is about the owner's own accepted work, not the public
        # catalogue; narrowing visibility must not make a student's approved
        # Proposal vanish from their own count.
        self.as_user(self.owner)
        response = self.client.get(DASHBOARD_STATS)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["approved_mine"], 3)
