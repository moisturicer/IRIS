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
