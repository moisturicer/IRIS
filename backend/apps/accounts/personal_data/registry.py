"""
Which models the personal-data export covers, declared one by one (IR-786).

**Why this exists.** The download is only as complete as its last update. A
model added later that holds a person's data would silently fall out of it, so
`test_personal_data_export.py` fails until the model is declared here, in one
of two dicts:

* `INCLUDED` -- model label to the export section that carries it. The section
  must exist in `export.SECTIONS`.
* `EXCLUDED` -- model label to the reason it is left out. A reason is a
  sentence, never a placeholder.

**What counts as a personal-data model.** `personal_data_models()` finds every
model with a relation to the user model, then every model that cascades from
one of those, repeatedly. The second step is what catches a Turn (it cascades
from a Conversation, and has no user column of its own).

ADR-051 names the other half of this rule: a deletion must also know what it
removes. That declaration is IR-794's; this one covers the download only.
"""

from __future__ import annotations

from django.apps import apps
from django.conf import settings
from django.db import models

# -- included: model -> export section ---------------------------------------

INCLUDED: dict[str, str] = {
    "accounts.User": "account",
    "accounts.StudentProfile": "account",
    "accounts.AdviserProfile": "account",
    "accounts.RoleRequest": "account",
    "accounts.UserInterest": "account",
    "accounts.NoticeAnswer": "consent",
    "accounts.UserSession": "sessions",
    "records.RecordOwner": "papers_owned",
    "records.Record": "papers_owned",
    "records.Author": "papers_owned",
    "records.Publication": "papers_owned",
    "records.Conference": "papers_owned",
    "records.ResearchLink": "papers_owned",
    "records.RecordVersion": "papers_owned",
    "records.RecordVersionDocument": "papers_owned",
    "documents.UploadSlot": "papers_owned",
    "documents.RecordFile": "papers_owned",
    "documents.RecordUpload": "papers_owned",
    "library.SavedRecord": "saved_papers",
    "library.SavedFeed": "saved_feeds",
    "records.DiscoveryInterests": "discovery",
    "records.DiscoveryDismissal": "discovery",
    "ai.Conversation": "conversations",
    "ai.Turn": "conversations",
    "ai.TurnCitation": "conversations",
    "records.DownloadRequest": "download_requests",
    "records.DeleteRequest": "delete_requests",
    "notifications.Notification": "notifications",
    "notifications.NotificationRead": "notifications",
    "opportunities.Opportunity": "opportunities_posted",
    "reviews.Review": "workflow_acts",
    "reviews.ReviewComment": "workflow_acts",
    "reviews.ReviewRound": "workflow_acts",
    "reviews.RecordClearance": "workflow_acts",
    "reviews.ResubmissionRequest": "workflow_acts",
    "reviews.RoutingEvent": "workflow_acts",
    "documents.UploadReview": "workflow_acts",
    "documents.DocumentRequest": "workflow_acts",
    "documents.DocumentRequestItem": "workflow_acts",
}

# -- excluded: model -> why --------------------------------------------------

_CREDENTIAL = "A credential or the record of one: never exported (ADR-051 decision 13)."
_PAPER_DERIVED = (
    "Made by the system from a paper's text (an index, vector, extraction or summary). "
    "The paper's own details are exported, and this holds nothing the person wrote."
)
_AI_MECHANICS = (
    "Operational record of how an Ask IRIS answer was produced. What the person asked "
    "and was answered is exported with the Conversation's Turns."
)
_WORKFLOW_MECHANICS = (
    "Scheduling or routing mechanics. The person appears only as the actor, and the "
    "matching act is in the Audit Log, which this download does not include."
)

