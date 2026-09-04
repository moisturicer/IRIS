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
ADMIN_ROLES    = {ROLE_KTTO, ROLE_RDCO}
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


def is_django_staff(user) -> bool:
    """True for Django superusers and staff accounts (no role required)."""
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_STUDENT


class IsAdviser(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_ADVISER


class IsKTTO(BasePermission):
    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) == ROLE_KTTO


class IsRDCO(BasePermission):
    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) == ROLE_RDCO


class IsITSO(BasePermission):
    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) == ROLE_ITSO


class IsIERC(BasePermission):
    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) == ROLE_IERC


class IsReviewer(BasePermission):
    """Adviser, KTTO, RDCO, ITSO, or IERC — or any Django staff account."""
    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) in REVIEWER_ROLES


class IsStaff(BasePermission):
    """KTTO, RDCO, ITSO, or IERC — or any Django staff account."""
    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) in STAFF_ROLES


class IsAdmin(BasePermission):
    """KTTO, RDCO, or any Django staff/superuser (account management, delete approvals)."""
    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) in ADMIN_ROLES


class IsOpportunityPoster(BasePermission):
    """RDCO, KTTO or Adviser — or any Django staff account. See IR-121."""
    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) in OPPORTUNITY_POSTER_ROLES


class IsOwnerOrStaff(BasePermission):
    """
    Object-level: the user owns the record OR is a staff member.
    The view must attach `obj.owners` as a queryset or list of users.
    """
    def has_object_permission(self, request, view, obj):
        if is_django_staff(request.user) or get_role_name(request.user) in STAFF_ROLES:
            return True
        return obj.owners.filter(user=request.user).exists()
