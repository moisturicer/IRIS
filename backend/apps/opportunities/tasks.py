from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.notifications import services as notify
from .models import Opportunity


@shared_task
def remove_lapsed_requests():
    """
    Delete every pending or rejected Call whose paper deadline has passed,
    telling its Adviser once (ADR-050 decision 9, as amended 2026-11-15;
    IR-762). Daily, just after midnight in Manila.

    Each Call is deleted under its own row lock and its notice is queued on
    that same commit, so a Call deleted is told exactly once: a second run, or
    one racing this, finds the row gone and sends nothing. `skip_locked` lets a
    run step past a Call another transaction is editing; the next run gets it.
    Returns how many it deleted.
    """
    today = timezone.localdate()
    removed = 0
    for call_id in Opportunity.objects.lapsed(today).values_list("pk", flat=True):
        with transaction.atomic():
            # Rechecked under the lock: an edit may have saved it since the list.
            call = (
                Opportunity.objects.lapsed(today)
                .select_for_update(skip_locked=True, of=("self",))
                .filter(pk=call_id)
                .select_related("posted_by")
                .first()
            )
            if call is None:
                continue
            call.delete()
            transaction.on_commit(lambda call=call: notify.notify_call_lapsed(call))
            removed += 1
    return removed
