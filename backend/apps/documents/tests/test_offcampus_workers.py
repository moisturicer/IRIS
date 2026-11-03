"""Off-campus reads gated and admitted across independent workers (IR-850).

Each probe is its own Python interpreter -- what two Celery workers are to each
other -- running the real extraction task against the real test database. They
start at the same instant and contend for one campaign.
"""

import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from django.db import connections

from apps.ai.admission.tests.support import CAMPAIGN
from apps.ai.models import ProviderReservation
from apps.ai.models.admission import SETTLED
from apps.documents.phases import ExtractionPhase

from .test_offcampus_extraction import PAGES, PRICES, _record

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]

BACKEND = Path(__file__).resolve().parents[3]
#: A read reserves PAGES x US$0.015 (12 credits x US$0.00125 a page). The test
#: reserve leaves 75% spendable, so this campaign fits 1.5 reads: one, not two.
ONE_READ_CAMPAIGN_USD = str(PAGES * 0.015 * 1.5 / 0.75)


def _environment(**overrides) -> dict:
    env = dict(os.environ)
    env.update(CAMPAIGN)
    env.update(PRICES)
    env.update(
        AI_PROVIDER_ADMISSION="enforce",
        DB_NAME=connections["default"].settings_dict["NAME"],
        DJANGO_SETTINGS_MODULE="config.settings.development",
    )
    env.update(overrides)
    return env


def _workers(record_ids, *, credits=None, **overrides) -> list[dict]:
    start_at = time.time() + 3.0  # long enough for every interpreter to boot
    extra = [] if credits is None else [str(credits)]
    probes = [
        subprocess.Popen(
            [sys.executable, "-m", "apps.documents.tests.extraction_probe", str(pk), str(start_at), *extra],
            cwd=BACKEND, env=_environment(**overrides),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for pk in record_ids
    ]
    results = []
    for probe in probes:
        out, err = probe.communicate(timeout=180)
        lines = [line for line in out.splitlines() if line.startswith("{")]
        assert lines, f"probe printed nothing; stderr:\n{err[-2000:]}"
        results.append(json.loads(lines[-1]))
    return results


def test_two_workers_cannot_both_spend_a_campaign_with_room_for_one_read(settings):
    overrides = {"AI_ADMISSION_CAMPAIGN_MAX_COST_USD": ONE_READ_CAMPAIGN_USD}
    first, second = _record(), _record()

    results = _workers([first.pk, second.pk], credits=PAGES * 12, **overrides)

    assert sorted(r["sent"] for r in results) == [0, 1], results
    assert sorted(r["status"] for r in results) == ["done", "failed"], results
    assert ProviderReservation.objects.using("admission").filter(state=SETTLED).count() == 1


def test_a_worker_sends_the_released_paper_and_holds_the_embargoed_one(settings):
    released, embargoed = _record(), _record(embargo=date(2030, 1, 1))

    results = _workers([released.pk, embargoed.pk], credits=24)

    assert results[0] == {"sent": 1, "status": "done", "phase": ExtractionPhase.READY}
    assert results[1] == {"sent": 0, "status": "queued", "phase": ExtractionPhase.AWAITING_DISCLOSURE}
