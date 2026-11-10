"""
What an account deletion does to every row that points at a `User` (ADR-051 §11, IR-785).

The `User` row is kept, so nothing here cascades by itself: each relation is
declared as kept, deleted or anonymized, with the reason. `test_account_deletion`
fails when a model gains a relation to `User` that isn't declared, so a new
feature can't silently keep a deleted person's private data.

- **KEEP**: the row stays and still points at the kept account, which now reads
  "Former user". History, shared work and audit facts are kept.
- **DELETE**: the row is the person's own private data and is deleted, optionally
  only where `where` matches (for example, only *pending* requests).
- **ANONYMIZE**: the row stays but the link is changed; `service.confirm` does it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.enums import RequestStatus

KEEP = "keep"
DELETE = "delete"
ANONYMIZE = "anonymize"


@dataclass(frozen=True)
class Rule:
    action: str
    why: str
    #: For DELETE: only rows matching these lookups go.
    where: dict = field(default_factory=dict)


PENDING = {"status": RequestStatus.PENDING}

#: `app_label.Model.field` -> what deletion does with it.
RELATIONS: dict[str, Rule] = {
    # --- accounts
    "accounts.StudentProfile.user":   Rule(DELETE, "Student profile: personal details"),
    "accounts.UserInterest.user":     Rule(DELETE, "The person's research-interest tags (IR-695); a tag nobody uses is then deleted"),
    "accounts.AdviserProfile.user":   Rule(DELETE, "Adviser profile: personal details"),
    "accounts.RoleRequest.user":      Rule(DELETE, "A pending role request is withdrawn; decided ones are history", PENDING),
    "accounts.RoleRequest.reviewed_by": Rule(KEEP, "Who decided someone else's request"),
    "accounts.SystemSetting.updated_by": Rule(KEEP, "Who last changed a setting"),
    "accounts.DataNotice.published_by": Rule(KEEP, "Who published a notice version"),
    "accounts.NoticeAnswer.user":     Rule(KEEP, "Consent history: each answer is kept with its version and time (ADR-054 decision 3)"),
    "accounts.UserSession.user":      Rule(KEEP, "Ended sign-in history, needed to refuse its tokens"),
    "accounts.RecoveryToken.user":    Rule(DELETE, "Unused recovery links"),
    "accounts.RecoveryIntent.user":   Rule(DELETE, "Pending recovery emails"),
    "accounts.AccountDeletionRequest.user": Rule(KEEP, "The request itself is the record of the deletion"),
    "accounts.AccountDeletionRequest.decided_by": Rule(KEEP, "Who decided someone else's request"),
    "accounts.User_groups.user":      Rule(DELETE, "Django permission groups"),
    "accounts.User_user_permissions.user": Rule(DELETE, "Django permissions"),
    "token_blacklist.OutstandingToken.user": Rule(KEEP, "Issued tokens, all blacklisted on deletion"),
    "admin.LogEntry.user":            Rule(KEEP, "Django admin's own change history"),
    "audit.AuditEvent.user":          Rule(KEEP, "Audit rows are insert-only and unchanged (ADR-051 §11)"),
    # --- records
    "records.DiscoveryInterests.user":    Rule(DELETE, "Private discovery interests"),
    "records.DiscoveryDismissal.user":    Rule(DELETE, "Private discovery dismissals"),
    "records.DiscoveryFeedSnapshot.user": Rule(DELETE, "Private feed snapshots"),
    "records.Record.adviser":         Rule(ANONYMIZE, "On a published paper the name is kept as text and the link cleared"),
    "records.Record.added_by":        Rule(KEEP, "Who added a paper"),
    "records.Record.dpa_accepted_by": Rule(KEEP, "Who accepted the agreement on a paper"),
    "records.Record.embargo_date_set_by": Rule(KEEP, "Who set an embargo date"),
    "records.Record.embargo_released_by": Rule(KEEP, "Who released an embargo"),
    "records.Record.ip_released_by":  Rule(KEEP, "Who released the IP mark"),
    "records.Record.deleted_by":      Rule(KEEP, "Who deleted a paper"),
    "records.UnlistedPublication.published_by": Rule(KEEP, "Who published a paper from Unlisted"),
    "records.RecordVersion.created_by": Rule(KEEP, "Who submitted a version"),
    "records.RecordOwner.user":       Rule(KEEP, "Ownership history; sole-owner drafts are deleted and the Contact person passes on"),
    "records.DownloadRequest.requested_by": Rule(DELETE, "A pending download request is withdrawn", PENDING),
    "records.DownloadRequest.reviewed_by":  Rule(KEEP, "Who decided someone else's request"),
    "records.DownloadRequest.revoked_by":   Rule(KEEP, "Who revoked someone else's grant"),
    "records.DeleteRequest.requested_by":   Rule(KEEP, "A paper's deletion request concerns the paper, not the person"),
    "records.DeleteRequest.reviewed_by":    Rule(KEEP, "Who decided someone else's request"),
    # --- reviews and documents: who reviewed what is history (ADR-051 §11)
    "reviews.Review.reviewed_by":           Rule(KEEP, "Review history"),
    "reviews.RecordClearance.reviewed_by":  Rule(KEEP, "Review history"),
    "reviews.RecordAssignment.opened_by":   Rule(KEEP, "Review history"),
    "reviews.RecordAssignment.closed_by":   Rule(KEEP, "Review history"),
    "reviews.Extension.actor":              Rule(KEEP, "Review history"),
    "reviews.ReviewerSeat.reviewer":        Rule(KEEP, "Review history; open seats block deletion"),
    "reviews.ReviewerSeat.assigned_by":     Rule(KEEP, "Review history"),
    "reviews.RoutingEvent.actor":           Rule(KEEP, "Review history"),
    "reviews.ResubmissionRequest.requested_by": Rule(KEEP, "Review history"),
    "reviews.ResubmissionRequest.resolved_by":  Rule(KEEP, "Review history"),
    "reviews.ReviewComment.author":         Rule(KEEP, "Comments show \"Former user\""),
    "reviews.ReviewComment.resolved_by":    Rule(KEEP, "Review history"),
    "reviews.ReviewComment.answered_by":    Rule(KEEP, "Review history"),
    "reviews.ReviewRound.actor":            Rule(KEEP, "Review history"),
    "reviews.ReviewThreadEvent.actor":      Rule(KEEP, "Review history"),
    "documents.RecordUpload.uploaded_by":   Rule(KEEP, "A paper's files belong to the paper"),
    "documents.UploadReview.reviewed_by":   Rule(KEEP, "Review history"),
    "documents.RecordFile.uploaded_by":     Rule(KEEP, "A paper's files belong to the paper"),
    "documents.DocumentRequest.requested_by": Rule(KEEP, "Review history"),
    # --- notifications
    "notifications.Notification.sender":    Rule(KEEP, "A notice someone else received"),
    "notifications.Notification.recipient": Rule(DELETE, "The person's own notifications"),
    "notifications.NotificationRead.user":  Rule(DELETE, "The person's own read marks"),
    # --- Ask IRIS and AI (the AI runtime's own Conversations: `ai.runs.purge`)
    "ai.Conversation.user":      Rule(DELETE, "Ask IRIS conversations"),
    "ai.AskRun.user":            Rule(DELETE, "Queued Ask IRIS questions"),
    "ai.ResearchRun.user":       Rule(DELETE, "Research runs"),
    "ai.ScreeningJudgment.user": Rule(DELETE, "The person's cached screening verdicts"),
    "ai.PaperBrief.requested_by": Rule(KEEP, "A paper's AI Overview is shared, not the person's"),
    # --- other features
    "opportunities.Opportunity.posted_by": Rule(KEEP, "A Call's Posted by shows \"Former user\""),
    "library.SavedRecord.owner":           Rule(DELETE, "Saved papers and reading status"),
    "library.SavedFeed.owner":             Rule(DELETE, "Private custom feeds (IR-577)"),
    "reviews.SavedReply.owner":            Rule(DELETE, "Private saved review replies (IR-877)"),
    "reviews.ViewedMark.user":             Rule(DELETE, "Private Viewed marks in a comparison (IR-877)"),
    "reviews.ReviewMention.user":          Rule(DELETE, "Mentions of the person in review comments (IR-877)"),
}


def label(model, field_name: str) -> str:
    return f"{model._meta.app_label}.{model.__name__}.{field_name}"


def user_relations():
    """Every (model, field name) that points at `User`, hidden relations included."""
    from django.contrib.auth import get_user_model

    for rel in get_user_model()._meta.get_fields(include_hidden=True):
        if rel.is_relation and rel.auto_created and not rel.concrete:
            yield rel.related_model, rel.field.name
