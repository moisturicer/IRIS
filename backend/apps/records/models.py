from django.db import models
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex


# ---- Reference / lookup tables ------------------------------------------

class Classification(models.Model):
    name = models.CharField(max_length=200, unique=True)
    def __str__(self): return self.name


class PSCEDClassification(models.Model):
    name = models.CharField(max_length=200, unique=True)
    def __str__(self): return self.name


class RecordType(models.Model):
    """Proposal, Thesis/Research, Project."""
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name


class AuthorRole(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name


class PublicationLevel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name


class ConferenceLevel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name


class BudgetType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name


class CollaborationType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name


# ---- Core record --------------------------------------------------------

#: The single definition of "a record any authenticated user may read".
#: Used by the public record list AND by AI retrieval, so a generated citation
#: can never point at a record the reader is not allowed to open.
PUBLICLY_VISIBLE_STATUSES = ("published", "approved", "completed")


class RecordManager(models.Manager):
    """Default queryset excludes soft-deleted records."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def with_deleted(self):
        return super().get_queryset()

    def publicly_visible(self):
        """Records readable by any authenticated user. Keep this the only predicate."""
        return self.get_queryset().filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)


class Record(models.Model):
    PIPELINE_STATUS = [
        ("draft",          "Draft"),
        # Proposal pipeline
        ("adviser_review", "Adviser Review"),          # back-and-forth with adviser until approved
        ("approved",       "Approved"),                # Proposal approved by adviser — visible as ongoing
        ("completed",      "Completed"),               # Proposal research finished — toggled manually by RDCO
        # Thesis/Research and Project pipeline
        ("rdco_intake",    "RDCO Intake Review"),      # RDCO checks completeness; may reject outright
        ("itso_review",     "ITSO Review"),              # Project only: ITSO sequential gate; KTTO also starts here in parallel
        ("parallel_review", "Parallel Office Review"), # T/R: IERC+KTTO; Project: IERC+KTTO after ITSO clears — offices tracked via RecordClearance
        ("rdco_review",     "RDCO Final Review"),      # RDCO consolidates all office clearances
        # Terminal / visible states
        ("published",      "Published"),
        ("declined",       "Declined"),                # revision requested; owner may resubmit
        ("rejected",       "Rejected"),                # terminal rejection; no resubmission
        ("pending_delete", "Pending Deletion"),
    ]

    title              = models.CharField(max_length=500)
    year_accomplished  = models.PositiveIntegerField(null=True, blank=True)
    year_completed     = models.PositiveIntegerField(null=True, blank=True)
    abstract           = models.TextField(blank=True)
    abstract_file      = models.FileField(upload_to="abstracts/", null=True, blank=True)
    classification     = models.ForeignKey(
        Classification, on_delete=models.SET_NULL, null=True, blank=True, related_name="records"
    )
    psced              = models.ForeignKey(
        PSCEDClassification, on_delete=models.SET_NULL, null=True, blank=True, related_name="records"
    )
    record_type        = models.ForeignKey(
        RecordType, on_delete=models.SET_NULL, null=True, blank=True, related_name="records"
    )
    adviser            = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="advised_records"
    )
    added_by           = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True,
        related_name="created_records"
    )

    # IP / tag flags
    is_ip                   = models.BooleanField(default=False)
    for_commercialization   = models.BooleanField(default=False)
    community_extension     = models.BooleanField(default=False)

    # Ethics trigger (ADR-018) -- IERC's SRS-defined scope is human/animal
    # subjects and sensitive data, which none of the flags above cover.
    requires_ethics_review  = models.BooleanField(default=False)

    # Conditional parallel-office routing (ADR-018, Proposed -- extends
    # ADR-002's transition table rather than replacing it). The submitter
    # requests offices here; apps.reviews.services.approve_record() reads
    # these at rdco_intake to decide which RecordClearance rows to create,
    # instead of a hardcoded set per record_type. requested_itso only takes
    # effect for Project -- Thesis/Research never routes through ITSO,
    # matching the structural distinction the type already encodes.
    requested_itso           = models.BooleanField(default=False)
    requested_ierc           = models.BooleanField(default=False)
    requested_ktto           = models.BooleanField(default=False)

    # Structured IP classification type (FR-M5-05)
    IP_TYPE_CHOICES = [
        ("patent",        "Patent"),
        ("copyright",     "Copyright"),
        ("trade_secret",  "Trade Secret"),
        ("utility_model", "Utility Model"),
    ]
    ip_type = models.CharField(
        max_length=20,
        choices=IP_TYPE_CHOICES,
        blank=True,
        default="",
        db_index=True,
        help_text="Specific IP classification set by RDCO/KTTO after final review.",
    )

    # Denormalized pipeline status -- updated by reviews.services on every review action
    pipeline_status = models.CharField(
        max_length=20, choices=PIPELINE_STATUS, default="draft", db_index=True
    )

    # Soft delete
    is_deleted  = models.BooleanField(default=False, db_index=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    deleted_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deleted_records"
    )

    access_count = models.PositiveIntegerField(default=0)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    # PostgreSQL full-text search vector -- updated via post_save signal in services.py
    search_vector = SearchVectorField(null=True, editable=False)

    objects = RecordManager()

    class Meta:
        ordering = ["-created_at"]
        indexes  = [GinIndex(fields=["search_vector"])]

    def __str__(self):
        return self.title[:80]


class RecordOwner(models.Model):
    """
    Many-to-many between Record and User for ownership.
    is_primary replaces the old `representative` text field.
    """
    record     = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="owners")
    user       = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="owned_records")
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ("record", "user")

    def __str__(self):
        tag = " (primary)" if self.is_primary else ""
        return f"{self.user.email} -> {self.record.title[:40]}{tag}"


class ResearchLink(models.Model):
    """Links a Proposal record to its Thesis/Research record."""
    proposal = models.OneToOneField(
        Record, on_delete=models.CASCADE, related_name="linked_thesis"
    )
    thesis   = models.OneToOneField(
        Record, on_delete=models.CASCADE, related_name="linked_proposal"
    )

    def __str__(self):
        return f"Proposal {self.proposal_id} -> Thesis {self.thesis_id}"


# ---- Related record details ----------------------------------------------

class Author(models.Model):
    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="authors")
    name   = models.CharField(max_length=200)
    role   = models.ForeignKey(AuthorRole, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.name


class Publication(models.Model):
    record          = models.OneToOneField(Record, on_delete=models.CASCADE, related_name="publication")
    isbn            = models.CharField(max_length=50, blank=True)
    issn            = models.CharField(max_length=50, blank=True)
    isi             = models.CharField(max_length=50, blank=True)
    year_published  = models.PositiveIntegerField(null=True, blank=True)
    level           = models.ForeignKey(PublicationLevel, on_delete=models.SET_NULL, null=True, blank=True)


class Conference(models.Model):
    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="conferences")
    title  = models.CharField(max_length=300)
    date   = models.DateField(null=True, blank=True)
    venue  = models.CharField(max_length=300, blank=True)
    level  = models.ForeignKey(ConferenceLevel, on_delete=models.SET_NULL, null=True, blank=True)


class Budget(models.Model):
    record          = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="budgets")
    allocation      = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    funding_source  = models.CharField(max_length=300, blank=True)
    budget_type     = models.ForeignKey(BudgetType, on_delete=models.SET_NULL, null=True, blank=True)


class Collaboration(models.Model):
    record         = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="collaborations")
    industry       = models.CharField(max_length=300, blank=True)
    institution    = models.CharField(max_length=300, blank=True)
    collab_type    = models.ForeignKey(CollaborationType, on_delete=models.SET_NULL, null=True, blank=True)


# ---- Download / Delete requests -----------------------------------------

class DownloadRequest(models.Model):
    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("declined", "Declined")]
    record       = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="download_requests")
    requested_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="download_requests")
    status       = models.CharField(max_length=10, choices=STATUS, default="pending")
    reviewed_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_download_requests"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class DeleteRequest(models.Model):
    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("declined", "Declined")]
    record       = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="delete_requests")
    requested_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="delete_requests")
    reason       = models.TextField(blank=True)
    status       = models.CharField(max_length=10, choices=STATUS, default="pending")
    previous_pipeline_status = models.CharField(max_length=20, blank=True, default="")
    reviewed_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_delete_requests"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
