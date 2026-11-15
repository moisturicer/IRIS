"""
IR-572 at the library API seam: a reader's own folders follow the account.

What this pins:

* folders are owner-only -- another reader's folder reads exactly like a
  missing one, and no list, rename, filing or deletion reaches it;
* a folder holds saved papers: filing a Record saves it, a Record is in a
  folder at most once, and unsaving takes it out of every folder;
* removing a Record from a folder never unsaves it and never counts as "Not
  interested" in discovery;
* creating, renaming and deleting are idempotent, and deleting a folder never
  deletes a save;
* filing rechecks `visible_to()`, and a filed Record that becomes unreadable
  stays listed by the id the reader supplied, and nothing else.
"""

import pathlib
import re

from django.conf import settings
from rest_framework.test import APIClient

from apps.records.models import DiscoveryDismissal, Record
from core.enums import PipelineStatus, ReadingStatus

from .models import MAX_FOLDERS, FolderMembership, LibraryFolder, SavedRecord
from .tests import LibraryTestCase, save_url

FOLDERS = "/api/v1/library/folders/"


def folder_url(folder_or_id):
    return f"{FOLDERS}{getattr(folder_or_id, 'id', folder_or_id)}/"


def filing_url(folder_or_id, record_or_id):
    return f"{folder_url(folder_or_id)}records/{getattr(record_or_id, 'id', record_or_id)}/"


class FolderTestCase(LibraryTestCase):
    def create(self, name):
        return self.client.post(FOLDERS, {"name": name}, format="json")

    def listed(self):
        response = self.client.get(FOLDERS)
        self.assertEqual(response.status_code, 200)
        return response.data["results"]


class CreateFolderTests(FolderTestCase):
    def test_a_reader_creates_a_folder_and_finds_it_listed_empty(self):
        response = self.create("Methods")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Methods")
        self.assertEqual(response.data["record_ids"], [])
        listed = self.listed()
        self.assertEqual([(f["id"], f["name"], f["record_ids"]) for f in listed], [(response.data["id"], "Methods", [])])

    def test_creating_a_name_the_reader_already_has_returns_that_folder(self):
        first = self.create("Methods")
        again = self.create("  methods ")

        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["id"], first.data["id"])
        self.assertEqual(again.data["name"], "Methods")
        self.assertEqual(LibraryFolder.objects.filter(owner=self.reader).count(), 1)

    def test_a_name_is_required_and_at_most_sixty_characters(self):
        for name in ("", "   ", None, 42, "x" * 61):
            with self.subTest(name=name):
                response = self.create(name)
                self.assertEqual(response.status_code, 400)
                self.assertIn("name", response.data)
        self.assertEqual(self.create("x" * 60).status_code, 201)
        self.assertEqual(LibraryFolder.objects.filter(owner=self.reader).count(), 1)

    def test_the_database_allows_one_name_per_account_ignoring_case(self):
        from django.db import IntegrityError, transaction

        LibraryFolder.objects.create(owner=self.reader, name="Methods")
        with self.assertRaises(IntegrityError), transaction.atomic():
            LibraryFolder.objects.create(owner=self.reader, name="METHODS")
        LibraryFolder.objects.create(owner=self.other, name="Methods")

    def test_the_limit_refuses_a_new_folder_and_deleting_one_makes_room(self):
        made = [self.create(f"Folder {n}").data for n in range(MAX_FOLDERS)]

        refused = self.create("One too many")

        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.data["code"], "folder_limit")
        self.assertEqual(refused.data["limit"], MAX_FOLDERS)
        self.assertEqual(LibraryFolder.objects.filter(owner=self.reader).count(), MAX_FOLDERS)
        # Asking again for a folder the reader already has is still answered.
        self.assertEqual(self.create("Folder 3").status_code, 200)

        self.client.delete(folder_url(made[0]["id"]))
        self.assertEqual(self.create("One too many").status_code, 201)

    def test_the_limit_is_per_account_and_listed_with_the_folders(self):
        for n in range(MAX_FOLDERS):
            LibraryFolder.objects.create(owner=self.other, name=f"Theirs {n}")

        self.assertEqual(self.create("Mine").status_code, 201)
        self.assertEqual(self.client.get(FOLDERS).data["limit"], MAX_FOLDERS)

    def test_folders_are_listed_oldest_first(self):
        for name in ("First", "Second", "Third"):
            self.create(name)

        self.assertEqual([f["name"] for f in self.listed()], ["First", "Second", "Third"])

    def test_an_anonymous_caller_is_refused(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(FOLDERS).status_code, 401)
        self.assertEqual(self.create("Methods").status_code, 401)


