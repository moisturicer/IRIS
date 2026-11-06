"""Shared helpers for tests that touch a Record."""

from django.utils import timezone

from apps.records.models import Record


def released_embargo(record_id: int) -> None:
    """
    Release a paper's embargo the way its Adviser or RDCO would (ADR-052 §6), so
    a test about something else sees the gate open. Every paper starts embargoed
    (IR-882); the release's own tests use the route.
    """
    Record.objects.filter(pk=record_id).update(
        is_embargoed=False, embargo_released_at=timezone.now(),
    )
