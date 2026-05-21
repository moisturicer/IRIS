from rest_framework.permissions import BasePermission

# Role name constants -- match the Role.name values in the DB exactly
ROLE_STUDENT = "Student"
ROLE_ADVISER = "Adviser"
ROLE_KTTO    = "KTTO"
ROLE_RDCO    = "RDCO"
ROLE_ITSO    = "ITSO"
ROLE_TBI     = "TBI"

# Convenience sets
REVIEWER_ROLES = {ROLE_ADVISER, ROLE_KTTO, ROLE_RDCO, ROLE_TBI}
STAFF_ROLES    = {ROLE_KTTO, ROLE_RDCO, ROLE_ITSO, ROLE_TBI}
ADMIN_ROLES    = {ROLE_KTTO, ROLE_RDCO}


def get_role_name(user) -> str:
    """Return the user's role name, or empty string if not set."""
    try:
        return user.role.name
    except AttributeError:
        return ""


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


class IsTBI(BasePermission):
    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_TBI


class IsReviewer(BasePermission):
    """Adviser, KTTO, RDCO, or TBI."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in REVIEWER_ROLES


class IsStaff(BasePermission):
    """KTTO, RDCO, ITSO, or TBI (dashboard access)."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in STAFF_ROLES


class IsAdmin(BasePermission):
    """KTTO or RDCO only (account management, delete approvals)."""
    def has_permission(self, request, view):
        return get_role_name(request.user) in ADMIN_ROLES


class IsOwnerOrStaff(BasePermission):
    """
    Object-level: the user owns the record OR is a staff member.
    The view must attach `obj.owners` as a queryset or list of users.
    """
    def has_object_permission(self, request, view, obj):
        if get_role_name(request.user) in STAFF_ROLES:
            return True
        return obj.owners.filter(user=request.user).exists()
