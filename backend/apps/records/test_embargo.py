"""
A paper's embargo answer at the API (ADR-052 decision 2, IR-811, IR-816).

Publish saves the answer through `POST /records/<id>/embargo-answer/` before the
file is sent, and `POST /records/<id>/submit/` refuses a paper that has none.
These pin three things: an answer is stored with who and when, a bad one changes
nothing, and a missing one never reads as "no embargo", whatever shape the
request takes.
"""

from datetime import date, timedelta
from uuid import uuid4
from unittest import mock

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.ai.models import ChunkSet, RecordOverview
from apps.ai.overview.service import PROMPT_VERSION
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import EmbargoState, PipelineStatus, RecordTypeName

from .models import Record, RecordOwner, RecordType
from .tests import make_user

QUEUE = "apps.ai.tasks.index_record.delay"
OVERVIEW_QUEUE = "apps.ai.overview.service._enqueue_overview"


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

    def _answer(self, record=None, format_="json", **answer):
        return self.client.post(
            reverse("record-embargo-answer", args=[(record or self.record).pk]),
            answer, format=format_,
        )

    def _submit(self, record=None):
        return self.client.post(
            reverse("record-submit", args=[(record or self.record).pk]),
            {"dpa_accepted": True}, format="json",
        )

    def _assert_unanswered(self):
        self.record.refresh_from_db()
        self.assertEqual(self.record.embargo_state, EmbargoState.UNKNOWN)
        self.assertIsNone(self.record.embargo_answered_at)
        self.assertIsNone(self.record.embargo_answered_by)
        self.assertIsNone(self.record.embargoed_until)


class AnsweringTheQuestionTests(DraftBase):
    """Publish's first question, saved before the file is sent."""

    def test_no_embargo_is_saved_with_who_and_when(self):
        response = self._answer(embargoed=False)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {"state": "none", "until": None})
        self.record.refresh_from_db()
        self.assertEqual(self.record.embargo_state, EmbargoState.NONE)
        self.assertIsNotNone(self.record.embargo_answered_at)
        self.assertEqual(self.record.embargo_answered_by, self.owner)

    def test_an_embargo_is_saved_with_its_date_who_and_when(self):
        until = _in_days(90)

        response = self._answer(embargoed=True, embargoed_until=until.isoformat())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {"state": "active", "until": until.isoformat()})
        self.record.refresh_from_db()
        self.assertEqual(self.record.embargo_state, EmbargoState.ACTIVE)
        self.assertEqual(self.record.embargoed_until, until)
        self.assertEqual(self.record.embargo_answered_by, self.owner)

    def test_todays_date_is_accepted_because_it_has_not_passed(self):
        response = self._answer(embargoed=True, embargoed_until=_in_days(0).isoformat())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_no_embargo_with_a_null_date_is_a_plain_no(self):
        response = self._answer(embargoed=False, embargoed_until=None)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.embargo_state, EmbargoState.NONE)

    def test_an_owner_may_change_the_answer_before_submission(self):
        """ADR-052 §5: nothing has been sent yet, so the answer stays theirs."""
        for stored in (
            {"embargo_answered_at": timezone.now(), "embargoed_until": _in_days(30)},
            {
                "embargo_answered_at": timezone.now(), "embargoed_until": _in_days(30),
                "embargo_released_at": timezone.now(),
            },
        ):
            with self.subTest(stored=sorted(stored)):
                record = self._draft(**stored)

                response = self._answer(record, embargoed=False)

                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                record.refresh_from_db()
                self.assertEqual(record.embargo_state, EmbargoState.NONE)
                self.assertIsNone(record.embargo_released_at)
                self.assertEqual(record.embargo_answered_by, self.owner)

    def test_a_bad_answer_changes_nothing(self):
        bad_answers = {
            "nothing at all": {},
            "on with no date": {"embargoed": True},
            "on with a null date": {"embargoed": True, "embargoed_until": None},
            "on with a date that is not one": {"embargoed": True, "embargoed_until": "soon"},
            "on with a past date": {"embargoed": True, "embargoed_until": _in_days(-1).isoformat()},
            "off with a date": {"embargoed": False, "embargoed_until": _in_days(30).isoformat()},
            "a date with no toggle": {"embargoed_until": _in_days(30).isoformat()},
            "a toggle that is not a yes or no": {"embargoed": "maybe"},
            "a null toggle": {"embargoed": None},
        }
        for name, answer in bad_answers.items():
            with self.subTest(name):
                response = self._answer(**answer)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self._assert_unanswered()

    def test_a_form_post_never_reads_as_no(self):
        """DRF reads a boolean missing from form data as False, which would record
        "no embargo" that nobody gave and let the paper be sent to a vendor."""
        for name, answer in {
            "no toggle at all": {"unrelated": "x"},
            "a blank date and no toggle": {"embargoed_until": ""},
            "a blank toggle": {"embargoed": ""},
        }.items():
            with self.subTest(name):
                response = self._answer(format_="multipart", **answer)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertIn("embargoed", response.data)
                self._assert_unanswered()

    def test_the_refusal_names_the_field_to_fix(self):
        response = self._answer(embargoed=True)

        self.assertIn("embargoed_until", response.data)

    def test_a_submitted_paper_cannot_be_answered_here(self):
        """Otherwise an owner could end an embargo here with no release (§6)."""
        record = self._draft(
            PipelineStatus.IN_REVIEW,
            embargo_answered_at=timezone.now(), embargoed_until=_in_days(30),
        )

        response = self._answer(record, embargoed=False)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        record.refresh_from_db()
        self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)

    def test_saving_the_answer_sends_nothing_on(self):
        """Consent comes at the last step, so the gate has nothing to open yet."""
        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            response = self._answer(embargoed=False)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        queue.assert_not_called()

    def test_patching_the_record_cannot_answer_for_it(self):
        """An answer that opens the gate comes through this route, with who and
        when, and never as an ordinary details edit."""
        response = self.client.patch(
            reverse("record-detail", args=[self.record.pk]),
            {
                "embargoed": False,
                "embargoed_until": _in_days(30).isoformat(),
                "embargo_answered_at": timezone.now().isoformat(),
                "embargo_released_at": timezone.now().isoformat(),
            },
            format="json",
        )

        self.assertLess(response.status_code, 500, response.data)
        self._assert_unanswered()


