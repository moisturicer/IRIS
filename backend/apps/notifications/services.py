from .models import Notification, NotificationType
from apps.accounts.models import Role


def _get_type(name: str) -> NotificationType:
    return NotificationType.objects.get(name=name)


def notify_role_request(user, requested_role: Role):
    """Broadcast to KTTO when a new role request is submitted."""
    # TODO: determine correct broadcast role based on requested_role
    ktto_role = Role.objects.filter(name="KTTO").first()
    Notification.objects.create(
        sender=user,
        broadcast_to_role=ktto_role,
        notif_type=_get_type("Role Request - Student"),
        message=f"{user.get_full_name()} requested the {requested_role.name} role.",
    )


def notify_record_reviewed(record, review):
    """Notify record owners when their record is approved or declined."""
    # TODO: implement -- send direct notification to all RecordOwner users
    pass


def notify_new_record(record, submitted_by):
    """Notify the adviser when a student submits a record."""
    # TODO: implement
    pass


def notify_download_request(record, requested_by):
    """Broadcast to RDCO when a download is requested."""
    # TODO: implement
    pass
