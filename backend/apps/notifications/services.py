"""
Notification service -- creates Notification rows and fires emails.

Design rules:
  - Functions must NEVER raise. A notification failure must not break the
    caller's request/response path.
  - All DB writes happen first; email is sent after so a failed email
    does not roll back an already-persisted notification.
  - Use send_email_async from core.utils for all outbound mail.
"""
from django.conf import settings
from core.utils import send_email_async
from .models import Notification, NotificationType


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_type(name: str) -> NotificationType:
    return NotificationType.objects.get(name=name)


def _role(name: str):
    from apps.accounts.models import Role
    return Role.objects.filter(name=name).first()


def _record_notif_type(record) -> NotificationType:
    rt_name = record.record_type.name if record.record_type else ""
    if rt_name == "Project":
        return _get_type("New Record (Project)")
    return _get_type("New Record (Proposal / Thesis)")


def _record_url(record) -> str:
    return f"{settings.FRONTEND_URL}/records/{record.pk}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def notify_new_record(record, submitted_by):
    """
    Notify the correct party when a student submits a record.

    Proposal        → direct notification + email to the assigned adviser
    Thesis/Research → broadcast to RDCO role
    Project         → broadcast to RDCO role
    """
    try:
        rt_name = record.record_type.name if record.record_type else ""

        if rt_name == "Proposal":
            adviser = record.adviser
            if not adviser:
                return
            Notification.objects.create(
                sender=submitted_by,
                recipient=adviser,
                record=record,
                notif_type=_record_notif_type(record),
                message=(
                    f"{submitted_by.get_full_name()} submitted a new Proposal for your review: "
                    f'"{record.title}".'
                ),
            )
            send_email_async(
                subject=f"[IRIS] New Proposal awaiting your review: {record.title[:60]}",
                message=(
                    f"Hello {adviser.first_name},\n\n"
                    f"{submitted_by.get_full_name()} has submitted a new Proposal for your review.\n\n"
                    f"Title: {record.title}\n\n"
                    f"Please log in to IRIS to review it:\n{_record_url(record)}\n\n"
                    f"-- The IRIS Team"
                ),
                recipient_list=[adviser.email],
            )

        else:
            # Thesis/Research and Project go to RDCO intake
            rdco_role = _role("RDCO")
            if not rdco_role:
                return
            Notification.objects.create(
                sender=submitted_by,
                broadcast_to_role=rdco_role,
                record=record,
                notif_type=_record_notif_type(record),
                message=(
                    f"{submitted_by.get_full_name()} submitted a new {rt_name} for RDCO intake review: "
                    f'"{record.title}".'
                ),
            )
            _email_role_users(
                role=rdco_role,
                subject=f"[IRIS] New {rt_name} submitted for intake review: {record.title[:60]}",
                greeting="Hello RDCO Team",
                body=(
                    f"{submitted_by.get_full_name()} has submitted a new {rt_name} record.\n\n"
                    f"Title: {record.title}\n\n"
                    f"Please log in to IRIS to review the submission:\n{_record_url(record)}"
                ),
            )
    except Exception:
        pass


