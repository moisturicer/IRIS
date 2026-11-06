"""
A paper's embargo before anyone acts on it (ADR-052 as amended for IR-882).

Every paper starts embargoed, with no date. Publish asks no question, a first
submission needs no answer, and the disclosure gate refuses the paper until the
Adviser or RDCO releases it (`test_embargo_acts.py` covers those acts). These pin
the default, that nothing a draft's owner sends can open it, and who sees it.
"""

from datetime import date, timedelta
from uuid import uuid4
from unittest import mock

from django.db import IntegrityError, transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.ai.policy import Reason, decision_for_record
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import EmbargoState, PipelineStatus, RecordTypeName

from .models import Record, RecordOwner, RecordType
from .tests import make_user

QUEUE = "apps.ai.tasks.index_record.delay"


def _in_days(days: int) -> date:
    return timezone.localdate() + timedelta(days=days)


class DraftBase(APITestCase):
    def setUp(self):
        self.record_type = RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0]
        self.owner = make_user("embargo-owner@cit.edu", "Student")
        self.adviser = make_user("embargo-adviser@cit.edu", "Adviser")
        self.record = self._draft()
        self.client.force_authenticate(self.owner)

    def _draft(self, status_=PipelineStatus.DRAFT, **fields):
        record = Record.objects.create(
            title="C" * 10 + uuid4().hex[:8], abstract="D" * 40, record_type=self.record_type,
            added_by=self.owner, adviser=self.adviser, pipeline_status=status_, **fields,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def _submit(self, record=None, **extra):
        return self.client.post(
            reverse("record-submit", args=[(record or self.record).pk]),
            {"dpa_accepted": True, **extra}, format="json",
        )

    def _assert_embargoed_with_no_date(self, record=None):
        record = record or self.record
        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)
        self.assertTrue(record.is_embargoed)
        self.assertIsNone(record.embargoed_until)
        self.assertIsNone(record.embargo_date_set_at)
        self.assertIsNone(record.embargo_released_at)


