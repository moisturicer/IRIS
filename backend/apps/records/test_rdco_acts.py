"""
RDCO replaces an Adviser, adds an owner and withdraws a paper in review
(ADR-051 decision 10, IR-797).

HTTP-level, one class per act, then the refusals every act shares. Records reach
review through `routing.enter_at_adviser` and the Adviser's accept & route, as in
the other workflow tests.
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from apps.records.models import Record, RecordOwner
from apps.reviews.models import RecordAssignment, ReviewerSeat
from apps.reviews.test_decisions import DecisionTestBase
from apps.reviews.workflow_test_helpers import make_user
from core.enums import (
    AssignmentState,
    Party,
    PipelineStatus,
    RoleName,
    SeatSource,
    SeatState,
)


def replace_url(record):
    return reverse("record-replace-adviser", args=[record.pk])


def add_owner_url(record):
    return reverse("record-add-owner", args=[record.pk])


def withdraw_url(record):
    return reverse("record-withdraw", args=[record.pk])


class RdcoActsTestBase(DecisionTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sysadmin = make_user("rdco-acts-sysadmin@cit.edu", RoleName.SYSTEM_ADMIN)
        cls.coordinator = make_user("rdco-acts-coordinator@cit.edu", RoleName.ITSO)
        cls.coordinator.is_office_coordinator = True
        cls.coordinator.save()

    def events(self, record, event_type):
        return list(AuditEvent.objects.filter(record=record, event_type=event_type).order_by("pk"))

    def told(self, user):
        return list(Notification.objects.filter(recipient=user).values_list("message", flat=True))

    def refused_roles(self):
        """Everyone who is not RDCO: each is a 403 on all three acts."""
        return [
            self.owner, self.adviser, self.itso, self.ierc, self.ktto,
            self.coordinator, self.reader, self.sysadmin,
        ]


# --- replace the Adviser ---------------------------------------------------------------

class ReplaceAdviserTests(RdcoActsTestBase):

    def test_rdco_replaces_the_adviser_and_the_new_one_is_seated(self):
        record = self.at_adviser()
        old_seat = self.adviser_seat(record)
        assignment = old_seat.assignment

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(
                replace_url(record), self.rdco,
                {"adviser": self.other_adviser.pk, "reason": "Out on leave."},
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["adviser"]["id"], self.other_adviser.pk)
        record.refresh_from_db()
        self.assertEqual(record.adviser, self.other_adviser)
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)

        old_seat.refresh_from_db()
        self.assertEqual(old_seat.state, SeatState.WITHDRAWN)
        assignment.refresh_from_db()
        # Same assignment, still active: the review's clock and filings carry on.
        self.assertEqual(assignment.state, AssignmentState.ACTIVE)
        new_seat = ReviewerSeat.objects.get(assignment=assignment, reviewer=self.other_adviser)
        self.assertEqual(new_seat.state, SeatState.ASSIGNED)
        self.assertEqual(new_seat.source, SeatSource.ASSIGNED)
        self.assertEqual(new_seat.assigned_by, self.rdco)
        self.assertEqual(new_seat.reassigned_from, old_seat)
        self.assertEqual(new_seat.reason, "Out on leave.")

    def test_the_new_adviser_carries_the_review_on_and_the_old_one_cannot(self):
        record = self.at_adviser()
        self.post(replace_url(record), self.rdco, {"adviser": self.other_adviser.pk})

        refused = self.accept(record, [{"party": Party.RDCO}], as_user=self.adviser)
        self.assertGreaterEqual(refused.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(self.active(record), {Party.ADVISER})

        accepted = self.accept(record, [{"party": Party.RDCO}], as_user=self.other_adviser)
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
        self.assertNotIn(Party.ADVISER, self.active(record))

    def test_it_is_one_audit_event_naming_both_advisers_and_both_seats(self):
        record = self.at_adviser()
        old_seat = self.adviser_seat(record)

        self.post(replace_url(record), self.rdco, {"adviser": self.other_adviser.pk, "reason": "Leave."})

        [event] = self.events(record, AuditEvent.ADVISER_REPLACED)
        self.assertEqual(event.user, self.rdco)
        new_seat = ReviewerSeat.objects.get(
            assignment=old_seat.assignment, reviewer=self.other_adviser,
        )
        self.assertEqual(event.metadata, {
            "assignment": old_seat.assignment_id,
            "previous_adviser": self.adviser.pk, "adviser": self.other_adviser.pk,
            "previous_seat": old_seat.pk, "seat": new_seat.pk, "reason": "Leave.",
        })

    def test_both_advisers_are_told_in_app_and_nobody_else(self):
        record = self.at_adviser()
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            self.post(replace_url(record), self.rdco, {"adviser": self.other_adviser.pk})

        new = Notification.objects.exclude(pk__in=before)
        self.assertEqual({n.recipient for n in new}, {self.adviser, self.other_adviser})
        old_notice = new.get(recipient=self.adviser)
        self.assertIn("replaced you", old_notice.message)
        # The old Adviser no longer advises it, so their notice links nothing.
        self.assertIsNone(old_notice.record_id)
        self.assertEqual(new.get(recipient=self.other_adviser).record_id, record.pk)

    def test_the_new_adviser_cannot_be_one_of_the_owners(self):
        record = self.at_adviser()
        RecordOwner.objects.create(record=record, user=self.other_adviser)
        seat = self.adviser_seat(record)

        response = self.post(replace_url(record), self.rdco, {"adviser": self.other_adviser.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("adviser", response.data)
        record.refresh_from_db()
        seat.refresh_from_db()
        self.assertEqual(record.adviser, self.adviser)
        self.assertEqual(seat.state, SeatState.IN_REVIEW)
        self.assertEqual(self.events(record, AuditEvent.ADVISER_REPLACED), [])

    def test_only_an_active_account_holding_the_adviser_role_is_accepted(self):
        record = self.at_adviser()
        inactive = make_user("rdco-acts-inactive-adviser@cit.edu", RoleName.ADVISER)
        inactive.is_active = False
        inactive.save()
        bodies = [
            {"adviser": self.reader.pk},        # a Student
            {"adviser": self.itso.pk},          # office staff
            {"adviser": inactive.pk},           # deactivated
            {"adviser": self.adviser.pk},       # already the Adviser
            {"adviser": 999999},                # no such account
            {"adviser": str(self.other_adviser.pk)},
            {"adviser": True},
            {"adviser": None},
            {},
        ]
        for body in bodies:
            with self.subTest(body=body):
                response = self.post(replace_url(record), self.rdco, body)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("adviser", response.data)
        record.refresh_from_db()
        self.assertEqual(record.adviser, self.adviser)

    def test_a_paper_with_no_open_adviser_review_has_nothing_to_hand_over(self):
        record = self.routed(Party.ITSO)  # the Adviser's turn is complete

        response = self.post(replace_url(record), self.rdco, {"adviser": self.other_adviser.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        record.refresh_from_db()
        self.assertEqual(record.adviser, self.adviser)

    def test_a_paper_not_in_review_is_refused(self):
        record = self.make_record()  # a draft

        response = self.post(replace_url(record), self.rdco, {"adviser": self.other_adviser.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# --- add an owner ----------------------------------------------------------------------

class AddOwnerTests(RdcoActsTestBase):

    def test_rdco_adds_an_owner_and_the_contact_person_is_unchanged(self):
        record = self.at_adviser()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(add_owner_url(record), self.rdco, {"email": self.reader.email})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        added = RecordOwner.objects.get(record=record, user=self.reader)
        self.assertFalse(added.is_primary)
        self.assertEqual(RecordOwner.objects.get(record=record, is_primary=True).user, self.owner)
        self.assertEqual(
            [(o["id"], o["is_primary"]) for o in response.data["owners"]],
            [(self.owner.pk, True), (self.reader.pk, False)],
        )

    def test_the_new_owner_can_now_read_and_act_on_the_paper(self):
        record = self.at_adviser()
        self.post(add_owner_url(record), self.rdco, {"email": self.reader.email})

        self.client.force_authenticate(self.reader)
        detail = self.client.get(reverse("record-detail", args=[record.pk]))

        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertIn("withdraw_submission", detail.data["capabilities"])

    def test_the_email_is_matched_ignoring_case_and_space(self):
        record = self.at_adviser()

        response = self.post(
            add_owner_url(record), self.rdco, {"email": f"  {self.reader.email.upper()} "},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_it_is_one_audit_event(self):
        record = self.at_adviser()

        self.post(add_owner_url(record), self.rdco, {"email": self.reader.email})

        [event] = self.events(record, AuditEvent.OWNER_ADDED)
        self.assertEqual(event.user, self.rdco)
        self.assertEqual(event.metadata, {"owner": self.reader.pk})

    def test_the_new_owner_and_the_owners_already_on_it_are_told_in_app(self):
        record = self.at_adviser()
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            self.post(add_owner_url(record), self.rdco, {"email": self.reader.email})

        new = Notification.objects.exclude(pk__in=before)
        self.assertEqual({n.recipient for n in new}, {self.reader, self.owner})
        self.assertIn("added you", new.get(recipient=self.reader).message)

    def test_only_an_existing_active_verified_account_can_be_added(self):
        record = self.at_adviser()
        unverified = make_user("rdco-acts-unverified@cit.edu", RoleName.STUDENT)
        unverified.is_verified = False
        unverified.save()
        inactive = make_user("rdco-acts-inactive@cit.edu", RoleName.STUDENT)
        inactive.is_active = False
        inactive.save()
        bodies = [
            {"email": unverified.email}, {"email": inactive.email},
            {"email": "nobody@cit.edu"}, {"email": ""}, {"email": None}, {"email": 7}, {},
        ]
        for body in bodies:
            with self.subTest(body=body):
                response = self.post(add_owner_url(record), self.rdco, body)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                # One answer for all of them: it never says which accounts exist.
                self.assertEqual(
                    [str(m) for m in response.data["email"]],
                    ["Use an existing, active, verified account."],
                )
        self.assertEqual(RecordOwner.objects.filter(record=record).count(), 1)

    def test_the_adviser_and_an_existing_owner_cannot_be_added(self):
        record = self.at_adviser()

        for who in (self.adviser, self.owner):
            with self.subTest(who=who.email):
                response = self.post(add_owner_url(record), self.rdco, {"email": who.email})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(RecordOwner.objects.filter(record=record).count(), 1)

    def test_a_paper_not_in_review_is_refused(self):
        draft = self.make_record()
        published = self.at_adviser()
        self.publish_via_rdco(published)

        for record in (draft, published):
            with self.subTest(status=record.pipeline_status):
                response = self.post(add_owner_url(record), self.rdco, {"email": self.reader.email})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(RecordOwner.objects.filter(record=record, user=self.reader).exists())


# --- withdraw --------------------------------------------------------------------------

class WithdrawTests(RdcoActsTestBase):

    REASON = "The owner has left the university and the paper is abandoned."

    def in_review_at_itso(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        return record

    def test_rdco_withdraws_a_paper_by_the_path_an_owners_delete_takes(self):
        record = self.in_review_at_itso()

        response = self.post(withdraw_url(record), self.rdco, {"reason": self.REASON})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        # What `DELETE /records/<id>/` leaves (see test_delete_withdraws_review).
        self.assertTrue(record.is_deleted)
        self.assertEqual(record.deleted_by, self.rdco)
        self.assertEqual(record.pipeline_status, PipelineStatus.PENDING_DELETE)
        assignments = RecordAssignment.objects.filter(record=record)
        self.assertFalse(assignments.filter(state=AssignmentState.ACTIVE).exists())
        withdrawn = assignments.filter(state=AssignmentState.WITHDRAWN)
        self.assertTrue(withdrawn.exists())
        self.assertTrue(all(a.closed_by_id == self.rdco.pk for a in withdrawn))
        seats = ReviewerSeat.objects.filter(assignment__record=record)
        self.assertFalse(seats.filter(state__in=(SeatState.ASSIGNED, SeatState.IN_REVIEW)).exists())

    def test_the_audit_event_carries_rdcos_reason(self):
        record = self.in_review_at_itso()

        self.post(withdraw_url(record), self.rdco, {"reason": f"  {self.REASON}  "})

        [event] = self.events(record, AuditEvent.RECORD_WITHDRAWN)
        self.assertEqual(event.user, self.rdco)
        self.assertEqual(event.metadata["reason"], self.REASON)
        self.assertIn(Party.ITSO, event.metadata["closed_parties"])

    def test_an_owners_own_withdrawal_still_carries_no_reason(self):
        record = self.in_review_at_itso()

        self.client.force_authenticate(self.owner)
        self.client.delete(reverse("record-detail", args=[record.pk]))

        [event] = self.events(record, AuditEvent.RECORD_WITHDRAWN)
        self.assertNotIn("reason", event.metadata)

    def test_the_owners_and_the_people_whose_work_ends_are_told(self):
        record = self.in_review_at_itso()
        co_owner = make_user("rdco-acts-coowner@cit.edu", RoleName.STUDENT)
        RecordOwner.objects.create(record=record, user=co_owner)
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            self.post(withdraw_url(record), self.rdco, {"reason": self.REASON})

        new = Notification.objects.exclude(pk__in=before)
        # Every owner, with RDCO's reason; the ITSO reviewer whose seat closed.
        for owner in (self.owner, co_owner):
            [message] = list(new.filter(recipient=owner).values_list("message", flat=True))
            self.assertIn("RDCO withdrew", message)
            self.assertIn(self.REASON, message)
        [reviewer_notice] = list(new.filter(recipient=self.itso).values_list("message", flat=True))
        self.assertIn("your review is closed", reviewer_notice)
        # RDCO's own act, even on a seat RDCO held, needs no notice to RDCO.
        self.assertFalse(new.filter(recipient=self.rdco).exists())

    def test_a_reason_is_required(self):
        record = self.in_review_at_itso()

        for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": None}, {"reason": 5},
                     {"reason": "x" * 1001}):
            with self.subTest(body=body):
                response = self.post(withdraw_url(record), self.rdco, body)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("reason", response.data)
        record.refresh_from_db()
        self.assertFalse(record.is_deleted)
        self.assertTrue(RecordAssignment.objects.filter(
            record=record, state=AssignmentState.ACTIVE,
        ).exists())
        self.assertEqual(self.events(record, AuditEvent.RECORD_WITHDRAWN), [])

    def test_only_a_paper_in_review_can_be_withdrawn(self):
        draft = self.make_record()
        published = self.at_adviser()
        self.publish_via_rdco(published)

        for record in (draft, published):
            with self.subTest(status=record.pipeline_status):
                response = self.post(withdraw_url(record), self.rdco, {"reason": self.REASON})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                record.refresh_from_db()
                self.assertFalse(record.is_deleted)


# --- what every act shares ---------------------------------------------------------------

class EveryActTests(RdcoActsTestBase):

    def acts(self, record):
        return [
            (replace_url(record), {"adviser": self.other_adviser.pk}),
            (add_owner_url(record), {"email": self.reader.email}),
            (withdraw_url(record), {"reason": "Withdrawn."}),
        ]

    def test_no_other_role_can_do_any_of_them(self):
        record = self.at_adviser()
        seat = self.adviser_seat(record)

        for user in self.refused_roles():
            for url, body in self.acts(record):
                with self.subTest(user=user.email, url=url):
                    self.assertEqual(
                        self.post(url, user, body).status_code, status.HTTP_403_FORBIDDEN,
                    )
        record.refresh_from_db()
        seat.refresh_from_db()
        self.assertEqual(record.adviser, self.adviser)
        self.assertFalse(record.is_deleted)
        self.assertEqual(RecordOwner.objects.filter(record=record).count(), 1)
        self.assertEqual(seat.state, SeatState.IN_REVIEW)
        for event_type in (AuditEvent.ADVISER_REPLACED, AuditEvent.OWNER_ADDED,
                           AuditEvent.RECORD_WITHDRAWN):
            self.assertEqual(self.events(record, event_type), [])

    def test_an_unknown_paper_is_a_404_for_rdco(self):
        record = self.at_adviser()
        missing = Record.objects.order_by("-pk").first().pk + 1000
        for name, body in (
            ("record-replace-adviser", {"adviser": self.other_adviser.pk}),
            ("record-add-owner", {"email": self.reader.email}),
            ("record-withdraw", {"reason": "x"}),
        ):
            with self.subTest(name=name):
                response = self.post(reverse(name, args=[missing]), self.rdco, body)
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Record.objects.filter(pk=record.pk).exists())

    def test_each_act_takes_the_per_record_lock(self):
        for name, body in (
            ("record-replace-adviser", {"adviser": self.other_adviser.pk}),
            ("record-add-owner", {"email": self.reader.email}),
            ("record-withdraw", {"reason": "Withdrawn."}),
        ):
            with self.subTest(name=name):
                record = self.at_adviser()
                with CaptureQueriesContext(connection) as queries:
                    response = self.post(reverse(name, args=[record.pk]), self.rdco, body)
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                locks = [
                    q["sql"] for q in queries.captured_queries
                    if "FOR UPDATE" in q["sql"] and 'FROM "records_record"' in q["sql"]
                ]
                self.assertTrue(locks, f"{name} never locked the record row")

    def test_every_act_works_on_any_paper_in_review_not_only_during_a_deletion(self):
        # Nothing here depends on an account deletion: the acts are RDCO's on
        # their own, whatever the paper's owner or Adviser is doing.
        record = self.at_adviser()
        self.assertEqual(
            self.post(add_owner_url(record), self.rdco, {"email": self.reader.email}).status_code, 200,
        )
        self.assertEqual(
            self.post(replace_url(record), self.rdco, {"adviser": self.other_adviser.pk}).status_code, 200,
        )
        self.assertEqual(
            self.post(withdraw_url(record), self.rdco, {"reason": "Withdrawn."}).status_code, 200,
        )