def notify_record_reviewed(record, review):
    """
    Dispatch notifications after a sequential review action
    (adviser_review, rdco_intake, rdco_review).

    On approval, notify whoever is next in the pipeline.
    On decline or rejection, notify the record owners.
    """
    try:
        stage   = review.stage   # adviser | rdco_intake | rdco
        outcome = review.status  # approved | declined | rejected

        _STAGE_LABELS = {
            "adviser":     "your Adviser",
            "rdco_intake": "RDCO (intake review)",
            "rdco":        "RDCO",
        }
        stage_label = _STAGE_LABELS.get(stage, stage)

        if outcome == "approved":
            new_status = record.pipeline_status  # already advanced before this call

            if stage == "adviser":
                # Proposal approved → published
                _notify_owners(
                    record, review,
                    notif_type=_get_type("Record Approved"),
                    message=(
                        f'Your Proposal "{record.title}" has been approved by your Adviser '
                        f"and is now published."
                    ),
                    email_subject=f"[IRIS] Your record has been approved: {record.title[:60]}",
                    email_body_template=(
                        f'Congratulations! Your Proposal "{record.title}" has been approved by your Adviser '
                        f"and is now published in IRIS.\n\n"
                        f"You can view it here:\n{_record_url(record)}"
                    ),
                )

            elif stage == "rdco_intake":
                if new_status == "itso_review":
                    # Project: ITSO reviews first; KTTO also starts here in parallel
                    _notify_roles_of_advance(
                        record, review,
                        role_names=["ITSO", "KTTO"],
                        message=(
                            f'Record "{record.title}" has passed RDCO intake review '
                            f"and is ready for ITSO and KTTO review."
                        ),
                        email_subject=f"[IRIS] Record awaiting office review: {record.title[:60]}",
                        email_body=(
                            f"A record has passed RDCO intake and is now awaiting review.\n\n"
                            f"Title: {record.title}\n\n"
                            f"Please log in to IRIS to review it:\n{_record_url(record)}"
                        ),
                        email_greeting="Hello Review Team",
                        owner_message=(
                            f'Your record "{record.title}" has passed RDCO intake review '
                            f"and is now with ITSO for technical review (KTTO is also reviewing in parallel)."
                        ),
                    )
                else:
                    # Thesis/Research: parallel_review — IERC + KTTO both start now in parallel
                    _notify_roles_of_advance(
                        record, review,
                        role_names=["IERC", "KTTO"],
                        message=(
                            f'Record "{record.title}" has passed RDCO intake review '
                            f"and is ready for IERC and KTTO parallel review."
                        ),
                        email_subject=f"[IRIS] Record awaiting parallel office review: {record.title[:60]}",
                        email_body=(
                            f"A record has passed RDCO intake and is now awaiting "
                            f"parallel review by IERC and KTTO.\n\n"
                            f"Title: {record.title}\n\n"
                            f"Please log in to IRIS to review it:\n{_record_url(record)}"
                        ),
                        email_greeting="Hello Review Team",
                        owner_message=(
                            f'Your record "{record.title}" has passed RDCO intake review '
                            f"and is now with IERC and KTTO for parallel review."
                        ),
                    )

            elif stage == "rdco":
                # RDCO final approval → published
                _notify_owners(
                    record, review,
                    notif_type=_get_type("Record Approved"),
                    message=f'Your record "{record.title}" has been approved by RDCO and is now published.',
                    email_subject=f"[IRIS] Your record has been approved: {record.title[:60]}",
                    email_body_template=(
                        f'Congratulations! Your record "{record.title}" has been approved by RDCO '
                        f"and is now published in IRIS.\n\n"
                        f"You can view it here:\n{_record_url(record)}"
                    ),
                )

        elif outcome == "declined":
            reason = review.comment or "No reason was provided."
            _notify_owners(
                record, review,
                notif_type=_get_type("Record Declined"),
                message=(
                    f'Your record "{record.title}" has been sent back for revision by {stage_label}. '
                    f"Reason: {reason}"
                ),
                email_subject=f"[IRIS] Revision requested for your record: {record.title[:60]}",
                email_body_template=(
                    f'Your record "{record.title}" has been reviewed by {stage_label} '
                    f"and requires revision.\n\n"
                    f"Reason: {reason}\n\n"
                    f"Please log in to IRIS, make the necessary changes, and resubmit:\n"
                    f"{_record_url(record)}"
                ),
            )

        else:  # rejected
            reason = review.comment or "No reason was provided."
            _notify_owners(
                record, review,
                notif_type=_get_type("Record Declined"),
                message=(
                    f'Your record "{record.title}" has been rejected by {stage_label}. '
                    f"Reason: {reason}"
                ),
                email_subject=f"[IRIS] Your record has been rejected: {record.title[:60]}",
                email_body_template=(
                    f'Your record "{record.title}" has been rejected by {stage_label}.\n\n'
                    f"Reason: {reason}\n\n"
                    f"If you believe this is an error, please contact the relevant office directly.\n\n"
                    f"You can view the record here:\n{_record_url(record)}"
                ),
            )

    except Exception:
        pass


