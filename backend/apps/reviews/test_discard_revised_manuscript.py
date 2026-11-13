"""
The owner throws away a revised manuscript they uploaded and have not yet
submitted (IR-1047).

ADR-032 §5 and its IR-273 Amendment: an owner's upload is stored but is not
the manuscript any reviewer reads, and not the one Ask IRIS answers from,
until its version is submitted. Until then the only ways back to the submitted
file were to upload another or for the last request to be withdrawn. This is
the owner's own way back, at the REST seam, one class per criterion.
"""

from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from core.enums import Party, ResubmissionRequestState

from .test_new_version import V1, V2, NewVersionTestBase


def discard_url(record):
    return reverse("record-discard-revised-manuscript", args=[record.pk])


class DiscardBase(NewVersionTestBase):

    def discard(self, record, as_user=None):
        return self.post(discard_url(record), as_user or self.owner, {})

    def discarded(self, record, as_user=None):
        response = self.discard(record, as_user)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        return response

    def revised(self):
        """A record with ITSO cleared, IERC asking, and the owner's upload waiting."""
        record = self.itso_cleared_and_ierc_asked()
        self.assertEqual(self.upload_manuscript(record).status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        return record

    def offered(self, record, as_user):
        return set(self.detail(record, as_user)["capabilities"])


class DiscardPutsTheSubmittedManuscriptBack(DiscardBase):

    def test_the_record_reads_the_submitted_version_again(self):
        record = self.revised()
        [v1] = self.versions(record)
        self.assertNotEqual(record.abstract_file.name, v1.manuscript.name)
        self.assertEqual(self.read_manuscript(record, self.owner), V2)

        response = self.discarded(record)

        self.assertEqual(record.abstract_file.name, v1.manuscript.name)
        self.assertEqual(self.read_manuscript(record, self.owner), V1)
        self.assertFalse(response.data["manuscript_unsubmitted"])
        self.assertFalse(self.detail(record, self.owner)["manuscript_unsubmitted"])

    def test_answers_with_the_record_detail(self):
        record = self.revised()

        response = self.discarded(record)

        self.assertEqual(response.data["id"], record.pk)
        self.assertIn("capabilities", response.data)

    def test_the_request_stays_open_and_nothing_is_submitted(self):
        record = self.revised()
        versions_before = len(self.versions(record))

        self.discarded(record)

        self.assertEqual(self.open_requests(record).count(), 1)
        self.assertEqual(len(self.versions(record)), versions_before)
        # Nothing has changed since the request, so submitting is refused.
        refused = self.submit_version(record)
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Nothing has changed", refused.data["detail"])

    def test_the_owner_may_upload_again_and_submit_that(self):
        record = self.revised()
        self.discarded(record)

        self.assertEqual(self.upload_manuscript(record, body=V2).status_code, status.HTTP_200_OK)
        self.submitted(record)

        _, v2 = self.versions(record)
        self.assertEqual(v2.manuscript.name, record.abstract_file.name)
        self.assertEqual(self.read_manuscript(record, self.ierc), V2)

    def test_reviewers_read_the_submitted_version_throughout_and_nobody_is_told(self):
        record = self.revised()
        notified = Notification.objects.count()
        self.assertEqual(self.read_manuscript(record, self.ierc), V1)

        self.discarded(record)

        self.assertEqual(self.read_manuscript(record, self.ierc), V1)
        self.assertEqual(Notification.objects.count(), notified)


class DiscardIsOfferedOnlyWhenThereIsSomethingToDiscard(DiscardBase):

    def test_offered_to_the_owner_once_a_revision_is_uploaded_and_gone_after_the_discard(self):
        record = self.itso_cleared_and_ierc_asked()
        self.assertNotIn("discard_revised_manuscript", self.offered(record, self.owner))

        self.upload_manuscript(record)
        self.assertIn("discard_revised_manuscript", self.offered(record, self.owner))

        self.discarded(record)
        self.assertNotIn("discard_revised_manuscript", self.offered(record, self.owner))

    def test_never_offered_to_a_reviewer(self):
        record = self.revised()

        for reviewer in (self.ierc, self.itso):
            self.assertNotIn("discard_revised_manuscript", self.offered(record, reviewer))


class DiscardIsTheOwnersAlone(DiscardBase):

    def test_a_reviewer_is_refused_and_the_upload_stays(self):
        record = self.revised()
        waiting = record.abstract_file.name

        response = self.discard(record, as_user=self.ierc)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        record.refresh_from_db()
        self.assertEqual(record.abstract_file.name, waiting)
        self.assertFalse(AuditEvent.objects.filter(
            record=record, event_type=AuditEvent.REVISION_DRAFT_DISCARDED,
        ).exists())


class DiscardNeedsAnUnsentUploadWhileARevisionIsAsked(DiscardBase):

    def test_nothing_unsent_is_a_400_that_says_so(self):
        record = self.itso_cleared_and_ierc_asked()

        response = self.discard(record)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("no unsent revised manuscript", response.data["detail"])
        self.assertFalse(AuditEvent.objects.filter(
            record=record, event_type=AuditEvent.REVISION_DRAFT_DISCARDED,
        ).exists())

    def test_a_second_discard_is_refused(self):
        record = self.revised()
        self.discarded(record)

        response = self.discard(record)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_revision_asked_is_a_400(self):
        record = self.thesis(Party.IERC)

        response = self.discard(record)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No reviewer has asked for a revision", response.data["detail"])

    def test_a_draft_is_a_400_and_its_manuscript_is_untouched(self):
        from .test_new_version import _pdf

        record = self.make_record(abstract_file=_pdf(V1))
        stored = record.abstract_file.name

        response = self.discard(record)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        record.refresh_from_db()
        self.assertEqual(record.abstract_file.name, stored)

    def test_a_withdrawn_last_request_leaves_nothing_to_discard(self):
        record = self.revised()
        request = self.open_requests(record).get()
        self.assertEqual(self.withdraw(record, self.ierc, request.pk).status_code, status.HTTP_200_OK)

        response = self.discard(record)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        request.refresh_from_db()
        self.assertEqual(request.state, ResubmissionRequestState.WITHDRAWN)


class DiscardIsRecorded(DiscardBase):

    def test_one_audit_event_names_who_and_which_version(self):
        record = self.revised()
        dropped = record.manuscript_revision

        self.discarded(record)

        [event] = AuditEvent.objects.filter(record=record, event_type=AuditEvent.REVISION_DRAFT_DISCARDED)
        self.assertEqual(event.user, self.owner)
        self.assertEqual(event.metadata["version"], 1)
        self.assertEqual(event.metadata["discarded_revision"], str(dropped))
        # By revision, never by file name or text.
        self.assertNotIn("revised.pdf", str(event.metadata))
