"""
A paper's views: one per account (IR-369, CONTEXT.md **View**).

Paper View posts `increment_access` on every load, so this decides on the
server whether an opening is a view. Reloads, React StrictMode's double call
and several tabs therefore all behave the same.

- A view is an account's first opening of a published paper. The paper's
  owners never count; its adviser, reviewers and office staff do.
- `Record.access_count` rises in the database, never as "read, add one,
  write", so two accounts opening at once both count. The unique constraint on
  `RecordView` is what makes the same account opening twice at once count once.
- The `ACCESS` audit event is written for every opening, counted or not, but
  at most once per account per paper per rolling 24 hours.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.models import Count, F, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event
from core.enums import PipelineStatus

from .models import Record, RecordView

#: How long one `ACCESS` audit event covers an account's openings of a paper.
AUDIT_WINDOW = timedelta(hours=24)

#: How far back Trending counts a paper's views (CONTEXT.md **Trending**).
TRENDING_WINDOW = timedelta(days=30)


def counts_as_view(record: Record, user) -> bool:
    if record.pipeline_status != PipelineStatus.PUBLISHED:
        return False
    return not record.owners.filter(user=user).exists()


def record_opening(record: Record, user) -> int:
    """Count `user`'s opening of `record` if it is a view; return the paper's views."""
    with transaction.atomic():
        _one_opening_at_a_time(record, user)
        now = timezone.now()
        if counts_as_view(record, user):
            try:
                with transaction.atomic():
                    RecordView.objects.create(record=record, user=user, viewed_at=now)
            except IntegrityError:
                pass  # Already a view: this account was counted before.
            else:
                Record.objects.filter(pk=record.pk).update(access_count=F("access_count") + 1)
        _audit(record, user, now)
    return Record.objects.filter(pk=record.pk).values_list("access_count", flat=True).get()


def _one_opening_at_a_time(record: Record, user) -> None:
    """Hold this account's openings of this paper in line until commit.

    Without it, two tabs opening at once both find no `ACCESS` event in the
    last day and both write one. Other accounts and other papers don't wait.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 369))",
            [f"record-view:{record.pk}:{user.pk}"],
        )


def _audit(record: Record, user, now) -> None:
    recent = AuditEvent.objects.filter(
        event_type=AuditEvent.ACCESS, user=user, record=record,
        created_at__gt=now - AUDIT_WINDOW,
    )
    if not recent.exists():
        create_audit_event(AuditEvent.ACCESS, user, record=record)


def with_recent_views(queryset):
    """`queryset` annotated with `recent_views`: views gained in the Trending window.

    A subquery rather than a join, so it can't multiply the rows other
    annotations (the list's `file_count`) count over.
    """
    since = timezone.now() - TRENDING_WINDOW
    recent = (
        RecordView.objects.filter(record=OuterRef("pk"), viewed_at__gte=since)
        .order_by().values("record").annotate(n=Count("pk")).values("n")
    )
    return queryset.annotate(
        recent_views=Coalesce(Subquery(recent, output_field=IntegerField()), Value(0)),
    )
