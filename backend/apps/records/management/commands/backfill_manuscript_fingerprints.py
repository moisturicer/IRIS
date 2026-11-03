"""Bounded, restartable historical source fingerprint coverage."""
import hashlib

from django.core.management.base import BaseCommand, CommandError

from apps.records.models import Record


class Command(BaseCommand):
    help = "Inspect missing Manuscript SHA-256 fingerprints; pass --apply to save guarded results."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("--limit must be between 1 and 1000")
        records = Record.objects.filter(
            pk__gt=options["after_id"], abstract_file__isnull=False,
            manuscript_sha256="",
        ).exclude(abstract_file="").order_by("pk")[:limit]
        scanned = saved = failed = replaced = 0
        last_id = options["after_id"]
        for record in records:
            scanned += 1
            last_id = record.pk
            path = record.abstract_file.name
            revision = record.manuscript_revision
            try:
                digest = hashlib.sha256()
                with record.abstract_file.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
            except (OSError, IOError, ValueError) as exc:
                failed += 1
                self.stdout.write(f"record={record.pk} failed={type(exc).__name__}")
                continue
            if options["apply"]:
                changed = Record.objects.filter(
                    pk=record.pk, abstract_file=path,
                    manuscript_revision=revision, manuscript_sha256="",
                ).update(manuscript_sha256=digest.hexdigest())
                if changed:
                    saved += 1
                else:
                    replaced += 1
                    self.stdout.write(f"record={record.pk} replaced_during_hash")
        remaining = Record.objects.filter(abstract_file__isnull=False, manuscript_sha256="").exclude(abstract_file="").count()
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(f"mode={mode} scanned={scanned} saved={saved} failed={failed} replaced={replaced} remaining={remaining} next_after_id={last_id}")
        if failed:
            self.stdout.write("Retry failures separately; advancing --after-id skips them.")
