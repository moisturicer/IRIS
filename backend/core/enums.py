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
    Where a record is. `Record.pipeline_status`.

    `draft -> in_review ->` a Decision's outcome (ADR-032 §2-§3): `approved`
    (a Proposal, shown as *Accepted*), `published`, `completed` (kept
    unlisted, shown as *Unlisted*; or a legacy Proposal the retired *complete*
    act finished) or `rejected` (shown as *Archived*). `pending_delete` holds
    accepted work while its delete request is reviewed.

    **One value for a record in review** (ADR-021 §4). Who holds it is its
    active assignments, not this column. The fixed pipeline's five stage values
    (`adviser_review`, `rdco_intake`, `itso_review`, `parallel_review`,
    `rdco_review`) and the stored `declined` were migrated to `in_review` by
    IR-260 and removed from the vocabulary by IR-274; a revision request is
    now an open `ResubmissionRequest`, never a status.
    """

    DRAFT = "draft", "Draft"
    IN_REVIEW = "in_review", "In Review"

    # A Decision's outcomes
    APPROVED = "approved", "Approved"
    COMPLETED = "completed", "Completed"
    PUBLISHED = "published", "Published"
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

    Note these are *not* pipeline statuses: the stage names the reviewing
    party (`itso`), while the pipeline status names the state the record is in
    (`in_review`).

    **This is also the party vocabulary** (ADR-021 §1), aliased as `Party`
    below. `intake` survives only as history, labelled "Intake (retired)"
    (ADR-032 §13): old Review, assignment and request rows keep it. Nothing new
    may assign or route to it -- see `ASSIGNABLE_PARTIES`, and the database
    constraint on `RecordAssignment` that refuses an active intake assignment.
    The old stage value `rdco_intake` meant the same party; IR-274 rewrote its
    rows to `intake` and removed it.
    """

    ADVISER = "adviser", "Adviser"
    #: Historical only (ADR-032 §13). Never assignable.
    INTAKE = "intake", "Intake (retired)"
    ITSO = "itso", "ITSO"
    IERC = "ierc", "IERC"
    KTTO = "ktto", "KTTO"
    RDCO = "rdco", "RDCO Final"


#: ADR-021 §1: "No new enum is needed." A party is a `ReviewStage`, named for
#: what it means at the call site.
Party = ReviewStage

#: The parties retired by ADR-032 §13. Their rows stay readable as history.
RETIRED_PARTIES = (Party.INTAKE,)

#: The parties anything new may be assigned, routed or requested as.
ASSIGNABLE_PARTIES = tuple(p for p in Party if p not in RETIRED_PARTIES)


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

    Only the three specialist offices. RDCO is deliberately absent: it decides
    rather than clears, and never holds a `RecordClearance` row, so admitting it here would let a caller construct a
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


class SeatState(models.TextChoices):
    """
    Where one reviewer's part in an office's assignment stands. `ReviewerSeat.state`.

    ADR-032 §4. `ASSIGNED` is a seat nobody has opened yet; *Open review* moves
    it to `IN_REVIEW` and stamps `opened_at`. `DONE` is the reviewer's part
    finished, and `WITHDRAWN` is a coordinator, or a decision, taking it away.
    Like `AssignmentState`, **not an outcome**: the verdict is the seat
    holder's own `Review` row.

    `IN_REVIEW` and `WITHDRAWN` share their values with `PipelineStatus` and
    `AssignmentState`, which is why this enum is not listed in the vocabulary
    guard: those two already govern the shared spellings, and `"done"` is also
    an unrelated `PdfExtraction` status.
    """

    ASSIGNED = "assigned", "Assigned"
    IN_REVIEW = "in_review", "In review"
    DONE = "done", "Done"
    WITHDRAWN = "withdrawn", "Withdrawn"


#: The seat states that still count as holding one: not finished, not taken away.
OPEN_SEAT_STATES = (SeatState.ASSIGNED, SeatState.IN_REVIEW)


class SeatSource(models.TextChoices):
    """
    How a reviewer came to hold a seat. `ReviewerSeat.source`. ADR-032 §4.

    - `ENTRY`: the record's Adviser, seated automatically when it is submitted.
    - `CLAIMED`: an office member took an unclaimed record from the pool.
    - `ASSIGNED`: an office coordinator seated a member.
    - `NOMINATED`: whoever routed the record to the office named the member.
    - `ADDED`: a seat holder brought in a colleague from their own office.
    """

    ENTRY = "entry", "Entry"
    CLAIMED = "claimed", "Claimed"
    ASSIGNED = "assigned", "Assigned"
    NOMINATED = "nominated", "Nominated"
    ADDED = "added", "Added"


