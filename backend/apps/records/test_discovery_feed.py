"""IR-567 at the authenticated records API seam."""

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
