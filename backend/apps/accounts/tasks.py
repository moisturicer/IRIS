from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .recovery.tasks import deliver_recovery_intent_task, dispatch_recovery_intents  # noqa: F401


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_email_task(self, subject: str, message: str, recipient_list: list):
    """
    Send an email asynchronously.
    Retries up to 3 times with a 30-second back-off on transient failures.
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def expire_unverified_registrations():
    """ADR-051 decision 24 (IR-705): beat calls this daily at 03:00 Manila."""
    from .unverified import expire_unverified_registrations as run

    return run()
