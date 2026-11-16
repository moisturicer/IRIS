"""
IR-573 at the reading-position API seam (ADR-044 §Amendment 2026-11-16, resume).

What this pins:

* a reader has at most one position per Record: the page and how far down it,
  bound to the Manuscript identity the server was serving them (revision and
  SHA-256), and saving again moves it rather than adding a row;
* the identity the reader says they were shown must still be the one served,
  else the write is refused and nothing is stored -- and a stored position is
  given back only while its identity is still served, so a replaced Manuscript
  never inherits another file's place;
* replacing or removing a Manuscript deletes the positions no one is served any
  more, whichever path wrote the new identity;
* only the 200 most recently read Records keep a position;
* a position is owner-only, and an unreadable Record is the same 404 as a
  missing one on both read and write;
* nothing outside the library reads a position, so draft and review reading is
  never a discovery signal.
"""

import uuid
from unittest import mock

from rest_framework.test import APIClient

from apps.records.models import Record, RecordVersion
from core.enums import PipelineStatus, VersionCause

from .models import MAX_READING_POSITIONS, ReadingPosition
from .test_history import offending_lines
from .tests import LibraryTestCase

POSITIONS = "/api/v1/library/positions/"


def position_url(record_or_id):
    return f"{POSITIONS}{getattr(record_or_id, 'id', record_or_id)}/"


class PositionTestCase(LibraryTestCase):
    def identified(self, title="Published research", **kwargs):
        """A Record whose Manuscript has an identity, as every accepted upload does."""
        record = self.record(title, **kwargs)
        self.replace_quietly(record)
        return record

    def replace_quietly(self, record):
        """New bytes written with `.update()`, as a maintenance command does: no signal fires."""
        Record.objects.filter(pk=record.pk).update(
            manuscript_revision=uuid.uuid4(), manuscript_sha256=uuid.uuid4().hex * 2,
        )
        record.refresh_from_db()
        return record.manuscript_revision

    def replace_by_upload(self, record):
        """New bytes accepted through the Record's own save, as an upload is."""
        record.manuscript_revision = uuid.uuid4()
        record.manuscript_sha256 = uuid.uuid4().hex * 2
        record.save(update_fields=["manuscript_revision", "manuscript_sha256", "updated_at"])
        return record.manuscript_revision

    def put(self, record, client=None, **overrides):
        body = {"manuscript_revision": str(record.manuscript_revision), "page": 12, "fraction": 0.25}
        body.update(overrides)
        return (client or self.client).put(position_url(record), body, format="json")

    def get(self, record, client=None):
        return (client or self.client).get(position_url(record))

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class ResumeTests(PositionTestCase):
    def test_a_paper_never_opened_has_no_position_and_reading_creates_none(self):
        record = self.identified()

        response = self.get(record)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"position": None})
        self.assertFalse(ReadingPosition.objects.exists())

    def test_a_saved_position_comes_back_bound_to_the_bytes_it_was_read_on(self):
        record = self.identified()

        saved = self.put(record, page=12, fraction=0.25)

        self.assertEqual(saved.status_code, 204)
        position = self.get(record).data["position"]
        self.assertEqual(
            (position["page"], position["fraction"], position["manuscript_revision"]),
            (12, 0.25, str(record.manuscript_revision)),
        )
        row = ReadingPosition.objects.get(owner=self.reader, record=record)
        self.assertEqual((row.manuscript_revision, row.manuscript_sha256),
                         (record.manuscript_revision, record.manuscript_sha256))

    def test_saving_again_moves_the_one_position(self):
        record = self.identified()

        self.put(record, page=3, fraction=0.5)
        self.put(record, page=7, fraction=0.1)

        self.assertEqual(ReadingPosition.objects.filter(owner=self.reader, record=record).count(), 1)
        self.assertEqual(self.get(record).data["position"]["page"], 7)

    def test_another_device_of_the_same_account_resumes_there(self):
        record = self.identified()
        self.put(record, self.as_user(self.reader), page=9, fraction=0.75)

        position = self.get(record, self.as_user(self.reader)).data["position"]

        self.assertEqual((position["page"], position["fraction"]), (9, 0.75))

    def test_a_malformed_position_is_refused_and_nothing_is_stored(self):
        record = self.identified()
        bad = [
            {"page": 0}, {"page": -2}, {"page": "12"}, {"page": True}, {"page": 1.5}, {"page": 10**12},
            {"fraction": -0.01}, {"fraction": 1.01}, {"fraction": "0.5"}, {"fraction": False},
            {"manuscript_revision": "not-a-uuid"},
        ]
        for overrides in bad:
            with self.subTest(overrides=overrides):
                self.assertEqual(self.put(record, **overrides).status_code, 400)
        missing = self.client.put(position_url(record), {"page": 1, "fraction": 0}, format="json")

        self.assertEqual(missing.status_code, 400)
        self.assertFalse(ReadingPosition.objects.exists())

    def test_the_ends_of_a_page_are_a_position(self):
        record = self.identified()

        self.assertEqual(self.put(record, fraction=0).status_code, 204)
        self.assertEqual(self.put(record, fraction=1).status_code, 204)


