"""Why an AI-runtime provider attempt was not made (IR-725).

Codes shared with Django's admission keep its names (IR-545).
"""

from __future__ import annotations

NOT_CONFIGURED = "not_configured"
STORE_UNAVAILABLE = "store_unavailable"
UNPRICED_MODEL = "unpriced_model"
LANE_NOT_CONFIGURED = "lane_not_configured"
LANE_BUSY = "lane_busy"
ACCOUNT_BUSY = "account_busy"
CAMPAIGN_EXHAUSTED = "campaign_exhausted"
RUN_BUDGET_EXHAUSTED = "run_budget_exhausted"
RUN_CANCELLED = "run_cancelled"
#: Specific to the AI runtime.
NOT_BOUND = "not_bound"
DEADLINE = "deadline"
ACCESS_REVOKED = "access_revoked"
WITHHELD = "source_unavailable"
PROVIDER_REFUSED = "provider_refused"


class AdmissionDenied(Exception):
    """Nothing was sent. Never retried."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
