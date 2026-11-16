"""
IR-756 at the reading-history API seam (ADR-044 §Amendment 2026-11-01, IR-756).

What this pins:

* a visit is recorded only by an explicit PUT, and opening a Record's detail
  records nothing;
* the owner is always the authenticated user, and a hidden Record is the same
  404 as a missing one;
* revisiting moves a Record to the top, and only the 50 most recent are kept;
* a Record that becomes unreadable is listed as unavailable with only its id;
* clearing deletes the rows, and pausing records nothing while keeping them;
* two devices of one account share one history, and two accounts on one
  client never see each other's;
* nothing outside the library reads the model.
"""

import pathlib
import re

from django.conf import settings
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.records.models import Record
from core.enums import PipelineStatus

from .models import MAX_HISTORY_ENTRIES, LibraryPreferences, ReadingVisit
from .tests import LibraryTestCase


def offending_lines(pattern, allowed) -> list[str]:
    """
    Every line outside `allowed` that names `pattern`, across every backend app,
    `core`, and the AI runtime (which reads PostgreSQL directly) -- not a list of
    the apps that recommend or rank, so a new surface that reaches for a reader's
    private reading is caught the day it is written. Tests and migrations are
    skipped.
    """
    repo = pathlib.Path(settings.BASE_DIR).parent
    sources = [
        *(repo / "backend" / "apps").rglob("*.py"),
        *(repo / "backend" / "core").rglob("*.py"),
        *(repo / "ai").rglob("*.py"),
        *(repo / "ai").rglob("*.sql"),
    ]
    assert any(p.parts[-2:] == ("library", "views.py") for p in sources), "the scan found no sources"
    regex = re.compile(pattern)
    offenders = []
    for path in sorted(sources):
        rel = path.relative_to(repo).as_posix()
        if rel.startswith(tuple(allowed)) or "/migrations/" in rel:
            continue
        if path.name.startswith("test") or "/tests/" in rel:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if regex.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()}")
    return offenders

HISTORY = "/api/v1/library/history/"


def visit_url(record_or_id):
    return f"{HISTORY}{getattr(record_or_id, 'id', record_or_id)}/"


class HistoryTestCase(LibraryTestCase):
    def visit(self, record, client=None):
        return (client or self.client).put(visit_url(record), {}, format="json")

    def listed(self, client=None):
        response = (client or self.client).get(HISTORY)
        self.assertEqual(response.status_code, 200)
        return response.data["results"]

    def listed_ids(self, client=None):
        return [entry["record_id"] for entry in self.listed(client)]


class RecordingTests(HistoryTestCase):
    def test_a_visit_is_listed_with_the_record(self):
        record = self.record("Opened paper")

        response = self.visit(record)

        self.assertEqual(response.status_code, 204)
        [entry] = self.listed()
        self.assertEqual(entry["record_id"], record.id)
        self.assertTrue(entry["available"])
        self.assertEqual(entry["record"]["title"], "Opened paper")
        self.assertIsNotNone(entry["viewed_at"])

    def test_revisiting_moves_a_record_to_the_top_and_keeps_one_row(self):
        first, second = self.record("First"), self.record("Second")
        self.visit(first)
        self.visit(second)

        self.visit(first)

        self.assertEqual(self.listed_ids(), [first.id, second.id])
        self.assertEqual(ReadingVisit.objects.filter(owner=self.reader, record=first).count(), 1)

    def test_only_the_fifty_most_recent_are_kept(self):
        records = [self.record(f"Paper {n}") for n in range(MAX_HISTORY_ENTRIES + 2)]
        for record in records:
            self.visit(record)

        listed = self.listed_ids()

        self.assertEqual(MAX_HISTORY_ENTRIES, 50)
        self.assertEqual(listed, [r.id for r in reversed(records)][:50])
        self.assertEqual(ReadingVisit.objects.filter(owner=self.reader).count(), 50)

    def test_reading_a_record_records_nothing(self):
        record = self.record()

        self.assertEqual(self.client.get(f"/api/v1/records/{record.id}/").status_code, 200)

        self.assertEqual(self.listed(), [])

    def test_a_visit_writes_no_audit_event(self):
        record = self.record()
        before = AuditEvent.objects.count()

        self.visit(record)
        self.client.delete(HISTORY)

        self.assertEqual(AuditEvent.objects.count(), before)

    def test_an_anonymous_caller_is_refused(self):
        record = self.record()
        anonymous = APIClient()

        self.assertEqual(anonymous.put(visit_url(record), {}, format="json").status_code, 401)
        self.assertEqual(anonymous.get(HISTORY).status_code, 401)
        self.assertEqual(anonymous.delete(HISTORY).status_code, 401)
        self.assertFalse(ReadingVisit.objects.exists())


class HistoryVisibilityTests(HistoryTestCase):
    def test_visiting_an_unreadable_record_is_the_same_404_as_a_missing_one(self):
        draft = self.record("Someone's draft", status=PipelineStatus.DRAFT)

        hidden = self.visit(draft)
        missing = self.visit(draft.id + 10_000)

        self.assertEqual((hidden.status_code, missing.status_code), (404, 404))
        self.assertEqual(hidden.data, missing.data)
        self.assertFalse(ReadingVisit.objects.exists())

    def test_a_visit_that_becomes_unreadable_is_listed_as_unavailable_and_discloses_nothing(self):
        record = self.record("Later withdrawn")
        self.visit(record)
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)

        response = self.client.get(HISTORY)

        self.assertEqual(response.data["results"], [{"record_id": record.id, "available": False}])
        self.assertNotIn("Later withdrawn", str(response.content))

    def test_deleting_a_record_removes_it_from_every_history(self):
        record = self.record()
        self.visit(record)
        other = APIClient()
        other.force_authenticate(self.other)
        self.visit(record, client=other)

        record.delete()

        self.assertFalse(ReadingVisit.objects.exists())


