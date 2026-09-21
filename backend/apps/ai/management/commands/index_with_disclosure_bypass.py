"""Index records with ADR-015's disclosure gate bypassed — development only (IR-317).

    python manage.py index_with_disclosure_bypass --dry-run       # what it would cost
    python manage.py index_with_disclosure_bypass --record 29     # index one record
    python manage.py index_with_disclosure_bypass                 # index the corpus

**Why this exists at all.** The gate refuses every record (IR-250: `Record`
carries no embargo field, and an undetermined embargo is treated as an
embargo), so `backfill_embeddings` indexes nothing and Ask IRIS answers "no
readable sources" to every question. Until CIT-U decides what an embargo is,
this is how the RAG work is exercised end to end instead of only in tests.

**Why a separate command rather than a flag on `backfill_embeddings`.** This
file is the whole bypass on the indexing path: IR-250 deletes it and nothing
is left behind to find. A `--bypass-disclosure` flag on the permanent command
would be surgery in a file that stays.

**What it deliberately does not do.** No `EmbeddingJob` rows and no Celery: a
dev tool run from a terminal is watched by the person running it, and the
durable per-record record of a corpus run belongs to `backfill_embeddings`,
which is the command an operator will actually use once the gate opens. The
spend ceiling *is* honoured — a bypass that also removed the cost guard would
be two decisions wearing one name.

Refuses with `DEBUG` off unless `--force`, like `seed_demo` and `load_corpus`.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai.backfill import (
    RunReport,
    cost_per_million,
    default_ceiling,
    plan_records,
    records_to_consider,
)
from apps.ai.policy.bypass import permit_everything


class Command(BaseCommand):
    help = (
        "Embed records with the ADR-015 disclosure gate bypassed. "
        "Development only (IR-317); removed by IR-250."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--record",
            type=int,
            action="append",
            dest="record_ids",
            help="Limit the run to this record id. Repeatable.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Consider at most this many records, lowest id first. 0 means all.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the plan and stop. Nothing is sent to the vendor.",
        )
        parser.add_argument(
            "--token-ceiling",
            type=int,
            default=None,
            help="Refuse to start when the estimate exceeds this many tokens. "
            "Defaults to AI_EMBEDDING_TOKEN_CEILING; 0 disables the guard.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run with DEBUG off. Says out loud that somebody chose to "
            "disable a security control outside development.",
        )

    def handle(self, *args, **options):
        self._refuse_outside_development(force=options["force"])

        from apps.ai.indexing import embed_active_chunk_set, embed_record_summary
        from apps.ai.models import (
            VECTOR_COLUMN_DIMENSIONS,
            assert_embedding_space_consistent,
            get_active_embedding_space,
        )

        assert_embedding_space_consistent(VECTOR_COLUMN_DIMENSIONS, context="indexing")
        space = get_active_embedding_space()

        records = records_to_consider(options["record_ids"])
        if options["limit"]:
            records = records[: options["limit"]]

        plan = plan_records(
            records,
            space_id=space.id,
            space_model=space.model_id,
            cost_per_million=cost_per_million(),
        )
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nEmbedding space {plan.space_id}: {plan.space_model}"
            )
        )
        self.stdout.write(f"  records to embed     {len(plan.to_embed)}")
        self.stdout.write(f"  chunks to embed      {plan.chunk_count:,}")
        self.stdout.write(f"  estimated tokens     {plan.estimated_tokens:,}")
        self.stdout.write(
            f"  approximate cost     ~{plan.estimated_cost:,.2f} "
            f"at {plan.cost_per_million}/M tokens"
        )

        ceiling = (
            options["token_ceiling"]
            if options["token_ceiling"] is not None
            else default_ceiling()
        )
        if plan.exceeds(ceiling):
            raise CommandError(
                f"Estimated {plan.estimated_tokens:,} tokens, over the ceiling of "
                f"{ceiling:,}. Nothing has been sent. Narrow the run (--record, "
                f"--limit) or raise the ceiling deliberately with --token-ceiling."
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run: nothing was sent."))
            return

        if not plan.to_embed:
            self.stdout.write(self.style.SUCCESS("\nNothing to embed."))
            return

        self.stdout.write(
            self.style.WARNING(
                "\nThe ADR-015 disclosure gate is bypassed for this run. Record "
                "content is being sent to a commercial vendor with no embargo "
                "check. Point this only at content already cleared to leave.\n"
                "  · Voyage's training opt-out is not retroactive and needs a "
                "payment method on file (ADR-015 requirement 2). Confirm the "
                "toggle is flipped before sending more.\n"
                "  · `/api/v1/ai/status/` reports the *setting*, not this "
                "command, so an index built here is not self-labelling — the "
                "banner appears only when "
                "AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT is also on."
            )
        )

        report = RunReport()
        for item in plan.to_embed:
            try:
                embed_record_summary(
                    item.record_id, skip_existing=True, permits=permit_everything
                )
                outcome = embed_active_chunk_set(
                    item.record_id, permits=permit_everything
                )
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                report.record_failure(item.record_id, exc)
                self.stdout.write(self.style.ERROR(f"  record {item.record_id}: {exc}"))
                continue
            report.record_outcome(outcome)

        self.stdout.write(self.style.MIGRATE_HEADING("\nRun"))
        self.stdout.write(f"  records embedded     {report.embedded_records}")
        self.stdout.write(f"  chunks embedded      {report.embedded_chunks:,}")
        self.stdout.write(f"  records skipped      {report.skipped_records}")
        if report.failed:
            self.stdout.write(
                self.style.ERROR(f"  failed               {len(report.failed)}")
            )
            for record_id, error in report.failed[:10]:
                self.stdout.write(f"      record {record_id}: {error}")

    def _refuse_outside_development(self, *, force: bool) -> None:
        if settings.DEBUG or force:
            return
        raise CommandError(
            "DEBUG is off, and this command disables ADR-015's disclosure gate "
            "— the control that stops unpublished student work reaching a "
            "commercial vendor. It is for development only. Pass --force if "
            "you are certain this environment holds nothing but content "
            "already cleared to leave."
        )
