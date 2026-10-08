"""
Record versions (IR-416; ADR-032 §5 and its 2026-10-08 Amendment).

At the REST seam IR-255 confirmed, one class per acceptance criterion:

- submitting writes v1 naming the current manuscript, on both submission
  paths; a legacy resubmission writes the next version;
- `(record, number)` is unique;
- a review records the version it was made against, on every path that
  writes one;
- the manuscript is locked once a record is submitted, for staff too;
- no code deletes a manuscript file a version names;
- earlier versions are read by participants only (IR-479's rule).

The backfill has its own file, `test_version_backfill_migration.py`.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.records.models import RecordVersion
from apps.records.versions import write_version
from apps.reviews.models import Review
from apps.reviews.test_office_review import OfficeReviewTestBase, detail_url
from apps.reviews.test_workflow_characterisation import WorkflowCharacterisationBase
from core.enums import (
    Party,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    ReviewStage,
    VersionCause,
)


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


class LegacyVersionTestBase(WorkflowCharacterisationBase):
    """The legacy pipeline, through HTTP: submit, decline, replace, resubmit."""

    def thesis(self, **extra):
        return self.make_record(
            RecordTypeName.THESIS_RESEARCH, abstract_file=_pdf(),
            requested_ierc=True, requested_ktto=True, **extra,
        )

    def submitted(self, record):
        response = self.submit_record(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        return record

    def replace_manuscript(self, record, as_user=None, body=b"%PDF-1.7 revised"):
        from unittest.mock import patch

        self.client.force_authenticate(as_user or self.owner)
        with patch("apps.documents.tasks.extract_manuscript_text.delay"):
            return self.client.patch(
                reverse("record-detail", args=[record.pk]),
                {"abstract_file": _pdf("revised.pdf", body)},
                format="multipart",
            )

    def declined_by_ktto(self):
        """Submitted, accepted at intake, IERC cleared, KTTO asked for changes."""
        record = self.submitted(self.thesis())
        self.review(record, self.rdco, ReviewDecision.APPROVED)
        self.review(record, self.ierc, ReviewDecision.APPROVED)
        self.review(record, self.ktto, ReviewDecision.DECLINED, comment="Revise.")
        self.assertEqual(self.status_of(record), PipelineStatus.DECLINED)
        return record


# --- AC: submitting writes v1 -------------------------------------------------------

class LegacySubmissionTests(LegacyVersionTestBase):

    def test_submitting_writes_v1_naming_the_current_manuscript(self):
        record = self.submitted(self.thesis())

        version = RecordVersion.objects.get(record=record)
        self.assertEqual(version.number, 1)
        self.assertEqual(version.cause, VersionCause.SUBMISSION)
        self.assertEqual(version.manuscript.name, record.abstract_file.name)
        self.assertEqual(version.created_by, self.owner)

    def test_a_refused_submission_writes_no_version(self):
        record = self.thesis()
        self.client.force_authenticate(self.owner)

        response = self.client.post(reverse("record-submit", args=[record.pk]), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(_versions(record), [])

    def test_a_record_submitted_with_no_manuscript_gets_a_version_naming_none(self):
        record = self.submitted(self.make_record(RecordTypeName.THESIS_RESEARCH))

        self.assertEqual(_versions(record), [(1, VersionCause.SUBMISSION, None)])


class LegacyResubmissionTests(LegacyVersionTestBase):

    def test_a_resubmission_writes_the_next_version_naming_the_new_manuscript(self):
        record = self.declined_by_ktto()
        first = record.abstract_file.name
        response = self.replace_manuscript(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.add_upload_after_decline(record)

        response = self.resubmit(record)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(_versions(record), [
            (1, VersionCause.SUBMISSION, first),
            (2, VersionCause.REVISION, record.abstract_file.name),
        ])
        self.assertNotEqual(first, record.abstract_file.name)

    def test_a_resubmission_with_the_same_manuscript_names_the_same_file(self):
        """A revision that left the manuscript alone still makes a version."""
        record = self.declined_by_ktto()
        self.add_upload_after_decline(record)

        self.resubmit(record)

        (_, _, v1), (_, cause, v2) = _versions(record)
        self.assertEqual(cause, VersionCause.REVISION)
        self.assertEqual(v1, v2)


# --- AC: (record, number) is unique ------------------------------------------------

class UniquenessTests(LegacyVersionTestBase):

    def test_two_versions_cannot_share_a_number(self):
        record = self.submitted(self.thesis())

        with self.assertRaises(IntegrityError), transaction.atomic():
            RecordVersion.objects.create(
                record=record, number=1, cause=VersionCause.REVISION,
            )

    def test_the_writer_numbers_on_from_the_highest_existing_version(self):
        """A backfilled history may start at v3; the next one is v4."""
        record = self.thesis(pipeline_status=PipelineStatus.DECLINED)
        RecordVersion.objects.create(record=record, number=3, cause=VersionCause.REVISION)

        version = write_version(record, self.owner, VersionCause.REVISION)

        self.assertEqual(version.number, 4)


# --- AC: a review records its version ----------------------------------------------

class LegacyReviewVersionTests(LegacyVersionTestBase):

    def test_each_legacy_review_records_the_version_it_was_made_against(self):
        record = self.declined_by_ktto()
        self.add_upload_after_decline(record)
        self.resubmit(record)
        self.review(record, self.ktto, ReviewDecision.APPROVED)

        reviews = list(
            Review.objects.filter(record=record).order_by("created_at", "pk")
            .values_list("stage", "status", "version__number")
        )
        self.assertEqual(reviews, [
            (ReviewStage.RDCO_INTAKE, ReviewDecision.APPROVED, 1),
            (ReviewStage.IERC, ReviewDecision.APPROVED, 1),
            (ReviewStage.KTTO, ReviewDecision.DECLINED, 1),
            (ReviewStage.KTTO, ReviewDecision.APPROVED, 2),
        ])


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


# --- AC: the manuscript is locked once submitted -----------------------------------

class ManuscriptLockTests(LegacyVersionTestBase):

    def test_a_submitted_record_refuses_a_new_manuscript_naming_its_status(self):
        for pipeline_status in (
            PipelineStatus.RDCO_INTAKE,
            PipelineStatus.IN_REVIEW,
            PipelineStatus.PUBLISHED,
            PipelineStatus.COMPLETED,
        ):
            with self.subTest(pipeline_status=pipeline_status):
                record = self.thesis(pipeline_status=pipeline_status)
                before = record.abstract_file.name

                response = self.replace_manuscript(record)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(str(pipeline_status), str(response.data["abstract_file"][0]))
                record.refresh_from_db()
                self.assertEqual(record.abstract_file.name, before)

    def test_staff_are_not_exempt(self):
        record = self.thesis(pipeline_status=PipelineStatus.PUBLISHED)

        response = self.replace_manuscript(record, as_user=self.rdco)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_clearing_the_manuscript_is_refused_too(self):
        record = self.thesis(pipeline_status=PipelineStatus.PUBLISHED)
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            reverse("record-detail", args=[record.pk]), {"abstract_file": None}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_draft_and_a_legacy_declined_record_accept_a_new_manuscript(self):
        for pipeline_status in (PipelineStatus.DRAFT, PipelineStatus.DECLINED):
            with self.subTest(pipeline_status=pipeline_status):
                record = self.thesis(pipeline_status=pipeline_status)

                response = self.replace_manuscript(record)

                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_other_details_of_a_submitted_record_are_not_this_rule_s_concern(self):
        record = self.thesis(pipeline_status=PipelineStatus.PUBLISHED)
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            reverse("record-detail", args=[record.pk]), {"title": "Renamed"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


# --- AC: no code deletes a manuscript file a version names -------------------------

class VersionFilesSurviveTests(LegacyVersionTestBase):

    def test_replacing_the_manuscript_leaves_the_earlier_version_s_file_in_storage(self):
        record = self.declined_by_ktto()
        v1 = RecordVersion.objects.get(record=record, number=1).manuscript.name

        self.replace_manuscript(record)

        record.refresh_from_db()
        self.assertNotEqual(record.abstract_file.name, v1)
        self.assertTrue(default_storage.exists(v1))

    def test_no_source_deletes_a_manuscript_file(self):
        """
        The behavioural test above covers today's one replacement path. This
        one stops the next: no module may call `.delete()` on a manuscript or
        version file, or delete through the storage directly.
        """
        pattern = re.compile(
            r"(abstract_file|manuscript)\.delete\(|storage\.delete\("
        )
        apps_dir = Path(settings.BASE_DIR) / "apps"
        offenders = [
            str(path.relative_to(apps_dir))
            for path in apps_dir.rglob("*.py")
            if "test" not in path.name and "tests" not in path.parts
            and pattern.search(path.read_text(encoding="utf-8"))
        ]

        self.assertEqual(offenders, [])


# --- AC: earlier versions are participants only ------------------------------------

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
