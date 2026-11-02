"""Celery entry points for recovery mail (ADR-045 §6).

Their only argument is an intent id; nothing secret crosses the broker, and
neither returns a value, so the result backend holds nothing either. Retries
are not Celery's: `delivery` schedules them on the intent itself, where the
dispatcher can see them if a message is lost.
"""

from celery import shared_task

from . import delivery


@shared_task(ignore_result=True)
def deliver_recovery_intent_task(intent_id: str) -> None:
    delivery.deliver_recovery_intent(intent_id)


@shared_task(ignore_result=True)
def dispatch_recovery_intents() -> None:
    delivery.dispatch_recovery_intents()
