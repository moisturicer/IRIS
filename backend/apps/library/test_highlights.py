"""
IR-583 at the highlights API seam (ADR-065).

What this pins:

* a highlight stores the Manuscript identity it was made on (revision and
  SHA-256), the page, the quote and its regions, apart from the reader's note;
* the identity the reader claims to be looking at must still be the one the
  server serves them, so a replaced Manuscript never takes a highlight made on
  the old one -- the write is refused and nothing is stored;
* a highlight made on bytes that are no longer served is listed `stale`, and is
  never moved onto the new bytes;
* a highlight is owner-only: staff, the Record's owners and other readers never
  read, change or delete it;
* an unreadable Record withholds the quotation and the anchor, and the highlight
  is listed as unavailable with nothing but ids the reader supplied;
* nothing outside the library reads the highlight model.
"""

import pathlib
import re
import uuid

from django.conf import settings

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordVersion
from core.enums import PipelineStatus, RoleName, VersionCause

from .models import MAX_HIGHLIGHT_REGIONS, ReadingHighlight, ReadingNote
from .tests import LibraryTestCase

HIGHLIGHTS = "/api/v1/library/highlights/"
QUOTE = "Rainfall explained 62% of the variance in discharge."
REGION = {"page": 3, "left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.23}


def record_url(record_or_id):
    return f"{HIGHLIGHTS}{getattr(record_or_id, 'id', record_or_id)}/"


def item_url(record, highlight_id):
    return f"{record_url(record)}{highlight_id}/"


class HighlightTestCase(LibraryTestCase):
    def identified(self, title="Published research", **kwargs):
        """A Record whose Manuscript has an identity, as every accepted upload does."""
        record = self.record(title, **kwargs)
        self.replace_manuscript(record)
        return record

    def replace_manuscript(self, record, sha256=None):
        """New bytes were accepted: a fresh revision, as `manuscript_changes` writes."""
        Record.objects.filter(pk=record.pk).update(
            manuscript_revision=uuid.uuid4(), manuscript_sha256=sha256 or uuid.uuid4().hex * 2,
        )
        record.refresh_from_db()
        return record.manuscript_revision

    def payload(self, record, **overrides):
        body = {
            "manuscript_revision": str(record.manuscript_revision),
            "page": 3, "quote": QUOTE, "prefix": "Results. ", "suffix": " The model",
            "regions": [REGION],
        }
        body.update(overrides)
        return body

    def make(self, record, client=None, **overrides):
        return (client or self.client).post(record_url(record), self.payload(record, **overrides), format="json")

    def person(self, email, role_name):
        role = Role.objects.get_or_create(name=role_name)[0]
        return User.objects.create_user(
            email=email, password="TestPass123!", first_name="H", last_name="P", role=role,
        )

    def _as(self, user):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user)
        return client


