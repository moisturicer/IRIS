"""
Workflow routing services for the IRIS review pipeline.

Pipeline routes (type-differentiated bookends; ADR-002):

  Proposal
    draft → adviser_review → approved   (visible as ongoing; NOT published)
    Adviser may decline (revision) → owner resubmits → adviser_review
    Adviser may reject  (terminal) → rejected

  Thesis / Research and Project
    draft → rdco_intake
          → [ itso_review ]   Project only, and only if ITSO was requested
          → [ parallel_review ]   IERC and/or KTTO, whichever were requested
          → rdco_review
          → published

Which of ITSO/IERC/KTTO actually run is no longer fixed by record_type alone
(ADR-018 — extends ADR-002's transition table rather than
replacing it: pipeline_status transitions are still the same declarative
table, only which offices get a RecordClearance row is now data on the
record — record.requested_itso/ierc/ktto — rather than hardcoded here).
ITSO remains structurally Project-only: Thesis/Research never enters
itso_review regardless of what requested_itso says. A record requesting no
offices at all skips straight from rdco_intake to rdco_review — see
_enter_clearance_stage(). Project's ITSO-before-IERC sequencing (KTTO starts
in parallel with ITSO; IERC only joins once ITSO clears, if requested) is
unchanged in shape, just conditional in which offices actually populate it.

At every stage, a reviewer may:
  approve / clear  -- advance to the next stage
  decline          -- send back to owner for revision (→ declined; owner resubmits)
  reject           -- terminal rejection (→ rejected; owner cannot resubmit)

Sequential stages (adviser_review, rdco_intake, rdco_review) use approve_record /
decline_record / reject_record.

Clearance stages (itso_review, parallel_review) use submit_clearance;
individual office statuses are tracked in RecordClearance rows.
"""
from django.utils import timezone

