"""
Readers report Comments, and RDCO or the System Admin remove them with a reason
or dismiss the reports (ADR-032 §7, amendment 2026-10-31; IR-691).

Decided 2026-11-15 (Hermoine Zozobrado): RDCO and the System Admin share the
Reported comments queue; either removes any comment, reported or not, from the
queue or from the paper; a writer's own delete closes the comment's open
reports, and an edit changes nothing; reporting spends the posting budget.

Pinned at the REST seam, one class per acceptance criterion.
"""

from unittest import mock

from django.conf import settings
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from apps.records.models import CommentReport, PublicComment
from core.enums import CommentDeletion, CommentReportState, PipelineStatus, RoleName

from .test_public_comments import CommentTestBase, make_paper, make_user


def report_url(record, comment_id):
    return reverse("record-comment-reports", args=[record.pk, comment_id])


QUEUE_URL = reverse("comment-moderation")


def remove_url(comment_id):
    return reverse("comment-moderation-remove", args=[comment_id])


def dismiss_url(comment_id):
    return reverse("comment-moderation-dismiss", args=[comment_id])


class ReportTestBase(CommentTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rdco = make_user("pc-rdco@cit.edu", RoleName.RDCO, first="Rita", last="Rdco")
        cls.sysadmin = make_user("pc-sysadmin@cit.edu", RoleName.SYSTEM_ADMIN, first="Sam", last="Admin")
        cls.itso = make_user("pc-itso@cit.edu", RoleName.ITSO, first="Ivo", last="Itso")

    def report(self, user, comment_id, reason="spam", note=None, record=None):
        body = {"reason": reason, **({"note": note} if note is not None else {})}
        return self.as_(user).post(report_url(record or self.paper, comment_id), body, format="json")

    def reported(self, user, comment_id, reason="spam", note=None):
        response = self.report(user, comment_id, reason, note)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, getattr(response, "data", None))
        return response

    def queue(self, user=None):
        return self.as_(user or self.rdco).get(QUEUE_URL)

    def rows(self, user=None):
        response = self.queue(user)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data["comments"]

    def remove(self, user, comment_id, reason="Personal attack on another reader."):
        return self.as_(user).post(remove_url(comment_id), {"reason": reason}, format="json")

    def dismiss(self, user, comment_id):
        return self.as_(user).post(dismiss_url(comment_id), {}, format="json")

    def shown(self, comment_id, user=None):
        return next(c for c in self.thread(user)["comments"] if c["id"] == comment_id)


# --- AC: reporting ---------------------------------------------------------------

