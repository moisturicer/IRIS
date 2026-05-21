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

class RecordManager(models.Manager):
    """Default queryset excludes soft-deleted records."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def with_deleted(self):
        return super().get_queryset()


class Record(models.Model):
    PIPELINE_STATUS = [
        ("draft",          "Draft"),
        ("adviser_review", "Adviser Review"),
        ("ktto_review",    "KTTO / TBI Review"),
        ("rdco_review",    "RDCO Review"),
        ("published",      "Published"),
        ("declined",       "Declined"),
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

    # IP / tag flags -- kept as booleans since they are fixed and only 3
    is_ip                   = models.BooleanField(default=False)
    for_commercialization   = models.BooleanField(default=False)
    community_extension     = models.BooleanField(default=False)

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
        return f"{self.user.username} -> {self.record.title[:40]}{tag}"


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
    reviewed_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_delete_requests"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
