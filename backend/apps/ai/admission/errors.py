"""Why a paid provider attempt was not made (IR-545, ADR-041)."""

from __future__ import annotations

from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.resilience.rate_limit import RateLimited

#: Reason codes. Public: a queued run journals them, so they are names a
#: reader may see, never a number, a key or a vendor message.
NOT_CONFIGURED = "not_configured"
STORE_UNAVAILABLE = "store_unavailable"
UNPRICED_MODEL = "unpriced_model"
UNBOUNDED_OUTPUT = "unbounded_output"
LANE_NOT_CONFIGURED = "lane_not_configured"
LANE_BUSY = "lane_busy"
ACCOUNT_BUSY = "account_busy"
CAMPAIGN_EXHAUSTED = "campaign_exhausted"
RUN_BUDGET_EXHAUSTED = "run_budget_exhausted"
LEASE_LOST = "lease_lost"
#: The run's asker cancelled it (IR-548): nothing new is sent on its behalf.
RUN_CANCELLED = "run_cancelled"

#: Denials that hold for every later attempt in the run, whatever its lane
#: or model: the budget is spent, or nothing is configured. The run stops
#: asking. A refusal tied to one lane, one model or one transient error is not
#: here -- an unpriced rerank must not stop the answer that follows it.
STICKY = frozenset({NOT_CONFIGURED, CAMPAIGN_EXHAUSTED, RUN_BUDGET_EXHAUSTED, RUN_CANCELLED})


class AdmissionDenied(LLMUnavailable, RateLimited):
    """No reservation, so no request was sent.

    An `LLMUnavailable`, so every answer path already turns it into its
    explicit unavailable state with the sources it has (ADR-008). A
    `RateLimited`, so retrieval degrades to full text the way it does for a
    spent token bucket. Kind `rate_limit`, so `RetryingLLMProvider` does not
    retry it. It never counts against a circuit and never switches to a
    fallback model: IRIS refused itself, the vendor did not fail.
    """

    counts_against_circuit = False

    def __init__(self, reason: str) -> None:
        LLMUnavailable.__init__(self, f"provider admission refused: {reason}", kind=ErrorKind.RATE_LIMIT)
        self.reason = reason


class AdmissionLost(AdmissionDenied):
    """A running stream's lease could not be renewed: it ran out and the slot
    was given to someone else. The stream stops rather than overlap them."""

    def __init__(self) -> None:
        super().__init__(LEASE_LOST)
