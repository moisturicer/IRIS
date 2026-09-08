"""
The workflow's vocabulary, defined once (IR-135).

Every value here is **byte-identical to what is already stored in the
database**. This module renames nothing. It is a refactor of the source, not of
the data: `makemigrations` produces `AlterField`s because `choices` is part of a
field's deconstruction, but no stored row changes and no column changes.

**Why this exists.** Status, stage, office and role values were repeated as bare
string literals across models, services, views and serializers -- `"approved"`
alone appeared 33 times. The values were *also* ambiguous across concepts:
`"approved"` is a pipeline status, a review decision, *and* a request status,
and `"declined"` is all three plus a clearance status. Nothing in the code said
which one a given site meant, so a reader had to infer it from context and a
find-and-replace could not be trusted.

This is a prerequisite for the declarative transition table (IR-136), not
incidental cleanup: a table keyed by string literals inherits the exact drift it
exists to remove.

**The concepts are deliberately separate even where their values coincide.**
`ReviewDecision.APPROVED`, `RequestStatus.APPROVED` and
`PipelineStatus.APPROVED` are all `"approved"` on the wire and mean three
different things -- a reviewer's verdict, a download request's outcome, and a
Proposal's terminal state. Collapsing them into one enum because the strings
match would re-create the ambiguity this module removes.

**What is not here.** `PdfExtraction.STATUS` (queued/running/done/failed) stays
in `apps/documents/models.py`: it belongs to the ingestion pipeline, shares no
value with the workflow vocabulary, and folding it in would widen this change
for no gain. Institution-facing *labels* are configuration (P1-05); the keys
below are the stable part.
"""

from django.db import models


class PipelineStatus(models.TextChoices):
    """
    Where a record sits in the review pipeline. `Record.pipeline_status`.

    Two routes converge here. A Proposal goes `draft -> adviser_review ->
    approved -> completed`. A Thesis/Research or Project goes `draft ->
    rdco_intake -> [itso_review] -> parallel_review -> rdco_review ->
    published`. `declined`, `rejected` and `pending_delete` can interrupt
    either.
    """

    DRAFT = "draft", "Draft"

    # Proposal pipeline
    ADVISER_REVIEW = "adviser_review", "Adviser Review"
    APPROVED = "approved", "Approved"
    COMPLETED = "completed", "Completed"

    # Thesis/Research and Project pipeline
    RDCO_INTAKE = "rdco_intake", "RDCO Intake Review"
    ITSO_REVIEW = "itso_review", "ITSO Review"
    PARALLEL_REVIEW = "parallel_review", "Parallel Office Review"
    RDCO_REVIEW = "rdco_review", "RDCO Final Review"

    # Terminal / visible states
    PUBLISHED = "published", "Published"
    DECLINED = "declined", "Declined"
    REJECTED = "rejected", "Rejected"
    PENDING_DELETE = "pending_delete", "Pending Deletion"


#: The statuses any authenticated user may read. Kept as a tuple of raw values
#: because it is compared against a database column and consumed by
#: `Record.objects.publicly_visible()` and `visible_to()` (IR-153).
PUBLICLY_VISIBLE_STATUSES = (
    PipelineStatus.PUBLISHED,
    PipelineStatus.APPROVED,
    PipelineStatus.COMPLETED,
)


class ReviewStage(models.TextChoices):
    """
    Which gate a `Review` row was recorded at. `Review.stage`.

    Note these are *not* pipeline statuses, though they read similarly: the
    stage names the reviewing party (`itso`), while the pipeline status names
    the state the record is in (`itso_review`).
    """

    ADVISER = "adviser", "Adviser"
    RDCO_INTAKE = "rdco_intake", "RDCO Intake"
    ITSO = "itso", "ITSO"
    IERC = "ierc", "IERC"
    KTTO = "ktto", "KTTO"
    RDCO = "rdco", "RDCO Final"