EXCLUDED: dict[str, str] = {
    "accounts.RecoveryIntent": _CREDENTIAL,
    "accounts.RecoveryToken": _CREDENTIAL,
    "token_blacklist.OutstandingToken": _CREDENTIAL,
    "token_blacklist.BlacklistedToken": _CREDENTIAL,
    "publication.ManuscriptWork": (
        "A download grant for a paper's file, holding a grant token: a credential, and the "
        "file itself is the paper."
    ),
    "accounts.DataNotice": (
        "A published version of the data notice: one text for the whole system, the same for "
        "everyone. The person appears only as its publisher. What a person answered to each "
        "version is exported as their consent history."
    ),
    "accounts.SystemSetting": (
        "System configuration. The person appears only as its last editor, which is a fact "
        "about the setting rather than about them."
    ),
    "admin.LogEntry": (
        "Django's own admin history, reachable by a Django superuser only. The Audit Log is "
        "the record of what a person did."
    ),
    "audit.AuditEvent": (
        "The Audit Log is the System Admin's record of acts. Its rows can name other people "
        "(a role change, a review), so it is not handed out as the person's own data. The "
        "export itself is audited here."
    ),
    "ai.AskRun": _AI_MECHANICS,
    "ai.AskRunAttempt": _AI_MECHANICS,
    "ai.AskRunEvent": _AI_MECHANICS,
    "ai.ChatSubmission": _AI_MECHANICS,
    "ai.ConversationState": _AI_MECHANICS,
    "ai.ResearchRun": _AI_MECHANICS,
    "ai.ResearchStep": _AI_MECHANICS,
    "ai.ShadowEvidenceDecision": _AI_MECHANICS,
    "ai.TurnEmbedding": "A vector computed from a Turn's text. The text is exported.",
    "ai.ScreeningJudgment": (
        "A cache of the system's verdict on whether a paper fits a question, holding a quote "
        "from the paper rather than anything the person wrote."
    ),
    "ai.PaperBrief": _PAPER_DERIVED,
    "ai.RecordOverview": _PAPER_DERIVED,
    "ai.RecordEmbedding": _PAPER_DERIVED,
    "ai.RecordSpaceEmbedding": _PAPER_DERIVED,
    "ai.ChunkSet": _PAPER_DERIVED,
    "ai.DocumentChunk": _PAPER_DERIVED,
    "ai.ChunkEmbedding": _PAPER_DERIVED,
    "ai.EmbeddingJob": _PAPER_DERIVED,
    "ai.IngestionJob": _PAPER_DERIVED,
    "documents.PdfExtraction": _PAPER_DERIVED,
    "documents.ExtractionFigure": _PAPER_DERIVED,
    "documents.ManuscriptMetadata": _PAPER_DERIVED,
    "records.DiscoveryFeedSnapshot": (
        "A frozen ordering of the catalogue for one reader, rebuilt on demand. The reader's "
        "choices are exported as Discovery interests and dismissals."
    ),
    "records.EmbargoReminder": "A scheduler's bookkeeping for reminder emails; it holds no content.",
    "reviews.RecordAssignment": _WORKFLOW_MECHANICS,
    "reviews.ReviewerSeat": _WORKFLOW_MECHANICS,
    "reviews.Extension": _WORKFLOW_MECHANICS,
    "reviews.DeadlineMoment": _WORKFLOW_MECHANICS,
    "reviews.ReviewThreadEvent": (
        "The change history of a review thread (severity, resolved, reopened, answered). The "
        "person appears only as the actor; the thread text they wrote is exported with their "
        "review comments."
    ),
    "records.ReviewText": _PAPER_DERIVED,
    "records.ReviewTextSection": _PAPER_DERIVED,
}


# -- discovery ----------------------------------------------------------------

def _relates_to(model: type[models.Model], target: type[models.Model], *, cascading_only: bool) -> bool:
    for field in model._meta.concrete_fields:
        if not (field.is_relation and field.related_model is target):
            continue
        if cascading_only and getattr(field.remote_field, "on_delete", None) is not models.CASCADE:
            continue
        return True
    return False


def personal_data_models() -> set[str]:
    """Labels of every model the export must account for.

    A model counts when it points at the user model by any foreign key, or
    cascades from a model that does. Nothing is hand-listed, so a model added
    next month appears here without anyone remembering to add it.
    """
    user_model = apps.get_model(settings.AUTH_USER_MODEL)
    every = [m for m in apps.get_models() if m is not user_model]
    found = {user_model}
    found |= {m for m in every if _relates_to(m, user_model, cascading_only=False)}
    frontier = list(found)
    while frontier:
        parent = frontier.pop()
        for model in every:
            if model not in found and _relates_to(model, parent, cascading_only=True):
                found.add(model)
                frontier.append(model)
    return {model._meta.label for model in found}


def undeclared(declared_included=None, declared_excluded=None) -> set[str]:
    """Models the export must account for that neither dict names."""
    included = INCLUDED if declared_included is None else declared_included
    excluded = EXCLUDED if declared_excluded is None else declared_excluded
    return personal_data_models() - set(included) - set(excluded)
