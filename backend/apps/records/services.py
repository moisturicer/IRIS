import re
from datetime import date

import pyexcel
from django.contrib.postgres.search import SearchVector
from core.enums import RecordTypeName
from .models import Record, RecordOwner


def update_search_vector(record: Record):
    """
    Rebuild the PostgreSQL full-text search vector for one record.
    Called from a post_save signal after title/abstract changes.
    """
    Record.objects.filter(pk=record.pk).update(
        search_vector=(
            SearchVector("title", weight="A") +
            SearchVector("abstract", weight="B")
        )
    )


def set_primary_owner(record: Record, user):
    """Mark a user as the primary owner of a record, clearing any previous primary."""
    RecordOwner.objects.filter(record=record, is_primary=True).update(is_primary=False)
    RecordOwner.objects.update_or_create(
        record=record, user=user, defaults={"is_primary": True}
    )


def soft_delete_record(record: Record, deleted_by):
    """
    Mark a record as deleted without removing it from the DB.

    The status move is the table's (IR-136 stage 2); the deletion bookkeeping --
    the flag, who did it and when -- is not workflow data and stays here. Two
    writes rather than one, both inside `apply()`'s transaction.
    """
    from django.utils import timezone
    from . import lifecycle

    lifecycle.apply(record, lifecycle.WorkflowEvent.SOFT_DELETE, deleted_by)
    record.is_deleted = True
    record.deleted_at = timezone.now()
    record.deleted_by = deleted_by
    record.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])


def parse_excel_import(file) -> tuple[list[dict], list[str]]:
    """
    Parse a .xls or .xlsx spreadsheet and return (rows, errors).
    Uses pyexcel with its pyexcel-xls / pyexcel-xlsx plugins (see
    requirements/base.txt). pyexcel is imported at module level, not caught
    here: a missing dependency is a broken deployment, and reporting it as a
    skipped row is what hid it until IR-315.

    Expected columns (header row 1 — case-insensitive):
      Title, Abstract, Year Accomplished, Year Completed,
      Record Type, Classification, PSCED Classification,
      Is IP, For Commercialization, Community Extension, Authors

    Rules:
    - Processing stops when the first cell of a row equals "END OF RECORDS".
    - Completely blank rows are silently skipped.
    - Authors should be comma-separated (e.g. "Juan Dela Cruz, Maria Santos").
    - Boolean columns accept: TRUE / FALSE / YES / NO / 1 / 0 (case-insensitive).

    This only reads the sheet. Whether a row's values can be accepted --
    Title present, years, names -- is `check_import_row`'s (IR-638), which
    reports every problem in a row rather than the first.

    Returns
    -------
    rows   : one dict per data row, cells as text, with its sheet ``row_num``
    errors : human-readable strings for a file that could not be read
    """
    import os

    file_name = getattr(file, "name", "upload.xlsx")
    ext = os.path.splitext(file_name)[1].lower()
    file_type = "xls" if ext == ".xls" else "xlsx"

    try:
        all_rows = pyexcel.get_array(file_stream=file, file_type=file_type)
    except Exception as exc:
        return [], [f"Could not open file: {exc}. Make sure it is a valid .xls or .xlsx file."]

    rows_iter = iter(all_rows)

    # --- Read and index the header row --------------------------------------
    try:
        raw_headers = next(rows_iter)
    except StopIteration:
        return [], ["The file appears to be empty."]

    header_map: dict[str, int] = {
        str(h).strip().lower(): idx
        for idx, h in enumerate(raw_headers)
        if h is not None
    }

    # --- Helper closures ----------------------------------------------------
    def get_col(row: tuple, name: str) -> str | None:
        idx = header_map.get(name.lower())
        if idx is None or idx >= len(row):
            return None
        val = row[idx]
        return str(val).strip() if val is not None and str(val).strip() != "" else None

    def parse_bool(val: str | None) -> bool:
        return str(val).strip().upper() in ("TRUE", "YES", "1", "Y") if val else False

    # --- Parse data rows ----------------------------------------------------
    records: list[dict] = []
    errors:  list[str]  = []

    for row_num, row in enumerate(rows_iter, start=2):
        # Stop on END OF RECORDS sentinel
        first_cell = row[0] if row else None
        if first_cell and str(first_cell).strip().upper() == "END OF RECORDS":
            break

        # Skip blank rows
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        authors_raw = get_col(row, "authors") or ""
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

        records.append({
            "row_num":               row_num,
            "title":                 get_col(row, "title"),
            "abstract":              get_col(row, "abstract") or "",
            "year_accomplished":     get_col(row, "year accomplished"),
            "year_completed":        get_col(row, "year completed"),
            "record_type_name":      get_col(row, "record type"),
            "classification_name":   get_col(row, "classification"),
            "psced_name":            get_col(row, "psced classification"),
            "is_ip":                 parse_bool(get_col(row, "is ip")),
            "for_commercialization": parse_bool(get_col(row, "for commercialization")),
            "community_extension":   parse_bool(get_col(row, "community extension")),
            "authors":               authors,
        })

    return records, errors


