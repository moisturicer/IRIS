"""
Changing an embargo after submission (ADR-052 decisions 5, 6 and 10, IR-812, IR-882).

Every paper starts embargoed with no date. Only the Adviser or RDCO set or move a
date, and only they release one (§5 as amended for IR-882, §6). Owners do neither.

Three things are pinned hardest. No owner, student or otherwise, changes an
embargo. No act blanks a date or releases a paper without the release route. And a
refusal says nothing about where someone else's embargo stands.
"""

from datetime import date, timedelta
from unittest import mock

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.ai.models import ChunkSet, RecordOverview
from apps.ai.overview.service import PROMPT_VERSION
from apps.ai.policy.records import decision_for_record
from apps.audit.models import AuditEvent
from core.enums import EmbargoState, PipelineStatus, RecordTypeName, RoleName

from .models import Record, RecordOwner, RecordType
from .tests import make_user

QUEUE = "apps.ai.tasks.index_record.delay"
OVERVIEW_QUEUE = "apps.ai.overview.service._enqueue_overview"
RECALL_WORDS = "can't be recalled"


def _in_days(days: int) -> date:
    return timezone.localdate() + timedelta(days=days)


class ActsBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.record_type = RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0]
        cls.owner = make_user("acts-owner@cit.edu", RoleName.STUDENT)
        cls.co_owner = make_user("acts-co-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("acts-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = make_user("acts-rdco@cit.edu", RoleName.RDCO)
        cls.itso = make_user("acts-itso@cit.edu", RoleName.ITSO)
        cls.ktto = make_user("acts-ktto@cit.edu", RoleName.KTTO)
        cls.reader = make_user("acts-reader@cit.edu", RoleName.STUDENT)

    def _paper(self, status_=PipelineStatus.PUBLISHED, *, until=None, released=False, **fields):
        """A consented paper. Embargoed with no date unless a test asks otherwise."""
        now = timezone.now()
        stamps = {"ai_consent": True}
        if until is not None:
            stamps.update(embargoed_until=until, embargo_date_set_at=now,
                          embargo_date_set_by=self.adviser)
        if released:
            stamps.update(is_embargoed=False, embargo_released_at=now,
                          embargo_released_by=self.adviser)
        record = Record.objects.create(
            title="Acts paper", abstract="An abstract long enough to read.",
            record_type=self.record_type, added_by=self.owner, adviser=self.adviser,
            pipeline_status=status_, **stamps, **fields,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        RecordOwner.objects.create(record=record, user=self.co_owner, is_primary=False)
        return record

    def _set(self, record, user, **body):
        self.client.force_authenticate(user)
        return self.client.post(reverse("record-embargo-set", args=[record.pk]), body, format="json")

    def _release(self, record, user):
        self.client.force_authenticate(user)
        return self.client.post(reverse("record-embargo-release", args=[record.pk]), {}, format="json")

    def _state(self, record):
        record.refresh_from_db()
        return record.embargo_state


class SettingADateTests(ActsBase):
    def test_the_adviser_and_rdco_set_one_with_who_and_when(self):
        for user in (self.adviser, self.rdco):
            with self.subTest(user=user.email):
                record = self._paper(PipelineStatus.IN_REVIEW)
                until = _in_days(90)

                response = self._set(record, user, embargoed_until=until.isoformat())

                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                self.assertEqual(response.data["state"], "active")
                self.assertEqual(response.data["until"], until.isoformat())
                self.assertEqual(self._state(record), EmbargoState.ACTIVE)
                self.assertEqual(record.embargoed_until, until)
                self.assertEqual(record.embargo_date_set_by, user)
                self.assertIsNotNone(record.embargo_date_set_at)
                self.assertFalse(decision_for_record(record).allowed)

    def test_no_owner_sets_or_extends_one(self):
        """IR-882: owners no longer judge IP or patent potential; they tell the Adviser."""
        for name, fields in {"undated": {}, "dated": {"until": _in_days(30)}}.items():
            for owner in (self.owner, self.co_owner):
                with self.subTest(paper=name, user=owner.email):
                    record = self._paper(**fields)
                    before = record.embargoed_until

                    response = self._set(record, owner, embargoed_until=_in_days(90).isoformat())

                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                    record.refresh_from_db()
                    self.assertEqual(record.embargoed_until, before)

    def test_no_other_office_sets_one(self):
        for user in (self.itso, self.ktto):
            with self.subTest(user=user.email):
                record = self._paper(PipelineStatus.IN_REVIEW)

                response = self._set(record, user, embargoed_until=_in_days(90).isoformat())

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                record.refresh_from_db()
                self.assertIsNone(record.embargoed_until)

    def test_someone_who_only_reads_the_published_paper_cannot(self):
        record = self._paper()

        response = self._set(record, self.reader, embargoed_until=_in_days(90).isoformat())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_paper_they_cannot_see_reads_as_missing(self):
        record = self._paper(PipelineStatus.IN_REVIEW)

        response = self._set(record, self.reader, embargoed_until=_in_days(90).isoformat())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_it_needs_a_date_from_today_on(self):
        record = self._paper()
        for bad in ({}, {"embargoed_until": None}, {"embargoed_until": ""},
                    {"embargoed_until": "soon"},
                    {"embargoed_until": _in_days(-1).isoformat()}):
            with self.subTest(body=bad):
                response = self._set(record, self.adviser, **bad)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("embargoed_until", response.data)
                record.refresh_from_db()
                self.assertIsNone(record.embargoed_until)

    def test_todays_date_is_accepted_because_it_has_not_passed(self):
        record = self._paper()

        response = self._set(record, self.adviser, embargoed_until=_in_days(0).isoformat())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_a_draft_has_nothing_to_change(self):
        record = self._paper(PipelineStatus.DRAFT)

        response = self._set(record, self.adviser, embargoed_until=_in_days(90).isoformat())

        self.assertIn(response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND))
        record.refresh_from_db()
        self.assertIsNone(record.embargoed_until)


class MovingADateTests(ActsBase):
    def test_moving_it_later_keeps_it_active(self):
        record = self._paper(until=_in_days(10))
        later = _in_days(200)

        response = self._set(record, self.adviser, embargoed_until=later.isoformat())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self._state(record), EmbargoState.ACTIVE)
        self.assertEqual(record.embargoed_until, later)

    def test_a_passed_date_can_be_moved_on(self):
        record = self._paper(until=_in_days(-30))

        response = self._set(record, self.rdco, embargoed_until=_in_days(30).isoformat())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self._state(record), EmbargoState.ACTIVE)

    def test_an_earlier_date_is_allowed_because_a_date_ends_nothing(self):
        record = self._paper(until=_in_days(200))
        sooner = _in_days(5)

        response = self._set(record, self.adviser, embargoed_until=sooner.isoformat())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self._state(record), EmbargoState.ACTIVE)
        self.assertEqual(record.embargoed_until, sooner)