class CreateAndReadTests(HighlightTestCase):
    def test_a_highlight_stores_the_manuscript_identity_page_quote_and_regions(self):
        record = self.identified()

        response = self.make(record)

        self.assertEqual(response.status_code, 201, response.content)
        row = ReadingHighlight.objects.get(owner=self.reader, record=record)
        self.assertEqual(row.manuscript_revision, record.manuscript_revision)
        self.assertEqual(row.manuscript_sha256, record.manuscript_sha256)
        self.assertEqual((row.page, row.quote), (3, QUOTE))
        self.assertEqual(row.regions, [REGION])
        self.assertEqual(response.data["state"], "current")
        self.assertEqual(response.data["quote"], QUOTE)
        self.assertTrue(response.data["available"])

    def test_the_highlight_is_kept_apart_from_the_readers_note(self):
        record = self.identified()
        self.client.put(
            f"/api/v1/library/notes/{record.id}/", {"body": "my own words", "base_revision": 0}, format="json",
        )

        self.make(record)

        note = ReadingNote.objects.get(owner=self.reader, record=record)
        self.assertEqual((note.body, note.revision), ("my own words", 1))
        self.assertNotIn(QUOTE, note.body)

    def test_saving_the_same_passage_twice_keeps_one_highlight(self):
        record = self.identified()

        first = self.make(record)
        again = self.make(record)

        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.data["id"], again.data["id"])
        self.assertEqual(ReadingHighlight.objects.filter(owner=self.reader, record=record).count(), 1)

    def test_a_record_lists_its_highlights_newest_first(self):
        record = self.identified()
        older = self.make(record, quote="First passage.").data["id"]
        newer = self.make(record, quote="Second passage.", page=4).data["id"]

        listed = self.client.get(record_url(record))

        self.assertEqual(listed.status_code, 200)
        self.assertEqual([h["id"] for h in listed.data["results"]], [newer, older])

    def test_a_malformed_highlight_is_refused_and_stores_nothing(self):
        record = self.identified()
        bad_region = {"page": 3, "left": 0.9, "top": 0.2, "right": 0.1, "bottom": 0.3}
        outside = {"page": 3, "left": 0.1, "top": 0.2, "right": 1.5, "bottom": 0.3}

        for overrides in (
            {"quote": ""},
            {"quote": "   "},
            {"quote": "q" * 2_001},
            {"page": 0},
            {"page": "3"},
            {"page": True},
            {"regions": [bad_region]},
            {"regions": [outside]},
            {"regions": [REGION] * (MAX_HIGHLIGHT_REGIONS + 1)},
            {"regions": "everything"},
            {"prefix": "p" * 501},
            {"manuscript_revision": "not-a-uuid"},
            {"manuscript_revision": None},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.make(record, **overrides).status_code, 400)
        self.assertFalse(ReadingHighlight.objects.exists())

    def test_a_highlight_with_no_regions_is_kept_and_opens_by_page_and_quote(self):
        # A passage the browser gave no boxes for still has a page and a quote.
        record = self.identified()

        response = self.make(record, regions=[])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["regions"], [])


class ManuscriptIdentityTests(HighlightTestCase):
    def test_a_highlight_made_on_a_replaced_manuscript_is_refused_and_stores_nothing(self):
        """The reader opened v1; v2 was accepted before they pressed Save."""
        record = self.identified()
        shown = str(record.manuscript_revision)
        self.replace_manuscript(record)

        response = self.make(record, manuscript_revision=shown)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "manuscript_changed")
        self.assertFalse(ReadingHighlight.objects.exists())

    def test_a_record_with_no_manuscript_identity_cannot_be_highlighted(self):
        record = self.record()  # never given a revision

        response = self.make(record, manuscript_revision=str(uuid.uuid4()))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "manuscript_unavailable")
        self.assertFalse(ReadingHighlight.objects.exists())

    def test_a_replaced_manuscript_makes_the_old_highlight_stale_and_never_moves_it(self):
        record = self.identified()
        old_revision = record.manuscript_revision
        old_sha = record.manuscript_sha256
        made = self.make(record).data["id"]
        self.replace_manuscript(record)

        listed = self.client.get(record_url(record)).data["results"]

        self.assertEqual([(h["id"], h["state"]) for h in listed], [(made, "stale")])
        row = ReadingHighlight.objects.get(pk=made)
        self.assertEqual((row.manuscript_revision, row.manuscript_sha256), (old_revision, old_sha))
        self.assertNotEqual(row.manuscript_revision, record.manuscript_revision)

    def test_a_stale_highlight_still_shows_its_quote_to_a_reader_who_may_read_the_record(self):
        record = self.identified()
        self.make(record)
        self.replace_manuscript(record)

        listed = self.client.get(record_url(record)).data["results"]

        self.assertEqual((listed[0]["quote"], listed[0]["page"]), (QUOTE, 3))

    def test_the_same_revision_with_different_bytes_is_stale(self):
        record = self.identified()
        self.make(record)
        Record.objects.filter(pk=record.pk).update(manuscript_sha256="f" * 64)

        listed = self.client.get(record_url(record)).data["results"]

        self.assertEqual(listed[0]["state"], "stale")

    def test_a_highlight_on_the_new_manuscript_is_current_beside_a_stale_one(self):
        record = self.identified()
        old = self.make(record).data["id"]
        self.replace_manuscript(record)

        new = self.make(record, quote="A passage in the new text.").data["id"]

        states = {h["id"]: h["state"] for h in self.client.get(record_url(record)).data["results"]}
        self.assertEqual(states, {old: "stale", new: "current"})

    def test_a_stale_highlight_names_the_version_that_still_has_its_bytes(self):
        record = self.identified()
        RecordVersion.objects.create(
            record=record, number=1, cause=VersionCause.SUBMISSION,
            manuscript_revision=record.manuscript_revision, manuscript_sha256=record.manuscript_sha256,
        )
        made = self.make(record).data["id"]
        revision = self.replace_manuscript(record)
        RecordVersion.objects.create(
            record=record, number=2, cause=VersionCause.REVISION,
            manuscript_revision=revision, manuscript_sha256=record.manuscript_sha256,
        )

        listed = {h["id"]: h for h in self.client.get(record_url(record)).data["results"]}

        self.assertEqual((listed[made]["state"], listed[made]["open_version"]), ("stale", 1))

    def test_a_current_highlight_names_no_other_version(self):
        record = self.identified()
        made = self.make(record).data

        self.assertIsNone(made["open_version"])


