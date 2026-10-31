"""
An accepted Proposal continues as a new Thesis or Project draft (IR-417;
ADR-032 §6, §12).

At the REST seam IR-255 confirmed, on IR-271's accept: a Proposal reaches
`approved` through its Adviser's real `decide/`, never by setting the status.
One class per acceptance criterion.
"""

from django.db import IntegrityError, transaction
from django.forms.models import model_to_dict
from django.urls import reverse
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITransactionTestCase, APIClient

from apps.documents.testing import real_pdf_bytes
from apps.records.models import Classification, Record, RecordOwner, RecordType
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import PipelineStatus, RecordTypeName

PROPOSAL = RecordTypeName.PROPOSAL


class ConcurrentContinuationTests(APITransactionTestCase):
    def test_simultaneous_requests_make_exactly_one_child(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        from apps.reviews.workflow_test_helpers import make_user
        from core.enums import RoleName

        owner = make_user("concurrent-owner@cit.edu", RoleName.STUDENT)
        proposal_type = RecordType.objects.get_or_create(name=PROPOSAL)[0]
        child_type = RecordType.objects.get_or_create(name=RecordTypeName.PROJECT)[0]
        proposal = Record.objects.create(title="Approved plan", record_type=proposal_type, pipeline_status=PipelineStatus.APPROVED)
        RecordOwner.objects.create(record=proposal, user=owner, is_primary=True)
        barrier = Barrier(2)

        def request_child():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(owner)
                barrier.wait(timeout=10)
                return client.post(continue_url(proposal), {"record_type": child_type.pk}, format="json").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: request_child(), range(2)))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(Record.objects.filter(derived_from=proposal).count(), 1)


def continue_url(record):
    return reverse("record-continue-as", args=[record.pk])


class ContinuationTestBase(DecisionTestBase):

    def accepted_proposal(self, **extra):
        """A Proposal its Adviser accepted, resting `approved`."""
        record = self.at_adviser(PROPOSAL, **extra)
        self.decided(record, self.adviser, "accept", "A sound plan; proceed.")
        return record

    def type_id(self, name):
        return RecordType.objects.get_or_create(name=name)[0].pk

    def snapshot(self, record):
        """Everything stored about `record`, its own row and what hangs off it."""
        record = Record.objects.with_deleted().get(pk=record.pk)
        return {
            "row": {**model_to_dict(record), "updated_at": record.updated_at},
            "owners": set(record.owners.values_list("user_id", "is_primary")),
            "authors": list(record.authors.values_list("name", flat=True)),
            "versions": list(record.versions.values_list("number", "manuscript", "cause")),
            "reviews": list(record.reviews.values_list("pk", "status", "comment")),
        }

    def continue_as(self, record, as_user, type_name=RecordTypeName.THESIS_RESEARCH):
        return self.post(continue_url(record), as_user, {"record_type": self.type_id(type_name)})


# --- AC: continuing creates a linked draft ------------------------------------------

