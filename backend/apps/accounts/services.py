from django.db import transaction
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from core.enums import RequestStatus
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
    """
    Verify the activation token and mark the user as verified. Returns user or None.

    RDCO hears of the person's role request here and nowhere earlier, so a
    mistyped address that is never verified alerts nobody (ADR-051 decision 20,
    IR-784). The token stays valid after use -- Django's generator hashes the
    password and last login, not `is_verified` -- so the link can be followed
    again. The flip is therefore one conditional UPDATE, and only the request
    that changed the row notifies: a repeated or concurrent click does not.
    """
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
    from apps.notifications.services import notify_role_request
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, OverflowError):
        return None

    if not default_token_generator.check_token(user, token):
        return None

    with transaction.atomic():
        newly_verified = User.objects.filter(pk=user.pk, is_verified=False).update(is_verified=True)
        if newly_verified:
            pending = (
                user.role_requests.filter(status=RequestStatus.PENDING)
                .select_related("requested_role")
                .order_by("-created_at")
                .first()
            )
            if pending:
                notify_role_request(user, pending.requested_role)
    user.is_verified = True
    return user


def approve_role_request(role_request: RoleRequest, reviewed_by: User):
    """Approve a role request, update the user's role, and notify them by email."""
    user = role_request.user
    user.assign_role(role_request.requested_role)

    role_request.status      = RequestStatus.APPROVED
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
    role_request.status      = RequestStatus.DECLINED
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
