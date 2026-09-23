"""GET /records/<id>/manuscript/ (IR-334, ADR-031).

Replaces a link that has been dead since IR-152: `RecordSerializer` emitted
`abstract_file` as `/media/...`, and nothing has served that path since IR-152
removed both the nginx `/media/` block and Django's `DEBUG` `static()` route.
Every "View Paper" button and every citation that followed a page link hit a
404. This endpoint is what a citation opens instead.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user
from core.enums import PipelineStatus


def _pdf():
    return SimpleUploadedFile(
        "thesis.pdf", b"%PDF-1.7 fake bytes", content_type="application/pdf"
    )


class ManuscriptEndpointTests(APITestCase):
    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("owner@cit.edu", "Student")
        self.stranger = make_user("stranger@cit.edu", "Student")
        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=self.record_type,
            added_by=self.owner, pipeline_status=PipelineStatus.PUBLISHED,
            abstract_file=_pdf(),
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

    def _get(self):
        return self.client.get(reverse("record-manuscript", args=[self.record.id]))

    def test_a_reader_who_may_see_the_record_gets_the_pdf(self):
        self.client.force_authenticate(self.owner)

        response = self._get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response["Content-Disposition"])

    def test_it_is_readable_by_range_for_a_client_that_pages_through_it(self):
        """`Accept-Ranges` is what lets a PDF renderer fetch pages instead of
        the whole file up front (IR-335)."""
        self.client.force_authenticate(self.owner)

        response = self._get()

        self.assertEqual(response["Accept-Ranges"], "bytes")

    def test_a_reader_who_may_not_see_the_record_gets_404_not_403(self):
        """The same rule every other record endpoint follows (IR-153): a
        refusal must read identically to a missing record, or the response
        itself confirms the record exists."""
        self.record.pipeline_status = PipelineStatus.DRAFT
        self.record.save(update_fields=["pipeline_status"])
        self.client.force_authenticate(self.stranger)

        response = self._get()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_anonymous_request_is_refused(self):
        response = self._get()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_record_with_no_file_is_404(self):
        bare = Record.objects.create(
            title="C" * 10, abstract="D" * 40, record_type=self.record_type,
            added_by=self.owner, pipeline_status=PipelineStatus.PUBLISHED,
        )
        RecordOwner.objects.create(record=bare, user=self.owner, is_primary=True)
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse("record-manuscript", args=[bare.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_access_audit_event_is_recorded(self):
        from apps.audit.models import AuditEvent

        self.client.force_authenticate(self.owner)

        self._get()

        event = AuditEvent.objects.filter(record=self.record, event_type="DOWNLOAD").latest("id")
        self.assertEqual(event.metadata.get("source"), "manuscript")


class AbstractFileUrlPointsAtTheServedEndpointTests(APITestCase):
    """The detail serializer used to echo the stored `/media/` path straight
    back. This is what replaced it (IR-334)."""

    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("owner@cit.edu", "Student")
        RecordOwner.objects.create(
            record=Record.objects.create(
                title="A" * 10, abstract="B" * 40, record_type=self.record_type,
                added_by=self.owner, pipeline_status=PipelineStatus.PUBLISHED,
                abstract_file=_pdf(),
            ),
            user=self.owner, is_primary=True,
        )
        self.record = Record.objects.get(added_by=self.owner)
        self.client.force_authenticate(self.owner)

    def test_abstract_file_is_the_manuscript_endpoint_not_a_media_path(self):
        response = self.client.get(reverse("record-detail", args=[self.record.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["abstract_file"],
            f"/api/v1/records/{self.record.id}/manuscript/",
        )

    def test_abstract_file_is_null_when_there_is_no_file_anywhere(self):
        bare = Record.objects.create(
            title="C" * 10, abstract="D" * 40, record_type=self.record_type,
            added_by=self.owner, pipeline_status=PipelineStatus.PUBLISHED,
        )
        RecordOwner.objects.create(record=bare, user=self.owner, is_primary=True)

        response = self.client.get(reverse("record-detail", args=[bare.id]))

        self.assertIsNone(response.data["abstract_file"])
