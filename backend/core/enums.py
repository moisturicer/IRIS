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

    **`IN_REVIEW` is added beside the stage values, not instead of them**
    (IR-256, ADR-021 §4). Under reviewer-directed routing a record's place in
    review is its active assignments, so one stored value replaces the five
    stage values and `declined`. Nothing stores it until IR-260 migrates those
    six away, and until then no review edge in `lifecycle.TRANSITIONS` leads to
    it.
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

    # Reviewer-directed routing (ADR-021 §4). Unused until IR-260.
    IN_REVIEW = "in_review", "In Review"

    # Terminal / visible states
    PUBLISHED = "published", "Published"
    DECLINED = "declined", "Declined"
    REJECTED = "rejected", "Rejected"
    PENDING_DELETE = "pending_delete", "Pending Deletion"


#: The statuses any authenticated user may read. Kept as a tuple of raw values
#: because it is compared against a database column and consumed by
#: `Record.objects.publicly_visible()` and `visible_to()` (IR-153) -- and through
#: them by Discover, record detail, the dashboard charts and Ask IRIS retrieval.
#:
#: Published only (ADR-021 §13, IR-264). It also held `approved` and `completed`
#: until then, and only a Proposal reaches those, so every approved or completed
#: Proposal was public: listed in Discover, openable by any account, citable by
#: Ask IRIS. A Proposal stays readable by its owners, its assigned adviser and
#: office staff through `visible_to()`'s other clauses.
PUBLICLY_VISIBLE_STATUSES = (PipelineStatus.PUBLISHED,)

#: The statuses whose deletion needs RDCO review: `perform_destroy` raises a
#: `DeleteRequest` instead of soft-deleting. Deliberately *not* derived from
#: `PUBLICLY_VISIBLE_STATUSES`: deletion used to branch on visibility, so
#: narrowing visibility alone would have let an owner soft-delete an approved or
#: completed Proposal with no review (ADR-021 §13). Accepted work needs review to
#: delete whether or not the public can see it.
DELETE_REVIEW_STATUSES = (
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

    **This is also the party vocabulary** (ADR-021 §1), aliased as `Party`
    below. The six parties are these six values with `rdco_intake` renamed to
    `intake`. IR-256 adds `INTAKE` beside `RDCO_INTAKE` rather than renaming it:
    `rdco_intake` is a stored `Review.stage`, and IR-260's migration rewrites
    those rows and removes the old value in the same step. Until then, nothing
    new may name a party `rdco_intake`; see `RecordAssignment.party`.
    """

    ADVISER = "adviser", "Adviser"
    RDCO_INTAKE = "rdco_intake", "RDCO Intake"
    #: Staff see "Intake & Triage", students see "Intake" (ADR-021 §2). The
    #: label here is the staff one; the student label is IR-258's to serve.
    INTAKE = "intake", "Intake & Triage"
    ITSO = "itso", "ITSO"
    IERC = "ierc", "IERC"
    KTTO = "ktto", "KTTO"
    RDCO = "rdco", "RDCO Final"


#: ADR-021 §1: "No new enum is needed." A party is a `ReviewStage`, named for
#: what it means at the call site.
Party = ReviewStage

#: The six parties of ADR-021 §1: `Party` without `RDCO_INTAKE`. That value is
#: a stored stage's history until IR-260 renames the rows, never a party's
#: identity (§2), so nothing new may be assigned to, routed to, or asked for
#: changes by it. When IR-260 deletes `RDCO_INTAKE`, this is simply `tuple(Party)`.
ASSIGNABLE_PARTIES = tuple(p for p in Party if p is not Party.RDCO_INTAKE)


class ReviewDecision(models.TextChoices):
    """
    A reviewer's verdict on a record. `Review.status`.

    `DECLINED` and `REJECTED` are not synonyms and the difference is the whole
    point: a decline requests a revision and the owner may resubmit, a rejection
    is terminal.

    **IR-256 (ADR-021 §8).** `DECLINED` keeps its stored value and is relabelled
    "Resubmission requested", which is what it has always meant. The record
    detail and review-queue payloads send the value, never this label. `NEGATIVE_FINDING` is a specialist office's finding
    against a record, which under ADR-021 replaces an office's power to reject.
    No endpoint accepts it yet: `ReviewWriteSerializer` pins the three decisions
    `/reviews/submit/` actually implements.
    """

    APPROVED = "approved", "Approved"
    DECLINED = "declined", "Resubmission requested"
    REJECTED = "rejected", "Rejected"
    NEGATIVE_FINDING = "negative_finding", "Negative finding"


class ClearanceStatus(models.TextChoices):
    """
    One office's clearance state for a record. `RecordClearance.status`.

    `CLEARED` rather than `APPROVED`: an office clears its own gate, it does not
    approve the record. The distinction carries the thesis contribution --
    on resubmission after a decline, only the declining office's row resets to
    `PENDING` and every other office's `CLEARED` is preserved.

    **IR-256 (ADR-021 §8).** `NOT_CLEARED` is an office's recorded negative
    outcome, the clearance-side twin of `ReviewDecision.NEGATIVE_FINDING`.
    `REJECTED` stays for historical rows, and nothing new will write it once
    IR-260 lands.
    """

    PENDING = "pending", "Pending"
    CLEARED = "cleared", "Cleared"
    DECLINED = "declined", "Declined"
    REJECTED = "rejected", "Rejected"
    NOT_CLEARED = "not_cleared", "Not cleared"


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


class AssignmentState(models.TextChoices):
    """
    Whether a party is still acting on a record. `RecordAssignment.state`.

    **Not an outcome** (ADR-021 §8). What the party concluded lives in `Review`
    and `RecordClearance`; putting it here as well would be a second source of
    truth for the same fact. `COMPLETED` means the party finished, and
    `WITHDRAWN` means a decision closed the assignment before it did (§12).
    """

    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    WITHDRAWN = "withdrawn", "Withdrawn"


class ResubmissionRequestState(models.TextChoices):
    """
    Where one party's request for changes stands. `ResubmissionRequest.state`.

    Replaces the stored `declined` pipeline status (ADR-021 §11). One stored
    status cannot say that two parties are each waiting on a revision; one row
    per request can.
    """

    OPEN = "open", "Open"
    RESUBMITTED = "resubmitted", "Resubmitted"
    WITHDRAWN = "withdrawn", "Withdrawn"


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
