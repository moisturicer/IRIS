"""
What a folder request may hold, and how a folder is shown (IR-572, ADR-070).

Kept apart from the views so the name rule and the listing shape are one
definition each, as `feeds.py` is for saved feeds.
"""

from django.db.models import Value
from django.db.models.functions import Lower
from rest_framework.exceptions import ValidationError

from .models import MAX_FOLDER_NAME, FolderMembership, LibraryFolder


def clean_name(raw) -> str:
    """The name as it will be stored: trimmed, present, at most 60 characters."""
    name = raw.strip() if isinstance(raw, str) else ""
    if not name:
        raise ValidationError({"name": ["Give the folder a name."]})
    if len(name) > MAX_FOLDER_NAME:
        raise ValidationError({"name": [f"Use {MAX_FOLDER_NAME} characters or fewer."]})
    return name


def folder_named(owner, name: str, *, excluding=None):
    """
    `owner`'s folder called `name`, ignoring case, or None.

    Compared with the database's own `LOWER()`, the function the unique rule
    `unique_library_folder_name` uses, so this check and that rule can never
    disagree about whether two names are the same.
    """
    found = LibraryFolder.objects.annotate(lowered=Lower("name")).filter(owner=owner, lowered=Lower(Value(name)))
    if excluding is not None:
        found = found.exclude(pk=excluding)
    return found.first()


def _record_ids(folder_ids) -> dict[int, list[int]]:
    """Each folder's Record ids, newest filing first. An id is one the reader
    filed themselves, so it is listed even once the Record is unreadable: the
    reader's save says `available: false`, and nothing more is disclosed."""
    by_folder: dict[int, list[int]] = {pk: [] for pk in folder_ids}
    rows = (
        FolderMembership.objects.filter(folder_id__in=folder_ids)
        .order_by("-added_at", "-pk")
        .values_list("folder_id", "saved_record__record_id")
    )
    for folder_id, record_id in rows:
        by_folder[folder_id].append(record_id)
    return by_folder


def _shape(folder, record_ids) -> dict:
    return {
        "id": folder.pk,
        "name": folder.name,
        "record_ids": record_ids,
        "created_at": folder.created_at,
        "updated_at": folder.updated_at,
    }


def entries(queryset) -> list[dict]:
    own = list(queryset)
    ids = _record_ids([folder.pk for folder in own])
    return [_shape(folder, ids[folder.pk]) for folder in own]


def entry(folder) -> dict:
    return _shape(folder, _record_ids([folder.pk])[folder.pk])


def duplicate_name() -> ValidationError:
    return ValidationError({"name": ["You already have a folder with that name."]})
