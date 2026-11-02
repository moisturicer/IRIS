"""The gate's verdict on real `Record` rows (ADR-052 §3, §9, IR-811).

`test_disclosure_policy.py` proves the table on values. These prove what a row
actually holds reaches that table: above all that a blank date on an unanswered
paper is not read as "no embargo", and that a passed date opens nothing.
"""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ai.policy import Reason, decision_for_record
from apps.records.models import Record
from core.enums import EmbargoState

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _paper(**fields) -> Record:
    """A consented paper with no IP mark, so only its embargo decides."""
    return Record.objects.create(
        title="A thesis", abstract="An abstract.", is_ip=False,
        dpa_accepted_at=timezone.now(), **fields,
    )


def _today():
    return timezone.localdate()


class TestAnUnansweredPaper:
    def test_a_new_paper_is_unknown_and_refused(self):
        record = _paper()

        assert record.embargo_state == EmbargoState.UNKNOWN
        decision = decision_for_record(record)
        assert decision.allowed is False
        assert decision.reasons == (Reason.EMBARGO_UNKNOWN,)

    def test_its_blank_date_is_not_read_as_no_embargo(self):
        """The trap ADR-052 names: an unanswered row and an answered "no" both
        store a blank date, and only the answer tells them apart."""
        record = _paper(embargoed_until=None)

        assert decision_for_record(record).allowed is False


class TestAnAnsweredPaper:
    def test_answered_no_is_none_and_allowed(self):
        record = _paper(embargo_answered_at=timezone.now())

        assert record.embargo_state == EmbargoState.NONE
        assert decision_for_record(record).allowed is True

    def test_answered_with_a_future_date_is_active_and_refused(self):
        record = _paper(
            embargo_answered_at=timezone.now(),
            embargoed_until=_today() + timedelta(days=30),
        )

        assert record.embargo_state == EmbargoState.ACTIVE
        decision = decision_for_record(record)
        assert decision.allowed is False
        assert decision.reasons == (Reason.EMBARGOED,)

    @pytest.mark.parametrize("days_ago", [0, 1, 400])
    def test_a_date_arriving_or_passing_opens_nothing(self, days_ago):
        """ADR-052 §9: the date is a reminder. On the day and every day after,
        the paper stays under embargo until a person releases it."""
        record = _paper(
            embargo_answered_at=timezone.now(),
            embargoed_until=_today() - timedelta(days=days_ago),
        )

        assert record.embargo_state == EmbargoState.ACTIVE
        assert decision_for_record(record).allowed is False

    def test_a_release_is_released_and_allowed(self):
        record = _paper(
            embargo_answered_at=timezone.now(),
            embargoed_until=_today() + timedelta(days=30),
            embargo_released_at=timezone.now(),
        )

        assert record.embargo_state == EmbargoState.RELEASED
        assert decision_for_record(record).allowed is True


class TestIndependentFacts:
    """ADR-052 §1, §13: an allowing embargo never overrides the other inputs."""

    def test_no_embargo_does_not_stand_in_for_consent(self):
        record = Record.objects.create(
            title="A thesis", abstract="An abstract.",
            embargo_answered_at=timezone.now(),
        )

        assert decision_for_record(record).reasons == (Reason.NO_CONSENT,)

    def test_no_embargo_does_not_clear_an_ip_mark(self):
        record = Record.objects.create(
            title="A thesis", abstract="An abstract.", is_ip=True,
            dpa_accepted_at=timezone.now(), embargo_answered_at=timezone.now(),
        )

        assert decision_for_record(record).reasons == (Reason.UNRELEASED_IP,)


class TestRowsThatCannotExist:
    """A row that would read as allowed without anyone having said so."""

    def test_a_release_needs_an_embargo_to_release(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            _paper(embargo_answered_at=timezone.now(), embargo_released_at=timezone.now())

    def test_a_date_needs_someone_to_have_answered(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            _paper(embargoed_until=_today() + timedelta(days=30))
