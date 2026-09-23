"""
The Review & Routing Tracker and the derived `workflow_state` (IR-258).

ADR-021 §14 and `docs/workflow_routing_architecture.md` §8: `GET
/records/<id>/tracker/` answers who holds a record, who has finished and how,
who was never asked, where it was routed and what revisions were asked for --
all from persisted rows. Record detail gains three of those answers,
`workflow_state`, `current_holders` and `can_act`.

**Seam: the records API** (IR-255's confirmed seam). Records are driven through
the real submit / review / resubmit endpoints, so the shadow rows IR-257
dual-writes are the ones the tracker reads -- nothing here builds an assignment
by hand. `awaiting_document`'s precedence is pinned on the pure derivation
below; reaching it over HTTP is `apps/documents/tests/test_document_requests.py`
(IR-262).

**Deliberately not built on `test_workflow_characterisation`'s base.** IR-260
retires that suite; this one has to outlive it.
"""

from datetime import timedelta

from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.documents.models import RecordUpload, UploadSlot
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.tracker import derive_workflow_state
from core.enums import PipelineStatus, RecordTypeName, RoleName

SUBMIT_REVIEW = "/api/v1/reviews/submit/"
RESUBMIT = "/api/v1/reviews/resubmit/"


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
            record_type=RecordType.objects.get(name=type_name),
            added_by=self.owner,
            pipeline_status=PipelineStatus.DRAFT,
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
        self.client.force_authenticate(actor)
        response = self.client.post(
            SUBMIT_REVIEW,
            {"record_id": record.pk, "status": decision, "comment": comment},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def resubmit(self, record):
        # The resubmit guard wants a document newer than the decline.
        slot = UploadSlot.objects.create(
            name=f"Manuscript {record.pk}", record_type=record.record_type
        )
        upload = RecordUpload.objects.create(
            record=record, slot=slot,
            file=SimpleUploadedFile(f"revised-{record.pk}.pdf", b"%PDF-1.4 revised"),
            uploaded_by=self.owner,
        )
        RecordUpload.objects.filter(pk=upload.pk).update(
            created_at=timezone.now() + timedelta(seconds=5)
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post(RESUBMIT, {"record_id": record.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def at_parallel_review(self):
        """A Thesis whose ITSO has cleared, with IERC and KTTO still pending."""
        record = self.submitted(
            RecordTypeName.THESIS_RESEARCH,
            requested_itso=True, requested_ierc=True, requested_ktto=True,
        )
        self.review(record, self.rdco, "approved", "Needs ITSO, IERC and KTTO.")
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
    """The acceptance criteria that describe what the party list shows."""

    def test_a_thesis_at_intake(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH, requested_itso=True)
        payload = self.tracker_ok(record, self.rdco)

        self.assertEqual(self.states(payload), {
            "intake": "active",
            "adviser": "not_requested",
            "itso": "not_requested",
            "ierc": "not_requested",
            "ktto": "not_requested",
            "rdco": "awaiting",
        })
        # The requested-office booleans are a suggestion to triage (ADR-021
        # §5), not a route: ITSO is not "requested" until Intake routes to it.
        self.assertEqual(
            [h["party"] for h in payload["current_holders"]], ["intake"]
        )
        self.assertEqual(payload["workflow_state"], "submitted")

    def test_the_six_parties_come_in_one_fixed_order(self):
        record = self.submitted(RecordTypeName.PROJECT)
        payload = self.tracker_ok(record, self.rdco)
        self.assertEqual(
            [row["party"] for row in payload["parties"]],
            ["intake", "adviser", "itso", "ierc", "ktto", "rdco"],
        )

    def test_mixed_progress(self):
        record = self.at_parallel_review()
        payload = self.tracker_ok(record, self.rdco)
        rows = self.rows(payload)

        self.assertEqual(rows["itso"]["state"], "completed")
        self.assertEqual(rows["itso"]["outcome"], "cleared")
        self.assertEqual(rows["intake"]["state"], "completed")
        self.assertEqual(rows["ierc"]["state"], "active")
        self.assertEqual(rows["ktto"]["state"], "active")
        self.assertEqual(rows["rdco"]["state"], "awaiting")
        # Active, but nobody at IERC or KTTO has recorded anything yet --
        # §8.2's "requested but not yet started".
        self.assertFalse(rows["ierc"]["started"])
        self.assertEqual(
            sorted(h["party"] for h in payload["current_holders"]), ["ierc", "ktto"]
        )
        self.assertEqual(payload["workflow_state"], "in_review")

    def test_after_resubmission_the_preserved_clearance_and_its_history_show(self):
        record = self.at_parallel_review()
        self.review(record, self.ierc, "declined", "Consent form is missing.")
        self.resubmit(record)
        payload = self.tracker_ok(record, self.owner)
        rows = self.rows(payload)

        self.assertTrue(rows["itso"]["preserved"])
        self.assertFalse(rows["ierc"]["preserved"])
        clearances = {c["office"]: c for c in payload["clearances"]}
        self.assertTrue(clearances["itso"]["preserved"])
        self.assertEqual(payload["resubmission"]["offices_preserved"], ["itso"])

        self.assertEqual(len(payload["resubmissions"]), 1)
        request = payload["resubmissions"][0]
        self.assertEqual(request["party"], "ierc")
        self.assertEqual(request["state"], "resubmitted")
        self.assertEqual(request["reason"], "Consent form is missing.")
        self.assertIsNotNone(request["resolved_at"])

    def test_a_new_proposal(self):
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        payload = self.tracker_ok(record, self.adviser)

        self.assertEqual(payload["workflow_state"], "submitted")
        self.assertEqual(self.rows(payload)["rdco"]["state"], "not_requested")
        self.assertEqual(self.rows(payload)["intake"]["state"], "not_requested")
        self.assertEqual(self.rows(payload)["adviser"]["state"], "active")

    def test_routing_history_groups_one_decision_to_several_parties(self):
        record = self.submitted(
            RecordTypeName.PROJECT, requested_itso=True, requested_ktto=True
        )
        self.review(record, self.rdco, "approved", "ITSO and KTTO, please.")
        history = self.tracker_ok(record, self.rdco)["routing_history"]

        self.assertEqual(len(history), 2)
        self.assertIsNone(history[0]["from"], "the submitter sent it in")
        self.assertEqual(history[0]["to"], ["intake"])
        self.assertEqual(history[1]["from"], "intake")
        self.assertEqual(sorted(history[1]["to"]), ["itso", "ktto"])
        self.assertEqual(history[1]["actor"], self.rdco.get_full_name())

    def test_routing_history_says_when_it_starts(self):
        record = self.submitted(RecordTypeName.PROJECT)
        payload = self.tracker_ok(record, self.rdco)
        # The backfill wrote no RoutingEvent (§6), so the history is only
        # complete from the date the shadow started. On a test database the
        # migration's own row supplies that date.
        self.assertIsNotNone(payload["routing_recorded_from"])

    def test_the_intake_label_depends_on_who_is_looking(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        staff = self.rows(self.tracker_ok(record, self.rdco))["intake"]["label"]
        student = self.rows(self.tracker_ok(record, self.owner))["intake"]["label"]
        self.assertEqual(staff, "Intake & Triage")
        self.assertEqual(student, "Intake")


class WorkflowStatePrecedenceTests(TrackerTestBase):
    """
    ADR-021 §4: terminal statuses pass through; an in-review record takes the
    first rule that matches. Each rule has a case, and each case that could
    also match a later rule says so -- that is what makes it a precedence test.
    """

    def state_of(self, record, viewer=None):
        tracked = self.tracker_ok(record, viewer or self.rdco)["workflow_state"]
        detailed = self.detail(record, viewer or self.rdco)["workflow_state"]
        self.assertEqual(tracked, detailed, "detail and tracker must agree")
        return tracked

    def test_1_awaiting_resubmission_beats_final_review(self):
        # The Adviser both holds the Proposal and decides it, and has already
        # reviewed it -- so without rule 1 this would be `final_review`.
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        self.review(record, self.adviser, "declined", "Tighten the scope.")
        self.assertEqual(self.state_of(record), "awaiting_resubmission")

    def test_1_awaiting_resubmission_while_other_offices_still_hold_it(self):
        record = self.at_parallel_review()
        self.review(record, self.ierc, "declined", "Consent form is missing.")
        self.assertEqual(self.state_of(record), "awaiting_resubmission")

    def test_3_submitted_beats_final_review_for_a_new_proposal(self):
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        self.assertEqual(self.state_of(record), "submitted")

    def test_3_submitted_for_a_new_thesis(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        self.assertEqual(self.state_of(record), "submitted")

    def test_4_final_review_once_only_the_decider_holds_it(self):
        record = self.submitted(RecordTypeName.PROJECT)
        self.review(record, self.rdco, "approved", "Nothing to clear.")
        self.assertEqual(self.state_of(record), "final_review")

    def test_4_final_review_for_a_proposal_the_adviser_has_already_reviewed(self):
        # Resubmitted after the Adviser's own request: the Adviser holds it
        # again and has recorded a review, so it is no longer `submitted`.
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        self.review(record, self.adviser, "declined", "Tighten the scope.")
        self.resubmit(record)
        self.assertEqual(self.state_of(record), "final_review")

    def test_5_in_review_otherwise(self):
        record = self.at_parallel_review()
        self.assertEqual(self.state_of(record), "in_review")

    def test_terminal_statuses_pass_through(self):
        for stored in (
            PipelineStatus.DRAFT, PipelineStatus.PUBLISHED, PipelineStatus.REJECTED,
            PipelineStatus.COMPLETED, PipelineStatus.APPROVED,
        ):
            with self.subTest(stored=stored):
                record = self.make_record(RecordTypeName.PROJECT)
                Record.objects.filter(pk=record.pk).update(pipeline_status=stored)
                self.assertEqual(self.state_of(record), stored.value)


class DeriveWorkflowStateTests(SimpleTestCase):
    """
    Where `awaiting_document` ranks, pinned on the pure derivation. An open
    `DocumentRequest` reaching it end to end is `test_document_requests.py`.
    """

    def derive(self, **facts):
        base = dict(
            pipeline_status="rdco_review",
            open_resubmissions=0,
            open_document_requests=0,
            active_parties={"rdco"},
            entry_party="intake",
            entry_party_has_acted=True,
            deciding_parties={"rdco"},
        )
        base.update(facts)
        return derive_workflow_state(**base)

    def test_2_awaiting_document_beats_submitted_and_final_review(self):
        self.assertEqual(
            self.derive(open_document_requests=1), "awaiting_document"
        )
        self.assertEqual(
            self.derive(
                open_document_requests=1,
                active_parties={"intake"},
                entry_party_has_acted=False,
            ),
            "awaiting_document",
        )

    def test_1_awaiting_resubmission_beats_awaiting_document(self):
        self.assertEqual(
            self.derive(open_resubmissions=1, open_document_requests=1),
            "awaiting_resubmission",
        )

    def test_no_active_assignment_is_in_review_not_final_review(self):
        # "every active assignment belongs to a decider" is vacuously true of
        # an empty set; a record nobody holds is not in final review.
        self.assertEqual(self.derive(active_parties=set()), "in_review")


class WorkflowStateIsNeverStoredTests(SimpleTestCase):
    """ADR-021 §4 and §5 of the architecture doc: derived, never a column."""

    databases = {"default"}

    def test_no_model_has_a_workflow_state_field(self):
        offenders = [
            f"{model._meta.label}.{field.name}"
            for model in django_apps.get_models()
            for field in model._meta.get_fields()
            if field.name == "workflow_state"
        ]
        self.assertEqual(offenders, [])

    def test_no_table_has_a_workflow_state_column(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE column_name = 'workflow_state' AND table_schema = 'public'"
            )
            self.assertEqual(cursor.fetchall(), [])


class TrackerAccessTests(TrackerTestBase):
    """`visible_to()` decides, and a refusal is the missing-record 404 (IR-153)."""

    def test_the_owner_the_assigned_adviser_and_office_staff_see_it(self):
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        for viewer in (self.owner, self.adviser, self.rdco, self.itso, self.ierc, self.ktto):
            with self.subTest(viewer=viewer.email):
                self.assertEqual(
                    self.tracker(record.pk, viewer).status_code, status.HTTP_200_OK
                )

    def test_anyone_else_gets_the_missing_record_404(self):
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        missing = self.tracker(record.pk + 10_000, self.stranger)
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        for viewer in (self.stranger, self.other_adviser):
            with self.subTest(viewer=viewer.email):
                refused = self.tracker(record.pk, viewer)
                self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(refused.data, missing.data)

    def test_anonymous_is_refused(self):
        record = self.submitted(RecordTypeName.PROJECT)
        self.client.force_authenticate(None)
        response = self.client.get(reverse("record-tracker", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RecordDetailWorkflowFieldsTests(TrackerTestBase):
    """Record detail carries `workflow_state`, `current_holders` and `can_act`."""

    def can_act(self, record, viewer):
        return self.detail(record, viewer)["can_act"]

    def test_detail_names_the_current_holders(self):
        record = self.at_parallel_review()
        holders = self.detail(record, self.owner)["current_holders"]
        self.assertEqual(sorted(h["party"] for h in holders), ["ierc", "ktto"])

    def test_rdco_acts_as_intake_at_intake_and_nobody_else_does(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        self.assertEqual(self.can_act(record, self.rdco), ["intake"])
        for viewer in (self.owner, self.itso):
            with self.subTest(viewer=viewer.email):
                self.assertEqual(self.can_act(record, viewer), [])

    def test_offices_act_only_where_the_pipeline_lets_them(self):
        record = self.submitted(
            RecordTypeName.PROJECT, requested_itso=True, requested_ierc=True
        )
        self.review(record, self.rdco, "approved")
        # IERC holds an active assignment at itso_review (IR-257's reading of
        # §6), but the pipeline -- still authoritative until IR-260 -- will
        # not take its clearance until ITSO has cleared. `can_act` must not
        # offer an action the server would refuse.
        self.assertEqual(self.can_act(record, self.itso), ["itso"])
        self.assertEqual(self.can_act(record, self.ierc), [])
        self.assertEqual(self.can_act(record, self.rdco), [])

    def test_only_the_assigned_adviser_acts_on_a_proposal(self):
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        self.assertEqual(self.can_act(record, self.adviser), ["adviser"])
        self.assertEqual(self.can_act(record, self.rdco), [])

    def test_nobody_acts_while_a_resubmission_is_awaited(self):
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        self.review(record, self.adviser, "declined", "Tighten the scope.")
        self.assertEqual(self.can_act(record, self.adviser), [])
