import uuid
from pathlib import Path

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

# Re-exported deliberately: PUBLICLY_VISIBLE_STATUSES now lives in core.enums
# beside the vocabulary it is built from, but `apps.records.models` has been its
# import site since IR-152 and callers (including IR-153's visibility predicate)
# reach for it here. Keeping the name importable from both places costs one line
# and avoids a rename that has nothing to do with this ticket.
from core.enums import (  # noqa: F401
    PUBLICLY_VISIBLE_STATUSES,
    CommentDeletion,
    EmbargoState,
    IPType,
    PipelineStatus,
    RequestStatus,
    ReviewTextState,
    VersionCause,
)


# ---- Reference / lookup tables ------------------------------------------

class Classification(models.Model):
    name = models.CharField(max_length=200, unique=True)
    def __str__(self): return self.name


class PSCEDClassification(models.Model):
    name = models.CharField(max_length=200, unique=True)
    def __str__(self): return self.name


class DiscoveryInterests(models.Model):
    """A reader's optional, private catalogue Areas."""

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="discovery_interests"
    )
    classifications = models.ManyToManyField(Classification, blank=True)
    psced = models.ManyToManyField(PSCEDClassification, blank=True)
    revision = models.PositiveBigIntegerField(default=0)


class DiscoveryDismissal(models.Model):
    """A reader's "Not interested" in one Record, private to them (IR-576)."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="discovery_dismissals"
    )
    record = models.ForeignKey("Record", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "record"], name="unique_discovery_dismissal"),
        ]


class DiscoveryFeedSnapshot(models.Model):
    """Frozen ordering for one reader; Record access is checked again on every page."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="discovery_feed_snapshots"
    )
    interest_revision = models.PositiveBigIntegerField()
    recipe_version = models.PositiveSmallIntegerField(default=1)
    mode = models.CharField(max_length=12)
    entries = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


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


def abstract_file_path(instance, filename: str) -> str:
    # Ignores the filename beyond its extension -- a long title overflowed
    # the old max_length here (IR-422); a random name sidesteps that.
    ext = Path(filename).suffix.lower()
    return f"abstracts/{uuid.uuid4().hex}{ext}"


# ---- Core record --------------------------------------------------------

#: The single definition of "a record any authenticated user may read" now lives
#: in `core.enums` and is re-exported at the top of this module. Used by the
#: public record list AND by AI retrieval, so a generated citation can never
#: point at a record the reader is not allowed to open.