class RenameAndDeleteTests(FolderTestCase):
    def test_renaming_changes_the_name_and_repeating_it_changes_nothing(self):
        made = self.create("Methods").data

        first = self.client.patch(folder_url(made["id"]), {"name": "Method papers"}, format="json")
        again = self.client.patch(folder_url(made["id"]), {"name": "Method papers"}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["name"], "Method papers")
        self.assertEqual([f["name"] for f in self.listed()], ["Method papers"])

    def test_renaming_to_another_folders_name_is_refused_but_recasing_ones_own_is_not(self):
        methods = self.create("Methods").data
        self.create("Results")

        taken = self.client.patch(folder_url(methods["id"]), {"name": "results"}, format="json")
        recased = self.client.patch(folder_url(methods["id"]), {"name": "METHODS"}, format="json")

        self.assertEqual(taken.status_code, 400)
        self.assertIn("name", taken.data)
        self.assertEqual(recased.status_code, 200)
        self.assertEqual(sorted(f["name"] for f in self.listed()), ["METHODS", "Results"])

    def test_a_rename_needs_a_valid_name(self):
        made = self.create("Methods").data

        for body in ({}, {"name": ""}, {"name": "x" * 61}):
            with self.subTest(body=body):
                self.assertEqual(self.client.patch(folder_url(made["id"]), body, format="json").status_code, 400)
        self.assertEqual(self.listed()[0]["name"], "Methods")

    def test_renaming_a_missing_folder_is_a_404(self):
        self.assertEqual(self.client.patch(folder_url(999_999), {"name": "Anything"}, format="json").status_code, 404)

    def test_deleting_is_idempotent(self):
        made = self.create("Methods").data

        first = self.client.delete(folder_url(made["id"]))
        again = self.client.delete(folder_url(made["id"]))

        self.assertEqual(first.status_code, 204)
        self.assertEqual(again.status_code, 204)
        self.assertEqual(self.listed(), [])


class FilingTests(FolderTestCase):
    def setUp(self):
        super().setUp()
        self.folder = self.create("Methods").data

    def test_filing_a_saved_record_adds_it_once_and_repeating_it_changes_nothing(self):
        record = self.record()
        self.client.put(save_url(record), {"reading_status": ReadingStatus.READING}, format="json")

        first = self.client.put(filing_url(self.folder["id"], record), format="json")
        again = self.client.put(filing_url(self.folder["id"], record), format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["folder"]["record_ids"], [record.id])
        self.assertEqual(again.data["save"]["reading_status"], ReadingStatus.READING)
        self.assertEqual(FolderMembership.objects.filter(folder_id=self.folder["id"]).count(), 1)
        self.assertEqual(self.listed()[0]["record_ids"], [record.id])

    def test_filing_an_unsaved_record_saves_it_without_a_status(self):
        record = self.record()

        response = self.client.put(filing_url(self.folder["id"], record), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["save"]["available"])
        self.assertIsNone(response.data["save"]["reading_status"])
        self.assertEqual(SavedRecord.objects.filter(owner=self.reader, record=record).count(), 1)

    def test_a_record_may_sit_in_several_folders_listed_newest_filing_first(self):
        older, newer = self.record("Older"), self.record("Newer")
        results = self.create("Results").data

        for folder in (self.folder, results):
            self.client.put(filing_url(folder["id"], older), format="json")
        self.client.put(filing_url(self.folder["id"], newer), format="json")

        listed = {f["name"]: f["record_ids"] for f in self.listed()}
        self.assertEqual(listed, {"Methods": [newer.id, older.id], "Results": [older.id]})

    def test_the_database_allows_one_membership_per_folder_and_record(self):
        from django.db import IntegrityError, transaction

        record = self.record()
        self.client.put(filing_url(self.folder["id"], record), format="json")
        save = SavedRecord.objects.get(owner=self.reader, record=record)

        with self.assertRaises(IntegrityError), transaction.atomic():
            FolderMembership.objects.create(folder_id=self.folder["id"], saved_record=save)

    def test_removing_from_a_folder_keeps_the_save_its_status_and_is_not_a_dismissal(self):
        record = self.record()
        self.client.put(save_url(record), {"reading_status": ReadingStatus.WANT_TO_READ}, format="json")
        self.client.put(filing_url(self.folder["id"], record), format="json")

        first = self.client.delete(filing_url(self.folder["id"], record))
        again = self.client.delete(filing_url(self.folder["id"], record))

        self.assertEqual(first.status_code, 204)
        self.assertEqual(again.status_code, 204)
        self.assertEqual(self.listed()[0]["record_ids"], [])
        save = SavedRecord.objects.get(owner=self.reader, record=record)
        self.assertEqual(save.reading_status, ReadingStatus.WANT_TO_READ)
        self.assertFalse(DiscoveryDismissal.objects.filter(user=self.reader).exists())

    def test_removing_from_one_folder_leaves_the_record_in_the_others(self):
        record = self.record()
        results = self.create("Results").data
        for folder in (self.folder, results):
            self.client.put(filing_url(folder["id"], record), format="json")

        self.client.delete(filing_url(self.folder["id"], record))

        self.assertEqual({f["name"]: f["record_ids"] for f in self.listed()}, {"Methods": [], "Results": [record.id]})

    def test_unsaving_takes_the_record_out_of_every_folder(self):
        record = self.record()
        results = self.create("Results").data
        for folder in (self.folder, results):
            self.client.put(filing_url(folder["id"], record), format="json")

        self.client.delete(save_url(record))

        self.assertEqual([f["record_ids"] for f in self.listed()], [[], []])
        self.assertFalse(FolderMembership.objects.exists())

    def test_deleting_a_folder_never_deletes_a_save(self):
        record = self.record()
        self.client.put(save_url(record), {"reading_status": ReadingStatus.COMPLETED}, format="json")
        self.client.put(filing_url(self.folder["id"], record), format="json")

        self.assertEqual(self.client.delete(folder_url(self.folder["id"])).status_code, 204)

        self.assertFalse(FolderMembership.objects.exists())
        save = SavedRecord.objects.get(owner=self.reader, record=record)
        self.assertEqual(save.reading_status, ReadingStatus.COMPLETED)
        self.assertFalse(DiscoveryDismissal.objects.filter(user=self.reader).exists())

    def test_filing_in_a_missing_folder_is_a_404_and_saves_nothing(self):
        record = self.record()

        response = self.client.put(filing_url(999_999, record), format="json")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(SavedRecord.objects.filter(owner=self.reader).exists())


