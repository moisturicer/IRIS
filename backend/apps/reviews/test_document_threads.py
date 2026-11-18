"""
A review thread on a supporting document (ADR-032 §7, Amendment 2026-11-18; IR-1204).

A reviewer may open a thread on one upload of a slot document, as a whole,
never a passage. It is a thread in every other respect: it blocks what a
manuscript thread blocks, is answered and closed the same way, goes in the
response letter labelled with its document, and keeps its upload from being
deleted. Pinned at the REST seam (ADR-032 §12), one class per point.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.urls import reverse
from rest_framework import status

from apps.documents.models import RecordUpload
from core.enums import Party, ThreadState

from .models import ReviewComment
from .test_review_threads import ANCHOR, FIX, ThreadTestBase
from .test_version_documents import VersionDocumentsTestBase


def letters_url(record):
    return reverse("record-response-letters", args=[record.pk])


def when(day):
    return datetime(2027, 3, day, 12, tzinfo=ZoneInfo("Asia/Manila"))


class DocumentThreadTestBase(ThreadTestBase, VersionDocumentsTestBase):

    def consent(self, record, uploads=1):
        """The record's Consent form slot with `uploads` versions; the newest is returned."""
        slot = self.slot(record, "Consent form")
        latest = None
        for day in range(1, uploads + 1):
            latest = self.upload(record, slot, when(day))
        return latest

    def on_document(self, record, as_user, upload, body="The consent form isn't signed.", **extra):
        return self.comment(record, as_user, body, document=upload.pk, **extra)

    def document_thread(self, record, as_user, upload, body="The consent form isn't signed.", **extra):
        response = self.on_document(record, as_user, upload, body, **extra)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data


# --- point 1: a thread may name one document upload, as a whole ---------------------

