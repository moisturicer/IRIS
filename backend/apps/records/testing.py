"""Shared helpers for tests that touch a Record."""

from django.utils import timezone

from apps.records.models import Record


def answered_no_embargo(record_id: int) -> None:
    """
    Give a draft the answer Publish saves first (ADR-052 decision 2), so a test
    about something else can submit it. The answer's own tests use the route.
    """
    Record.objects.filter(pk=record_id).update(embargo_answered_at=timezone.now())
