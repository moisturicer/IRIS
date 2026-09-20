"""
IR-266: a Thesis/Research Record can request and receive ITSO review.

ADR-021 §5 reverses ADR-018's rule that ITSO reviews Projects only: a thesis
that produces patentable work must be able to get an IP assessment. On the
current pipeline that means a Thesis/Research Record requesting ITSO takes the
same clearance route a Project does -- `itso_review` first (KTTO in parallel),
IERC joining only once ITSO clears and only if requested, then final review.

**Why this module stands alone.** IR-260 retires `test_workflow_characterisation.py`
and the matrix built on it. The rule pinned here survives the cutover -- ITSO
stays open to every record type under ADR-021 -- so it must not be deleted with
them. Nothing here imports from those suites.

**Seam: the API, end to end.** The Record is created and submitted through the
records API as its owner would, accepted at intake and cleared through the
reviews API, and ITSO's queue is read from `GET /reviews/pending/`. A Record
built straight into `rdco_intake` would skip the one step that proves the
wizard's request reaches the router: that `requested_itso` survives the write
serializer for a Thesis.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordType
from apps.reviews.models import RecordClearance
from core.enums import (
    ClearanceStatus,
    Office,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    RoleName,
)

RECORDS = "/api/v1/records/"
REVIEW_SUBMIT = "/api/v1/reviews/submit/"
PENDING = "/api/v1/reviews/pending/"


def _user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class ItsoForThesisTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("itso-thesis-owner@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("itso-thesis-rdco@cit.edu", RoleName.RDCO)
        cls.itso = _user("itso-thesis-itso@cit.edu", RoleName.ITSO)
        cls.ierc = _user("itso-thesis-ierc@cit.edu", RoleName.IERC)
        cls.ktto = _user("itso-thesis-ktto@cit.edu", RoleName.KTTO)

    # --- drivers -----------------------------------------------------------------

    def submit_as_owner(self, type_name, **requested):
        """Create the draft and submit it through the API, as the wizard does."""
        self.client.force_authenticate(self.owner)
        created = self.client.post(
            RECORDS,
            {
                "title": f"ITSO route for {type_name}",
                "abstract": "A" * 40,
                "record_type": RecordType.objects.get(name=type_name).pk,
                "authors": ["Test Author"],
                **requested,
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        record = Record.objects.get(pk=created.data["id"])

        submitted = self.client.post(
            f"{RECORDS}{record.pk}/submit/", {"dpa_accepted": True}, format="json"
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_INTAKE)
        return record

    def review(self, record, actor, decision=ReviewDecision.APPROVED):
        self.client.force_authenticate(actor)
        response = self.client.post(
            REVIEW_SUBMIT,
            {"record_id": record.pk, "status": decision, "comment": "Reason given."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response

    # --- observations ------------------------------------------------------------

    def status_of(self, record):
        record.refresh_from_db()
        return record.pipeline_status

    def clearances(self, record):
        return dict(
            RecordClearance.objects.filter(record=record).values_list("office", "status")
        )

    def queue_ids(self, actor):
        self.client.force_authenticate(actor)
        response = self.client.get(PENDING)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["id"] for row in response.data}

    # --- the rule ------------------------------------------------------------------

    def test_a_thesis_requesting_itso_reaches_itso_at_intake(self):
        record = self.submit_as_owner(
            RecordTypeName.THESIS_RESEARCH, requested_itso=True
        )

        self.review(record, self.rdco)

        self.assertEqual(self.status_of(record), PipelineStatus.ITSO_REVIEW)
        self.assertEqual(self.clearances(record), {Office.ITSO: ClearanceStatus.PENDING})
        self.assertIn(record.pk, self.queue_ids(self.itso))

    def test_clearing_itso_on_a_thesis_brings_in_requested_ierc_like_a_project(self):
        """
        Walked for both types side by side: "exactly as a Project does" is a
        comparison, and asserting the thesis alone would pass if both moved.
        """
        for type_name in (RecordTypeName.PROJECT, RecordTypeName.THESIS_RESEARCH):
            with self.subTest(record_type=type_name):
                record = self.submit_as_owner(
                    type_name,
                    requested_itso=True, requested_ierc=True, requested_ktto=True,
                )
                self.review(record, self.rdco)
                self.assertEqual(self.status_of(record), PipelineStatus.ITSO_REVIEW)
                # Intake creates every requested row, IERC's included; what keeps
                # IERC waiting is its queue, which reads `parallel_review` only.
                # So "IERC joins once ITSO clears" is asserted on the queue.
                self.assertIn(record.pk, self.queue_ids(self.itso))
                self.assertIn(record.pk, self.queue_ids(self.ktto))
                self.assertNotIn(
                    record.pk, self.queue_ids(self.ierc),
                    "IERC joins only once ITSO clears",
                )

                self.review(record, self.itso)

                self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)
                self.assertEqual(
                    self.clearances(record),
                    {
                        Office.ITSO: ClearanceStatus.CLEARED,
                        Office.IERC: ClearanceStatus.PENDING,
                        Office.KTTO: ClearanceStatus.PENDING,
                    },
                )
                self.assertIn(record.pk, self.queue_ids(self.ierc))

                self.review(record, self.ierc)
                self.review(record, self.ktto)
                self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)

    def test_a_thesis_requesting_only_itso_goes_to_final_review_once_it_clears(self):
        record = self.submit_as_owner(
            RecordTypeName.THESIS_RESEARCH, requested_itso=True
        )
        self.review(record, self.rdco)

        self.review(record, self.itso)

        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)
        self.assertEqual(self.clearances(record), {Office.ITSO: ClearanceStatus.CLEARED})
        self.assertIn(record.pk, self.queue_ids(self.rdco))

    def test_a_thesis_not_requesting_itso_never_reaches_itso(self):
        record = self.submit_as_owner(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True, requested_ktto=True
        )

        self.review(record, self.rdco)

        self.assertEqual(self.status_of(record), PipelineStatus.PARALLEL_REVIEW)
        self.assertNotIn(Office.ITSO, self.clearances(record))
        self.assertNotIn(record.pk, self.queue_ids(self.itso))

        self.review(record, self.ierc)
        self.review(record, self.ktto)

        self.assertEqual(self.status_of(record), PipelineStatus.RDCO_REVIEW)
        self.assertNotIn(Office.ITSO, self.clearances(record))
