"""Shared limits hold across independent processes (IR-545).

Each probe is a separate Python interpreter with its own Django, its own
connections and no memory shared with this one -- what two Celery workers or
two replicas are to each other. They start at the same instant and contend
for the same campaign row in the real test database. A process-local counter
would let each of them spend the whole limit; the totals below show they
spent it once between them.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from django.db import connections

from apps.ai.admission import errors, ledger
from apps.ai.models import ProviderCampaign, ProviderReservation
from apps.ai.models.admission import ABANDONED, OPEN

from .support import CAMPAIGN, enforce

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]

BACKEND = Path(__file__).resolve().parents[4]


def _environment(**overrides) -> dict:
    env = dict(os.environ)
    env.update(CAMPAIGN)
    env.update(
        AI_PROVIDER_ADMISSION="enforce",
        DB_NAME=connections["default"].settings_dict["NAME"],
        DJANGO_SETTINGS_MODULE="config.settings.development",
    )
    env.update(overrides)
    return env


def _run(mode: str, count: int, *, processes: int = 2, **overrides) -> list[dict]:
    start_at = time.time() + 3.0  # long enough for every interpreter to boot
    probes = [
        subprocess.Popen(
            [sys.executable, "-m", "apps.ai.admission.tests.probe", mode, str(count), str(start_at)],
            cwd=BACKEND, env=_environment(**overrides),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(processes)
    ]
    results = []
    for probe in probes:
        out, err = probe.communicate(timeout=120)
        lines = [line for line in out.splitlines() if line.startswith("{")]
        assert lines, f"probe printed nothing; stderr:\n{err[-2000:]}"
        results.append(json.loads(lines[-1]))
    return results


def _rows(**filters):
    return ProviderReservation.objects.using("admission").filter(**filters)


def test_two_processes_share_one_lane_limit(settings):
    overrides = {"AI_ADMISSION_LANE_CONCURRENCY": '{"research": 3}'}
    enforce(settings, **overrides)
    results = _run("hold", 5, **overrides)

    assert sum(r["admitted"] for r in results) == 3, results
    assert sorted(reason for r in results for reason in r["refused"]) == [errors.LANE_BUSY] * 7
    assert _rows(state=OPEN, lane="research").count() == 3


def test_two_processes_share_one_campaign_ceiling(settings):
    # 10 attempts, 25% protected: 7 spendable between both processes.
    overrides = {"AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS": "10", "AI_ADMISSION_RUN_MAX_ATTEMPTS": "100"}
    enforce(settings, **overrides)
    results = _run("spend", 10, **overrides)

    assert sum(r["admitted"] for r in results) == 7, results
    campaign = ProviderCampaign.objects.using("admission").get(key=CAMPAIGN["AI_ADMISSION_CAMPAIGN"])
    assert campaign.charged_attempts == 7
    assert all(set(r["refused"]) <= {errors.CAMPAIGN_EXHAUSTED} for r in results)


def test_a_crashed_worker_keeps_its_slot_until_its_lease_ends(settings):
    overrides = {
        "AI_ADMISSION_LANE_CONCURRENCY": '{"research": 1}',
        "AI_ADMISSION_LEASE_GRACE_SECONDS": "0",
        "PROBE_TIMEOUT": "2",
    }
    enforce(settings, **overrides)
    (crashed,) = _run("crash", 1, processes=1, **overrides)
    assert crashed["admitted"] == 1
    (orphan,) = _rows()

    request = ledger.Request(
        operation="llm", default_lane="research", account="probe-account", models=("cheap",),
        input_tokens=10, output_tokens=10, timeout_seconds=2.0,
    )
    from apps.ai.admission.scope import workload

    with workload("research"):
        with pytest.raises(errors.AdmissionDenied) as refused:
            ledger.admit(request)
        assert refused.value.reason == errors.LANE_BUSY, "its remote call may still be running"

        remaining = (orphan.lease_expires_at - orphan.created_at).total_seconds()
        time.sleep(max(0.0, remaining) + 0.2)
        ledger.admit(request)

    orphan.refresh_from_db(using="admission")
    assert orphan.state == ABANDONED
    assert orphan.charge_cost_micros == orphan.reserved_cost_micros, "unknown, so charged in full"