def notify_clearance_result(record, review, *, office: str, advanced: bool, all_done: bool = False):
    """
    Notify parties after a parallel office clearance (ITSO, IERC, or KTTO).

    advanced=True, all_done=True  → all offices cleared; RDCO notified for final review;
                                     owners told record is with RDCO.
    advanced=True, all_done=False → ITSO cleared; IERC notified to start; owners updated.
    advanced=False, status=approved → partial clearance; owners told which office cleared.
    advanced=False, status=declined → revision; owners notified.
    advanced=False, status=rejected → rejection; owners notified.
    """
    try:
        outcome = review.status  # approved | declined | rejected
        reason  = review.comment or "No reason was provided."

        _OFFICE_LABELS = {
            "itso": "ITSO",
            "ierc": "IERC",
            "ktto": "KTTO",
        }
        office_label = _OFFICE_LABELS.get(office, office.upper())

        if outcome == "declined":
            _notify_owners(
                record, review,
                notif_type=_get_type("Record Declined"),
                message=(
                    f'Your record "{record.title}" has been sent back for revision by {office_label}. '
                    f"Reason: {reason}"
                ),
                email_subject=f"[IRIS] Revision requested by {office_label}: {record.title[:60]}",
                email_body_template=(
                    f'Your record "{record.title}" has been reviewed by {office_label} '
                    f"and requires revision.\n\n"
                    f"Reason: {reason}\n\n"
                    f"Please log in to IRIS, make the necessary changes, and resubmit:\n"
                    f"{_record_url(record)}"
                ),
            )
            return

        if outcome == "rejected":
            _notify_owners(
                record, review,
                notif_type=_get_type("Record Declined"),
                message=(
                    f'Your record "{record.title}" has been rejected by {office_label}. '
                    f"Reason: {reason}"
                ),
                email_subject=f"[IRIS] Your record has been rejected by {office_label}: {record.title[:60]}",
                email_body_template=(
                    f'Your record "{record.title}" has been rejected by {office_label}.\n\n'
                    f"Reason: {reason}\n\n"
                    f"If you believe this is an error, please contact the {office_label} office directly.\n\n"
                    f"You can view the record here:\n{_record_url(record)}"
                ),
            )
            return

        # outcome == 'approved'
        if all_done:
            # All offices cleared → RDCO final review
            _notify_roles_of_advance(
                record, review,
                role_names=["RDCO"],
                message=(
                    f'Record "{record.title}" has been cleared by all reviewing offices '
                    f"and is ready for RDCO final review."
                ),
                email_subject=f"[IRIS] Record awaiting RDCO final review: {record.title[:60]}",
                email_body=(
                    f"A record has been cleared by all offices and is now awaiting RDCO final review.\n\n"
                    f"Title: {record.title}\n\n"
                    f"Please log in to IRIS to review it:\n{_record_url(record)}"
                ),
                email_greeting="Hello RDCO Team",
                owner_message=(
                    f'Your record "{record.title}" has been cleared by all reviewing offices '
                    f"and is now awaiting RDCO final review."
                ),
            )
        elif advanced and office == "itso":
            # ITSO cleared → IERC now starts; KTTO may still be running
            _notify_roles_of_advance(
                record, review,
                role_names=["IERC"],
                message=(
                    f'Record "{record.title}" has been cleared by ITSO. '
                    f"IERC ethics review is now required."
                ),
                email_subject=f"[IRIS] Record awaiting IERC ethics review: {record.title[:60]}",
                email_body=(
                    f"A record has been cleared by ITSO and now requires IERC ethics review.\n\n"
                    f"Title: {record.title}\n\n"
                    f"Please log in to IRIS to review it:\n{_record_url(record)}"
                ),
                email_greeting="Hello IERC Team",
                owner_message=(
                    f'Your record "{record.title}" has been cleared by ITSO '
                    f"and is now with IERC for ethics review."
                ),
            )
        else:
            # Partial clearance (KTTO or IERC cleared but not all done yet)
            notif_type = _get_type("Record Advanced")
            _notify_owners(
                record, review,
                notif_type=notif_type,
                message=(
                    f'Your record "{record.title}" has been cleared by {office_label}. '
                    f"Review is still in progress with other offices."
                ),
                email_subject=f"[IRIS] {office_label} cleared your record: {record.title[:60]}",
                email_body_template=(
                    f'Your record "{record.title}" has been reviewed and cleared by {office_label}.\n\n'
                    f"Review is still in progress with other offices. "
                    f"You will be notified once all offices have cleared your record.\n\n"
                    f"Track your record here:\n{_record_url(record)}"
                ),
            )

    except Exception:
        pass


