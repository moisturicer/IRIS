"""The gate's verdict on real `Record` rows (ADR-052 §3, §9, IR-811, IR-882).

`test_disclosure_policy.py` proves the table on values. These prove what a row
actually holds reaches that table: above all that a new paper, with nothing
stamped, is embargoed (IR-882), and that a passed date opens nothing.
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


def _dated(days, **fields):
    return _paper(embargo_date_set_at=timezone.now(),
                  embargoed_until=_today() + timedelta(days=days), **fields)


def _released(**fields):
    return {"is_embargoed": False, "embargo_released_at": timezone.now(), **fields}


class TestANewPaper:
    def test_it_is_embargoed_with_no_date_and_refused(self):
        record = _paper()

        assert record.embargo_state == EmbargoState.ACTIVE
        assert record.embargoed_until is None
        decision = decision_for_record(record)
        assert decision.allowed is False
        assert decision.reasons == (Reason.EMBARGOED,)


class TestADatedPaper:
    def test_a_future_date_is_active_and_refused(self):
        record = _dated(30)

        assert record.embargo_state == EmbargoState.ACTIVE
        decision = decision_for_record(record)
        assert decision.allowed is False
        assert decision.reasons == (Reason.EMBARGOED,)

    @pytest.mark.parametrize("days_ago", [0, 1, 400])
    def test_a_date_arriving_or_passing_opens_nothing(self, days_ago):
        """ADR-052 §9: the date is a reminder. On the day and every day after,
        the paper stays under embargo until a person releases it."""
        record = _dated(-days_ago)

        assert record.embargo_state == EmbargoState.ACTIVE
        assert decision_for_record(record).allowed is False


class TestAReleasedPaper:
    @pytest.mark.parametrize("dated", [True, False], ids=["dated", "undated"])
    def test_a_release_is_released_and_allowed(self, dated):
        record = _dated(30, **_released()) if dated else _paper(**_released())

        assert record.embargo_state == EmbargoState.RELEASED
        assert decision_for_record(record).allowed is True


class TestIndependentFacts:
    """ADR-052 §1, §13: a release never overrides the other inputs."""

    def test_a_release_does_not_stand_in_for_consent(self):
        record = Record.objects.create(title="A thesis", abstract="An abstract.", **_released())

        assert decision_for_record(record).reasons == (Reason.NO_CONSENT,)

    def test_a_release_does_not_clear_an_ip_mark(self):
        record = Record.objects.create(
            title="A thesis", abstract="An abstract.", is_ip=True,
            dpa_accepted_at=timezone.now(), **_released(),
        )

        assert decision_for_record(record).reasons == (Reason.UNRELEASED_IP,)


class TestRowsThatCannotExist:
    """A row that would read as something nobody did."""

    def test_released_needs_a_release_stamp(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            _paper(is_embargoed=False)

    def test_a_release_stamp_cannot_sit_on_an_embargoed_paper(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            _paper(embargo_released_at=timezone.now())

    def test_a_date_needs_to_say_when_it_was_set(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            _paper(embargoed_until=_today() + timedelta(days=30))
