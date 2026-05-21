from django.utils import timezone
from core.exceptions import InvalidPipelineTransition, RecordAlreadyApproved
from .models import Review
from apps.records.models import Record
from apps.notifications.services import notify_record_reviewed


# Maps pipeline_status to which stage a review at that status creates
_STAGE_MAP = {
    "adviser_review": "adviser",
    "ktto_review":    "ktto",
    "rdco_review":    "rdco",
}

# After approval at each stage, advance to this next status
_ADVANCE_MAP = {
    "adviser": "ktto_review",
    "ktto":    "rdco_review",
    "rdco":    "published",
}

# On decline at any stage, set this status
_DECLINE_STATUS = "declined"


def approve_record(record: Record, reviewed_by, comment: str = "") -> Review:
    """
    Create an approval Review and advance the record's pipeline_status.
    Raises InvalidPipelineTransition if the record is not at a reviewable stage.
    """
    stage = _STAGE_MAP.get(record.pipeline_status)
    if not stage:
        raise InvalidPipelineTransition(
            f"Record is at '{record.pipeline_status}' -- cannot approve."
        )

    review = Review.objects.create(
        record=record,
        reviewed_by=reviewed_by,
        stage=stage,
        status="approved",
        comment=comment,
    )

    record.pipeline_status = _ADVANCE_MAP[stage]
    record.save(update_fields=["pipeline_status", "updated_at"])

    # TODO: call notify_record_reviewed(record, review) once notifications.services is wired up

    return review


def decline_record(record: Record, reviewed_by, comment: str = "") -> Review:
    """
    Create a declined Review and set the record's pipeline_status to 'declined'.
    """
    stage = _STAGE_MAP.get(record.pipeline_status)
    if not stage:
        raise InvalidPipelineTransition(
            f"Record is at '{record.pipeline_status}' -- cannot decline."
        )

    review = Review.objects.create(
        record=record,
        reviewed_by=reviewed_by,
        stage=stage,
        status="declined",
        comment=comment,
    )

    record.pipeline_status = _DECLINE_STATUS
    record.save(update_fields=["pipeline_status", "updated_at"])

    # TODO: call notify_record_reviewed(record, review)

    return review


def resubmit_record(record: Record, submitted_by) -> Record:
    """
    Revert a declined record back to the stage where it was last declined.
    Only the record owner can call this.
    """
    if record.pipeline_status != "declined":
        raise InvalidPipelineTransition("Only declined records can be resubmitted.")

    # Find the last decline to know which stage to revert to
    last_decline = (
        Review.objects.filter(record=record, status="declined")
        .order_by("-created_at")
        .first()
    )

    if last_decline:
        revert_to = f"{last_decline.stage}_review"
    else:
        revert_to = "adviser_review"  # fallback

    record.pipeline_status = revert_to
    record.save(update_fields=["pipeline_status", "updated_at"])

    # TODO: create a notification to the relevant reviewer role

    return record
