"""
RDCO publishes an Unlisted paper later (ADR-047 §10, ADR-052 decision 14 as
amended; IR-878), at the REST seam.

An Unlisted paper is a Thesis/Research or Project RDCO accepted and kept out of
Discover (`completed`). Once its embargo is released, any RDCO member may
publish it. Nothing about its review reopens.
"""

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from apps.records.models import Record
from apps.records.testing import released_embargo
from apps.reviews.test_decisions import DecisionTestBase
from apps.reviews.test_my_reviews import MINE
from core.enums import Party, PipelineStatus

NOTE = "The patent was filed on 18 December."


def publish_url(record):
    return reverse("record-publish-unlisted", args=[record.pk])


class PublishUnlistedTestBase(DecisionTestBase):

    def unlisted(self, *, released=True):
        """Kept unlisted by RDCO while embargoed, then released by its Adviser, or not."""
        record = self.at_adviser()
        self.accepted_to(record, Party.RDCO)
        self.opened_seat(record, Party.RDCO, self.rdco)
        self.decided(record, self.rdco, "keep_unlisted")
        if released:
            released_embargo(record.pk)
        record.refresh_from_db()
        return record

    def publish(self, record, as_user, body=None):
        return self.post(publish_url(record), as_user, body if body is not None else {})


class RdcoPublishesAReleasedUnlistedPaper(PublishUnlistedTestBase):

    def test_it_becomes_published_and_the_publish_is_audited(self):
        record = self.unlisted()
        decisions_before = AuditEvent.objects.filter(
            record=record, event_type=AuditEvent.DECISION_RECORDED,
        ).count()

        response = self.publish(record, self.rdco, {"note": NOTE})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)
        published = AuditEvent.objects.get(record=record, event_type=AuditEvent.PUBLISHED)
        self.assertEqual(published.user, self.rdco)
        self.assertEqual(published.metadata["party"], "rdco")
        self.assertEqual(published.metadata["via"], "publish_unlisted")
        self.assertNotIn(NOTE, str(published.metadata))
        # One final Decision per paper (AUDIT_EXPORT.md, total turnaround).
        self.assertEqual(
            AuditEvent.objects.filter(record=record, event_type=AuditEvent.DECISION_RECORDED).count(),
            decisions_before,
        )

    def test_the_owners_and_the_adviser_are_told_with_the_note(self):
        record = self.unlisted()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.publish(record, self.rdco, {"note": NOTE})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        told = Notification.objects.filter(record=record, notif_type__name="Record Published")
        self.assertEqual({n.recipient for n in told}, {self.owner, self.adviser})
        self.assertTrue(all(NOTE in n.message for n in told))

    def test_any_rdco_member_may_publish_it_and_nothing_reopens(self):
        record = self.unlisted()
        reviews = record.reviews.count()
        active = record.assignments.filter(state="active").count()
        response = self.publish(record, self.rdco2)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(record.reviews.count(), reviews)
        self.assertEqual(record.assignments.filter(state="active").count(), active)


class PublishingUnlistedIsRefused(PublishUnlistedTestBase):

    def test_an_embargoed_paper_is_refused_naming_the_embargo(self):
        record = self.unlisted(released=False)
        response = self.publish(record, self.rdco)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Under embargo. Release the embargo, then publish.")
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.COMPLETED)
        self.assertFalse(AuditEvent.objects.filter(record=record, event_type=AuditEvent.PUBLISHED).exists())

    def test_a_dated_embargo_is_named_with_its_date(self):
        record = self.unlisted(released=False)
        Record.objects.filter(pk=record.pk).update(
            embargoed_until="2099-01-15", embargo_date_set_at=timezone.now(),
        )
        response = self.publish(record, self.rdco)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Under embargo until 15 Jan 2099", response.data["detail"])

    def test_nobody_outside_rdco_may_publish_it(self):
        record = self.unlisted()
        for user in (self.owner, self.adviser, self.itso, self.stranger):
            with self.subTest(user=user.email):
                self.assertEqual(self.publish(record, user).status_code, status.HTTP_403_FORBIDDEN)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.COMPLETED)

    def test_only_an_unlisted_paper_is_published_this_way(self):
        in_review = self.at_rdco()
        released_embargo(in_review.pk)
        published = self.at_adviser()
        self.publish_via_rdco(published)
        for record in (in_review, published):
            with self.subTest(status=record.pipeline_status):
                response = self.publish(record, self.rdco)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data["detail"], "Only an Unlisted paper can be published this way.")

    def test_a_note_that_is_not_text_is_refused(self):
        record = self.unlisted()
        response = self.publish(record, self.rdco, {"note": ["Patent filed."]})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("note", response.data)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.COMPLETED)

    def test_a_note_past_its_limit_is_refused(self):
        record = self.unlisted()
        response = self.publish(record, self.rdco, {"note": "x" * 1001})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("note", response.data)


