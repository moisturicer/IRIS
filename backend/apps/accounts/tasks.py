from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings


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


@shared_task(bind=True, max_retries=3)
def send_verification_email_task(self, user_id: int):
    """
    TODO: move send_verification_email() logic here so the registration
    endpoint never blocks on email delivery.
    """
    pass


@shared_task(bind=True, max_retries=3)
def send_role_request_email_task(self, user_id: int, role_name: str):
    """TODO: notify KTTO/RDCO by email when a new role request comes in."""
    pass
