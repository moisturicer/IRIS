"""
A reader's private research library (ADR-044).

`apps/records` owns institutional workflow and `apps/documents` owns uploaded
files; neither is the place for what one reader keeps for themselves. Later
slices (IR-572 folders, IR-573 positions, IR-580 notes, IR-756 history) add to
this app.

**Nothing here is registered in Django admin, and nothing writes an
`AuditEvent`.** A library is private to its reader (ADR-044 §3).
"""

from django.conf import settings
from django.db import models

from core.enums import ReadingStatus


class SavedRecord(models.Model):
    """
    One Record one reader saved, with at most one reading status (ADR-044 §2).

    Unique on `(owner, record)`, so a Record is saved at most once per reader;
    the single nullable `reading_status` gives "at most one status" with no
    extra check. Setting a status saves the Record, and unsaving deletes the
    row, which clears its status with it.

    Both foreign keys cascade: removing an account removes its library, and a
    deleted Record vanishes from every library. A withdrawn or restricted one
    stays, and is listed as unavailable (ADR-044 §4).
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_records"
    )
    record = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="+"
    )
    reading_status = models.CharField(
        max_length=16, choices=ReadingStatus.choices, null=True, blank=True
    )
    saved_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "record"], name="unique_saved_record"),
        ]
        indexes = [models.Index(fields=["owner", "-saved_at"], name="library_saved_owner_idx")]

    def __str__(self):
        return f"SavedRecord(owner={self.owner_id}, record={self.record_id})"