class ManuscriptIdentityTests(PositionTestCase):
    def test_a_position_for_bytes_no_longer_served_is_refused(self):
        record = self.identified()
        shown = str(record.manuscript_revision)
        self.replace_quietly(record)

        response = self.put(record, manuscript_revision=shown)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "manuscript_changed")
        self.assertFalse(ReadingPosition.objects.exists())

    def test_a_manuscript_with_no_identity_takes_no_position(self):
        record = self.record()

        response = self.put(record, manuscript_revision=str(uuid.uuid4()))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "manuscript_unavailable")
        self.assertFalse(ReadingPosition.objects.exists())

    def test_a_replaced_manuscript_never_inherits_the_old_files_place(self):
        """Replaced by a path no signal sees: the place is not given back, and goes."""
        record = self.identified()
        self.put(record, page=12)
        self.replace_quietly(record)

        response = self.get(record)

        self.assertEqual(response.data, {"position": None})
        self.assertFalse(ReadingPosition.objects.exists())

    def test_an_upload_deletes_the_positions_on_the_bytes_it_replaced(self):
        record = self.identified()
        self.put(record)
        self.put(record, self.as_user(self.other))

        self.replace_by_upload(record)

        self.assertFalse(ReadingPosition.objects.filter(record=record).exists())

    def test_removing_the_manuscript_deletes_every_position_on_it(self):
        record = self.identified()
        self.put(record)

        record.manuscript_revision = None
        record.manuscript_sha256 = ""
        record.save(update_fields=["manuscript_revision", "manuscript_sha256"])

        self.assertFalse(ReadingPosition.objects.exists())

    def test_deleting_the_record_deletes_every_position_on_it(self):
        record, kept = self.identified(), self.identified("Another paper")
        self.put(record)
        self.put(kept)

        record.delete()

        self.assertEqual(list(ReadingPosition.objects.values_list("record_id", flat=True)), [kept.id])

    def test_saving_a_record_without_new_bytes_keeps_every_position(self):
        record = self.identified()
        self.put(record)

        record.title = "A better title"
        record.save()
        record.save(update_fields=["title"])

        self.assertEqual(ReadingPosition.objects.filter(record=record).count(), 1)

    def test_the_bytes_anyone_is_still_served_keep_their_positions(self):
        """The owner reads their unsubmitted upload; everyone else the latest Version.
        Both are still served, so both places stay; only an older file's goes."""
        record = self.identified()
        submitted, sha = record.manuscript_revision, record.manuscript_sha256
        older = uuid.uuid4()
        RecordVersion.objects.create(
            record=record, number=1, cause=VersionCause.SUBMISSION,
            manuscript_revision=submitted, manuscript_sha256=sha,
        )
        on_older = ReadingPosition.objects.create(
            owner=self.author, record=record, manuscript_revision=older, manuscript_sha256="0" * 64, page=2, fraction=0,
        )
        on_submitted = ReadingPosition.objects.create(
            owner=self.reader, record=record, manuscript_revision=submitted, manuscript_sha256=sha, page=4, fraction=0,
        )

        upload = self.replace_by_upload(record)
        on_upload = ReadingPosition.objects.create(
            owner=self.author, record=record, manuscript_revision=upload,
            manuscript_sha256=record.manuscript_sha256, page=6, fraction=0,
        )
        record.save(update_fields=["manuscript_revision", "manuscript_sha256"])

        kept = set(ReadingPosition.objects.filter(record=record).values_list("pk", flat=True))
        self.assertEqual(kept, {on_submitted.pk, on_upload.pk})
        self.assertNotIn(on_older.pk, kept)

    def test_a_new_version_deletes_the_positions_on_the_one_it_supersedes(self):
        record = self.identified()
        first = record.manuscript_revision
        RecordVersion.objects.create(
            record=record, number=1, cause=VersionCause.SUBMISSION,
            manuscript_revision=first, manuscript_sha256=record.manuscript_sha256,
        )
        ReadingPosition.objects.create(
            owner=self.other, record=record, manuscript_revision=first,
            manuscript_sha256=record.manuscript_sha256, page=5, fraction=0,
        )
        second = self.replace_quietly(record)

        RecordVersion.objects.create(
            record=record, number=2, cause=VersionCause.REVISION,
            manuscript_revision=second, manuscript_sha256=record.manuscript_sha256,
        )

        self.assertFalse(ReadingPosition.objects.filter(manuscript_revision=first).exists())