class RecordManager(models.Manager):
    """Default queryset excludes soft-deleted records."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def with_deleted(self):
        return super().get_queryset()

    def publicly_visible(self):
        """Records readable by any authenticated user. Keep this the only predicate."""
        return self.get_queryset().filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)

    def visible_to(self, user):
        """
        Every record `user` is entitled to read. The one read-visibility
        predicate (IR-153) -- `RecordViewSet` applies it on every action, and AI
        retrieval must filter through it too, so a generated citation can never
        point at a record the reader cannot open.

        Four disjoint grounds, in the order they matter:

        * **Office staff** (KTTO/RDCO/ITSO/IERC) see everything. They run the
          clearance pipeline; RDCO cannot perform intake review on a record it
          cannot open.
        * **Owners** see their own records at any pipeline status, which is what
          makes a draft readable to the person writing it.
        * **The assigned adviser** sees the record they advise. `Adviser` is in
          `REVIEWER_ROLES` but deliberately not in `STAFF_ROLES`, so the role
          alone grants nothing -- the grant is the `adviser` FK pointing at this
          user. Without this, every record would be unreachable by the person
          it enters review with (ADR-032 §1).
        * **Anyone authenticated** sees the public catalogue.

        Anonymous users get nothing; DRF refuses them before this runs, but a
        predicate that quietly returned the public catalogue to `AnonymousUser`
        would be a trap for the next caller that reuses it outside a view.

        Wider than `publicly_visible()` and narrower than the bare manager. The
        `distinct()` is required because the owner clause joins through
        `RecordOwner`, which can match a record more than once.
        """
        from core.permissions import STAFF_ROLES, get_role_name

        qs = self.get_queryset()
        if not user or not user.is_authenticated:
            return qs.none()
        if get_role_name(user) in STAFF_ROLES:
            return qs
        return qs.filter(
            models.Q(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
            | models.Q(owners__user=user)
            | models.Q(adviser=user)
        ).distinct()


class Record(models.Model):
    class Origin(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        INSTITUTIONAL = "institutional", "Institutional"
        IMPORTED_REFERENCE = "imported_reference", "Imported reference"
        SYNTHETIC = "synthetic", "Synthetic"

    #: Kept as a class attribute for callers that reach for
    #: `Record.PIPELINE_STATUS`; the values themselves are `core.enums`
    #: (IR-135). The per-status commentary that used to live here is on
    #: `PipelineStatus` now, beside the values it explains.
    PIPELINE_STATUS = PipelineStatus.choices

    title              = models.CharField(max_length=500)
    origin             = models.CharField(max_length=24, choices=Origin.choices, default=Origin.UNKNOWN)
    publication_year   = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(9999)])
    year_accomplished  = models.PositiveIntegerField(null=True, blank=True)
    year_completed     = models.PositiveIntegerField(null=True, blank=True)
    abstract           = models.TextField(blank=True)
    abstract_file      = models.FileField(
        upload_to=abstract_file_path, max_length=255, null=True, blank=True
    )
    manuscript_revision = models.UUIDField(null=True, blank=True, editable=False)
    manuscript_sha256 = models.CharField(max_length=64, blank=True, editable=False, db_index=True)
    manuscript_filename = models.CharField(max_length=255, blank=True, editable=False)
    duplicate_acknowledgement = models.CharField(max_length=64, blank=True, editable=False)
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
    #: The Adviser's name as plain text, kept when their account is deleted
    #: while this paper is published (ADR-051 §11, IR-785). `adviser` is then
    #: cleared, so the name links to nobody. Blank on every other paper.
    adviser_name       = models.CharField(max_length=250, blank=True, default="")
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

    # The submitter's hint of which offices the record needs (ADR-018). Under
    # ADR-032 the Adviser routes: `apps.reviews.routing` shows these flags to
    # the router as hints, and they route nothing by themselves (§3).
    requested_itso           = models.BooleanField(default=False)
    requested_ierc           = models.BooleanField(default=False)
    requested_ktto           = models.BooleanField(default=False)

    # Structured IP classification type (FR-M5-05)
    IP_TYPE_CHOICES = IPType.choices
    ip_type = models.CharField(
        max_length=20,
        choices=IPType.choices,
        blank=True,
        default="",
        db_index=True,
        help_text="Specific IP classification set by RDCO/KTTO after final review.",
    )

    # Where the record is: draft, in review, or a Decision's outcome (ADR-032).
    # Who holds a record in review is its active assignments, not this value.
    pipeline_status = models.CharField(
        max_length=20, choices=PipelineStatus.choices,
        default=PipelineStatus.DRAFT, db_index=True
    )

    # Resubmission history (IR-139). Both are maintained by
    # reviews.new_version and exist because neither can be derived
    # after the fact: a decline's timestamp is when the reviewer decided, not
    # when the owner resubmitted, and the gap between them is exactly the window
    # in which a clearance is either preserved or re-granted. Serializing
    # `preserved` from a decline timestamp would call a re-granted clearance
    # preserved whenever an office happened to clear before the decline landed.
    resubmission_count   = models.PositiveIntegerField(default=0)
    last_resubmitted_at  = models.DateTimeField(null=True, blank=True)
    # When a detail field last actually changed (IR-273), stamped by
    # `RecordWriteSerializer.update`. A new version answers a revision request
    # only if something changed since the request; `updated_at` cannot say
    # that, because every workflow save moves it too. The manuscript is not a
    # detail: a new one is told apart by the file a version names.
    details_edited_at    = models.DateTimeField(null=True, blank=True)
    # Moved by every detail save (IR-833), so a save made from an older view of
    # the draft can be refused instead of overwriting a newer one. A
    # manuscript alone does not move it: the file is not a detail.
    details_revision     = models.PositiveIntegerField(default=0)
    # The author's decision about each field Publish can fill in from the PDF
    # (IR-833): which it filled in, and which the author typed, accepted,
    # cleared or dismissed. Validated by `RecordWriteSerializer`; owners only.
    metadata_sources     = models.JSONField(default=dict, blank=True)

    # Data Privacy Act consent, per disclosure (IR-226, FR-M6-02). Stamped by
    # `RecordViewSet.submit`, and for test data by `seed_demo` and
    # `corpus_clearance` -- neither field is writable
    # through a serializer, because a consent record the subject can set on
    # themselves through the ordinary update path is not evidence of anything.
    #
    # **The timestamp's presence is the acceptance.** There is deliberately no
    # accompanying boolean: two fields encoding one fact can disagree, and the
    # disagreement would surface exactly when someone needs to prove consent.
    #
    # `User.consent_given` is a different fact and stays where it is -- it
    # records that this person accepted the terms once, at signup (FR-M6-06).
    # This records that *this disclosure* was submitted under them, which is
    # what the wizard's step-3 gate has always claimed to collect and, until
    # now, only ever enforced in the browser.
    dpa_accepted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When DPA consent was accepted for this disclosure. Null means never.",
    )
    dpa_accepted_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dpa_accepted_records",
        help_text="Who accepted. SET_NULL so a deleted account cannot erase the timestamp.",
    )

    @property
    def dpa_accepted(self) -> bool:
        """Whether this disclosure carries DPA consent.

        Derived, never stored, so it cannot drift from the timestamp it
        describes. Serializers expose this; nothing writes it.

        **Legacy since IR-791 (ADR-054 decision 17):** nothing reads this for a
        decision any more. The disclosure gate reads `ai_consent`.
        """
        return self.dpa_accepted_at is not None

    # The Contact person's answer to "may AI use my papers?", copied onto the
    # paper when its draft is created (ADR-054 decisions 9, 10; IR-791). It is
    # what the disclosure gate reads (`apps.ai.policy.records`).
    #
    # **Keeps the answer it started with.** Nothing ever copies a person's later
    # answer onto it, and changing the Contact person doesn't either. The only
    # writers are `apps.records.ai_answer.store_on_new_draft` (creation) and
    # `apps.accounts.ai_answer.change_ai_answer`, which turns a No into a Yes for
    # a person's own papers when they choose "all my papers" (decision 13).
    # Co-owners' answers never count. No serializer can write it.
    #
    # **Null is "no answer stored", and the gate refuses it** -- a paper with no
    # Contact person, one made by an import, or one older than IR-791.
    ai_consent = models.BooleanField(
        null=True, blank=True,
        help_text="The Contact person's AI answer when this draft was created. Null means none stored; the gate refuses it.",
    )

    # The paper's embargo (ADR-052, embargoed by default as amended for IR-882).
    # Its own fact: separate from status, IP and consent, because a published
    # paper can still be under an agreement. Stamped by `apps.records.embargo`
    # and by nothing else; none of these is writable through a serializer.
    #
    # **Every paper starts embargoed.** Only a release by the Adviser or RDCO
    # clears `is_embargoed`, so a code path that forgets to stamp anything
    # leaves the paper blocked, never open.
    is_embargoed = models.BooleanField(
        default=True,
        help_text="True until the Adviser or RDCO releases it. Only a released paper reaches the AI or can be published.",
    )
    embargoed_until = models.DateField(
        null=True, blank=True,
        help_text="The date to review the embargo. A reminder: it never ends the embargo.",
    )
    # Renamed from the answer stamps by `records/0032` in Django only: the columns
    # keep their old names, which `publication`'s SQL functions read.
    embargo_date_set_at = models.DateTimeField(
        null=True, blank=True, db_column="embargo_answered_at",
        help_text="When the review date was last set. Null when no date was ever set.",
    )
    embargo_date_set_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        db_column="embargo_answered_by_id",
        related_name="embargo_dated_records",
        help_text="Who set the date. SET_NULL so a deleted account cannot erase the timestamp.",
    )
    embargo_released_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When a person released the embargo. Null while it is embargoed.",
    )
    embargo_released_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="embargo_released_records",
        help_text="Who released it. SET_NULL so a deleted account cannot erase the timestamp.",
    )

    @property
    def embargo_state(self) -> EmbargoState:
        """Where the embargo stands (ADR-052 §3 as amended for IR-882).

        Derived from `is_embargoed`, and it reads no clock: a passed date stays
        `ACTIVE` until a person releases it (§9).
        """
        return EmbargoState.ACTIVE if self.is_embargoed else EmbargoState.RELEASED

    # KTTO's release of an IP mark (ADR-052 §11-13, IR-813). The mark stays on
    # the paper, and this is what opens the disclosure check for it. Stamped by
    # `apps.records.ip_release` and nothing else. A release can't outlive its
    # mark (the constraint below), so a paper marked again starts unreleased.
    ip_released_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When KTTO released the IP mark for the AI. Null means it has not been released.",
    )
    ip_released_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ip_released_records",
        help_text="Who released it. SET_NULL so a deleted account cannot erase the timestamp.",
    )

    @property
    def ip_released(self) -> bool:
        return self.ip_released_at is not None

    # Soft delete
    is_deleted  = models.BooleanField(default=False, db_index=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    deleted_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deleted_records"
    )

    # Lineage (ADR-032 §6, IR-417): the accepted Proposal this Thesis or
    # Project continues. Written once, by `continuation.continue_proposal`,
    # and never through a serializer. One continuation per Proposal, including
    # a soft-deleted child, is enforced by the constraint below.
    derived_from = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="continuations",
    )
    keywords = models.JSONField(default=list, blank=True)

    access_count = models.PositiveIntegerField(default=0)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    # PostgreSQL full-text search vector -- updated via post_save signal in services.py
    search_vector = SearchVectorField(null=True, editable=False)

    objects = RecordManager()

    class Meta:
        ordering = ["-created_at"]
        indexes  = [GinIndex(fields=["search_vector"])]
        constraints = [
            models.UniqueConstraint(
                fields=["derived_from"],
                name="record_one_continuation",
            ),
            # A release is stamped exactly when the paper is not embargoed, and a
            # date always says who set it (ADR-052, IR-882).
            models.CheckConstraint(
                condition=(
                    models.Q(is_embargoed=True, embargo_released_at__isnull=True)
                    | models.Q(is_embargoed=False, embargo_released_at__isnull=False)
                ),
                name="record_embargo_release_matches_state",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(embargoed_until__isnull=True)
                    | models.Q(embargo_date_set_at__isnull=False)
                ),
                name="record_embargo_date_says_when_set",
            ),
            models.CheckConstraint(
                condition=models.Q(ip_released_at__isnull=True) | models.Q(is_ip=True),
                name="record_ip_release_needs_mark",
            ),
        ]

    def __str__(self):
        return self.title[:80]


class RecordVersion(models.Model):
    """
    A numbered snapshot of what a record put in front of its reviewers
    (ADR-032 §5, as amended 2026-10-08 for IR-416).

    v1 is written when the record is first submitted, and each resubmission
    writes the next. Every write goes through `apps.records.versions`, which
    numbers them.

    **`manuscript` names the stored manuscript file; it is not an FK.** The
    manuscript is `Record.abstract_file`, one field replaced in place, not a
    `RecordUpload`. A new upload is stored under a fresh random name
    (`abstract_file_path`), so it never touches the file an earlier version
    names. Nothing may delete a file a version still names;
    `test_record_versions.py` pins that. Null when the record was submitted
    with no manuscript, which the server has never refused.

    `created_at` has a default rather than `auto_now_add` so the backfill
    (`records/0015`) can date a version it reconstructs. `created_by` is null
    where nobody is recorded: imported, seeded and corpus records, and
    backfilled revisions.
    """

    record     = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="versions")
    number     = models.PositiveIntegerField()
    manuscript = models.FileField(
        upload_to=abstract_file_path, max_length=255, null=True, blank=True,
    )
    manuscript_revision = models.UUIDField(null=True, blank=True, editable=False)
    manuscript_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    manuscript_filename = models.CharField(max_length=255, blank=True, editable=False)
    cause      = models.CharField(max_length=16, choices=VersionCause.choices)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="record_versions",
    )
    created_at = models.DateTimeField(default=timezone.now)
    #: True when this version's documents were reconstructed from upload
    #: times rather than recorded at submission (ADR-058 §2, IR-872): every
    #: version written before IR-872. Shown, so a guess is never read as a record.
    documents_reconstructed = models.BooleanField(default=False)
    #: The text reviewers compare and anchor threads to (ADR-058 §1 as
    #: amended, IR-871). A Version that changes the manuscript gets its own;
    #: a metadata-only one points at the one before it. Null where there is no
    #: manuscript, or for a Version from before IR-871 that `read_review_texts`
    #: hasn't reached yet. `RESTRICT`: no code deletes a text a Version names.
    review_text = models.ForeignKey(
        "ReviewText", on_delete=models.RESTRICT, null=True, blank=True, related_name="versions",
    )

    class Meta:
        ordering = ["record", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["record", "number"], name="record_version_number_unique",
            ),
        ]

    def __str__(self):
        return f"{self.record_id} v{self.number}"


class RecordVersionDocument(models.Model):
    """
    One upload slot's document as it stood when a version was submitted
    (ADR-058 §2, IR-872). `write_version` writes one row per slot that had a
    file; a slot with nothing uploaded gets no row. A document uploaded
    between versions is not stored here: "added during vN" is read from upload
    times (`versions.documents_added_during`).

    **`upload` is `RESTRICT`**: no code may delete a document a version names.
    A record's own hard delete still cascades through both, because RESTRICT,
    unlike PROTECT, allows a delete that removes the version too.
    """

    version = models.ForeignKey(RecordVersion, on_delete=models.CASCADE, related_name="documents")
    upload  = models.ForeignKey(
        "documents.RecordUpload", on_delete=models.RESTRICT, related_name="version_documents",
    )

    class Meta:
        ordering = ["version", "upload__slot__name", "upload_id"]
        constraints = [
            models.UniqueConstraint(fields=["version", "upload"], name="version_document_unique"),
        ]

    def __str__(self):
        return f"{self.version} · upload {self.upload_id}"


class ReviewText(models.Model):
    """
    One manuscript file's text for review, read on campus with no AI (ADR-058
    §1 as amended 2026-11-05, IR-871). It is not the LlamaParse Extraction:
    it is read at submission whatever the embargo or AI consent says, and it
    is never chunked, embedded or retrieved. Served only under
    `may_read_review`.

    **Never re-read in place.** Once a reading is stored it stays what it
    was, so a Thread's anchor keeps resolving against the text it was checked
    against; `reader` names the reader that produced it. Only `pending` and
    `unavailable` texts are ever read (`store.read_text`).
    """

    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="review_texts")
    #: The manuscript file it reads, as the Version names it.
    source_file = models.CharField(max_length=255)
    manuscript_sha256 = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=16, choices=ReviewTextState.choices,
                             default=ReviewTextState.PENDING)
    #: Why there is no text: a `sandbox` reason code. Blank when read.
    reason = models.CharField(max_length=32, blank=True)
    reader = models.CharField(max_length=64, blank=True)
    #: The reader this text was made for, known before it is read (IR-873,
    #: ADR-058 §3 as amended 2026-11-08). A comparison asks for a reading of a
    #: file by one reader, so a second request finds the first instead of
    #: queueing another. Blank on a text attached before IR-873 and never read.
    requested_reader = models.CharField(max_length=64, blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    #: What may be wrong with the sections found (`reader._finish`), e.g. no headings.
    warnings = models.JSONField(default=list, blank=True)
    #: Read later by `read_review_texts` from the Version's own file, not at submission.
    read_after_submission = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["record", "created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(state=ReviewTextState.READ) | (
                    ~models.Q(reader="") & models.Q(read_at__isnull=False)
                ),
                name="review_text_read_names_its_reader",
            ),
            # One reading of a file per reader: the one a Version was given at
            # submission, or the one a comparison added beside it (IR-873).
            models.UniqueConstraint(
                fields=["record", "source_file", "manuscript_sha256", "requested_reader"],
                condition=~models.Q(requested_reader=""),
                name="review_text_one_reading_per_reader",
            ),
        ]

    def __str__(self):
        return f"{self.record_id} · {self.source_file} · {self.state}"


class ReviewTextSection(models.Model):
    """
    One section of a review text: its heading, the page it starts on, and its
    passages (IR-871). A passage is a sentence or a ruled table's row, stored
    as JSON `{text, page, paragraph, kind, regions}`, with `regions` in
    ADR-031's page-fraction shape. `key` is the heading without its numbering,
    with `#2` and on for a repeated heading, or `front-matter`; `text_hash`
    hashes the normalised passages, so a later reading can tell an unchanged
    section from a changed one exactly.
    """

    text = models.ForeignKey(ReviewText, on_delete=models.CASCADE, related_name="sections")
    ordinal = models.PositiveIntegerField()
    key = models.CharField(max_length=255)
    heading = models.TextField(blank=True)
    page = models.PositiveIntegerField()
    text_hash = models.CharField(max_length=64)
    passages = models.JSONField(default=list)

    class Meta:
        ordering = ["text", "ordinal"]
        constraints = [
            models.UniqueConstraint(fields=["text", "ordinal"], name="review_section_ordinal_unique"),
            models.UniqueConstraint(fields=["text", "key"], name="review_section_key_unique"),
        ]

    def __str__(self):
        return f"{self.text_id} §{self.ordinal} {self.key[:40]}"


class EmbargoReminder(models.Model):
    """
    A reminder already sent about one embargo's review date (ADR-052 §9).

    The unique key is the idempotency, as with `DeadlineMoment`: a re-run, a
    missed tick or two beat instances insert the same row, and only one wins.
    `embargo_set_at` is the paper's `embargo_date_set_at`, which every set and
    extend restamps, so a new date, or a released paper held again, starts the
    reminders over. `step` is 0 on the date, then one more per 5 working days.
    """

    record = models.ForeignKey("Record", on_delete=models.CASCADE, related_name="embargo_reminders")
    embargo_set_at = models.DateTimeField()
    step = models.PositiveIntegerField()
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["sent_at", "pk"]
        constraints = [models.UniqueConstraint(
            fields=["record", "embargo_set_at", "step"], name="one_embargo_reminder_per_step",
        )]


class UnlistedPublication(models.Model):
    """
    RDCO published an Unlisted paper after its Decision (ADR-047 §10, IR-878).

    The Decision's `Review` says only "approved", so the history tells
    *published* from *kept unlisted* by the paper's status. Once an Unlisted
    paper is published later, this row is what keeps its Decision reading
    *kept unlisted*, and it holds the optional note, which the audit log never
    carries. A paper is published from Unlisted at most once: nothing moves a
    published paper back to Unlisted.
    """

    record = models.OneToOneField(
        "Record", on_delete=models.CASCADE, related_name="unlisted_publication",
    )
    published_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+",
    )
    published_at = models.DateTimeField(default=timezone.now)
    note = models.TextField(blank=True, default="")


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


class RecordView(models.Model):
    """One account's first opening of a published paper (IR-369, CONTEXT.md **View**).

    Kept only to count each account once and to date the view for Trending.
    No serializer or endpoint reads it, and it isn't part of the Library or
    Reading history. It goes with the account (`accounts.deletion.registry`)
    and with the paper (the cascade below). `Record.access_count` is the
    count; `apps.records.views_count` writes both together.
    """

    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="views")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    viewed_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["record", "user"], name="record_view_once_per_account"),
        ]
        indexes = [models.Index(fields=["record", "viewed_at"], name="record_view_recent")]


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


# ---- Download / Delete requests -----------------------------------------

#: The longest note a reader or RDCO may leave on a download request (IR-688).
DOWNLOAD_NOTE_MAX_LENGTH = 500


class DownloadRequest(models.Model):
    STATUS = RequestStatus.choices
    record       = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="download_requests")
    requested_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="download_requests")
    status       = models.CharField(
        max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    reviewed_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_download_requests"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # When an approval stops letting the requester download (ADR-048). Expired
    # is worked out from this, not stored.
    grant_expires_at = models.DateTimeField(null=True, blank=True)
    # Why the reader asks (IR-688). Required of every new request; blank only
    # on requests made before notes existed.
    note = models.CharField(max_length=DOWNLOAD_NOTE_MAX_LENGTH, blank=True, default="")
    # RDCO's reason for a decline or a revocation (IR-688). An approval takes
    # none. Blank on a decline made before notes existed: "No note recorded".
    rdco_note = models.CharField(max_length=DOWNLOAD_NOTE_MAX_LENGTH, blank=True, default="")
    # A revocation keeps `reviewed_by`/`reviewed_at` as the approval's.
    revoked_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="revoked_download_requests",
    )
    revoked_at   = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)


class DeleteRequest(models.Model):
    STATUS = RequestStatus.choices
    record       = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="delete_requests")
    requested_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="delete_requests")
    reason       = models.TextField(blank=True)
    status       = models.CharField(
        max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    previous_pipeline_status = models.CharField(max_length=20, blank=True, default="")
    reviewed_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_delete_requests"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


#: A Comment's longest text (ADR-032 §7, amendment 2026-10-31).
PUBLIC_COMMENT_MAX_LENGTH = 2_000


class PublicComment(models.Model):
    """
    A Comment on a published paper (ADR-032 §7, amendment 2026-10-31; IR-690).

    Never shares a model with the review discussion (`reviews.ReviewComment`).
    Shown only while its paper is published (`apps.records.public_comments`);
    a paper that stops being public keeps its comments, unseen. A deleted or
    removed comment keeps its text, which no response ever carries, so a
    report about it can still be checked (IR-691).
    """

    record      = models.ForeignKey(Record, on_delete=models.CASCADE, related_name="public_comments")
    #: `SET_NULL`: a deleted account's comment stays, shown as "Former user".
    author      = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="public_comments",
    )
    body        = models.TextField()
    #: The comment it answers, on the same paper. The thread stays flat.
    reply_to    = models.ForeignKey(
        "self", on_delete=models.RESTRICT, null=True, blank=True, related_name="replies",
    )
    created_at  = models.DateTimeField(default=timezone.now)
    #: Set by an edit; the earlier wording is not kept.
    edited_at   = models.DateTimeField(null=True, blank=True)
    deletion_kind = models.CharField(max_length=20, choices=CommentDeletion.choices, null=True, blank=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    deleted_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    #: A moderator's reason (IR-691); blank for a writer's own delete.
    removal_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["record", "created_at"], name="public_comment_thread")]

    def __str__(self):
        return f"Comment {self.pk} on record {self.record_id}"
