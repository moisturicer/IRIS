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
"""

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

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
        record = Record.objects.create(
            title=f"{MARKER} {label}",
            abstract=f"{MARKER} sensor networks for upland farms, {label}.",
            record_type=RecordType.objects.get(name=type_name),
            added_by=cls.owner,
            adviser=cls.adviser,
            pipeline_status=pipeline_status,
        )
        RecordOwner.objects.create(record=record, user=cls.owner, is_primary=True)
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
        response = self.client.post(AI_SEARCH, {"query": MARKER, "top_k": 20}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        returned = {row["id"] for row in response.data["results"]}
        self.assertIn(self.published_thesis.pk, returned)
        self.assertNotIn(self.approved_proposal.pk, returned)
        self.assertNotIn(self.completed_proposal.pk, returned)

    def test_ask_iris_ask_never_cites_a_proposal(self):
        # Even for the owner: retrieval reads the public catalogue, so an answer
        # never cites a record a *different* reader of the answer could not open.
        for label, user in (("stranger", self.stranger), ("owner", self.owner)):
            with self.subTest(user=label):
                cache.clear()
                self.as_user(user)
                response = self.client.post(
                    AI_ASK, {"question": f"What is known about {MARKER}?", "top_k": 20},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

                cited = set(response.data["citations"])
                sourced = {s["id"] for s in response.data["sources"]}
                self.assertIn(self.published_thesis.pk, cited)
                for proposal in self.proposals:
                    self.assertNotIn(proposal.pk, cited)
                    self.assertNotIn(proposal.pk, sourced)

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
