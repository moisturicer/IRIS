"""
IR-566 at the library API seam (ADR-044 §2-§5).

What this pins:

* the owner is always the authenticated user -- another reader's saves are
  never listed, changed or removed;
* saving rechecks `visible_to()`, so an unreadable Record answers the same 404
  as a missing one;
* a saved Record that becomes unreadable is listed as unavailable and carries
  nothing but the id the reader supplied;
* PUT and DELETE are idempotent, and a Record has at most one status;
* two devices of one account see one library.
"""

from django.db import IntegrityError, transaction
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import PipelineStatus, ReadingStatus, RecordTypeName, RoleName

from .models import SavedRecord

SAVES = "/api/v1/library/saves/"


def save_url(record_or_id):
    return f"{SAVES}{getattr(record_or_id, 'id', record_or_id)}/"


class LibraryTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        role = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        cls.reader = User.objects.create_user(
            email="library-reader@cit.edu", password="TestPass123!",
            first_name="A", last_name="Reader", role=role,
        )
        cls.other = User.objects.create_user(
            email="library-other@cit.edu", password="TestPass123!",
            first_name="B", last_name="Reader", role=role,
        )
        cls.author = User.objects.create_user(
            email="library-author@cit.edu", password="TestPass123!",
            first_name="C", last_name="Author", role=role,
        )
        cls.thesis = RecordType.objects.get(name=RecordTypeName.THESIS_RESEARCH)

    def setUp(self):
        self.client.force_authenticate(self.reader)

    def record(self, title="Published research", *, status=PipelineStatus.PUBLISHED, owner=None):
        owner = owner or self.author
        record = Record.objects.create(
            title=title, abstract="An abstract.", record_type=self.thesis,
            added_by=owner, pipeline_status=status, year_accomplished=2026,
        )
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)
        return record


