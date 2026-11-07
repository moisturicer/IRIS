"""
KTTO's release of an IP-marked paper (ADR-052 decisions 11 to 13, IR-813).

The mark stays on the paper and the release is its own stamp, so a marked paper
reaches the AI only once KTTO has acted. Three things are pinned hardest. No one
but KTTO releases, not RDCO, not the Adviser and not an owner. `tags/` can no
longer clear the mark, which would open the check with no release. And the IP
mark and the embargo are independent: each needs its own release, and consent
still applies.
"""

from datetime import timedelta
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.ai.policy.disclosure import Reason
from apps.ai.policy.records import decision_for_record
from apps.audit.models import AuditEvent
from core.enums import PipelineStatus, RecordTypeName, RoleName

from . import ip_release
from .models import Record, RecordOwner, RecordType
from .tests import make_user


class IpReleaseFixtures:
    @classmethod
    def setUpTestData(cls):
        cls.record_type = RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0]
        cls.owner = make_user("ip-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("ip-adviser@cit.edu", RoleName.ADVISER)
        cls.ktto = make_user("ip-ktto@cit.edu", RoleName.KTTO)
        cls.rdco = make_user("ip-rdco@cit.edu", RoleName.RDCO)
        cls.itso = make_user("ip-itso@cit.edu", RoleName.ITSO)
        cls.ierc = make_user("ip-ierc@cit.edu", RoleName.IERC)
        cls.reader = make_user("ip-reader@cit.edu", RoleName.STUDENT)

    def _paper(self, status_=PipelineStatus.PUBLISHED, *, is_ip=True, until=None,
               embargo_released=False, consent=True, ip_released=False):
        """A paper that would reach the AI but for what a test asks for."""
        now = timezone.now()
        stamps = {}
        if consent:
            stamps.update(dpa_accepted_at=now, dpa_accepted_by=self.owner)
        if until is not None:
            stamps.update(embargoed_until=until, embargo_date_set_at=now,
                          embargo_date_set_by=self.adviser)
        # Released unless a test dates an embargo and doesn't release it (IR-882).
        if embargo_released or until is None:
            stamps.update(is_embargoed=False, embargo_released_at=now,
                          embargo_released_by=self.adviser)
        if ip_released:
            stamps.update(ip_released_at=now, ip_released_by=self.ktto)
        record = Record.objects.create(
            title="An IP paper", abstract="An abstract long enough to read.",
            record_type=self.record_type, added_by=self.owner, adviser=self.adviser,
            pipeline_status=status_, is_ip=is_ip, **stamps,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record


def _in_days(days):
    return timezone.localdate() + timedelta(days=days)


class AReleaseNeedsItsMarkTests(IpReleaseFixtures, TestCase):
    """Decision 11's "marking a paper as IP again needs a new release"."""

    def test_a_release_cannot_outlive_the_mark(self):
        record = self._paper(ip_released=True)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Record.objects.filter(pk=record.pk).update(is_ip=False)

    def test_an_unmarked_paper_cannot_hold_a_release(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._paper(is_ip=False, ip_released=True)

    def test_a_paper_marked_again_starts_unreleased(self):
        record = self._paper(ip_released=True)
        Record.objects.filter(pk=record.pk).update(
            is_ip=False, ip_released_at=None, ip_released_by=None,
        )
        Record.objects.filter(pk=record.pk).update(is_ip=True)
        record.refresh_from_db()

        self.assertEqual(decision_for_record(record).reasons, (Reason.UNRELEASED_IP,))


class ReleaseBase(IpReleaseFixtures, APITestCase):
    def _release(self, record, user):
        self.client.force_authenticate(user)
        return self.client.post(reverse("record-ip-release", args=[record.pk]), {}, format="json")


class WhoReleasesTests(ReleaseBase):
    def test_ktto_releases_it_with_who_and_when_and_the_mark_stays(self):
        record = self._paper()
        self.assertEqual(decision_for_record(record).reasons, (Reason.UNRELEASED_IP,))

        response = self._release(record, self.ktto)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {"marked": True, "released": True})
        record.refresh_from_db()
        self.assertTrue(record.is_ip)
        self.assertEqual(record.ip_released_by, self.ktto)
        self.assertIsNotNone(record.ip_released_at)
        self.assertTrue(decision_for_record(record).allowed)

    def test_no_one_else_can_not_rdco_nor_the_adviser_nor_an_owner(self):
        for user in (self.rdco, self.itso, self.ierc, self.adviser, self.owner):
            with self.subTest(user=user.email):
                record = self._paper()

                response = self._release(record, user)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                record.refresh_from_db()
                self.assertFalse(record.ip_released)

    def test_a_reader_of_the_published_paper_cannot(self):
        record = self._paper()

        self.assertEqual(self._release(record, self.reader).status_code, status.HTTP_403_FORBIDDEN)

    def test_a_paper_they_cannot_see_reads_as_missing(self):
        record = self._paper(PipelineStatus.IN_REVIEW)

        self.assertEqual(self._release(record, self.reader).status_code, status.HTTP_404_NOT_FOUND)

    def test_who_may_ask_is_checked_before_what_there_is_to_release(self):
        record = self._paper(is_ip=False)

        self.assertEqual(self._release(record, self.rdco).status_code, status.HTTP_403_FORBIDDEN)


class WhatCanBeReleasedTests(ReleaseBase):
    def test_an_unmarked_paper_has_nothing_to_release(self):
        record = self._paper(is_ip=False)

        response = self._release(record, self.ktto)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        record.refresh_from_db()
        self.assertFalse(record.ip_released)

    def test_a_released_mark_is_not_released_twice(self):
        record = self._paper(ip_released=True)
        first = Record.objects.get(pk=record.pk).ip_released_at

        response = self._release(record, self.ktto)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        record.refresh_from_db()
        self.assertEqual(record.ip_released_at, first)

    def test_a_draft_cannot_be_released(self):
        record = self._paper(PipelineStatus.DRAFT)

        response = self._release(record, self.ktto)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], ip_release.DRAFT_HAS_NOTHING_TO_RELEASE)
        record.refresh_from_db()
        self.assertFalse(record.ip_released)

    def test_a_paper_in_review_can_be_released(self):
        record = self._paper(PipelineStatus.IN_REVIEW)

        self.assertEqual(self._release(record, self.ktto).status_code, status.HTTP_200_OK)