class ReviewDecision(models.TextChoices):
    """
    A reviewer's verdict on a record. `Review.status`.

    `DECLINED` and `REJECTED` are not synonyms and the difference is the whole
    point: a decline requests a revision and the owner may resubmit, a rejection
    is terminal.
    """

    APPROVED = "approved", "Approved"
    DECLINED = "declined", "Declined"
    REJECTED = "rejected", "Rejected"


class ClearanceStatus(models.TextChoices):
    """
    One office's clearance state for a record. `RecordClearance.status`.

    `CLEARED` rather than `APPROVED`: an office clears its own gate, it does not
    approve the record. The distinction carries the thesis contribution --
    on resubmission after a decline, only the declining office's row resets to
    `PENDING` and every other office's `CLEARED` is preserved.
    """

    PENDING = "pending", "Pending"
    CLEARED = "cleared", "Cleared"
    DECLINED = "declined", "Declined"
    REJECTED = "rejected", "Rejected"


class Office(models.TextChoices):
    """
    A clearing office. `RecordClearance.office`.

    Only the three parallel-clearance offices. RDCO is deliberately absent: it
    performs intake and final review as sequential stages and never holds a
    `RecordClearance` row, so admitting it here would let a caller construct a
    clearance that the workflow has no gate for. RDCO appears in `ReviewStage`
    and `RoleName` instead.
    """

    ITSO = "itso", "ITSO"
    IERC = "ierc", "IERC"
    KTTO = "ktto", "KTTO"


class RequestStatus(models.TextChoices):
    """
    The outcome of a request a person makes and staff rule on:
    `DownloadRequest.status`, `DeleteRequest.status`, `RoleRequest.status`.

    One enum for all three because it is genuinely one concept -- asked,
    granted, refused -- not three that happen to share strings.
    """

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    DECLINED = "declined", "Declined"


class IPType(models.TextChoices):
    """Specific IP classification set by RDCO/KTTO after final review. `Record.ip_type`."""

    PATENT = "patent", "Patent"
    COPYRIGHT = "copyright", "Copyright"
    TRADE_SECRET = "trade_secret", "Trade Secret"
    UTILITY_MODEL = "utility_model", "Utility Model"


class RoleName(models.TextChoices):
    """
    Canonical `Role.name` values.

    `Role` is a database table, not a choices field, so these are **not** used
    as `choices=` anywhere. They exist because role names are compared as
    literals in authorization code, and a typo in that comparison fails *open* --
    `get_role_name(user) in STAFF_ROLES` silently admits nobody rather than
    raising. `core.permissions` builds its role sets from these.

    The value is the human-readable name because that is what is stored; there
    is no separate key. Seeded by `accounts/0003`.
    """

    STUDENT = "Student", "Student"
    ADVISER = "Adviser", "Adviser"
    KTTO = "KTTO", "KTTO"
    RDCO = "RDCO", "RDCO"
    ITSO = "ITSO", "ITSO"
    IERC = "IERC", "IERC"


class RecordTypeName(models.TextChoices):
    """
    Canonical `RecordType.name` values, seeded by `records/0002`.

    Like `RoleName`, a table rather than a choices field, and named here because
    routing turns on these strings: `_type_name(record) == "Proposal"` decides
    whether a submission enters `adviser_review` or `rdco_intake`.

    **Note the spaces in `THESIS_RESEARCH`.** The stored value is
    `"Thesis / Research"`; several comments and docstrings in the codebase write
    it as `"Thesis/Research"`. Nothing compares against that shorter form today
    -- routing only ever tests `Proposal` and `Project` and lets Thesis/Research
    fall through the `else` -- so the drift is currently harmless prose. It is
    exactly the kind that stops being harmless the moment someone writes the
    equality test the comment implies, which is why the real value is pinned
    here.
    """

    PROPOSAL = "Proposal", "Proposal"
    THESIS_RESEARCH = "Thesis / Research", "Thesis / Research"
    PROJECT = "Project", "Project"