def notify_resubmit(record, submitted_by, new_status: str):
    """
    Notify the correct party when an owner resubmits a declined record.

    new_status == "adviser_review"  → notify the assigned adviser (Proposal)
    new_status == "rdco_intake"     → notify RDCO (Thesis/Research, Project full restart)
    new_status == "parallel_review" → notify offices with a pending clearance (IERC/KTTO)
    new_status == "itso_review"     → notify offices with a pending clearance (ITSO/KTTO)
    """
    try:
        notif_type = _get_type("Record Resubmission")
        url        = _record_url(record)

        if new_status == "adviser_review":
            adviser = record.adviser
            if not adviser:
                return
            Notification.objects.create(
                sender=submitted_by,
                recipient=adviser,
                record=record,
                notif_type=notif_type,
                message=(
                    f"{submitted_by.get_full_name()} has resubmitted "
                    f'"{record.title}" for your review.'
                ),
            )
            send_email_async(
                subject=f"[IRIS] Record resubmitted for your review: {record.title[:60]}",
                message=(
                    f"Hello {adviser.first_name},\n\n"
                    f"{submitted_by.get_full_name()} has resubmitted a record after revision.\n\n"
                    f"Title: {record.title}\n\n"
                    f"Please log in to IRIS to review it:\n{url}\n\n"
                    f"-- The IRIS Team"
                ),
                recipient_list=[adviser.email],
            )

        elif new_status in ("parallel_review", "itso_review"):
            # Smart resubmit: notify only the office(s) with a pending clearance
            from apps.reviews.models import RecordClearance
            _OFFICE_TO_ROLE = {"ierc": "IERC", "ktto": "KTTO", "itso": "ITSO"}
            pending_offices = list(
                RecordClearance.objects.filter(record=record, status="pending")
                .values_list("office", flat=True)
            )
            for office_key in pending_offices:
                role_name = _OFFICE_TO_ROLE.get(office_key)
                if not role_name:
                    continue
                role = _role(role_name)
                if not role:
                    continue
                Notification.objects.create(
                    sender=submitted_by,
                    broadcast_to_role=role,
                    record=record,
                    notif_type=notif_type,
                    message=(
                        f"{submitted_by.get_full_name()} has resubmitted "
                        f'"{record.title}" after revision. Please re-review.'
                    ),
                )
                _email_role_users(
                    role=role,
                    subject=f"[IRIS] Record resubmitted for {role_name} review: {record.title[:60]}",
                    greeting=f"Hello {role_name} Team",
                    body=(
                        f"{submitted_by.get_full_name()} has resubmitted a record after revision.\n\n"
                        f"Title: {record.title}\n\n"
                        f"Please log in to IRIS to review it:\n{url}"
                    ),
                )

        else:
            # rdco_intake: Thesis/Research or Project resubmitted to RDCO
            rdco_role = _role("RDCO")
            if not rdco_role:
                return
            Notification.objects.create(
                sender=submitted_by,
                broadcast_to_role=rdco_role,
                record=record,
                notif_type=notif_type,
                message=(
                    f"{submitted_by.get_full_name()} has resubmitted "
                    f'"{record.title}" for RDCO intake review.'
                ),
            )
            _email_role_users(
                role=rdco_role,
                subject=f"[IRIS] Record resubmitted for intake review: {record.title[:60]}",
                greeting="Hello RDCO Team",
                body=(
                    f"{submitted_by.get_full_name()} has resubmitted a record after revision.\n\n"
                    f"Title: {record.title}\n\n"
                    f"Please log in to IRIS to review it:\n{url}"
                ),
            )
    except Exception:
        pass