class ReportingTests(ReportTestBase):

    def test_report_is_offered_on_someone_else_s_comment_and_never_on_your_own(self):
        made = self.posted(self.ana)

        self.assertTrue(self.shown(made["id"], self.ben)["can_report"])
        self.assertFalse(self.shown(made["id"], self.ana)["can_report"])

    def test_a_reader_reports_and_the_report_keeps_the_text_as_it_was(self):
        made = self.posted(self.ana, "Buy cheap followers at example.test")

        self.reported(self.ben, made["id"], "spam")
        self.edit(self.ana, made["id"], "Sorry, wrong thread.")

        report = CommentReport.objects.get()
        self.assertEqual((report.reporter, report.reason, report.state),
                         (self.ben, "spam", CommentReportState.OPEN))
        self.assertEqual(report.reported_text, "Buy cheap followers at example.test")

    def test_a_reader_cannot_report_their_own_comment(self):
        made = self.posted(self.ana)

        response = self.report(self.ana, made["id"])

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(CommentReport.objects.exists())

    def test_report_is_no_longer_offered_once_you_have_reported(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])

        self.assertFalse(self.shown(made["id"], self.ben)["can_report"])
        self.assertTrue(self.shown(made["id"], self.owner)["can_report"])

    def test_reporting_twice_succeeds_and_keeps_one_report(self):
        made = self.posted(self.ana)

        self.reported(self.ben, made["id"], "spam")
        self.reported(self.ben, made["id"], "harassment")

        self.assertEqual(list(CommentReport.objects.values_list("reason", flat=True)), ["spam"])

    def test_other_needs_a_note_and_an_unknown_reason_is_refused(self):
        made = self.posted(self.ana)

        for reason, note in (("other", None), ("other", "   "), ("rude", None), ("other", "x" * 501)):
            with self.subTest(reason=reason, note=note):
                self.assertEqual(self.report(self.ben, made["id"], reason, note).status_code,
                                 status.HTTP_400_BAD_REQUEST)
        self.reported(self.ben, made["id"], "other", "Shares a classmate's phone number.")
        self.assertEqual(CommentReport.objects.get().note, "Shares a classmate's phone number.")

    def test_a_deleted_comment_cannot_be_reported(self):
        made = self.posted(self.ana)
        self.delete(self.ana, made["id"])

        self.assertEqual(self.report(self.ben, made["id"]).status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_paper_that_is_not_published_answers_like_a_hidden_record(self):
        made = self.posted(self.ana)
        self.paper.pipeline_status = PipelineStatus.IN_REVIEW
        self.paper.save(update_fields=["pipeline_status"])

        self.assertEqual(self.report(self.ben, made["id"]).status_code, status.HTTP_404_NOT_FOUND)

    def test_rdco_hears_of_a_comment_s_first_report_and_nobody_else_hears_of_any(self):
        made = self.posted(self.ana)
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            self.reported(self.ben, made["id"])
            self.reported(self.owner, made["id"])

        told = Notification.objects.exclude(pk__in=before)
        self.assertEqual(told.count(), 1)
        notice = told.get()
        self.assertEqual(notice.broadcast_to_role.name, RoleName.RDCO)
        self.assertEqual((notice.task_kind, notice.task_id), ("comment_report", made["id"]))
        self.assertIn("Solar dryers for rural farms", notice.message)
        # A notice names its sender to every RDCO account; a report's must not (review, 2026-11-15).
        self.assertIsNone(notice.sender)

    def test_the_thread_never_says_a_comment_was_reported(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])

        for user in (self.ana, self.owner, self.ben):
            with self.subTest(user=user.email):
                self.assertNotIn("report", str(self.shown(made["id"], user)).replace("can_report", ""))

    def test_reporting_spends_the_posting_budget(self):
        from apps.records.public_comments import CommentPostBurstThrottle

        made = self.posted(self.ana)
        other = self.posted(self.owner, "Another comment.")
        rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "public_comment_burst": "2/minute"}
        with mock.patch.object(CommentPostBurstThrottle, "THROTTLE_RATES", rates):
            self.posted(self.ben, "One.")
            self.reported(self.ben, made["id"])
            self.assertEqual(self.report(self.ben, other["id"]).status_code, status.HTTP_429_TOO_MANY_REQUESTS)


# --- AC: the queue ---------------------------------------------------------------

class QueueTests(ReportTestBase):

    def test_rdco_and_the_system_admin_read_it_and_nobody_else_does(self):
        for user in (self.rdco, self.sysadmin):
            with self.subTest(user=user.email):
                self.assertEqual(self.queue(user).status_code, status.HTTP_200_OK)
        for user in (self.ana, self.owner, self.itso):
            with self.subTest(user=user.email):
                self.assertEqual(self.queue(user).status_code, status.HTTP_403_FORBIDDEN)

    def test_a_row_says_what_was_reported_where_why_and_how_often(self):
        made = self.posted(self.ana, "Original wording.")
        self.reported(self.ben, made["id"], "spam")
        self.reported(self.owner, made["id"], "other", "It names a student.")
        self.edit(self.ana, made["id"], "Edited wording.")

        [row] = self.rows()

        self.assertEqual(row["id"], made["id"])
        self.assertEqual(row["record"], {"id": self.paper.pk, "title": "Solar dryers for rural farms"})
        self.assertEqual(row["author_name"], "Ana Cruz")
        self.assertEqual(row["reported_texts"], ["Original wording."])
        self.assertEqual(row["current_text"], "Edited wording.")
        self.assertIsNone(row["deletion_kind"])
        self.assertEqual(row["report_count"], 2)
        self.assertEqual(row["reasons"], [{"reason": "spam", "count": 1}, {"reason": "other", "count": 1}])
        self.assertEqual(row["notes"], ["It names a student."])
        self.assertIn("first_reported_at", row)
        # Who reported stays with the reports: the queue never names them.
        self.assertNotIn("Ben", str(row))

    def test_newest_report_first_and_only_open_reports(self):
        first = self.posted(self.ana, "First.")
        second = self.posted(self.owner, "Second.")
        handled = self.posted(self.owner, "Handled.")
        self.reported(self.ben, first["id"])
        self.reported(self.ben, handled["id"])
        self.reported(self.ben, second["id"])
        self.dismiss(self.rdco, handled["id"])

        self.assertEqual([r["id"] for r in self.rows()], [second["id"], first["id"]])


# --- AC: removal -----------------------------------------------------------------

