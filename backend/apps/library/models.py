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
from django.db.models.functions import Lower

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


#: How many saved feeds one account may hold (IR-577). One constant, so changing
#: the decision is one edit; the interface reads the number from the API.
MAX_SAVED_FEEDS = 10


class SavedFeed(models.Model):
    """
    A reader's private custom feed: Discover's own query, saved under a name
    (IR-577, IR-557 user stories 15-17).

    `query` holds exactly the keys Discover writes into its URL (`q`, `type`,
    `college`, `classification`, `year`, `ip`, `sort`), spelt the way Discover
    spells them, so opening a feed is navigating to Discover with that query
    and there is no second filter representation. `apps/library/feeds.py`
    validates it on the way in and reports values the taxonomy has since lost;
    nothing here rewrites them, because dropping one would silently widen the
    feed.

    Owner-only: every queryset starts from `owner=request.user`, so another
    reader's feed cannot be addressed. Kept until its owner deletes it or the
    account is removed (the foreign key cascades); there is no expiry. The name
    is unique per account ignoring case, which the database enforces.

    Like `SavedRecord`, it is not in Django admin and writes no `AuditEvent`.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_feeds"
    )
    name = models.CharField(max_length=60)
    query = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("name"), "owner", name="unique_saved_feed_name"),
        ]

    def __str__(self):
        return f"SavedFeed(owner={self.owner_id}, name={self.name!r})"