class VersionCause(models.TextChoices):
    """
    Why a record has a new Version. `RecordVersion.cause`. ADR-032 §5.

    - `SUBMISSION`: the record was first submitted (v1).
    - `REVISION`: the owner resubmitted after a reviewer asked for changes.
    """

    SUBMISSION = "submission", "Submission"
    REVISION = "revision", "Revision"


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


class DocumentRequestState(models.TextChoices):
    """
    Where one party's request for documents stands. `DocumentRequest.state`.

    ADR-022 §1. `OPEN` holds the record at `awaiting_document`; `FULFILLED`
    means every item has an upload; `WITHDRAWN` is the requesting party
    dropping it, or a decision closing it (§3, §4).
    """

    OPEN = "open", "Open"
    FULFILLED = "fulfilled", "Fulfilled"
    WITHDRAWN = "withdrawn", "Withdrawn"


class DocumentRequestItemState(models.TextChoices):
    """
    One requested document. `DocumentRequestItem.state`.

    ADR-022 §1 and §3. The owner's upload moves `MISSING` to `UPLOADED`; the
    requesting party's review moves it to `ACCEPTED`, or rejects it.

    **A rejected item is stored as `MISSING`, not `REJECTED`** (IR-263):
    §3.4 sends it "back to `missing` with a comment", and the owner must be
    able to upload against it again. The rejection is recorded as the item's
    `rejection_reason` and `decided_at`. `REJECTED` is kept because ADR-022
    §1 lists it, but nothing writes it.
    """

    MISSING = "missing", "Missing"
    UPLOADED = "uploaded", "Uploaded"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class WorkflowState(models.TextChoices):
    """
    Where an in-review record stands, as the API states it (ADR-021 §4).

    **Derived, never stored** -- no model field takes these as choices, and
    `apps/records/test_tracker.py` fails if a column named `workflow_state`
    appears. `apps.reviews.tracker.derive_workflow_state` is the only author.
    A record that is not in review reports its stored `PipelineStatus` instead,
    so the wire value is one of these *or* a terminal status.

    `IN_REVIEW` deliberately shares its value with `PipelineStatus.IN_REVIEW`:
    it is the same fact, seen from the stored side and the derived side.
    """

    AWAITING_RESUBMISSION = "awaiting_resubmission", "Awaiting resubmission"
    AWAITING_DOCUMENT = "awaiting_document", "Awaiting document"
    SUBMITTED = "submitted", "Submitted"
    FINAL_REVIEW = "final_review", "Final review"
    IN_REVIEW = "in_review", "In review"


class TrackerPartyState(models.TextChoices):
    """
    One party's row on the Review & Routing Tracker (`workflow_routing_architecture.md` §8.2).

    Not stored. The first three restate `AssignmentState` for a party whose
    latest assignment is in that state; the last two describe a party with no
    assignment at all, and differ only in whether the party will certainly be
    needed: RDCO on a Thesis/Research or Project is `awaiting`, never
    `not_requested`, because RDCO always decides those (ADR-021 §14).
    """

    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    WITHDRAWN = "withdrawn", "Withdrawn"
    NOT_REQUESTED = "not_requested", "Not requested"
    AWAITING = "awaiting", "Awaiting"
    #: ADR-032 §10 and its 2026-10-08 Amendment: RDCO on a record on the
    #: adviser-first model that no specialist office has ever held. RDCO
    #: enters only by the hand-back, so nothing waits on it there (IR-269).
    NOT_REQUIRED = "not_required", "Not required"


class MyReviewsTab(models.TextChoices):
    """
    The three tabs of My Reviews (ADR-032 §9). Not stored: a request
    parameter and the wire format. `IN_REVIEW` shares its spelling with
    `PipelineStatus` and `SeatState`, which is why the tab is named here
    rather than typed by hand.
    """

    TO_REVIEW = "to_review", "To review"
    IN_REVIEW = "in_review", "In review"
    DONE = "done", "Done"


class ReviewOutcome(models.TextChoices):
    """
    What one reviewer concluded, as a Done row on My Reviews states it.

    Never stored: derived from the reviewer's own verdict `Review` (ADR-032
    §9 Amendment, 2026-10-08). `REVISION_REQUESTED` is the old pipeline's
    decline, which closed a reviewer's part; the new model never closes a
    seat that way, so it has no filter of its own.
    """

    CLEARED = "cleared", "Cleared"
    FINDING = "finding", "Finding recorded"
    ACCEPTED = "accepted", "Accepted"
    PUBLISHED = "published", "Published"
    REJECTED = "rejected", "Rejected"
    REVISION_REQUESTED = "revision_requested", "Revision requested"



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
    workflow rules turn on these strings: a Proposal is decided by its Adviser
    alone and never routed (ADR-032 §2).

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
