"""A versioned, on-demand paper reading (IR-556)."""

import uuid

from django.conf import settings
from django.db import models


class PaperBrief(models.Model):
    record = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="paper_briefs")
    chunk_set = models.ForeignKey("ai.ChunkSet", on_delete=models.CASCADE)
    content_hash = models.CharField(max_length=64)
    prompt_version = models.PositiveSmallIntegerField()
    profile_hash = models.CharField(max_length=64)
    model_id = models.CharField(max_length=200, blank=True)
    models_used = models.JSONField(default=list)
    state = models.CharField(max_length=16, default="generating")
    reason = models.CharField(max_length=48, blank=True)
    fields = models.JSONField(default=dict)
    section_briefs = models.JSONField(default=list)
    claim = models.UUIDField(default=uuid.uuid4)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    started_at = models.DateTimeField(null=True)
    usage = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["record", "content_hash", "prompt_version", "profile_hash"],
            name="unique_paper_brief_version",
        )]
