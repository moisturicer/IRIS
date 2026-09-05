from django.db import models


class UploadSlot(models.Model):
    """
    Defines what kind of document a record type requires.
    E.g. "Proposal" record type might require "Ethical Clearance", "Concept Paper", etc.
    Seed these via a data migration.
    """
    name        = models.CharField(max_length=200)
    record_type = models.ForeignKey(
        "records.RecordType", on_delete=models.CASCADE, related_name="upload_slots"
    )
    is_required = models.BooleanField(default=True)

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


class PdfExtraction(models.Model):
    """
    Tracks the Celery PDF text-extraction task for a RecordUpload.
    Created immediately when a PDF is submitted; updated by the background task.

    Two outputs, not one (IR-107 / ADR-013 / ADR-016).  ``extracted_text`` is
    the flat string ``Record.search_vector`` indexes, and it keeps working
    exactly as it did.  ``structure`` is the document the chunker consumes:
    element kinds, headings, table rows, and the page and bounding-box data a
    citation is highlighted from.  Flattening at extraction is irreversible —
    coordinates cannot be recovered by matching chunk text back against a PDF
    — so both are persisted, and the flat one is derived from the structured
    one rather than extracted separately.
    """
    STATUS = [
        ("queued",  "Queued"),
        ("running", "Running"),
        ("done",    "Done"),
        ("failed",  "Failed"),
    ]
    upload         = models.OneToOneField(
        RecordUpload, on_delete=models.CASCADE, related_name="pdf_extraction"
    )
    status         = models.CharField(max_length=10, choices=STATUS, default="queued", db_index=True)
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

    def __str__(self):
        return f"PdfExtraction upload={self.upload_id} status={self.status}"

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
