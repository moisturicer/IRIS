"""The response to reviewers (ADR-032 §7; IR-876), at the REST seam.

Decided 2026-11-09: the letter is frozen onto the Version when it is
submitted; it holds every open thread of the parties that asked, with
"No answer given" where the owner gave none; and everyone who may read the
review reads the whole letter, their own party's part first."""
from django.urls import reverse
from rest_framework import status

from core.enums import Party, PipelineStatus

from .models import ReviewComment
from .test_review_threads import FIX, SUGGEST, ThreadTestBase


def letters_url(record):
    return reverse("record-response-letters", args=[record.pk])


class LetterTestBase(ThreadTestBase):

    def letters(self, record, as_user):
        self.client.force_authenticate(as_user)
        return self.client.get(letters_url(record))

    def asked_with_two_threads(self):
        """ITSO sends a Must fix and a Suggestion with a Revision request."""
        record = self.itso_open()
        fix = self.thread(record, self.itso, "Redo the prior-art search.", severity=FIX)
        idea = self.thread(record, self.itso, "Consider a diagram.", severity=SUGGEST)
        self.sent(record, self.itso, "request_revision", summary="Redo the search.")
        self.edit_title(record)
        return record, fix["id"], idea["id"]

    def preview(self, record):
        return self.detail(record, self.owner)["revision"]["new_version"]["letter"]


def summary(entries):
    return [(e["thread"], e["severity"], e["answer"], e["note"]) for e in entries]


class AssembledTests(LetterTestBase):

    def test_the_submit_preview_assembles_the_letter_from_the_answers(self):
        record, fix, idea = self.asked_with_two_threads()
        self.assertEqual(summary(self.preview(record)), [
            (fix, FIX, None, ""), (idea, SUGGEST, None, ""),
        ])

        self.answer(record, fix, "addressed", "Section 2, p. 4.")

        entry = self.preview(record)[0]
        self.assertEqual((entry["answer"], entry["note"]), ("addressed", "Section 2, p. 4."))
        self.assertEqual((entry["party"], entry["party_label"], entry["comment"]),
                         (Party.ITSO, "ITSO", "Redo the prior-art search."))

    def test_submitting_freezes_the_letter_onto_the_new_version(self):
        record, fix, idea = self.asked_with_two_threads()
        self.answer(record, fix, "addressed", "Section 2, p. 4.")
        self.submitted(record)

        # A later answer changes the thread, never the letter.
        self.answer(record, fix, "declined", "On reflection, out of scope.")
        body = self.letters(record, self.itso).data

        self.assertEqual([letter["version"] for letter in body], [2])
        self.assertEqual(summary(body[0]["entries"]), [
            (fix, FIX, "addressed", "Section 2, p. 4."), (idea, SUGGEST, None, ""),
        ])

    def test_only_the_requesting_parties_threads_are_in_it(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.must_fix_sent(record, self.itso)
        asked = self.thread(record, self.ierc, "Add the consent form.", severity=FIX)
        self.sent(record, self.ierc, "request_revision", summary="Consent form.")
        self.answer(record, asked["id"], "addressed", "Appendix C.")
        self.edit_title(record)

        self.assertEqual([e["thread"] for e in self.preview(record)], [asked["id"]])

    def test_a_draft_or_a_resolved_thread_is_not_in_it(self):
        record, fix, idea = self.asked_with_two_threads()
        self.act(record, self.itso, idea, "resolve")
        self.thread(record, self.itso, "Draft I haven't sent.", severity=FIX)

        self.assertEqual([e["thread"] for e in self.preview(record)], [fix])


class WhoReadsItTests(LetterTestBase):

    def test_each_reader_sees_the_whole_letter_their_own_party_first(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        itso = self.thread(record, self.itso, "Prior art?", severity=FIX)
        self.sent(record, self.itso, "request_revision", summary="Prior art.")
        ierc = self.thread(record, self.ierc, "Consent?", severity=FIX)
        self.sent(record, self.ierc, "request_revision", summary="Consent.")
        for made in (itso, ierc):
            self.answer(record, made["id"], "addressed", "Done.")
        self.edit_title(record)
        self.submitted(record)

        def order(user):
            return [e["thread"] for e in self.letters(record, user).data[0]["entries"]]

        self.assertEqual(order(self.itso), [itso["id"], ierc["id"]])
        self.assertEqual(order(self.ierc), [ierc["id"], itso["id"]])
        self.assertEqual(sorted(order(self.owner)), sorted([itso["id"], ierc["id"]]))

    def test_anyone_the_review_refuses_gets_a_404(self):
        record, fix, _ = self.asked_with_two_threads()
        self.answer(record, fix, "addressed", "Section 2.")
        self.submitted(record)
        type(record).objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        self.assertEqual(self.letters(record, self.stranger).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_version_answering_no_thread_has_no_letter(self):
        record = self.itso_open()
        self.sent(record, self.itso, "request_revision", summary="Fix the title.")
        self.edit_title(record)
        self.submitted(record)

        self.assertEqual(self.letters(record, self.owner).data, [])
        self.assertFalse(ReviewComment.objects.filter(record=record).exists())