class OwnershipTests(HighlightTestCase):
    def test_another_reader_lists_none_of_them_and_cannot_remove_one(self):
        record = self.identified()
        made = self.make(record).data["id"]
        stranger = self._as(self.other)

        listed = stranger.get(record_url(record))
        everything = stranger.get(HIGHLIGHTS)
        removed = stranger.delete(item_url(record, made))

        self.assertEqual(listed.data["results"], [])
        self.assertEqual(everything.data["results"], [])
        self.assertNotIn(QUOTE, str(listed.content) + str(everything.content))
        self.assertEqual(removed.status_code, 204)
        self.assertTrue(ReadingHighlight.objects.filter(pk=made, owner=self.reader).exists())

    def test_nobody_else_reads_them_not_staff_not_an_administrator_not_the_records_owner(self):
        record = self.identified()
        self.make(record)
        staff = [
            self.person(f"hl-{name.value.lower().replace(' ', '')}@cit.edu", name)
            for name in (RoleName.KTTO, RoleName.RDCO, RoleName.ITSO, RoleName.IERC,
                         RoleName.ADVISER, RoleName.SYSTEM_ADMIN)
        ]
        for person in (*staff, self.author):
            with self.subTest(person=person.email):
                client = self._as(person)
                for response in (client.get(record_url(record)), client.get(HIGHLIGHTS)):
                    self.assertNotIn(QUOTE, str(response.content))
                    self.assertEqual(response.data["results"], [])

    def test_a_body_naming_another_owner_is_ignored(self):
        record = self.identified()

        self.make(record, owner=self.other.id)

        self.assertTrue(ReadingHighlight.objects.filter(owner=self.reader).exists())
        self.assertFalse(ReadingHighlight.objects.filter(owner=self.other).exists())

    def test_two_readers_hold_their_own_highlights_of_one_passage(self):
        record = self.identified()
        self.make(record)
        self.make(record, client=self._as(self.other))

        self.assertEqual(ReadingHighlight.objects.filter(record=record).count(), 2)
        self.assertEqual(len(self.client.get(record_url(record)).data["results"]), 1)

    def test_removing_a_highlight_deletes_it_and_repeating_it_is_still_a_204(self):
        record = self.identified()
        made = self.make(record).data["id"]

        first = self.client.delete(item_url(record, made))
        again = self.client.delete(item_url(record, made))

        self.assertEqual((first.status_code, again.status_code), (204, 204))
        self.assertFalse(ReadingHighlight.objects.exists())

    def test_an_anonymous_caller_is_refused(self):
        record = self.identified()
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(HIGHLIGHTS).status_code, 401)
        self.assertEqual(self.client.get(record_url(record)).status_code, 401)
        self.assertEqual(self.make(record).status_code, 401)
        self.assertEqual(self.client.delete(item_url(record, 1)).status_code, 401)