class NothingButAReleaseOpensItTests(ActsBase):
    def _assert_still_held(self, record, until):
        self.assertEqual(self._state(record), EmbargoState.ACTIVE)
        self.assertEqual(record.embargoed_until, until)
        self.assertIsNone(record.embargo_released_at)

    def test_setting_a_null_date_is_refused(self):
        until = _in_days(60)
        record = self._paper(until=until)

        response = self._set(record, self.adviser, embargoed_until=None)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_still_held(record, until)

    def test_editing_the_record_cannot_reach_it(self):
        until = _in_days(60)
        record = self._paper(PipelineStatus.IN_REVIEW, until=until)
        self.client.force_authenticate(self.owner)

        self.client.patch(
            reverse("record-detail", args=[record.pk]),
            {"embargoed_until": None, "is_embargoed": False,
             "embargo_released_at": timezone.now().isoformat()},
            format="json",
        )

        self._assert_still_held(record, until)


class ReleasingAnEmbargoTests(ActsBase):
    def test_the_adviser_and_rdco_release_it_with_who_and_when(self):
        for name, fields in {"undated": {}, "dated": {"until": _in_days(60)}}.items():
            for user in (self.adviser, self.rdco):
                with self.subTest(paper=name, user=user.email):
                    record = self._paper(**fields)

                    response = self._release(record, user)

                    self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                    self.assertEqual(response.data["state"], "released")
                    self.assertEqual(self._state(record), EmbargoState.RELEASED)
                    self.assertFalse(record.is_embargoed)
                    self.assertEqual(record.embargo_released_by, user)
                    self.assertIsNotNone(record.embargo_released_at)
                    self.assertEqual(record.embargoed_until, fields.get("until"))
                    self.assertTrue(decision_for_record(record).allowed)

    def test_a_student_owner_cannot_even_on_their_own_paper(self):
        record = self._paper(until=_in_days(60))

        for owner in (self.owner, self.co_owner):
            with self.subTest(user=owner.email):
                response = self._release(record, owner)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(self._state(record), EmbargoState.ACTIVE)

    def test_no_other_office_can(self):
        record = self._paper(until=_in_days(60))

        for user in (self.itso, self.ktto):
            with self.subTest(user=user.email):
                response = self._release(record, user)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(self._state(record), EmbargoState.ACTIVE)

    def test_a_refusal_says_nothing_about_where_the_embargo_stands(self):
        """A reader may open a published paper, and may not learn it's under an agreement."""
        held = self._paper(until=_in_days(60))
        clear = self._paper(released=True)

        first = self._release(held, self.reader)
        second = self._release(clear, self.reader)

        self.assertEqual(first.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(second.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(first.data, second.data)

    def test_a_paper_they_cannot_see_reads_as_missing(self):
        record = self._paper(PipelineStatus.IN_REVIEW, until=_in_days(60))

        self.assertEqual(self._release(record, self.reader).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_released_paper_cannot_be_released_again(self):
        record = self._paper(until=_in_days(60), released=True)

        response = self._release(record, self.adviser)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._state(record), EmbargoState.RELEASED)

    def test_a_draft_cannot_be_released(self):
        record = self._paper(PipelineStatus.DRAFT, until=_in_days(60))

        response = self._release(record, self.adviser)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._state(record), EmbargoState.ACTIVE)


class AReleasedPaperCanBeHeldAgainTests(ActsBase):
    """Decided 2026-11-02 under IR-812: a new embargo, not an undone release."""

    def test_setting_a_new_date_makes_it_active_again(self):
        record = self._paper(until=_in_days(60), released=True)
        later = _in_days(300)

        response = self._set(record, self.rdco, embargoed_until=later.isoformat())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self._state(record), EmbargoState.ACTIVE)
        self.assertEqual(record.embargoed_until, later)
        self.assertIsNone(record.embargo_released_at)
        self.assertIsNone(record.embargo_released_by)

    def test_an_owner_cannot_hold_it_again(self):
        """The IR-812 amendment's owner override is gone with IR-882."""
        record = self._paper(released=True)

        response = self._set(record, self.owner, embargoed_until=_in_days(300).isoformat())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._state(record), EmbargoState.RELEASED)

    def test_only_the_adviser_or_rdco_can_release_it_again(self):
        record = self._paper(until=_in_days(60), released=True)
        self._set(record, self.adviser, embargoed_until=_in_days(300).isoformat())

        self.assertEqual(self._release(record, self.owner).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._release(record, self.rdco).status_code, status.HTTP_200_OK)
        self.assertEqual(self._state(record), EmbargoState.RELEASED)


