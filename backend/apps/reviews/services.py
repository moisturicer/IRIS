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
    RecordTypeName,
    ReviewDecision,
    ReviewStage,
    RoleName,
)
from core.exceptions import InvalidPipelineTransition
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

def _type_name(record: Record) -> str:
    """Return the record type name, or '' if not set."""
    return record.record_type.name if record.record_type else ""


# Maps pipeline_status → Review.stage for sequential stages only
_STATUS_TO_STAGE: dict[str, str] = {
    PipelineStatus.ADVISER_REVIEW: ReviewStage.ADVISER,
    PipelineStatus.RDCO_INTAKE:    ReviewStage.RDCO_INTAKE,
    PipelineStatus.RDCO_REVIEW:    ReviewStage.RDCO,
}

# Sequential stages where approve/decline/reject are used
REVIEWABLE_STATUSES = set(_STATUS_TO_STAGE.keys())

# Clearance stages — handled exclusively via submit_clearance
CLEARANCE_STATUSES = {PipelineStatus.ITSO_REVIEW, PipelineStatus.PARALLEL_REVIEW}

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

    if record.pipeline_status not in CLEARANCE_STATUSES:
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


def _all_clearances_done(record: Record) -> bool:
    """Return True when no pending clearances remain for this record."""
    return not RecordClearance.objects.filter(
        record=record, status=ClearanceStatus.PENDING
    ).exists()


def _first_status_for_type(record: Record) -> str:
    """The pipeline_status a record enters when submitted or resubmitted."""
    return (
        PipelineStatus.ADVISER_REVIEW
        if _type_name(record) == RecordTypeName.PROPOSAL
        else PipelineStatus.RDCO_INTAKE
    )


