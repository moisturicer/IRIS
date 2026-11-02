"""Django owns committed work; AI owns receipts (IR-737, ADR-049)."""
import uuid

from django.db import models


class ManuscriptWork(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey("records.Record", on_delete=models.CASCADE)
    revision = models.UUIDField(editable=False)
    source_file = models.TextField()
    operation = models.CharField(max_length=32, default="local_extraction")
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True)
    grant_token = models.TextField(default="", editable=False)
    grant_expires_at = models.DateTimeField(null=True, editable=False)
    authority_generation = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["record"], condition=models.Q(revoked_at=None),
            name="one_current_manuscript_work",
        ), models.UniqueConstraint(fields=["record", "revision", "operation"],
                                   name="unique_manuscript_work_revision")]


class ManuscriptInvalidation(models.Model):
    """Non-content cleanup facts survive the institutional Record's deletion."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record_id = models.BigIntegerField()
    work_id = models.UUIDField()
    reason = models.CharField(max_length=32)
    authority_generation = models.PositiveBigIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["work_id", "authority_generation", "reason"],
                                               name="unique_manuscript_invalidation")]
