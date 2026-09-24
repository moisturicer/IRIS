"""Bulk-load a corpus of PDFs from a directory (IR-313).

    python manage.py load_corpus <dir> --dry-run
    python manage.py load_corpus <dir>

``<dir>`` is laid out one folder per category:

    <dir>/<category>/<paper>.pdf
    <dir>/<category>/<another paper>.pdf

Each category folder becomes a ``Classification``, created if absent. Each
PDF becomes one ``Record``, titled from its filename, with the PDF attached
as ``abstract_file`` -- the manuscript field a citation opens (see
``RecordViewSet.manuscript``).

**The catch this exists to handle.** Setting ``abstract_file`` through the
web API queues manuscript extraction from a hook on ``RecordViewSet``
(``_queue_manuscript_extraction_if_present``), not a model signal. A
management command writing through the ORM gets none of it, so this command
creates the ``PdfExtraction`` row and queues ``extract_manuscript_text``
itself, exactly as the viewset does.

The status a bulk-loaded record lands in reuses ``lifecycle.LEGACY_IMPORT_STATUS``
-- the same declared bypass ``RecordViewSet.import_excel`` uses for a legacy
spreadsheet import -- rather than inventing a second one. It is publicly
visible by default, so Ask IRIS retrieval can find what gets loaded.

Idempotent by title within a category: a PDF whose filename (minus
extension) already names a Record under that Classification is skipped, not
re-created. A non-PDF file in a category folder is skipped with a message,
not a failure.

Needs Docling and a worker on the ``extraction`` queue to actually complete;
chunking is queued automatically after
(``documents.tasks._queue_chunking_if_manuscript``). No vendor account
needed -- chunking does not embed.

Refuses to run with ``DEBUG`` off unless ``--force``, matching ``seed_demo``.
"""

from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.documents.models import DocumentKind, PdfExtraction
from apps.documents.tasks import extract_manuscript_text
from apps.records import lifecycle
from apps.records.models import Classification, Record, RecordOwner, RecordType
from core.enums import RecordTypeName

#: A dedicated, unusable-password account -- deliberately not `seed_demo`'s
#: admin account, so this command works on a database that never ran
#: `seed_demo` and does not quietly attribute an arbitrary corpus to
#: whichever human happens to hold that email today.
DEFAULT_OWNER_EMAIL = "corpus-loader@cit.edu"


class Command(BaseCommand):
    help = "Bulk-load a corpus of PDFs from a directory, one folder per category (IR-313)."

    def add_arguments(self, parser):
        parser.add_argument("directory", help="Root directory, one subfolder per category.")
        parser.add_argument(
            "--record-type", default=RecordTypeName.THESIS_RESEARCH,
            help=f"RecordType name for every loaded Record (default: {RecordTypeName.THESIS_RESEARCH}).",
        )
        parser.add_argument(
            "--status", default=lifecycle.LEGACY_IMPORT_STATUS,
            help=f"pipeline_status for every loaded Record (default: {lifecycle.LEGACY_IMPORT_STATUS} -- "
                 "publicly visible, so Ask IRIS retrieval can find it).",
        )
        parser.add_argument(
            "--owner-email", default=DEFAULT_OWNER_EMAIL,
            help=f"Email recorded as added_by and primary owner (default: {DEFAULT_OWNER_EMAIL}). "
                 "Created, with an unusable password, if it does not already exist.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Report what would happen; write nothing.",
        )
        parser.add_argument(
            "--force", action="store_true", help="Load even when DEBUG is off.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "refusing to load a corpus with DEBUG off -- this writes Records "
                "and queues extraction against whatever database is configured. "
                "Pass --force if you are certain this is not production."
            )

        root = Path(options["directory"])
        if not root.is_dir():
            raise CommandError(f"{root} is not a directory.")

        self.dry_run = options["dry_run"]
        self.status = options["status"]

        categories = sorted(p for p in root.iterdir() if p.is_dir())
        if not categories:
            self.stdout.write(self.style.WARNING(f"No category subfolders found under {root}."))
            return

        owner = None if self.dry_run else self._resolve_owner(options["owner_email"])
        record_type = (
            None if self.dry_run
            else RecordType.objects.get_or_create(name=options["record_type"])[0]
        )

        created = skipped_existing = skipped_non_pdf = queued = 0
        for category_dir in categories:
            classification = self._classification_for(category_dir.name)
            for path in sorted(category_dir.iterdir()):
                if not path.is_file():
                    continue
                if path.suffix.lower() != ".pdf":
                    self.stdout.write(f"  skip (not a PDF): {path.relative_to(root)}")
                    skipped_non_pdf += 1
                    continue

                title = path.stem
                if Record.objects.filter(title=title, classification=classification).exists():
                    self.stdout.write(f"  = [{category_dir.name}] {title[:70]} (already exists)")
                    skipped_existing += 1
                    continue

                if self.dry_run:
                    self.stdout.write(f"  + [{category_dir.name}] {title[:70]} (would create, would queue)")
                    created += 1
                    queued += 1
                    continue

                record = self._load_one(path, title, classification, record_type, owner)
                self.stdout.write(
                    f"  + [{category_dir.name}] {title[:70]} -> record {record.id}, extraction queued"
                )
                created += 1
                queued += 1

        self.stdout.write("")
        verb = "Would create" if self.dry_run else "Created"
        queued_verb = "would be queued" if self.dry_run else "queued"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {created} record(s); {skipped_existing} already existed; "
            f"{skipped_non_pdf} non-PDF file(s) skipped; {queued} extraction(s) {queued_verb}."
        ))

    def _classification_for(self, name: str):
        # A read-only lookup in dry-run, not `None`: the idempotency check
        # right after this compares against it, and a dry-run against a
        # corpus already loaded must see the real Classification or every
        # existing record reads as new.
        if self.dry_run:
            return Classification.objects.filter(name=name).first()
        return Classification.objects.get_or_create(name=name)[0]

    def _resolve_owner(self, email: str) -> User:
        # Keyed on `created`: a blank password reads as "usable" to Django,
        # and an existing account's real password must never be touched.
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"first_name": "Corpus", "last_name": "Loader", "is_verified": True},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user

    def _load_one(self, path: Path, title: str, classification, record_type, owner: User) -> Record:
        # One transaction: a record left with no extraction queued would
        # dodge every re-run's idempotency check forever (it keys on the
        # Record existing, not on extraction having been queued).
        with transaction.atomic():
            record = Record.objects.create(
                title=title,
                record_type=record_type,
                classification=classification,
                added_by=owner,
                pipeline_status=self.status,
            )
            with path.open("rb") as fh:
                record.abstract_file.save(path.name, File(fh), save=True)
            RecordOwner.objects.create(record=record, user=owner, is_primary=True)

            PdfExtraction.objects.update_or_create(
                record=record,
                defaults={"status": "queued", "error": "", "kind": DocumentKind.MANUSCRIPT},
            )
            transaction.on_commit(lambda record_id=record.id: extract_manuscript_text.delay(record_id))

        return record