class OwnershipAndVisibilityTests(PositionTestCase):
    def test_another_reader_and_the_papers_author_never_see_it(self):
        record = self.identified()
        self.put(record, page=12)

        for user in (self.other, self.author):
            with self.subTest(user=user.email):
                self.assertEqual(self.get(record, self.as_user(user)).data, {"position": None})

    def test_another_readers_save_never_moves_mine(self):
        record = self.identified()
        self.put(record, page=12)

        self.put(record, self.as_user(self.other), page=40)

        self.assertEqual(self.get(record).data["position"]["page"], 12)

    def test_an_unreadable_record_is_the_same_404_as_a_missing_one(self):
        hidden = self.identified("Someone's draft", status=PipelineStatus.DRAFT)
        missing = Record.objects.order_by("-pk").first().pk + 100

        for target in (hidden, missing):
            with self.subTest(target=target):
                self.assertEqual(self.client.get(position_url(target)).status_code, 404)
                body = {"manuscript_revision": str(uuid.uuid4()), "page": 1, "fraction": 0}
                self.assertEqual(self.client.put(position_url(target), body, format="json").status_code, 404)
        self.assertFalse(ReadingPosition.objects.exists())

    def test_a_paper_that_becomes_unreadable_withholds_its_position(self):
        record = self.identified()
        self.put(record)

        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)

        self.assertEqual(self.get(record).status_code, 404)
        self.assertEqual(self.put(record).status_code, 404)

    def test_signing_out_ends_access(self):
        record = self.identified()
        self.client.force_authenticate(None)

        self.assertEqual(self.get(record).status_code, 401)
        self.assertEqual(self.put(record).status_code, 401)


class RetentionTests(PositionTestCase):
    def test_two_hundred_records_keep_a_position(self):
        self.assertEqual(MAX_READING_POSITIONS, 200)

    def test_a_new_paper_past_the_limit_drops_the_least_recently_read(self):
        first, second, third, fourth = (self.identified(f"Paper {n}") for n in range(4))
        with mock.patch("apps.library.positions.MAX_READING_POSITIONS", 3):
            for record in (first, second, third):
                self.put(record)
            self.put(first, page=2)  # read again: now the most recent
            self.put(fourth)

        kept = set(ReadingPosition.objects.filter(owner=self.reader).values_list("record_id", flat=True))
        self.assertEqual(kept, {first.pk, third.pk, fourth.pk})

    def test_the_limit_is_per_reader(self):
        mine, theirs = self.identified("Mine"), self.identified("Theirs")
        with mock.patch("apps.library.positions.MAX_READING_POSITIONS", 1):
            self.put(theirs, self.as_user(self.other))
            self.put(mine)

        self.assertEqual(ReadingPosition.objects.count(), 2)


class NoOtherSurfaceReadsPositionsTests(PositionTestCase):
    """IR-553: private draft and review reading never becomes a discovery signal."""

    #: The library's model, its views and routes, the position rules and the
    #: receiver that deletes replaced ones, and the two account registries.
    ALLOWED = (
        "backend/apps/library/models.py",
        "backend/apps/library/views.py",
        "backend/apps/library/urls.py",
        "backend/apps/library/positions.py",
        "backend/apps/library/signals.py",
        "backend/apps/accounts/personal_data/",
        "backend/apps/accounts/deletion/",
    )
    PATTERN = r"ReadingPosition|reading_positions?|library_readingposition"

    def test_no_other_app_reads_a_position(self):
        self.assertEqual(
            offending_lines(self.PATTERN, self.ALLOWED), [],
            "IR-573: nothing outside the library may read where a reader is in a paper.",
        )

    def test_the_model_is_not_registered_in_the_django_admin(self):
        from django.contrib import admin

        self.assertNotIn(ReadingPosition, admin.site._registry)
