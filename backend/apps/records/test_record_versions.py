"""Record versions on the adviser-first workflow (IR-416 and IR-260)."""

import re
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.records.models import RecordVersion
from apps.records.versions import write_version
from apps.reviews.models import Review
from apps.reviews.test_office_review import OfficeReviewTestBase, detail_url
from core.enums import Party, PipelineStatus, RecordTypeName, VersionCause

def _pdf(name="thesis.pdf", body=b"%PDF-1.7 first"):
    return SimpleUploadedFile(name, body, content_type="application/pdf")


def _versions(record):
    """(number, cause, manuscript), an empty file field read as None."""
    return [
        (number, cause, manuscript or None)
        for number, cause, manuscript in RecordVersion.objects.filter(record=record)
        .order_by("number").values_list("number", "cause", "manuscript")
    ]


def version_manuscript_url(record, number):
    return reverse("record-version-manuscript", args=[record.pk, number])


class NewModelVersionTests(OfficeReviewTestBase):

    def test_entering_at_the_adviser_writes_v1(self):
        record = self.new_model(abstract_file=_pdf())

        self.assertEqual(
            _versions(record), [(1, VersionCause.SUBMISSION, record.abstract_file.name)],
        )

    def test_accept_and_route_and_an_office_clear_record_the_version(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)

        self.cleared(record, self.itso)

        self.assertEqual(
            set(Review.objects.filter(record=record).values_list("stage", "version__number")),
            {(Party.ADVISER, 1), (Party.ITSO, 1)},
        )


class SourceSafetyTests(SimpleTestCase):
    def test_no_source_deletes_a_manuscript_file(self):
        pattern = re.compile(r"(abstract_file|manuscript)\.delete\(|storage\.delete\(")
        apps_dir = Path(settings.BASE_DIR) / "apps"
        offenders = [
            str(path.relative_to(apps_dir))
            for path in apps_dir.rglob("*.py")
            if "test" not in path.name and "tests" not in path.parts
            and pattern.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])

class VersionReadTests(OfficeReviewTestBase):

    def setUp(self):
        super().setUp()
        self.record = self.routed(Party.ITSO)
        self.record.refresh_from_db()
        self.v1_name = self.record.abstract_file.name
        # A second version, as a resubmission writes it, naming a new file.
        self.record.abstract_file.save("revised.pdf", _pdf("revised.pdf", b"%PDF-1.7 v2"))
        write_version(self.record, self.owner, VersionCause.REVISION)

    def routed(self, *parties, type_name=RecordTypeName.THESIS_RESEARCH):
        record = self.new_model(type_name, abstract_file=_pdf(body=b"%PDF-1.7 v1"))
        self.accepted_to(record, *parties)
        return record

    def get(self, url, as_user):
        self.client.force_authenticate(as_user)
        return self.client.get(url)

    def publish(self):
        self.record.pipeline_status = PipelineStatus.PUBLISHED
        self.record.save(update_fields=["pipeline_status"])

    def test_an_owner_sees_every_version_oldest_first(self):
        versions = self.get(detail_url(self.record), self.owner).data["versions"]

        self.assertEqual([v["number"] for v in versions], [1, 2])
        self.assertEqual([v["cause"] for v in versions], ["submission", "revision"])
        self.assertEqual(
            versions[0]["manuscript_url"],
            f"/api/v1/records/{self.record.pk}/versions/1/manuscript/",
        )

    def test_a_participant_who_is_not_an_owner_reads_an_earlier_version(self):
        self.seat(self.record, Party.ITSO, self.itso)

        detail = self.get(detail_url(self.record), self.itso).data
        response = self.get(version_manuscript_url(self.record, 1), self.itso)

        self.assertEqual(len(detail["versions"]), 2)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.7 v1")
        self.assertIn("(v1)", response["Content-Disposition"])

    def test_a_reader_of_the_published_paper_sees_no_versions_and_gets_404(self):
        self.publish()

        detail = self.get(detail_url(self.record), self.stranger)
        response = self.get(version_manuscript_url(self.record, 1), self.stranger)

        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertIsNone(detail.data["versions"])
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_tracker_carries_versions_and_each_review_s_version(self):
        payload = self.tracker(self.record)

        self.assertEqual([v["number"] for v in payload["versions"]], [1, 2])
        self.assertEqual([r["version"] for r in payload["reviews"]], [1])

        self.publish()
        self.assertIsNone(self.tracker(self.record, self.stranger)["versions"])

    def test_a_version_that_does_not_exist_or_names_no_file_is_404(self):
        bare = self.new_model()

        missing = self.get(version_manuscript_url(self.record, 9), self.owner)
        no_file = self.get(version_manuscript_url(bare, 1), self.owner)

        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(no_file.status_code, status.HTTP_404_NOT_FOUND)

    def test_reading_a_version_is_audited_with_its_number(self):
        self.get(version_manuscript_url(self.record, 1), self.owner)

        event = AuditEvent.objects.filter(record=self.record, event_type="DOWNLOAD").latest("id")
        self.assertEqual(event.metadata["version"], 1)
        self.assertEqual(event.user, self.owner)
