from django.conf import settings
from core.enums import RequestStatus
from core.utils import send_email_async
from .models import User, RoleRequest


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
