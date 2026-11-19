"""
Scan every file stored before uploads were scanned, once (IR-666, ADR-074 decision 4).

    python manage.py scan_stored_uploads --dry-run   # report, change nothing
    python manage.py scan_stored_uploads             # quarantine what fails

Run in the deployment that turns scanning on, right after it starts (the
command ships in that release), so files stored before scanning are checked as
soon as possible. Running it again is harmless: a clean file is scanned again,
and a quarantined one is no longer named by any row.

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
- what IRIS read from it goes too, so Ask IRIS can't cite it: a Record's
  current Manuscript is reset as if it had none (`reset_manuscript`: its
  extraction, Figures and formulas deleted, its chunks deactivated), and a
  slot upload's extraction is deleted;
- `FILE_QUARANTINED` is audited with the file's digest, size and signature;
- its uploader, where known, and RDCO are told in-app.

**Fail closed:** if the scanner can't answer, the run stops with nothing
changed for that file, and says so. It never treats an unscanned file as clean.
"""
from __future__ import annotations

import hashlib
import logging
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

logger = logging.getLogger(__name__)


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
    help = "Scan every stored upload once and quarantine any that fails (ADR-074)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what fails; change nothing.")

    def handle(self, *args, dry_run=False, **options):
        scanner = current_scanner()
        if scanner is None:
            raise CommandError("Scanning is switched off (MALWARE_SCAN=off): nothing can be scanned.")

        files = stored_files()
        clean = missing = failed = 0
        rdco_told: set = set()
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
                quarantine(name, refs, data, verdict.signature, rdco_told=rdco_told)

        verb = "would be quarantined" if dry_run else "quarantined"
        self.stdout.write(
            f"{len(files)} stored file(s): {clean} clean, {failed} {verb}, {missing} missing from storage."
        )


def quarantine(name: str, refs: list[Ref], data: bytes, signature: str, *, rdco_told: set) -> None:
    """
    Move `name` out of use: its rows emptied, what was read from it dropped,
    audited and told; once that commits, its bytes go to QUARANTINE_ROOT and
    leave storage. RDCO is told once per Record (`rdco_told` spans the run).
    """
    from django.apps import apps

    from apps.audit.models import AuditEvent
    from apps.audit.services import create_audit_event
    from apps.documents.models import PdfExtraction
    from apps.documents.sources import reset_manuscript
    from apps.notifications.services import notify_file_quarantined
    from apps.records.models import Record

    digest = hashlib.sha256(data).hexdigest()
    told = set()
    with transaction.atomic():
        for ref in refs:
            Model = apps.get_model(ref.model)
            row = Model._base_manager.filter(pk=ref.pk).first()
            if row is None:
                continue
            record = row if ref.model == "records.Record" else getattr(row, "record", None)
            Model._base_manager.filter(pk=ref.pk).update(**{ref.field: None if _nullable(Model, ref.field) else ""})
            if ref.model == "records.Record":
                # Under the Record lock, as every manuscript change is.
                locked = Record._base_manager.select_for_update().get(pk=ref.pk)
                reset_manuscript(locked)
            elif ref.model == "documents.RecordUpload":
                PdfExtraction.objects.filter(upload_id=ref.pk).delete()
            create_audit_event(AuditEvent.FILE_QUARANTINED, None, record=record, metadata={
                "model": ref.model, "pk": ref.pk, "field": ref.field,
                "sha256": digest, "size": len(data), "signature": signature,
            })
            uploader = _uploader(row, ref.model, record)
            key = (getattr(record, "pk", None), getattr(uploader, "pk", None))
            if key not in told:
                told.add(key)
                tell_rdco = key[0] not in rdco_told
                rdco_told.add(key[0])
                what = "the manuscript" if ref.field in ("abstract_file", "manuscript") else                     f'the file "{getattr(row, "filename", "") or Path(name).name}"'
                transaction.on_commit(lambda r=record, u=uploader, w=what, t=tell_rdco: notify_file_quarantined(
                    record=r, uploader=u, what=w, tell_rdco=t))
        # The bytes move only once every row has let go of them: kept first, then deleted.
        transaction.on_commit(lambda: _move_to_quarantine(name, data))


def _move_to_quarantine(name: str, data: bytes) -> None:
    root = Path(settings.QUARANTINE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    kept = root / f"{uuid.uuid4().hex}-{Path(name).name}"
    kept.write_bytes(data)
    try:
        default_storage.delete(name)
    except OSError:
        # No row names it any more, so nothing can serve it; say where it is.
        logger.error("Quarantined %s to %s but could not remove it from storage; remove it by hand.", name, kept)


def _nullable(Model, field: str) -> bool:
    return Model._meta.get_field(field).null


def _uploader(row, model: str, record):
    if model in ("documents.RecordUpload", "documents.RecordFile"):
        return row.uploaded_by
    if model == "records.RecordVersion":
        return row.created_by
    owner = record.owners.filter(is_primary=True).select_related("user").first() if record is not None else None
    return getattr(owner, "user", None)
