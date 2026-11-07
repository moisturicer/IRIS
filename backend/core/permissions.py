from rest_framework.permissions import BasePermission

from core.enums import (
    DELETE_REVIEW_STATUSES, OPEN_SEAT_STATES, AssignmentState, EmbargoState, Party,
    PipelineStatus, RoleName, WorkflowState,
)

# Role name constants -- match the Role.name values in the DB exactly.
# Aliases onto `RoleName` since IR-135: the names are kept because the sets
# below and a dozen call sites read better with them, but the *values* are
# single-sourced now. A typo in a role comparison fails open -- an unknown name
# simply matches nobody -- so these must never drift from the seeded rows.
ROLE_STUDENT = RoleName.STUDENT
ROLE_ADVISER = RoleName.ADVISER
ROLE_KTTO    = RoleName.KTTO
ROLE_RDCO    = RoleName.RDCO
ROLE_ITSO    = RoleName.ITSO
ROLE_IERC    = RoleName.IERC
ROLE_SYSTEM_ADMIN = RoleName.SYSTEM_ADMIN

# Convenience sets
REVIEWER_ROLES = {ROLE_ADVISER, ROLE_KTTO, ROLE_RDCO, ROLE_ITSO, ROLE_IERC}
STAFF_ROLES    = {ROLE_KTTO, ROLE_RDCO, ROLE_ITSO, ROLE_IERC}
# RDCO administers people's accounts and the request queues. It is not IRIS's
# administrator: the System Admin is (ADR-051 §1), and holds no workflow access,
# so it is in none of the sets above.
ADMIN_ROLES    = {ROLE_RDCO}
#: The roles RDCO may give, to someone outside the offices (ADR-051 §4, amended).
#: Office roles are the System Admin's to give, and the System Admin role itself
#: is given only in Django's admin site.
RDCO_GIVES     = {ROLE_STUDENT, ROLE_ADVISER}
#: Who opens the Users page: RDCO and the System Admin.
ACCOUNT_ADMIN_ROLES = ADMIN_ROLES | {ROLE_SYSTEM_ADMIN}
#: What `get_role_name` returns for an account with no role yet.
NO_ROLE = ""
# Who may author a disclosure. SRS Use Cases M2-2.1 (Create IP Disclosure Draft)
# and M2-2.2 (Submit Record for Review) both name the actor "Record Owner
# (Student or Adviser)". Deliberately excludes the clearing offices -- ITSO,
# IERC and KTTO must not author records they may later clear -- and RDCO, which
# decides the specialist path, so authoring would mean deciding its own record.
# RDCO files on behalf of others through the bulk import path instead.
AUTHOR_ROLES   = {ROLE_STUDENT, ROLE_ADVISER}
# Who may publish a Calls & Conferences opportunity (IR-121, narrowed by
# IR-757). Deliberately not STAFF_ROLES: that set includes the clearing offices
# (ITSO, IERC, KTTO), who do not post calls, and excludes Adviser, who is exactly
# the "teacher posting a departmental call" the feature was asked for. Students
# never post.
OPPORTUNITY_POSTER_ROLES = {ROLE_RDCO, ROLE_ADVISER}
# Who may correct or remove *someone else's* posting. Deliberately its own set
# rather than a reference to ADMIN_ROLES, so a change to who administers accounts
# cannot silently change who may edit every call on the board.
OPPORTUNITY_MODERATOR_ROLES = {ROLE_RDCO}


def get_role_name(user) -> str:
    """Return the user's role name, or empty string if not set."""
    try:
        return user.role.name
    except AttributeError:
        return ""


# --- a note on Django's is_staff, deliberately not a function -------------
#
# `is_staff` answers "may you open the Django admin site". It is not an
# authorization signal for this API, and there is no helper here that treats it
# as one -- not even an unused one, because an unused helper is an invitation.
#
# It was one. Every class below began `is_django_staff(user) or <role check>`,
# and migration `accounts/0005` set `is_staff = True` on RDCO, KTTO, ITSO and
# IERC so those accounts could reach /admin. The left operand was therefore
# always true for all four offices and the role check never ran: `ADMIN_ROLES`
# constrained nobody, the audit log admitted every office, and an ITSO officer
# could record IERC's ethics clearance. Migration `accounts/0009` reverses the
# seeding for role-holders; superusers keep the flag, and with it /admin.
#
# If you need "may this account open /admin", read `user.is_staff` at the point
# of use and say why. Do not reintroduce a shared predicate (IR-165).


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_STUDENT


