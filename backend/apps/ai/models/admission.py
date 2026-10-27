"""What every paid provider attempt reserved and was charged (IR-545, ADR-041).

Two tables, both written only through the `admission` database alias so a
reservation commits on its own, whatever transaction its caller is inside.

`ProviderCampaign` is one spending ceiling and its running totals. Its row is
the lock: every admission takes it ``FOR UPDATE``, so two processes, workers or
replicas cannot both read "one attempt left" and both spend it.

`ProviderReservation` is one physical attempt -- one HTTP request to a vendor,
including a retry or a fallback model. It is written *before* the request is
sent, holding the worst case the request could cost, and settled afterwards
to what the vendor reported. An attempt whose usage never comes back keeps
its reservation as its charge: unknown is conservative, not zero.

The campaign's ``charged_*`` columns are the sum of every reservation's
``charge_*`` columns, kept in step inside the same transaction; a test checks
the invariant.
"""

from django.db import models

OPEN = "open"
SETTLED = "settled"
#: Its lease ran out with no settlement: the worker died or stalled. Charged
#: at its reservation, and no longer holding a concurrency slot.
ABANDONED = "abandoned"
#: Admitted, then never sent: nothing to pay for.
RELEASED = "released"

_STATES = [(s, s.title()) for s in (OPEN, SETTLED, ABANDONED, RELEASED)]


class ProviderCampaign(models.Model):
    key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    charged_attempts = models.PositiveIntegerField(default=0)
    charged_input_tokens = models.BigIntegerField(default=0)
    charged_output_tokens = models.BigIntegerField(default=0)
    #: Micro-US-dollars, so no float ever accumulates.
    charged_cost_micros = models.BigIntegerField(default=0)
    #: Summed wall time of physical attempts, reserved at each one's lease.
    charged_active_ms = models.BigIntegerField(default=0)

    def __str__(self) -> str:
        return f"ProviderCampaign({self.key})"


class ProviderReservation(models.Model):
    campaign = models.ForeignKey(
        ProviderCampaign, on_delete=models.PROTECT, related_name="reservations"
    )
    #: The workload that caused the call: chat, research, ingestion, ...
    lane = models.CharField(max_length=32)
    #: A digest of the vendor endpoint and key, never the key itself. Two
    #: lanes or tasks sharing a credential share this, and its limit.
    account = models.CharField(max_length=32)
    #: `embed`, `rerank`, `llm` or `decision`.
    operation = models.CharField(max_length=16)
    model = models.CharField(max_length=128)
    #: The run that owns the call (``ask:<uuid>`` for a queued question), or
    #: blank outside one. Per-run caps sum over it.
    run_key = models.CharField(max_length=64, blank=True)
    work_key = models.CharField(max_length=64, blank=True, db_index=True)
    state = models.CharField(max_length=16, choices=_STATES, default=OPEN)
    created_at = models.DateTimeField()
    #: Until this moment the attempt may still be talking to the vendor, so
    #: it holds its concurrency slot. Renewed while a stream is still arriving.
    lease_expires_at = models.DateTimeField()
    settled_at = models.DateTimeField(null=True, blank=True)
    #: Whether the request was actually handed to the transport. An attempt
    #: that failed before sending is released, not charged.
    sent = models.BooleanField(default=False)
    #: Whether the vendor reported its usage. False means the charge is the
    #: reservation.
    usage_reported = models.BooleanField(default=False)
    reserved_input_tokens = models.BigIntegerField()
    reserved_output_tokens = models.BigIntegerField()
    reserved_cost_micros = models.BigIntegerField()
    reserved_active_ms = models.BigIntegerField()
    charge_input_tokens = models.BigIntegerField()
    charge_output_tokens = models.BigIntegerField()
    charge_cost_micros = models.BigIntegerField()
    charge_active_ms = models.BigIntegerField()
    #: 1 while it counts as a physical attempt; 0 once released unsent.
    charge_attempts = models.PositiveSmallIntegerField(default=1)

    class Meta:
        indexes = [
            models.Index(fields=["campaign", "state", "lane"]),
            models.Index(fields=["campaign", "state", "account"]),
            models.Index(fields=["campaign", "run_key"]),
        ]

    def __str__(self) -> str:
        return f"ProviderReservation({self.pk}, {self.lane}, {self.state})"
