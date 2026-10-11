"""Remove seeded demo records left behind by older workflow versions.

Run without arguments to preview the affected records. Pass ``--execute`` to
delete them and their database-linked workflow data. Only records whose title
starts with ``[DEMO]`` are in scope; shared accounts, catalogue data, and
uploaded files are not removed.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.records.models import Record


PREFIX = "[DEMO]"


class Command(BaseCommand):
    help = "Preview or remove seeded [DEMO] records and their linked database rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Delete the listed demo records. Without this flag, only preview.",
        )

    def handle(self, *args, **options):
        records = Record.objects.filter(title__startswith=PREFIX).order_by("id")
        rows = list(records.values_list("id", "title"))
        if not rows:
            self.stdout.write("No [DEMO] records found.")
            return

        self.stdout.write(f"Found {len(rows)} [DEMO] record(s):")
        for record_id, title in rows:
            self.stdout.write(f"  {record_id}: {title}")

        if not options["execute"]:
            self.stdout.write("Preview only. Pass --execute to delete these records.")
            return

        if not settings.DEBUG:
            raise CommandError("refusing to delete demo records while DEBUG is off")

        with transaction.atomic():
            deleted, _by_model = records.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Deleted {len(rows)} [DEMO] record(s) and {deleted - len(rows)} linked database row(s)."
        ))
