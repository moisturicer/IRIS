from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from core.utils import send_email_async
from .models import User, RoleRequest


def send_verification_email(user: User, request):
    """
    Build and send an email verification link via Celery (send_email_async dispatches
    to the send_email_task Celery task so registration never blocks on mail delivery).
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
    """Approve a role request, update the user's role, and notify them by email."""
    user = role_request.user
    user.role = role_request.requested_role
    user.save(update_fields=["role"])

    role_request.status      = "approved"
    role_request.reviewed_by = reviewed_by
    role_request.save(update_fields=["status", "reviewed_by"])

    # Notify the user that their account is now active
    login_url = f"{settings.FRONTEND_URL}/login"
    send_email_async(
        subject="Your IRIS account has been approved",
        message=(
            f"Hello {user.first_name},\n\n"
            f"Your account has been approved and you have been assigned the role of "
            f"{role_request.requested_role.name}.\n\n"
            f"You can now log in to IRIS at: {login_url}\n\n"
            f"Welcome aboard!\n"
            f"— The IRIS Team"
        ),
        recipient_list=[user.email],
    )


def decline_role_request(role_request: RoleRequest, reviewed_by: User):
    """Decline a role request and notify the user."""
    role_request.status      = "declined"
    role_request.reviewed_by = reviewed_by
    role_request.save(update_fields=["status", "reviewed_by"])

    send_email_async(
        subject="Your IRIS account request was not approved",
        message=(
            f"Hello {role_request.user.first_name},\n\n"
            f"Unfortunately, your request for the {role_request.requested_role.name} role "
            f"on IRIS could not be approved at this time.\n\n"
            f"If you believe this is an error, please contact your department administrator "
            f"or the RDCO office.\n\n"
            f"— The IRIS Team"
        ),
        recipient_list=[role_request.user.email],
    )
