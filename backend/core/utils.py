import random
import string
import zipfile
import os
from io import BytesIO
from django.core.mail import send_mail
from django.conf import settings


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
    Simple wrapper around send_mail.
    TODO: replace with a Celery task (apps.accounts.tasks.send_email_task)
          so email sending never blocks a request.
    """
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False,
    )
