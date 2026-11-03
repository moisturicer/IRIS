from celery import shared_task

from .embargo_reminders import run_embargo_reminders


@shared_task
def send_embargo_reminders():
    """ADR-052 §9: beat calls this daily; the database says what is owed."""
    return run_embargo_reminders()
