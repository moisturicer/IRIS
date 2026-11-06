"""Mark papers already loaded for testing as cleared for the AI (IR-815, IR-882).

    python manage.py mark_corpus_cleared --dry-run
    python manage.py mark_corpus_cleared
    python manage.py mark_corpus_cleared --owner-email someone@cit.edu

ADR-052 decision 16, as amended for IR-882: a development database's proxy
papers are released once. Every paper starts embargoed, so the gate refuses them
until something releases them. `load_corpus --clear-for-ai` does the same for
papers it is loading now.

Only the named loader's papers that are embargoed with no review date and have
never been released. A date someone set is never overridden, a released paper
held again stays held, a draft is left alone, and a paper declared institutional
stays embargoed and is named. Finding nothing, it says whose papers are waiting,
because the default owner is only a guess at how a corpus was loaded.

Spends nothing. It queues no indexing, so what a corpus would cost stays a
separate choice: `backfill_embeddings --dry-run` says, and dropping `--dry-run`
pays for it.

Refuses with `DEBUG` off, and has no `--force`.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from apps.accounts.models import User
from apps.records.corpus_clearance import clear_for_ai, refuse_outside_development
from apps.records.management.commands.load_corpus import DEFAULT_OWNER_EMAIL
from apps.records.models import Record
from core.enums import PipelineStatus


def _who_holds(waiting) -> str:
    holders = waiting.values("added_by__email").annotate(papers=Count("pk")).order_by("-papers")
    if not holders:
        return "No submitted paper is waiting for a release."
    named = ", ".join(
        f"{row['added_by__email'] or 'no owner'} ({row['papers']})" for row in holders
    )
    return f"Papers waiting for a release belong to: {named}."


class Command(BaseCommand):
    help = "Release a loader's embargoed test papers for the AI (IR-815, IR-882). Development only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-email", default=DEFAULT_OWNER_EMAIL,
            help=f"Whose loaded papers to mark (default: {DEFAULT_OWNER_EMAIL}).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Report what would happen; write nothing.",
        )

    def handle(self, *args, **options):
        refuse_outside_development()

        waiting = Record.objects.filter(
            is_embargoed=True, embargoed_until__isnull=True, embargo_date_set_at__isnull=True,
        ).exclude(pipeline_status=PipelineStatus.DRAFT)

        email = options["owner_email"]
        owner = User.objects.filter(email=email).first()
        if owner is None:
            raise CommandError(f"no account has the email {email}. {_who_holds(waiting)}")

        theirs = waiting.filter(added_by=owner).order_by("pk")
        for record in theirs.filter(origin=Record.Origin.INSTITUTIONAL):
            self.stdout.write(
                self.style.WARNING(f"  left embargoed (declared institutional): {record.title[:70]}")
            )

        papers = list(theirs.exclude(origin=Record.Origin.INSTITUTIONAL))
        if not papers:
            self.stdout.write(_who_holds(waiting))
        if options["dry_run"]:
            self.stdout.write(f"Would mark {len(papers)} paper(s) owned by {email}.")
            return

        with transaction.atomic():
            for record in papers:
                clear_for_ai(record, actor=owner)

        self.stdout.write(self.style.SUCCESS(f"Marked {len(papers)} paper(s) owned by {email}."))
        self.stdout.write(
            "Nothing was sent. To see what embedding them would cost: "
            "python manage.py backfill_embeddings --dry-run"
        )