class RemovalTests(ReportTestBase):

    def test_rdco_removes_a_reported_comment_with_a_reason(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])
        self.posted(self.ben, "A reply.", reply_to=made["id"])

        response = self.remove(self.rdco, made["id"], "Harasses another reader.")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, getattr(response, "data", None))
        shown = self.shown(made["id"])
        self.assertEqual((shown["deletion_kind"], shown["body"], shown["author_name"]),
                         (CommentDeletion.MODERATOR, None, None))
        comment = PublicComment.objects.get(pk=made["id"])
        self.assertEqual((comment.deleted_by, comment.removal_reason), (self.rdco, "Harasses another reader."))
        report = CommentReport.objects.get()
        self.assertEqual((report.state, report.resolved_by), (CommentReportState.REMOVED, self.rdco))
        self.assertEqual(self.rows(), [])

    def test_the_writer_is_told_why_and_the_reporter_is_not(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            self.remove(self.rdco, made["id"], "Shares personal data.")

        told = Notification.objects.exclude(pk__in=before)
        self.assertEqual([n.recipient for n in told], [self.ana])
        self.assertIn("Shares personal data.", told.get().message)

    def test_the_system_admin_removes_a_comment_nobody_reported(self):
        made = self.posted(self.ana)

        self.assertEqual(self.remove(self.sysadmin, made["id"]).status_code, status.HTTP_204_NO_CONTENT)
        # With no replies, a removed comment leaves no marker.
        self.assertEqual(self.thread()["comments"], [])
        self.assertEqual(PublicComment.objects.get(pk=made["id"]).deletion_kind, CommentDeletion.MODERATOR)

    def test_remove_is_offered_to_rdco_and_the_system_admin_only(self):
        made = self.posted(self.ana)
        self.posted(self.ben, "A reply keeps the marker.", reply_to=made["id"])

        for user, offered in ((self.rdco, True), (self.sysadmin, True), (self.ana, False),
                              (self.owner, False), (self.itso, False)):
            with self.subTest(user=user.email):
                self.assertIs(self.shown(made["id"], user)["can_remove"], offered)
        self.remove(self.rdco, made["id"])
        self.assertFalse(self.shown(made["id"], self.rdco)["can_remove"])

    def test_a_reason_is_required(self):
        made = self.posted(self.ana)

        for reason in ("", "   "):
            with self.subTest(reason=reason):
                self.assertEqual(self.remove(self.rdco, made["id"], reason).status_code,
                                 status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(PublicComment.objects.get(pk=made["id"]).deletion_kind)

    def test_nobody_else_removes(self):
        made = self.posted(self.ana)

        for user in (self.ana, self.owner, self.itso):
            with self.subTest(user=user.email):
                self.assertEqual(self.remove(user, made["id"]).status_code, status.HTTP_403_FORBIDDEN)
        self.assertIsNone(PublicComment.objects.get(pk=made["id"]).deletion_kind)

    def test_the_second_moderator_is_told_it_is_already_handled(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])
        self.remove(self.rdco, made["id"], "First reason.")

        for act in (lambda: self.remove(self.sysadmin, made["id"], "Second reason."),
                    lambda: self.dismiss(self.sysadmin, made["id"])):
            response = act()
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertIn("already", response.data["detail"])
        self.assertEqual(PublicComment.objects.get(pk=made["id"]).removal_reason, "First reason.")

    def test_a_comment_that_does_not_exist_is_a_404(self):
        self.assertEqual(self.remove(self.rdco, 10_000_000).status_code, status.HTTP_404_NOT_FOUND)

    def test_removal_is_audited_without_the_comment_s_text(self):
        made = self.posted(self.ana, "Something unkind.")
        self.reported(self.ben, made["id"])

        self.remove(self.rdco, made["id"], "Unkind to a reader.")

        event = AuditEvent.objects.get(event_type=AuditEvent.COMMENT_REMOVED)
        self.assertEqual((event.user, event.record_id), (self.rdco, self.paper.pk))
        self.assertEqual(event.metadata, {"comment": made["id"], "reason": "Unkind to a reader.",
                                          "reports_closed": 1})


# --- AC: dismissal ---------------------------------------------------------------

class DismissalTests(ReportTestBase):

    def test_dismiss_closes_the_reports_and_leaves_the_comment(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])
        self.reported(self.owner, made["id"])

        response = self.dismiss(self.sysadmin, made["id"])

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(set(CommentReport.objects.values_list("state", flat=True)), {CommentReportState.DISMISSED})
        self.assertIsNone(self.shown(made["id"])["deletion_kind"])
        self.assertEqual(self.rows(), [])
        event = AuditEvent.objects.get(event_type=AuditEvent.COMMENT_REPORTS_DISMISSED)
        self.assertEqual(event.metadata, {"comment": made["id"], "reports_closed": 2})

    def test_a_comment_with_no_open_report_is_already_handled(self):
        made = self.posted(self.ana)

        self.assertEqual(self.dismiss(self.rdco, made["id"]).status_code, status.HTTP_409_CONFLICT)

    def test_nobody_else_dismisses(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])

        self.assertEqual(self.dismiss(self.owner, made["id"]).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(CommentReport.objects.get().state, CommentReportState.OPEN)


# --- decision 2026-11-15: what the writer's own changes do ----------------------

class WriterChangesTests(ReportTestBase):

    def test_the_writer_deleting_closes_its_open_reports(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])

        self.delete(self.ana, made["id"])

        self.assertEqual(CommentReport.objects.get().state, CommentReportState.WRITER_DELETED)
        self.assertEqual(self.rows(), [])

    def test_an_edit_leaves_the_report_open(self):
        made = self.posted(self.ana)
        self.reported(self.ben, made["id"])

        self.edit(self.ana, made["id"], "Reworded.")

        self.assertEqual(CommentReport.objects.get().state, CommentReportState.OPEN)


