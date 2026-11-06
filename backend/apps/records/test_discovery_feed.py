"""IR-567, IR-575 and IR-576 at the authenticated records API seam."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import (
    Classification, PSCEDClassification, Record, RecordOwner, RecordType,
)
from core.enums import PipelineStatus, RecordTypeName, RoleName


FEED = "/api/v1/records/for-you/"
INTERESTS = "/api/v1/records/interests/"


def not_interested(record):
    return f"/api/v1/records/{record.id}/not-interested/"


def save_url(record):
    return f"/api/v1/library/saves/{record.id}/"


class DiscoveryFeedTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        role = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        cls.reader = User.objects.create_user(
            email="discovery-reader@cit.edu", password="TestPass123!",
            first_name="A", last_name="Reader", role=role,
        )
        cls.other = User.objects.create_user(
            email="other-reader@cit.edu", password="TestPass123!",
            first_name="B", last_name="Reader", role=role,
        )
        cls.thesis = RecordType.objects.get(name=RecordTypeName.THESIS_RESEARCH)
        cls.agriculture = Classification.objects.create(name="Agriculture")
        cls.computing = Classification.objects.create(name="Computer Science")
        cls.psced = PSCEDClassification.objects.create(name="Education")

    def setUp(self):
        self.client.force_authenticate(self.reader)

    def record(self, title, *, classification=None, psced=None, days_old=0,
               status=PipelineStatus.PUBLISHED, owner=None):
        record = Record.objects.create(
            title=title, abstract="An abstract.", record_type=self.thesis,
            added_by=owner or self.other, pipeline_status=status,
            classification=classification, psced=psced,
            year_accomplished=2001 if days_old else 2026,
        )
        RecordOwner.objects.create(record=record, user=owner or self.other, is_primary=True)
        Record.objects.filter(pk=record.pk).update(
            created_at=timezone.now() - timedelta(days=days_old)
        )
        return record

    def test_no_interests_is_honestly_latest_and_older_work_remains_eligible(self):
        older = self.record("Older research", days_old=5000)
        newer = self.record("Newer research")
        self.record("Private draft", status=PipelineStatus.DRAFT, owner=self.reader)

        response = self.client.get(FEED)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mode"], "latest")
        self.assertEqual([row["id"] for row in response.data["results"]], [newer.id, older.id])
        self.assertEqual(
            [row["reason"] for row in response.data["results"]],
            [{"kind": "latest"}, {"kind": "latest"}],
        )

    def test_selected_areas_round_robin_by_stable_area_id_with_actual_reasons(self):
        ag_old = self.record("Agriculture older", classification=self.agriculture, days_old=5000)
        ag_new = self.record("Agriculture new", classification=self.agriculture)
        cs_old = self.record("Computing older", classification=self.computing, days_old=4000)
        cs_new = self.record("Computing new", classification=self.computing)
        unmatched = self.record("Unmatched newest")

        saved = self.client.put(
            INTERESTS,
            {"classification_ids": [self.computing.id, self.agriculture.id], "psced_ids": []},
            format="json",
        )
        self.assertEqual(saved.status_code, 200)
        response = self.client.get(FEED)

        self.assertEqual(response.data["mode"], "for_you")
        self.assertEqual(
            [row["id"] for row in response.data["results"]],
            [ag_new.id, cs_new.id, ag_old.id, cs_old.id, unmatched.id],
        )
        self.assertEqual(
            [row["reason"] for row in response.data["results"]],
            [
                {"kind": "selected_area", "area": "Agriculture"},
                {"kind": "selected_area", "area": "Computer Science"},
                {"kind": "selected_area", "area": "Agriculture"},
                {"kind": "selected_area", "area": "Computer Science"},
                {"kind": "latest"},
            ],
        )

    def test_psced_selection_and_unknown_areas(self):
        match = self.record("PSCED match", psced=self.psced)
        invalid = self.client.put(
            INTERESTS, {"classification_ids": [999999], "psced_ids": []}, format="json"
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.client.get(INTERESTS).data["classifications"], [])

        saved = self.client.put(
            INTERESTS, {"classification_ids": [], "psced_ids": [self.psced.id]}, format="json"
        )
        self.assertEqual(saved.status_code, 200)
        row = self.client.get(FEED).data["results"][0]
        self.assertEqual(row["id"], match.id)
        self.assertEqual(row["reason"], {"kind": "selected_area", "area": "Education"})

    def test_catalogue_filters_narrow_for_you_before_ranking(self):
        self.record("Agriculture", classification=self.agriculture)
        computing = self.record("Computing", classification=self.computing)
        self.record("Older computing", classification=self.computing, days_old=5000)
        self.client.put(
            INTERESTS,
            {"classification_ids": [self.agriculture.id, self.computing.id], "psced_ids": []},
            format="json",
        )

        response = self.client.get(FEED, {"classification": str(self.computing.id), "year_from": 2026, "year_to": 2026})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mode"], "for_you")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual([row["id"] for row in response.data["results"]], [computing.id])
        self.assertEqual(response.data["results"][0]["reason"], {"kind": "selected_area", "area": "Computer Science"})

    def test_ties_and_records_in_two_selected_taxonomies_do_not_repeat(self):
        first = self.record("Agriculture first", classification=self.agriculture)
        second = self.record("Agriculture second", classification=self.agriculture, psced=self.psced)
        psced_only = self.record("PSCED only", psced=self.psced)
        computing = self.record("Computing", classification=self.computing)
        tied_time = timezone.now() - timedelta(days=10)
        Record.objects.filter(pk__in=[first.id, second.id, psced_only.id, computing.id]).update(
            created_at=tied_time
        )
        self.client.put(
            INTERESTS,
            {
                "classification_ids": [self.computing.id, self.agriculture.id],
                "psced_ids": [self.psced.id],
            },
            format="json",
        )

        rows = self.client.get(FEED).data["results"]
        first_round = {
            ("classification", self.agriculture.id): second.id,
            ("classification", self.computing.id): computing.id,
            ("psced", self.psced.id): psced_only.id,
        }
        area_order = sorted(first_round, key=lambda area: (area[1], area[0]))
        self.assertEqual(
            [row["id"] for row in rows],
            [first_round[area] for area in area_order] + [first.id],
        )
        self.assertEqual(
            next(row["reason"] for row in rows if row["id"] == second.id),
            {"kind": "selected_area", "area": "Agriculture"},
        )

    def test_snapshot_is_owned_stale_after_interest_change_and_rechecks_visibility(self):
        records = [self.record(f"Record {i}") for i in range(23)]
        first = self.client.get(FEED).data
        self.assertEqual(len(first["results"]), 20)
        self.assertIsNotNone(first["next_cursor"])
        first_ids = {row["id"] for row in first["results"]}

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(FEED, {"cursor": first["next_cursor"]}).status_code, 400)
        self.client.force_authenticate(self.reader)

        # A Record already frozen into the next page becomes unavailable.
        hidden = next(record for record in records if record.id not in first_ids)
        Record.objects.filter(pk=hidden.id).update(pipeline_status=PipelineStatus.DRAFT)
        second = self.client.get(FEED, {"cursor": first["next_cursor"]})
        self.assertEqual(second.status_code, 200)
        second_ids = [row["id"] for row in second.data["results"]]
        self.assertNotIn(hidden.id, second_ids)
        self.assertFalse(first_ids.intersection(second_ids))

        self.client.put(
            INTERESTS, {"classification_ids": [self.agriculture.id], "psced_ids": []},
            format="json",
        )
        stale = self.client.get(FEED, {"cursor": first["next_cursor"]})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "stale_cursor")

    def test_filtered_cursor_keeps_its_original_criteria(self):
        self.record("Agriculture", classification=self.agriculture)
        for index in range(21):
            self.record(f"Computing {index}", classification=self.computing)

        first = self.client.get(FEED, {"classification": self.computing.id}).data
        second = self.client.get(
            FEED, {"cursor": first["next_cursor"], "classification": self.agriculture.id}
        ).data

        self.assertEqual(first["count"], 21)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(second["results"][0]["classification_name"], "Computer Science")

    def test_interests_are_private_to_each_account(self):
        self.client.put(
            INTERESTS, {"classification_ids": [self.agriculture.id], "psced_ids": []},
            format="json",
        )
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(INTERESTS).data["classifications"], [])
        self.assertEqual(self.client.get(FEED).data["mode"], "latest")

    # ── IR-576: Not interested, Undo and reset ──────────────────────────────

    def test_not_interested_removes_at_once_and_persists_without_staling_the_cursor(self):
        records = [self.record(f"Record {i}") for i in range(23)]
        first = self.client.get(FEED).data
        first_ids = {row["id"] for row in first["results"]}
        later = next(record for record in records if record.id not in first_ids)

        dismissed = self.client.post(not_interested(later))
        self.assertEqual(dismissed.status_code, 201)
        self.assertEqual(self.client.post(not_interested(later)).status_code, 200)

        # The page already frozen in the snapshot drops it, and the cursor still works.
        second = self.client.get(FEED, {"cursor": first["next_cursor"]})
        self.assertEqual(second.status_code, 200)
        self.assertNotIn(later.id, [row["id"] for row in second.data["results"]])
        self.assertEqual(second.data["count"], 22)

        # A new snapshot leaves it out from the start.
        fresh = self.client.get(FEED).data
        self.assertEqual(fresh["count"], 22)
        self.assertNotIn(later.id, [row["id"] for row in fresh["results"]])

    def test_undo_restores_the_item_under_a_fresh_snapshot(self):
        for i in range(21):
            self.record(f"Record {i}")
        target = self.record("Newest")
        self.client.post(not_interested(target))
        before = self.client.get(FEED).data
        self.assertNotIn(target.id, [row["id"] for row in before["results"]])

        undone = self.client.delete(not_interested(target))
        self.assertEqual(undone.status_code, 204)

        stale = self.client.get(FEED, {"cursor": before["next_cursor"]})
        self.assertEqual(stale.status_code, 409)
        after = self.client.get(FEED).data
        self.assertEqual(after["results"][0]["id"], target.id)
        # Undoing something never dismissed is harmless.
        self.assertEqual(self.client.delete(not_interested(target)).status_code, 204)

    def test_not_interested_needs_a_record_the_reader_can_read(self):
        hidden = self.record("Someone else's draft", status=PipelineStatus.DRAFT)

        self.assertEqual(self.client.post(not_interested(hidden)).status_code, 404)
        Record.objects.filter(pk=hidden.pk).update(pipeline_status=PipelineStatus.PUBLISHED)
        self.assertIn(hidden.id, [row["id"] for row in self.client.get(FEED).data["results"]])

    def test_reset_clears_areas_and_feedback_and_invalidates_the_feed(self):
        for i in range(21):
            self.record(f"Record {i}")
        dismissed = self.record("Dismissed", classification=self.agriculture)
        self.client.put(
            INTERESTS, {"classification_ids": [self.agriculture.id], "psced_ids": []},
            format="json",
        )
        self.client.post(not_interested(dismissed))
        before = self.client.get(FEED).data
        self.assertIsNotNone(before["next_cursor"])

        reset = self.client.delete(INTERESTS)

        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.data, {"classifications": [], "psced": []})
        self.assertEqual(self.client.get(INTERESTS).data, {"classifications": [], "psced": []})
        self.assertEqual(self.client.get(FEED, {"cursor": before["next_cursor"]}).status_code, 409)
        after = self.client.get(FEED).data
        self.assertEqual(after["mode"], "latest")
        self.assertEqual(after["results"][0]["id"], dismissed.id)

    def test_feedback_belongs_to_one_account(self):
        shared = self.record("Shared")
        self.client.post(not_interested(shared))

        self.client.force_authenticate(self.other)
        self.assertIn(shared.id, [row["id"] for row in self.client.get(FEED).data["results"]])
        self.client.delete(INTERESTS)
        self.client.delete(not_interested(shared))

        self.client.force_authenticate(self.reader)
        self.assertNotIn(shared.id, [row["id"] for row in self.client.get(FEED).data["results"]])

    # ── IR-575: saved research shapes For you ───────────────────────────────

    def save(self, record, reading_status=None):
        body = {"reading_status": reading_status} if reading_status else {}
        response = self.client.put(save_url(record), body, format="json")
        self.assertIn(response.status_code, (200, 201))
        return response

    def ids(self, response):
        return [row["id"] for row in response.data["results"]]

    def reasons(self, response):
        return [row["reason"] for row in response.data["results"]]

    def test_a_saved_record_makes_its_area_an_interest_with_its_own_reason(self):
        saved = self.record("Agriculture saved", classification=self.agriculture, days_old=100)
        fresh = self.record("Agriculture new", classification=self.agriculture)
        unmatched = self.record("Unmatched newest")
        self.save(saved)

        response = self.client.get(FEED)

        self.assertEqual(response.data["mode"], "for_you")
        # Latest alone would put the unmatched Record first.
        self.assertEqual(self.ids(response), [fresh.id, saved.id, unmatched.id])
        self.assertEqual(
            self.reasons(response),
            [
                {"kind": "saved_area", "area": "Agriculture"},
                {"kind": "saved_area", "area": "Agriculture"},
                {"kind": "latest"},
            ],
        )

    def test_saved_psced_area_counts_and_a_save_without_an_area_adds_nothing(self):
        saved = self.record("PSCED saved", psced=self.psced, days_old=100)
        match = self.record("PSCED match", psced=self.psced, days_old=50)
        self.save(saved)
        self.save(self.record("No area at all"))

        response = self.client.get(FEED)

        self.assertEqual(response.data["mode"], "for_you")
        self.assertEqual(self.ids(response)[0], match.id)
        self.assertEqual(self.reasons(response)[0], {"kind": "saved_area", "area": "Education"})

        # With only the area-less save left there is no signal, so the feed says so.
        self.client.delete(save_url(saved))
        self.assertEqual(self.client.get(FEED).data["mode"], "latest")

    def test_saved_and_chosen_areas_share_the_rotation_and_a_chosen_area_keeps_its_reason(self):
        ag_saved = self.record("Agriculture saved", classification=self.agriculture, days_old=100)
        ag_new = self.record("Agriculture new", classification=self.agriculture)
        cs_new = self.record("Computing new", classification=self.computing)
        cs_old = self.record("Computing older", classification=self.computing, days_old=4000)
        self.client.put(
            INTERESTS, {"classification_ids": [self.computing.id], "psced_ids": []}, format="json"
        )
        self.save(ag_saved)

        response = self.client.get(FEED)

        # Unsaved Records rotate across both Areas in stable Area-ID order
        # (Agriculture was created first); the saved one comes after them all.
        self.assertEqual(self.ids(response), [ag_new.id, cs_new.id, cs_old.id, ag_saved.id])
        self.assertEqual(
            self.reasons(response),
            [
                {"kind": "saved_area", "area": "Agriculture"},
                {"kind": "selected_area", "area": "Computer Science"},
                {"kind": "selected_area", "area": "Computer Science"},
                {"kind": "saved_area", "area": "Agriculture"},
            ],
        )

        # Saving a Record in an Area the reader already chose changes no reason.
        self.save(cs_new)
        again = self.client.get(FEED)
        self.assertEqual(
            {row["id"]: row["reason"] for row in again.data["results"]}[cs_new.id],
            {"kind": "selected_area", "area": "Computer Science"},
        )

    def test_saved_and_completed_records_come_after_new_ones_in_their_area(self):
        saved = self.record("Saved", classification=self.agriculture)
        completed = self.record("Completed", classification=self.agriculture, days_old=10)
        unread = self.record("Unread", classification=self.agriculture, days_old=20)
        oldest = self.record("Unread oldest", classification=self.agriculture, days_old=5000)
        self.client.put(
            INTERESTS, {"classification_ids": [self.agriculture.id], "psced_ids": []},
            format="json",
        )
        self.save(saved)
        self.save(completed, "completed")

        response = self.client.get(FEED)

        # Older research stays eligible; only the saved ones move, keeping their own order.
        self.assertEqual(self.ids(response), [unread.id, oldest.id, saved.id, completed.id])

    def test_saved_records_come_after_new_ones_across_areas_too(self):
        ag_saved = self.record("Agriculture saved", classification=self.agriculture)
        cs_new = self.record("Computing new", classification=self.computing, days_old=10)
        cs_old = self.record("Computing older", classification=self.computing, days_old=4000)
        self.client.put(
            INTERESTS,
            {"classification_ids": [self.agriculture.id, self.computing.id], "psced_ids": []},
            format="json",
        )
        self.save(ag_saved)

        # A saved Record in a short Area must not outrank new ones in a longer Area.
        self.assertEqual(self.ids(self.client.get(FEED)), [cs_new.id, cs_old.id, ag_saved.id])

    def test_a_record_in_a_chosen_area_is_explained_by_it_even_when_a_saved_area_holds_it_too(self):
        saved = self.record("Agriculture saved", classification=self.agriculture, days_old=100)
        both = self.record(
            "Agriculture and Education", classification=self.agriculture, psced=self.psced
        )
        self.client.put(
            INTERESTS, {"classification_ids": [], "psced_ids": [self.psced.id]}, format="json"
        )
        self.save(saved)

        response = self.client.get(FEED)

        self.assertEqual(self.ids(response), [both.id, saved.id])
        self.assertEqual(
            self.reasons(response),
            [
                {"kind": "selected_area", "area": "Education"},
                {"kind": "saved_area", "area": "Agriculture"},
            ],
        )

    def test_a_dismissed_record_still_contributes_the_area_it_was_saved_in(self):
        saved = self.record("Saved then dismissed", classification=self.agriculture, days_old=100)
        match = self.record("Agriculture match", classification=self.agriculture, days_old=50)
        unmatched = self.record("Unmatched newest")
        self.save(saved)
        self.client.post(not_interested(saved))

        response = self.client.get(FEED)

        # Unsaving and Not interested are independent: the dismissal removes the
        # item, and the save still speaks for its Area.
        self.assertEqual(self.ids(response), [match.id, unmatched.id])
        self.assertEqual(self.reasons(response)[0], {"kind": "saved_area", "area": "Agriculture"})

    def test_a_save_the_reader_can_no_longer_read_stops_being_a_signal(self):
        saved = self.record("Agriculture saved", classification=self.agriculture, days_old=100)
        match = self.record("Agriculture match", classification=self.agriculture, days_old=50)
        unmatched = self.record("Unmatched newest")
        self.save(saved)
        self.assertEqual(self.client.get(FEED).data["mode"], "for_you")

        Record.objects.filter(pk=saved.pk).update(pipeline_status=PipelineStatus.DRAFT)
        response = self.client.get(FEED)

        self.assertEqual(response.data["mode"], "latest")
        self.assertEqual(self.ids(response), [unmatched.id, match.id])
        self.assertEqual(self.reasons(response), [{"kind": "latest"}, {"kind": "latest"}])

    def test_a_snapshot_stops_naming_a_signal_whose_record_was_withdrawn_after_it_was_frozen(self):
        saved = self.record("Agriculture saved", classification=self.agriculture, days_old=100)
        for index in range(22):
            self.record(f"Agriculture {index}", classification=self.agriculture)
        self.save(saved)
        first = self.client.get(FEED).data
        self.assertEqual({row["reason"]["kind"] for row in first["results"]}, {"saved_area"})

        Record.objects.filter(pk=saved.pk).update(pipeline_status=PipelineStatus.DRAFT)
        second = self.client.get(FEED, {"cursor": first["next_cursor"]})

        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["results"])
        for row in second.data["results"]:
            self.assertEqual(row["reason"], {"kind": "latest"})

    def test_changing_saves_invalidates_the_snapshot_but_repeating_one_does_not(self):
        for index in range(22):
            self.record(f"Record {index}")
        target = self.record("Target", classification=self.agriculture)
        cursor = self.client.get(FEED).data["next_cursor"]
        self.assertIsNotNone(cursor)

        self.save(target)
        self.assertEqual(self.client.get(FEED, {"cursor": cursor}).status_code, 409)

        cursor = self.client.get(FEED).data["next_cursor"]
        self.save(target)  # Already saved, nothing changed.
        self.assertEqual(self.client.get(FEED, {"cursor": cursor}).status_code, 200)

        self.save(target, "completed")  # A status moves it down, so the order may change.
        self.assertEqual(self.client.get(FEED, {"cursor": cursor}).status_code, 409)

        cursor = self.client.get(FEED).data["next_cursor"]
        self.client.put(save_url(target), {"reading_status": None}, format="json")
        self.assertEqual(self.client.get(FEED, {"cursor": cursor}).status_code, 409)

        cursor = self.client.get(FEED).data["next_cursor"]
        self.assertEqual(self.client.delete(save_url(target)).status_code, 204)
        self.assertEqual(self.client.get(FEED, {"cursor": cursor}).status_code, 409)

        cursor = self.client.get(FEED).data["next_cursor"]
        self.assertEqual(self.client.delete(save_url(target)).status_code, 204)  # Nothing to remove.
        self.assertEqual(self.client.get(FEED, {"cursor": cursor}).status_code, 200)

    def test_one_readers_saves_never_shape_anothers_feed(self):
        saved = self.record("Agriculture saved", classification=self.agriculture, days_old=100)
        match = self.record("Agriculture match", classification=self.agriculture, days_old=50)
        unmatched = self.record("Unmatched newest")
        self.save(saved)

        self.client.force_authenticate(self.other)
        response = self.client.get(FEED)

        self.assertEqual(response.data["mode"], "latest")
        self.assertEqual(self.ids(response), [unmatched.id, match.id, saved.id])
        self.assertEqual(self.reasons(response), [{"kind": "latest"}] * 3)

    def test_for_you_rows_carry_what_the_discover_card_needs(self):
        saved = self.record("Agriculture saved", classification=self.agriculture)
        self.save(saved)

        row = self.client.get(FEED).data["results"][0]

        self.assertEqual(row["abstract"], "An abstract.")
        self.assertIn("has_manuscript", row)
