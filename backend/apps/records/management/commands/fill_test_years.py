"""Give loaded test papers random completion and publication years (IR-1316).

    python manage.py fill_test_years --dry-run
    python manage.py fill_test_years
    python manage.py fill_test_years --undo

For testing date questions only: the years are made up and say nothing about the
papers. Only the named loader's published papers declared an imported reference or
synthetic are touched, and only their blank years. The same seed always gives a
paper the same years, so `--undo` with that seed blanks them again and keeps any a
person has since changed. It cannot tell a recorded year that happens to equal the
seed's from one it wrote, so run it only on papers this command filled.

Refuses with `DEBUG` off, and has no `--force`. Calls no vendor.
"""

import random
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.records.management.commands.load_corpus import DEFAULT_OWNER_EMAIL
from apps.records.models import Record
from core.enums import PipelineStatus

FIRST_YEAR = 2015
#: The years end here whatever the clock says, so a seed always means the same values.
LAST_YEAR = 2026


def years_for(record_id: int, seed: int) -> tuple[int, int]:
    """(completion year, publication year), published in its completion year or up to two later."""
    rng = random.Random(f"{seed}:{record_id}")
    completed = rng.randint(FIRST_YEAR, LAST_YEAR)
    return completed, min(LAST_YEAR, completed + rng.randint(0, 2))


class Command(BaseCommand):
    help = "Fill blank years on loaded test papers at random (IR-1316). Development only."

    def add_arguments(self, parser):
        parser.add_argument("--owner-email", default=DEFAULT_OWNER_EMAIL,
                            help=f"Whose loaded papers to fill (default: {DEFAULT_OWNER_EMAIL}).")
        parser.add_argument("--seed", type=int, default=1316)
        parser.add_argument("--undo", action="store_true", help="Blank the years this seed gave.")
        parser.add_argument("--dry-run", action="store_true", help="Report what would happen; write nothing.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("refusing to write made-up years with DEBUG off.")
        if date.today().year < LAST_YEAR:
            raise CommandError(f"The clock is before {LAST_YEAR}: these years would be in the future.")
        owner = User.objects.filter(email=options["owner_email"]).first()
        if owner is None:
            raise CommandError(f"no account has the email {options['owner_email']}.")
        papers = Record.objects.filter(
            added_by=owner, pipeline_status=PipelineStatus.PUBLISHED,
            origin__in=(Record.Origin.IMPORTED_REFERENCE, Record.Origin.SYNTHETIC),
        ).order_by("pk")

        changed = 0
        with transaction.atomic():
            for record in papers.select_for_update():
                values = self._values(record, options["seed"], options["undo"])
                if not values:
                    continue
                changed += 1
                self.stdout.write(f"  Record {record.pk}: {values}")
                if not options["dry_run"]:
                    # update(), not save(): a made-up year needs no re-index or edit stamp.
                    Record.objects.filter(pk=record.pk).update(**values)
        verb = "Would change" if options["dry_run"] else "Changed"
        self.stdout.write(f"{verb} {changed} of {papers.count()} test paper(s), seed {options['seed']}.")

    @staticmethod
    def _values(record, seed: int, undo: bool) -> dict:
        completed, published = years_for(record.pk, seed)
        values = {}
        if undo:
            if record.year_accomplished == completed:
                values["year_accomplished"] = None
            if record.publication_year == published:
                values["publication_year"] = None
        else:
            if record.year_accomplished is None and record.year_completed is None:
                values["year_accomplished"] = completed
            if record.publication_year is None:
                values["publication_year"] = published
        return values
