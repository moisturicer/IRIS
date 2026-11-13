"""
A notification that asked for action says when its task ended (ADR-069, IR-1075).

Driven through the real workflow and the notification endpoints: the pool
notice a router sends, a nominee's, an owner's revision request, and the
resubmission that reopens the rows those tasks lived on. The request kinds with
no workflow of their own here (download, delete, role, document) are driven
through their rows, since only the row decides when the task ended.

Acceptance, in order: closing a task marks its notifications resolved; a
resolved notification leaves the unread count and stays in the full list;
resolved is final across a clearance reset, which sends a *new* notification;
an informational notification and one sent before the fields existed never
resolve; the pool notice's copy is two whole sentences.
"""
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import Role, RoleRequest
from apps.documents.models import DocumentRequest
from apps.notifications import settling
from apps.notifications.models import Notification, NotificationType, TaskKind
from apps.records.models import DeleteRequest, DownloadRequest
from apps.reviews import seats
from apps.reviews.models import RecordAssignment, ReviewerSeat
from core.enums import (
    AssignmentState,
    DocumentRequestState,
    Party,
    RequestStatus,
    RoleName,
    SeatState,
)

from apps.reviews.test_new_version import RESTART_ALL, V1, NewVersionTestBase, _pdf
from apps.reviews.workflow_test_helpers import make_user


def list_rows(client, as_user, **params):
    client.force_authenticate(as_user)
    response = client.get(reverse("notification-list"), {"page_size": 100, **params})
    assert response.status_code == status.HTTP_200_OK, response.data
    rows = response.data["results"] if isinstance(response.data, dict) else response.data
    return {row["id"]: row for row in rows}


class ResolvedNotificationTestBase(NewVersionTestBase):

    def rows(self, as_user, **params):
        return list_rows(self.client, as_user, **params)

    def notice(self, record, *, to=None, role=None, type_name="Record Routed"):
        query = Notification.objects.filter(record=record, notif_type__name=type_name)
        query = query.filter(recipient=to) if to else query.filter(broadcast_to_role=role)
        return query.latest("pk")

    def open_seat(self, record, party, reviewer):
        """Open the seat `reviewer` already holds (a nominee's, not a new claim)."""
        seat = ReviewerSeat.objects.get(
            assignment__record=record, assignment__party=party, reviewer=reviewer,
        )
        seat.state = SeatState.IN_REVIEW
        seat.opened_at = timezone.now()
        seat.save(update_fields=["state", "opened_at"])
        return seat

    def thesis_via(self, *routes):
        """A Thesis with a manuscript, accepted to RDCO and routed on as `routes`."""
        record = self.new_model(abstract_file=_pdf(V1))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.accept(record, [{"party": Party.RDCO, "nominees": [self.rdco.pk]}])
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            response = self.route(record, self.rdco, list(routes))
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return record


# --- the pool notice -----------------------------------------------------------------

class PoolNoticeTests(ResolvedNotificationTestBase):

    def routed_to_itso_pool(self):
        return self.thesis_via({"party": Party.ITSO})

    def test_the_pool_notice_is_two_whole_sentences(self):
        record = self.routed_to_itso_pool()

        notice = self.notice(record, role=self.itso.role)

        self.assertEqual(
            notice.message,
            # The sender is named the way the tracker names the party.
            f'{Party.RDCO.label} sent "{record.title}" to ITSO. '
            f"It waits in ITSO's pool until a reviewer claims it.",
        )

    def test_it_is_open_and_unread_until_someone_claims_it(self):
        record = self.routed_to_itso_pool()
        notice = self.notice(record, role=self.itso.role)

        row = self.rows(self.itso, unread="true")[notice.pk]

        self.assertIsNone(row["resolved_at"])
        self.assertEqual(row["resolved_label"], "")

    def test_claiming_resolves_it_for_every_member_and_leaves_read_state_alone(self):
        record = self.routed_to_itso_pool()
        notice = self.notice(record, role=self.itso.role)

        seats.claim(self.assignment(record, Party.ITSO), self.itso)

        for member in (self.itso, self.itso_coordinator):
            self.assertNotIn(notice.pk, self.rows(member, unread="true"))
            row = self.rows(member)[notice.pk]
            self.assertIsNotNone(row["resolved_at"])
            self.assertTrue(row["resolved_label"].startswith("Claimed by "), row["resolved_label"])
            # Whether *this person* opened it is theirs alone.
            self.assertFalse(row["is_read"])

    def test_it_stays_resolved_if_the_claimer_later_loses_the_seat(self):
        record = self.routed_to_itso_pool()
        notice = self.notice(record, role=self.itso.role)
        seat = seats.claim(self.assignment(record, Party.ITSO), self.itso)
        self.rows(self.itso)  # stamped the first time it is looked at

        ReviewerSeat.objects.filter(pk=seat.pk).update(state="withdrawn")

        notice.refresh_from_db()
        self.assertIsNotNone(notice.resolved_at)
        self.assertNotIn(notice.pk, self.rows(self.itso_coordinator, unread="true"))

    def test_a_decision_that_closes_the_assignment_resolves_it_without_a_claim(self):
        record = self.routed_to_itso_pool()
        notice = self.notice(record, role=self.itso.role)
        RecordAssignment.objects.filter(
            record=record, party=Party.ITSO,
        ).update(state=AssignmentState.WITHDRAWN, closed_at=timezone.now())

        row = self.rows(self.itso)[notice.pk]

        self.assertTrue(row["resolved_label"].startswith("Withdrawn on "), row["resolved_label"])


