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
(ADR-018, Proposed — extends ADR-002's transition table rather than
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
    "adviser_review": "adviser",
    "rdco_intake":    "rdco_intake",
    "rdco_review":    "rdco",
}

# Sequential stages where approve/decline/reject are used
REVIEWABLE_STATUSES = set(_STATUS_TO_STAGE.keys())

# Clearance stages — handled exclusively via submit_clearance
CLEARANCE_STATUSES = {"itso_review", "parallel_review"}

# Maps reviewer role name → clearance office key
ROLE_TO_OFFICE: dict[str, str] = {
    "ITSO": "itso",
    "IERC": "ierc",
    "KTTO": "ktto",
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
    if role_name == "Adviser":
        return status == "adviser_review" and record.adviser_id == user.pk
    if role_name == "RDCO":
        return status in ("rdco_intake", "rdco_review")
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
        record=record, office=office, status="pending"
    ).exists()

    if not has_pending:
        return False, office

    status = record.pipeline_status
    if status == "itso_review" and office in ("itso", "ktto"):
        return True, office
    if status == "parallel_review" and office in ("ierc", "ktto"):
        return True, office
    return False, office


def _all_clearances_done(record: Record) -> bool:
    """Return True when no pending clearances remain for this record."""
    return not RecordClearance.objects.filter(record=record, status="pending").exists()


def _first_status_for_type(record: Record) -> str:
    """The pipeline_status a record enters when submitted or resubmitted."""
    return "adviser_review" if _type_name(record) == "Proposal" else "rdco_intake"


def _enter_clearance_stage(record: Record) -> str:
    """
    Create RecordClearance rows for whatever offices were requested, and
    return the pipeline_status that follows rdco_intake.

    ADR-018 (Proposed): the office set is no longer hardcoded by record_type.
    requested_itso only takes effect for Project -- Thesis/Research has no
    ITSO stage at all, matching the structural distinction the type already
    encodes (see the module docstring's two route diagrams). A record
    requesting nothing goes straight to rdco_review: a clearance stage with
    no office attached would just auto-clear, which is worse than skipping it.
    """
    rt = _type_name(record)
    offices: list[str] = []
    if rt == "Project" and record.requested_itso:
        offices.append("itso")
    if record.requested_ierc:
        offices.append("ierc")
    if record.requested_ktto:
        offices.append("ktto")

    for office in offices:
        RecordClearance.objects.get_or_create(record=record, office=office)

    if "itso" in offices:
        return "itso_review"
    if offices:
        return "parallel_review"
    return "rdco_review"


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
        stage=stage, status="approved", comment=comment,
    )

    if record.pipeline_status == "rdco_intake":
        next_status = _enter_clearance_stage(record)
    elif record.pipeline_status == "adviser_review":
        # Proposals end at 'approved' (visible as ongoing); all other types published at rdco_review
        next_status = "approved" if _type_name(record) == "Proposal" else "published"
    elif record.pipeline_status == "rdco_review":
        next_status = "published"
    else:
        next_status = "published"  # fallback; should never be reached

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
        stage=stage, status="declined", comment=comment,
    )
    record.pipeline_status = "declined"
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
        stage=stage, status="rejected", comment=comment,
    )
    record.pipeline_status = "rejected"
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
    if decision == "approved":
        review_status     = "approved"
        clearance_status  = "cleared"
    elif decision == "rejected":
        review_status     = "rejected"
        clearance_status  = "rejected"
    else:  # declined
        review_status     = "declined"
        clearance_status  = "declined"

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
    if decision in ("declined", "rejected"):
        record.pipeline_status = "rejected" if decision == "rejected" else "declined"
        record.save(update_fields=["pipeline_status", "updated_at"])
        notify_clearance_result(record, review, office=office, advanced=False)
        return review

    # ── ITSO approved at itso_review (Project only) ───────────────────────
    if office == "itso" and record.pipeline_status == "itso_review":
        # IERC begins after ITSO clears -- but only if it was actually
        # requested (ADR-018). Unconditionally creating it here, as before,
        # would force an ethics review nobody asked for.
        if record.requested_ierc:
            RecordClearance.objects.get_or_create(record=record, office="ierc")
        # KTTO may have already cleared, be pending, or never have been
        # requested at all -- _all_clearances_done reflects whichever is true.
        if _all_clearances_done(record):
            record.pipeline_status = "rdco_review"
            record.save(update_fields=["pipeline_status", "updated_at"])
            notify_clearance_result(record, review, office="itso", advanced=True, all_done=True)
        else:
            record.pipeline_status = "parallel_review"
            record.save(update_fields=["pipeline_status", "updated_at"])
            notify_clearance_result(record, review, office="itso", advanced=True)
        return review

    # ── All other approved clearances ─────────────────────────────────────
    if _all_clearances_done(record):
        record.pipeline_status = "rdco_review"
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
    if record.pipeline_status != "declined":
        raise InvalidPipelineTransition(
            "Only records in 'declined' status can be resubmitted."
        )

    # Validate that the owner uploaded something new since the decline
    last_decline = (
        Review.objects.filter(record=record, status="declined")
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

    CLEARANCE_OFFICES = {"itso", "ierc", "ktto"}

    if last_decline and last_decline.stage in CLEARANCE_OFFICES:
        # Smart resubmit: only reset the declining office's clearance
        office = last_decline.stage
        RecordClearance.objects.filter(record=record, office=office).update(
            status="pending", reviewed_by=None, comment=""
        )
        # Route back to the clearance stage this office reviews at
        if office == "itso":
            new_status = "itso_review"
        elif office == "ierc":
            new_status = "parallel_review"
        else:  # ktto — can review at both itso_review (Project) and parallel_review
            itso_pending = RecordClearance.objects.filter(
                record=record, office="itso", status="pending"
            ).exists()
            new_status = "itso_review" if itso_pending else "parallel_review"
    else:
        # Sequential stage decline: full reset, restart from the beginning
        RecordClearance.objects.filter(record=record).delete()
        new_status = _first_status_for_type(record)

    record.pipeline_status = new_status
    record.save(update_fields=["pipeline_status", "updated_at"])
    notify_resubmit(record, submitted_by, new_status=new_status)
    return record