class WhatAlreadyLeftTests(ActsBase):
    """The response says so whenever the check could already have let text out."""

    def _notice(self, **paper):
        record = self._paper(**paper)
        response = self._set(record, self.adviser, embargoed_until=_in_days(90).isoformat())
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data.get("notice", "")

    def test_a_released_paper_could_have_gone(self):
        self.assertIn(RECALL_WORDS, self._notice(released=True))
        self.assertIn(RECALL_WORDS, self._notice(until=_in_days(60), released=True))

    def test_nothing_is_said_when_the_check_never_let_it_out(self):
        self.assertEqual(self._notice(), "")
        self.assertEqual(self._notice(until=_in_days(60)), "")


class AReleaseSendsThePaperOnTests(ActsBase):
    """Decision 10: a paper refused during its embargo isn't left out for good."""

    def _release_and_commit(self, record, user=None):
        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            response = self._release(record, user or self.adviser)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return queue

    def test_it_queues_the_paper_for_indexing(self):
        for fields in ({}, {"until": _in_days(60)}):
            with self.subTest(fields=sorted(fields)):
                record = self._paper(**fields)

                self._release_and_commit(record).assert_called_once_with(record.pk)

    def test_it_asks_again_for_the_overview_refused_during_the_embargo(self):
        record = self._paper(until=_in_days(60))
        ChunkSet.objects.create(
            record=record, extraction_hash="e", strategy_id="s", options={},
            content_hash="c", is_active=True,
        )
        RecordOverview.objects.create(
            record=record, state="unavailable", content_hash="c", prompt_version=PROMPT_VERSION,
        )

        with mock.patch(OVERVIEW_QUEUE) as overview:
            self._release_and_commit(record)

        overview.assert_called_once()
        self.assertEqual(RecordOverview.objects.get(record=record).state, "generating")

    def test_an_ip_mark_still_holds_it_back(self):
        record = self._paper(until=_in_days(60), is_ip=True)

        self._release_and_commit(record).assert_not_called()

    def test_a_refused_release_sends_nothing(self):
        record = self._paper(until=_in_days(60))

        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            response = self._release(record, self.owner)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        queue.assert_not_called()

    def test_setting_one_sends_nothing(self):
        record = self._paper(released=True)

        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            self._set(record, self.adviser, embargoed_until=_in_days(90).isoformat())

        queue.assert_not_called()

    def test_a_broker_outage_does_not_fail_the_release(self):
        record = self._paper(until=_in_days(60))

        with mock.patch(QUEUE, side_effect=OSError("broker down")):
            with self.captureOnCommitCallbacks(execute=True):
                response = self._release(record, self.adviser)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self._state(record), EmbargoState.RELEASED)