class SaveAndUnsaveTests(LibraryTestCase):
    def test_saving_creates_one_row_and_repeating_it_changes_nothing(self):
        record = self.record()

        first = self.client.put(save_url(record), {}, format="json")
        again = self.client.put(save_url(record), {}, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(SavedRecord.objects.filter(owner=self.reader, record=record).count(), 1)
        self.assertEqual(first.data["record"]["id"], record.id)
        self.assertTrue(first.data["available"])
        self.assertIsNone(first.data["reading_status"])

    def test_a_status_saves_the_record_and_a_new_status_replaces_the_old(self):
        record = self.record()

        self.client.put(save_url(record), {"reading_status": ReadingStatus.WANT_TO_READ}, format="json")
        response = self.client.put(save_url(record), {"reading_status": ReadingStatus.COMPLETED}, format="json")

        self.assertEqual(response.status_code, 200)
        save = SavedRecord.objects.get(owner=self.reader, record=record)
        self.assertEqual(save.reading_status, ReadingStatus.COMPLETED)

    def test_omitting_the_status_keeps_it_and_null_clears_it(self):
        record = self.record()
        self.client.put(save_url(record), {"reading_status": ReadingStatus.READING}, format="json")

        kept = self.client.put(save_url(record), {}, format="json")
        cleared = self.client.put(save_url(record), {"reading_status": None}, format="json")

        self.assertEqual(kept.data["reading_status"], ReadingStatus.READING)
        self.assertIsNone(cleared.data["reading_status"])
        self.assertTrue(SavedRecord.objects.filter(owner=self.reader, record=record).exists())

    def test_an_unknown_status_is_refused_and_writes_nothing(self):
        record = self.record()

        response = self.client.put(save_url(record), {"reading_status": "finished"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SavedRecord.objects.exists())

    def test_unsaving_is_idempotent_and_clears_the_status_with_the_save(self):
        record = self.record()
        self.client.put(save_url(record), {"reading_status": ReadingStatus.READING}, format="json")

        first = self.client.delete(save_url(record))
        again = self.client.delete(save_url(record))

        self.assertEqual((first.status_code, again.status_code), (204, 204))
        self.assertFalse(SavedRecord.objects.exists())

    def test_the_database_allows_one_save_per_reader_and_record(self):
        record = self.record()
        SavedRecord.objects.create(owner=self.reader, record=record)

        with self.assertRaises(IntegrityError), transaction.atomic():
            SavedRecord.objects.create(owner=self.reader, record=record)

    def test_an_anonymous_caller_is_refused(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(SAVES).status_code, 401)
        self.assertEqual(self.client.put(save_url(self.record()), {}, format="json").status_code, 401)


class OwnershipTests(LibraryTestCase):
    def test_the_list_holds_only_the_callers_own_saves(self):
        mine, theirs = self.record("Mine"), self.record("Theirs")
        SavedRecord.objects.create(owner=self.reader, record=mine)
        SavedRecord.objects.create(owner=self.other, record=theirs)

        response = self.client.get(SAVES)

        self.assertEqual([row["record_id"] for row in response.data["results"]], [mine.id])

    def test_a_body_naming_another_owner_is_ignored(self):
        record = self.record()

        self.client.put(save_url(record), {"owner": self.other.id}, format="json")

        self.assertTrue(SavedRecord.objects.filter(owner=self.reader, record=record).exists())
        self.assertFalse(SavedRecord.objects.filter(owner=self.other).exists())

    def test_deleting_cannot_reach_another_readers_save(self):
        record = self.record()
        SavedRecord.objects.create(owner=self.other, record=record, reading_status=ReadingStatus.READING)

        response = self.client.delete(save_url(record))

        self.assertEqual(response.status_code, 204)
        self.assertTrue(SavedRecord.objects.filter(owner=self.other, record=record).exists())

    def test_writing_cannot_change_another_readers_status(self):
        record = self.record()
        SavedRecord.objects.create(owner=self.other, record=record, reading_status=ReadingStatus.READING)

        self.client.put(save_url(record), {"reading_status": ReadingStatus.COMPLETED}, format="json")

        self.assertEqual(
            SavedRecord.objects.get(owner=self.other, record=record).reading_status, ReadingStatus.READING,
        )


class VisibilityTests(LibraryTestCase):
    def test_saving_an_unreadable_record_is_the_same_404_as_a_missing_one(self):
        draft = self.record("Someone's draft", status=PipelineStatus.DRAFT)
        missing_id = draft.id + 10_000

        hidden = self.client.put(save_url(draft), {}, format="json")
        missing = self.client.put(save_url(missing_id), {}, format="json")

        self.assertEqual((hidden.status_code, missing.status_code), (404, 404))
        self.assertEqual(hidden.data, missing.data)
        self.assertFalse(SavedRecord.objects.exists())

    def test_an_owner_may_save_their_own_draft(self):
        draft = self.record("My draft", status=PipelineStatus.DRAFT, owner=self.reader)

        self.assertEqual(self.client.put(save_url(draft), {}, format="json").status_code, 201)

    def test_a_save_that_becomes_unreadable_is_listed_as_unavailable_and_discloses_nothing(self):
        record = self.record("Later withdrawn")
        self.client.put(save_url(record), {"reading_status": ReadingStatus.READING}, format="json")
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)

        response = self.client.get(SAVES)

        self.assertEqual(response.data["results"], [{"record_id": record.id, "available": False}])
        self.assertNotIn("Later withdrawn", str(response.content))

    def test_an_unavailable_save_can_still_be_removed(self):
        record = self.record()
        SavedRecord.objects.create(owner=self.reader, record=record)
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)

        self.assertEqual(self.client.delete(save_url(record)).status_code, 204)
        self.assertFalse(SavedRecord.objects.exists())

    def test_deleting_a_record_removes_it_from_every_library(self):
        record = self.record()
        SavedRecord.objects.create(owner=self.reader, record=record)
        SavedRecord.objects.create(owner=self.other, record=record)

        record.delete()

        self.assertFalse(SavedRecord.objects.exists())


class TwoDevicesTests(LibraryTestCase):
    def test_a_save_on_one_device_is_seen_with_its_status_on_another(self):
        record = self.record()
        lab_pc, laptop = APIClient(), APIClient()
        lab_pc.force_authenticate(self.reader)
        laptop.force_authenticate(self.reader)

        lab_pc.put(save_url(record), {"reading_status": ReadingStatus.READING}, format="json")
        listed = laptop.get(SAVES).data["results"]

        self.assertEqual(
            [(row["record_id"], row["reading_status"]) for row in listed],
            [(record.id, ReadingStatus.READING)],
        )

    def test_two_accounts_on_one_client_never_see_each_others_saves(self):
        record = self.record()
        shared_pc = APIClient()

        shared_pc.force_authenticate(self.reader)
        shared_pc.put(save_url(record), {}, format="json")
        shared_pc.force_authenticate(self.other)
        listed = shared_pc.get(SAVES).data["results"]

        self.assertEqual(listed, [])
