"""Cut the corpus over to LlamaParse, with the bill shown first (IR-842, ADR-056).

    python manage.py reextract_manuscripts --dry-run
    python manage.py reextract_manuscripts --credit-ceiling 2000 [--record N ...]
    python manage.py reextract_manuscripts --rollback [--record N ...]

A run queues each permitted paper's read on the `extraction` queue; the gate
and admission apply to every read. Re-chunking swaps atomically once a read
lands, and then `backfill_embeddings` embeds only the changed chunks.

Resumable and idempotent: a paper already read or in flight is skipped, a
failed one is read again. No ceiling has a default, so a real run must state one.
"""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai import reextraction


class Command(BaseCommand):
    help = "Re-read manuscripts with LlamaParse, showing the cost first."

    def add_arguments(self, parser):
        parser.add_argument("--record", type=int, action="append", dest="record_ids")
        parser.add_argument("--limit", type=int, default=0, help="At most this many papers, lowest id first.")
        parser.add_argument("--dry-run", action="store_true", help="Print the plan and stop.")
        parser.add_argument(
            "--credit-ceiling", default=None,
            help="Refuse when the estimate exceeds this many LlamaParse credits. Required for a real run.",
        )
        parser.add_argument(
            "--rollback", action="store_true",
            help="Reactivate each record's previous ChunkSet. Reads nothing and spends nothing.",
        )

    def handle(self, *args, **options):
        if options["rollback"]:
            restored = reextraction.rollback(options["record_ids"])
            self.stdout.write(self.style.SUCCESS(f"Restored the previous ChunkSet of {restored} record(s)."))
            return

        try:
            plan = reextraction.plan_cutover(options["record_ids"])
        except reextraction.NotConfigured as error:
            raise CommandError(f"Extraction price is not set: {error}. Nothing was sent.") from None
        if options["limit"]:
            plan = plan.limited(options["limit"])
        self._write_plan(plan)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run: nothing was sent."))
            return

        ceiling = self._ceiling(options["credit_ceiling"])
        if settings.EXTRACTION_BACKEND != "llamaparse":
            raise CommandError(
                f"EXTRACTION_BACKEND is {settings.EXTRACTION_BACKEND!r}; set it to 'llamaparse' "
                f"first, or the reads would go to Docling. Nothing was sent."
            )
        if plan.exceeds(ceiling):
            raise CommandError(
                f"Estimated {plan.credits:,} credits, over the ceiling of {ceiling:,}. Nothing was sent. "
                f"Narrow the run (--record, --limit) or raise the ceiling deliberately."
            )
        queued = reextraction.queue_reads(plan)
        self.stdout.write(self.style.SUCCESS(
            f"\nQueued {queued} paper(s) on the `extraction` queue. Run backfill_embeddings "
            f"--dry-run once they finish."
        ))

    def _ceiling(self, raw):
        try:
            ceiling = Decimal(raw) if raw is not None else Decimal(0)
        except InvalidOperation:
            raise CommandError(f"--credit-ceiling must be a number, not {raw!r}.") from None
        if ceiling <= 0:
            raise CommandError("A real run needs --credit-ceiling set above 0: spend is approved before it runs.")
        return ceiling

    def _write_plan(self, plan):
        self.stdout.write(self.style.MIGRATE_HEADING("\nLlamaParse cutover"))
        self.stdout.write(f"  papers to read       {len(plan.to_read)}")
        self.stdout.write(f"  pages                {plan.pages}")
        self.stdout.write(f"  credits (upper)      {plan.credits:,}  at {plan.credits_per_page}/page")
        self.stdout.write(f"  LlamaParse (upper)   ~US${plan.usd:,.2f}")
        self.stdout.write(
            f"  Voyage (upper)       ~US${plan.embed_usd:,.4f}  ({plan.embed_tokens:,} tokens if every "
            f"chunk changed; backfill_embeddings --dry-run prices the real set)"
        )
        self.stdout.write("  describe_figure      per Figure; unknown until each paper is read")
        reasons: dict[str, int] = {}
        for item in plan.skipped:
            reasons[item.reason] = reasons.get(item.reason, 0) + 1
        if reasons:
            self.stdout.write(self.style.MIGRATE_HEADING("\nSkipped"))
            for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
                self.stdout.write(f"  {count:>6}  {reason}")