class EveryPaperStartsEmbargoedTests(DraftBase):
    def test_a_new_paper_is_active_with_no_date(self):
        self._assert_embargoed_with_no_date()

    def test_the_gate_refuses_it_even_with_consent(self):
        Record.objects.filter(pk=self.record.pk).update(dpa_accepted_at=timezone.now())
        self.record.refresh_from_db()

        decision = decision_for_record(self.record)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reasons, (Reason.EMBARGOED,))

    def test_a_release_needs_its_stamp_in_the_database(self):
        """The flag and the release stamp can't disagree, so no write clears one alone."""
        for fields in ({"is_embargoed": False}, {"embargo_released_at": timezone.now()}):
            with self.subTest(sorted(fields)), self.assertRaises(IntegrityError), transaction.atomic():
                Record.objects.filter(pk=self.record.pk).update(**fields)

    def test_a_date_needs_to_say_when_it_was_set(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Record.objects.filter(pk=self.record.pk).update(embargoed_until=_in_days(30))


class PublishAsksNothingTests(DraftBase):
    def test_there_is_no_route_to_answer_the_question(self):
        """IR-816's `embargo-answer/` is gone with the question."""
        with self.assertRaises(NoReverseMatch):
            reverse("record-embargo-answer", args=[self.record.pk])
        response = self.client.post(
            f"/api/v1/records/{self.record.pk}/embargo-answer/", {"embargoed": False}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self._assert_embargoed_with_no_date()

    def test_a_first_submission_needs_no_answer_and_stays_embargoed(self):
        response = self._submit()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, PipelineStatus.IN_REVIEW)
        self._assert_embargoed_with_no_date()

    def test_submitting_sends_nothing_on(self):
        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            response = self._submit()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        queue.assert_not_called()

    def test_saying_no_embargo_in_the_submit_body_changes_nothing(self):
        response = self._submit(embargoed=False, is_embargoed=False)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self._assert_embargoed_with_no_date()

    def test_patching_the_record_cannot_release_or_date_it(self):
        """An embargo changes only through its own acts, with who and when."""
        response = self.client.patch(
            reverse("record-detail", args=[self.record.pk]),
            {
                "is_embargoed": False,
                "embargoed_until": _in_days(30).isoformat(),
                "embargo_date_set_at": timezone.now().isoformat(),
                "embargo_released_at": timezone.now().isoformat(),
            },
            format="json",
        )

        self.assertLess(response.status_code, 500, response.data)
        self._assert_embargoed_with_no_date()

    def test_a_draft_owner_cannot_set_or_release_one(self):
        """Owners don't set dates (§5 as amended) or release (§6), even on a draft."""
        for name in ("record-embargo-set", "record-embargo-release"):
            with self.subTest(name):
                response = self.client.post(
                    reverse(name, args=[self.record.pk]),
                    {"embargoed_until": _in_days(30).isoformat()}, format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self._assert_embargoed_with_no_date()


class TheEmbargoStandsTests(DecisionTestBase):
    """ADR-052 §4. A new Version doesn't touch it, and nor does fixing a typo."""

    def test_a_new_version_keeps_the_embargo_and_its_date(self):
        record = self.at_adviser()
        set_at = timezone.now() - timedelta(days=3)
        until = _in_days(60)
        Record.objects.filter(pk=record.pk).update(
            embargo_date_set_at=set_at, embargo_date_set_by=self.adviser, embargoed_until=until,
        )
        self.asked(record, self.adviser)

        self.client.force_authenticate(self.owner)
        edited = self.client.patch(
            reverse("record-detail", args=[record.pk]),
            {"abstract": "Revised methods after the adviser's request. " * 2},
            format="json",
        )
        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        response = self.client.post(reverse("record-new-version", args=[record.pk]), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        record.refresh_from_db()
        self.assertEqual(record.resubmission_count, 1, "the new version itself was recorded")
        self.assertTrue(record.is_embargoed)
        self.assertEqual(record.embargo_date_set_at, set_at)
        self.assertEqual(record.embargo_date_set_by, self.adviser)
        self.assertEqual(record.embargoed_until, until)


class RecordDetailShowsTheEmbargoTests(APITestCase):
    """
    The state and date go to owners, the Adviser and office staff, and to no one
    else (decision 18). Any signed-in reader can open a published paper, and that
    a paper is under an agreement is not theirs to learn from it.
    """

    @classmethod
    def setUpTestData(cls):
        cls.until = _in_days(45)
        cls.owner = make_user("detail-owner@cit.edu", "Student")
        cls.adviser = make_user("detail-adviser@cit.edu", "Adviser")
        cls.record = Record.objects.create(
            title="E" * 10, abstract="F" * 40, adviser=cls.adviser,
            pipeline_status=PipelineStatus.PUBLISHED,
            embargo_date_set_at=timezone.now(), embargo_date_set_by=cls.adviser,
            embargoed_until=cls.until,
        )
        RecordOwner.objects.create(record=cls.record, user=cls.owner, is_primary=True)

    def _detail_as(self, user, record=None):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("record-detail", args=[(record or self.record).pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_owners_the_adviser_and_office_staff_see_the_state_and_date(self):
        readers = {
            "owner": self.owner,
            "adviser": self.adviser,
            **{
                role: make_user(f"detail-{role.lower()}@cit.edu", role)
                for role in ("KTTO", "RDCO", "ITSO", "IERC")
            },
        }
        for name, user in readers.items():
            with self.subTest(name):
                self.assertEqual(
                    self._detail_as(user)["embargo"],
                    {"state": EmbargoState.ACTIVE, "until": self.until.isoformat()},
                )

    def test_other_readers_of_a_published_paper_learn_nothing(self):
        stranger = make_user("detail-stranger@cit.edu", "Student")
        other_adviser = make_user("detail-other-adviser@cit.edu", "Adviser")
        for user in (stranger, other_adviser):
            with self.subTest(user.email):
                data = self._detail_as(user)
                self.assertIsNone(data["embargo"])
                self.assertFalse([key for key in data if key.startswith("embargo")
                                  and key != "embargo"])
                self.assertNotIn("is_embargoed", data)

    def test_a_paper_nobody_has_dated_reads_active_with_no_date(self):
        record = Record.objects.create(
            title="H" * 10, abstract="I" * 40, adviser=self.adviser,
            pipeline_status=PipelineStatus.PUBLISHED,
        )

        self.assertEqual(
            self._detail_as(self.adviser, record)["embargo"],
            {"state": EmbargoState.ACTIVE, "until": None},
        )

    def test_the_catalogue_does_not_carry_it(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse("record-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        row = next(r for r in response.data["results"] if r["id"] == self.record.pk)
        self.assertFalse([key for key in row if "embargo" in key])
