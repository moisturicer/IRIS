from django.db import models
from django.utils import timezone

from core.enums import ASSIGNABLE_PARTIES, DocumentRequestItemState, DocumentRequestState


class UploadSlot(models.Model):
    """
    Defines what kind of document a record type requires.
    E.g. "Proposal" record type might require "Ethical Clearance", "Concept Paper", etc.
    Seed these via a data migration.

    `record` is set only on an **ad-hoc** slot: one made for a document request's
    free-text "Other" item (ADR-022 §3), so the file still belongs to a slot
    rather than being a loose `RecordFile`. An ad-hoc slot is that record's
    alone and is never on its type's list.
    """
    name        = models.CharField(max_length=200)
    record_type = models.ForeignKey(
        "records.RecordType", on_delete=models.CASCADE, related_name="upload_slots"
    )
    is_required = models.BooleanField(default=True)
    record      = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, null=True, blank=True,
        related_name="adhoc_slots",
    )

    def __str__(self):
        return f"{self.record_type.name} | {self.name}"


class UploadStatus(models.Model):
    """Seed: Pending, For Application, Reviewed, Filed, Disapproved, Approved."""
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name


class RecordUpload(models.Model):
    """
    A versioned file uploaded to a specific UploadSlot for a Record.
    Each new upload to the same slot auto-increments the version number.
    """
    record      = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="uploads")
    slot        = models.ForeignKey(UploadSlot, on_delete=models.CASCADE, related_name="uploads")
    file        = models.FileField(upload_to="documents/")
    version     = models.PositiveIntegerField(default=1)
    status      = models.ForeignKey(
        UploadStatus, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploads"
    )
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="uploaded_documents"
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        # Version is auto-set in documents.services -- do not set manually
        unique_together = ("record", "slot", "version")

    def __str__(self):
        return f"{self.record_id} | {self.slot.name} v{self.version}"


class UploadReview(models.Model):
    """
    A reviewer's comment + status change on a specific RecordUpload version.
    Replaces CheckedUpload.
    """
    upload      = models.ForeignKey(RecordUpload, on_delete=models.CASCADE, related_name="reviews")
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="document_reviews"
    )
    status      = models.ForeignKey(
        UploadStatus, on_delete=models.SET_NULL, null=True, related_name="upload_reviews"
    )
    comment     = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review of upload {self.upload_id} by {self.reviewed_by_id}"


class DocumentKind(models.TextChoices):
    """What kind of document an extraction holds — the RAG corpus boundary.

    [ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) §Decision
    ("Retrieval scope," amended 2026-09-08) draws this as a document-*type*
    distinction, explicitly not an endpoint one: whatever feeds the chunker
    "must key off 'is this the manuscript,' not off which upload path was
    used to attach the file."

    It lives here rather than in ``core.enums`` for the reason that module's
    own "What is not here" note gives about ``PdfExtraction.STATUS``: this is
    ingestion-pipeline vocabulary, and shares no value with the workflow's.
    """

    MANUSCRIPT = "manuscript", "Manuscript"
    SUPPLEMENTARY = "supplementary", "Supplementary"