def _enter_clearance_stage(record: Record) -> str:
    """
    Create RecordClearance rows for whatever offices were requested, and
    return the pipeline_status that follows rdco_intake.

    ADR-018: the office set is no longer hardcoded by record_type.
    requested_itso only takes effect for Project -- Thesis/Research has no
    ITSO stage at all, matching the structural distinction the type already
    encodes (see the module docstring's two route diagrams). A record
    requesting nothing goes straight to rdco_review: a clearance stage with
    no office attached would just auto-clear, which is worse than skipping it.
    """
    rt = _type_name(record)
    offices: list[str] = []
    if rt == RecordTypeName.PROJECT and record.requested_itso:
        offices.append(Office.ITSO)
    if record.requested_ierc:
        offices.append(Office.IERC)
    if record.requested_ktto:
        offices.append(Office.KTTO)

    for office in offices:
        RecordClearance.objects.get_or_create(record=record, office=office)

    if Office.ITSO in offices:
        return PipelineStatus.ITSO_REVIEW
    if offices:
        return PipelineStatus.PARALLEL_REVIEW
    return PipelineStatus.RDCO_REVIEW


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
    stage = _STATUS_TO_STAGE.get(record.pipeline_status)
    if not stage:
        raise InvalidPipelineTransition(
            f"Record is at '{record.pipeline_status}' — use submit_clearance for office reviews."
        )

    review = Review.objects.create(
        record=record, reviewed_by=reviewed_by,
        stage=stage, status=ReviewDecision.APPROVED, comment=comment,
    )

    if record.pipeline_status == PipelineStatus.RDCO_INTAKE:
        next_status = _enter_clearance_stage(record)
    elif record.pipeline_status == PipelineStatus.ADVISER_REVIEW:
        # Proposals end at 'approved' (visible as ongoing); all other types published at rdco_review
        next_status = (
            PipelineStatus.APPROVED
            if _type_name(record) == RecordTypeName.PROPOSAL
            else PipelineStatus.PUBLISHED
        )
    elif record.pipeline_status == PipelineStatus.RDCO_REVIEW:
        next_status = PipelineStatus.PUBLISHED
    else:
        next_status = PipelineStatus.PUBLISHED  # fallback; should never be reached

    record.pipeline_status = next_status
    record.save(update_fields=["pipeline_status", "updated_at"])
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
    stage = _STATUS_TO_STAGE.get(record.pipeline_status)
    if not stage:
        raise InvalidPipelineTransition(
            f"Record is at '{record.pipeline_status}' — use submit_clearance for office reviews."
        )

    review = Review.objects.create(
        record=record, reviewed_by=reviewed_by,
        stage=stage, status=ReviewDecision.DECLINED, comment=comment,
    )
    record.pipeline_status = PipelineStatus.DECLINED
    record.save(update_fields=["pipeline_status", "updated_at"])
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
    stage = _STATUS_TO_STAGE.get(record.pipeline_status)
    if not stage:
        raise InvalidPipelineTransition(
            f"Record is at '{record.pipeline_status}' — use submit_clearance for office reviews."
        )

    review = Review.objects.create(
        record=record, reviewed_by=reviewed_by,
        stage=stage, status=ReviewDecision.REJECTED, comment=comment,
    )
    record.pipeline_status = PipelineStatus.REJECTED
    record.save(update_fields=["pipeline_status", "updated_at"])
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

    # ── Decline or reject: pause the pipeline ─────────────────────────────
    if decision in (ReviewDecision.DECLINED, ReviewDecision.REJECTED):
        record.pipeline_status = (
            PipelineStatus.REJECTED
            if decision == ReviewDecision.REJECTED
            else PipelineStatus.DECLINED
        )
        record.save(update_fields=["pipeline_status", "updated_at"])
        notify_clearance_result(record, review, office=office, advanced=False)
        return review

    # ── ITSO approved at itso_review (Project only) ───────────────────────
    if office == Office.ITSO and record.pipeline_status == PipelineStatus.ITSO_REVIEW:
        # IERC begins after ITSO clears -- but only if it was actually
        # requested (ADR-018). Unconditionally creating it here, as before,
        # would force an ethics review nobody asked for.
        if record.requested_ierc:
            RecordClearance.objects.get_or_create(record=record, office=Office.IERC)
        # KTTO may have already cleared, be pending, or never have been
        # requested at all -- _all_clearances_done reflects whichever is true.
        if _all_clearances_done(record):
            record.pipeline_status = PipelineStatus.RDCO_REVIEW
            record.save(update_fields=["pipeline_status", "updated_at"])
            notify_clearance_result(
                record, review, office=Office.ITSO, advanced=True, all_done=True
            )
        else:
            record.pipeline_status = PipelineStatus.PARALLEL_REVIEW
            record.save(update_fields=["pipeline_status", "updated_at"])
            notify_clearance_result(record, review, office=Office.ITSO, advanced=True)
        return review

    # ── All other approved clearances ─────────────────────────────────────
    if _all_clearances_done(record):
        record.pipeline_status = PipelineStatus.RDCO_REVIEW
        record.save(update_fields=["pipeline_status", "updated_at"])
        notify_clearance_result(record, review, office=office, advanced=True, all_done=True)
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

    # Office values, compared against `Review.stage`, which is a ReviewStage.
    # The two vocabularies deliberately share these three values: the stage a
    # clearance review is recorded at *is* the office that reviewed it. Naming
    # the set `Office` says which meaning is intended here -- the branch below
    # goes straight on to filter RecordClearance by it. Worth pinning before
    # IR-136 keys a transition table on one or the other.
    CLEARANCE_OFFICES = {Office.ITSO, Office.IERC, Office.KTTO}

    if last_decline and last_decline.stage in CLEARANCE_OFFICES:
        # Smart resubmit: only reset the declining office's clearance
        office = last_decline.stage
        RecordClearance.objects.filter(record=record, office=office).update(
            status=ClearanceStatus.PENDING, reviewed_by=None, comment=""
        )
        # Route back to the clearance stage this office reviews at
        if office == Office.ITSO:
            new_status = PipelineStatus.ITSO_REVIEW
        elif office == Office.IERC:
            new_status = PipelineStatus.PARALLEL_REVIEW
        else:  # ktto — can review at both itso_review (Project) and parallel_review
            itso_pending = RecordClearance.objects.filter(
                record=record, office=Office.ITSO, status=ClearanceStatus.PENDING
            ).exists()
            new_status = (
                PipelineStatus.ITSO_REVIEW if itso_pending else PipelineStatus.PARALLEL_REVIEW
            )
    else:
        # Sequential stage decline: full reset, restart from the beginning
        RecordClearance.objects.filter(record=record).delete()
        new_status = _first_status_for_type(record)

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
