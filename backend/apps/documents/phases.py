"""PDF processing phases; a reader's saved-paper status is a separate vocabulary."""
from django.db import models


class ExtractionPhase(models.TextChoices):
    QUEUED = "queued", "Queued"
    READING = "reading", "Reading PDF"
    RETRYING = "retrying", "Retrying"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
    AWAITING_SUBMISSION = "awaiting_submission", "Awaiting submission"
    # IR-850: the Extractor leaves campus and the disclosure gate refuses.
    AWAITING_DISCLOSURE = "awaiting_disclosure", "Not read: awaiting consent or release"
