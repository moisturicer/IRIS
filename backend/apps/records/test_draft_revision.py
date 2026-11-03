"""Revision-checked draft edits and saved field-source decisions (IR-833).

IR-830 decision 16: Publish saves Details as the author works, and a save
made from an older view of the draft must not overwrite a newer one. Each
detail save moves `details_revision`; a save naming an older revision in
`expected_details_revision` is refused with `409 stale_edit` and changes
nothing. A save that names none is unchecked, as every client was before.

`metadata_sources` holds the author's decision about each autofilled field
(which values the dialog filled in, which they typed, accepted, cleared or
dismissed) so a reopened draft does not mistake a system placeholder for the
author's words. Only the record's owners see it.

At the REST seam, with real PostgreSQL for the race.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase

from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user
from core.enums import PipelineStatus


def _draft(owner, **fields):
    record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]
    record = Record.objects.create(
        title="My Clearance Study", record_type=record_type, added_by=owner,
        pipeline_status=PipelineStatus.DRAFT, **fields,
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    return record


class DetailsRevisionTests(APITestCase):
    def setUp(self):
        self.owner = make_user("owner@cit.edu", "Student")
        self.record = _draft(self.owner)
        self.client.force_authenticate(self.owner)
        self.url = reverse("record-detail", args=[self.record.id])

    def _revision(self):
        return self.client.get(self.url).data["details_revision"]

    def test_a_save_from_the_current_revision_is_kept_and_moves_the_revision(self):
        before = self._revision()

        response = self.client.patch(self.url, {"title": "A Better Title", "expected_details_revision": before}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["details_revision"], before + 1)
        self.assertEqual(self.client.get(self.url).data["title"], "A Better Title")

    def test_a_save_from_an_older_revision_is_refused_and_changes_nothing(self):
        stale = self._revision()
        self.client.patch(self.url, {"title": "Typed in another tab", "expected_details_revision": stale}, format="json")

        response = self.client.patch(self.url, {"title": "An older autosave", "expected_details_revision": stale}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "stale_edit")
        self.assertEqual(response.data["details_revision"], stale + 1)
        self.assertEqual(self.client.get(self.url).data["title"], "Typed in another tab")

    def test_a_save_that_names_no_revision_is_unchecked(self):
        before = self._revision()

        response = self.client.patch(self.url, {"title": "Edited on the paper page"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["details_revision"], before + 1)

    def test_the_revision_must_be_a_number(self):
        response = self.client.patch(self.url, {"title": "A Better Title", "expected_details_revision": "latest"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expected_details_revision", response.data)

    def test_a_stranger_cannot_learn_the_revision(self):
        self.client.force_authenticate(make_user("stranger@cit.edu", "Student"))

        response = self.client.patch(self.url, {"title": "x", "expected_details_revision": 0}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("details_revision", response.data)


class MetadataSourcesTests(APITestCase):
    def setUp(self):
        self.owner = make_user("owner@cit.edu", "Student")
        self.adviser = make_user("adviser@cit.edu", "Adviser")
        self.record = _draft(self.owner, adviser=self.adviser)
        self.client.force_authenticate(self.owner)
        self.url = reverse("record-detail", args=[self.record.id])

    def test_decisions_saved_with_the_values_come_back_on_reopening(self):
        sources = {
            "title": {"state": "automatic", "source_revision": "rev-1", "previous": "My Clearance Study"},
            "abstract": {"state": "authored"},
            "keywords": {"state": "dismissed", "source_revision": "rev-1"},
        }

        response = self.client.patch(self.url, {"title": "Found In The PDF", "metadata_sources": sources}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        reopened = self.client.get(self.url).data
        self.assertEqual(reopened["title"], "Found In The PDF")
        self.assertEqual(reopened["metadata_sources"], sources)

    def test_a_new_draft_can_mark_its_title_as_a_placeholder(self):
        record_type = RecordType.objects.get_or_create(name="Thesis / Research")[0]

        response = self.client.post(reverse("record-list"), {
            "title": "My Clearance Study", "record_type": record_type.pk,
            "metadata_sources": {"title": {"state": "placeholder"}},
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        detail = self.client.get(reverse("record-detail", args=[response.data["id"]])).data
        self.assertEqual(detail["metadata_sources"], {"title": {"state": "placeholder"}})

    def test_a_decision_for_an_unknown_field_or_state_is_refused(self):
        for sources in (
            {"adviser": {"state": "automatic"}},
            {"title": {"state": "guessed"}},
            {"title": "automatic"},
            {"title": {"state": "automatic", "confidence": 0.9}},
            ["title"],
        ):
            with self.subTest(sources=sources):
                response = self.client.patch(self.url, {"metadata_sources": sources}, format="json")

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("metadata_sources", response.data)

    def test_only_owners_see_the_decisions_or_the_revision(self):
        self.client.patch(self.url, {"metadata_sources": {"title": {"state": "authored"}}}, format="json")
        self.client.force_authenticate(self.adviser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["metadata_sources"])
        self.assertIsNone(response.data["details_revision"])

    def test_saving_decisions_never_changes_owners_or_routing(self):
        self.client.patch(self.url, {"metadata_sources": {"authors": {"state": "accepted", "source_revision": "rev-1"}}}, format="json")

        record = Record.objects.get(pk=self.record.pk)
        self.assertEqual(list(record.owners.values_list("user_id", flat=True)), [self.owner.pk])
        self.assertEqual(record.adviser_id, self.adviser.pk)
        self.assertFalse(record.requested_itso or record.requested_ierc or record.requested_ktto)


class ConcurrentSaveTests(APITransactionTestCase):
    def test_two_saves_from_one_revision_keep_exactly_one(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections

        owner = make_user("concurrent-owner@cit.edu", "Student")
        record = _draft(owner)
        url = reverse("record-detail", args=[record.id])
        revision = Record.objects.get(pk=record.pk).details_revision
        barrier = Barrier(2)

        def save(title):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(owner)
                barrier.wait(timeout=10)
                return client.patch(url, {"title": title, "expected_details_revision": revision}, format="json").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, ["First tab's title", "Second tab's title"]))

        self.assertEqual(sorted(results), [200, 409])
        saved = Record.objects.get(pk=record.pk)
        self.assertEqual(saved.details_revision, revision + 1)
        self.assertIn(saved.title, {"First tab's title", "Second tab's title"})
