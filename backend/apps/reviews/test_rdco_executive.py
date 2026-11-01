"""ADR-047 through the record API and real workflow services."""
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.notifications.models import Notification
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews import routing, seats
from apps.reviews.models import RecordAssignment, ResubmissionRequest, RoutingEvent
from core.enums import PipelineStatus, RecordTypeName, RoleName

from .workflow_test_helpers import make_user


class ExecutiveReviewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("executive-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("executive-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = make_user("executive-rdco@cit.edu", RoleName.RDCO)
        cls.itso = make_user("executive-itso@cit.edu", RoleName.ITSO)
        cls.itso2 = make_user("executive-itso2@cit.edu", RoleName.ITSO)
        cls.ierc = make_user("executive-ierc@cit.edu", RoleName.IERC)

    def setUp(self):
        self.record = Record.objects.create(
            title="Executive review", abstract="Research abstract " * 5,
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            adviser=self.adviser, added_by=self.owner, pipeline_status=PipelineStatus.DRAFT,
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        routing.enter_at_adviser(self.record, self.owner)
        seat = self.record.assignments.get(party="adviser").seats.get()
        seats.open_review(seat, self.adviser)

    def post(self, act, actor, body):
        self.client.force_authenticate(actor)
        return self.client.post(reverse(f"record-{act}", args=[self.record.pk]), body, format="json")

    def detail(self, actor):
        self.client.force_authenticate(actor)
        return self.client.get(reverse("record-detail", args=[self.record.pk])).data

    def send(self):
        response = self.post("accept-and-route", self.adviser, {
            "to": [{"party": "rdco", "nominees": [self.rdco.pk]}], "reason": "Institutional review",
            "suggested_offices": ["itso"],
        })
        self.assertEqual(response.status_code, 200, response.data)
        seats.open_review(self.record.assignments.get(party="rdco").seats.get(), self.rdco)

    def test_send_opens_only_rdco_and_preserves_suggestions(self):
        self.send()
        self.assertEqual(list(self.record.assignments.filter(state="active").values_list("party", flat=True)), ["rdco"])
        self.assertEqual(RoutingEvent.objects.get(record=self.record, from_party="adviser").suggested_offices, ["itso"])
        self.client.force_authenticate(self.rdco)
        options = self.client.get(reverse("record-route-options", args=[self.record.pk])).data
        self.assertEqual(options["suggested_offices"], ["itso"])
        self.assertNotIn("accept_route", self.detail(self.adviser)["capabilities"])

    def test_adviser_cannot_request_a_specialist(self):
        response = self.post("accept-and-route", self.adviser, {"to": [{"party": "itso"}], "reason": "IP"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("RDCO", response.data["detail"])
        self.assertFalse(self.record.assignments.filter(party="itso").exists())

    def test_office_pool_or_multiple_nominees_and_validation_are_atomic(self):
        self.send()
        response = self.post("route", self.rdco, {"to": [{"party": "itso", "nominees": [self.itso.pk, self.itso2.pk]}, {"party": "ierc"}], "reason": "IP and ethics"})
        self.assertEqual(response.status_code, 200, response.data)
        itso = self.record.assignments.get(party="itso")
        self.assertEqual(set(itso.seats.values_list("reviewer_id", flat=True)), {self.itso.pk, self.itso2.pk})
        self.assertFalse(self.record.assignments.get(party="ierc").seats.exists())
        count = self.record.routing_events.count()
        for nominees in ([self.itso.pk, self.itso.pk], [self.ierc.pk], [True], ["1"]):
            r = self.post("route", self.rdco, {"to": [{"party": "itso", "nominees": nominees}], "reason": "Additional opinion"})
            self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(self.record.routing_events.count(), count)
        r = self.post("route", self.rdco, {"to": [{"party": "itso"}], "reason": "Again"})
        self.assertEqual(r.status_code, 400)

    def test_rdco_can_publish_while_offices_review_and_keeps_a_completed_clearance(self):
        from apps.reviews.models import RecordClearance
        self.send()
        response = self.post("route", self.rdco, {"to": [
            {"party": "itso", "nominees": [self.itso.pk]}, {"party": "ierc", "nominees": [self.ierc.pk]}], "reason": "IP and ethics"})
        self.assertEqual(response.status_code, 200, response.data)
        seats.open_review(self.record.assignments.get(party="itso").seats.get(), self.itso)
        self.post("office-review", self.itso, {"outcome": "cleared"})
        response = self.post("decide", self.rdco, {"outcome": "publish", "token": self.detail(self.rdco)["decision"]["token"]})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(RecordClearance.objects.get(record=self.record, office="itso").status, "cleared")
        self.assertEqual(self.record.assignments.get(party="ierc").state, "withdrawn")

    def test_rdco_can_close_a_review_whose_account_no_longer_exists(self):
        self.send()
        self.post("route", self.rdco, {"to": [{"party": "itso", "nominees": [self.itso.pk]}], "reason": "IP"})
        self.record.assignments.get(party="itso").seats.update(reviewer=None)
        flags = self.detail(self.rdco)["decision"]
        self.assertIn("Former reviewer", flags["closes"]["assignments"][0]["holders"])
        response = self.post("decide", self.rdco, {"outcome": "keep_unlisted", "token": flags["token"]})
        self.assertEqual(response.status_code, 200, response.data)

    def test_office_completion_does_not_open_or_recreate_rdco(self):
        self.send()
        r = self.post("route", self.rdco, {"to": [{"party": "itso", "nominees": [self.itso.pk]}], "reason": "IP"})
        self.assertEqual(r.status_code, 200)
        seats.open_review(self.record.assignments.get(party="itso").seats.get(), self.itso)
        before = self.record.routing_events.count()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post("office-review", self.itso, {"outcome": "cleared", "comment": "No concern"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.record.assignments.filter(party="rdco").count(), 1)
        self.assertEqual(self.record.routing_events.count(), before)
        self.assertTrue(Notification.objects.filter(record=self.record, recipient=self.rdco, message__contains="ITSO finished").exists())

    def test_rdco_overrides_revision_and_closes_reviews_with_history(self):
        self.send()
        self.post("route", self.rdco, {"to": [{"party": "ierc", "nominees": [self.ierc.pk]}], "reason": "Ethics"})
        seats.open_review(self.record.assignments.get(party="ierc").seats.get(), self.ierc)
        r = self.post("request-revision", self.ierc, {"reason": "Consent missing"})
        self.assertEqual(r.status_code, 200, r.data)
        detail = self.detail(self.rdco)
        self.assertIsNone(detail["decision"]["blocked"])
        self.assertEqual(detail["readiness"]["verdict"], "ready")
        self.assertEqual(detail["decision"]["closes"]["revision_requests"][0]["party"], "ierc")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post("decide", self.rdco, {"outcome": "reject", "comment": "Cannot proceed", "token": detail["decision"]["token"]})
        self.assertEqual(response.status_code, 200, response.data)
        request = ResubmissionRequest.objects.get(record=self.record)
        self.assertEqual(request.state, "withdrawn")
        self.assertIsNotNone(request.closed_by_decision_id)
        self.assertEqual(request.closed_by_decision_id, self.record.assignments.get(party="ierc").closed_by_decision_id)
        self.assertTrue(Notification.objects.filter(record=self.record, recipient=self.owner, message__contains=f"#{request.pk} from IERC").exists())

    def test_revision_opened_after_confirmation_makes_token_stale(self):
        self.send()
        token = self.detail(self.rdco)["decision"]["token"]
        self.post("request-revision", self.rdco, {"reason": "Clarification"})
        response = self.post("decide", self.rdco, {"outcome": "publish", "token": token})
        self.assertEqual(response.status_code, 409, response.data)
        self.assertTrue(ResubmissionRequest.objects.filter(record=self.record, state="open").exists())

    def test_executive_decision_restores_the_last_submitted_manuscript(self):
        self.send()
        self.post("request-revision", self.rdco, {"reason": "Clarify methods"})
        version = self.record.versions.latest("number")
        version.manuscript = "abstracts/submitted.pdf"
        version.save(update_fields=["manuscript"])
        self.record.abstract_file = "abstracts/unsubmitted.pdf"
        self.record.save(update_fields=["abstract_file"])
        response = self.post("decide", self.rdco, {"outcome": "publish", "token": self.detail(self.rdco)["decision"]["token"]})
        self.assertEqual(response.status_code, 200, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.abstract_file.name, "abstracts/submitted.pdf")
        self.assertEqual(self.record.versions.count(), 1)

    def test_adviser_may_never_publish(self):
        detail = self.detail(self.adviser)
        self.assertNotIn("accept_publish", detail["capabilities"])
        response = self.post("decide", self.adviser, {"outcome": "publish", "token": detail["decision"]["token"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("RDCO", response.data["detail"])

    def test_adviser_still_waits_for_revision_before_sending_or_rejecting(self):
        self.post("request-revision", self.adviser, {"reason": "Revise methods"})
        detail = self.detail(self.adviser)
        response = self.post("decide", self.adviser, {"outcome": "reject", "comment": "Out of scope.", "token": detail["decision"]["token"]})
        self.assertEqual(response.status_code, 400)
        response = self.post("accept-and-route", self.adviser, {"to": [{"party": "rdco"}], "reason": "Institutional review"})
        self.assertEqual(response.status_code, 400)

    def test_specialist_cannot_route_to_rdco(self):
        self.send()
        self.post("route", self.rdco, {"to": [{"party": "itso", "nominees": [self.itso.pk]}], "reason": "IP"})
        response = self.post("route", self.itso, {"to": [{"party": "rdco"}], "reason": "Executive review"})
        self.assertEqual(response.status_code, 400)

    def test_cutover_is_idempotent_and_reverses_only_its_own_assignments(self):
        migration = import_module("apps.reviews.migrations.0023_open_rdco_for_routed_records")
        editor = SimpleNamespace(connection=connection)
        # A legacy specialist record which passed its Adviser before cutover.
        self.record.assignments.filter(party="adviser").update(state="completed")
        RecordAssignment.objects.create(record=self.record, party="itso")
        migration.forward(apps, editor)
        opened = self.record.assignments.get(party="rdco")
        self.assertEqual(opened.reason, migration.REASON)
        migration.forward(apps, editor)
        self.assertEqual(self.record.assignments.filter(party="rdco").count(), 1)
        migration.backward(apps, editor)
        self.assertFalse(self.record.assignments.filter(party="rdco").exists())
        self.assertTrue(self.record.assignments.filter(party="itso").exists())

    def test_cutover_leaves_adviser_records_and_existing_rdco_turns_alone(self):
        migration = import_module("apps.reviews.migrations.0023_open_rdco_for_routed_records")
        editor = SimpleNamespace(connection=connection)
        migration.forward(apps, editor)
        self.assertFalse(self.record.assignments.filter(party="rdco").exists())
        self.send()
        migration.forward(apps, editor)
        self.assertEqual(self.record.assignments.filter(party="rdco").count(), 1)
        migration.backward(apps, editor)
        self.assertEqual(self.record.assignments.filter(party="rdco").count(), 1)

    def test_migration_reverse_refuses_to_erase_a_reviewers_work(self):
        migration = import_module("apps.reviews.migrations.0023_open_rdco_for_routed_records")
        editor = SimpleNamespace(connection=connection)
        self.record.assignments.filter(party="adviser").update(state="completed")
        migration.forward(apps, editor)
        seats.claim(self.record.assignments.get(party="rdco"), self.rdco)
        with self.assertRaisesRegex(RuntimeError, "preserve its history"):
            migration.backward(apps, editor)

    def test_migration_reverse_preserves_an_unclaimed_pools_extension_history(self):
        from django.utils import timezone
        from apps.reviews.models import Extension

        migration = import_module("apps.reviews.migrations.0023_open_rdco_for_routed_records")
        editor = SimpleNamespace(connection=connection)
        self.record.assignments.filter(party="adviser").update(state="completed")
        migration.forward(apps, editor)
        assignment = self.record.assignments.get(party="rdco")
        now = timezone.now()
        extension = Extension.objects.create(assignment=assignment, actor=self.rdco,
            previous_due_at=now, due_at=now + timedelta(days=1), reason="Additional time")
        with self.assertRaisesRegex(RuntimeError, "preserve its history"):
            migration.backward(apps, editor)
        self.assertTrue(Extension.objects.filter(pk=extension.pk).exists())

    def test_migration_reverse_preserves_document_requests_made_from_a_pool(self):
        from apps.documents.models import DocumentRequest

        migration = import_module("apps.reviews.migrations.0023_open_rdco_for_routed_records")
        editor = SimpleNamespace(connection=connection)
        self.record.assignments.filter(party="adviser").update(state="completed")
        migration.forward(apps, editor)
        assignment = self.record.assignments.get(party="rdco")
        request = DocumentRequest.objects.create(record=self.record, assignment=assignment,
            party="rdco", requested_by=self.rdco, message="Please attach the endorsement.")
        with self.assertRaisesRegex(RuntimeError, "preserve its history"):
            migration.backward(apps, editor)
        request.refresh_from_db()
        self.assertEqual(request.assignment_id, assignment.pk)
