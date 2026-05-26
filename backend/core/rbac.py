"""
core/rbac.py  —  Role Permission Matrix (SDD §6.3)

Implements the RolePermissionMatrix described in the SDD class diagram:
  - get_permissions_for_role(role: str) -> List[str]
  - can_execute(role: str, action: str) -> bool

This is the single source-of-truth for which roles may perform which
actions. DRF permission classes in core/permissions.py delegate to this
matrix for coarse-grained role checks; fine-grained object-level checks
(e.g. "is this the record owner?") remain in the permission classes.

Action name constants are defined at module level so views can import
them instead of using raw strings, e.g.:

    from core.rbac import ACTION_APPROVE, RolePermissionMatrix
    if RolePermissionMatrix.can_execute(user_role, ACTION_APPROVE):
        ...
"""

# ---------------------------------------------------------------------------
# Action name constants  (match SDD §6.3 component table)
# ---------------------------------------------------------------------------

ACTION_VIEW_OWN    = "VIEW_OWN"           # View records the user owns
ACTION_VIEW_ALL    = "VIEW_ALL"           # View all submissions in the system
ACTION_APPROVE     = "APPROVE"            # Approve a pending submission
ACTION_REJECT      = "REJECT"             # Reject a pending submission
ACTION_EXPORT      = "EXPORT"             # Export records to Excel/PDF
ACTION_MANAGE_USERS = "MANAGE_USERS"      # Create / deactivate user accounts


# ---------------------------------------------------------------------------
# Role ↔ Action permission matrix
# ---------------------------------------------------------------------------
#
# Roles match Role.name values stored in the database exactly.
# To grant a new role a permission, add the action to its set here.
#
_MATRIX: dict[str, set[str]] = {
    "Student": {
        ACTION_VIEW_OWN,
    },
    "Adviser": {
        ACTION_VIEW_OWN,
        ACTION_APPROVE,
        ACTION_REJECT,
    },
    "KTTO": {
        ACTION_VIEW_OWN,
        ACTION_VIEW_ALL,
        ACTION_APPROVE,
        ACTION_REJECT,
        ACTION_EXPORT,
        ACTION_MANAGE_USERS,
    },
    "RDCO": {
        ACTION_VIEW_OWN,
        ACTION_VIEW_ALL,
        ACTION_APPROVE,
        ACTION_REJECT,
        ACTION_EXPORT,
        ACTION_MANAGE_USERS,
    },
    "ITSO": {
        ACTION_VIEW_OWN,
        ACTION_VIEW_ALL,
        ACTION_EXPORT,
    },
    "IERC": {
        ACTION_VIEW_OWN,
        ACTION_VIEW_ALL,
    },
    "TBI": {
        ACTION_VIEW_OWN,
        ACTION_VIEW_ALL,
        ACTION_APPROVE,
        ACTION_REJECT,
    },
}


# ---------------------------------------------------------------------------
# RolePermissionMatrix  (SDD §6.3 class diagram)
# ---------------------------------------------------------------------------

class RolePermissionMatrix:
    """
    Configurable mapping of roles to permitted actions.

    All methods are class-level (no instantiation needed) so callers
    simply write:

        RolePermissionMatrix.can_execute('Student', ACTION_VIEW_ALL)
        # → False

        RolePermissionMatrix.get_permissions_for_role('KTTO')
        # → ['VIEW_OWN', 'VIEW_ALL', 'APPROVE', 'REJECT', 'EXPORT', 'MANAGE_USERS']
    """

    @classmethod
    def get_permissions_for_role(cls, role: str) -> list[str]:
        """
        Return the sorted list of action names permitted for *role*.
        Returns an empty list for unrecognised roles.
        """
        return sorted(_MATRIX.get(role, set()))

    @classmethod
    def can_execute(cls, role: str, action: str) -> bool:
        """
        Return True if *role* is permitted to perform *action*.
        Django superusers / is_staff bypass is handled at the view layer
        (core/permissions.py); this method is purely matrix-driven.
        """
        return action in _MATRIX.get(role, set())