# --- ADR-069: the notice settles when its reports are handled --------------------

class NoticeSettlesTests(ReportTestBase):

    def test_rdco_s_notice_says_how_the_reports_ended(self):
        from apps.notifications.settling import settle

        made = self.posted(self.ana)
        with self.captureOnCommitCallbacks(execute=True):
            self.reported(self.ben, made["id"])
        notice = Notification.objects.get(task_kind="comment_report")
        self.assertEqual(settle(Notification.objects.filter(pk=notice.pk)), 0)

        self.remove(self.rdco, made["id"])

        settle(Notification.objects.filter(pk=notice.pk))
        notice.refresh_from_db()
        self.assertTrue(notice.resolved_label.startswith("Removed on "))


# --- decision 2026-11-15: the sidebar's count ------------------------------------

class QueueCountTests(ReportTestBase):

    def counts(self, user):
        return self.as_(user).get(reverse("dashboard-queue-counts"))

    def test_both_moderators_see_how_many_comments_wait(self):
        first = self.posted(self.ana)
        second = self.posted(self.owner, "Second.")
        self.reported(self.ben, first["id"])
        self.reported(self.owner, first["id"])
        self.reported(self.ben, second["id"])

        self.assertEqual(self.counts(self.rdco).data["reported_comments"], 2)
        # The System Admin's sidebar has this queue alone, so it reads this count alone.
        self.assertEqual(self.counts(self.sysadmin).data, {"reported_comments": 2})

    def test_anyone_else_is_still_refused(self):
        self.assertEqual(self.counts(self.itso).status_code, status.HTTP_403_FORBIDDEN)


class OnAnotherPaperTests(ReportTestBase):

    def test_a_comment_reported_through_another_paper_s_address_is_a_404(self):
        made = self.posted(self.ana)
        other = make_paper(self.owner, title="Another paper")

        self.assertEqual(self.report(self.ben, made["id"], record=other).status_code, status.HTTP_404_NOT_FOUND)


# --- "A paper that stops being public takes its comments with it" -----------------

class PaperLeavesPublicTests(ReportTestBase):

    def setUp(self):
        super().setUp()
        self.made = self.posted(self.ana)
        self.reported(self.ben, self.made["id"])
        self.paper.pipeline_status = PipelineStatus.IN_REVIEW
        self.paper.save(update_fields=["pipeline_status"])

    def test_its_reported_comments_leave_the_queue_and_the_count(self):
        for user in (self.rdco, self.sysadmin):
            with self.subTest(user=user.email):
                self.assertEqual(self.rows(user), [])
                counts = self.as_(user).get(reverse("dashboard-queue-counts")).data
                self.assertEqual(counts["reported_comments"], 0)

    def test_its_comments_cannot_be_removed_or_dismissed(self):
        for user in (self.rdco, self.sysadmin):
            with self.subTest(user=user.email):
                self.assertEqual(self.remove(user, self.made["id"]).status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(self.dismiss(user, self.made["id"]).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(CommentReport.objects.get().state, CommentReportState.OPEN)

    def test_they_come_back_when_the_paper_is_public_again(self):
        self.paper.pipeline_status = PipelineStatus.PUBLISHED
        self.paper.save(update_fields=["pipeline_status"])

        self.assertEqual([row["id"] for row in self.rows()], [self.made["id"]])
