"""Renew current processing authority, including work whose wakeup was lost."""
import time
from django.core.management.base import BaseCommand, CommandError
from apps.publication.dispatch import reconcile


class Command(BaseCommand):
    help = "Reconcile committed Manuscript work (IR-737); calls no provider."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, required=True)
        parser.add_argument("--poll-seconds", type=float)

    def handle(self, *args, limit, poll_seconds=None, **options):
        if not 1 <= limit <= 1000 or (poll_seconds is not None and not 0 < poll_seconds <= 60):
            raise CommandError("limit must be 1..1000 and poll-seconds must be >0 and <=60")
        while True:
            self.stdout.write(f"published: {reconcile(limit=limit)}")
            if poll_seconds is None:
                return
            time.sleep(poll_seconds)
