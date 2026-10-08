from rest_framework.permissions import BasePermission

from core.enums import OPEN_SEAT_STATES, AssignmentState, Party, RoleName

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

# Convenience sets
REVIEWER_ROLES = {ROLE_ADVISER, ROLE_KTTO, ROLE_RDCO, ROLE_ITSO, ROLE_IERC}
STAFF_ROLES    = {ROLE_KTTO, ROLE_RDCO, ROLE_ITSO, ROLE_IERC}
ADMIN_ROLES    = {ROLE_RDCO}
# Who may author a disclosure. SRS Use Cases M2-2.1 (Create IP Disclosure Draft)
# and M2-2.2 (Submit Record for Review) both name the actor "Record Owner
# (Student or Adviser)". Deliberately excludes the clearing offices -- ITSO,
# IERC and KTTO must not author records they may later clear -- and RDCO, which
# performs both intake and final review, so authoring would mean reviewing its
# own record at two of the three gates. RDCO files on behalf of others through
# the bulk import path instead.
AUTHOR_ROLES   = {ROLE_STUDENT, ROLE_ADVISER}
# Who may publish a Calls & Conferences opportunity (IR-121). Deliberately not
# STAFF_ROLES: that set includes ITSO/IERC, who review clearances and have no
# reason to post calls, and excludes Adviser, who is exactly the "teacher
# posting a departmental call" the feature was asked for. Students never post.
OPPORTUNITY_POSTER_ROLES = {ROLE_RDCO, ROLE_KTTO, ROLE_ADVISER}
# Who may correct or remove *someone else's* posting. Deliberately its own set
# rather than a reference to ADMIN_ROLES: when IR-165 narrowed ADMIN_ROLES to
# {RDCO}, borrowing it here would have silently stripped KTTO of the moderation
# its own docstring promises -- a change to IR-121's behaviour with no ticket
# behind it. An institutional noticeboard needs two people who can fix a
# deadline when the poster is unavailable.
OPPORTUNITY_MODERATOR_ROLES = {ROLE_RDCO, ROLE_KTTO}


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


class IsStaff(BasePermission):
    """KTTO, RDCO, ITSO or IERC. Role only -- see the module note on is_staff."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in STAFF_ROLES


class IsAdmin(BasePermission):
    """RDCO alone: account administration, the audit log, and the request queues."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in ADMIN_ROLES


class IsOpportunityPoster(BasePermission):
    """
    Who may post a call, and who may then edit or delete one. See IR-121.

    `has_permission` gates *posting* by role: RDCO, KTTO or Adviser (or Django
    staff). `has_object_permission` gates *editing an existing posting*, and the
    two are deliberately different — without the second, every Adviser in the
    university could rewrite or delete RDCO's grant announcements, because they
    share a role bucket. Role membership answers "may you post?", never "is this
    yours?".

    The rule mirrors `IsOwnerOrStaff` below: the person who posted it, or an
    admin (RDCO/KTTO/Django staff) acting as a moderator. An Adviser can edit
    only their own call; RDCO and KTTO can correct anyone's, which is what an
    institutional noticeboard needs when a deadline changes and the poster is
    unavailable. Narrow that to poster-only if the team prefers.
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
      right now, its pool included -- someone about to claim, or a reviewer on
      the legacy pipeline deciding straight from the pool, needs the history
      before acting. The server twin of the frontend's `isParticipant`.

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


class IsOwnerOrStaff(BasePermission):
    """
    Object-level: the user owns the record OR is a staff member.
    The view must attach `obj.owners` as a queryset or list of users.
    """
    def has_object_permission(self, request, view, obj):
        return owns_or_staffs_record(request.user, obj)
