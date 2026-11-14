"""
RDCO's Setup: each record type's Requirements, Templates and description
(ADR-063 decisions 1-5 and 8-12, IR-971).

A Requirement is the existing `UploadSlot` of a record type (never an ad-hoc
one). Whatever RDCO sets here shows at once wherever slots show, because every
list reads `listed_slots`.

- The **label** (`is_required`) never blocks submitting (decision 3).
- The **Manuscript** is the paper itself, not a slot: a fixed first row whose
  description and Template live on `RecordType` (decision 4). It can't be
  removed or made Optional, so nothing here offers to.
- **Removing** a requirement some Record has used hides it and keeps the files;
  an unused one is deleted (decision 5). "Used" means a file was uploaded to it
  or a document request asked for it: deleting either would orphan that history.
- **Every change is audited** (decision 11). Descriptions are recorded as
  character counts, never their text.

The view gates every call on RDCO; this module assumes the caller passed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event
from core.enums import RequirementRemoval

from .models import UploadSlot
from .template_files import display_name, template_problem

MAX_DESCRIPTION_CHARS = 2000
MAX_NAME_CHARS = 200
MANUSCRIPT = "Manuscript"


class SetupError(Exception):
    """A change Setup refuses, with the reason shown to RDCO. 400."""


@dataclass(frozen=True)
class Removal:
    outcome: RequirementRemoval


# -- reading ------------------------------------------------------------------


def listed_slots(record_type_id) -> QuerySet:
    """A record type's Requirements in RDCO's order: not ad-hoc, not hidden."""
    return UploadSlot.objects.filter(
        record_type_id=record_type_id, record__isnull=True, hidden_at__isnull=True,
    ).order_by("position", "pk")


def slots_for_record(record) -> QuerySet:
    """
    The slots a paper shows: its type's listed ones, its own ad-hoc ones
    (ADR-022 §3), and any hidden one it has a file in (decision 5).
    """
    return UploadSlot.objects.filter(
        Q(record__isnull=True, hidden_at__isnull=True)
        | Q(record=record)
        | Q(record__isnull=True, hidden_at__isnull=False, uploads__record=record),
        record_type_id=record.record_type_id,
    ).distinct().order_by("position", "pk")


def requirement(pk) -> Optional[UploadSlot]:
    """A listed Requirement by id, or None: ad-hoc and hidden slots are not Setup's."""
    try:
        return UploadSlot.objects.select_related("record_type").get(
            pk=pk, record__isnull=True, hidden_at__isnull=True,
        )
    except (UploadSlot.DoesNotExist, ValueError, TypeError):
        return None


# -- validation -----------------------------------------------------------------


def _name(value, record_type_id, *, exclude_pk=None) -> str:
    name = (value or "").strip() if isinstance(value, str) else ""
    if not name:
        raise SetupError("Give the requirement a name.")
    if len(name) > MAX_NAME_CHARS:
        raise SetupError(f"Keep the name to {MAX_NAME_CHARS} characters.")
    if name.casefold() == MANUSCRIPT.casefold():
        raise SetupError("The Manuscript is always the first requirement.")
    clash = listed_slots(record_type_id).filter(name__iexact=name)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        raise SetupError("This record type already has a requirement with that name.")
    return name


