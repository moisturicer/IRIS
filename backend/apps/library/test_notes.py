"""
IR-580 at the notes API seam (ADR-064).

What this pins:

* a note is owner-only: staff, the Record's owners, an administrator and other
  readers never read, change or delete it;
* every call rechecks `visible_to()`, so an unreadable Record answers the same
  404 as a missing one, and the text is kept and comes back with access;
* a write carries the revision it was based on, and a stale one is refused with
  the server's text and writes nothing -- there is no last-writer-wins;
* the body is capped, and a refused write stores nothing;
* nothing that recommends, discusses or reviews imports the note model.
"""

import pathlib
import re

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.accounts.models import Role, User
from apps.records.models import Record
from core.enums import PipelineStatus, RoleName

from .models import MAX_NOTE_LENGTH, ReadingNote
from .tests import LibraryTestCase

NOTES = "/api/v1/library/notes/"


def note_url(record_or_id):
    return f"{NOTES}{getattr(record_or_id, 'id', record_or_id)}/"


class NoteTestCase(LibraryTestCase):
    def write(self, record, body, base_revision=0, client=None):
        return (client or self.client).put(
            note_url(record), {"body": body, "base_revision": base_revision}, format="json",
        )

    def person(self, email, role_name):
        role = Role.objects.get_or_create(name=role_name)[0]
        return User.objects.create_user(
            email=email, password="TestPass123!", first_name="N", last_name="P", role=role,
        )


class ReadAndWriteTests(NoteTestCase):
    def test_a_record_with_no_note_reads_empty_and_creates_nothing(self):
        record = self.record()

        response = self.client.get(note_url(record))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["body"], "")
        self.assertEqual(response.data["revision"], 0)
        self.assertIsNone(response.data["updated_at"])
        self.assertFalse(ReadingNote.objects.exists())

    def test_the_first_save_is_revision_one_and_each_save_adds_one(self):
        record = self.record()

        first = self.write(record, "Method looks thin.", base_revision=0)
        second = self.write(record, "Method looks thin. Check n.", base_revision=1)

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual((first.data["revision"], second.data["revision"]), (1, 2))
        note = ReadingNote.objects.get(owner=self.reader, record=record)
        self.assertEqual((note.body, note.revision), ("Method looks thin. Check n.", 2))
        self.assertEqual(self.client.get(note_url(record)).data["body"], "Method looks thin. Check n.")

    def test_an_empty_body_is_stored_and_keeps_its_revision_chain(self):
        record = self.record()
        self.write(record, "something", base_revision=0)

        cleared = self.write(record, "", base_revision=1)

        self.assertEqual((cleared.status_code, cleared.data["revision"]), (200, 2))
        self.assertTrue(ReadingNote.objects.filter(owner=self.reader, record=record, body="").exists())

    def test_the_body_may_be_exactly_the_cap_and_no_longer(self):
        record = self.record()

        at_cap = self.write(record, "a" * MAX_NOTE_LENGTH, base_revision=0)
        over = self.write(record, "a" * (MAX_NOTE_LENGTH + 1), base_revision=1)

        self.assertEqual(at_cap.status_code, 200)
        self.assertEqual(over.status_code, 400)
        self.assertEqual(len(ReadingNote.objects.get(owner=self.reader, record=record).body), MAX_NOTE_LENGTH)
        self.assertEqual(ReadingNote.objects.get(owner=self.reader, record=record).revision, 1)

    def test_a_body_that_is_not_text_or_a_missing_revision_is_refused_and_writes_nothing(self):
        record = self.record()

        for payload in (
            {"base_revision": 0},
            {"body": 5, "base_revision": 0},
            {"body": "x"},
            {"body": "x", "base_revision": "0"},
            {"body": "x", "base_revision": -1},
            {"body": "x", "base_revision": True},
        ):
            with self.subTest(payload=payload):
                response = self.client.put(note_url(record), payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertFalse(ReadingNote.objects.exists())

    def test_writing_a_note_does_not_save_the_record(self):
        from .models import SavedRecord

        self.write(self.record(), "private", base_revision=0)

        self.assertFalse(SavedRecord.objects.exists())

    def test_deleting_removes_the_note_and_repeating_it_is_still_a_204(self):
        record = self.record()
        self.write(record, "gone soon", base_revision=0)

        first = self.client.delete(note_url(record))
        again = self.client.delete(note_url(record))

        self.assertEqual((first.status_code, again.status_code), (204, 204))
        self.assertFalse(ReadingNote.objects.exists())
        self.assertEqual(self.client.get(note_url(record)).data["revision"], 0)

    def test_the_database_allows_one_note_per_reader_and_record(self):
        record = self.record()
        ReadingNote.objects.create(owner=self.reader, record=record, body="a")

        with self.assertRaises(IntegrityError), transaction.atomic():
            ReadingNote.objects.create(owner=self.reader, record=record, body="b")

    def test_an_anonymous_caller_is_refused(self):
        record = self.record()
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(note_url(record)).status_code, 401)
        self.assertEqual(self.write(record, "x").status_code, 401)
        self.assertEqual(self.client.delete(note_url(record)).status_code, 401)