# --- a nominee, and the reset ----------------------------------------------------------

class NomineeNoticeTests(ResolvedNotificationTestBase):

    def nominated(self, *also):
        return self.thesis_via({"party": Party.ITSO, "nominees": [self.itso.pk]}, *also)

    def test_reviewing_resolves_the_nominees_notice_for_them(self):
        record = self.nominated()
        notice = self.notice(record, to=self.itso)
        self.assertIsNone(self.rows(self.itso)[notice.pk]["resolved_at"])

        self.open_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)

        row = self.rows(self.itso)[notice.pk]
        self.assertTrue(row["resolved_label"].startswith("Reviewed by you on "), row["resolved_label"])
        self.assertNotIn(notice.pk, self.rows(self.itso, unread="true"))

    @override_settings(WORKFLOW_TABLE=RESTART_ALL)
    def test_a_reset_never_reopens_it_and_sends_a_new_notification(self):
        record = self.nominated({"party": Party.IERC})
        first = self.notice(record, to=self.itso)
        self.open_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        # IERC asks for a revision, so the owner can submit a version.
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        self.edit_title(record)

        # The first notification has not been looked at since ITSO cleared.
        self.assertIsNone(Notification.objects.get(pk=first.pk).resolved_at)
        with self.captureOnCommitCallbacks(execute=True):
            self.submitted(record)

        # ITSO's assignment reopened and its seat went back into review ...
        self.assertEqual(
            self.seat_state(record, Party.ITSO, self.itso), SeatState.IN_REVIEW,
        )
        # ... yet the first notification says what happened the first time,
        first.refresh_from_db()
        self.assertTrue(first.resolved_label.startswith("Reviewed by you on "), first.resolved_label)
        self.assertNotIn(first.pk, self.rows(self.itso, unread="true"))
        # ... and the new request is a new notification that asks again.
        again = self.notice(record, to=self.itso, type_name="New Version Submitted")
        self.assertNotEqual(again.pk, first.pk)
        self.assertEqual((again.task_kind, again.resolved_at), (TaskKind.SEAT, None))
        self.assertIn(again.pk, self.rows(self.itso, unread="true"))


# --- an owner's revision request --------------------------------------------------------