def _description(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SetupError("A description is plain text.")
    text = value.strip()
    if len(text) > MAX_DESCRIPTION_CHARS:
        raise SetupError(f"Keep the description to {MAX_DESCRIPTION_CHARS} characters.")
    return text


def _required(value) -> bool:
    if not isinstance(value, bool):
        raise SetupError("Say whether the requirement is Required or Optional.")
    return value


def _type_meta(record_type) -> dict:
    return {"record_type": record_type.pk, "record_type_name": record_type.name}


def _slot_meta(slot) -> dict:
    return {**_type_meta(slot.record_type), "slot": slot.pk, "name": slot.name}


def _lock_type(record_type):
    from apps.records.models import RecordType

    return RecordType.objects.select_for_update().get(pk=record_type.pk)


def _drop_file_after_commit(field_file) -> None:
    """
    Delete a replaced or removed Template's file once the change has committed,
    so the old file is never offered again (decision 8) and a rolled-back
    change keeps it. Reads the name now: saving a new file into the same field
    renames this object.
    """
    if not field_file:
        return
    storage, name = field_file.storage, field_file.name
    transaction.on_commit(lambda: storage.delete(name))


# -- Requirements ---------------------------------------------------------------


def add_requirement(record_type, user, *, name, is_required, description="") -> UploadSlot:
    with transaction.atomic():
        record_type = _lock_type(record_type)
        clean_name = _name(name, record_type.pk)
        last = listed_slots(record_type.pk).order_by("-position").values_list("position", flat=True).first()
        slot = UploadSlot.objects.create(
            record_type=record_type,
            name=clean_name,
            is_required=_required(is_required),
            description=_description(description),
            position=(last or 0) + 1,
        )
        create_audit_event(AuditEvent.REQUIREMENT_ADDED, user, metadata={
            **_slot_meta(slot), "is_required": slot.is_required,
            "description_characters": len(slot.description),
        })
    return slot


def edit_requirement(slot, user, changes: dict) -> UploadSlot:
    """Change a Requirement's name, label or description. Unknown fields are refused."""
    allowed = {"name", "is_required", "description"}
    unknown = set(changes) - allowed
    if unknown:
        raise SetupError(f"These can't be changed here: {', '.join(sorted(unknown))}.")
    with transaction.atomic():
        slot = UploadSlot.objects.select_for_update().select_related("record_type").get(pk=slot.pk)
        diff = {}
        if "name" in changes:
            name = _name(changes["name"], slot.record_type_id, exclude_pk=slot.pk)
            if name != slot.name:
                diff["name"] = [slot.name, name]
                slot.name = name
        if "is_required" in changes:
            required = _required(changes["is_required"])
            if required != slot.is_required:
                diff["is_required"] = [slot.is_required, required]
                slot.is_required = required
        if "description" in changes:
            description = _description(changes["description"])
            if description != slot.description:
                diff["description_characters"] = [len(slot.description), len(description)]
                slot.description = description
        if diff:
            slot.save(update_fields=["name", "is_required", "description"])
            create_audit_event(AuditEvent.REQUIREMENT_CHANGED, user, metadata={
                **_slot_meta(slot), "changes": diff,
            })
    return slot


def reorder_requirements(record_type, user, order: Iterable) -> list[int]:
    """Put the record type's Requirements in `order`, which must name each one exactly once."""
    try:
        ids = [int(pk) for pk in order]
    except (TypeError, ValueError):
        raise SetupError("Give the requirements' ids in their new order.")
    with transaction.atomic():
        record_type = _lock_type(record_type)
        current = list(listed_slots(record_type.pk).values_list("pk", flat=True))
        if len(ids) != len(set(ids)) or set(ids) != set(current):
            raise SetupError("The order must list every requirement of this record type once.")
        for position, pk in enumerate(ids, start=1):
            UploadSlot.objects.filter(pk=pk).update(position=position)
        if ids != current:
            create_audit_event(AuditEvent.REQUIREMENTS_REORDERED, user, metadata={
                **_type_meta(record_type), "order": ids,
            })
    return ids


def remove_requirement(slot, user) -> Removal:
    with transaction.atomic():
        slot = UploadSlot.objects.select_for_update().select_related("record_type").get(pk=slot.pk)
        meta = _slot_meta(slot)
        used = slot.uploads.exists() or slot.request_items.exists()
        if used:
            slot.hidden_at = timezone.now()
            slot.save(update_fields=["hidden_at"])
            outcome = RequirementRemoval.HIDDEN
        else:
            _drop_file_after_commit(slot.template)
            slot.delete()
            outcome = RequirementRemoval.DELETED
        create_audit_event(AuditEvent.REQUIREMENT_REMOVED, user, metadata={**meta, "outcome": outcome.value})
    return Removal(outcome)


# -- Templates ------------------------------------------------------------------


def _replace(instance, file_field: str, name_field: str, file, user, meta: dict) -> None:
    problem = template_problem(file)
    if problem:
        raise SetupError(problem)
    replaced = bool(getattr(instance, file_field))
    if replaced:
        _drop_file_after_commit(getattr(instance, file_field))
    name = display_name(file.name)
    getattr(instance, file_field).save(name, file, save=False)
    setattr(instance, name_field, name)
    instance.save(update_fields=[file_field, name_field])
    create_audit_event(AuditEvent.TEMPLATE_REPLACED, user, metadata={
        **meta, "filename": name, "bytes": file.size, "replaced": replaced,
    })


def _remove(instance, file_field: str, name_field: str, user, meta: dict) -> bool:
    current = getattr(instance, file_field)
    if not current:
        return False
    _drop_file_after_commit(current)
    filename = getattr(instance, name_field)
    setattr(instance, file_field, "")
    setattr(instance, name_field, "")
    instance.save(update_fields=[file_field, name_field])
    create_audit_event(AuditEvent.TEMPLATE_REMOVED, user, metadata={**meta, "filename": filename})
    return True


def set_requirement_template(slot, user, file) -> UploadSlot:
    with transaction.atomic():
        slot = UploadSlot.objects.select_for_update().select_related("record_type").get(pk=slot.pk)
        _replace(slot, "template", "template_name", file, user,
                 {**_slot_meta(slot), "target": "requirement"})
    return slot


def remove_requirement_template(slot, user) -> bool:
    with transaction.atomic():
        slot = UploadSlot.objects.select_for_update().select_related("record_type").get(pk=slot.pk)
        return _remove(slot, "template", "template_name", user,
                       {**_slot_meta(slot), "target": "requirement"})


def set_manuscript_template(record_type, user, file):
    with transaction.atomic():
        record_type = _lock_type(record_type)
        _replace(record_type, "manuscript_template", "manuscript_template_name", file, user,
                 {**_type_meta(record_type), "target": "manuscript"})
    return record_type


def remove_manuscript_template(record_type, user) -> bool:
    with transaction.atomic():
        record_type = _lock_type(record_type)
        return _remove(record_type, "manuscript_template", "manuscript_template_name", user,
                       {**_type_meta(record_type), "target": "manuscript"})


# -- the record type's own text ---------------------------------------------------


def describe_record_type(record_type, user, changes: dict):
    """Change a record type's description or its Manuscript's description."""
    allowed = {"description", "manuscript_description"}
    unknown = set(changes) - allowed
    if unknown:
        raise SetupError(f"These can't be changed here: {', '.join(sorted(unknown))}.")
    with transaction.atomic():
        record_type = _lock_type(record_type)
        diff = {}
        for field in allowed & set(changes):
            text = _description(changes[field])
            before = getattr(record_type, field)
            if text != before:
                diff[f"{field}_characters"] = [len(before), len(text)]
                setattr(record_type, field, text)
        if diff:
            record_type.save(update_fields=list(allowed))
            create_audit_event(AuditEvent.RECORD_TYPE_DESCRIBED, user, metadata={
                **_type_meta(record_type), "changes": diff,
            })
    return record_type
