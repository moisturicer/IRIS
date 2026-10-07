"""
`manage.py enter_new_model <record_id>` -- put a draft on the adviser-first
model, for development and demos only (IR-261, decided 2026-10-08).

Until IR-260 makes submission enter records itself, the only way onto the new
model is `routing.enter_at_adviser`, which `seed_demo` calls for one record.
This command calls the same function for any draft, so routing can be
demoed and tried again without editing the database by hand. It applies the
same rules -- a draft, an Adviser who is not an owner -- because it *is* that
function.

**Refuses with `DEBUG` off, and has no `--force`.** Unlike `seed_demo`, this
is a shortcut around the real submission path, so it must never run against a
production database. **IR-260 deletes it.**
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Development only: put a draft on the adviser-first review model (IR-261)."

    def add_arguments(self, parser):
        parser.add_argument("record_id", type=int, help="The draft to enter at its Adviser.")

    def handle(self, *args, **options):
        from apps.records.models import Record
        from apps.reviews.routing import RoutingError, enter_at_adviser

        if not settings.DEBUG:
            raise CommandError(
                "refusing to run with DEBUG off: this skips the real submission path "
                "and is for development only. It has no --force."
            )

        record = Record.objects.filter(pk=options["record_id"]).select_related("adviser").first()
        if record is None:
            raise CommandError(f"No record {options['record_id']}.")
        try:
            enter_at_adviser(record)
        except RoutingError as exc:
            raise CommandError(str(exc))

        record.refresh_from_db()
        adviser = record.adviser.get_full_name() or record.adviser.email
        self.stdout.write(self.style.SUCCESS(
            f"Record {record.pk} '{record.title[:60]}' is {record.pipeline_status}, "
            f"waiting at its Adviser ({adviser})."
        ))
