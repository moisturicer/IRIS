"""Read papers with Unstructured for IR-1054's trial chunk sets.

    python manage.py trial_read_unstructured --question-set <set.json> --dry-run
    python manage.py trial_read_unstructured --all --limit 6 --replace-stored-read

Replaces each paper's stored extraction; run it on a database copy.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai.trial_reads import USD_PER_PAGE, read_records, records_in_question_set, stored_pages


class Command(BaseCommand):
    help = "Read papers with Unstructured into their stored extraction (IR-1054). Development only."

    def add_arguments(self, parser):
        parser.add_argument("--record", type=int, action="append", default=[])
        parser.add_argument("--question-set", type=Path, action="append", default=[])
        parser.add_argument("--all", action="store_true", help="Every paper with an active chunk set.")
        parser.add_argument("--limit", type=int, help="Stop after this many paid reads.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--replace-stored-read", action="store_true",
                            help="Required to send: each read replaces the stored extraction.")
        parser.add_argument("--store-media", action="store_true",
                            help="For papers already read: store Figures and formula crops "
                                 "from the stored read. Sends nothing to Unstructured.")

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["replace_stored_read"]:
            raise CommandError("Each read replaces the paper's stored extraction; pass "
                               "--replace-stored-read, on a database copy.")
        if not settings.DEBUG:
            raise CommandError("Refused with DEBUG off: this is a development measurement tool.")
        ids = self._records(options)
        if options["store_media"]:
            from apps.ai.trial_reads import store_media

            for record_id, (figures, formulas) in store_media(ids).items():
                self.stdout.write(f"  record {record_id}: {figures} figure(s), {formulas} formula crop(s)")
            return
        if options["limit"] is not None:
            ids = ids[:options["limit"]] if options["dry_run"] else ids
        if options["dry_run"]:
            pages = stored_pages(ids)
            self.stdout.write(f"Dry run: would read {len(ids)} paper(s), about {pages} pages, "
                              f"about ${pages * USD_PER_PAGE:.2f} at ${USD_PER_PAGE}/page.")
            return
        from apps.ai.extraction.selection import unstructured_extractor

        outcome = read_records(ids, extractor=unstructured_extractor(), limit=options["limit"],
                               report=self.stdout.write)
        self.stdout.write(
            f"Read {len(outcome.read)} paper(s): {outcome.pages} pages billed, about "
            f"${outcome.pages * USD_PER_PAGE:.2f}. Skipped {len(outcome.skipped)}, "
            f"failed {len(outcome.failed)}.")
        for record_id, reason in {**outcome.skipped, **outcome.failed}.items():
            self.stdout.write(f"  record {record_id}: {reason}")

    def _records(self, options):
        from apps.ai.models.chunk import ChunkSet

        ids = set(options["record"])
        for path in options["question_set"]:
            ids.update(records_in_question_set(path))
        if options["all"]:
            ids.update(ChunkSet.objects.filter(is_active=True).values_list("record_id", flat=True))
        if not ids:
            raise CommandError("Name papers with --record, --question-set or --all.")
        return sorted(ids)
