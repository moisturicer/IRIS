"""How much of the provider campaign is spent (IR-545, ADR-041)?

    python manage.py provider_campaign

Prints the configured campaign's charged totals against its limits -- the
core share and the whole ceiling -- and how many attempts are in flight per
lane. Reads only; calls no vendor and reserves nothing. Charges include open
reservations at their worst case and every attempt whose usage the vendor
never reported, so the figure is an upper bound on the bill, not an estimate.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.ai.admission.ledger import ALIAS
from apps.ai.admission.limits import NotConfigured, read_limits
from apps.ai.models import ProviderCampaign, ProviderReservation
from apps.ai.models.admission import OPEN


class Command(BaseCommand):
    help = "Show the provider campaign's charged totals against its limits."

    def handle(self, *args, **options):
        try:
            limits = read_limits()
        except NotConfigured as unset:
            raise CommandError(f"Provider admission is not configured: {unset}") from None
        campaign = ProviderCampaign.objects.using(ALIAS).filter(key=limits.campaign_key).first()
        out = self.stdout
        out.write(f"campaign {limits.campaign_key}")
        if campaign is None:
            out.write("  nothing charged yet")
            return
        reserve = "released" if limits.reserve_released else "held"
        out.write(f"  protected reserve {limits.reserve_fraction:.0%}, {reserve}")
        rows = (
            ("attempts", campaign.charged_attempts, limits.spendable.attempts, limits.campaign.attempts),
            ("input tokens", campaign.charged_input_tokens, limits.spendable.input_tokens,
             limits.campaign.input_tokens),
            ("output tokens", campaign.charged_output_tokens, limits.spendable.output_tokens,
             limits.campaign.output_tokens),
            ("cost US$", campaign.charged_cost_micros / 1e6, limits.spendable.cost_micros / 1e6,
             limits.campaign.cost_micros / 1e6),
            ("active minutes", campaign.charged_active_ms / 60_000, limits.spendable.active_ms / 60_000,
             limits.campaign.active_ms / 60_000),
        )
        out.write(f"  {'':<15}{'charged':>14}{'spendable':>14}{'ceiling':>14}")
        for name, charged, spendable, ceiling in rows:
            out.write(f"  {name:<15}{charged:>14,.2f}{spendable:>14,.2f}{ceiling:>14,.2f}")
        in_flight = (
            ProviderReservation.objects.using(ALIAS)
            .filter(campaign=campaign, state=OPEN)
            .values("lane").annotate(n=Count("pk")).order_by("lane")
        )
        out.write("  in flight: " + (
            ", ".join(f"{row['lane']} {row['n']}/{limits.lanes.get(row['lane'], 0)}" for row in in_flight)
            or "none"
        ))
