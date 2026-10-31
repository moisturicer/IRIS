"""Give records with no abstract one read from their own manuscript (IR-703).

    python manage.py backfill_abstracts --dry-run
    python manage.py backfill_abstracts

Only empty abstracts are written. Record vectors embed title + abstract, so
re-embed the changed records afterwards. Refuses with DEBUG off unless --force.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai.abstracts import FRONT_CHUNKS, abstract_from
from apps.ai.indexing import active_chunks
from apps.records.models import Record


class Command(BaseCommand):
    help = "Fill empty Record abstracts from each record's manuscript chunks (IR-703)."

    def add_arguments(self, parser):
        parser.add_argument("--classification", action="append", default=[],
                            help="Only records in this Classification (repeatable).")
        parser.add_argument("--dry-run", action="store_true", help="Report; write nothing.")
        parser.add_argument("--force", action="store_true", help="Run even when DEBUG is off.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("refusing with DEBUG off; pass --force if this is not production.")
        written = missing = 0
        records = Record.objects.filter(abstract="")
        if options["classification"]:
            records = records.filter(classification__name__in=options["classification"])
        for record in records.order_by("pk"):
            chunks = active_chunks(record.pk).values_list("context_path", "content")[:FRONT_CHUNKS]
            abstract = abstract_from(chunks)
            if abstract is None:
                missing += 1
                self.stdout.write(f"  - {record.pk} {record.title[:70]} (none found)")
                continue
            if not options["dry_run"]:
                record.abstract = abstract
                record.save(update_fields=["abstract"])
            written += 1
            self.stdout.write(f"  + {record.pk} {record.title[:70]} ({len(abstract)} chars)")
        verb = "would be written" if options["dry_run"] else "written"
        self.stdout.write(self.style.SUCCESS(
            f"{written} abstract(s) {verb}; {missing} record(s) had none to find."))
