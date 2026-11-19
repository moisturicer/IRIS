"""
An unsubmitted draft is its creator's alone (IR-1227, ADR-009 decision 6).

At the HTTP routes: everyone but the account that created it -- a co-owner
it names, office staff, the Adviser it names, the System Admin and any other
user -- gets the 404 a missing record gets, on the record, its documents and
its review, and it is in nobody else's lists. Once submitted, the record
reads as before, co-owners included.
"""

from django.urls import reverse
from rest_framework import status

from apps.accounts.tests import make_user
from apps.ai.models import EmbeddingJob
from apps.notifications.models import Notification
from apps.records.models import RecordOwner
from apps.reviews.test_routing import RoutingTestBase
from core.enums import RoleName

MISSING = 999_999


def record_routes(pk):
    """Label -> url for the routes that name the record in their path."""
    return {
        "detail": reverse("record-detail", args=[pk]),
        "tracker": reverse("record-tracker", args=[pk]),
        "manuscript": reverse("record-manuscript", args=[pk]),
        "similar": reverse("record-similar", args=[pk]),
        "document requests": reverse("record-document-requests", args=[pk]),
        "review comments": reverse("record-review-comments", args=[pk]),
    }


def document_routes(pk):
    """Label -> url for the document routes that take the record as a parameter."""
    return {
        "slots": reverse("record-slot-list", args=[pk]),
        "uploads": f"{reverse('record-uploads')}?record={pk}",
        "files": f"{reverse('record-files')}?record={pk}",
        "download all": f"{reverse('record-files-download-all')}?record={pk}",
    }


class DraftVisibilityTestBase(RoutingTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sysadmin = make_user("draft-sysadmin@cit.edu", RoleName.SYSTEM_ADMIN)
        cls.classmate = make_user("draft-classmate@cit.edu", RoleName.STUDENT)
        cls.co_owner = make_user("draft-co-owner@cit.edu", RoleName.STUDENT)

    def make_record(self, *args, **kwargs):
        """A draft `self.owner` created, naming `self.co_owner` as a co-owner."""
        record = super().make_record(*args, **kwargs)
        RecordOwner.objects.create(record=record, user=self.co_owner, is_primary=False)
        return record

    def others(self):
        """Everyone who did not create the draft."""
        return {
            "co-owner": self.co_owner, "named adviser": self.adviser, "itso": self.itso,
            "ierc": self.ierc, "ktto": self.ktto, "rdco": self.rdco, "system admin": self.sysadmin,
            "another student": self.classmate,
        }

    def get(self, user, url):
        self.client.force_authenticate(user)
        return self.client.get(url)


class NobodyButItsOwnerOpensADraftTests(DraftVisibilityTestBase):

    def test_everyone_else_gets_not_found_on_the_record_and_its_review(self):
        draft = self.make_record()
        missing = record_routes(MISSING)
        for who, user in self.others().items():
            for label, url in record_routes(draft.pk).items():
                with self.subTest(who=who, route=label):
                    response = self.get(user, url)
                    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                    self.assertEqual(response.data, self.get(user, missing[label]).data,
                                     "a hidden draft must answer exactly as a missing record")

    def test_an_office_cannot_queue_a_draft_for_indexing(self):
        draft = self.make_record()
        self.client.force_authenticate(self.rdco)
        response = self.client.post(reverse("ai-embed-record", args=[draft.pk]), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data,
                         self.client.post(reverse("ai-embed-record", args=[MISSING]), {}, format="json").data)
        self.assertFalse(EmbeddingJob.objects.filter(record_id=draft.pk).exists())

    def test_everyone_else_gets_not_found_on_its_documents_as_for_a_missing_record(self):
        draft = self.make_record()
        missing = document_routes(MISSING)
        for who, user in self.others().items():
            for label, url in document_routes(draft.pk).items():
                with self.subTest(who=who, route=label):
                    response = self.get(user, url)
                    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                    self.assertEqual(response.data, self.get(user, missing[label]).data,
                                     "a hidden draft must answer exactly as a missing record")

    def test_the_owner_still_reads_it_and_its_documents(self):
        draft = self.make_record()
        routes = {**record_routes(draft.pk), **document_routes(draft.pk)}
        for label in ("detail", "tracker", "slots", "uploads", "files"):
            with self.subTest(route=label):
                self.assertEqual(self.get(self.owner, routes[label]).status_code, status.HTTP_200_OK)

    def test_the_owner_is_offered_to_continue_and_delete_it(self):
        draft = self.make_record()
        detail = self.get(self.owner, reverse("record-detail", args=[draft.pk])).data
        self.assertIn("continue_draft", detail["capabilities"])
        self.assertIn("delete_record", detail["capabilities"])


class ADraftIsInNobodyElsesListsTests(DraftVisibilityTestBase):

    def mine(self, user):
        return {row["id"] for row in self.get(user, reverse("record-mine")).data}

    def test_my_submissions_lists_it_for_its_creator_alone(self):
        draft = self.make_record()
        self.assertIn(draft.pk, self.mine(self.owner))
        self.assertNotIn(draft.pk, self.mine(self.co_owner))

    def test_the_dashboard_counts_it_for_its_creator_alone(self):
        self.make_record()
        stats = reverse("dashboard-stats")
        self.assertEqual(self.get(self.owner, stats).data["total_mine"], 1)
        self.assertEqual(self.get(self.co_owner, stats).data["total_mine"], 0)

    def test_deleting_it_tells_nobody(self):
        draft = self.make_record()
        self.client.force_authenticate(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(reverse("record-detail", args=[draft.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(recipient=self.co_owner).exists())


class ASubmittedRecordReadsAsBeforeTests(DraftVisibilityTestBase):

    def test_its_adviser_the_offices_and_its_co_owners_read_it_once_submitted(self):
        submitted = self.new_model()  # names the co-owner, as every record here does
        for who, user in (("named adviser", self.adviser), ("rdco", self.rdco), ("itso", self.itso),
                          ("co-owner", self.co_owner)):
            with self.subTest(who=who):
                self.assertEqual(self.get(user, reverse("record-detail", args=[submitted.pk])).status_code,
                                 status.HTTP_200_OK)
                self.assertEqual(self.get(user, document_routes(submitted.pk)["files"]).status_code,
                                 status.HTTP_200_OK)

    def test_another_student_still_cannot_reach_a_submitted_record_s_documents(self):
        submitted = self.new_model()
        response = self.get(self.classmate, document_routes(submitted.pk)["files"])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, "unchanged: 403, not 404")