def notify_proposal_completed(record, marked_by):
    """
    Notify record owners when RDCO marks a Proposal as completed.
    """
    try:
        notif_type = _get_type("Record Approved")
        message = (
            f'Your Proposal "{record.title}" has been marked as completed by RDCO. '
            f"It remains visible in the repository as a completed research proposal."
        )
        owners = list(record.owners.select_related("user").all())
        for ownership in owners:
            Notification.objects.create(
                sender=marked_by,
                recipient=ownership.user,
                record=record,
                notif_type=notif_type,
                message=message,
            )
        if owners:
            primary = next((o.user for o in owners if o.is_primary), owners[0].user)
            send_email_async(
                subject=f"[IRIS] Your proposal has been marked as completed: {record.title[:60]}",
                message=(
                    f"Hello {primary.first_name},\n\n"
                    f'Your Proposal "{record.title}" has been marked as completed by RDCO.\n\n'
                    f"It remains publicly visible in the IRIS repository as a completed research proposal.\n\n"
                    f"You can view it here:\n{_record_url(record)}\n\n"
                    f"-- The IRIS Team"
                ),
                recipient_list=[primary.email],
            )
    except Exception:
        pass


def notify_role_request(user, requested_role):
    """
    Broadcast to RDCO when a new role request is submitted.
    Student and Adviser role requests are approved by RDCO staff;
    staff accounts (RDCO, KTTO, ITSO, IERC) are managed directly by Admin.
    """
    try:
        if requested_role.name == "Adviser":
            notif_type_name = "Role Request - Adviser"
        else:
            notif_type_name = "Role Request - Student"

        rdco_role = _role("RDCO")
        if rdco_role:
            Notification.objects.create(
                sender=user,
                broadcast_to_role=rdco_role,
                notif_type=_get_type(notif_type_name),
                message=f"{user.get_full_name()} requested the {requested_role.name} role.",
            )
    except Exception:
        pass


def notify_download_request(record, requested_by):
    """Broadcast to KTTO and RDCO when a user requests to download a record's files."""
    try:
        notif_type = _get_type("Download Request Submitted")
        for role_name in ("KTTO", "RDCO"):
            role = _role(role_name)
            if role:
                Notification.objects.create(
                    sender=requested_by,
                    broadcast_to_role=role,
                    record=record,
                    notif_type=notif_type,
                    message=(
                        f"{requested_by.get_full_name()} has requested to download "
                        f'files for record "{record.title}".'
                    ),
                )
    except Exception:
        pass


def notify_download_reviewed(download_request, reviewed_by, approved: bool):
    """Notify the requester when their download request is approved or declined."""
    try:
        requester = download_request.requested_by
        record    = download_request.record
        url       = _record_url(record)

        if approved:
            notif_type = _get_type("Download Request Approved")
            message    = f'Your download request for "{record.title}" has been approved.'
            Notification.objects.create(
                sender=reviewed_by,
                recipient=requester,
                record=record,
                notif_type=notif_type,
                message=message,
            )
            send_email_async(
                subject=f"[IRIS] Download request approved: {record.title[:60]}",
                message=(
                    f"Hello {requester.first_name},\n\n"
                    f'Your request to download files for "{record.title}" has been approved.\n\n'
                    f"You can access the record here:\n{url}\n\n"
                    f"-- The IRIS Team"
                ),
                recipient_list=[requester.email],
            )
        else:
            notif_type = _get_type("Download Request Declined")
            Notification.objects.create(
                sender=reviewed_by,
                recipient=requester,
                record=record,
                notif_type=notif_type,
                message=f'Your download request for "{record.title}" has been declined.',
            )
    except Exception:
        pass


