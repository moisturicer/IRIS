"""A settled attempt records the vendor's prompt-cache hits and is charged in full (IR-953)."""

import pytest

from apps.ai.models.admission import ProviderReservation

from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_admission_db import admitted, answer_one, reply

runtime = runs_db.runtime

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def cached_reply(cached):
    body = reply(prompt_tokens=9, completion_tokens=3)
    body["usage"]["prompt_tokens_details"] = {"cached_tokens": cached}
    return body


def test_cached_tokens_are_recorded_and_the_charge_is_not_discounted(runtime):
    _, transport = admitted(runtime, cached_reply(8))
    _, status = answer_one(runtime, "cached-tokens@cit.edu", "cached-tokens-01", transport)
    assert status["state"] == "completed"
    [reservation] = ProviderReservation.objects.all()
    assert reservation.cached_input_tokens == 8
    # Same charge as an uncached attempt: 9 x US$1/M + 3 x US$2/M.
    assert (reservation.charge_input_tokens, reservation.charge_cost_micros) == (9, 15)


def test_an_unreported_cache_count_stays_unknown(runtime):
    _, transport = admitted(runtime, reply(prompt_tokens=9, completion_tokens=3))
    answer_one(runtime, "cached-unknown@cit.edu", "cached-unknown-1", transport)
    assert ProviderReservation.objects.get().cached_input_tokens is None
