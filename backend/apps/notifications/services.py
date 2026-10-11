"""
Notification service -- creates Notification rows and fires emails.

Design rules:
  - Functions must NEVER raise. A notification failure must not break the
    caller's request/response path. It is logged at ERROR instead, naming
    the function and the record (IR-300), so a dropped notice is visible.
  - All DB writes happen first; email is sent after so a failed email
    does not roll back an already-persisted notification.
  - Use send_email_async from core.utils for all outbound mail.
"""
import logging

from django.conf import settings
from core.enums import (
    Office, Party, PipelineStatus, RecordTypeName, ReviewDecision, ReviewStage, RoleName,
)
from core.utils import send_email_async
from .models import Notification, NotificationType

logger = logging.getLogger(__name__)


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
    if rt_name == RecordTypeName.PROJECT:
        return _get_type("New Record (Project)")
    return _get_type("New Record (Proposal / Thesis)")


def _record_url(record) -> str:
    return f"{settings.FRONTEND_URL}/records/{record.pk}"


def _log_failure(event: str, *, record=None, request=None, user=None):
    """
    Log a notify function's swallowed exception, with its traceback (IR-300).

    Called from inside an `except` block. Names the event and what it was
    about: the record, a request and the record it belongs to, or the user
    for a notice that has no record. Reads only ids already on the objects,
    so the logging itself cannot fail on a query.
    """
    if request is not None:
        about = (
            f"{type(request).__name__} {getattr(request, 'pk', None)} "
            f"on record {getattr(request, 'record_id', None)}"
        )
    elif user is not None:
        about = f"user {getattr(user, 'pk', None)}"
    else:
        about = f"record {getattr(record, 'pk', None)}"
    logger.exception("Notification %s failed for %s", event, about)


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

        adviser = record.adviser
        if not adviser:
            return
        Notification.objects.create(
            sender=submitted_by,
            recipient=adviser,
            record=record,
            notif_type=_record_notif_type(record),
            message=(
                f"{submitted_by.get_full_name()} submitted a new {rt_name} for your review: "
                f'"{record.title}".'
            ),
        )
        send_email_async(
            subject=f"[IRIS] New {rt_name} awaiting your review: {record.title[:60]}",
            message=(
                f"Hello {adviser.first_name},\n\n"
                f"{submitted_by.get_full_name()} has submitted a new {rt_name} for your review.\n\n"
                f"Title: {record.title}\n\n"
                f"Please log in to IRIS to review it:\n{_record_url(record)}\n\n"
                f"-- The IRIS Team"
            ),
            recipient_list=[adviser.email],
        )
    except Exception:
        _log_failure("notify_new_record", record=record)


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
            ReviewStage.ADVISER:     "your Adviser",
            ReviewStage.RDCO_INTAKE: "RDCO (intake review)",
            # `.label`, not the bare string: this map is prose shown to a
            # person ("your Adviser"), and the office's display name is the
            # label rather than the stored key.
            ReviewStage.RDCO:        RoleName.RDCO.label,
        }
        stage_label = _STAGE_LABELS.get(stage, stage)

        if outcome == ReviewDecision.APPROVED:
            new_status = record.pipeline_status  # already advanced before this call

            if stage == ReviewStage.ADVISER:
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

            elif stage == ReviewStage.RDCO_INTAKE:
                if new_status == PipelineStatus.ITSO_REVIEW:
                    # ITSO was requested (either type since IR-266): ITSO reviews
                    # first; KTTO, if requested, starts here in parallel
                    _notify_roles_of_advance(
                        record, review,
                        role_names=[RoleName.ITSO, RoleName.KTTO],
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
                    # No ITSO requested: the record went to parallel_review (or
                    # straight to rdco_review if nothing was requested)
                    _notify_roles_of_advance(
                        record, review,
                        role_names=[RoleName.IERC, RoleName.KTTO],
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

            elif stage == ReviewStage.RDCO:
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

        elif outcome == ReviewDecision.DECLINED:
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
        _log_failure("notify_record_reviewed", record=record)


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
            Office.ITSO: RoleName.ITSO,
            Office.IERC: RoleName.IERC,
            Office.KTTO: RoleName.KTTO,
        }
        office_label = _OFFICE_LABELS.get(office, office.upper())

        if outcome == ReviewDecision.DECLINED:
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

        if outcome == ReviewDecision.REJECTED:
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
                role_names=[RoleName.RDCO],
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
        elif advanced and office == Office.ITSO:
            # ITSO cleared → IERC now starts; KTTO may still be running
            _notify_roles_of_advance(
                record, review,
                role_names=[RoleName.IERC],
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
        _log_failure("notify_clearance_result", record=record)


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

        if new_status == PipelineStatus.ADVISER_REVIEW:
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

        elif new_status in (PipelineStatus.PARALLEL_REVIEW, PipelineStatus.ITSO_REVIEW):
            # Smart resubmit: notify only the office(s) with a pending clearance
            from apps.reviews.models import RecordClearance
            _OFFICE_TO_ROLE = {
                Office.IERC: RoleName.IERC,
                Office.KTTO: RoleName.KTTO,
                Office.ITSO: RoleName.ITSO,
            }
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
            rdco_role = _role(RoleName.RDCO)
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
        _log_failure("notify_resubmit", record=record)


def _role_for_party(party: str):
    """
    The role that staffs an office party (ADR-021 §1), read from the tracker's
    one role-to-party map rather than restated here. None for the Adviser
    party, which is a person -- the record's own `adviser` -- not a role.
    """
    from apps.reviews.tracker import ROLE_TO_PARTIES

    for role_name, parties in ROLE_TO_PARTIES.items():
        if role_name != RoleName.ADVISER and party in parties:
            return _role(role_name)
    return None


def notify_routed(
    record, *, actor, from_label, target_labels, opened_parties, nominees, reason, accepted,
):
    """
    A record was routed to one or more offices (ADR-032 §4, IR-261).

    - Every member of each office the record **newly** reached **into its
      pool**: the pool is shared work, so the whole office hears, in-app and by
      email. An office that already held the record is not told again, and
      neither is one whose router named a nominee -- the record went straight
      to that person, so "in your office's pool" would be false (2026-10-08).
      The caller passes only pool offices in `opened_parties`.
    - Each nominee, personally: the work is theirs.
    - The owners, only when the Adviser **accepted** it. Onward routing between
      offices is review traffic, visible on the tracker.
    """
    try:
        notif_type = NotificationType.objects.get_or_create(name="Record Routed")[0]
        url = _record_url(record)
        title = record.title

        from apps.accounts.models import User as UserModel

        for party in opened_parties:
            role = _role_for_party(party)
            if role is None:
                continue
            message = (
                f'{from_label} sent "{title}" to your office for review: {reason} '
                f"It is in your office's pool until someone claims it."
            )
            Notification.objects.create(
                sender=actor, broadcast_to_role=role, record=record,
                notif_type=notif_type, message=message,
            )
            emails = list(
                UserModel.objects.filter(role=role, is_active=True).values_list("email", flat=True)
            )
            if emails:
                send_email_async(
                    subject=f"[IRIS] For review: {title[:60]}",
                    message=f"Hello,\n\n{message}\n\n{url}\n\n-- The IRIS Team",
                    recipient_list=emails,
                )

        for nominee, office_label in nominees:
            message = f'{from_label} nominated you to review "{title}" for {office_label}.'
            Notification.objects.create(
                sender=actor, recipient=nominee, record=record,
                notif_type=notif_type, message=message,
            )
            send_email_async(
                subject=f"[IRIS] You were nominated to review: {title[:60]}",
                message=f"Hello {nominee.first_name},\n\n{message}\n\n{url}\n\n-- The IRIS Team",
                recipient_list=[nominee.email],
            )

        if accepted:
            offices = " and ".join(target_labels)
            message = f'Your Adviser accepted "{title}" and sent it to {offices} for review.'
            for ownership in record.owners.select_related("user").all():
                Notification.objects.create(
                    sender=actor, recipient=ownership.user, record=record,
                    notif_type=notif_type, message=message,
                )
    except Exception:
        _log_failure("notify_routed", record=record)


def notify_office_completed(
    record, *, actor, office_label, outcome_label, handed_back, rdco_holding, rdco_holders,
):
    """
    A specialist office finished its review round (ADR-032 §3-§4, IR-269).

    - The owners hear the office's outcome. A single reviewer's verdict is
      not announced: it shows on the record, and the office's outcome is the
      fact the author can act on.
    - On the hand-back, every RDCO member hears, in-app and by email: RDCO's
      pool is shared work, as an office pool is in `notify_routed`. The owners
      hear that the record is with RDCO.
    - When RDCO already holds the record -- it routed it back for another
      look -- RDCO's seat holders hear that the office finished, or the whole
      office when nobody there is seated yet.
    """
    try:
        notif_type = NotificationType.objects.get_or_create(name="Office Review Complete")[0]
        url = _record_url(record)
        title = record.title
        owners = [o.user for o in record.owners.select_related("user").all()]

        message = f'{office_label} finished its review of "{title}": {outcome_label}.'
        if handed_back:
            message += " It is now with RDCO for its final decision."
        for owner in owners:
            Notification.objects.create(
                sender=actor, recipient=owner, record=record,
                notif_type=notif_type, message=message,
            )

        rdco_message = None
        if handed_back:
            rdco_message = (
                f'Every office has finished reviewing "{title}". It is in RDCO\'s '
                f"pool for its final decision until someone claims it."
            )
        elif rdco_holding:
            rdco_message = f'{office_label} finished its review of "{title}": {outcome_label}.'
        if rdco_message is None:
            return

        if rdco_holding and rdco_holders:
            for holder in rdco_holders:
                Notification.objects.create(
                    sender=actor, recipient=holder, record=record,
                    notif_type=notif_type, message=rdco_message,
                )
            emails = [u.email for u in rdco_holders if u.email]
        else:
            role = _role_for_party(Party.RDCO)
            if role is None:
                return
            Notification.objects.create(
                sender=actor, broadcast_to_role=role, record=record,
                notif_type=notif_type, message=rdco_message,
            )
            from apps.accounts.models import User as UserModel

            emails = list(
                UserModel.objects.filter(role=role, is_active=True).values_list("email", flat=True)
            )
        if emails:
            send_email_async(
                subject=f"[IRIS] For final review: {title[:60]}" if handed_back
                else f"[IRIS] {office_label} finished: {title[:60]}",
                message=f"Hello,\n\n{rdco_message}\n\n{url}\n\n-- The IRIS Team",
                recipient_list=emails,
            )
    except Exception:
        _log_failure("notify_office_completed", record=record)


def notify_decided(record, *, actor, decided_by, outcome, reason, closed_requests, cut_off):
    """
    A Decision ended the record's review (ADR-032 §2-§3; IR-270, IR-271).

    - Every owner hears it once, in-app, and the primary owner by email. A
      rejection carries its reason as written; a document request the
      decision withdrew is mentioned here rather than separately.
    - Each reviewer whose open seat the decision withdrew hears that their
      review is closed, in-app only. Nobody else: no office pool is told.
    """
    from apps.reviews.decisions import ACCEPT, KEEP_UNLISTED, OUTCOME_PHRASE, PUBLISH

    try:
        title = record.title
        if outcome == ACCEPT:
            message = f'{decided_by} accepted your proposal "{title}".'
            headline = "Accepted"
        elif outcome == PUBLISH:
            message = f'{decided_by} accepted "{title}" and published it to Discover.'
            headline = "Published"
        elif outcome == KEEP_UNLISTED:
            message = (
                f'{decided_by} accepted "{title}" and kept it unlisted: it is not in '
                f"Discover, and you can still open it."
            )
            headline = "Accepted"
        else:
            message = f'{decided_by} rejected "{title}". It is archived. Reason: {reason}'
            headline = "Rejected"
        if closed_requests:
            message += (
                " Its open document request is withdrawn, so nothing more is needed."
                if closed_requests == 1 else
                " Its open document requests are withdrawn, so nothing more is needed."
            )

        notif_type = NotificationType.objects.get_or_create(name="Record Decided")[0]
        owners = list(record.owners.select_related("user").all())
        for ownership in owners:
            Notification.objects.create(
                sender=actor, recipient=ownership.user, record=record,
                notif_type=notif_type, message=message,
            )

        closed = f'{decided_by} {OUTCOME_PHRASE[outcome]}, so your review of "{title}" is closed.'
        for reviewer in cut_off:
            Notification.objects.create(
                sender=actor, recipient=reviewer, record=record,
                notif_type=notif_type, message=closed,
            )

        if owners:
            primary = next((o.user for o in owners if o.is_primary), owners[0].user)
            send_email_async(
                subject=f"[IRIS] {headline}: {title[:60]}",
                message=(
                    f"Hello {primary.first_name},\n\n{message}\n\n"
                    f"{_record_url(record)}\n\n-- The IRIS Team"
                ),
                recipient_list=[primary.email],
            )
    except Exception:
        _log_failure("notify_decided", record=record)


def notify_revision_requested(revision_request, *, party_label: str):
    """
    Tell every owner that a party has asked for a revision (ADR-032 §5
    Amendment, IR-272). The owners only: reviewers see *Waiting on author*.
    """
    try:
        record = revision_request.record
        message = (
            f'{party_label} asked for a revision of "{record.title}". '
            f"Nothing can be decided until you submit a new version."
        )
        owners = list(record.owners.select_related("user").all())
        notif_type = NotificationType.objects.get_or_create(name="Revision Requested")[0]
        for ownership in owners:
            Notification.objects.create(
                sender=revision_request.requested_by,
                recipient=ownership.user,
                record=record,
                notif_type=notif_type,
                message=message,
            )
        if owners:
            primary = next((o.user for o in owners if o.is_primary), owners[0].user)
            send_email_async(
                subject=f"[IRIS] Revision requested: {record.title[:60]}",
                message=(
                    f"Hello {primary.first_name},\n\n"
                    f"{message}\n\n"
                    f"{party_label} wrote:\n{revision_request.reason}\n\n"
                    f"{_record_url(record)}\n\n"
                    f"-- The IRIS Team"
                ),
                recipient_list=[primary.email],
            )
    except Exception:
        _log_failure("notify_revision_requested", request=revision_request)


def notify_revision_withdrawn(revision_request, *, party_label: str, withdrawn_by):
    """Tell every owner that a party withdrew its revision request (IR-272). In-app only."""
    try:
        record = revision_request.record
        message = f'{party_label} withdrew its revision request for "{record.title}".'
        notif_type = NotificationType.objects.get_or_create(name="Revision Requested")[0]
        for ownership in record.owners.select_related("user").all():
            Notification.objects.create(
                sender=withdrawn_by,
                recipient=ownership.user,
                record=record,
                notif_type=notif_type,
                message=message,
            )
    except Exception:
        _log_failure("notify_revision_withdrawn", request=revision_request)


def notify_new_version(record, version, *, submitted_by, reviewers, asked_by: str):
    """
    Tell the reviewers of the parties that asked for a revision that the owner
    answered with a new version, which they now review (ADR-032 §5, IR-273).
    Nobody else: every other party's work stands. In-app only.
    """
    try:
        message = (
            f'The owner submitted v{version.number} of "{record.title}" in answer to '
            f"{asked_by}'s revision request. Review the new version."
        )
        notif_type = NotificationType.objects.get_or_create(name="New Version Submitted")[0]
        for reviewer in reviewers:
            Notification.objects.create(
                sender=submitted_by,
                recipient=reviewer,
                record=record,
                notif_type=notif_type,
                message=message,
            )
    except Exception:
        _log_failure("notify_new_version", record=record)


def notify_document_requested(document_request, *, party_label: str):
    """
    Tell every owner that a party has asked for documents (ADR-022 §3.1).

    `party_label` is the student-facing name, so Intake reads "Intake".
    """
    try:
        record = document_request.record
        wanted = ", ".join(item.label for item in document_request.items.all())
        message = (
            f'{party_label} requested documents for "{record.title}": {wanted}. '
            f"Upload them from the record page."
        )
        owners = list(record.owners.select_related("user").all())
        notif_type = NotificationType.objects.get_or_create(name="Document Requested")[0]
        for ownership in owners:
            Notification.objects.create(
                sender=document_request.requested_by,
                recipient=ownership.user,
                record=record,
                notif_type=notif_type,
                message=message,
            )
        if owners:
            primary = next((o.user for o in owners if o.is_primary), owners[0].user)
            send_email_async(
                subject=f"[IRIS] Documents requested: {record.title[:60]}",
                message=(
                    f"Hello {primary.first_name},\n\n"
                    f"{message}\n\n"
                    f"{party_label} wrote:\n{document_request.message}\n\n"
                    f"{_record_url(record)}\n\n"
                    f"-- The IRIS Team"
                ),
                recipient_list=[primary.email],
            )
    except Exception:
        _log_failure("notify_document_requested", request=document_request)


def notify_document_request_fulfilled(document_request, *, uploaded_by):
    """
    Tell the requesting party that every item now has an upload (ADR-022 §3.3).

    An office hears as a role broadcast, as offices do everywhere else here.
    The Adviser party is the record's assigned Adviser, directly.
    """
    try:
        record = document_request.record
        notif_type = NotificationType.objects.get_or_create(name="Document Request Fulfilled")[0]
        message = (
            f'Every document you requested for "{record.title}" has been uploaded. '
            f"It is ready for you to check."
        )
        if document_request.party == Party.ADVISER:
            if record.adviser is None:
                return
            Notification.objects.create(
                sender=uploaded_by, recipient=record.adviser, record=record,
                notif_type=notif_type, message=message,
            )
            send_email_async(
                subject=f"[IRIS] Requested documents uploaded: {record.title[:60]}",
                message=(
                    f"Hello {record.adviser.first_name},\n\n{message}\n\n"
                    f"{_record_url(record)}\n\n-- The IRIS Team"
                ),
                recipient_list=[record.adviser.email],
            )
            return

        role = _role_for_party(document_request.party)
        if not role:
            return
        Notification.objects.create(
            sender=uploaded_by, broadcast_to_role=role, record=record,
            notif_type=notif_type, message=message,
        )
        _email_role_users(
            role=role,
            subject=f"[IRIS] Requested documents uploaded: {record.title[:60]}",
            greeting=f"Hello {role.name} Team",
            body=f"{message}\n\n{_record_url(record)}",
        )
    except Exception:
        _log_failure("notify_document_request_fulfilled", request=document_request)


def notify_document_rejected(document_request, item, *, rejected_by):
    """
    Tell every owner that the requesting party rejected an upload, and why
    (ADR-022 §3.4, IR-263). The item is asked for again: the owner uploads a
    replacement from the record page, as for the original request.
    """
    try:
        from apps.reviews.tracker import party_label

        record = document_request.record
        asker = party_label(document_request.party, staff_viewer=False)
        message = (
            f'{asker} did not accept "{item.label}" for "{record.title}" and asked '
            f"for it again: {item.rejection_reason}"
        )
        owners = list(record.owners.select_related("user").all())
        notif_type = NotificationType.objects.get_or_create(name="Document Rejected")[0]
        for ownership in owners:
            Notification.objects.create(
                sender=rejected_by,
                recipient=ownership.user,
                record=record,
                notif_type=notif_type,
                message=message,
            )
        if owners:
            primary = next((o.user for o in owners if o.is_primary), owners[0].user)
            send_email_async(
                subject=f"[IRIS] Requested document not accepted: {record.title[:60]}",
                message=(
                    f"Hello {primary.first_name},\n\n"
                    f"{message}\n\n"
                    f"{_record_url(record)}\n\n"
                    f"-- The IRIS Team"
                ),
                recipient_list=[primary.email],
            )
    except Exception:
        _log_failure("notify_document_rejected", request=document_request)


def notify_role_request(user, requested_role):
    """
    Broadcast to RDCO when a new role request is submitted.
    Student and Adviser role requests are approved by RDCO staff;
    staff accounts (RDCO, KTTO, ITSO, IERC) are managed directly by Admin.
    """
    try:
        if requested_role.name == RoleName.ADVISER:
            notif_type_name = "Role Request - Adviser"
        else:
            notif_type_name = "Role Request - Student"

        rdco_role = _role(RoleName.RDCO)
        if rdco_role:
            Notification.objects.create(
                sender=user,
                broadcast_to_role=rdco_role,
                notif_type=_get_type(notif_type_name),
                message=f"{user.get_full_name()} requested the {requested_role.name} role.",
            )
    except Exception:
        _log_failure("notify_role_request", user=user)


def notify_download_request(record, requested_by):
    """Broadcast to KTTO and RDCO when a user requests to download a record's files."""
    try:
        notif_type = _get_type("Download Request Submitted")
        for role_name in (RoleName.KTTO, RoleName.RDCO):
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
        _log_failure("notify_download_request", record=record)


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
        _log_failure("notify_download_reviewed", request=download_request)


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
        _log_failure("notify_delete_approved", request=delete_request)


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
        _log_failure("notify_delete_declined", request=delete_request)


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
