from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from core.utils import send_email_async
from .models import User, RoleRequest


def send_verification_email(user: User, request):
    """
    Build and send an email verification link.
    TODO: move send to a Celery task (apps.accounts.tasks.send_verification_email_task).
    """
    uid   = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link  = f"{settings.FRONTEND_URL}/activate/{uid}/{token}"

    send_email_async(
        subject="Verify your IRIS account",
        message=f"Hello {user.first_name},\n\nClick the link to verify your account:\n{link}",
        recipient_list=[user.email],
    )


def activate_user(uidb64: str, token: str) -> User | None:
    """Verify the activation token and mark the user as verified. Returns user or None."""
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError):
        return None

    if default_token_generator.check_token(user, token):
        user.is_verified = True
        user.save(update_fields=["is_verified"])
        return user
    return None


def approve_role_request(role_request: RoleRequest, reviewed_by: User):
    """Approve a role request and update the user's role."""
    role_request.user.role = role_request.requested_role
    role_request.user.save(update_fields=["role"])
    role_request.status      = "approved"
    role_request.reviewed_by = reviewed_by
    role_request.save(update_fields=["status", "reviewed_by"])
    # TODO: send approval notification to user
