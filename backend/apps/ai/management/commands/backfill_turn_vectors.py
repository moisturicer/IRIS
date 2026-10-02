"""Give existing Turns the answer vector IR-447 added, with the bill first.

    python manage.py backfill_turn_vectors --dry-run    # what it would cost
    python manage.py backfill_turn_vectors              # run it inline

Shaped like `backfill_embeddings` next door, and for the same reason: a plan
an operator reads, then a run they choose.

**Why it exists.** IR-447 stores a Turn's answer as a second memory vector,
but only for Turns written after it shipped. Every Conversation already in the
database keeps its question vectors alone, so a fact stated only in an older
answer stays unreachable until this is run. Nothing backfills implicitly --
this spends money, so it is a decision an operator makes.

**Inline only, deliberately.** `backfill_embeddings` offers `--queue` because
a corpus run is thousands of records of PDF text; a Turn's answer is a few
hundred tokens and a Conversation holds a handful of them, so the work is
small enough that a broker and a worker would be ceremony. If a deployment
ever has enough history for that to stop being true, `--queue` is the thing to
add, not a second command.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai.backfill import cost_per_million, default_ceiling
from apps.ai.turn_backfill import (
    TurnRunReport,
    embed_turn_answer,
    plan_turns,
    turns_to_consider,
)


class Command(BaseCommand):
    help = (
        "Embed existing Turns' answers into an Embedding Space as memory "
        "vectors, showing the cost first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--conversation",
            type=int,
            action="append",
            dest="conversation_ids",
            help="Limit the run to this conversation id. Repeatable.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Consider at most this many Turns, lowest id first. 0 means all.",
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
            "--space",
            type=int,
            default=None,
            dest="space_id",
            help="Fill this space instead of the active one. Use when "
            "preparing a pending space for promotion.",
        )

    def handle(self, *args, **options):
        from apps.ai.composition import composition_root
        from apps.ai.models import (
            VECTOR_COLUMN_DIMENSIONS,
            assert_embedding_space_consistent,
            get_active_embedding_space,
        )

        # Before anything is counted, let alone sent: a plan costed against a
        # space the vector columns cannot hold is a plan for a run that fails
        # on its first write.
        assert_embedding_space_consistent(VECTOR_COLUMN_DIMENSIONS, context="indexing")
        space = self._target_space(options["space_id"], get_active_embedding_space)

        turns = turns_to_consider(options["conversation_ids"])
        if options["limit"]:
            turns = turns[: options["limit"]]

        plan = plan_turns(
            turns,
            space_id=space.id,
            space_model=space.model_id,
            cost_per_million=cost_per_million(),
        )
        self._write_plan(plan)

        ceiling = (
            options["token_ceiling"]
            if options["token_ceiling"] is not None
            else default_ceiling()
        )
        if plan.exceeds(ceiling):
            raise CommandError(
                f"Estimated {plan.estimated_tokens:,} tokens, over the ceiling "
                f"of {ceiling:,}. Nothing has been sent. Either narrow the run "
                f"(--conversation, --limit) or raise the ceiling deliberately "
                f"with --token-ceiling."
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run: nothing was sent."))
            return

        if not plan.to_embed:
            self.stdout.write(self.style.SUCCESS("\nNothing to embed."))
            return

        self._run_inline(plan, space_id=space.id, embedder=composition_root().embedder())

    # -- space -----------------------------------------------------------

    def _target_space(self, space_id, get_active):
        from apps.ai.models import EmbeddingSpace

        if space_id is None:
            return get_active()
        try:
            return EmbeddingSpace.objects.get(pk=space_id)
        except EmbeddingSpace.DoesNotExist as exc:
            raise CommandError(f"No embedding space with id {space_id}.") from exc

    # -- output ----------------------------------------------------------

    def _write_plan(self, plan):
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nEmbedding space {plan.space_id}: {plan.space_model}"
            )
        )
        self.stdout.write(f"  Turns considered     {plan.considered}")
        self.stdout.write(f"  Turns to embed       {len(plan.to_embed)}")
        self.stdout.write(
            f"  estimated tokens     {plan.estimated_tokens:,}  "
            f"(an upper bound, not a quote)"
        )
        self.stdout.write(
            f"  approximate cost     ~{plan.estimated_cost:,.2f} "
            f"at {plan.cost_per_million}/M tokens"
        )
        for reason, count in sorted(plan.skipped.items()):
            self.stdout.write(f"  skipped: {reason} — {count}")

    # -- run -------------------------------------------------------------

    def _run_inline(self, plan, *, space_id, embedder):
        from apps.ai.models import Turn

        report = TurnRunReport()
        for entry in plan.to_embed:
            turn = Turn.objects.get(pk=entry.turn_id)
            try:
                embed_turn_answer(turn, space_id=space_id, embedder=embedder)
            except Exception as exc:
                # Logged and carried, not raised: one Turn that will not embed
                # must not abandon the rest, and the run is resumable anyway,
                # so the next invocation retries exactly what is still missing.
                report.record_failure(entry.turn_id, exc)
                self.stderr.write(self.style.ERROR(f"  turn {entry.turn_id}: {exc}"))
            else:
                report.embedded += 1

        self.stdout.write(
            self.style.SUCCESS(f"\nEmbedded {report.embedded} Turn answers.")
        )
        if report.failed:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(report.failed)} failed. Re-run to retry only those."
                )
            )