class RevisionNoticeTests(ResolvedNotificationTestBase):

    def asked_of_the_owner(self):
        record = self.thesis_via({"party": Party.ITSO}, {"party": Party.IERC})
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        with self.captureOnCommitCallbacks(execute=True):
            request = self.asked(record, self.ierc)
        return record, request, self.notice(record, to=self.owner, type_name="Revision Requested")

    def test_a_new_version_resolves_it(self):
        record, _request, notice = self.asked_of_the_owner()
        self.assertIn(notice.pk, self.rows(self.owner, unread="true"))

        self.edit_title(record)
        self.submitted(record)

        row = self.rows(self.owner)[notice.pk]
        self.assertTrue(
            row["resolved_label"].startswith("Answered with a new version on "),
            row["resolved_label"],
        )
        self.assertNotIn(notice.pk, self.rows(self.owner, unread="true"))

    def test_withdrawing_it_resolves_the_original_and_the_withdrawal_stays_informational(self):
        record, request, notice = self.asked_of_the_owner()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.withdraw(record, self.ierc, request.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        rows = self.rows(self.owner)
        self.assertTrue(rows[notice.pk]["resolved_label"].startswith("Withdrawn by IERC on "))
        informational = [
            n for n in Notification.objects.filter(
                record=record, recipient=self.owner, notif_type__name="Revision Requested",
            ) if n.pk != notice.pk
        ]
        self.assertEqual([n.task_kind for n in informational], [""])
        self.assertIsNone(rows[informational[0].pk]["resolved_at"])


# --- what never resolves ---------------------------------------------------------------

class NeverResolvesTests(ResolvedNotificationTestBase):

    def test_an_informational_notification_never_resolves(self):
        record = self.thesis_via({"party": Party.ITSO})
        self.opened_seat(record, Party.ITSO, self.itso)
        with self.captureOnCommitCallbacks(execute=True):
            self.cleared(record, self.itso)

        done = self.notice(record, to=self.owner, type_name="Office Review Complete")

        self.assertEqual(self.rows(self.owner)[done.pk]["resolved_at"], None)
        self.assertEqual(done.task_kind, "")

    def test_a_notification_sent_before_this_existed_is_left_as_it_was(self):
        old = Notification.objects.create(
            recipient=self.owner, record=None,
            notif_type=NotificationType.objects.get_or_create(name="Record Routed")[0],
            message="sent before IR-1075",
        )

        row = self.rows(self.owner, unread="true")[old.pk]

        self.assertIsNone(row["resolved_at"])

    def test_a_task_that_cannot_be_read_does_not_break_the_list(self):
        kind = TaskKind.SEAT
        notice = Notification.objects.create(
            recipient=self.owner, notif_type=NotificationType.objects.get_or_create(
                name="Record Routed")[0],
            message="x", task_kind=kind, task_id=10**9,
        )
        with mock.patch.dict(settling.RESOLVERS, {kind: mock.Mock(side_effect=RuntimeError("boom"))}):
            with self.assertLogs(settling.logger, level="ERROR"):
                rows = self.rows(self.owner, unread="true")

        self.assertIn(notice.pk, rows)

    def test_a_task_whose_row_is_gone_stays_open(self):
        notice = Notification.objects.create(
            recipient=self.owner, notif_type=NotificationType.objects.get_or_create(
                name="Record Routed")[0],
            message="x", task_kind=TaskKind.REVISION, task_id=10**9,
        )

        self.assertIn(notice.pk, self.rows(self.owner, unread="true"))


# --- the request kinds -----------------------------------------------------------------

class RequestKindTests(ResolvedNotificationTestBase):
    """Each kind ends when its row leaves `open`/`pending`, and says how."""

    def bound(self, kind, row, *, recipient=None, role=None, record=None):
        return Notification.objects.create(
            recipient=recipient, broadcast_to_role=role, record=record,
            notif_type=NotificationType.objects.get_or_create(name=f"Test {kind}")[0],
            message="asks for action", task_kind=kind, task_id=row.pk,
        )

    def test_a_download_request_ends_when_rdco_rules_on_it(self):
        record = self.new_model()
        request = DownloadRequest.objects.create(record=record, requested_by=self.stranger)
        notice = self.bound(TaskKind.DOWNLOAD_REQUEST, request, role=self.rdco.role, record=record)
        self.assertIsNone(self.rows(self.rdco)[notice.pk]["resolved_at"])

        DownloadRequest.objects.filter(pk=request.pk).update(
            status=RequestStatus.APPROVED, reviewed_by=self.rdco, reviewed_at=timezone.now(),
        )

        row = self.rows(self.rdco2)[notice.pk]
        self.assertTrue(row["resolved_label"].startswith("Approved on "), row["resolved_label"])
        self.assertNotIn(notice.pk, self.rows(self.rdco, unread="true"))

    def test_a_delete_request_ends_when_it_is_declined(self):
        record = self.new_model()
        request = DeleteRequest.objects.create(record=record, requested_by=self.owner)
        notice = self.bound(TaskKind.DELETE_REQUEST, request, role=self.rdco.role, record=record)

        DeleteRequest.objects.filter(pk=request.pk).update(
            status=RequestStatus.DECLINED, reviewed_at=timezone.now(),
        )

        self.assertTrue(
            self.rows(self.rdco)[notice.pk]["resolved_label"].startswith("Declined on ")
        )

    def test_a_role_request_ends_when_it_is_approved(self):
        student = Role.objects.get(name=RoleName.STUDENT)
        applicant = make_user("resolved-applicant@cit.edu", RoleName.STUDENT)
        request = RoleRequest.objects.create(user=applicant, requested_role=student)
        notice = self.bound(TaskKind.ROLE_REQUEST, request, role=self.rdco.role)

        RoleRequest.objects.filter(pk=request.pk).update(
            status=RequestStatus.APPROVED, reviewed_at=timezone.now(),
        )

        self.assertTrue(
            self.rows(self.rdco)[notice.pk]["resolved_label"].startswith("Approved on ")
        )

    def test_a_document_request_ends_when_fulfilled_and_stays_so_if_an_upload_is_rejected(self):
        record = self.new_model()
        request = DocumentRequest.objects.create(
            record=record, party=Party.ITSO, requested_by=self.itso, message="Consent form",
        )
        notice = self.bound(TaskKind.DOCUMENT_REQUEST, request, recipient=self.owner, record=record)
        self.assertIsNone(self.rows(self.owner)[notice.pk]["resolved_at"])

        DocumentRequest.objects.filter(pk=request.pk).update(
            state=DocumentRequestState.FULFILLED, closed_at=timezone.now(),
        )
        # The reopening path settles first, as `documents.requests.reject_item` does.
        settling.settle_record(record)
        DocumentRequest.objects.filter(pk=request.pk).update(
            state=DocumentRequestState.OPEN, closed_at=None,
        )

        row = self.rows(self.owner)[notice.pk]
        self.assertTrue(row["resolved_label"].startswith("Documents uploaded on "), row["resolved_label"])