class RevokedAccessTests(HighlightTestCase):
    def revoke(self, record):
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.DRAFT)

    def test_an_unreadable_record_is_the_same_404_as_a_missing_one_to_read_or_write(self):
        draft = self.identified("Someone's draft", status=PipelineStatus.DRAFT)
        missing_id = draft.id + 10_000

        for call in (
            lambda r: self.client.get(record_url(r)),
            lambda r: self.client.post(record_url(r), self.payload(draft), format="json"),
        ):
            hidden, missing = call(draft), call(missing_id)
            self.assertEqual((hidden.status_code, missing.status_code), (404, 404))
            self.assertEqual(hidden.data, missing.data)
        self.assertFalse(ReadingHighlight.objects.exists())

    def test_revoked_access_withholds_the_quote_and_the_anchor_everywhere(self):
        record = self.identified("Later restricted")
        made = self.make(record).data["id"]
        self.revoke(record)

        per_record = self.client.get(record_url(record))
        everything = self.client.get(HIGHLIGHTS)

        self.assertEqual(per_record.status_code, 404)
        self.assertEqual(everything.status_code, 200)
        self.assertEqual(everything.data["results"], [{"id": made, "record_id": record.id, "available": False}])
        body = per_record.content.decode() + everything.content.decode()
        for secret in (QUOTE, "Results. ", "regions", "quote", "manuscript"):
            self.assertNotIn(secret, body)

    def test_a_revoked_highlight_is_kept_and_comes_back_with_access(self):
        record = self.identified("Restricted for a while")
        self.make(record)
        self.revoke(record)
        self.client.get(HIGHLIGHTS)

        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        listed = self.client.get(record_url(record)).data["results"]
        self.assertEqual((listed[0]["quote"], listed[0]["state"]), (QUOTE, "current"))

    def test_the_reader_can_still_remove_a_highlight_they_can_no_longer_open(self):
        record = self.identified()
        made = self.make(record).data["id"]
        self.revoke(record)

        self.assertEqual(self.client.delete(item_url(record, made)).status_code, 204)

        self.assertFalse(ReadingHighlight.objects.exists())
        self.assertEqual(self.client.get(HIGHLIGHTS).data["results"], [])

    def test_the_account_list_mixes_readable_and_unavailable_sources(self):
        open_record = self.identified("Still open")
        shut_record = self.identified("Shut later")
        kept = self.make(open_record).data["id"]
        gone = self.make(shut_record).data["id"]
        self.revoke(shut_record)

        results = {h["id"]: h for h in self.client.get(HIGHLIGHTS).data["results"]}

        self.assertEqual(results[kept]["quote"], QUOTE)
        self.assertTrue(results[kept]["available"])
        self.assertEqual(results[gone], {"id": gone, "record_id": shut_record.id, "available": False})

    def test_deleting_the_record_deletes_its_highlights(self):
        record = self.identified()
        self.make(record)

        Record.objects.filter(pk=record.pk).delete()

        self.assertFalse(ReadingHighlight.objects.exists())


class NoOtherSurfaceReadsHighlightsTests(HighlightTestCase):
    """A highlight quotes a paper for one reader: it is never a signal or an input."""

    ALLOWED = (
        "apps/library/",
        "apps/accounts/personal_data/",
        "apps/accounts/deletion/",
    )
    PATTERN = re.compile(r"ReadingHighlight|reading_highlights?")

    def test_no_other_app_reads_the_highlight_model(self):
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
        self.assertEqual(offenders, [], "ADR-065: nothing outside the library may read a reader's highlights.")

    def test_highlights_are_not_registered_in_the_django_admin(self):
        from django.contrib import admin

        self.assertNotIn(ReadingHighlight, admin.site._registry)
