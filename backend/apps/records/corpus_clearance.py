"""
Clearing a test paper for the AI (ADR-052 decision 16, IR-815, amended IR-882).

Every paper starts embargoed, and a real one is released by its Adviser or RDCO.
A proxy paper has neither, so the test-data commands release it here, never with
`DEBUG` off and never for a paper declared institutional. A paper's origin defaults to
unknown, so these narrow what a command can reach and don't prove a paper isn't
real: that still rests on who runs them.

Both the release and consent are written because the gate needs both, and a
loaded paper has neither. When per-person consent lands (ADR-054, IR-791), the second one moves.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from .embargo import mark_released
from .models import Record


def refuse_outside_development() -> None:
    """Refuse with `DEBUG` off. There is no `--force`: see this module's docstring."""
    if not settings.DEBUG:
        raise CommandError(
            "refusing to clear papers for the AI with DEBUG off. This releases "
            "test papers' embargoes, and on a real database only a paper's "
            "Adviser or RDCO may do that."
        )


def clear_for_ai(record: Record, *, actor) -> None:
    """Release the embargo, and give consent unless someone already has."""
    if record.is_embargoed:
        mark_released(record, actor=actor)
    if record.dpa_accepted_at is None:
        record.dpa_accepted_at = timezone.now()
        record.dpa_accepted_by = actor
        record.save(update_fields=["dpa_accepted_at", "dpa_accepted_by", "updated_at"])
    # A read held for this release goes now (IR-850).
    from apps.documents.sources import read_awaiting

    transaction.on_commit(lambda: read_awaiting(record.pk), robust=True)
