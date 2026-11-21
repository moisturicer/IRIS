"""
My Templates: the proposal Templates an Adviser shares (ADR-063 decision 8, IR-975).

- Each has a **title**, a short plain-text **description** (links are made
  clickable by the screen, decision 10) and a **file**, under Setup's file
  rules and the malware scan. Only the newest file is ever offered.
- The list is the **Adviser's own**, in the Adviser's order. Only the owner
  changes or removes one: every change looks the Template up among the
  caller's own, so RDCO, or another Adviser, finds nothing (a 404).
- **Shown** to everyone signed in only while the owner is an Adviser whose
  profile is open (`shown_templates`): a suspended or locked account, or one
  that no longer holds the Adviser role, shows none, everywhere, and its rows
  are kept, so lifting the suspension shows them again. A **deleted** account's
  Templates and files are removed with it (`remove_all_of_deleted_account`).
- **Every change is audited** (decision 11); descriptions as character
  counts, never their text. Downloads are not.

The view gates every change on the Adviser role; this module assumes it.
"""

from __future__ import annotations

from typing import Iterable, Optional

from django.db import transaction
from django.db.models import QuerySet

from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event
from core.enums import RoleName

from . import template_rules as rules
from .models import AdviserTemplate
from .template_files import display_name, drop_file_after_commit


class TemplateError(Exception):
    """A change My Templates refuses, with the reason shown to the Adviser. 400."""


class TemplateGone(Exception):
    """The Template was removed meanwhile (another tab). 404, as if never found."""


# -- reading ------------------------------------------------------------------


def my_templates(user) -> QuerySet:
    """The Adviser's own Templates, in their order."""
    return AdviserTemplate.objects.filter(owner=user).order_by("position", "pk")


def own_template(user, pk) -> Optional[AdviserTemplate]:
    """One of the caller's own Templates, or None: anyone else's is not theirs to change."""
    try:
        return my_templates(user).get(pk=pk)
    except (AdviserTemplate.DoesNotExist, ValueError, TypeError):
        return None


def shown_templates() -> QuerySet:
    """
    The Templates anyone signed in may see: their owner is an Adviser with an
    open profile (`open_profiles`, the one predicate for who still shows).
    """
    from apps.accounts.public_profile import open_profiles

    advisers = open_profiles().filter(role__name=RoleName.ADVISER)
    return (
        AdviserTemplate.objects.filter(owner__in=advisers)
        .select_related("owner")
        .order_by("owner__last_name", "owner__first_name", "owner_id", "position", "pk")
    )


# -- validation -----------------------------------------------------------------


def _title(value) -> str:
    return rules.name(value, what="title", missing="Give the Template a title.", error=TemplateError)


def _description(value) -> str:
    return rules.description(value, error=TemplateError)


def _check_file(file, user) -> None:
    rules.check_file(file, user, where="my_template", error=TemplateError)


def _meta(template) -> dict:
    return {"template": template.pk, "title": template.title}


def _lock_owner_row(user) -> None:
    """Take a row lock on the Adviser, so one Adviser's changes to their list's positions run one at a time."""
    from apps.accounts.models import User

    list(User.objects.select_for_update().filter(pk=user.pk).values_list("pk", flat=True))


def _locked(template) -> AdviserTemplate:
    try:
        return AdviserTemplate.objects.select_for_update().get(pk=template.pk)
    except AdviserTemplate.DoesNotExist:
        raise TemplateGone


# -- changes ----------------------------------------------------------------------


def add_template(user, *, title, description="", file=None) -> AdviserTemplate:
    clean_title, clean_description = _title(title), _description(description)
    _check_file(file, user)
    with transaction.atomic():
        _lock_owner_row(user)
        last = my_templates(user).order_by("-position").values_list("position", flat=True).first()
        name = display_name(file.name)
        template = AdviserTemplate(
            owner=user, title=clean_title, description=clean_description,
            file_name=name, position=(last or 0) + 1,
        )
        template.file.save(name, file, save=False)
        template.save()
        create_audit_event(AuditEvent.ADVISER_TEMPLATE_ADDED, user, metadata={
            **_meta(template), "description_characters": len(template.description),
            "filename": name, "bytes": file.size,
        })
    return template


def edit_template(template, user, changes: dict, file=None) -> AdviserTemplate:
    """Change a Template's title or description, and/or replace its file."""
    rules.only_fields(changes, {"title", "description"}, error=TemplateError)
    title = _title(changes["title"]) if "title" in changes else None
    description = _description(changes["description"]) if "description" in changes else None
    if file is not None:
        _check_file(file, user)
    with transaction.atomic():
        template = _locked(template)
        diff = {}
        if title is not None and title != template.title:
            diff["title"] = [template.title, title]
            template.title = title
        if description is not None and description != template.description:
            diff["description_characters"] = [len(template.description), len(description)]
            template.description = description
        if file is not None:
            drop_file_after_commit(template.file)
            name = display_name(file.name)
            diff["file"] = [template.file_name, name]
            diff["bytes"] = file.size
            template.file.save(name, file, save=False)
            template.file_name = name
        if diff:
            template.save()
            create_audit_event(AuditEvent.ADVISER_TEMPLATE_CHANGED, user, metadata={
                **_meta(template), "changes": diff,
            })
    return template


def reorder_templates(user, order: Iterable) -> list[int]:
    """Put the Adviser's Templates in `order`, which must name each of theirs exactly once."""
    ids = rules.order_ids(order, error=TemplateError, ask="Give your Templates' ids in their new order.")
    with transaction.atomic():
        _lock_owner_row(user)
        current = list(my_templates(user).values_list("pk", flat=True))
        rules.check_complete_order(ids, current, error=TemplateError,
                                   mismatch="The order must list each of your Templates once.")
        for position, pk in enumerate(ids, start=1):
            AdviserTemplate.objects.filter(pk=pk).update(position=position)
        if ids != current:
            create_audit_event(AuditEvent.ADVISER_TEMPLATES_REORDERED, user, metadata={"order": ids})
    return ids


def remove_all_of_deleted_account(person) -> int:
    """
    A deleted account's Templates, and their files once the deletion commits
    (IR-975): a deleted Adviser can never show again, so nothing is kept.
    Account deletion's own audit event records the act. Returns how many went.
    """
    gone = list(AdviserTemplate.objects.filter(owner=person))
    for template in gone:
        drop_file_after_commit(template.file)
    AdviserTemplate.objects.filter(pk__in=[t.pk for t in gone]).delete()
    return len(gone)


def remove_template(template, user) -> None:
    """Delete the Template and, once that commits, its file. No paper points at one."""
    with transaction.atomic():
        template = _locked(template)
        meta = {**_meta(template), "filename": template.file_name}
        drop_file_after_commit(template.file)
        template.delete()
        create_audit_event(AuditEvent.ADVISER_TEMPLATE_REMOVED, user, metadata=meta)