def notify_delete_approved(delete_request, reviewed_by):
    """Notify the requester when their delete request is approved."""
    try:
        requester = delete_request.requested_by
        record    = delete_request.record

        Notification.objects.create(
            sender=reviewed_by,
            recipient=requester,
            record=record,
            notif_type=_get_type("Delete Request Approved"),
            message=(
                f'Your deletion request for "{record.title}" has been approved. '
                f"The record has been removed."
            ),
        )
    except Exception:
        pass


def notify_delete_declined(delete_request, reviewed_by):
    """Notify the requester when their delete request is declined."""
    try:
        requester = delete_request.requested_by
        record    = delete_request.record

        Notification.objects.create(
            sender=reviewed_by,
            recipient=requester,
            record=record,
            notif_type=_get_type("Delete Request Declined"),
            message=(
                f'Your deletion request for "{record.title}" has been declined. '
                f"The record remains published."
            ),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _notify_roles_of_advance(
    record, review, *, role_names, message,
    email_subject, email_body, email_greeting,
    owner_message: str = "",
):
    """
    Create broadcast Notification rows for each role in role_names,
    send a single email to all users in those roles,
    and optionally notify the record owners about pipeline progress.
    """
    from apps.accounts.models import User as UserModel

    all_emails = []
    notif_type = _get_type("Record Advanced")

    for role_name in role_names:
        role = _role(role_name)
        if not role:
            continue
        Notification.objects.create(
            sender=review.reviewed_by,
            broadcast_to_role=role,
            record=record,
            notif_type=notif_type,
            message=message,
        )
        emails = list(
            UserModel.objects.filter(role=role, is_active=True)
            .values_list("email", flat=True)
        )
        all_emails.extend(emails)

    if all_emails:
        send_email_async(
            subject=email_subject,
            message=(
                f"{email_greeting},\n\n"
                f"{email_body}\n\n"
                f"-- The IRIS Team"
            ),
            recipient_list=list(set(all_emails)),
        )

    if owner_message:
        _notify_owners(
            record, review,
            notif_type=notif_type,
            message=owner_message,
            email_subject=f"[IRIS] Update on your record: {record.title[:60]}",
            email_body_template=owner_message + f"\n\nTrack your record here:\n{_record_url(record)}",
        )


def _notify_owners(record, review, *, notif_type, message, email_subject, email_body_template):
    """Create a direct Notification for every record owner, then email the primary owner."""
    owners = list(record.owners.select_related("user").all())
    if not owners:
        return

    for ownership in owners:
        Notification.objects.create(
            sender=review.reviewed_by,
            recipient=ownership.user,
            record=record,
            notif_type=notif_type,
            message=message,
        )

    primary = next((o.user for o in owners if o.is_primary), owners[0].user)
    send_email_async(
        subject=email_subject,
        message=(
            f"Hello {primary.first_name},\n\n"
            f"{email_body_template}\n\n"
            f"-- The IRIS Team"
        ),
        recipient_list=[primary.email],
    )


def _email_role_users(role, *, subject, greeting, body):
    """Send one email to all active users with the given role."""
    from apps.accounts.models import User as UserModel

    emails = list(
        UserModel.objects.filter(role=role, is_active=True)
        .values_list("email", flat=True)
    )
    if emails:
        send_email_async(
            subject=subject,
            message=f"{greeting},\n\n{body}\n\n-- The IRIS Team",
            recipient_list=emails,
        )