class PdfExtraction(models.Model):
    """
    Tracks the Celery PDF text-extraction task for either a RecordUpload
    (a supplementary document) or a Record's manuscript directly.
    Created immediately when a PDF is submitted; updated by the background task.

    ``structure`` is the document the chunker consumes: element kinds,
    headings, table rows, and the page and bounding-box data a citation is
    highlighted from. Flattening at extraction is irreversible — coordinates
    cannot be recovered by matching chunk text back against a PDF — so
    ``structure`` is persisted alongside ``extracted_text`` rather than
    derived from it later.

    Exactly one of ``upload``/``record`` is set (IR-195, ADR-013's
    2026-09-08 amendment): a supplementary upload has no manuscript to be
    confused with, and the manuscript has no UploadSlot to hang off. Two
    nullable one-to-ones plus a check constraint, rather than a polymorphic
    "owner" field, because the two carry different files and are written by
    different triggers.

    **Which FK is set is not what decides whether this is chunked** (IR-239).
    ``kind`` is, and it is stored rather than derived precisely so that the
    answer survives a path that does not exist yet — a manuscript attached
    through an ``UploadSlot``, say. Deriving it from ``record_id is not None``
    would re-encode the endpoint coincidence ADR-013's amendment blames for
    the original defect.
    """
    STATUS = [
        ("queued",  "Queued"),
        ("running", "Running"),
        ("done",    "Done"),
        ("failed",  "Failed"),
    ]
    upload         = models.OneToOneField(
        RecordUpload, on_delete=models.CASCADE, related_name="pdf_extraction",
        null=True, blank=True,
    )
    record         = models.OneToOneField(
        "records.Record", on_delete=models.CASCADE, related_name="manuscript_extraction",
        null=True, blank=True,
    )
    status         = models.CharField(max_length=10, choices=STATUS, default="queued", db_index=True)
    # The RAG corpus boundary, stored on the row the chunker reads (IR-239).
    # Defaults to SUPPLEMENTARY so the failure mode is closed: a row whose
    # creator forgot to say what it holds is left out of the corpus rather
    # than quietly indexed into it. Both production creation sites set it
    # explicitly anyway -- the default is the backstop, not the mechanism.
    kind           = models.CharField(
        max_length=16,
        choices=DocumentKind.choices,
        default=DocumentKind.SUPPLEMENTARY,
        db_index=True,
    )
    extracted_text = models.TextField(blank=True)
    # The serialized NormalizedDocument -- see apps.ai.extraction.serialization
    # for the format, and as_normalized_document() below for the way back.
    structure      = models.JSONField(default=dict, blank=True)
    # Ties a ChunkSet to the extraction it was derived from, so re-running
    # ingestion on an unchanged document is a hash comparison rather than a
    # re-chunk. Indexed because that comparison is the lookup.
    content_hash   = models.CharField(max_length=64, blank=True, db_index=True)
    # Which extractor produced the result. One value today; recorded anyway,
    # so the question is answerable from the row rather than from its date.
    extractor      = models.CharField(max_length=32, blank=True)
    celery_task_id = models.CharField(max_length=200, blank=True)
    error          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    completed_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(upload__isnull=False, record__isnull=True)
                    | models.Q(upload__isnull=True, record__isnull=False)
                ),
                name="pdfextraction_exactly_one_of_upload_or_record",
            ),
        ]

    def __str__(self):
        return f"PdfExtraction upload={self.upload_id} record={self.record_id} status={self.status}"

    @property
    def resolved_record_id(self):
        """The record this extraction belongs to, however it got here."""
        return self.upload.record_id if self.upload_id else self.record_id

    def as_normalized_document(self):
        """The stored structure as the document the chunker consumes, or
        ``None`` for a row that has not extracted successfully.

        The import is local because ``apps.documents`` has no other reason to
        depend on ``apps.ai``, and ingestion is the one direction that
        dependency may ever run.
        """
        if not self.structure:
            return None
        from apps.ai.extraction import document_from_json

        return document_from_json(self.structure)


class RecordFile(models.Model):
    """
    Direct file attachment to a record (not tied to an UploadSlot).
    Used for miscellaneous files the owner wants to attach.
    """
    record      = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="files")
    file        = models.FileField(upload_to="record_files/")
    filename    = models.CharField(max_length=300)
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="record_files"
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename


# ---------------------------------------------------------------------------
# Document requests (ADR-022, IR-262)
#
# A reviewer asking the owner for specific documents without a resubmission.
# Like ADR-021's tables, nothing deletes from these: a request changes `state`
# and the row is the history. The record's `awaiting_document` state is derived
# from open rows here and never stored.
# ---------------------------------------------------------------------------

class DocumentRequest(models.Model):
    """One party asking the owner for documents. ADR-022 §1."""

    record       = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="document_requests"
    )
    #: The assignment the request was made under. `party` is stored as well,
    #: because the assignment may close while the request is still open.
    assignment   = models.ForeignKey(
        "reviews.RecordAssignment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="document_requests",
    )
    party        = models.CharField(
        max_length=20, choices=[(p.value, p.label) for p in ASSIGNABLE_PARTIES]
    )
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="document_requests_made",
    )
    #: Why, shown to the owner as written. Plain text, never markup.
    message      = models.TextField()
    state        = models.CharField(
        max_length=20, choices=DocumentRequestState.choices,
        default=DocumentRequestState.OPEN,
    )
    created_at   = models.DateTimeField(default=timezone.now)
    closed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["record", "created_at", "pk"]
        indexes  = [models.Index(fields=["record", "state"])]

    def __str__(self):
        return f"Record {self.record_id} | {self.party} | {self.state}"


class DocumentRequestItem(models.Model):
    """One document asked for. ADR-022 §1."""

    request    = models.ForeignKey(
        DocumentRequest, on_delete=models.CASCADE, related_name="items"
    )
    #: Chosen from the picklist. Null for a free-text "Other" item.
    slot       = models.ForeignKey(
        UploadSlot, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="request_items",
    )
    #: `slot.name` for a picklist item, the reviewer's words for "Other".
    label      = models.CharField(max_length=200)
    #: The upload that answered it. `SET_NULL`: deleting a file version must
    #: not delete the record that it was asked for.
    upload     = models.ForeignKey(
        RecordUpload, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="request_items",
    )
    state      = models.CharField(
        max_length=20, choices=DocumentRequestItemState.choices,
        default=DocumentRequestItemState.MISSING,
    )
    sort_order = models.PositiveIntegerField(default=0)
    #: The requesting party's reason, the last time it rejected an upload
    #: (ADR-022 §3.4, IR-263). The item itself goes back to `missing`, so this
    #: is what tells the owner why. Plain text, never markup.
    rejection_reason = models.TextField(blank=True, default="")
    #: When the requesting party last accepted or rejected an upload.
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["request", "sort_order", "pk"]

    def __str__(self):
        return f"Request {self.request_id} | {self.label} | {self.state}"