QUEUE = "apps.ai.tasks.index_record.delay"


class SendingItOnTests(ReleaseBase):
    def test_it_queues_the_paper_for_indexing(self):
        record = self._paper()

        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            self._release(record, self.ktto)

        queue.assert_called_once_with(record.pk)

    def test_a_refused_release_sends_nothing(self):
        record = self._paper()

        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            self._release(record, self.rdco)

        queue.assert_not_called()

    def test_an_embargo_still_holds_it_back_and_nothing_is_sent(self):
        record = self._paper(until=_in_days(60))

        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            response = self._release(record, self.ktto)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        queue.assert_not_called()
        record.refresh_from_db()
        self.assertEqual(decision_for_record(record).reasons, (Reason.EMBARGOED,))


class IndependentFactsTests(ReleaseBase):
    """Decision 13: each needs its own release, and consent still applies."""

    def test_a_paper_under_both_needs_both_released_in_either_order(self):
        for first, second in (("ip", "embargo"), ("embargo", "ip")):
            with self.subTest(first=first):
                record = self._paper(until=_in_days(60))
                self._act(record, first)
                record.refresh_from_db()
                self.assertFalse(decision_for_record(record).allowed)

                self._act(record, second)
                record.refresh_from_db()
                self.assertTrue(decision_for_record(record).allowed)

    def test_both_released_without_consent_stays_refused(self):
        record = self._paper(until=_in_days(60), consent=False)
        self._act(record, "ip")
        self._act(record, "embargo")
        record.refresh_from_db()

        self.assertEqual(decision_for_record(record).reasons, (Reason.NO_CONSENT,))

    def _act(self, record, which):
        if which == "ip":
            response = self._release(record, self.ktto)
        else:
            self.client.force_authenticate(self.adviser)
            response = self.client.post(reverse("record-embargo-release", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class AuditTests(ReleaseBase):
    def test_a_release_is_recorded_with_who_and_the_ip_type(self):
        record = self._paper()
        Record.objects.filter(pk=record.pk).update(ip_type="patent")

        self._release(record, self.ktto)

        event = AuditEvent.objects.get(event_type=AuditEvent.IP_RELEASED, record=record)
        self.assertEqual(event.user, self.ktto)
        self.assertEqual(event.metadata["ip_type"], "patent")

    def test_a_refused_release_records_nothing(self):
        record = self._paper(is_ip=False)

        self._release(record, self.ktto)
        self._release(self._paper(), self.rdco)

        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.IP_RELEASED).exists())


