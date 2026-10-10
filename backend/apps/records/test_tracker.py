"""
The Review & Routing Tracker after the adviser-first cutover (IR-260).

ADR-021 §14 and `docs/workflow_routing_architecture.md` §8: `GET
/records/<id>/tracker/` answers who holds a record, who has finished and how,
who was never asked, where it was routed and what revisions were asked for --
all from persisted rows. Record detail carries two of those answers,
`workflow_state` and `current_holders`. (A third, `can_act`, answered for the
retired fixed pipeline's review form and was deleted with it by IR-274.)

**Seam: the records API.** Submission, routing, office review and revision use
the public endpoints. Document requests are covered by the shared fixture in
`apps/documents/tests`.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordAssignment
from core.enums import PipelineStatus, RecordTypeName, RoleName


def make_user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name=role_name, role=role, is_verified=True,
    )


class TrackerTestBase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("tracker-owner@cit.edu", RoleName.STUDENT)
        cls.stranger = make_user("tracker-stranger@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("tracker-adviser@cit.edu", RoleName.ADVISER)
        cls.other_adviser = make_user("tracker-other-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = make_user("tracker-rdco@cit.edu", RoleName.RDCO)
        cls.itso = make_user("tracker-itso@cit.edu", RoleName.ITSO)
        cls.ierc = make_user("tracker-ierc@cit.edu", RoleName.IERC)
        cls.ktto = make_user("tracker-ktto@cit.edu", RoleName.KTTO)

    # --- drivers, all through HTTP --------------------------------------------

    def make_record(self, type_name, **extra):
        record = Record.objects.create(
            title=f"Tracker {type_name}",
            abstract="A" * 40,
            record_type=RecordType.objects.get_or_create(name=type_name)[0],
            added_by=self.owner,
            pipeline_status=PipelineStatus.DRAFT,
            adviser=extra.pop("adviser", self.adviser),
            **extra,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def submitted(self, type_name, **extra):
        record = self.make_record(type_name, **extra)
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            reverse("record-submit", args=[record.pk]),
            {"dpa_accepted": True}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return record

    def review(self, record, actor, decision, comment=""):
        """Office action through the adviser-first public API."""
        assignment = RecordAssignment.objects.get(
            record=record, party=actor.role.name.lower(), state="active",
        )
        seat = assignment.seats.get(reviewer=actor)
        self.client.force_authenticate(actor)
        opened = self.client.post(f"/api/v1/seats/{seat.pk}/open/", {}, format="json")
        self.assertEqual(opened.status_code, status.HTTP_200_OK, opened.data)
        response = self.client.post(
            reverse("record-office-review", args=[record.pk]),
            {"outcome": "cleared" if decision == "approved" else "finding", "comment": comment},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def route_requested(self, record):
        entry = RecordAssignment.objects.get(record=record, party="adviser", state="active")
        seat = entry.seats.get(reviewer=self.adviser)
        self.client.force_authenticate(self.adviser)
        opened = self.client.post(f"/api/v1/seats/{seat.pk}/open/", {}, format="json")
        self.assertEqual(opened.status_code, status.HTTP_200_OK, opened.data)
        to = [
            {"party": party, "nominee": getattr(self, party).pk}
            for party in ("itso", "ierc", "ktto")
            if getattr(record, f"requested_{party}")
        ]
        response = self.client.post(
            reverse("record-accept-and-route", args=[record.pk]),
            {"to": to, "reason": "Specialist review requested by the author."}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def at_parallel_review(self):
        """A Thesis whose ITSO has cleared, with IERC and KTTO still pending."""
        record = self.submitted(
            RecordTypeName.THESIS_RESEARCH,
            requested_itso=True, requested_ierc=True, requested_ktto=True,
        )
        self.route_requested(record)
        self.review(record, self.itso, "approved", "No patent concerns.")
        return record

    # --- observations ---------------------------------------------------------

    def tracker(self, record_pk, viewer=None):
        self.client.force_authenticate(viewer or self.owner)
        return self.client.get(reverse("record-tracker", args=[record_pk]))

    def tracker_ok(self, record, viewer=None):
        response = self.tracker(record.pk, viewer)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def detail(self, record, viewer=None):
        self.client.force_authenticate(viewer or self.owner)
        response = self.client.get(reverse("record-detail", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    @staticmethod
    def rows(payload):
        return {row["party"]: row for row in payload["parties"]}

    def states(self, payload):
        return {party: row["state"] for party, row in self.rows(payload).items()}


class TrackerPartiesTests(TrackerTestBase):
    """The tracker reports the assignments that now drive the workflow."""

    def test_submission_enters_adviser_and_never_intake(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        payload = self.tracker_ok(record)
        self.assertEqual(payload["workflow_state"], "submitted")
        self.assertEqual(self.states(payload)["adviser"], "active")
        self.assertNotIn("intake", [holder["party"] for holder in payload["current_holders"]])
        self.assertEqual(self.detail(record)["current_holders"][0]["party"], "adviser")

    def test_intake_is_never_shown_as_a_step(self):
        """IR-274 (ADR-032 §13): no Intake row unless the record has Intake history."""
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        self.assertNotIn("intake", self.rows(self.tracker_ok(record)))

    def test_intake_history_stays_readable(self):
        from apps.reviews.models import RecordAssignment

        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        RecordAssignment.objects.create(
            record=record, party="intake", state="withdrawn",
            reason="ADR-032: intake retired",
        )
        row = self.rows(self.tracker_ok(record))["intake"]
        self.assertEqual((row["label"], row["state"]), ("Intake (retired)", "withdrawn"))

    def test_routed_offices_and_preserved_itso_clearance(self):
        record = self.at_parallel_review()
        payload = self.tracker_ok(record)
        states = self.states(payload)
        self.assertEqual(states["itso"], "completed")
        self.assertEqual(states["ierc"], "active")
        self.assertEqual(states["ktto"], "active")
        self.assertEqual(self.detail(record)["workflow_state"], "in_review")

    def test_revision_request_is_visible_to_its_owner(self):
        record = self.at_parallel_review()
        seat = RecordAssignment.objects.get(record=record, party="ierc").seats.get(
            reviewer=self.ierc,
        )
        self.client.force_authenticate(self.ierc)
        opened = self.client.post(f"/api/v1/seats/{seat.pk}/open/", {}, format="json")
        self.assertEqual(opened.status_code, status.HTTP_200_OK, opened.data)
        requested = self.client.post(
            reverse("record-request-revision", args=[record.pk]),
            {"reason": "Please revise the consent procedure."}, format="json",
        )
        self.assertEqual(requested.status_code, status.HTTP_200_OK, requested.data)
        self.assertEqual(self.tracker_ok(record)["workflow_state"], "awaiting_resubmission")
        self.assertEqual(self.detail(record)["workflow_state"], "awaiting_resubmission")

    def test_unrelated_reader_cannot_see_in_flight_tracker(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        self.assertEqual(self.tracker(record.pk, self.stranger).status_code, 404)
