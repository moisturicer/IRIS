"""
IR-1287 (ADR-073 decision 3, amended): the paper page's tracker, timeline and
documents update live.

A workflow or document write on a record publishes `record:<id>` on commit to
the own channel of everyone `may_read_review` admits, once per transaction, and
to no one else. An unsubmitted draft is its creator's alone (IR-1227), so a
co-owner it names hears nothing. Pinned through a recorder: CI has no Redis.
"""
from collections import Counter

from apps.documents.models import RecordFile
from apps.live import channels as ch
from apps.live.publish import use_publisher
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.test_review_threads import ThreadTestBase
from apps.tests.test_authorization_matrix import make_user
from core.enums import Party, PipelineStatus

from .test_live import Recorder


class PaperHintTests(ThreadTestBase):

    def sends(self, record, write):
        """How often each channel was told exactly `record:<id>` while `write` committed."""
        recorder = Recorder()
        with use_publisher(recorder), self.captureOnCommitCallbacks(execute=True):
            write()
        topic = ch.record_topic(record.pk)
        return Counter(channel for channel, topics in recorder.sent if topics == [topic])

    def channel(self, user):
        return ch.user_channel(user.pk)

    def attach(self, record, user, name="consent-form.pdf"):
        return RecordFile.objects.create(record=record, uploaded_by=user, file="x.pdf", filename=name)

    def test_a_file_added_tells_the_review_s_readers_and_nobody_else(self):
        record = self.at_adviser_open()
        sent = self.sends(record, lambda: self.attach(record, self.owner))
        self.assertEqual(sent[self.channel(self.owner)], 1)
        self.assertEqual(sent[self.channel(self.adviser)], 1)
        for outsider in (self.stranger, self.itso):
            self.assertNotIn(self.channel(outsider), sent)
        self.assertFalse([c for c in sent if c.startswith(ch.PREFIX + "role:")])

    def test_a_file_removed_tells_them_too(self):
        record = self.at_adviser_open()
        attached = self.attach(record, self.owner)
        sent = self.sends(record, attached.delete)
        self.assertEqual(sent[self.channel(self.owner)], 1)

    def test_routing_tells_each_reader_once_however_many_rows_it_writes(self):
        record = self.new_model()
        sent = self.sends(record, lambda: self.accepted_to(record, Party.ITSO))
        self.assertTrue(sent, "routing told nobody")
        self.assertEqual(sent[self.channel(self.owner)], 1)
        for member in (self.itso, self.itso2):
            self.assertEqual(sent[self.channel(member)], 1, member.email)
        self.assertNotIn(self.channel(self.stranger), sent)
        self.assertTrue(all(count == 1 for count in sent.values()), sent)

    def test_an_unsubmitted_draft_tells_its_creator_only(self):
        creator = make_user("live-draft-creator@cit.edu", "Student")
        co_owner = make_user("live-draft-coowner@cit.edu", "Student")
        kind = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        draft = Record.objects.create(
            title="Live draft", record_type=kind, added_by=creator,
            pipeline_status=PipelineStatus.DRAFT,
        )
        RecordOwner.objects.create(record=draft, user=creator, is_primary=True)
        RecordOwner.objects.create(record=draft, user=co_owner)

        sent = self.sends(draft, lambda: self.attach(draft, creator))

        self.assertNotIn(self.channel(co_owner), sent)
        self.assertLessEqual(set(sent), {self.channel(creator)})
