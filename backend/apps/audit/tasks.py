from celery import shared_task

from .retention import run_retention


@shared_task
def erase_expired_personal_data():
    """ADR-051 decision 19: beat calls this daily; each type's setting says how old is too old."""
    return run_retention()
