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
    record.is_deleted  = True
    record.deleted_at  = timezone.now()
    record.deleted_by  = deleted_by
    record.pipeline_status = "pending_delete"
    record.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "pipeline_status", "updated_at"])


def parse_excel_import(file) -> list[dict]:
    """
    Parse a .xls/.xlsx file and return a list of record dicts.
    TODO: implement using pyexcel -- match column headers to Record fields.
    Imported records default to pipeline_status='draft' and record_type='Project'.
    """
    raise NotImplementedError("TODO: implement Excel import parser")
