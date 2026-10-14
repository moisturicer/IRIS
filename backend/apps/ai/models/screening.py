"""A reader's remembered screening verdicts (IR-547): derived, never source text."""

from django.conf import settings
from django.db import models


class ScreeningJudgment(models.Model):
    """What the screening model decided about one Record for one reader.

    A derived artifact kept apart from the Record: it holds a decision, the
    verbatim quote that supports it and where the quote was found -- no title,
    abstract or passage. `key` is a digest of everything the decision depended
    on (the Record's content and extraction, the criterion, the model, the
    prompt and schema, and the approval policy), so any change is a different
    key and the old row is simply never found again.

    Rows belong to one reader. A row is a hint, not a grant: whoever reads it
    still has to be allowed to read the Record now, and the quote is checked
    against the Record as it is now.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    record = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="+")
    key = models.CharField(max_length=64)
    state = models.CharField(max_length=16)
    quote = models.TextField(blank=True)
    source = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="one_screening_judgment_per_reader_key"),
        ]
        indexes = [models.Index(fields=["user", "record"], name="screening_judgment_user_record")]