#: The earliest year an imported record may carry (IR-638); the latest is next year.
EARLIEST_IMPORT_YEAR = 1900


class ImportChoices:
    """
    The names an import row may use, each looked up once per file, ignoring
    case (IR-638). Loaded at the start of an import, not per row.
    """

    def __init__(self):
        from .models import Classification, PSCEDClassification, RecordType

        self.record_types = {t.name.lower(): t for t in RecordType.objects.all()}
        self.classifications = {c.name.lower(): c for c in Classification.objects.all()}
        self.psced = {p.name.lower(): p for p in PSCEDClassification.objects.all()}


#: A year cell as a spreadsheet gives it: a whole number, or one written as a
#: float (``2021.0``). Not ``float()``, which would also read "2_024" or "2.024e3".
_YEAR_CELL = re.compile(r"\d+(\.0+)?")


def _accepted_names(names: dict) -> str:
    """The names a column accepts, for an error message."""
    return ", ".join(sorted((choice.name for choice in names.values()), key=str.lower)) or "(none)"


def check_import_row(row: dict, choices: ImportChoices) -> tuple[dict, list[str]]:
    """
    A parsed row's values as the Record will hold them, and every reason the
    row cannot be imported (IR-638).

    The import publishes with no review, so a value the system cannot accept
    skips the row and says why, under the same rule as a missing Title:
    - Title is required.
    - A year is blank, or a whole number from 1900 to next year, and Year
      Completed is not earlier than Year Accomplished.
    - Record Type, Classification and PSCED Classification must match an
      existing name, ignoring case. A blank Classification or PSCED stays
      blank; a blank Record Type is Project.

    Each problem names its column and the value given, and a name lists the
    accepted ones. The row is imported only when the list is empty.
    """
    problems: list[str] = []
    latest = date.today().year + 1

    if not row["title"]:
        problems.append("Title is required")

    def year(column: str, raw: str | None) -> int | None:
        if raw is None:
            return None
        value = int(float(raw)) if _YEAR_CELL.fullmatch(raw) else None
        if value is None or not EARLIEST_IMPORT_YEAR <= value <= latest:
            problems.append(f'{column} "{raw}" is not a year from {EARLIEST_IMPORT_YEAR} to {latest}')
            return None
        return value

    accomplished = year("Year Accomplished", row["year_accomplished"])
    completed = year("Year Completed", row["year_completed"])
    if accomplished is not None and completed is not None and completed < accomplished:
        problems.append(f'Year Completed "{completed}" is earlier than Year Accomplished "{accomplished}"')

    def look_up(column: str, raw: str | None, names: dict):
        if raw is None:
            return None
        found = names.get(raw.lower())
        if found is None:
            problems.append(f'{column} "{raw}" is not one of: {_accepted_names(names)}')
        return found

    if row["record_type_name"] is None:
        # Blank keeps the documented default, which a database may lack.
        record_type = choices.record_types.get(RecordTypeName.PROJECT.lower())
        if record_type is None:
            problems.append(f'Record Type is blank and its default "{RecordTypeName.PROJECT}" does not exist')
    else:
        record_type = look_up("Record Type", row["record_type_name"], choices.record_types)
    classification = look_up("Classification", row["classification_name"], choices.classifications)
    psced = look_up("PSCED Classification", row["psced_name"], choices.psced)

    return {
        "title":                 row["title"],
        "abstract":              row["abstract"],
        "year_accomplished":     accomplished,
        "year_completed":        completed,
        "record_type":           record_type,
        "classification":        classification,
        "psced":                 psced,
        "is_ip":                 row["is_ip"],
        "for_commercialization": row["for_commercialization"],
        "community_extension":   row["community_extension"],
    }, problems


def queue_manuscript_extraction(record: Record) -> None:
    """
    Send `record`'s manuscript to extraction, after commit, so the chunker
    reads the file the record now names (IR-195 / ADR-013's 2026-09-08
    amendment). Called by every write that changes `abstract_file` through the
    API, except an owner's revised manuscript, which is sent when its new
    version is submitted (IR-273).
    """
    from django.db import transaction

    from apps.documents.models import DocumentKind, PdfExtraction
    from apps.documents.tasks import extract_manuscript_text

    if not record.abstract_file:
        return
    # kind, explicitly: abstract_file *is* the manuscript, and IR-239 moved
    # that judgement onto the row so the chunker reads it there rather than
    # inferring it from which task was queued.
    PdfExtraction.objects.update_or_create(
        record=record,
        defaults={"status": "queued", "error": "", "kind": DocumentKind.MANUSCRIPT},
    )
    transaction.on_commit(lambda: extract_manuscript_text.delay(record.id))
