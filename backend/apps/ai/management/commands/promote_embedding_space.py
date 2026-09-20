"""Make an Embedding Space live, once it is actually complete (IR-282).

    python manage.py promote_embedding_space --space 3 --check
    python manage.py promote_embedding_space --space 3

**Separate from the backfill on purpose.** Promotion is the decision that a
space is ready to answer questions; folding it into the run that fills the
space would make it a side effect of finishing, and "finishing" includes
finishing badly. A space that goes active half-indexed answers confidently
from the half it holds, and a chunk with no vector does not rank low — it is
simply not there, invisibly.

So this refuses while any active chunk lacks a vector in the target space,
and says which records are short. Nothing promotes automatically.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai.promotion import PromotionRefused, promote, records_missing_vectors


class Command(BaseCommand):
    help = "Promote a pending EmbeddingSpace to active, refusing if it is incomplete."

    def add_arguments(self, parser):
        parser.add_argument(
            "--space",
            type=int,
            required=True,
            dest="space_id",
            help="The EmbeddingSpace id to promote.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report readiness and stop. Nothing is promoted.",
        )
        parser.add_argument(
            "--show",
            type=int,
            default=20,
            help="How many short records to list (default 20).",
        )

    def handle(self, *args, **options):
        from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState

        space = EmbeddingSpace.objects.filter(pk=options["space_id"]).first()
        if space is None:
            raise CommandError(f"No EmbeddingSpace with id {options['space_id']}.")

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\nEmbeddingSpace {space.pk}: {space}")
        )

        shortfalls = records_missing_vectors(space.pk)
        if shortfalls:
            self.stdout.write(
                self.style.ERROR(
                    f"  {len(shortfalls)} record(s) have active chunks with no "
                    f"vector in this space:"
                )
            )
            for short in shortfalls[: options["show"]]:
                self.stdout.write(
                    f"      record {short.record_id}: {short.missing} of "
                    f"{short.total} chunk(s) short — {short.title[:60]}"
                )
            if len(shortfalls) > options["show"]:
                self.stdout.write(f"      … and {len(shortfalls) - options['show']} more")
        else:
            self.stdout.write(self.style.SUCCESS("  every active chunk has a vector"))

        if options["check"]:
            return

        if space.state == EmbeddingSpaceState.ACTIVE:
            self.stdout.write(self.style.WARNING("\nAlready active. Nothing to do."))
            return

        try:
            promote(space)
        except PromotionRefused as exc:
            raise CommandError(
                f"{exc} Run `backfill_embeddings` until this reports clean, then "
                f"promote again."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"\nPromoted space {space.pk} to active. Any previously active "
                f"space is retired, not deleted — its vectors point at it with "
                f"on_delete=CASCADE."
            )
        )
