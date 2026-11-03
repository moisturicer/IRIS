"""GET /records/<id>/figures/<figure_id>/ (IR-845, ADR-056 §9).

A Figure is part of the paper, so it is read exactly as the paper is: through
`visible_to`, with a refusal that reads like a missing record. It never takes
a file path. This is the endpoint IR-292 planned; ADR-025's crop-on-request
is not built.
"""

import base64
import uuid

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.documents.models import DocumentKind, ExtractionFigure, PdfExtraction
from apps.records.models import Record, RecordOwner, RecordType, RecordVersion
from apps.records.tests import make_user
from core.enums import PipelineStatus, RoleName

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _pdf(name="thesis.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.7 fake bytes", content_type="application/pdf")


class FigureEndpointTests(APITestCase):
    def setUp(self):
        record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.owner = make_user("fig-owner@cit.edu", RoleName.STUDENT)
        self.adviser = make_user("fig-adviser@cit.edu", RoleName.ADVISER)
        self.staff = make_user("fig-rdco@cit.edu", RoleName.RDCO)
        self.stranger = make_user("fig-stranger@cit.edu", RoleName.STUDENT)
        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=record_type, added_by=self.owner,
            pipeline_status=PipelineStatus.IN_REVIEW, adviser=self.adviser,
            abstract_file=_pdf(), manuscript_revision=uuid.uuid4(),
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        self.extraction = PdfExtraction.objects.create(
            record=self.record, kind=DocumentKind.MANUSCRIPT, status="done",
            source_revision=self.record.manuscript_revision, source_file=self.record.abstract_file.name,
        )
        self.figure = self._figure(self.extraction, self.record.manuscript_revision)

    def _figure(self, extraction, revision):
        figure = ExtractionFigure(extraction=extraction, source_revision=revision, page=2,
                                  bbox={"x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0}, media_type="image/png")
        figure.image.save("figure.png", ContentFile(PNG), save=False)
        figure.save()
        return figure

    def _get(self, user, record_id=None, figure_id=None):
        self.client.force_authenticate(user)
        return self.client.get(reverse("record-figure", args=[
            record_id or self.record.id, figure_id or self.figure.id,
        ]))

    def test_the_owner_adviser_and_office_staff_get_the_image(self):
        for reader in (self.owner, self.adviser, self.staff):
            with self.subTest(reader=reader.email):
                response = self._get(reader)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(b"".join(response.streaming_content), PNG)
                self.assertEqual(response["Content-Type"], "image/png")

    def test_the_image_is_never_cached_or_sniffed_as_something_else(self):
        response = self._get(self.owner)

        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("inline", response["Content-Disposition"])

    def test_an_unrelated_reader_gets_the_404_of_a_missing_record(self):
        refused = self._get(self.stranger)
        missing = self._get(self.stranger, record_id=self.record.id + 1000)

        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(refused.json(), missing.json())

    def test_a_figure_is_only_reachable_through_its_own_record(self):
        other = Record.objects.create(
            title="C" * 10, abstract="D" * 40, record_type=self.record.record_type, added_by=self.stranger,
            pipeline_status=PipelineStatus.DRAFT, abstract_file=_pdf(), manuscript_revision=uuid.uuid4(),
        )
        RecordOwner.objects.create(record=other, user=self.stranger, is_primary=True)
        hidden = self._figure(
            PdfExtraction.objects.create(record=other, kind=DocumentKind.MANUSCRIPT,
                                         source_revision=other.manuscript_revision),
            other.manuscript_revision,
        )

        response = self._get(self.owner, figure_id=hidden.id)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_figure_from_a_replaced_manuscript_is_not_served(self):
        stale = self._figure(self.extraction, uuid.uuid4())

        response = self._get(self.owner, figure_id=stale.id)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_while_a_revision_awaits_submission_others_see_the_submitted_figures(self):
        """Everyone but the owner is served the submitted Manuscript until the
        revision is submitted (IR-273), so they see its Figures too."""
        submitted = self.record.manuscript_revision
        RecordVersion.objects.create(record=self.record, number=1, manuscript=self.record.abstract_file.name,
                                     manuscript_revision=submitted)
        self.record.abstract_file = _pdf("revised.pdf")
        self.record.manuscript_revision = uuid.uuid4()
        self.record.save()

        self.assertEqual(self._get(self.adviser).status_code, status.HTTP_200_OK)
        self.assertEqual(self._get(self.owner).status_code, status.HTTP_404_NOT_FOUND)
