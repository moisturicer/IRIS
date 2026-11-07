from celery import shared_task

from .embargo_reminders import run_embargo_reminders


@shared_task
def send_embargo_reminders():
    """ADR-052 §9: beat calls this daily; the database says what is owed."""
    return run_embargo_reminders()


@shared_task
def read_review_text(text_id):
    """ADR-058 §1 as amended (IR-871): read one Version's review text, on
    campus, in the IR-830 sandbox. On `default`: it calls nothing outside."""
    from .review_text.store import read_text

    return read_text(text_id)