class EveryActIsAuditedTests(ActsBase):
    """Decision 8. Read back from the rows, with one row per act."""

    def _event(self, record, event_type):
        return AuditEvent.objects.get(record=record, event_type=event_type)

    def test_dating_an_undated_embargo_is_a_set(self):
        record = self._paper()
        until = _in_days(90)

        self._set(record, self.adviser, embargoed_until=until.isoformat())

        event = self._event(record, AuditEvent.EMBARGO_SET)
        self.assertEqual(event.user, self.adviser)
        self.assertEqual(event.metadata, {"until": until.isoformat(), "previous_state": "active"})
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.EMBARGO_EXTENDED).exists())

    def test_moving_a_date_is_its_own_event_with_both_dates(self):
        before, after = _in_days(10), _in_days(200)
        record = self._paper(until=before)

        self._set(record, self.rdco, embargoed_until=after.isoformat())

        event = self._event(record, AuditEvent.EMBARGO_EXTENDED)
        self.assertEqual(event.user, self.rdco)
        self.assertEqual(
            event.metadata, {"until": after.isoformat(), "previous_until": before.isoformat()},
        )
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.EMBARGO_SET).exists())

    def test_holding_a_released_paper_again_is_a_set_that_says_so(self):
        record = self._paper(until=_in_days(60), released=True)

        self._set(record, self.adviser, embargoed_until=_in_days(90).isoformat())

        self.assertEqual(
            self._event(record, AuditEvent.EMBARGO_SET).metadata["previous_state"], "released",
        )

    def test_a_release_is_recorded_with_the_date_it_held(self):
        for until in (_in_days(60), None):
            with self.subTest(until=until):
                record = self._paper(until=until)

                self._release(record, self.rdco)

                event = self._event(record, AuditEvent.EMBARGO_RELEASED)
                self.assertEqual(event.user, self.rdco)
                self.assertEqual(event.metadata, {"until": until.isoformat() if until else None})

    def test_a_refused_act_records_nothing(self):
        record = self._paper(until=_in_days(60))

        self._release(record, self.owner)
        self._set(record, self.owner, embargoed_until=_in_days(90).isoformat())
        self._set(record, self.adviser, embargoed_until=None)

        self.assertFalse(AuditEvent.objects.filter(
            record=record, event_type__startswith="EMBARGO",
        ).exists())


class RecordDetailOffersTheActsTests(ActsBase):
    """The screen compares no role names, so `capabilities` has to carry these."""

    def _offered(self, record, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("record-detail", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return set(response.data["capabilities"]) & {"set_embargo", "release_embargo"}

    def test_who_is_offered_what_on_an_active_embargo(self):
        record = self._paper(until=_in_days(60))
        expected = {
            self.owner: set(),
            self.co_owner: set(),
            self.adviser: {"set_embargo", "release_embargo"},
            self.rdco: {"set_embargo", "release_embargo"},
            self.itso: set(),
            self.ktto: set(),
            self.reader: set(),
        }
        for user, offered in expected.items():
            with self.subTest(user=user.email):
                self.assertEqual(self._offered(record, user), offered)

    def test_release_is_not_offered_on_a_released_paper(self):
        record = self._paper(until=_in_days(60), released=True)

        for user in (self.adviser, self.rdco):
            with self.subTest(user=user.email):
                self.assertEqual(self._offered(record, user), {"set_embargo"})

    def test_a_draft_offers_neither(self):
        record = self._paper(PipelineStatus.DRAFT, until=_in_days(60))

        for user in (self.owner, self.adviser):
            with self.subTest(user=user.email):
                self.assertEqual(self._offered(record, user), set())
