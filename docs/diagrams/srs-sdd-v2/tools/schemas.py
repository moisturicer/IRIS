"""E-*: schema extracts for SDD v2 §3 ("6. Schema" in v1), generated from the models.

Each lists the tables a feature reads or writes. gen_v2.schema() draws them
from section-d/tools/models.json (run extract_models.py first), with every key
and up to four other fields, the same rules as the full ERDs D-8 to D-15. The
AI runtime's own schema is D-14 in full.
"""


def fig(fid, sec, name, models, fmt="portrait"):
    return {"title": f"E-{fid}  Schema: {name}", "caption": f"SDD v2 §{sec}.", "models": models, "format": fmt}


FIGURES = {
    "E-1.1-accounts": fig("1.1", "3.1.1–3.1.4", "accounts, notice and recovery", [
        "accounts.User", "accounts.Role", "accounts.DataNotice", "accounts.NoticeAnswer",
        "accounts.RecoveryToken", "accounts.RecoveryIntent", "accounts.UserSession"]),
    "E-1.5-roles": fig("1.5", "3.1.5–3.1.7", "roles, requests, deletion and settings", [
        "accounts.User", "accounts.Role", "accounts.RoleRequest", "accounts.AccountDeletionRequest", "accounts.SystemSetting"]),
    "E-2.1-records": fig("2.1", "3.2.1, 3.2.4", "records and Versions", [
        "records.Record", "records.RecordOwner", "records.RecordType", "records.RecordVersion",
        "records.RecordVersionDocument", "records.ReviewText", "records.Author"], "landscape"),
    "E-2.2-documents": fig("2.2", "3.2.2, 3.2.3", "requirements and uploads", [
        "documents.UploadSlot", "documents.RecordUpload", "documents.RecordFile", "documents.AdviserTemplate",
        "records.RecordType"]),
    "E-2.5-requests": fig("2.5", "3.2.5, 3.2.6", "download and delete requests", [
        "records.Record", "records.DownloadRequest", "records.DeleteRequest"]),
    "E-3.1-workflow": fig("3.1", "3.3.1–3.3.4", "assignments, Seats, clearances and revision requests", [
        "reviews.RecordAssignment", "reviews.ReviewerSeat", "reviews.RecordClearance", "reviews.ResubmissionRequest",
        "reviews.Review", "reviews.RoutingEvent", "records.RecordVersion"], "landscape"),
    "E-3.5-doc-requests": fig("3.5", "3.3.5", "document requests", [
        "documents.DocumentRequest", "documents.DocumentRequestItem", "documents.UploadSlot", "documents.RecordUpload",
        "reviews.RecordAssignment"]),
    "E-3.6-threads": fig("3.6", "3.3.6", "review threads", [
        "reviews.ReviewComment", "reviews.ThreadPlace", "reviews.ReviewThreadEvent", "reviews.ReviewMention",
        "reviews.SavedReply"]),
    "E-3.7-deadlines": fig("3.7", "3.3.7", "turnaround", [
        "reviews.RecordAssignment", "reviews.Turnaround", "reviews.Holiday", "reviews.Extension", "reviews.DeadlineMoment"]),
    "E-3.8-embargo": fig("3.8", "3.3.8, 3.5.3", "IP and embargo", ["records.Record", "records.EmbargoReminder"]),
    "E-4.1-notifications": fig("4.1", "3.4.1", "notifications", [
        "notifications.Notification", "notifications.NotificationType", "notifications.NotificationRead"]),
    "E-5.1-extraction": fig("5.1", "3.5.1", "extraction", [
        "documents.PdfExtraction", "documents.ExtractionFigure", "documents.RecordUpload"]),
    "E-5.2-indexing": fig("5.2", "3.5.2", "chunks and vectors", [
        "ai.ChunkSet", "ai.DocumentChunk", "ai.ChunkEmbedding", "ai.EmbeddingSpace", "ai.RecordSpaceEmbedding"]),
    "E-5.6-overview": fig("5.6", "3.5.6, 3.5.8", "overviews, briefs and index jobs", [
        "ai.RecordOverview", "ai.PaperBrief", "ai.EmbeddingJob"]),
    "E-6.1-library": fig("6.1", "3.6.1–3.6.3", "the reader's library", [
        "library.SavedRecord", "library.LibraryFolder", "library.FolderMembership", "library.ReadingNote",
        "library.ReadingHighlight", "library.ReadingPosition", "library.ReadingVisit"], "landscape"),
    "E-6.4-calls": fig("6.4", "3.6.4", "Calls & Conferences", ["opportunities.Opportunity", "opportunities.SavedCall"]),
    "E-6.5-discovery": fig("6.5", "3.6.5", "personal discovery", [
        "records.DiscoveryInterests", "records.DiscoveryDismissal", "records.DiscoveryFeedSnapshot"]),
    "E-7.1-audit": fig("7.1", "3.7.1–3.7.3", "audit and settings", ["audit.AuditEvent", "accounts.SystemSetting"]),
}
