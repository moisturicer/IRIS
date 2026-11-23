"""
IR-1284 (ADR-073 decision 3, amended): the review discussion updates live.

A change to a review comment publishes `record:<id>` on commit to the own
channel of everyone `may_read_review` admits, and to no one else -- an ITSO
member with no part in the record, a stranger, or a role channel. A draft is
its writer's alone, so a draft's change is told to its writer only. The bulk
writes that send no signal (Finish review, a Decision) still tell the readers.
Pinned at the REST seam, through a recorder: CI has no Redis.
"""
from apps.live import channels as ch
from apps.live.publish import use_publisher
from apps.reviews.models import ReviewComment
from apps.reviews.test_review_comments import comment_url
from apps.reviews.test_review_threads import FIX, ThreadTestBase
from core.enums import Party

from .test_live import Recorder


class ReviewHintTests(ThreadTestBase):

    def hinted(self, record, write):
        """The channels told `record:<id>` while `write` ran and committed."""
        recorder = Recorder()
        with use_publisher(recorder), self.captureOnCommitCallbacks(execute=True):
            write()
        topic = ch.record_topic(record.pk)
        return {channel for channel, topics in recorder.sent if topic in topics}

    def channels(self, *users):
        return {ch.user_channel(u.pk) for u in users}

    def assert_only_readers(self, told, readers, outsiders):
        self.assertTrue(self.channels(*readers) <= told, told)
        self.assertFalse(self.channels(*outsiders) & told, told)
        self.assertFalse({c for c in told if c.startswith(ch.PREFIX + "role:")}, told)

    # --- who is told ---------------------------------------------------------------

    def test_a_conversation_comment_tells_every_reader_and_nobody_else(self):
        record = self.at_adviser_open()
        told = self.hinted(record, lambda: self.discussed(record, self.owner, "Is chapter 2 enough?"))
        self.assert_only_readers(told, [self.owner, self.adviser], [self.stranger, self.itso])

    def test_a_reply_tells_the_owner(self):
        record = self.at_adviser_open()
        asked = self.discussed(record, self.owner, "Is chapter 2 enough?")
        told = self.hinted(record, lambda: self.discussed(
            record, self.adviser, "Add the survey.", reply_to=asked["id"]))
        self.assert_only_readers(told, [self.owner, self.adviser], [self.stranger, self.itso])

    def test_an_office_pool_member_who_reads_the_review_is_told(self):
        record = self.itso_open()
        told = self.hinted(record, lambda: self.discussed(record, self.owner, "Who checks the patent?"))
        self.assert_only_readers(told, [self.owner, self.itso, self.itso2], [self.stranger])

    def test_resolving_and_reopening_tell_the_readers(self):
        record = self.at_adviser_open()
        made = self.must_fix_sent(record, self.adviser)
        for act in ("resolve", "reopen"):
            with self.subTest(act=act):
                told = self.hinted(record, lambda: self.act(record, self.adviser, made["id"], act))
                self.assert_only_readers(told, [self.owner, self.adviser], [self.stranger, self.itso])

    def test_answering_a_thread_tells_its_reviewer(self):
        record = self.at_adviser_open()
        made = self.must_fix_sent(record, self.adviser)
        told = self.hinted(record, lambda: self.answer(record, made["id"]))
        self.assert_only_readers(told, [self.owner, self.adviser], [self.stranger])

    # --- drafts ----------------------------------------------------------------------

    def test_a_draft_is_told_to_its_writer_only(self):
        record = self.itso_open()
        draft = {}
        told = self.hinted(record, lambda: draft.update(self.thread(record, self.itso, "Prior art?")))
        self.assertTrue(draft["is_draft"])
        self.assertEqual(told, self.channels(self.itso))

        def deleted():
            self.client.force_authenticate(self.itso)
            self.client.delete(comment_url(record, draft["id"]))
        self.assertEqual(self.hinted(record, deleted), self.channels(self.itso))

    def test_finishing_a_review_tells_the_readers_its_drafts_reached(self):
        record = self.itso_open()
        self.thread(record, self.itso, "Prior art?", severity=FIX)
        told = self.hinted(record, lambda: self.sent(record, self.itso))
        self.assert_only_readers(told, [self.owner, self.itso, self.itso2], [self.stranger])

    def test_a_decision_closing_threads_tells_the_readers(self):
        record = self.at_rdco()
        ReviewComment.objects.create(
            record=record, author=self.itso, body="Prior art?", party=Party.ITSO, severity=FIX,
        )
        told = self.hinted(record, lambda: self.decided(
            record, self.rdco, "keep_unlisted", "IP is KTTO's to pursue later."))
        self.assert_only_readers(told, [self.owner, self.rdco], [self.stranger])

    # --- what is never sent ------------------------------------------------------------

    def test_a_refused_comment_tells_nobody(self):
        record = self.at_adviser_open()
        self.assertEqual(self.hinted(record, lambda: self.discuss(record, self.stranger, "Hi.")), set())
