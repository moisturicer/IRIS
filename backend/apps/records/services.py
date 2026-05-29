from django.db.models import Value
from django.contrib.postgres.search import SearchVector
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
    """Mark a record as deleted without removing it from the DB."""
    from django.utils import timezone
    record.is_deleted       = True
    record.deleted_at       = timezone.now()
    record.deleted_by       = deleted_by
    record.pipeline_status  = "pending_delete"
    record.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "pipeline_status", "updated_at"])


def parse_excel_import(file) -> tuple[list[dict], list[str]]:
    """
    Parse a .xls or .xlsx spreadsheet and return (rows, errors).
    Uses pyexcel-xls / pyexcel-xlsx (see requirements/base.txt).

    Expected columns (header row 1 — case-insensitive):
      Title, Abstract, Year Accomplished, Year Completed,
      Record Type, Classification, PSCED Classification,
      Is IP, For Commercialization, Community Extension, Authors

    Rules:
    - Title is the only required column.
    - Processing stops when the first cell of a row equals "END OF RECORDS".
    - Completely blank rows are silently skipped.
    - Rows missing a Title are logged as errors and skipped.
    - Authors should be comma-separated (e.g. "Juan Dela Cruz, Maria Santos").
    - Boolean columns accept: TRUE / FALSE / YES / NO / 1 / 0 (case-insensitive).
    - Record Type defaults to "Project" when blank or unrecognised.
    - Year columns accept integers; non-integer values are stored as None.

    Returns
    -------
    rows   : list of dicts ready for bulk Record creation
    errors : human-readable strings describing skipped rows
    """
    import os

    file_name = getattr(file, "name", "upload.xlsx")
    ext = os.path.splitext(file_name)[1].lower()
    file_type = "xls" if ext == ".xls" else "xlsx"

    try:
        import pyexcel
        all_rows = pyexcel.get_array(file_stream=file, file_type=file_type)
    except ImportError:
        return [], ["pyexcel is not installed. Check requirements/base.txt."]
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

    def parse_year(val: str | None) -> int | None:
        if val is None:
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

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

        title = get_col(row, "title")
        if not title:
            errors.append(f"Row {row_num}: skipped — Title is required.")
            continue

        authors_raw = get_col(row, "authors") or ""
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

        records.append({
            "title":                 title,
            "abstract":              get_col(row, "abstract") or "",
            "year_accomplished":     parse_year(get_col(row, "year accomplished")),
            "year_completed":        parse_year(get_col(row, "year completed")),
            "record_type_name":      get_col(row, "record type") or "Project",
            "classification_name":   get_col(row, "classification"),
            "psced_name":            get_col(row, "psced classification"),
            "is_ip":                 parse_bool(get_col(row, "is ip")),
            "for_commercialization": parse_bool(get_col(row, "for commercialization")),
            "community_extension":   parse_bool(get_col(row, "community extension")),
            "authors":               authors,
        })

    return records, errors
