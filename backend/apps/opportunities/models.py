"""
Calls for papers -- conferences, congresses, symposia, workshops, journals and
book chapters (ADR-050).

Deliberately a separate app rather than a home inside apps.records (IR-121):
an Opportunity shares no workflow, clearance or ownership semantics with a
Record, and burying it in the app that carries the thesis contribution would
muddy it. A separate app is also cleanly deletable if the pilot cuts this.

The name is `Opportunity`, not `Conference`, because records.Conference already
exists and means something else entirely -- a FK on Record recording "this paper
was presented at X". Reusing that name would be actively confusing.
"""
from datetime import date, timedelta

from django.conf import settings
from django.db import models


class OpportunityQuerySet(models.QuerySet):
    def visible(self, today=None):
        """
        What a browser should see.

        Past-deadline items do not vanish the moment they close -- someone
        mid-application needs to still find the page they were reading. They
        grey out as "Closed" in place (see `is_closed`) and only drop off the
        board once they are stale enough that nobody is still acting on them.
        """
        today = today or date.today()
        return self.filter(due_date__gte=today - Opportunity.HIDE_AFTER_CLOSE)


class Opportunity(models.Model):
    """A call for papers, posted in IRIS by RDCO or an Adviser (ADR-050)."""

    # How long a closed opportunity stays greyed out on the board before it
    # drops off entirely. IR-761 replaces this with the Over rule (decision 7).
    HIDE_AFTER_CLOSE = timedelta(days=30)

    # ADR-050 decision 2. Grants, funding windows and internal CIT-U calls are
    # off the board (decision 1); migration 0002 deleted them, each with a copy
    # in a CALL_DELETED audit event (decision 16).
    TYPE_CONFERENCE   = "conference"
    TYPE_CONGRESS     = "congress"
    TYPE_SYMPOSIUM    = "symposium"
    TYPE_WORKSHOP     = "workshop"
    TYPE_JOURNAL      = "journal"
    TYPE_BOOK_CHAPTER = "book_chapter"
    TYPE_CHOICES = [
        (TYPE_CONFERENCE,   "Conference"),
        (TYPE_CONGRESS,     "Congress"),
        (TYPE_SYMPOSIUM,    "Symposium"),
        (TYPE_WORKSHOP,     "Workshop"),
        (TYPE_JOURNAL,      "Journal"),
        (TYPE_BOOK_CHAPTER, "Book Chapter"),
    ]
    # A journal issue or a book has no event (decision 4), so a Call of these
    # types stores no start or end date: `save` clears both.
    TYPES_WITHOUT_EVENT = frozenset({TYPE_JOURNAL, TYPE_BOOK_CHAPTER})

    opportunity_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    title            = models.CharField(max_length=300)
    # "About" on screen.
    description      = models.TextField(blank=True)
    # "Link" on screen.
    external_url     = models.URLField(max_length=500, blank=True)
    # The paper deadline.
    due_date         = models.DateField()
    # About, location, Areas and link are required by the serializer, not
    # here: a Conference Deadline migrated by 0002 may lack them until it is
    # next saved (decision 16).
    location         = models.CharField(max_length=300, blank=True)
    areas            = models.ManyToManyField(
        "records.Classification", blank=True, related_name="calls",
    )
    start_date       = models.DateField(null=True, blank=True)
    end_date         = models.DateField(null=True, blank=True)
    # Free text: fees are often tiered or in another currency (decision 3).
    registration_fee = models.CharField(max_length=200, blank=True)
    is_featured      = models.BooleanField(default=False)
    posted_by        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="posted_opportunities",
    )
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    objects = OpportunityQuerySet.as_manager()

    class Meta:
        # Featured first, then soonest deadline: the board's job is "what closes
        # next", not "what was posted last".
        ordering = ["-is_featured", "due_date"]
        verbose_name_plural = "opportunities"
        indexes = [models.Index(fields=["due_date"])]

    def save(self, *args, **kwargs):
        if self.opportunity_type in self.TYPES_WITHOUT_EVENT:
            self.start_date = None
            self.end_date = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_opportunity_type_display()}: {self.title[:60]}"

    def days_left(self, today=None):
        """Whole days until the deadline. Negative once it has passed."""
        return (self.due_date - (today or date.today())).days

    def is_closed(self, today=None):
        return self.days_left(today) < 0

    def poster_name(self):
        """Posted by: the poster's account name (decision 3), or "" once they are gone."""
        if not self.posted_by:
            return ""
        return self.posted_by.get_full_name() or self.posted_by.email
