"""Index the corpus, with the bill shown first (IR-282).

    python manage.py backfill_embeddings --dry-run      # what it would cost
    python manage.py backfill_embeddings                # run it inline
    python manage.py backfill_embeddings --queue        # hand it to workers

Shaped like `inspect_chunks` and `seed_demo` next door: a plan an operator
reads, then a run they choose.

**Dry run first is not a suggestion.** Indexing is metered per token and the
chunk token budget is known to undercount by roughly 44% (IR-243), so a
misconfigured chunk size is a live way to spend real money on a mistake. The
estimate is printed before anything is sent, and a hard ceiling refuses to
start when it is exceeded.

**Resumable and idempotent, by construction rather than by a checkpoint
file.** What the run embeds is "active chunks with no vector in this space",
recomputed each time, so a crash at record 3,000 resumes at record 3,000 and
a re-run of a finished corpus costs one query per record and no vendor call.
A chunk whose text survived a re-chunk already carries its vector across, so
unchanged text is skipped for free.

**The 4,910 placeholder uploads are skipped by construction.** Their whole
content is sixteen bytes of `%PDF-1.7 fake bytes`; they never extracted, so
they have no chunk set and there is nothing to embed. They are *counted and
named* in the report rather than merely absent, because five thousand
silently missing records is indistinguishable from a broken run. Nothing here
deletes them — that is a separate decision with a separate blast radius.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ai.backfill import (
    cost_per_million,
    default_ceiling,
    plan_records,
    records_to_consider,
    RunReport,
)


class Command(BaseCommand):
    help = "Embed the corpus into the active Embedding Space, showing the cost first."

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
            "--queue",
            action="store_true",
            help="Dispatch a Celery task per record instead of embedding inline. "
            "Needs a broker and a worker on the `embedding` queue.",
        )
        parser.add_argument(
            "--token-ceiling",
            type=int,
            default=None,
            help="Refuse to start when the estimate exceeds this many tokens. "
            "Defaults to AI_EMBEDDING_TOKEN_CEILING; 0 disables the guard.",
        )
        parser.add_argument(
            "--space",
            type=int,
            default=None,
            dest="space_id",
            help="Fill this EmbeddingSpace instead of the active one, so it can "
            "be promoted once complete. **Chunk vectors only**: `RecordEmbedding` "
            "is one row per record with no space key, so a summary vector cannot "
            "exist in two spaces at once and writing one here would overwrite the "
            "live space's. Summaries are left alone in this mode.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-embed chunks that already have a vector in this space. "
            "Spends the whole corpus again — say why before using it.",
        )

    def handle(self, *args, **options):
        from apps.ai.models import (
            VECTOR_COLUMN_DIMENSIONS,
            assert_embedding_space_consistent,
            get_active_embedding_space,
        )

        # Before anything is counted, let alone sent: a plan costed against a
        # space the columns cannot hold is a plan for a run that would fail
        # on its first write.
        assert_embedding_space_consistent(VECTOR_COLUMN_DIMENSIONS, context="indexing")
        space = self._target_space(options["space_id"], get_active_embedding_space)

        records = records_to_consider(options["record_ids"])
        if options["limit"]:
            records = records[: options["limit"]]

        plan = plan_records(
            records,
            space_id=space.id,
            space_model=space.model_id,
            cost_per_million=cost_per_million(),
            include_summaries=options["space_id"] is None,
        )
        self._write_plan(plan)

        ceiling = (
            options["token_ceiling"]
            if options["token_ceiling"] is not None
            else default_ceiling()
        )
        if plan.exceeds(ceiling):
            raise CommandError(
                f"Estimated {plan.estimated_tokens:,} tokens, over the ceiling of "
                f"{ceiling:,}. Nothing has been sent. Either narrow the run "
                f"(--record, --limit), check AI_CHUNK_MAX_TOKENS, or raise the "
                f"ceiling deliberately with --token-ceiling."
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run: nothing was sent."))
            return

        if not plan.to_embed:
            self.stdout.write(self.style.SUCCESS("\nNothing to embed."))
            return

        if options["queue"]:
            if options["space_id"] is not None:
                raise CommandError(
                    "--queue and --space cannot be combined: `index_record` "
                    "writes the active space. Run a targeted fill inline."
                )
            self._queue(plan, force=options["force"])
            return

        self._run_inline(
            plan, force=options["force"], space_id=options["space_id"]
        )

    # -- output ----------------------------------------------------------

    def _write_plan(self, plan):
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nEmbedding space {plan.space_id}: {plan.space_model}"
            )
        )
        self.stdout.write(f"  records considered   {len(plan.records)}")
        self.stdout.write(f"  records to embed     {len(plan.to_embed)}")
        self.stdout.write(f"  chunks to embed      {plan.chunk_count:,}")
        self.stdout.write(f"  summaries to embed   {plan.summary_count}")
        self.stdout.write(
            f"  estimated tokens     {plan.estimated_tokens:,}  "
            f"(an upper bound, not a quote)"
        )
        self.stdout.write(
            f"  approximate cost     ~{plan.estimated_cost:,.2f} "
            f"at {plan.cost_per_million}/M tokens"
        )

        reasons: dict[str, int] = {}
        for skipped in plan.skipped:
            reasons[skipped.reason] = reasons.get(skipped.reason, 0) + 1
        if reasons:
            self.stdout.write(self.style.MIGRATE_HEADING("\nSkipped"))
            for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
                self.stdout.write(f"  {count:>6}  {reason}")
        if plan.stub_records:
            self.stdout.write(
                self.style.WARNING(
                    f"  → {plan.stub_records} of those are placeholder uploads "
                    f"({len(plan.records)} records considered). They never "
                    f"extracted, so there is nothing to embed; nothing here "
                    f"deletes them."
                )
            )

    def _queue(self, plan, *, force: bool):
        from apps.ai.models import EmbeddingJob
        from apps.ai.tasks import index_record

        for item in plan.to_embed:
            job = EmbeddingJob.objects.create(record_id=item.record_id)
            task = index_record.delay(item.record_id, force=force)
            job.celery_task_id = task.id
            job.save(update_fields=["celery_task_id"])
        self.stdout.write(
            self.style.SUCCESS(
                f"\nQueued {len(plan.to_embed)} record(s) on the `embedding` queue. "
                f"Watch EmbeddingJob rows for failures."
            )
        )

    def _target_space(self, space_id, active):
        from apps.ai.models import EmbeddingSpace

        if space_id is None:
            return active()
        space = EmbeddingSpace.objects.filter(pk=space_id).first()
        if space is None:
            raise CommandError(f"No EmbeddingSpace with id {space_id}.")
        return space

    def _run_inline(self, plan, *, force: bool, space_id=None):
        """Embed record by record in this process, recording every failure.

        One record's failure does not abandon the rest: a corpus run that
        stops on the first bad row leaves an operator re-running the whole
        thing to find the second one. Everything that failed is listed at the
        end and stays pending, so the next run picks it up.
        """
        from apps.ai.indexing import embed_active_chunk_set, embed_record_summary
        from apps.ai.models import EmbeddingJob

        report = RunReport()
        for item in plan.to_embed:
            # A job row per record, on the inline path as much as the queued
            # one. Printing a failure to a terminal that is then closed is
            # not a record of it, and IR-282 asks that a failed per-record
            # job say why — which has to outlive the process that saw it.
            job = EmbeddingJob.objects.create(record_id=item.record_id, status="running")
            try:
                if space_id is None:
                    embed_record_summary(item.record_id, skip_existing=not force)
                outcome = embed_active_chunk_set(
                    item.record_id, force=force, space_id=space_id
                )
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                job.status = "failed"
                job.error = str(exc)
                job.save(update_fields=["status", "error"])
                report.record_failure(item.record_id, exc)
                self.stdout.write(
                    self.style.ERROR(f"  record {item.record_id}: {exc}")
                )
                continue

            if outcome.refused:
                job.status = "failed"
                job.error = outcome.reason
                job.save(update_fields=["status", "error"])
            else:
                job.status = "done"
                job.completed_at = timezone.now()
                job.save(update_fields=["status", "completed_at"])
            report.record_outcome(outcome)

        self._write_report(report)

    def _write_report(self, report):
        self.stdout.write(self.style.MIGRATE_HEADING("\nRun"))
        self.stdout.write(f"  records embedded     {report.embedded_records}")
        self.stdout.write(f"  chunks embedded      {report.embedded_chunks:,}")
        self.stdout.write(f"  records skipped      {report.skipped_records}")
        if report.refused:
            self.stdout.write(
                self.style.WARNING(f"  refused by policy    {len(report.refused)}")
            )
            for record_id, reason in report.refused[:10]:
                self.stdout.write(f"      record {record_id}: {reason}")
        if report.failed:
            self.stdout.write(self.style.ERROR(f"  failed               {len(report.failed)}"))
            for record_id, error in report.failed[:10]:
                self.stdout.write(f"      record {record_id}: {error}")
            self.stdout.write(
                "  Those records stay pending; re-running picks them up, and "
                "each carries an EmbeddingJob row saying why it failed."
            )
