"""
IR-1350 (ADR-073 amendment 2026-11-28): the two remaining staff queues are live.

- A comment reported, or its reports closed (dismissed, removed by a moderator,
  deleted by its writer), tells RDCO and the System Admin `queues`, the two
  roles that share the Reported comments queue (IR-693), and nobody else.
- An account deletion asked, cancelled, confirmed or rejected tells the
  System Admin `queues`, and nobody else.

Through a recorder: CI has no Redis.
"""
from django.test import TestCase

from apps.accounts.deletion import service as deletion
from apps.accounts.models import AccountDeletionRequest
from apps.live import channels as ch
from apps.live.publish import use_publisher
from apps.records import comment_moderation, public_comments
from apps.records.models import PublicComment
from apps.records.test_public_comments import make_paper, make_user
from core.enums import RoleName

from .test_live import Recorder

MODERATORS = sorted([ch.role_channel(RoleName.RDCO), ch.role_channel(RoleName.SYSTEM_ADMIN)])
SYSTEM_ADMIN = [ch.role_channel(RoleName.SYSTEM_ADMIN)]


class HintTestBase(TestCase):
    def told(self, write):
        """The channels told `queues` while `write` ran and committed, each once."""
        recorder = Recorder()
        with use_publisher(recorder), self.captureOnCommitCallbacks(execute=True):
            write()
        return sorted({channel for channel, topics in recorder.sent if ch.QUEUES in topics})


class ReportedCommentHintTests(HintTestBase):
    def setUp(self):
        self.owner = make_user("live-mod-owner@cit.edu")
        self.writer = make_user("live-mod-writer@cit.edu")
        self.reader = make_user("live-mod-reader@cit.edu")
        self.rdco = make_user("live-mod-rdco@cit.edu", RoleName.RDCO)
        self.admin = make_user("live-mod-admin@cit.edu", RoleName.SYSTEM_ADMIN)
        self.paper = make_paper(self.owner)
        self.comment = PublicComment.objects.create(
            record=self.paper, author=self.writer, body="Did you test this in the rainy season?",
        )

    def reported(self):
        public_comments.report(self.paper, self.reader, self.comment.pk, reason="spam")

    def test_reporting_tells_both_moderator_roles_only(self):
        self.assertEqual(self.told(self.reported), MODERATORS)

    def test_dismissing_tells_both_moderator_roles_only(self):
        self.reported()
        told = self.told(lambda: comment_moderation.dismiss(self.rdco, self.comment.pk))
        self.assertEqual(told, MODERATORS)

    def test_removing_tells_both_moderator_roles_only(self):
        self.reported()
        told = self.told(lambda: comment_moderation.remove(
            self.admin, self.comment.pk, reason="Personal attack on another reader.",
        ))
        self.assertEqual(told, MODERATORS)

    def test_the_writer_deleting_a_reported_comment_tells_both_moderator_roles(self):
        self.reported()
        told = self.told(lambda: public_comments.delete(self.paper, self.writer, self.comment.pk))
        self.assertEqual(told, MODERATORS)

    def test_deleting_an_unreported_comment_tells_nobody(self):
        told = self.told(lambda: public_comments.delete(self.paper, self.writer, self.comment.pk))
        self.assertEqual(told, [])


class AccountDeletionHintTests(HintTestBase):
    def setUp(self):
        self.person = make_user("live-del-person@cit.edu")
        self.admin = make_user("live-del-admin@cit.edu", RoleName.SYSTEM_ADMIN)

    def asked(self) -> AccountDeletionRequest:
        return deletion.request_deletion(self.person)

    def test_asking_tells_the_system_admin_only(self):
        self.assertEqual(self.told(self.asked), SYSTEM_ADMIN)

    def test_cancelling_tells_the_system_admin_only(self):
        self.asked()
        self.assertEqual(self.told(lambda: deletion.cancel_deletion(self.person)), SYSTEM_ADMIN)

    def test_rejecting_tells_the_system_admin_only(self):
        request = self.asked()
        told = self.told(lambda: deletion.reject_deletion(request.pk, self.admin, "Papers still in review."))
        self.assertEqual(told, SYSTEM_ADMIN)

    def test_confirming_tells_the_system_admin_only(self):
        request = self.asked()
        told = self.told(lambda: deletion.confirm_deletion(request.pk, self.admin))
        self.assertEqual(told, SYSTEM_ADMIN)