class RecordDetailSaysWhyItIsHeldBack(PublishUnlistedTestBase):

    def test_rdco_reads_the_embargo_until_it_is_released(self):
        record = self.unlisted(released=False)
        self.assertEqual(
            self.detail(record, self.rdco2)["publish_unlisted"],
            {"blocked": "Under embargo. Release the embargo, then publish."},
        )
        released_embargo(record.pk)
        self.assertEqual(self.detail(record, self.rdco2)["publish_unlisted"], {"blocked": None})

    def test_nobody_else_reads_it(self):
        record = self.unlisted()
        for user in (self.owner, self.adviser, self.itso):
            with self.subTest(user=user.email):
                self.assertIsNone(self.detail(record, user)["publish_unlisted"])


class TheHistoryStaysTrue(PublishUnlistedTestBase):
    """
    Option A of the IR-878 design session: once an Unlisted paper is published
    later, RDCO's Decision still reads *kept unlisted*, and the later publish is
    its own entry. Before IR-878 the history read the outcome from the status.
    """

    def unlisted_over_ierc(self):
        """RDCO kept it unlisted while IERC was still reviewing; then it is released."""
        record = self.at_rdco()
        response = self.route(record, self.rdco, [{"party": Party.IERC}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.decided(record, self.rdco, "keep_unlisted")
        released_embargo(record.pk)
        return record

    def published_later(self, record):
        response = self.publish(record, self.rdco2, {"note": NOTE})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_my_reviews_keeps_rdcos_decision_accepted(self):
        record = self.unlisted()
        self.published_later(record)
        self.client.force_authenticate(self.rdco)
        rows = self.client.get(MINE, {"tab": "done"}).data["rows"]
        self.assertEqual([(r["record"], r["outcome"]) for r in rows], [(record.pk, "accepted")])
        self.assertEqual(self.client.get(MINE, {"tab": "done", "outcome": "published"}).data["rows"], [])

    def test_the_tracker_names_the_decision_as_kept_unlisted(self):
        record = self.unlisted_over_ierc()
        self.published_later(record)
        ierc = self.rows(self.tracker(record, self.owner))[Party.IERC]
        self.assertEqual(ierc["withdrawn_by_decision"], "RDCO accepted the record and kept it unlisted")

    def test_the_tracker_shows_the_later_publish_with_its_note(self):
        record = self.unlisted()
        self.assertIsNone(self.tracker(record, self.owner)["published_later"])
        self.published_later(record)
        entry = self.tracker(record, self.owner)["published_later"]
        self.assertEqual(entry["label"], "RDCO Final")
        self.assertEqual(entry["published_by_name"], self.rdco2.get_full_name())
        self.assertEqual(entry["note"], NOTE)
        self.assertTrue(entry["published_at"])

    def test_a_reader_learns_when_it_was_published_but_not_who_or_why(self):
        record = self.unlisted()
        self.published_later(record)
        entry = self.tracker(record, self.reader)["published_later"]
        self.assertTrue(entry["published_at"])
        self.assertIsNone(entry["published_by_name"])
        self.assertIsNone(entry["note"])