class HistoryOwnershipTests(HistoryTestCase):
    def test_two_devices_of_one_account_share_one_history(self):
        record = self.record()
        lab_pc, laptop = APIClient(), APIClient()
        lab_pc.force_authenticate(self.reader)
        laptop.force_authenticate(self.reader)

        self.visit(record, client=lab_pc)

        self.assertEqual(self.listed_ids(client=laptop), [record.id])

    def test_two_accounts_on_one_client_never_see_each_others_history(self):
        record = self.record()
        shared_pc = APIClient()
        shared_pc.force_authenticate(self.reader)
        self.visit(record, client=shared_pc)

        shared_pc.force_authenticate(self.other)

        self.assertEqual(self.listed(client=shared_pc), [])

    def test_a_body_naming_another_owner_is_ignored(self):
        record = self.record()

        self.client.put(visit_url(record), {"owner": self.other.id}, format="json")

        self.assertEqual(list(ReadingVisit.objects.values_list("owner_id", flat=True)), [self.reader.id])

    def test_clearing_deletes_only_the_callers_history(self):
        first, second = self.record("First"), self.record("Second")
        self.visit(first)
        self.visit(second)
        other = APIClient()
        other.force_authenticate(self.other)
        self.visit(first, client=other)

        response = self.client.delete(HISTORY)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.listed(), [])
        self.assertFalse(ReadingVisit.objects.filter(owner=self.reader).exists())
        self.assertEqual(self.listed_ids(client=other), [first.id])


PREFERENCES = "/api/v1/library/preferences/"


class PauseTests(HistoryTestCase):
    def pause(self, keep, client=None):
        return (client or self.client).patch(PREFERENCES, {"keep_history": keep}, format="json")

    def test_history_is_kept_by_default_and_reading_the_setting_creates_nothing(self):
        response = self.client.get(PREFERENCES)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"keep_history": True})
        self.assertFalse(LibraryPreferences.objects.exists())

    def test_while_paused_a_visit_records_nothing_and_existing_history_is_kept(self):
        earlier, later = self.record("Earlier"), self.record("Later")
        self.visit(earlier)

        paused = self.pause(False)
        response = self.visit(later)

        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.data, {"keep_history": False})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.listed_ids(), [earlier.id])

    def test_a_paused_visit_does_not_move_an_existing_entry(self):
        first, second = self.record("First"), self.record("Second")
        self.visit(first)
        self.visit(second)
        self.pause(False)

        self.visit(first)

        self.assertEqual(self.listed_ids(), [second.id, first.id])

    def test_resuming_records_visits_again(self):
        record = self.record()
        self.pause(False)
        self.pause(True)

        self.visit(record)

        self.assertEqual(self.client.get(PREFERENCES).data, {"keep_history": True})
        self.assertEqual(self.listed_ids(), [record.id])

    def test_pausing_on_one_device_pauses_the_other(self):
        record = self.record()
        lab_pc, laptop = APIClient(), APIClient()
        lab_pc.force_authenticate(self.reader)
        laptop.force_authenticate(self.reader)

        self.pause(False, client=lab_pc)
        self.visit(record, client=laptop)

        self.assertEqual(laptop.get(PREFERENCES).data, {"keep_history": False})
        self.assertEqual(self.listed(client=laptop), [])

    def test_one_readers_pause_never_affects_another(self):
        record = self.record()
        other = APIClient()
        other.force_authenticate(self.other)

        self.pause(False)
        self.visit(record, client=other)

        self.assertEqual(other.get(PREFERENCES).data, {"keep_history": True})
        self.assertEqual(self.listed_ids(client=other), [record.id])

    def test_a_value_that_is_not_true_or_false_is_refused_and_changes_nothing(self):
        for bad in ("no", 0, None):
            response = self.pause(bad)
            self.assertEqual(response.status_code, 400, bad)
        self.assertEqual(self.client.patch(PREFERENCES, {}, format="json").status_code, 400)
        self.assertFalse(LibraryPreferences.objects.exists())

    def test_an_anonymous_caller_is_refused(self):
        anonymous = APIClient()

        self.assertEqual(anonymous.get(PREFERENCES).status_code, 401)
        self.assertEqual(anonymous.patch(PREFERENCES, {"keep_history": False}, format="json").status_code, 401)


class NoOtherSurfaceReadsHistoryTests(HistoryTestCase):
    """ADR-044 §Amendment 2026-11-01, points 2 and 6: history is never a
    discovery signal, and only its reader sees it."""

    #: The only files that may name either model: the library's own model, views
    #: and routes, and the two registries that give an account's data back to it
    #: or delete it with it. The rest of `apps/library` (saved feeds, which
    #: reach into Discover) is scanned like any other app.
    ALLOWED = (
        "backend/apps/library/models.py",
        "backend/apps/library/views.py",
        "backend/apps/library/urls.py",
        "backend/apps/accounts/personal_data/",
        "backend/apps/accounts/deletion/",
    )
    #: The models, their related names, the setting, and the tables themselves,
    #: so raw SQL is caught too.
    PATTERN = (
        r"ReadingVisit|reading_visits?|LibraryPreferences|library_preferences|keep_history"
        r"|library_readingvisit|library_librarypreferences"
    )

    def test_no_other_app_reads_the_history(self):
        self.assertEqual(
            offending_lines(self.PATTERN, self.ALLOWED), [],
            "IR-756: nothing outside the library may read a reader's history.",
        )

    def test_neither_model_is_registered_in_the_django_admin(self):
        from django.contrib import admin

        self.assertNotIn(ReadingVisit, admin.site._registry)
        self.assertNotIn(LibraryPreferences, admin.site._registry)