class FilingVisibilityTests(FolderTestCase):
    def setUp(self):
        super().setUp()
        self.folder = self.create("Methods").data

    def test_filing_an_unreadable_record_is_the_same_404_as_a_missing_one(self):
        draft = self.record("Someone's draft", status=PipelineStatus.DRAFT)

        hidden = self.client.put(filing_url(self.folder["id"], draft), format="json")
        missing = self.client.put(filing_url(self.folder["id"], 999_999), format="json")

        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.content, missing.content)
        self.assertFalse(SavedRecord.objects.filter(owner=self.reader).exists())
        self.assertEqual(self.listed()[0]["record_ids"], [])

    def test_a_filed_record_that_becomes_unreadable_stays_listed_by_its_id_alone(self):
        record = self.record("Later restricted")
        self.client.put(filing_url(self.folder["id"], record), format="json")
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)

        self.assertEqual(self.listed()[0]["record_ids"], [record.id])
        listed = self.client.get(FOLDERS).content.decode()
        self.assertNotIn("Later restricted", listed)
        saves = self.client.get("/api/v1/library/saves/").data["results"]
        self.assertEqual(saves, [{"record_id": record.id, "available": False}])

    def test_an_unavailable_record_can_still_be_removed_from_a_folder(self):
        record = self.record()
        self.client.put(filing_url(self.folder["id"], record), format="json")
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)

        self.assertEqual(self.client.delete(filing_url(self.folder["id"], record)).status_code, 204)

        self.assertEqual(self.listed()[0]["record_ids"], [])
        self.assertTrue(SavedRecord.objects.filter(owner=self.reader, record=record).exists())

    def test_deleting_a_record_removes_it_from_every_folder(self):
        record = self.record()
        self.client.put(filing_url(self.folder["id"], record), format="json")

        record.delete()

        self.assertEqual(self.listed()[0]["record_ids"], [])