class AThreadOnADocumentTests(DocumentThreadTestBase):

    def test_a_reviewer_opens_one_and_it_names_the_upload_by_slot_and_version(self):
        record = self.at_adviser_open()
        upload = self.consent(record)

        made = self.document_thread(record, self.adviser, upload, severity=FIX, post_now=True)

        self.assertEqual(made["document"], {
            "upload": upload.pk, "slot": "Consent form", "version": 1,
            "label": "Consent form, v1", "earlier": False, "extension": "pdf",
        })
        self.assertIsNone(made["anchor"])
        self.assertEqual(made["severity"], FIX)
        self.assertEqual(made["kind"], "thread")
        listed = next(c for c in self.listed(record, self.owner).data if c["id"] == made["id"])
        self.assertEqual(listed["document"]["label"], "Consent form, v1")

    def test_posting_one_tells_the_authors_which_document(self):
        from apps.notifications.models import Notification

        record = self.itso_open()
        upload = self.consent(record)

        with self.captureOnCommitCallbacks(execute=True):
            self.document_thread(record, self.itso, upload, severity=FIX, post_now=True)

        [notice] = Notification.objects.filter(record=record, notif_type__name="Review Thread Posted")
        self.assertEqual(notice.recipient, self.owner)
        self.assertEqual(notice.message, f'ITSO posted a Must fix on Consent form, v1 of "{record.title}".')

    def test_a_general_or_passage_thread_names_no_document(self):
        record = self.at_adviser_open()

        made = self.thread(record, self.adviser, "Consider a figure.")

        self.assertIsNone(made["document"])

    def test_it_is_a_draft_until_sent_like_any_reviewer_s_thread(self):
        record = self.at_adviser_open()

        made = self.document_thread(record, self.adviser, self.consent(record))

        self.assertTrue(made["is_draft"])
        self.assertNotIn(made["id"], self.ids(record, self.owner))

    def test_an_owner_does_not_open_one(self):
        record = self.at_adviser_open()

        response = self.on_document(record, self.owner, self.consent(record))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ReviewComment.objects.filter(record=record, anchor_upload__isnull=False).exists())

    def test_another_record_s_upload_is_refused_as_if_missing(self):
        record = self.at_adviser_open()
        other = self.make_record()

        response = self.on_document(record, self.adviser, self.consent(other))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not one of this record's documents", response.data["detail"])

    def test_an_upload_that_does_not_exist_is_refused(self):
        record = self.at_adviser_open()

        response = self.comment(record, self.adviser, "Signed?", document=999999)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_the_newest_upload_of_its_document_takes_a_new_thread(self):
        # Decided 2026-11-18: a new thread is never born "from an earlier upload".
        record = self.at_adviser_open()
        newest = self.consent(record, uploads=2)
        first = RecordUpload.objects.get(record=record, slot=newest.slot, version=1)

        response = self.on_document(record, self.adviser, first)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("newest upload", response.data["detail"])
        self.assertEqual(self.on_document(record, self.adviser, newest).status_code, status.HTTP_201_CREATED)

    def test_it_names_a_document_or_a_passage_never_both_and_suggests_no_wording(self):
        record = self.at_adviser_open()
        upload = self.consent(record)

        for extra in ({"anchor": ANCHOR}, {"suggestion": "Signed by the participant."}):
            with self.subTest(extra=list(extra)):
                response = self.on_document(record, self.adviser, upload, **extra)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_reply_or_a_conversation_comment_names_no_document(self):
        record = self.at_adviser_open()
        upload = self.consent(record)
        made = self.document_thread(record, self.adviser, upload, post_now=True)

        reply = self.on_document(record, self.owner, upload, "Uploading it now.", reply_to=made["id"])
        talk = self.comment(record, self.adviser, "Thanks.", kind="discussion", document=upload.pk)

        self.assertEqual(reply.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(talk.status_code, status.HTTP_400_BAD_REQUEST)


# --- point 5: a newer upload does not move it ----------------------------------------

class ANewerUploadTests(DocumentThreadTestBase):

    def test_the_thread_stays_on_its_upload_and_reads_from_an_earlier_upload(self):
        record = self.at_adviser_open()
        first = self.consent(record)
        made = self.document_thread(record, self.adviser, first, post_now=True)

        self.upload(record, first.slot, when(9))

        listed = next(c for c in self.listed(record, self.owner).data if c["id"] == made["id"])
        self.assertEqual(
            {k: listed["document"][k] for k in ("upload", "label", "earlier")},
            {"upload": first.pk, "label": "Consent form, v1", "earlier": True},
        )
        self.assertEqual(listed["state"], ThreadState.OPEN)


# --- point 6: it blocks what a manuscript thread blocks -------------------------------

class WhatItBlocksTests(DocumentThreadTestBase):

    def test_its_party_s_open_must_fix_blocks_the_clear_and_is_counted(self):
        record = self.itso_open()
        self.document_thread(record, self.itso, self.consent(record), severity=FIX)
        self.sent(record, self.itso)

        clear = self.review(record, self.itso)

        self.assertEqual(clear.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ITSO has 1 open Must fix thread", clear.data["detail"])
        self.assertEqual(len(self.thread_items(record, self.itso)), 1)

    def test_the_next_version_waits_for_an_answer_which_goes_in_the_letter(self):
        record = self.itso_open()
        made = self.document_thread(record, self.itso, self.consent(record), severity=FIX)
        self.sent(record, self.itso, "request_revision", summary="Sign the consent form.")
        self.edit_title(record)

        refused = self.submit_version(record)
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("1 thread from ITSO", refused.data["detail"])

        self.assertEqual(self.answer(record, made["id"], note="Signed copy uploaded.").status_code, 200)
        self.submitted(record)

        self.client.force_authenticate(self.itso)
        letter = self.client.get(letters_url(record)).data[0]
        entry = next(e for e in letter["entries"] if e["thread"] == made["id"])
        self.assertEqual(entry["document"], "Consent form, v1")
        self.assertEqual((entry["answer"], entry["note"]), ("addressed", "Signed copy uploaded."))
        self.assertIsNone(entry["page"])

    def test_a_decision_closes_it_with_its_reason(self):
        record = self.at_adviser_open()
        made = self.document_thread(record, self.adviser, self.consent(record), severity=FIX)
        self.sent(record, self.adviser)

        self.decided(record, self.adviser, "reject", "Out of scope for this programme.")

        thread = ReviewComment.objects.get(pk=made["id"])
        self.assertEqual(thread.state, ThreadState.CLOSED)
        self.assertEqual(thread.closed_reason, "Out of scope for this programme.")


# --- point 10: an upload with a thread is kept -----------------------------------------

class AnUploadWithAThreadIsKeptTests(DocumentThreadTestBase):

    def test_nobody_deletes_it_while_a_thread_names_it_even_a_draft(self):
        from apps.documents.serializers import RecordUploadSerializer

        record = self.at_adviser_open()
        # Uploaded after v1 was submitted, so no Version keeps it: only the thread will.
        upload = self.consent(record)
        self.assertIsNone(RecordUploadSerializer(upload).data["delete_refused"])
        self.document_thread(record, self.adviser, upload)
        self.assertIn("A review thread is about this file", RecordUploadSerializer(upload).data["delete_refused"])

        for user in (self.owner, self.rdco):
            with self.subTest(user=user.email):
                response = self.delete(upload, user)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("A review thread is about this file", response.data["detail"])
        self.assertTrue(RecordUpload.objects.filter(pk=upload.pk).exists())

    def test_the_database_refuses_too_but_a_record_s_own_delete_still_cascades(self):
        from django.db.models import RestrictedError

        from apps.records.models import Record

        record = self.at_adviser_open()
        upload = self.consent(record)
        self.document_thread(record, self.adviser, upload)

        with self.assertRaises(RestrictedError):
            RecordUpload.objects.filter(pk=upload.pk).delete()
        Record.objects.filter(pk=record.pk).delete()
        self.assertFalse(RecordUpload.objects.filter(pk=upload.pk).exists())