class ConflictTests(NoteTestCase):
    def test_a_stale_revision_is_a_409_carrying_the_servers_text_and_writes_nothing(self):
        record = self.record()
        # Device A and device B both open the note at revision 0.
        self.write(record, "Written on the lab PC", base_revision=0)

        stale = self.write(record, "Written at home", base_revision=0)

        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "revision_conflict")
        self.assertEqual(stale.data["body"], "Written on the lab PC")
        self.assertEqual(stale.data["revision"], 1)
        note = ReadingNote.objects.get(owner=self.reader, record=record)
        self.assertEqual((note.body, note.revision), ("Written on the lab PC", 1))

    def test_a_revision_ahead_of_the_server_is_also_a_conflict(self):
        record = self.record()

        response = self.write(record, "x", base_revision=7)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["revision"], 0)
        self.assertFalse(ReadingNote.objects.exists())

    def test_reconciling_means_saving_against_the_revision_the_409_returned(self):
        record = self.record()
        self.write(record, "server text", base_revision=0)
        conflict = self.write(record, "my text", base_revision=0)

        merged = self.write(record, "server text + my text", base_revision=conflict.data["revision"])

        self.assertEqual((merged.status_code, merged.data["revision"]), (200, 2))

    def test_deleting_does_not_need_a_revision(self):
        record = self.record()
        self.write(record, "text", base_revision=0)

        self.assertEqual(self.client.delete(note_url(record)).status_code, 204)


class OwnershipTests(NoteTestCase):
    def test_another_reader_sees_an_empty_note_not_this_ones(self):
        record = self.record()
        self.write(record, "my private opinion", base_revision=0)
        self.client.force_authenticate(self.other)

        response = self.client.get(note_url(record))

        self.assertEqual((response.status_code, response.data["body"], response.data["revision"]), (200, "", 0))
        self.assertNotIn("private opinion", str(response.content))

    def test_nobody_else_can_read_change_or_delete_it(self):
        record = self.record()
        self.write(record, "my private opinion", base_revision=0)
        staff = [
            self.person(f"note-{name.value.lower().replace(' ', '')}@cit.edu", name)
            for name in (RoleName.KTTO, RoleName.RDCO, RoleName.ITSO, RoleName.IERC,
                         RoleName.ADVISER, RoleName.SYSTEM_ADMIN)
        ]
        # The Record's own owner is not special either.
        for person in (*staff, self.author, self.other):
            with self.subTest(person=person.email):
                self.client.force_authenticate(person)

                read = self.client.get(note_url(record))
                overwrite = self.write(record, "taken over", base_revision=1)
                delete = self.client.delete(note_url(record))

                self.assertNotIn("private opinion", str(read.content))
                self.assertEqual(read.data.get("body", ""), "")
                self.assertNotIn("private opinion", str(overwrite.content))
                self.assertIn(delete.status_code, (204, 404))
                note = ReadingNote.objects.get(owner=self.reader, record=record)
                self.assertEqual((note.body, note.revision), ("my private opinion", 1))

    def test_a_body_naming_another_owner_is_ignored(self):
        record = self.record()

        self.client.put(
            note_url(record), {"body": "mine", "base_revision": 0, "owner": self.other.id}, format="json",
        )

        self.assertTrue(ReadingNote.objects.filter(owner=self.reader, record=record).exists())
        self.assertFalse(ReadingNote.objects.filter(owner=self.other).exists())

    def test_two_readers_hold_two_notes_on_one_record(self):
        record = self.record()
        self.write(record, "reader one", base_revision=0)
        self.write(record, "reader two", base_revision=0, client=self._as(self.other))

        self.assertEqual(ReadingNote.objects.filter(record=record).count(), 2)
        self.assertEqual(self.client.get(note_url(record)).data["body"], "reader one")

    def _as(self, user):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user)
        return client


