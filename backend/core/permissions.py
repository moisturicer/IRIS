from rest_framework.permissions import BasePermission

# Role name constants -- match the Role.name values in the DB exactly
ROLE_STUDENT = "Student"
ROLE_ADVISER = "Adviser"
ROLE_KTTO    = "KTTO"
ROLE_RDCO    = "RDCO"
ROLE_ITSO    = "ITSO"
ROLE_IERC    = "IERC"

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


def get_role_name(user) -> str:
    """Return the user's role name, or empty string if not set."""
    try:
        return user.role.name
    except AttributeError:
        return ""


def is_django_admin_site_user(user) -> bool:
    """
    True for accounts that may open the Django admin site at /admin.

    **Not an authorization signal for this API.** It was one, and that was the
    defect IR-165 closed: `is_staff` answers "may you open the Django admin
    site", never "may you approve an IP disclosure". Migration `accounts/0005`
    set `is_staff = True` on every office role, so every permission class that
    began `is_django_staff(user) or ...` short-circuited to True for RDCO, KTTO,
    ITSO and IERC alike -- `ADMIN_ROLES` constrained nobody and the audit log,
    intended for RDCO, admitted all four offices.

    Nothing in `core.permissions` calls this. It exists so the distinction has a
    name, and so `apps/tests/test_authorization_matrix.py` can assert that a
    role-less superuser is refused by the API.
    """
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))


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
    """Adviser, KTTO, RDCO, ITSO, or IERC — or any Django staff account."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in REVIEWER_ROLES


class IsStaff(BasePermission):
    """KTTO, RDCO, ITSO, or IERC — or any Django staff account."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in STAFF_ROLES


class IsAdmin(BasePermission):
    """KTTO, RDCO, or any Django staff/superuser (account management, delete approvals)."""
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
        if get_role_name(request.user) in ADMIN_ROLES:
            return True
        return obj.posted_by_id == request.user.pk


class IsOwnerOrStaff(BasePermission):
    """
    Object-level: the user owns the record OR is a staff member.
    The view must attach `obj.owners` as a queryset or list of users.
    """
    def has_object_permission(self, request, view, obj):
        if get_role_name(request.user) in STAFF_ROLES:
            return True
        return obj.owners.filter(user=request.user).exists()
