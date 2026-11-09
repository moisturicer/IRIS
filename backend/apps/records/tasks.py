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
    from apps.reviews.tasks import place_review_threads

    from .models import ReviewText
    from .review_text.store import read_text

    state = read_text(text_id)
    # A new reading may complete a pair, so a thread can now be found in it
    # (ADR-032 §7, IR-876).
    record_id = ReviewText.objects.filter(pk=text_id).values_list("record_id", flat=True).first()
    if record_id is not None:
        place_review_threads.delay(record_id)
    return state
