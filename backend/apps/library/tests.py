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

from apps.accounts.models import College, Role, User
from apps.records.models import Classification, Record, RecordOwner, RecordType
from core.enums import PipelineStatus, ReadingStatus, RecordTypeName, RoleName

from .models import MAX_SAVED_FEEDS, SavedFeed, SavedRecord

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


# -- IR-577: private custom feeds ---------------------------------------------

FEEDS = "/api/v1/library/feeds/"


def feed_url(feed_or_id):
    return f"{FEEDS}{getattr(feed_or_id, 'id', feed_or_id)}/"


class SavedFeedTests(LibraryTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.flood = Classification.objects.create(name="Environmental Science")
        cls.civil = Classification.objects.create(name="Civil Engineering")
        cls.college = College.objects.create(name="College of Engineering", code="COE-F")

    def make(self, name="Coastal hazards", **query):
        query = query or {"q": "flood"}
        return self.client.post(FEEDS, {"name": name, "query": query}, format="json")

    # -- create, list, edit, delete ------------------------------------------

    def test_a_reader_saves_a_feed_and_finds_it_listed_with_its_query(self):
        response = self.make(
            "Coastal hazards",
            q="flood", classification=f"{self.civil.id},{self.flood.id}",
            college=str(self.college.id), year="2018", sort="viewed",
        )

        self.assertEqual(response.status_code, 201)
        # Ids are stored the way Discover spells them: sorted, once each.
        expected = {
            "q": "flood", "classification": f"{self.flood.id},{self.civil.id}",
            "college": str(self.college.id), "year": "2018", "sort": "viewed",
        }
        self.assertEqual(response.data["query"], expected)
        self.assertEqual(response.data["stale"], {})
        listed = self.client.get(FEEDS).data
        self.assertEqual(listed["limit"], MAX_SAVED_FEEDS)
        self.assertEqual(
            [(f["name"], f["query"]) for f in listed["results"]], [("Coastal hazards", expected)]
        )

    def test_a_feed_can_be_renamed_and_its_criteria_replaced(self):
        feed_id = self.make("Old name", q="flood").data["id"]

        renamed = self.client.patch(feed_url(feed_id), {"name": "New name"}, format="json")
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual((renamed.data["name"], renamed.data["query"]), ("New name", {"q": "flood"}))

        replaced = self.client.patch(
            feed_url(feed_id),
            {"query": {"classification": str(self.civil.id), "sort": "viewed"}},
            format="json",
        )
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(
            replaced.data["query"], {"classification": str(self.civil.id), "sort": "viewed"}
        )
        self.assertEqual(replaced.data["name"], "New name")

    def test_a_feed_can_be_deleted_and_deleting_it_again_is_a_404(self):
        feed_id = self.make().data["id"]

        self.assertEqual(self.client.delete(feed_url(feed_id)).status_code, 204)
        self.assertEqual(self.client.get(FEEDS).data["results"], [])
        self.assertEqual(self.client.delete(feed_url(feed_id)).status_code, 404)

    def test_removing_the_account_removes_its_feeds(self):
        self.make()
        self.reader.delete()

        self.assertEqual(SavedFeed.objects.count(), 0)

    # -- names -----------------------------------------------------------------

    def test_a_name_is_required_and_at_most_sixty_characters(self):
        for bad in ("", "   ", "x" * 61):
            response = self.make(bad)
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn("name", response.data)
        self.assertEqual(self.make("x" * 60).status_code, 201)
        missing = self.client.post(FEEDS, {"query": {"q": "flood"}}, format="json")
        self.assertEqual(missing.status_code, 400)

    def test_a_name_is_unique_within_the_account_ignoring_case(self):
        self.make("Coastal hazards")

        duplicate = self.make("  COASTAL hazards ")

        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("name", duplicate.data)
        self.assertEqual(SavedFeed.objects.filter(owner=self.reader).count(), 1)
        # Another account may use the same name.
        self.client.force_authenticate(self.other)
        self.assertEqual(self.make("Coastal hazards").status_code, 201)

    def test_renaming_to_another_feeds_name_is_refused_but_recasing_ones_own_is_not(self):
        self.make("Alpha")
        beta = self.make("Beta").data["id"]

        clash = self.client.patch(feed_url(beta), {"name": "alpha"}, format="json")
        self.assertEqual(clash.status_code, 400)
        self.assertIn("name", clash.data)
        recased = self.client.patch(feed_url(beta), {"name": "BETA"}, format="json")
        self.assertEqual(recased.status_code, 200)

    def test_the_database_allows_one_name_per_account_ignoring_case(self):
        SavedFeed.objects.create(owner=self.reader, name="Alpha", query={"q": "x"})

        with self.assertRaises(IntegrityError), transaction.atomic():
            SavedFeed.objects.create(owner=self.reader, name="ALPHA", query={"q": "y"})

    # -- criteria --------------------------------------------------------------

    def test_a_feed_needs_at_least_one_criterion(self):
        for query in ({}, {"sort": "viewed"}, {"q": "   "}):
            response = self.client.post(FEEDS, {"name": "Empty", "query": query}, format="json")
            self.assertEqual(response.status_code, 400, query)
            self.assertIn("query", response.data)
        self.assertEqual(SavedFeed.objects.count(), 0)

    def test_every_value_is_checked_and_nothing_is_written_when_one_is_wrong(self):
        bad_queries = [
            {"classification": "999999"},
            {"classification": f"{self.flood.id},999999"},
            {"college": "999999"},
            {"type": "999999"},
            {"classification": "abc"},
            {"year": "20x8"},
            {"year": "208"},
            {"ip": "bogus"},
            {"sort": "bogus"},
            {"q": "flood", "feed": "for_you"},  # a tab is not a criterion
            {"q": "flood", "psced": "1"},       # not a Discover key
            "flood",
            ["flood"],
        ]
        for query in bad_queries:
            response = self.client.post(FEEDS, {"name": "Bad", "query": query}, format="json")
            self.assertEqual(response.status_code, 400, query)
            self.assertIn("query", response.data, query)
        self.assertEqual(SavedFeed.objects.count(), 0)

    def test_the_ip_filter_and_record_type_are_accepted(self):
        ok = self.make("IP", ip="has_ip", type=str(self.thesis.id))
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(self.make("Patents", ip="patent").status_code, 201)

    # -- the limit -------------------------------------------------------------

    def test_the_account_limit_refuses_the_next_feed_and_deleting_one_makes_room(self):
        ids = [self.make(f"Feed {n}").data["id"] for n in range(MAX_SAVED_FEEDS)]

        refused = self.make("One too many")

        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.data["code"], "feed_limit")
        self.assertEqual(
            refused.data["detail"],
            f"You have {MAX_SAVED_FEEDS} saved feeds. Delete one to save another.",
        )
        self.assertEqual(SavedFeed.objects.filter(owner=self.reader).count(), MAX_SAVED_FEEDS)

        self.client.delete(feed_url(ids[0]))
        self.assertEqual(self.make("One too many").status_code, 201)

    def test_the_limit_is_per_account_and_does_not_block_edits(self):
        ids = [self.make(f"Feed {n}").data["id"] for n in range(MAX_SAVED_FEEDS)]

        renamed = self.client.patch(feed_url(ids[0]), {"name": "Renamed"}, format="json")
        self.assertEqual(renamed.status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.make("Mine").status_code, 201)

    # -- stale values are corrected, never widened -----------------------------

    def test_a_deleted_taxonomy_value_is_reported_stale_and_never_dropped(self):
        gone = Classification.objects.create(name="Retired Area")
        gone_id = gone.id
        feed_id = self.make(
            "Mixed", classification=f"{self.flood.id},{gone_id}", q="flood"
        ).data["id"]
        gone.delete()

        listed = self.client.get(FEEDS).data["results"][0]

        # The stored query is untouched, so nothing silently widens.
        self.assertEqual(listed["query"]["classification"], f"{self.flood.id},{gone_id}")
        self.assertEqual(listed["stale"], {"classification": [gone_id]})

        # Renaming does not touch the criteria, so it works while they are stale.
        renamed = self.client.patch(feed_url(feed_id), {"name": "Mixed 2"}, format="json")
        self.assertEqual(renamed.status_code, 200)
        # Re-saving the stale value is refused: it has to be corrected first.
        still_stale = self.client.patch(
            feed_url(feed_id),
            {"query": {"classification": f"{self.flood.id},{gone_id}"}},
            format="json",
        )
        self.assertEqual(still_stale.status_code, 400)
        # Removing it corrects the feed, and the report clears.
        fixed = self.client.patch(
            feed_url(feed_id),
            {"query": {"classification": str(self.flood.id), "q": "flood"}},
            format="json",
        )
        self.assertEqual(fixed.status_code, 200)
        self.assertEqual(fixed.data["stale"], {})

    def test_a_deleted_college_is_reported_stale_too(self):
        college = College.objects.create(name="Gone college", code="GONE-1")
        college_id = college.id
        self.make("C", college=str(college_id))
        college.delete()

        listed = self.client.get(FEEDS).data["results"][0]

        self.assertEqual(listed["query"], {"college": str(college_id)})
        self.assertEqual(listed["stale"], {"college": [college_id]})

    # -- ownership -------------------------------------------------------------

    def test_the_list_holds_only_the_callers_own_feeds(self):
        self.make("Mine")
        self.client.force_authenticate(self.other)
        self.make("Theirs")

        self.assertEqual([f["name"] for f in self.client.get(FEEDS).data["results"]], ["Theirs"])

    def test_another_readers_feed_reads_exactly_like_a_missing_one(self):
        mine = self.make("Mine").data["id"]
        self.client.force_authenticate(self.other)

        for call in (
            lambda pk: self.client.patch(feed_url(pk), {"name": "Hijacked"}, format="json"),
            lambda pk: self.client.delete(feed_url(pk)),
        ):
            hidden, missing = call(mine), call(mine + 1000)
            self.assertEqual(hidden.status_code, 404)
            self.assertEqual(hidden.data, missing.data)
        self.assertEqual(SavedFeed.objects.get(pk=mine).name, "Mine")

    def test_a_body_naming_another_owner_is_ignored(self):
        response = self.client.post(
            FEEDS,
            {"name": "Mine", "query": {"q": "flood"}, "owner": self.other.id, "owner_id": self.other.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(SavedFeed.objects.get(pk=response.data["id"]).owner_id, self.reader.id)

    def test_two_accounts_on_one_client_never_see_each_others_feeds(self):
        shared_pc = APIClient()
        shared_pc.force_authenticate(self.reader)
        shared_pc.post(FEEDS, {"name": "Readers", "query": {"q": "flood"}}, format="json")
        shared_pc.force_authenticate(self.other)

        self.assertEqual(shared_pc.get(FEEDS).data["results"], [])

    def test_an_anonymous_caller_is_refused(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(FEEDS).status_code, 401)
        post = self.client.post(FEEDS, {"name": "x", "query": {"q": "y"}}, format="json")
        self.assertEqual(post.status_code, 401)
