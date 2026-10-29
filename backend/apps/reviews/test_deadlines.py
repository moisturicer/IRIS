"""Assignment clocks are informational, fixed at opening (ADR-043 §§1–6)."""
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from apps.audit.models import AuditEvent
from apps.documents.models import DocumentRequest
from apps.documents.requests import withdraw_request
from core.enums import Party

from .deadlines import deadline_payload
from .models import Holiday, RecordAssignment, Turnaround
from .test_seats import SeatTestBase
from .test_new_version import NewVersionTestBase

MANILA = ZoneInfo("Asia/Manila")


def at(day, hour=12, minute=0):
    return datetime(2027, 3, day, hour, minute, tzinfo=MANILA)


class AssignmentDeadlineTests(SeatTestBase):
    def setUp(self):
        self.record = self.make_record(adviser=self.adviser)

    def opening(self, party=Party.ITSO, when=None):
        return RecordAssignment.objects.create(
            record=self.record, party=party, opened_at=when or at(25),
        )

    def test_working_days_skip_opening_day_weekend_and_holiday(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=2)
        Holiday.objects.create(date=at(26).date(), name="Demo holiday")
        assignment = self.opening()
        self.assertEqual(assignment.due_at, at(30, 23, 59))
        self.assertEqual(assignment.original_due_at, assignment.due_at)

    def test_unconfigured_has_no_clock_and_configuration_changes_do_not_rewrite(self):
        assignment = self.opening()
        self.assertIsNone(assignment.due_at)
        Turnaround.objects.create(party=Party.ITSO, working_days=5)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.due_at)
        other = self.opening(Party.IERC)
        self.assertIsNone(other.due_at)

    def test_manila_due_boundary_and_closed_assignment(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=1)
        assignment = self.opening()
        with patch("apps.reviews.deadlines.timezone.now", return_value=at(26, 23, 59)):
            self.assertFalse(deadline_payload(assignment)["is_overdue"])
        with patch("apps.reviews.deadlines.timezone.now", return_value=at(27, 0)):
            self.assertTrue(deadline_payload(assignment)["is_overdue"])
            assignment.state = "completed"
            assignment.save(update_fields=["state"])
            self.assertFalse(deadline_payload(assignment)["is_overdue"])

    def test_overlapping_own_requests_pause_once_other_party_does_not(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=1)
        assignment = self.opening(when=at(22))
        original = assignment.due_at
        with patch("django.utils.timezone.now", return_value=at(23)):
            first = DocumentRequest.objects.create(record=self.record, assignment=assignment,
                                                   party=Party.ITSO, message="First", created_at=at(23))
        with patch("django.utils.timezone.now", return_value=at(24)):
            second = DocumentRequest.objects.create(record=self.record, assignment=assignment,
                                                    party=Party.ITSO, message="Second", created_at=at(24))
            DocumentRequest.objects.create(record=self.record, party=Party.IERC, message="Other")
            withdraw_request(first, self.itso)
            assignment.refresh_from_db()
            self.assertFalse(deadline_payload(assignment)["is_overdue"])
            self.assertEqual(assignment.due_at, original)
        with patch("django.utils.timezone.now", return_value=at(25)):
            withdraw_request(second, self.itso)
        assignment.refresh_from_db()
        self.assertEqual(assignment.due_at, at(25, 23, 59))
        self.assertEqual(assignment.extensions.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(event_type="ASSIGNMENT_EXTENDED").count(), 1)

    def test_only_own_coordinator_extends_with_reason_and_later_date(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=1)
        assignment = self.opening()
        url = f"/api/v1/assignments/{assignment.pk}/extend/"
        data = {"due_at": at(30, 23, 59).isoformat(), "reason": "Committee unavailable"}
        for actor in (self.owner, self.adviser, self.itso, self.ierc_coordinator, self.rdco):
            self.assertEqual(self.post(url, actor, data).status_code, 403)
        self.assertEqual(self.post(url, self.stranger, data).status_code, 404)
        self.assertEqual(self.post(url, self.itso_coordinator, {**data, "reason": " "}).status_code, 400)
        self.assertEqual(self.post(url, self.itso_coordinator, data).status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.original_due_at, at(26, 23, 59))
        self.assertEqual(assignment.due_at, at(30, 23, 59))
        self.assertEqual(self.post(url, self.itso_coordinator, data).status_code, 400)
        self.assertEqual(assignment.extensions.count(), 1)

    def test_reassignment_preserves_date_and_changed_turnaround(self):
        config = Turnaround.objects.create(party=Party.ITSO, working_days=1)
        assignment = self.opening()
        before = assignment.due_at
        seat = self.seat(assignment, self.itso)
        config.working_days = 10
        config.save()
        response = self.post(f"/api/v1/seats/{seat.pk}/reassign/", self.itso_coordinator,
                             {"reviewer": self.itso2.pk})
        self.assertEqual(response.status_code, 201, response.data)
        assignment.refresh_from_db()
        self.assertEqual(assignment.due_at, before)

    def test_adviser_cannot_extend_even_with_coordinator_flag(self):
        Turnaround.objects.create(party=Party.ADVISER, working_days=1)
        assignment = self.opening(Party.ADVISER)
        self.adviser.is_office_coordinator = True
        self.adviser.save(update_fields=["is_office_coordinator"])
        response = self.post(f"/api/v1/assignments/{assignment.pk}/extend/", self.adviser,
                             {"due_at": at(30, 23, 59).isoformat(), "reason": "Busy"})
        self.assertEqual(response.status_code, 403)

    def test_adviser_document_wait_moves_date_only_by_system_extension(self):
        Turnaround.objects.create(party=Party.ADVISER, working_days=2)
        assignment = self.opening(Party.ADVISER, when=at(22))
        with patch("django.utils.timezone.now", return_value=at(23)):
            request = DocumentRequest.objects.create(record=self.record, assignment=assignment,
                                                     party=Party.ADVISER, message="Endorsement")
        with patch("django.utils.timezone.now", return_value=at(25)):
            withdraw_request(request, self.adviser)
        assignment.refresh_from_db()
        self.assertEqual(assignment.due_at, at(26, 23, 59))
        extension = assignment.extensions.get()
        self.assertTrue(extension.system)
        self.assertIsNone(extension.actor)

    def test_other_partys_request_does_not_pause_and_audit_failure_rolls_back(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=1)
        assignment = self.opening()
        other = self.opening(Party.IERC)
        DocumentRequest.objects.create(record=self.record, assignment=other,
                                       party=Party.IERC, message="Other office")
        with patch("apps.reviews.deadlines.timezone.now", return_value=at(29)):
            self.assertTrue(deadline_payload(assignment)["is_overdue"])
        from .deadlines import extend
        original = assignment.due_at
        with patch("apps.audit.workflow.AuditEvent.objects.create", side_effect=RuntimeError("audit")):
            with self.assertRaisesRegex(RuntimeError, "audit"):
                extend(assignment, self.itso_coordinator, due_at=at(30, 23, 59), reason="More time")
        assignment.refresh_from_db()
        self.assertEqual(assignment.due_at, original)
        self.assertFalse(assignment.extensions.exists())

    def test_fulfillment_and_reopening_count_new_pause_only_with_holidays(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=2)
        Holiday.objects.create(date=at(26).date(), name="Holiday")
        assignment = self.opening(when=at(24))
        self.assertEqual(assignment.due_at, at(29, 23, 59))
        with patch("django.utils.timezone.now", return_value=at(25)):
            request = DocumentRequest.objects.create(record=self.record, assignment=assignment,
                                                     party=Party.ITSO, message="Form")
        with patch("django.utils.timezone.now", return_value=at(29)):
            request.state = "fulfilled"
            request.closed_at = at(29)
            request.save(update_fields=["state", "closed_at"])
        assignment.refresh_from_db()
        self.assertEqual(assignment.due_at, at(30, 23, 59))
        with patch("django.utils.timezone.now", return_value=at(30)):
            request.state = "open"
            request.closed_at = None
            request.save(update_fields=["state", "closed_at"])
            withdraw_request(request, self.itso)
        assignment.refresh_from_db()
        self.assertEqual(assignment.due_at, at(30, 23, 59))
        self.assertEqual(assignment.extensions.count(), 1)

    def test_endpoint_missing_hidden_anonymous_and_roleless_contract(self):
        from apps.accounts.models import User

        assignment = self.opening()
        url = f"/api/v1/assignments/{assignment.pk}/extend/"
        missing = "/api/v1/assignments/2147483647/extend/"
        admin = User.objects.create_superuser(email="deadline-admin@cit.edu", password="TestPass123!", role=None)
        for actor in (self.stranger, admin):
            self.client.force_authenticate(actor)
            hidden = self.client.post(url, {}, format="json")
            absent = self.client.post(missing, {}, format="json")
            self.assertEqual(hidden.status_code, 404)
            self.assertEqual((hidden.status_code, hidden.content), (absent.status_code, absent.content))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 401)

    def test_deadline_and_extension_prose_follow_review_visibility(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=1)
        assignment = self.opening()
        from .deadlines import extend
        extend(assignment, self.itso_coordinator, due_at=at(30, 23, 59), reason="Private reason")
        assignment.refresh_from_db()
        self.assertTrue(deadline_payload(assignment, self.itso_coordinator)["can_extend"])
        self.assertFalse(deadline_payload(assignment, self.owner)["can_extend"])
        self.assertEqual(deadline_payload(assignment, readable=False)["extensions"][0]["reason"], None)

    def test_no_transition_clearance_or_decision_reads_deadline(self):
        import ast
        from pathlib import Path

        # Payload builders may project clocks; the acts must never branch on
        # them. Keep this guard independent of any chosen deadline values.
        for filename in ("decisions.py", "office_review.py", "routing.py", "revisions.py", "withdrawal.py"):
            tree = ast.parse(Path(__file__).with_name(filename).read_text(encoding="utf-8"))
            reads = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                     and node.attr in {"due_at", "original_due_at", "is_overdue"}]
            self.assertEqual(reads, [], filename)
        tree = ast.parse(Path(__file__).with_name("seats.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name != "seat_payload":
                self.assertFalse(any(isinstance(part, ast.Attribute) and part.attr == "due_at"
                                     for part in ast.walk(node)), node.name)


class VersionDeadlineTests(NewVersionTestBase):
    def setUp(self):
        for party in (Party.ADVISER, Party.ITSO, Party.IERC, Party.RDCO):
            Turnaround.objects.create(party=party, working_days=2)

    def test_new_version_refreshes_only_requesting_party_and_suspends_revision_clock(self):
        with patch("django.utils.timezone.now", return_value=at(22)):
            record = self.itso_cleared_and_ierc_asked()
        itso = RecordAssignment.objects.get(record=record, party=Party.ITSO)
        ierc = RecordAssignment.objects.get(record=record, party=Party.IERC)
        before = (itso.due_at, itso.original_due_at, itso.clock_started_at)
        with patch("django.utils.timezone.now", return_value=at(29)):
            self.assertFalse(deadline_payload(ierc)["is_overdue"])
            self.assertTrue(deadline_payload(ierc)["clock_paused"])
            self.edit_title(record)
            self.submitted(record)
        ierc.refresh_from_db()
        itso.refresh_from_db()
        self.assertEqual(ierc.due_at, at(31, 23, 59))
        self.assertEqual((itso.due_at, itso.original_due_at, itso.clock_started_at), before)

    def test_submission_routing_and_handback_all_start_configured_clocks(self):
        with patch("django.utils.timezone.now", return_value=at(25)):
            record = self.thesis(Party.ITSO)
            adviser = RecordAssignment.objects.get(record=record, party=Party.ADVISER)
            office = RecordAssignment.objects.get(record=record, party=Party.ITSO)
            self.assertEqual(adviser.due_at, at(29, 23, 59))
            self.assertEqual(office.due_at, at(29, 23, 59))
            self.opened_seat(record, Party.ITSO, self.itso)
            self.cleared(record, self.itso)
            rdco = RecordAssignment.objects.get(record=record, party=Party.RDCO)
            self.assertEqual(rdco.due_at, at(29, 23, 59))

    def test_rerouting_active_assignment_preserves_date_and_overdue_does_not_block_review(self):
        with patch("django.utils.timezone.now", return_value=at(22)):
            record = self.thesis(Party.ITSO, Party.IERC)
        itso = RecordAssignment.objects.get(record=record, party=Party.ITSO)
        before = itso.due_at
        self.opened_seat(record, Party.IERC, self.ierc)
        with patch("django.utils.timezone.now", return_value=at(29)):
            response = self.route(record, self.ierc, [{"party": "itso", "nominee": self.itso.pk}])
            self.assertEqual(response.status_code, 200, response.data)
            itso.refresh_from_db()
            self.assertEqual(itso.due_at, before)
            self.assertTrue(deadline_payload(itso)["is_overdue"])
            seat = itso.seats.get(reviewer=self.itso)
            opened = self.post(f"/api/v1/seats/{seat.pk}/open/", self.itso, {})
            self.assertEqual(opened.status_code, 200, opened.data)
            self.cleared(record, self.itso)
        self.assertEqual(record.clearances.get(office=Party.ITSO).status, "cleared")

    def test_pool_seat_tracker_and_capabilities_share_deadline_facts(self):
        record = self.thesis(Party.ITSO)
        assignment = RecordAssignment.objects.get(record=record, party=Party.ITSO)
        expected = assignment.due_at.isoformat()
        self.client.force_authenticate(self.itso_coordinator)
        tracker = self.client.get(f"/api/v1/records/{record.pk}/tracker/").data
        row = next(p for p in tracker["parties"] if p["party"] == "itso")
        self.assertEqual(row["due_at"], expected)
        self.assertTrue(row["can_extend"])
        capability = next(p for p in tracker["assignment_deadlines"] if p["party"] == "itso")
        self.assertEqual(capability["due_at"], expected)
        pool = self.client.get("/api/v1/reviews/mine/").data["rows"]
        self.assertEqual(next(r for r in pool if r["record"] == record.pk)["due_at"], expected)
        claimed = self.post(f"/api/v1/assignments/{assignment.pk}/claim/", self.itso, {})
        self.assertEqual(claimed.status_code, 201, claimed.data)
        self.assertEqual(claimed.data["due_at"], expected)
        self.assertFalse(claimed.data["can_extend"])

    def test_earlier_extension_remains_in_tracker_after_rerouting(self):
        from .deadlines import extend

        with patch("django.utils.timezone.now", return_value=at(22)):
            record = self.thesis(Party.ITSO, Party.IERC)
        first = RecordAssignment.objects.get(record=record, party=Party.ITSO)
        extend(first, self.itso_coordinator, due_at=at(29, 23, 59), reason="First round extension")
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        response = self.route(record, self.ierc, [{"party": "itso"}])
        self.assertEqual(response.status_code, 200, response.data)
        payload = self.tracker(record, self.itso_coordinator)
        old = next(a for a in payload["assignment_deadline_history"] if a["assignment"] == first.pk)
        self.assertEqual(old["extensions"][0]["reason"], "First round extension")
        self.assertEqual(old["state"], "completed")
