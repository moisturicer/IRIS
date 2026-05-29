import random
import string
import zipfile
import os
from io import BytesIO


def generate_pin(length: int = 6) -> str:
    """Generate a random alphanumeric PIN for record access."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def build_zip(files: list) -> BytesIO:
    """
    Build an in-memory ZIP from a list of file field objects.
    Each item must have .name and a readable .file attribute.
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f.file.path, arcname=os.path.basename(f.file.name))
    buffer.seek(0)
    return buffer


def send_email_async(subject: str, message: str, recipient_list: list):
    """
    Dispatch an email via Celery so it never blocks the request/response cycle.

    Falls back to a direct synchronous send (fail_silently=True) if the Celery
    broker is unreachable, so email is never silently dropped in development.
    """
    try:
        from apps.accounts.tasks import send_email_task
        send_email_task.delay(
            subject=subject,
            message=message,
            recipient_list=recipient_list,
        )
    except Exception:
        # Broker unavailable — send synchronously as a last resort.
        from django.core.mail import send_mail
        from django.conf import settings
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                fail_silently=True,
            )
        except Exception:
            pass