class OwnershipTests(FolderTestCase):
    def setUp(self):
        super().setUp()
        self.theirs = LibraryFolder.objects.create(owner=self.other, name="Their folder")
        self.their_record = self.record("Their paper")
        their_save = SavedRecord.objects.create(owner=self.other, record=self.their_record)
        FolderMembership.objects.create(folder=self.theirs, saved_record=their_save)

    def test_the_list_holds_only_the_callers_own_folders(self):
        self.create("Mine")

        self.assertEqual([f["name"] for f in self.listed()], ["Mine"])

    def test_another_readers_folder_reads_exactly_like_a_missing_one(self):
        record = self.record()
        cases = [
            ("patch", folder_url(self.theirs), folder_url(999_999), {"name": "Taken over"}),
            ("put", filing_url(self.theirs, record), filing_url(999_999, record), None),
        ]
        for method, theirs, missing, body in cases:
            with self.subTest(method=method):
                hidden = getattr(self.client, method)(theirs, body, format="json")
                absent = getattr(self.client, method)(missing, body, format="json")
                self.assertEqual(hidden.status_code, 404)
                self.assertEqual(hidden.content, absent.content)

        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.name, "Their folder")
        self.assertEqual(list(self.theirs.memberships.values_list("saved_record__record_id", flat=True)), [self.their_record.id])
        self.assertFalse(SavedRecord.objects.filter(owner=self.reader).exists())

    def test_deleting_cannot_reach_another_readers_folder_or_its_filings(self):
        self.assertEqual(self.client.delete(filing_url(self.theirs, self.their_record)).status_code, 204)
        self.assertEqual(self.client.delete(folder_url(self.theirs)).status_code, 204)

        self.assertTrue(LibraryFolder.objects.filter(pk=self.theirs.pk).exists())
        self.assertEqual(self.theirs.memberships.count(), 1)

    def test_a_body_naming_another_owner_is_ignored(self):
        response = self.client.post(FOLDERS, {"name": "Mine", "owner": self.other.id}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(LibraryFolder.objects.get(pk=response.data["id"]).owner, self.reader)

    def test_two_readers_may_use_the_same_name(self):
        self.assertEqual(self.create("Their folder").status_code, 201)

        self.assertEqual(LibraryFolder.objects.filter(name="Their folder").count(), 2)

    def test_removing_the_account_removes_its_folders_and_filings(self):
        self.other.delete()

        self.assertFalse(LibraryFolder.objects.filter(pk=self.theirs.pk).exists())
        self.assertFalse(FolderMembership.objects.exists())


class DevicesAndAccountsTests(FolderTestCase):
    def test_a_folder_made_on_one_device_is_seen_with_its_papers_on_another(self):
        record = self.record()
        laptop, phone = APIClient(), APIClient()
        laptop.force_authenticate(self.reader)
        phone.force_authenticate(self.reader)

        made = laptop.post(FOLDERS, {"name": "Methods"}, format="json").data
        laptop.put(filing_url(made["id"], record), format="json")
        phone.patch(folder_url(made["id"]), {"name": "Method papers"}, format="json")

        on_laptop = laptop.get(FOLDERS).data["results"]
        on_phone = phone.get(FOLDERS).data["results"]
        self.assertEqual(on_laptop, on_phone)
        self.assertEqual([(f["name"], f["record_ids"]) for f in on_phone], [("Method papers", [record.id])])

    def test_two_accounts_on_one_client_never_see_each_others_folders(self):
        record = self.record()
        made = self.create("Reader's folder").data
        self.client.put(filing_url(made["id"], record), format="json")

        self.client.force_authenticate(self.other)
        self.assertEqual(self.listed(), [])
        self.assertEqual(self.client.put(filing_url(made["id"], record), format="json").status_code, 404)

        self.client.force_authenticate(self.reader)
        self.assertEqual([(f["name"], f["record_ids"]) for f in self.listed()], [("Reader's folder", [record.id])])


class FoldersAreNeverASignalTests(FolderTestCase):
    """ADR-070 §5: a folder organises a reader's saves for them alone."""

    #: The only places that may name the models: the library itself, and the two
    #: registries that give an account's data back to it or delete it with it.
    ALLOWED = (
        "apps/library/",
        "apps/accounts/personal_data/",
        "apps/accounts/deletion/",
    )
    PATTERN = re.compile(r"LibraryFolder|FolderMembership|library_folders")

    def test_no_other_app_reads_the_folder_models(self):
        """Every app, not a list of the recommenders: a new surface that reaches
        for folders -- For you, a ranking, a count -- is caught the day it is
        written."""
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
        self.assertEqual(offenders, [], "ADR-070 §5: nothing outside the library may read a reader's folders.")

    def test_folders_are_not_registered_in_the_django_admin(self):
        from django.contrib import admin

        self.assertNotIn(LibraryFolder, admin.site._registry)
        self.assertNotIn(FolderMembership, admin.site._registry)