class ContinueCreatesALinkedDraftTests(ContinuationTestBase):

    def test_copied_keywords_and_owners_are_editable_only_on_the_child(self):
        proposal = self.accepted_proposal(keywords=["clearance", "research"])
        before = self.snapshot(proposal)
        child_id = self.continue_as(proposal, self.owner).data["id"]
        self.assertEqual(self.detail(Record.objects.get(pk=child_id), self.owner)["keywords"], ["clearance", "research"])
        self.client.force_authenticate(self.owner)
        response = self.client.patch(reverse("record-detail", args=[child_id]), {
            "keywords": ["workflow"], "owner_emails": [self.owner.email, self.reader.email],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        child = Record.objects.get(pk=child_id)
        self.assertEqual(child.keywords, ["workflow"])
        self.assertEqual(set(child.owners.values_list("user_id", flat=True)), {self.owner.pk, self.reader.pk})
        self.assertEqual(self.snapshot(proposal), before)

    def test_owner_edits_cannot_remove_the_actor_or_add_the_adviser(self):
        proposal = self.accepted_proposal()
        child_id = self.continue_as(proposal, self.owner).data["id"]
        self.client.force_authenticate(self.owner)
        for emails in ([self.reader.email], [self.owner.email, self.adviser.email], [self.owner.email, "missing@example.com"]):
            response = self.client.patch(reverse("record-detail", args=[child_id]), {"owner_emails": emails}, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_mixed_case_owner_email_is_resolved_and_null_child_type_is_refused(self):
        proposal = self.accepted_proposal()
        self.owner.email = "MixedCase@cit.edu"
        self.owner.save(update_fields=["email"])
        child_id = self.continue_as(proposal, self.owner).data["id"]
        self.client.force_authenticate(self.owner)
        url = reverse("record-detail", args=[child_id])
        response = self.client.patch(url, {"owner_emails": ["mixedcase@cit.edu"]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = self.client.patch(url, {"record_type": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_the_owner_gets_a_draft_of_the_chosen_type_prefilled_from_the_proposal(self):
        classification = Classification.objects.create(name="Continuation field")
        proposal = self.accepted_proposal(classification=classification)
        proposal.authors.create(name="Ana Cruz")
        RecordOwner.objects.create(record=proposal, user=self.reader)

        response = self.continue_as(proposal, self.owner, RecordTypeName.PROJECT)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        child = Record.objects.get(pk=response.data["id"])
        self.assertEqual(child.derived_from, proposal)
        self.assertEqual(child.pipeline_status, PipelineStatus.DRAFT)
        self.assertEqual(child.record_type.name, RecordTypeName.PROJECT)
        self.assertEqual(
            (child.title, child.abstract, child.classification, child.adviser),
            (proposal.title, proposal.abstract, classification, self.adviser),
        )
        self.assertEqual(
            set(child.owners.values_list("user_id", "is_primary")),
            {(self.owner.pk, True), (self.reader.pk, False)},
        )
        self.assertEqual(list(child.authors.values_list("name", flat=True)), ["Ana Cruz"])
        self.assertFalse(child.abstract_file)
        self.assertEqual(child.added_by, self.owner)

    def test_the_proposal_is_left_exactly_as_it_was(self):
        proposal = self.accepted_proposal()
        before = self.snapshot(proposal)

        self.assertEqual(self.continue_as(proposal, self.owner).status_code, status.HTTP_201_CREATED)

        self.assertEqual(self.snapshot(proposal), before)

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}})
    def test_the_child_requires_its_own_manuscript_then_enters_at_its_adviser(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        proposal = self.accepted_proposal()
        child_id = self.continue_as(proposal, self.owner).data["id"]
        submit = reverse("record-submit", args=[child_id])
        response = self.post(submit, self.owner, {"dpa_accepted": True})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            reverse("record-detail", args=[child_id]),
            {"abstract_file": SimpleUploadedFile("thesis.pdf", real_pdf_bytes(), "application/pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = self.post(submit, self.owner, {"dpa_accepted": True})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        detail = self.detail(Record.objects.get(pk=child_id), self.owner)
        self.assertEqual(detail["pipeline_status"], PipelineStatus.IN_REVIEW)
        self.assertEqual([holder["party"] for holder in detail["current_holders"]], ["adviser"])


# --- AC: one continuation per Proposal ------------------------------------------------

class OneContinuationTests(ContinuationTestBase):

    def test_a_second_continuation_is_refused_and_makes_nothing(self):
        proposal = self.accepted_proposal()
        self.assertEqual(self.continue_as(proposal, self.owner).status_code, status.HTTP_201_CREATED)

        response = self.continue_as(proposal, self.owner, RecordTypeName.PROJECT)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.data)
        self.assertEqual(response.data["detail"], "This proposal has already been continued.")
        self.assertEqual(Record.objects.filter(derived_from=proposal).count(), 1)

    def test_the_database_refuses_a_second_live_continuation_written_around_the_service(self):
        proposal = self.accepted_proposal()
        self.continue_as(proposal, self.owner)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Record.objects.create(title="A second child", derived_from=proposal)

    def test_a_discarded_draft_does_not_allow_a_second_continuation(self):
        proposal = self.accepted_proposal()
        first = self.continue_as(proposal, self.owner).data["id"]
        self.client.force_authenticate(self.owner)
        self.assertEqual(
            self.client.delete(reverse("record-detail", args=[first])).status_code,
            status.HTTP_204_NO_CONTENT,
        )

        response = self.continue_as(proposal, self.owner, RecordTypeName.PROJECT)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.data)


# --- AC: only an owner of an approved Proposal ---------------------------------------

class WhoMayContinueTests(ContinuationTestBase):

    def assert_refused(self, response, code, detail=None):
        self.assertEqual(response.status_code, code, response.data)
        if detail:
            self.assertEqual(response.data["detail"], detail)

    def test_a_co_owner_may_continue(self):
        proposal = self.accepted_proposal()
        RecordOwner.objects.create(record=proposal, user=self.reader)

        self.assertEqual(self.continue_as(proposal, self.reader).status_code, status.HTTP_201_CREATED)

    def test_the_adviser_and_an_office_who_can_read_it_are_refused(self):
        proposal = self.accepted_proposal()

        for user in (self.adviser, self.rdco):
            self.assert_refused(
                self.continue_as(proposal, user), status.HTTP_403_FORBIDDEN,
                "Only an owner of this proposal may continue it.",
            )
        self.assertFalse(Record.objects.filter(derived_from=proposal).exists())

    def test_a_stranger_cannot_learn_the_proposal_exists(self):
        proposal = self.accepted_proposal()

        self.assert_refused(self.continue_as(proposal, self.stranger), status.HTTP_404_NOT_FOUND)

    def test_a_proposal_still_in_review_is_refused(self):
        proposal = self.at_adviser(PROPOSAL)

        self.assert_refused(
            self.continue_as(proposal, self.owner), status.HTTP_400_BAD_REQUEST,
            "A proposal can be continued only once its Adviser has accepted it.",
        )

    def test_a_rejected_proposal_is_refused(self):
        proposal = self.at_adviser(PROPOSAL)
        self.decided(proposal, self.adviser, "reject", "The study duplicates earlier work.")

        self.assert_refused(self.continue_as(proposal, self.owner), status.HTTP_400_BAD_REQUEST)

    def test_a_thesis_is_not_a_proposal(self):
        thesis = self.at_adviser()
        self.decided(thesis, self.adviser, "publish")

        self.assert_refused(
            self.continue_as(thesis, self.owner), status.HTTP_400_BAD_REQUEST,
            "Only a proposal can be continued.",
        )

    def test_it_continues_as_a_thesis_or_a_project_never_a_proposal(self):
        proposal = self.accepted_proposal()

        self.assert_refused(
            self.continue_as(proposal, self.owner, PROPOSAL), status.HTTP_400_BAD_REQUEST,
            "A proposal continues as a Thesis / Research or a Project.",
        )
        response = self.post(continue_url(proposal), self.owner, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("record_type", response.data)


# --- AC: both records show the lineage link ------------------------------------------

class LineageTests(ContinuationTestBase):

    def lineage(self, record, as_user):
        return self.detail(record, as_user)["lineage"]

    def test_each_record_points_at_the_other(self):
        proposal = self.accepted_proposal()
        child = Record.objects.get(pk=self.continue_as(proposal, self.owner).data["id"])

        self.assertEqual(self.lineage(child, self.owner), {
            "derived_from": {
                "id": proposal.pk, "title": proposal.title, "record_type_name": PROPOSAL,
            },
            "continued_as": None,
        })
        self.assertEqual(self.lineage(proposal, self.owner), {
            "derived_from": None,
            "continued_as": {
                "id": child.pk, "title": child.title,
                "record_type_name": RecordTypeName.THESIS_RESEARCH,
            },
        })

    def test_a_record_with_no_lineage_says_so(self):
        thesis = self.at_adviser()

        self.assertEqual(
            self.lineage(thesis, self.owner), {"derived_from": None, "continued_as": None},
        )

    def test_a_link_is_never_shown_to_someone_who_cannot_open_its_record(self):
        proposal = self.accepted_proposal()
        child = Record.objects.get(pk=self.continue_as(proposal, self.owner).data["id"])
        child.pipeline_status = PipelineStatus.PUBLISHED
        child.save(update_fields=["pipeline_status"])

        self.assertIsNone(self.lineage(child, self.stranger)["derived_from"])
        self.assertIsNotNone(self.lineage(child, self.owner)["derived_from"])

    def test_a_discarded_continuation_is_not_shown(self):
        proposal = self.accepted_proposal()
        first = self.continue_as(proposal, self.owner).data["id"]
        self.client.force_authenticate(self.owner)
        self.client.delete(reverse("record-detail", args=[first]))

        self.assertIsNone(self.lineage(proposal, self.owner)["continued_as"])
