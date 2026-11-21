"""Publishing, not releasing, hands a paper to the AI (IR-1252, ADR-052 as amended 2026-11-21).

The disclosure gate refuses an unpublished paper, so the act that opens it is the
one that publishes: RDCO's publish Decision, RDCO publishing a paper kept
unlisted, or a declined delete request restoring a published paper. Each queues
the paper's read, indexing and AI Overview once it commits. A release still asks
the gate, which now says no until the paper is published.
"""

from unittest.mock import patch

from django.urls import reverse
from rest_framework import status

from apps.records.models import Record
from apps.records.testing import released_embargo
from core.enums import Party

from .test_decisions import DecisionTestBase


class PublishingSendsThePaperTests(DecisionTestBase):

    def consented(self, record):
        Record.objects.filter(pk=record.pk).update(ai_consent=True)
        record.refresh_from_db()
        return record

    def sent(self, act):
        """The records queued for indexing by `act`, once its transaction commits."""
        with patch("apps.ai.tasks.index_record.delay") as queued, \
                patch("apps.ai.overview.service.overview_for"), \
                self.captureOnCommitCallbacks(execute=True):
            act()
        return [call.args[0] for call in queued.call_args_list]

    def test_rdco_publishing_a_paper_queues_it(self):
        record = self.consented(self.at_rdco())

        self.assertEqual(self.sent(lambda: self.decided(record, self.rdco, "publish")), [record.pk])

    def test_keeping_it_unlisted_queues_nothing(self):
        record = self.consented(self.at_rdco())
        released_embargo(record.pk)

        self.assertEqual(self.sent(lambda: self.decided(record, self.rdco, "keep_unlisted")), [])

    def test_releasing_a_paper_still_in_review_queues_nothing(self):
        record = self.consented(self.at_rdco())

        def release():
            response = self.post(reverse("record-embargo-release", args=[record.pk]), self.adviser, {})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertEqual(self.sent(release), [])

    def test_publishing_a_paper_kept_unlisted_queues_it(self):
        record = self.consented(self.at_adviser())
        self.accepted_to(record, Party.RDCO)
        self.opened_seat(record, Party.RDCO, self.rdco)
        self.decided(record, self.rdco, "keep_unlisted")
        released_embargo(record.pk)

        def publish():
            response = self.post(reverse("record-publish-unlisted", args=[record.pk]), self.rdco, {})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertEqual(self.sent(publish), [record.pk])

    def test_declining_a_delete_request_restores_a_published_paper_and_queues_it(self):
        from apps.records.models import DeleteRequest

        record = self.consented(self.at_rdco())
        self.decided(record, self.rdco, "publish")
        Record.objects.filter(pk=record.pk).update(pipeline_status="pending_delete")
        request = DeleteRequest.objects.create(
            record=record, requested_by=self.owner, status="pending",
            previous_pipeline_status="published",
        )

        def decline():
            response = self.post(reverse("delete-request-decline", args=[request.pk]), self.rdco,
                                 {"note": "Keep it, please."})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertEqual(self.sent(decline), [record.pk])
