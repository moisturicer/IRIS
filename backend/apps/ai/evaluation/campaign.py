"""May a paid evaluation start inside the shared provider campaign? (IR-550)

Paid evaluation questions, load submissions, retries, fallbacks, probes and
debugging all spend through the same admission ledger (IR-545, ADR-041). This
reads that ledger and asks `capacity.plan_burst` whether ``n`` more runs, each
at its per-run cap, fit what is spendable before the protected reserve. It
reserves nothing: admission still decides every physical attempt, and a run
that does not fit here does not start.
"""

from __future__ import annotations

from apps.ai.admission.ledger import ALIAS
from apps.ai.admission.limits import NotConfigured, enforcing, read_limits
from apps.ai.models import ProviderCampaign

from .capacity import LIMITS, plan_burst


class PaidRunRefused(Exception):
    """A paid evaluation cannot start; the message says why."""


def _ceiling(ceiling) -> dict:
    return {limit: getattr(ceiling, limit) for limit in LIMITS}


def paid_plan(n: int) -> dict:
    """The plan for ``n`` paid runs, or `PaidRunRefused` when nothing can bound them."""
    if not enforcing():
        raise PaidRunRefused(
            "AI_PROVIDER_ADMISSION is not 'enforce', so paid evaluation would bypass the "
            "campaign ceiling")
    try:
        limits = read_limits()
    except NotConfigured as unset:
        raise PaidRunRefused(f"provider admission is not configured: {unset}") from None
    row = ProviderCampaign.objects.using(ALIAS).filter(key=limits.campaign_key).first()
    charged = {limit: (getattr(row, f"charged_{limit}") if row else 0) for limit in LIMITS}
    plan = plan_burst(n, per_run=_ceiling(limits.run), spendable=_ceiling(limits.spendable),
                      charged=charged)
    return {"campaign": limits.campaign_key, "reserve_released": limits.reserve_released, **plan}
