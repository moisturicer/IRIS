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
from django.conf import settings
from django.db import models
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from core.enums import CallEventState, CallPapersState, CallStatus
from core.permissions import is_call_moderator


class OpportunityQuerySet(models.QuerySet):
    def visible_to(self, user):
        """
        The Calls `user` may open (ADR-050 decision 8): every confirmed Call,
        plus their own in any status; RDCO sees all. Anything else is filtered
        out, so the API answers it exactly like a missing Call (404).
        """
        if is_call_moderator(user):
            return self
        return self.filter(models.Q(status=CallStatus.CONFIRMED) | models.Q(posted_by=user))

    def waiting(self, today=None):
        """
        Waiting for RDCO's decision: pending, with its paper deadline not yet
        passed. The same rule as `Opportunity.is_waiting`.
        """
        return self.filter(
            status=CallStatus.PENDING, due_date__gte=today or timezone.localdate(),
        )

    def lapsed(self, today=None):
        """
        Pending or rejected Calls whose paper deadline has passed: they have left
        RDCO's queue, and the daily job deletes them (decision 9, amended).
        """
        return self.filter(
            status__in=(CallStatus.PENDING, CallStatus.REJECTED),
            due_date__lt=today or timezone.localdate(),
        )

    def on_board(self, today=None):
        """What the board lists: confirmed Calls that aren't Over."""
        return self.filter(status=CallStatus.CONFIRMED).not_over(today)

    def not_over(self, today=None):
        """
        The Calls the board lists: every one not yet Over (ADR-050 decision 7).

        The same rule as `Opportunity.is_over`, in SQL: a Call stays through
        the latest of its deadline, start and end dates. A Call whose deadline
        has passed stays, marked Submissions closed, until its event is over.
        """
        today = today or timezone.localdate()
        last_day = Greatest(
            "due_date",
            Coalesce("start_date", "due_date"),
            Coalesce("end_date", "due_date"),
        )
        return self.alias(last_day=last_day).filter(last_day__gte=today)


class Opportunity(models.Model):
    """A call for papers, posted in IRIS by RDCO or an Adviser (ADR-050)."""

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
    # ADR-050 decision 8 (IR-762). Pending by default, so a Call saved by any
    # path that forgets to decide stays off the board rather than going public
    # unchecked. The view confirms RDCO's own at once.
    status           = models.CharField(
        max_length=16, choices=CallStatus.choices, default=CallStatus.PENDING,
    )
    # RDCO's reason for rejecting it; cleared when the Adviser resubmits.
    review_reason    = models.TextField(blank=True)
    # When RDCO last confirmed or rejected it. Who did is IR-763's audit event.
    reviewed_at      = models.DateTimeField(null=True, blank=True)
    posted_by        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="posted_opportunities",
    )
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    objects = OpportunityQuerySet.as_manager()

    class Meta:
        # Soonest deadline first: the board's job is "what closes next", not
        # "what was posted last". Featured doesn't move a Call (ADR-050
        # decision 12, IR-762); it only adds a star and a label.
        ordering = ["due_date", "id"]
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
        return (self.due_date - (today or timezone.localdate())).days

    def is_closed(self, today=None):
        return self.days_left(today) < 0

    # ADR-050 decisions 6 and 7 (IR-761). Every rule takes "today" so a test can
    # pass the day in; left out, it is Manila's date, not the machine's.

    def last_day(self):
        """The latest date entered. A Call is Over the day after it."""
        return max(d for d in (self.due_date, self.start_date, self.end_date) if d)

    def is_over(self, today=None):
        return (today or timezone.localdate()) > self.last_day()

    def papers_state(self, today=None):
        if (today or timezone.localdate()) <= self.due_date:
            return CallPapersState.ACCEPTING
        return CallPapersState.CLOSED

    def has_event(self):
        return bool(self.start_date or self.end_date)

    def event_state(self, today=None):
        """
        Upcoming, Happening now or Over; None for a Call with no event dates
        until the Call itself is Over.

        An event is over the day after its last date, even while a later paper
        deadline keeps the Call on the board (owner, 2026-11-15). An end date
        with no start is never Happening now (owner, 2026-11-15).
        """
        today = today or timezone.localdate()
        if not self.has_event():
            return CallEventState.OVER if self.is_over(today) else None
        if self.start_date:
            if today < self.start_date:
                return CallEventState.UPCOMING
            if today <= max(self.start_date, self.end_date or self.start_date):
                return CallEventState.HAPPENING
        elif today <= self.end_date:
            return CallEventState.UPCOMING
        return CallEventState.OVER

    #: An event's Over, worded so it reads beside "Accepting papers" (owner,
    #: 2026-11-15). A Call with no event reads plain "Over".
    EVENT_OVER_LABEL = "Event over"

    def papers_label(self, today=None):
        return self.papers_state(today).label

    def event_label(self, today=None):
        state = self.event_state(today)
        if state is None:
            return None
        if state == CallEventState.OVER and self.has_event():
            return self.EVENT_OVER_LABEL
        return state.label

    def is_waiting(self, today=None):
        """
        Waiting for RDCO's decision: pending, with its paper deadline not yet
        passed. A lapsed request has left RDCO's queue and is deleted by the
        daily job (decision 9, as amended), so it can't be decided either.
        """
        return self.status == CallStatus.PENDING and self.due_date >= (today or timezone.localdate())

    def posted_by_adviser(self):
        """
        Was this posted by someone other than RDCO, whose account still exists?
        Then RDCO removing it needs a reason they receive (ADR-050 decision 11,
        owner 2026-11-15). Read from the poster's role today.
        """
        return self.posted_by is not None and not is_call_moderator(self.posted_by)

    def poster_name(self):
        """Posted by: the poster's account name (decision 3), or "" once they are gone."""
        if not self.posted_by:
            return ""
        return self.posted_by.get_full_name() or self.posted_by.email
