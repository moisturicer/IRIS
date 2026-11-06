"""Give earlier Versions their review text (ADR-058 §1 as amended, point 4; IR-871).

    python manage.py read_review_texts --dry-run
    python manage.py read_review_texts
    python manage.py read_review_texts --record 42

A Version written before IR-871 has no review text. This reads each one from
its own manuscript file, the file its reviewers were served, as if it had been
read at submission. A metadata-only Version shares the previous Version's text,
and one whose file is gone reads "vN's text was not kept". It also retries any
text left `unavailable` because the sandbox couldn't run, or still `pending` an
hour after it was attached because its queued read was lost.

Reads on this machine, in the IR-830 sandbox, with no network call and no
model, so it spends nothing and asks no embargo or consent. It never re-reads a
text already stored. Idempotent: a second run finds nothing to do.

Needs every REVIEW_TEXT_* limit, and Linux; without them it refuses before
writing anything.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.records.review_text import sandbox, store


class Command(BaseCommand):
    help = "Read review text for Versions that have none (ADR-058 §1, IR-871). Spends nothing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Say what would be read, shared or marked not kept; write nothing.")
        parser.add_argument("--record", type=int, help="Only this Record's Versions.")

    def handle(self, *args, **options):
        plan = store.backfill_plan(options["record"])
        counts = {action: sum(1 for _, a, _ in plan if a == action)
                  for action in ("read", "share", "not_kept", "retry")}
        summary = (f"{counts['read']} to read from their own file, {counts['share']} sharing the "
                   f"previous Version's text, {counts['not_kept']} with no file (text not kept), "
                   f"{counts['retry']} to retry.")
        if options["dry_run"]:
            for version, action, _ in plan:
                self.stdout.write(f"record {version.record_id} v{version.number}: {action}")
            self.stdout.write(summary)
            return
        if counts["read"] or counts["retry"]:
            try:
                sandbox.limits()
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            import sys

            if sys.platform != "linux":
                raise CommandError("The review text sandbox needs Linux (RLIMIT_AS).")
        done = store.backfill(options["record"])
        self.stdout.write(self.style.SUCCESS(
            f"Read {done['read']}, shared {done['share']}, not kept {done['not_kept']}, "
            f"retried {done['retry']}."
        ))
