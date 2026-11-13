"""Remove evaluation trial chunk sets and their vectors (IR-1051).

    python manage.py cleanup_trial_chunk_sets --dry-run
    python manage.py cleanup_trial_chunk_sets --variant trail_off
    python manage.py cleanup_trial_chunk_sets --all

Touches only rows with `trial_variant` set; a live or superseded chunk set is
never matched.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai.trials import delete_trial_sets, trial_variants


class Command(BaseCommand):
    help = "Delete trial chunk sets made by eval_retrieval --variant."

    def add_arguments(self, parser):
        parser.add_argument("--variant", help="Delete only this variant.")
        parser.add_argument("--all", action="store_true", help="Delete every variant.")
        parser.add_argument("--dry-run", action="store_true",
                            help="List what would be deleted and stop.")

    def handle(self, *args, **options):
        stored = trial_variants()
        if options["dry_run"] or not (options["variant"] or options["all"]):
            if not stored:
                self.stdout.write("No trial chunk sets are stored.")
            for name, count in stored.items():
                self.stdout.write(f"{name}: {count} record(s)")
            if not options["dry_run"]:
                raise CommandError("Name one with --variant, or pass --all.")
            if not (options["variant"] or options["all"]):
                return
        if options["variant"] and options["variant"] not in stored:
            raise CommandError(f"No trial variant named {options['variant']!r}.")
        counts = delete_trial_sets(options["variant"], dry_run=options["dry_run"])
        verb = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(
            f"{verb} {counts['sets']} trial set(s), {counts['chunks']} chunk(s), "
            f"{counts['vectors']} vector(s)."
        )
