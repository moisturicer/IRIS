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


#: The longest note body, in characters (ADR-064 §4). The editor's own copy is
#: `MAX_NOTE_LENGTH` in `useReadingNote.ts`: change both together.
MAX_NOTE_LENGTH = 20_000


class ReadingNote(models.Model):
    """
    One reader's private note on one Record (IR-580, ADR-064).

    `revision` is what makes two devices safe: a write names the revision it
    started from and is refused, with the server's text, if the note has moved
    on, so no save silently replaces another. A note has no quotation of the
    paper in it, only what the reader typed.

    Unique on `(owner, record)`. Both foreign keys cascade: removing an account
    removes its notes and a deleted Record removes the notes on it. A Record
    that is merely withdrawn or restricted keeps them (the retention rule,
    ADR-064 §6); they are unreachable until access returns, because every
    endpoint rechecks `Record.objects.visible_to()`.

    Not in Django admin, no `AuditEvent`, and never imported by anything that
    recommends, discusses, reviews or prompts (a guard test enforces it).
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_notes"
    )
    record = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="+"
    )
    body = models.TextField(blank=True, default="")
    #: 1 on the first save; the API treats "no note yet" as revision 0.
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "record"], name="unique_reading_note"),
        ]

    def __str__(self):
        return f"ReadingNote(owner={self.owner_id}, record={self.record_id})"


#: What a highlight's quotation, its surrounding text and its regions may hold
#: (ADR-065 §3). They are the review threads' own bounds (`reviews.comments`),
#: because the same selection code produces both.
MAX_HIGHLIGHT_QUOTE = 2_000
MAX_HIGHLIGHT_CONTEXT = 500
MAX_HIGHLIGHT_REGIONS = 50


class ReadingHighlight(models.Model):
    """
    A passage one reader saved from a Manuscript (IR-583, ADR-065).

    **It belongs to the bytes it was made on.** `manuscript_revision` and
    `manuscript_sha256` are the identity the server was serving that reader when
    the highlight was saved (`records.versions.served_manuscript_identity`), and
    they never change. The regions are fractions of pages of *those* bytes, so a
    highlight is current only while the reader is served exactly that identity;
    after a replacement it is stale, and nothing here rewrites it to point at the
    new file.

    The reader's own words about a paper are `ReadingNote.body`. A highlight
    holds source text only -- the quotation, a little context either side, the
    page and the regions -- so the two are never mixed (ADR-065 §1).

    Both foreign keys cascade, as for notes (ADR-064 §1). A Record that is merely
    withdrawn or restricted keeps its highlights; they are withheld, quote and
    anchor together, until access returns, because every presentation rechecks
    `Record.objects.visible_to()`.

    Not in Django admin, no `AuditEvent`, and never imported by anything that
    recommends, discusses, reviews or prompts (a guard test enforces it).
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_highlights"
    )
    record = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="+"
    )
    manuscript_revision = models.UUIDField()
    manuscript_sha256 = models.CharField(max_length=64)
    page = models.PositiveIntegerField()
    quote = models.TextField()
    prefix = models.TextField(blank=True, default="")
    suffix = models.TextField(blank=True, default="")
    #: ADR-031's page-fraction rectangles, `{page, left, top, right, bottom}`.
    regions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "record", "-created_at"], name="library_highlight_idx")]

    def __str__(self):
        return f"ReadingHighlight(owner={self.owner_id}, record={self.record_id})"


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
