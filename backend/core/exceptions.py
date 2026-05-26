from rest_framework.exceptions import APIException
from rest_framework import status


class RecordNotFound(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Record not found."


class NotRecordOwner(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not own this record."


class RecordAlreadyApproved(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This record has already been approved and cannot be modified."


class InvalidPipelineTransition(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This pipeline status transition is not allowed."


class PinInvalid(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The PIN is invalid or has already been used."


# ---- RBAC Enforcement Exception Handler (FR-M6-03) ----------------------
#
# Intercepts PermissionDenied responses to:
# 1. Return an enriched 403 with RBAC diagnostic info
#    (authenticated role vs required role).
# 2. Log the access violation to the AuditEvent table as
#    UNAUTHORIZED_BYPASS — matching the SRS wireframe.

import logging
from rest_framework.views import exception_handler
from rest_framework.exceptions import PermissionDenied

_logger = logging.getLogger("iris.security")


def rbac_exception_handler(exc, context):
    """
    Drop-in replacement for DRF's default exception handler.

    When a PermissionDenied is raised, this handler:
    - Builds an RBAC diagnostic payload showing authenticated vs required role.
    - Creates an UNAUTHORIZED_BYPASS AuditEvent for the immutable audit log.
    - Returns a structured 403 JSON response matching the SRS wireframe.

    All other exceptions are delegated to DRF's default handler unchanged.
    """
    response = exception_handler(exc, context)

    if response is not None and isinstance(exc, PermissionDenied):
        request = context.get("request")
        view = context.get("view")

        # --- Determine the user's authenticated role ---
        authenticated_role = _get_user_role(request)

        # --- Determine the required role from the permission class ---
        required_role = _get_required_role(exc, view)

        # --- Build the enriched 403 response ---
        response.data = {
            "detail": (
                "You do not have the required role-based permissions "
                "to access this workflow tier."
            ),
            "status_code": 403,
            "rbac_diagnostic": {
                "authenticated_role": authenticated_role,
                "required_role": required_role,
            },
            "audit_note": "Access violation attempt logged in AuditLog.",
        }

        # --- Log to the audit table ---
        _log_unauthorized_bypass(request, view, authenticated_role, required_role)

    return response


def _get_user_role(request) -> str:
    """Return the human-readable role name for the authenticated user."""
    if request and hasattr(request, "user") and request.user.is_authenticated:
        try:
            return request.user.role.name
        except AttributeError:
            return "NO_ROLE_ASSIGNED"
    return "ANONYMOUS"


def _get_required_role(exc, view) -> str:
    """
    Best-effort extraction of the required role from the permission
    class that denied access.

    Permission classes in core/permissions.py set a `required_role`
    attribute so we can surface it in the 403 diagnostic.
    Falls back to the exception detail message.
    """
    if view:
        for perm_class in getattr(view, "permission_classes", []):
            cls = perm_class if isinstance(perm_class, type) else type(perm_class)
            required = getattr(cls, "required_role", None)
            if required:
                return required

    return str(getattr(exc, "detail", "Unknown"))


def _log_unauthorized_bypass(request, view, authenticated_role, required_role):
    """
    Create an UNAUTHORIZED_BYPASS AuditEvent.
    Wrapped in try/except so a logging failure never blocks the 403 response.
    """
    try:
        from apps.audit.models import AuditEvent

        user = None
        if request and hasattr(request, "user") and request.user.is_authenticated:
            user = request.user

        view_name = ""
        if view:
            view_name = f"{type(view).__name__}.{getattr(view, 'action', request.method)}"

        AuditEvent.objects.create(
            event_type=AuditEvent.UNAUTHORIZED_BYPASS,
            user=user,
            metadata={
                "authenticated_role": authenticated_role,
                "required_role": required_role,
                "method": request.method if request else "",
                "path": request.get_full_path() if request else "",
                "view": view_name,
            },
        )

        _logger.warning(
            "UNAUTHORIZED_BYPASS: user=%s role=%s required=%s path=%s",
            user,
            authenticated_role,
            required_role,
            request.get_full_path() if request else "?",
        )
    except Exception:
        # Never let audit logging break the API response
        _logger.exception("Failed to log UNAUTHORIZED_BYPASS audit event")