class TagsCannotClearTheMarkTests(IpReleaseFixtures, APITestCase):
    """Decision 12: clearing `is_ip` would open the check with no release."""

    def _tags(self, record, user, **body):
        self.client.force_authenticate(user)
        return self.client.patch(reverse("record-tags", args=[record.pk]), body, format="json")

    def test_no_office_can_clear_it_ktto_included(self):
        for user in (self.ktto, self.rdco, self.itso, self.ierc):
            with self.subTest(user=user.email):
                record = self._paper()

                response = self._tags(record, user, is_ip=False)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                record.refresh_from_db()
                self.assertTrue(record.is_ip)
                self.assertEqual(decision_for_record(record).reasons, (Reason.UNRELEASED_IP,))

    def test_a_refused_clear_changes_nothing_else_it_carried(self):
        record = self._paper()

        self._tags(record, self.ktto, is_ip=False, ip_type="patent", for_commercialization=True)

        record.refresh_from_db()
        self.assertEqual(record.ip_type, "")
        self.assertFalse(record.for_commercialization)

    def test_a_released_mark_cannot_be_cleared_either(self):
        record = self._paper(ip_released=True)

        self.assertEqual(
            self._tags(record, self.ktto, is_ip=False).status_code, status.HTTP_400_BAD_REQUEST,
        )

    def test_the_other_fields_keep_working(self):
        record = self._paper()

        response = self._tags(
            record, self.rdco, ip_type="patent", for_commercialization=True, is_ip=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(record.ip_type, "patent")
        self.assertTrue(record.for_commercialization)
        self.assertTrue(record.is_ip)

    def test_an_office_can_still_mark_a_paper_and_it_starts_unreleased(self):
        record = self._paper(is_ip=False)

        response = self._tags(record, self.itso, is_ip=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(decision_for_record(record).reasons, (Reason.UNRELEASED_IP,))

    def test_false_on_an_unmarked_paper_clears_nothing_and_is_allowed(self):
        record = self._paper(is_ip=False)

        self.assertEqual(self._tags(record, self.ktto, is_ip=False).status_code, status.HTTP_200_OK)


class OfferedTests(IpReleaseFixtures, APITestCase):
    """`capabilities` carries the release, so the screen compares no role names."""

    def _offers_release(self, record, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("record-detail", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return "release_ip" in response.data["capabilities"]

    def test_only_ktto_is_offered_it_on_a_marked_paper(self):
        record = self._paper()

        self.assertTrue(self._offers_release(record, self.ktto))
        for user in (self.rdco, self.itso, self.ierc, self.adviser, self.owner, self.reader):
            with self.subTest(user=user.email):
                self.assertFalse(self._offers_release(record, user))

    def test_it_is_not_offered_with_nothing_to_release(self):
        for record in (self._paper(is_ip=False), self._paper(ip_released=True),
                       self._paper(PipelineStatus.DRAFT)):
            with self.subTest(record=record.pk):
                self.assertFalse(self._offers_release(record, self.ktto))


class WhoSeesTheReleaseTests(IpReleaseFixtures, APITestCase):
    """The record says whether the mark is released, to whoever sees its embargo."""

    def _ip_release(self, record, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("record-detail", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["ip_release"]

    def test_owners_the_adviser_and_offices_see_whether_it_is_released(self):
        unreleased, released = self._paper(), self._paper(ip_released=True)
        for user in (self.owner, self.adviser, self.ktto, self.rdco, self.itso):
            with self.subTest(user=user.email):
                self.assertEqual(
                    self._ip_release(unreleased, user), {"released": False, "released_at": None},
                )
                seen = self._ip_release(released, user)
                self.assertTrue(seen["released"])
                self.assertIsNotNone(seen["released_at"])

    def test_a_reader_of_the_published_paper_is_told_nothing(self):
        self.assertIsNone(self._ip_release(self._paper(ip_released=True), self.reader))

    def test_an_unmarked_paper_has_no_release_to_show(self):
        self.assertIsNone(self._ip_release(self._paper(is_ip=False), self.owner))
