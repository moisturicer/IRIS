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


def is_django_staff(user) -> bool:
    """True for Django superusers and staff accounts (no role required)."""
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))


class IsStudent(BasePermission):
    required_role = ROLE_STUDENT

    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_STUDENT


class IsAdviser(BasePermission):
    required_role = ROLE_ADVISER

    def has_permission(self, request, view):
        return get_role_name(request.user) == ROLE_ADVISER


class IsKTTO(BasePermission):
    required_role = ROLE_KTTO

    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) == ROLE_KTTO


class IsRDCO(BasePermission):
    required_role = ROLE_RDCO

    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) == ROLE_RDCO


class IsITSO(BasePermission):
    required_role = ROLE_ITSO

    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) == ROLE_ITSO


class IsTBI(BasePermission):
    required_role = ROLE_TBI

    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) == ROLE_TBI


class IsReviewer(BasePermission):
    """Adviser, KTTO, RDCO, or TBI — or any Django staff account."""
    required_role = "Reviewer (Adviser, KTTO, RDCO, or TBI)"

    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) in REVIEWER_ROLES


class IsStaff(BasePermission):
    """KTTO, RDCO, ITSO, or TBI — or any Django staff account."""
    required_role = "Staff (KTTO, RDCO, ITSO, or TBI)"

    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) in STAFF_ROLES


class IsAdmin(BasePermission):
    """KTTO, RDCO, or any Django staff/superuser (account management, delete approvals)."""
    required_role = "Admin (KTTO or RDCO)"

    def has_permission(self, request, view):
        return is_django_staff(request.user) or get_role_name(request.user) in ADMIN_ROLES


class IsOwnerOrStaff(BasePermission):
    """
    Object-level: the user owns the record OR is a staff member.
    The view must attach `obj.owners` as a queryset or list of users.
    """
    required_role = "Record Owner or Staff"

    def has_object_permission(self, request, view, obj):
        if is_django_staff(request.user) or get_role_name(request.user) in STAFF_ROLES:
            return True
        return obj.owners.filter(user=request.user).exists()

