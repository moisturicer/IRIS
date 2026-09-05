"""
Research opportunities with deadlines -- internal calls, conference deadlines,
funding windows and institutional grants.

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
    """A dated, outbound-linked call published by a CIT-U office."""

    # How long a closed opportunity stays greyed out on the board before it
    # drops off entirely.
    HIDE_AFTER_CLOSE = timedelta(days=30)

    TYPE_INTERNAL_CALL       = "internal_call"
    TYPE_CONFERENCE_DEADLINE = "conference_deadline"
    TYPE_FUNDING_WINDOW      = "funding_window"
    TYPE_INSTITUTIONAL_GRANT = "institutional_grant"
    TYPE_CHOICES = [
        (TYPE_INTERNAL_CALL,       "Internal Call"),
        (TYPE_CONFERENCE_DEADLINE, "Conference Deadline"),
        (TYPE_FUNDING_WINDOW,      "Funding Window"),
        (TYPE_INSTITUTIONAL_GRANT, "Institutional Grant"),
    ]

    # `source` exists so an externally-found call (DOST, CHED) is attributed as
    # external rather than looking like CIT-U published it. Nothing in IRIS
    # scrapes anything -- a staff member types these in. See IR-121.
    SOURCE_INTERNAL = "internal"
    SOURCE_EXTERNAL = "external"
    SOURCE_CHOICES = [
        (SOURCE_INTERNAL, "Internal"),
        (SOURCE_EXTERNAL, "External"),
    ]

    opportunity_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    title            = models.CharField(max_length=300)
    posting_office   = models.CharField(max_length=200)
    # Free text, exactly as the mockup has it ("Engineering, Computing & Allied
    # Sciences Faculty"). Deliberately NOT structured: reliable audience
    # targeting needs data this system does not have, and half-targeting is
    # worse than none. It is display copy, not a routing key.
    audience         = models.CharField(max_length=300, blank=True)
    description      = models.TextField(blank=True)
    # Only meaningful for grants and funding windows; a conference deadline has
    # no ceiling, so null is a real value here rather than a missing one.
    funding_ceiling  = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    external_url     = models.URLField(max_length=500, blank=True)
    due_date         = models.DateField()
    is_featured      = models.BooleanField(default=False)
    tags             = models.JSONField(default=list, blank=True)
    source           = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_INTERNAL)
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

    def __str__(self):
        return f"{self.get_opportunity_type_display()}: {self.title[:60]}"

    def days_left(self, today=None):
        """Whole days until the deadline. Negative once it has passed."""
        return (self.due_date - (today or date.today())).days

    def is_closed(self, today=None):
        return self.days_left(today) < 0
