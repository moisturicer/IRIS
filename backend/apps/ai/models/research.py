"""Private research-run telemetry. Content belongs in Turns, never here (IR-512)."""

import uuid

from django.conf import settings
from django.db import models


class ResearchRunQuerySet(models.QuerySet):
    def owned_by(self, user):
        return self.filter(user=user)


class ResearchRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    conversation = models.ForeignKey(
        "ai.Conversation", null=True, blank=True, on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=24, default="running")
    stop_reason = models.CharField(max_length=48, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    prompt_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    validation_codes = models.JSONField(default=list)

    objects = ResearchRunQuerySet.as_manager()


class ResearchStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ResearchRun, related_name="steps", on_delete=models.CASCADE)
    position = models.PositiveIntegerField()
    kind = models.CharField(max_length=16)
    tool = models.CharField(max_length=32, blank=True)
    argument_digest = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=24)
    duplicate = models.BooleanField(default=False)
    latency_ms = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(null=True)
    output_tokens = models.PositiveIntegerField(null=True)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["run", "position"], name="research_step_position")]
