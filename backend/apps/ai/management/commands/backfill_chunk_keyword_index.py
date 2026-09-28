"""Fill the chunk keyword index for chunks that have none (IR-393).

    python manage.py backfill_chunk_keyword_index --dry-run   # how many are short
    python manage.py backfill_chunk_keyword_index             # fill them

Migration `0015` fills the table once and the trigger keeps it current, so a
healthy deployment has nothing to do here; this is for a table restored from
an older dump, or a fill interrupted partway. Resumable and idempotent the
way `backfill_embeddings` is -- by recomputing what is short, not by a
checkpoint.
"""

from django.core.management.base import BaseCommand

from apps.ai.keyword_index import (
    DEFAULT_BATCH_SIZE,
    backfill_chunk_keyword_index,
    chunks_awaiting_backfill,
)


class Command(BaseCommand):
    help = "Populate the DocumentChunk keyword index for chunks that have none."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many chunks are short and stop.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Rows per UPDATE. Default {DEFAULT_BATCH_SIZE}.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after this many chunks. 0 means all of them.",
        )

    def handle(self, *args, **options):
        outstanding = chunks_awaiting_backfill()
        self.stdout.write(f"chunks with no keyword index: {outstanding}")

        if options["dry_run"]:
            self.stdout.write("dry run: nothing written.")
            return

        if not outstanding:
            self.stdout.write(self.style.SUCCESS("nothing to do."))
            return

        filled = backfill_chunk_keyword_index(
            batch_size=options["batch_size"],
            limit=options["limit"],
            on_batch=lambda total: self.stdout.write(f"  filled {total}/{outstanding}"),
        )
        remaining = chunks_awaiting_backfill()
        self.stdout.write(
            self.style.SUCCESS(f"filled {filled}; {remaining} still outstanding.")
        )
