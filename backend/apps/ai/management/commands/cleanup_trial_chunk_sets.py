"""Remove evaluation trial chunk sets and their vectors (IR-1051).

    python manage.py cleanup_trial_chunk_sets --dry-run --all
    python manage.py cleanup_trial_chunk_sets --variant trail_off
    python manage.py cleanup_trial_chunk_sets --all

Touches only rows with `trial_variant` set; a live or superseded set never matches.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai.trials import delete_trial_sets, trial_variants


class Command(BaseCommand):
    help = "Delete trial chunk sets made by eval_retrieval --variant."

    def add_arguments(self, parser):
        which = parser.add_mutually_exclusive_group(required=True)
        which.add_argument("--variant", help="Delete only this variant.")
        which.add_argument("--all", action="store_true", help="Delete every variant.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Say what would be deleted and stop.")

    def handle(self, *args, **options):
        stored = trial_variants()
        variant = options["variant"]
        if variant is not None and variant not in stored:
            known = ", ".join(stored) or "none"
            raise CommandError(f"No trial variant named {variant!r} (stored: {known}).")
        counts = delete_trial_sets(variant, dry_run=options["dry_run"])
        verb = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(
            f"{verb} {counts['sets']} trial set(s), {counts['chunks']} chunk(s), "
            f"{counts['vectors']} vector(s)."
        )