class VisibilityTests(NoteTestCase):
    def test_an_unreadable_record_is_the_same_404_as_a_missing_one_on_every_call(self):
        draft = self.record("Someone's draft", status=PipelineStatus.DRAFT)
        missing_id = draft.id + 10_000

        for call in (
            lambda r: self.client.get(note_url(r)),
            lambda r: self.write(r, "x"),
            lambda r: self.client.delete(note_url(r)),
        ):
            hidden, missing = call(draft), call(missing_id)
            self.assertEqual((hidden.status_code, missing.status_code), (404, 404))
            self.assertEqual(hidden.data, missing.data)
        self.assertFalse(ReadingNote.objects.exists())

    def test_revoked_access_keeps_the_text_and_returning_access_brings_it_back(self):
        record = self.record("Later restricted")
        self.write(record, "kept through revocation", base_revision=0)
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)

        read = self.client.get(note_url(record))
        write = self.write(record, "overwrite attempt", base_revision=1)
        delete = self.client.delete(note_url(record))

        self.assertEqual((read.status_code, write.status_code, delete.status_code), (404, 404, 404))
        self.assertNotIn("kept through revocation", str(read.content))
        note = ReadingNote.objects.get(owner=self.reader, record=record)
        self.assertEqual((note.body, note.revision), ("kept through revocation", 1))

        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)
        self.assertEqual(self.client.get(note_url(record)).data["body"], "kept through revocation")

    def test_an_owner_may_keep_a_note_on_their_own_draft(self):
        draft = self.record("My draft", status=PipelineStatus.DRAFT, owner=self.reader)

        self.assertEqual(self.write(draft, "plan", base_revision=0).status_code, 200)

    def test_deleting_the_record_deletes_its_notes(self):
        record = self.record()
        self.write(record, "gone with it", base_revision=0)

        Record.objects.filter(pk=record.pk).delete()

        self.assertFalse(ReadingNote.objects.exists())


class NoOtherSurfaceReadsNotesTests(NoteTestCase):
    """ADR-064 §7: notes are never a signal and never an input."""

    #: The only places that may name the model: the library itself, and the two
    #: registries that give an account's data back to it or delete it with it.
    ALLOWED = (
        "apps/library/",
        "apps/accounts/personal_data/",
        "apps/accounts/deletion/",
    )
    PATTERN = re.compile(r"ReadingNote|reading_notes?")

    def test_no_other_app_reads_the_note_model(self):
        """Every app, not a list of the ones that recommend, discuss or prompt:
        a new surface that reaches for notes is caught the day it is written."""
        backend = pathlib.Path(settings.BASE_DIR)
        offenders = []
        for path in sorted((backend / "apps").rglob("*.py")):
            rel = path.relative_to(backend).as_posix()
            if rel.startswith(self.ALLOWED) or "/migrations/" in rel:
                continue
            if path.name.startswith("test") or "/tests/" in rel:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if self.PATTERN.search(line):
                    offenders.append(f"{rel}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "ADR-064 §7: nothing outside the library may read a reader's notes.")

    def test_notes_are_not_registered_in_the_django_admin(self):
        from django.contrib import admin

        self.assertNotIn(ReadingNote, admin.site._registry)