from core.enums import (
    ClearanceStatus,
    Office,
    PipelineStatus,
    ReviewDecision,
    RoleName,
)
from core.exceptions import InvalidPipelineTransition
from apps.records import lifecycle
from .models import Review, RecordClearance
from apps.records.models import Record
from apps.notifications.services import (
    notify_record_reviewed,
    notify_resubmit,
    notify_clearance_result,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# The stage vocabulary, the sequential/parallel split and the routing all live
# in `apps.records.lifecycle` now (IR-136). `_STATUS_TO_STAGE`,
# `REVIEWABLE_STATUSES`, `CLEARANCE_STATUSES`, `_type_name`,
# `_first_status_for_type`, `_all_clearances_done` and `_enter_clearance_stage`
# were all deleted rather than left as thin wrappers: a second copy of the
# routing is exactly the drift the table exists to remove.

# Maps reviewer role name → clearance office key
ROLE_TO_OFFICE: dict[str, str] = {
    RoleName.ITSO: Office.ITSO,
    RoleName.IERC: Office.IERC,
    RoleName.KTTO: Office.KTTO,
}


def _can_review(user, record: Record) -> bool:
    """
    Return True if the user may submit a sequential review (approve/decline/reject)
    at the record's current pipeline stage.

    Adviser : only the assigned adviser, at adviser_review.
    RDCO    : any RDCO user, at rdco_intake or rdco_review.

    There is no Django-staff bypass. There was one, and because migration
    accounts/0005 set is_staff=True on every office role it meant ITSO, IERC and
    KTTO could approve or reject at the sequential adviser/RDCO gates their
    office has no standing at (IR-165).
    """
    role_name = user.role.name if user.role else ""
    status    = record.pipeline_status
    if role_name == RoleName.ADVISER:
        return status == PipelineStatus.ADVISER_REVIEW and record.adviser_id == user.pk
    if role_name == RoleName.RDCO:
        return status in (PipelineStatus.RDCO_INTAKE, PipelineStatus.RDCO_REVIEW)
    return False


def _can_submit_clearance(user, record: Record) -> tuple[bool, str]:
    """
    Return (can_submit, office_key).

    Checks that:
      1. The user's role maps to a valid clearance office.
      2. The record is in a clearance stage.
      3. A pending RecordClearance for that office exists for this record.
      4. The office is appropriate for the current stage:
           itso_review → 'itso' or 'ktto'
           parallel_review → 'ierc' or 'ktto'

    There is no Django-staff bypass. The previous one let any is_staff account
    record *whichever clearance happened to be pending*, regardless of office --
    so with accounts/0005 seeding is_staff=True across the offices, an ITSO
    officer could sign IERC's ethics clearance. That is precisely the office
    separation the thesis contribution rests on (IR-165).
    """
    role_name = user.role.name if user.role else ""
    office    = ROLE_TO_OFFICE.get(role_name, "")

    if not office:
        return False, ""

    if not lifecycle.is_clearance_stage(record.pipeline_status):
        return False, office

    has_pending = RecordClearance.objects.filter(
        record=record, office=office, status=ClearanceStatus.PENDING
    ).exists()

    if not has_pending:
        return False, office

    status = record.pipeline_status
    if status == PipelineStatus.ITSO_REVIEW and office in (Office.ITSO, Office.KTTO):
        return True, office
    if status == PipelineStatus.PARALLEL_REVIEW and office in (Office.IERC, Office.KTTO):
        return True, office
    return False, office


# ---------------------------------------------------------------------------
# Sequential review actions: adviser_review, rdco_intake, rdco_review
# ---------------------------------------------------------------------------

def approve_record(record: Record, reviewed_by, comment: str = "") -> Review:
    """
    Approve the record at its current sequential stage and advance the pipeline.

    At rdco_intake this also creates RecordClearance rows for whichever
    offices were requested (ADR-018) — see _enter_clearance_stage().
    """
    if not _can_review(reviewed_by, record):
        raise InvalidPipelineTransition(
            f"You are not authorised to review this record at '{record.pipeline_status}'."
        )
    stage = lifecycle.review_stage_for(record.pipeline_status)
    if not stage:
        raise InvalidPipelineTransition(
            f"Record is at '{record.pipeline_status}' — use submit_clearance for office reviews."
        )

    review = Review.objects.create(
        record=record, reviewed_by=reviewed_by,
        stage=stage, status=ReviewDecision.APPROVED, comment=comment,
    )

    # Where this lands is the table's call now (IR-136). The four-branch
    # cascade that used to live here -- intake into the clearance stage,
    # adviser_review splitting on record type, rdco_review publishing, and a
    # fallback nobody could reach -- is `TRANSITIONS` plus two resolvers.
    lifecycle.apply(record, lifecycle.WorkflowEvent.APPROVE, reviewed_by)
    notify_record_reviewed(record, review)
    return review


def decline_record(record: Record, reviewed_by, comment: str = "") -> Review:
    """
    Request revision at a sequential stage.
    The record enters 'declined'; the owner may call resubmit_record() to re-enter.
    """
    if not _can_review(reviewed_by, record):
        raise InvalidPipelineTransition(
            f"You are not authorised to review this record at '{record.pipeline_status}'."
        )
    stage = lifecycle.review_stage_for(record.pipeline_status)
    if not stage:
        raise InvalidPipelineTransition(
            f"Record is at '{record.pipeline_status}' — use submit_clearance for office reviews."
        )

    review = Review.objects.create(
        record=record, reviewed_by=reviewed_by,
        stage=stage, status=ReviewDecision.DECLINED, comment=comment,
    )
    lifecycle.apply(record, lifecycle.WorkflowEvent.DECLINE, reviewed_by)
    notify_record_reviewed(record, review)
    return review


def reject_record(record: Record, reviewed_by, comment: str = "") -> Review:
    """
    Terminal rejection at a sequential stage.
    The record enters 'rejected'; the owner cannot resubmit.
    """
    if not _can_review(reviewed_by, record):
        raise InvalidPipelineTransition(
            f"You are not authorised to review this record at '{record.pipeline_status}'."
        )
    stage = lifecycle.review_stage_for(record.pipeline_status)
    if not stage:
        raise InvalidPipelineTransition(
            f"Record is at '{record.pipeline_status}' — use submit_clearance for office reviews."
        )

    review = Review.objects.create(
        record=record, reviewed_by=reviewed_by,
        stage=stage, status=ReviewDecision.REJECTED, comment=comment,
    )
    lifecycle.apply(record, lifecycle.WorkflowEvent.REJECT, reviewed_by)
    notify_record_reviewed(record, review)
    return review


# ---------------------------------------------------------------------------
# Clearance action: itso_review, parallel_review
# ---------------------------------------------------------------------------

def submit_clearance(
    record: Record,
    reviewed_by,
    office: str,
    decision: str,
    comment: str = "",
) -> Review:
    """
    Submit an office clearance during a parallel review stage.

    decision: 'approved' (cleared) | 'declined' (revision requested) | 'rejected' (terminal)

    Transition logic:
      • decline / reject  → record enters declined / rejected; all clearances paused.
      • ITSO approves at itso_review (Project):
          – Creates an IERC clearance (IERC starts after ITSO).
          – Advances pipeline to parallel_review.
      • Any other approval (KTTO at itso_review; IERC/KTTO at parallel_review):
          – If all remaining clearances are now cleared → advances to rdco_review.
          – Otherwise → records partial progress, no status change.
    """
    can, resolved_office = _can_submit_clearance(reviewed_by, record)
    if not can:
        raise InvalidPipelineTransition(
            f"You are not authorised to submit a clearance at '{record.pipeline_status}'."
        )
    # Use the resolved office (covers the Django-staff fallback case)
    if not office:
        office = resolved_office

    # Map external decision labels to internal model values
    if decision == ReviewDecision.APPROVED:
        review_status     = ReviewDecision.APPROVED
        clearance_status  = ClearanceStatus.CLEARED
    elif decision == ReviewDecision.REJECTED:
        review_status     = ReviewDecision.REJECTED
        clearance_status  = ClearanceStatus.REJECTED
    else:  # declined
        review_status     = ReviewDecision.DECLINED
        clearance_status  = ClearanceStatus.DECLINED

    # Always create an audit Review row
    review = Review.objects.create(
        record=record, reviewed_by=reviewed_by,
        stage=office, status=review_status, comment=comment,
    )

    # Update (or create) the RecordClearance row for this office
    clearance, _ = RecordClearance.objects.get_or_create(record=record, office=office)
    clearance.status      = clearance_status
    clearance.reviewed_by = reviewed_by
    clearance.comment     = comment
    clearance.save(update_fields=["status", "reviewed_by", "comment", "updated_at"])

    # ── Where the record goes next is the table's call (IR-136) ───────────
    # The ITSO-then-IERC sequencing and the "have all offices cleared" check
    # are `after_clearance`; declines and rejections are literal edges. What
    # stays here is orchestration: the notification, and the distinction
    # between advancing and merely recording partial progress, which is a
    # message to a person rather than a workflow rule.
    was = record.pipeline_status
    event = {
        ReviewDecision.DECLINED: lifecycle.WorkflowEvent.DECLINE,
        ReviewDecision.REJECTED: lifecycle.WorkflowEvent.REJECT,
    }.get(decision, lifecycle.WorkflowEvent.APPROVE)

    destination = lifecycle.apply(record, event, reviewed_by, office=office)

    if decision in (ReviewDecision.DECLINED, ReviewDecision.REJECTED):
        notify_clearance_result(record, review, office=office, advanced=False)
        return review

    advanced = destination != was
    all_done = destination == PipelineStatus.RDCO_REVIEW
    if advanced:
        notify_clearance_result(
            record, review, office=office, advanced=True, all_done=all_done
        )
    else:
        notify_clearance_result(record, review, office=office, advanced=False)

    return review


# ---------------------------------------------------------------------------
# Resubmission
# ---------------------------------------------------------------------------

def resubmit_record(record: Record, submitted_by) -> Record:
    """
    Resubmit a declined record back into the pipeline.

    Smart routing based on the stage that declined:
      Clearance office (ITSO/IERC/KTTO): reset only that office's clearance and
        route back to the correct clearance stage, preserving other offices' progress.
      Sequential stage (adviser/rdco_intake/rdco): delete all clearances and
        restart from the first stage for the record type.

    Requires at least one document to have been uploaded after the last decline.
    """
    if record.pipeline_status != PipelineStatus.DECLINED:
        raise InvalidPipelineTransition(
            "Only records in 'declined' status can be resubmitted."
        )

    # Validate that the owner uploaded something new since the decline
    last_decline = (
        Review.objects.filter(record=record, status=ReviewDecision.DECLINED)
        .order_by("-created_at")
        .first()
    )
    if last_decline:
        from apps.documents.models import RecordUpload
        has_new_upload = RecordUpload.objects.filter(
            record=record, created_at__gt=last_decline.created_at
        ).exists()
        if not has_new_upload:
            raise InvalidPipelineTransition(
                "Please upload at least one updated document before resubmitting."
            )

    # **ADR-003's contribution, resolved by the table rather than by a set
    # literal here.** Which of the two policies applies -- reset only the
    # declining office and preserve its peers, or drop every clearance and
    # restart -- turns on whether `last_decline.stage` names a clearance office.
    # That membership test used to be `CLEARANCE_OFFICES` written out on the
    # line above; it now comes from `STAGES`, so an office added to a group
    # cannot leave a stale literal behind. The clearance-row surgery moves with
    # it, because resetting one office's row *is* the transition, not a side
    # effect of it.
    declining_stage = last_decline.stage if last_decline else None
    new_status = lifecycle.apply(
        record,
        lifecycle.WorkflowEvent.RESUBMIT,
        submitted_by,
        declining_stage=declining_stage,
    )

    # Record the resubmission itself, not just its effect (IR-139). `preserved`
    # is defined against this timestamp: a clearance decided before it survived
    # a resubmission, one decided after it was granted fresh. Without this the
    # distinction that carries the contribution cannot be recovered afterwards.
    record.pipeline_status = new_status
    record.resubmission_count = (record.resubmission_count or 0) + 1
    record.last_resubmitted_at = timezone.now()
    record.save(
        update_fields=[
            "pipeline_status",
            "resubmission_count",
            "last_resubmitted_at",
            "updated_at",
        ]
    )
    notify_resubmit(record, submitted_by, new_status=new_status)
    return record