class SubmittingNeedsAnAnswerTests(DraftBase):
    """The form asks first, so a paper with no answer cannot enter review."""

    def _assert_refused_as_unanswered(self, response):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("embargoed", response.data)
        self._assert_unanswered()
        self.assertEqual(self.record.pipeline_status, PipelineStatus.DRAFT)
        self.assertIsNone(self.record.dpa_accepted_at)

    def test_a_first_submission_with_no_answer_is_refused_and_stays_a_draft(self):
        self._assert_refused_as_unanswered(self._submit())

    def test_a_refused_submission_sends_nothing_on(self):
        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            self._assert_refused_as_unanswered(self._submit())

        queue.assert_not_called()

    def test_an_answer_in_the_submit_body_is_not_an_answer(self):
        """One route writes the answer, so it always arrives before the file."""
        self._assert_refused_as_unanswered(self.client.post(
            reverse("record-submit", args=[self.record.pk]),
            {"dpa_accepted": True, "embargoed": False}, format="json",
        ))

    def test_a_saved_answer_is_enough_to_submit_and_stands(self):
        record = self._draft(
            embargo_answered_at=timezone.now(), embargo_answered_by=self.adviser,
            embargoed_until=_in_days(30),
        )

        response = self._submit(record)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        self.assertEqual(record.embargo_state, EmbargoState.ACTIVE)
        self.assertEqual(record.embargo_answered_by, self.adviser)


