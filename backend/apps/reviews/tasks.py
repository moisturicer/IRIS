from celery import shared_task

from .reminders import run_deadline_notifications


@shared_task
def send_deadline_notifications():
    """ADR-043 §8: beat calls this hourly; the database says what is owed."""
    return run_deadline_notifications()
