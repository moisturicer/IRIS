from celery import shared_task

from .reminders import run_deadline_notifications


@shared_task
def send_deadline_notifications():
    """ADR-043 §8: beat calls this hourly; the database says what is owed."""
    return run_deadline_notifications()


@shared_task
def place_review_threads(record_id):
    """ADR-032 §7 (IR-876): find each open anchored thread's passage in the
    Record's later Versions. Queued after a reading and after a submission;
    it does nothing until both readings of a pair exist, so running it early
    or twice is harmless."""
    from apps.records.models import Record

    from .thread_places import place_threads

    record = Record.objects.filter(pk=record_id).first()
    return place_threads(record) if record else 0