class SendingThePaperOnTests(DraftBase):
    """
    ADR-052 §Consequences: a normal paper reaches the AI "once its owner says no
    embargo". Its upload was refused while it was a draft with no consent, and a
    refused paper is never tried again, so submitting has to queue it. Whatever
    the gate still refuses is not queued.
    """

    def _submit_and_commit(self, record=None):
        with mock.patch(QUEUE) as queue, self.captureOnCommitCallbacks(execute=True):
            response = self._submit(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return queue

    def test_answering_no_queues_the_paper_for_indexing(self):
        self._answer(embargoed=False)

        self._submit_and_commit().assert_called_once_with(self.record.pk)

    def test_an_active_embargo_queues_nothing(self):
        self._answer(embargoed=True, embargoed_until=_in_days(30).isoformat())

        self._submit_and_commit().assert_not_called()

    def test_an_ip_mark_still_holds_the_paper_back(self):
        record = self._draft(is_ip=True)
        self._answer(record, embargoed=False)

        self._submit_and_commit(record).assert_not_called()

    def _overview_refused_at_upload(self):
        """What chunking leaves behind: its overview was refused by the gate and
        stored as unavailable, which stands until someone asks again."""
        ChunkSet.objects.create(
            record=self.record, extraction_hash="e", strategy_id="s", options={},
            content_hash="c", is_active=True,
        )
        RecordOverview.objects.create(
            record=self.record, state="unavailable", content_hash="c",
            prompt_version=PROMPT_VERSION,
        )

    def test_answering_no_asks_again_for_the_overview_refused_at_upload(self):
        self._overview_refused_at_upload()
        self._answer(embargoed=False)

        with mock.patch(OVERVIEW_QUEUE) as overview:
            self._submit_and_commit()

        overview.assert_called_once()
        self.assertEqual(RecordOverview.objects.get(record=self.record).state, "generating")

    def test_an_active_embargo_leaves_the_overview_alone(self):
        self._overview_refused_at_upload()
        self._answer(embargoed=True, embargoed_until=_in_days(30).isoformat())

        with mock.patch(OVERVIEW_QUEUE) as overview:
            self._submit_and_commit()

        overview.assert_not_called()
        self.assertEqual(RecordOverview.objects.get(record=self.record).state, "unavailable")

    def test_a_broker_outage_does_not_fail_the_submission(self):
        """The submission has already committed. A paper that missed its queue
        is one a backfill can reach, and the owner's act succeeded."""
        self._answer(embargoed=False)

        with (
            mock.patch(QUEUE, side_effect=ConnectionError("broker down")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self._submit()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, PipelineStatus.IN_REVIEW)


class TheAnswerStandsTests(DecisionTestBase):
    """ADR-052 §4. Not asked again, and not re-stamped by fixing a typo."""

    def test_a_new_version_keeps_the_answer(self):
        record = self.at_adviser()
        answered_at = timezone.now() - timedelta(days=3)
        until = _in_days(60)
        Record.objects.filter(pk=record.pk).update(
            embargo_answered_at=answered_at, embargo_answered_by=self.owner, embargoed_until=until,
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
        self.assertEqual(record.embargo_answered_at, answered_at)
        self.assertEqual(record.embargo_answered_by, self.owner)
        self.assertEqual(record.embargoed_until, until)


class RecordDetailShowsTheEmbargoTests(APITestCase):
    """
    The state and date go to owners, the Adviser and office staff, and to no one
    else. Any signed-in reader can open a published paper, and that a paper is
    under an agreement is not theirs to learn from it.
    """

    @classmethod
    def setUpTestData(cls):
        cls.until = _in_days(45)
        cls.owner = make_user("detail-owner@cit.edu", "Student")
        cls.adviser = make_user("detail-adviser@cit.edu", "Adviser")
        cls.record = Record.objects.create(
            title="E" * 10, abstract="F" * 40, adviser=cls.adviser,
            pipeline_status=PipelineStatus.PUBLISHED,
            embargo_answered_at=timezone.now(), embargo_answered_by=cls.owner,
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
                self.assertFalse([key for key in data if key.startswith("embargoed")])

    def test_an_unanswered_paper_says_so(self):
        record = Record.objects.create(
            title="H" * 10, abstract="I" * 40, adviser=self.adviser,
            pipeline_status=PipelineStatus.PUBLISHED,
        )

        self.assertEqual(
            self._detail_as(self.adviser, record)["embargo"],
            {"state": EmbargoState.UNKNOWN, "until": None},
        )

    def test_the_catalogue_does_not_carry_it(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(reverse("record-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        row = next(r for r in response.data["results"] if r["id"] == self.record.pk)
        self.assertFalse([key for key in row if key.startswith("embargo")])