class IsAdviser(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_ADVISER


class IsKTTO(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_KTTO


class IsRDCO(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_RDCO


class IsITSO(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_ITSO


class IsIERC(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_IERC


class IsAuthor(BasePermission):
    """Student or Adviser -- the roles the SRS names as a Record Owner."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in AUTHOR_ROLES


class IsReviewer(BasePermission):
    """Adviser, KTTO, RDCO, ITSO or IERC. Role only -- see the module note on is_staff."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in REVIEWER_ROLES


def is_office_staff(user) -> bool:
    """KTTO, RDCO, ITSO or IERC. Role only -- see the module note on is_staff."""
    return get_role_name(user) in STAFF_ROLES


class IsStaff(BasePermission):
    """KTTO, RDCO, ITSO or IERC. Role only -- see the module note on is_staff."""
    def has_permission(self, request, view):
        return is_office_staff(request.user)


class IsAdmin(BasePermission):
    """RDCO alone: account administration and the request queues."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in ADMIN_ROLES


def is_system_admin(user) -> bool:
    return get_role_name(user) == ROLE_SYSTEM_ADMIN


class IsSystemAdmin(BasePermission):
    """
    The System Admin alone: the Audit Log, system settings and office roles
    (ADR-051 §3). `is_superuser` grants nothing here, as everywhere (IR-165).
    """
    def has_permission(self, request, view):
        return is_system_admin(request.user)


class IsAccountAdmin(BasePermission):
    """RDCO or the System Admin: the Users page and its role changes."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in ACCOUNT_ADMIN_ROLES


def role_change_refusal(actor, target, role) -> str | None:
    """
    Why `actor` may not give `target` the role `role`, or None when they may.

    Nobody gives or changes the System Admin role through IRIS: it is given in
    Django's admin site (ADR-051 §5, amended). The System Admin gives any other
    role. RDCO gives Student or Adviser to someone outside the offices.
    """
    if role.name == ROLE_SYSTEM_ADMIN or is_system_admin(target):
        return "The System Admin role is given and removed only in Django's admin site."
    if is_system_admin(actor):
        return None
    if get_role_name(actor) in ADMIN_ROLES:
        if role.name in RDCO_GIVES and get_role_name(target) in RDCO_GIVES | {NO_ROLE}:
            return None
        return "Office roles are given by the System Admin."
    return "You do not have permission to change roles."


class IsOpportunityPoster(BasePermission):
    """
    Who may post a call, and who may then edit or delete one. See IR-121, IR-757.

    `has_permission` gates *posting* by role: RDCO or Adviser.
    `has_object_permission` gates *editing an existing posting*, and the two are
    deliberately different — without the second, every Adviser in the university
    could rewrite or delete RDCO's grant announcements, because they share a role
    bucket. Role membership answers "may you post?", never "is this yours?".

    The rule mirrored the old record `IsOwnerOrStaff` (retired by IR-508): the
    person who posted it, or RDCO acting as a moderator. An Adviser can edit only
    their own call; RDCO can correct anyone's, which is what an institutional
    noticeboard needs when a deadline changes and the poster is unavailable. A
    role that can no longer post cannot change a call it posted earlier, because
    `has_permission` runs first.
    """
    def has_permission(self, request, view):
        return get_role_name(request.user) in OPPORTUNITY_POSTER_ROLES

    def has_object_permission(self, request, view, obj):
        if get_role_name(request.user) in OPPORTUNITY_MODERATOR_ROLES:
            return True
        return obj.posted_by_id == request.user.pk


def owns_or_staffs_record(user, record) -> bool:
    """
    May `user` reach this record's documents and act on the record itself?

    The single owner-or-staff rule (IR-153). It was previously written out by
    hand at five call sites -- four in `apps/documents/views.py`, one in
    `apps/reviews/views.py` -- each spelling `get_role_name(...) in STAFF_ROLES
    or record.owners.filter(...)` again. Five copies of an authorization rule is
    five places for one of them to drift, and drift in this direction is silent:
    the endpoint keeps working, it just stops refusing the right people.

    Deliberately narrower than `Record.objects.visible_to()`, which is the
    *read* predicate for record metadata and lets any authenticated user see a
    published record. Being able to read a record's catalogue entry is not
    permission to download its manuscript -- that is what `DownloadRequest`
    exists to mediate.

    `record.owners` is a `RecordOwner` queryset, so ownership is a membership
    test, not an equality test against a single field.
    """
    if not user or not user.is_authenticated:
        return False
    if get_role_name(user) in STAFF_ROLES:
        return True
    return record.owners.filter(user=user).exists()


def may_read_embargo(user, record) -> bool:
    """
    May `user` see where `record`'s embargo stands? Owners, the Adviser and
    office staff (ADR-052, IR-811).

    Reading a record is not enough: every signed-in user reads a published one,
    and that a paper is under an agreement is not theirs to learn from it.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return record.adviser_id == user.pk or owns_or_staffs_record(user, record)


def may_set_embargo(user, record) -> bool:
    """
    The Adviser or RDCO set, move or renew an embargo's date (ADR-052 §5, as
    amended for IR-882). Owners no longer can, before or after submission: every
    paper starts embargoed, and a date is the Adviser's or RDCO's judgement of IP
    or patent potential, made during review.
    """
    return record.adviser_id == user.pk or get_role_name(user) == ROLE_RDCO


def may_release_embargo(user, record) -> bool:
    """
    The Adviser or RDCO, and never a student owner, even on their own paper (§6).
    A release sends text out for good, and an embargo may protect a sponsor's
    agreement or the other owners' wishes. If the Adviser has left, RDCO does it.
    """
    return record.adviser_id == user.pk or get_role_name(user) == ROLE_RDCO


def may_release_ip(user, record) -> bool:
    """
    KTTO alone releases an IP-marked paper, because KTTO evaluates IP (ADR-052
    §11-12). Not RDCO, not the Adviser and not an owner.
    """
    return get_role_name(user) == ROLE_KTTO


def is_record_owner(user, record) -> bool:
    """
    Does `user` own `record`? Ownership alone: no staff role, and no seat,
    stands in for it. A revision is the owner's to make, so a new version, a
    replacement manuscript and the details edit that answers a revision
    request all ask this (IR-273), as do every details edit and submission
    (IR-507).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return record.owners.filter(user=user).exists()


# --- reviewer seats (ADR-032 §4, §10; IR-415) --------------------------------
#
# Each new authority ADR-032 grants -- an office member may claim, a coordinator
# may assign, a seat holder may add a colleague -- is one of these predicates,
# checked at the endpoint. None is ever inferred from a role name alone at the
# call site, and none from the `capabilities` hint the frontend renders.

#: The office party each office role staffs. **The Adviser is not an office**:
#: an Adviser reviews a record only through the entry seat on one they advise.
#: RDCO staffs `rdco` only; `intake` is retired (ADR-032 §1) and nobody is
#: seated on it.
OFFICE_PARTY_BY_ROLE = {
    ROLE_ITSO: Party.ITSO,
    ROLE_IERC: Party.IERC,
    ROLE_KTTO: Party.KTTO,
    ROLE_RDCO: Party.RDCO,
}


def office_parties_of(user) -> frozenset:
    """The office parties `user` is a member of: one, or none."""
    if not user or not user.is_authenticated:
        return frozenset()
    party = OFFICE_PARTY_BY_ROLE.get(get_role_name(user))
    return frozenset({str(party)}) if party else frozenset()


def is_office_member(user, party) -> bool:
    """Does `user`'s role staff the office `party`? (ADR-032 §4)"""
    return str(party) in office_parties_of(user)


def is_office_coordinator(user, party) -> bool:
    """
    May `user` assign, reassign and withdraw seats for `party`?

    A member of that office whom an administrator made a coordinator. The flag
    alone grants nothing: a coordinator's authority stops at their own office.
    """
    return bool(getattr(user, "is_office_coordinator", False)) and is_office_member(user, party)


def holds_seat(user, record, party) -> bool:
    """
    Does `user` hold an open seat on `record`'s active `party` assignment?

    Open means assigned or in review: a reviewer whose part is `done`, or whose
    seat was withdrawn, no longer holds it.
    """
    from apps.reviews.models import ReviewerSeat

    if not user or not user.is_authenticated:
        return False
    return ReviewerSeat.objects.filter(
        assignment__record=record,
        assignment__party=str(party),
        assignment__state=AssignmentState.ACTIVE,
        reviewer=user,
        state__in=OPEN_SEAT_STATES,
    ).exists()


def is_record_participant(user, record) -> bool:
    """
    An owner of `record`, or anyone who has ever held a seat on it (ADR-032 §10).

    "Ever": a reviewer keeps the Review and Files sections once their part is
    done, so they can revisit what they worked on (IR-411, settled 2026-10-06).
    It gates the review discussion and the timeline.
    """
    from apps.reviews.models import ReviewerSeat

    if not user or not user.is_authenticated:
        return False
    if record.owners.filter(user=user).exists():
        return True
    return ReviewerSeat.objects.filter(assignment__record=record, reviewer=user).exists()


def may_read_review(user, record) -> bool:
    """
    May `user` read `record`'s review content -- who reviewed it and what they
    wrote? (IR-479, ADR-032 §10 Amendment 2026-10-08)

    Reviewer names and review comments are internal workflow data, so reading
    the Record is not enough: an office member reads every record, and once a
    record is published every signed-in user does. Access is by participation:

    - `is_record_participant`: an owner, or anyone who has ever held a seat;
    - or a member of a party holding an **active** assignment on the record
      right now, its pool included -- someone about to claim needs the
      history before acting. The server twin of the frontend's `isParticipant`.

    No role reads it everywhere, RDCO included; an audit is Django admin's.
    Document requests keep their own, party-wide rule (`may_read_requests`,
    ADR-022 §Amendment 5), which this deliberately does not replace.
    """
    from apps.reviews.models import RecordAssignment
    from apps.reviews.tracker import staffable_parties

    if not user or not getattr(user, "is_authenticated", False):
        return False
    if is_record_participant(user, record):
        return True
    staffable = staffable_parties(record, user)
    return bool(staffable) and RecordAssignment.objects.filter(
        record=record, party__in=staffable, state=AssignmentState.ACTIVE,
    ).exists()


# Which capability offers each Decision outcome (IR-270, IR-271).
DECISION_CAPABILITY = {
    "accept": "accept_proposal",
    "publish": "accept_publish",
    "keep_unlisted": "keep_unlisted",
    "reject": "reject",
}


#: What an owner's `DELETE /records/<id>/` does in each status, named as the act
#: it is (IR-508, ADR-032 §10 Amendment): gone now, withdrawn from review, or a
#: request RDCO decides. One endpoint, three keys, so a button names its
#: consequence. `pending_delete` is absent: a decision is already pending.
DELETE_CAPABILITY = {
    PipelineStatus.DRAFT: "delete_record",
    PipelineStatus.REJECTED: "delete_record",
    PipelineStatus.IN_REVIEW: "withdraw_submission",
    **{status: "request_deletion" for status in DELETE_REVIEW_STATUSES},
}


def record_capabilities(record, user, *, workflow, my_seats, routing, office_review,
                        revision, decision) -> list[str]:
    """Action keys offered by Record detail (ADR-032 §10, IR-418).

    These are rendering hints assembled from the same server predicates and
    action flags the endpoints use. An action still checks authority and state
    when called; a blocked action may be offered so its reason can be shown.
    `apps.records.test_capabilities` pairs every key with its endpoint.
    """
    from apps.documents.attachments import filing_party
    from apps.reviews.seats import add_reviewer_assignment

    offered = ["cite"]
    if not user or not getattr(user, "is_authenticated", False):
        return offered

    # A seat still to work is a review to open (IR-274 retired `can_act`).
    if any(seat["state"] in OPEN_SEAT_STATES for seat in my_seats):
        offered.append("open_review")
    if routing["send_to_rdco"]:
        offered.append("send_to_rdco")
    if routing["route_as"] is not None:
        offered.append("route")
    offered.extend(DECISION_CAPABILITY[outcome] for outcome in decision["outcomes"])
    if office_review["party"] is not None:
        offered.append("office_review")
    # `add-reviewer/`: an open seat on an active office assignment, RDCO's too.
    if add_reviewer_assignment(record, user) is not None:
        offered.append("add_reviewer")
    if workflow["can_request_document"]:
        offered.append("request_document")
    if revision["withdrawable"] is not None:
        offered.append("withdraw_revision")
    elif revision["party"] is not None:
        offered.append("request_revision")
    # `finish-review/`: anyone holding an open seat here, the party
    # `revision.party` names (ADR-032 §7, IR-874). Each verdict it carries is
    # still offered, and refused, by its own key above.
    if revision["party"] is not None:
        offered.append("finish_review")

    if is_record_owner(user, record):
        from apps.records.continuation import continuable

        if continuable(record):
            offered.append("continue_as")
        if workflow["workflow_state"] == PipelineStatus.DRAFT:
            offered.extend(["continue_draft", "edit_details"])
        elif workflow["workflow_state"] == WorkflowState.AWAITING_RESUBMISSION:
            if revision["new_version"] is not None:
                offered.extend(["create_version", "replace_manuscript"])
            offered.append("edit_details")
        delete_act = DELETE_CAPABILITY.get(record.pipeline_status)
        if delete_act is not None:
            offered.append(delete_act)

    # `embargo-set/` and `embargo-release/` (ADR-052 §5, §6), once submitted. A
    # draft has nothing to change: every paper starts embargoed (IR-882).
    if record.pipeline_status != PipelineStatus.DRAFT:
        if may_set_embargo(user, record):
            offered.append("set_embargo")
        if record.embargo_state == EmbargoState.ACTIVE and may_release_embargo(user, record):
            offered.append("release_embargo")
        from apps.records.ip_release import why_not_releasable

        if may_release_ip(user, record) and why_not_releasable(record) is None:
            offered.append("release_ip")

    # RDCO's three acts on a paper in review (ADR-051 §10, IR-797): `add-owner/`
    # and `withdraw/`, and `replace-adviser/` while an Adviser review is open.
    # The same predicates `rdco_acts` checks, so the hint cannot offer more.
    from apps.records import rdco_acts

    if rdco_acts.is_rdco(user) and record.pipeline_status == PipelineStatus.IN_REVIEW:
        if rdco_acts.adviser_review(record) is not None:
            offered.append("replace_adviser")
        offered.extend(["add_owner", "withdraw_paper"])

    # `review-comments/`: the record's participants, once it is submitted
    # (ADR-032 §7, IR-419). A pool member reads the discussion but is not
    # offered a place in it.
    if record.pipeline_status != PipelineStatus.DRAFT and is_record_participant(user, record):
        offered.append("comment_review")

    # Both role-gated endpoints refuse anyone who is not office staff
    # (`IsStaff`) before any other check, so the offers do too.
    office_staff = is_office_staff(user)
    # `tags/`: office staff, on any record they can see (decided 2026-10-11:
    # the offer follows the endpoint, no longer published records alone).
    if office_staff:
        offered.append("tag_ip")
    # `documents/files/upload/`: office staff whose office takes part (IR-474).
    # An Adviser takes part too, but is not staff, so is never offered it.
    if office_staff and filing_party(record, user) is not None:
        offered.append("attach_file")
    return offered


class MaySetEmbargo(BasePermission):
    def has_object_permission(self, request, view, obj):
        return may_set_embargo(request.user, obj)


class MayReleaseEmbargo(BasePermission):
    def has_object_permission(self, request, view, obj):
        return may_release_embargo(request.user, obj)


class MayReleaseIp(BasePermission):
    def has_object_permission(self, request, view, obj):
        return may_release_ip(request.user, obj)


class IsRecordOwner(BasePermission):
    """
    Object-level: the user owns the record. No staff role stands in for it.

    The record update, `submit/` and delete (IR-507, IR-508, ADR-032 §10
    Amendment): a record's details are its owners' to write, its Data Privacy
    Act consent an owner's to give, and its removal an owner's to start. The
    retired `IsOwnerOrStaff` let an office do all three on a record that was
    not theirs -- recorded as `dpa_accepted_by`, or as the requester of a
    delete request -- and was deleted with its last user (IR-508).
    """
    def has_object_permission(self, request, view, obj):
        return is_record_owner(request.user, obj)
