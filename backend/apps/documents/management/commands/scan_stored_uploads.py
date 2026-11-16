"""
Scan every file stored before uploads were scanned, once (IR-666, ADR-072 decision 4).

    python manage.py scan_stored_uploads --dry-run   # report, change nothing
    python manage.py scan_stored_uploads             # quarantine what fails

Run in the deployment that turns scanning on, before the new release serves,
so no file reaches a reader without having passed a scan. It is idempotent: a
clean file is scanned again harmlessly, and a quarantined one is gone.

**What it reads:** every file a person uploaded and IRIS keeps: slot uploads
(`RecordUpload`), office attachments (`RecordFile`), and Manuscripts
(`Record.abstract_file` and each `RecordVersion.manuscript`; deleted Records
included). Profile photos and Figure or formula crops are not: IRIS wrote
those bytes itself (a photo is re-encoded, a crop is cut from a stored PDF).

**What a failing file becomes:**

- its bytes move to `QUARANTINE_ROOT`, outside `MEDIA_ROOT`, so nothing can
  serve them, kept for inspection;
- every row naming it keeps its history but loses the file (the field is
  emptied), and each download path answers "no longer available". No row is
  deleted: a version's documents are `RESTRICT`ed and must stay listed;
- `FILE_QUARANTINED` is audited with the file's digest, size and signature;
- its uploader, where known, and RDCO are told in-app.

**Fail closed:** if the scanner can't answer, the run stops with nothing
changed for that file, and says so. It never treats an unscanned file as clean.
"""
from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.documents.scanning import ScanUnavailable, current_scanner


@dataclass(frozen=True)
class Ref:
    """One row naming a stored file: which model, which row, which field."""
    model: str
    pk: int
    field: str


def stored_files() -> dict[str, list[Ref]]:
    """Every stored upload's name, with every row that names it."""
    from apps.documents.models import RecordFile, RecordUpload
    from apps.records.models import Record, RecordVersion

    names: dict[str, list[Ref]] = defaultdict(list)
    sources = (
        (RecordUpload.objects.all(), "documents.RecordUpload", "file"),
        (RecordFile.objects.all(), "documents.RecordFile", "file"),
        # Deleted Records too: their files are still on disk.
        (Record._base_manager.all(), "records.Record", "abstract_file"),
        (RecordVersion.objects.all(), "records.RecordVersion", "manuscript"),
    )
    for queryset, model, field in sources:
        for pk, name in queryset.exclude(**{field: ""}).exclude(**{f"{field}__isnull": True}).values_list("pk", field):
            names[name].append(Ref(model, pk, field))
    return dict(names)


class Command(BaseCommand):
    help = "Scan every stored upload once and quarantine any that fails (ADR-072)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what fails; change nothing.")

    def handle(self, *args, dry_run=False, **options):
        scanner = current_scanner()
        if scanner is None:
            raise CommandError("Scanning is switched off (MALWARE_SCAN=off): nothing can be scanned.")

        files = stored_files()
        clean = missing = failed = 0
        for name, refs in sorted(files.items()):
            if not default_storage.exists(name):
                missing += 1
                continue
            try:
                with default_storage.open(name, "rb") as handle:
                    data = handle.read()
                verdict = scanner.scan(BytesIO(data))
            except ScanUnavailable as exc:
                raise CommandError(
                    f"The scanner did not answer at {name!r} ({exc}). Nothing more was scanned; "
                    "run it again once the scanner is up."
                ) from exc
            if verdict.clean:
                clean += 1
                continue
            failed += 1
            self.stdout.write(f"FAILS {name}: {verdict.signature} ({len(refs)} row(s))")
            if not dry_run:
                quarantine(name, refs, data, verdict.signature)

        verb = "would be quarantined" if dry_run else "quarantined"
        self.stdout.write(
            f"{len(files)} stored file(s): {clean} clean, {failed} {verb}, {missing} missing from storage."
        )


def quarantine(name: str, refs: list[Ref], data: bytes, signature: str) -> Path:
    """Move `name` out of use: its bytes to QUARANTINE_ROOT, its rows emptied, audited, told."""
    from django.apps import apps

    from apps.audit.models import AuditEvent
    from apps.audit.services import create_audit_event
    from apps.notifications.services import notify_file_quarantined

    root = Path(settings.QUARANTINE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    kept = root / f"{uuid.uuid4().hex}-{Path(name).name}"
    kept.write_bytes(data)

    told = set()
    with transaction.atomic():
        for ref in refs:
            Model = apps.get_model(ref.model)
            row = Model._base_manager.filter(pk=ref.pk).first()
            if row is None:
                continue
            record = row if ref.model == "records.Record" else getattr(row, "record", None)
            Model._base_manager.filter(pk=ref.pk).update(**{ref.field: None if _nullable(Model, ref.field) else ""})
            create_audit_event(AuditEvent.FILE_QUARANTINED, None, record=record, metadata={
                "model": ref.model, "pk": ref.pk, "field": ref.field,
                "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "signature": signature,
            })
            uploader = _uploader(row, ref.model, record)
            key = (getattr(record, "pk", None), getattr(uploader, "pk", None))
            if key not in told:
                told.add(key)
                what = "the manuscript" if ref.field in ("abstract_file", "manuscript") else \
                    f'the file "{getattr(row, "filename", "") or Path(name).name}"'
                transaction.on_commit(lambda r=record, u=uploader, w=what: notify_file_quarantined(
                    record=r, uploader=u, what=w))
        # The bytes leave storage only once every row has let go of them.
        transaction.on_commit(lambda: default_storage.delete(name))
    return kept


def _nullable(Model, field: str) -> bool:
    return Model._meta.get_field(field).null


def _uploader(row, model: str, record):
    if model in ("documents.RecordUpload", "documents.RecordFile"):
        return row.uploaded_by
    if model == "records.RecordVersion":
        return row.created_by
    owner = record.owners.filter(is_primary=True).select_related("user").first() if record is not None else None
    return getattr(owner, "user", None)
