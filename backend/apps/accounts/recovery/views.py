"""The anonymous recovery HTTP contract (ADR-045 §2).

Every response here is one of a few fixed bodies, so nothing a client sees
depends on whether an address has an account. These views authenticate no
one -- an Authorization header is ignored -- and use none of DRF's
process-local throttles: `limits` is the throttle, shared across workers.
"""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import DatabaseError
from rest_framework.exceptions import MethodNotAllowed, ParseError, UnsupportedMediaType
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import RecoveryPurpose, User

from . import limits, service

MAX_BODY_BYTES = 4096
MAX_EMAIL_LENGTH = 254

#: How long a client is told to wait after a 503: no counter can say.
UNAVAILABLE_RETRY_SECONDS = 60
INVALID_LINK = {
    "code": "invalid_link",
    "detail": "This link is invalid or no longer available. Request a new email.",
}
UNAVAILABLE = {
    "code": "temporarily_unavailable",
    "detail": "Unable to process this request. Try again later.",
    "retry_after": UNAVAILABLE_RETRY_SECONDS,
}


def request_received() -> dict:
    """The one answer to every well-formed request (§2), naming the cooldown."""
    seconds = settings.RECOVERY_COOLDOWN_SECONDS
    return {
        "code": "request_received",
        "detail": "If this address is eligible, an email will arrive shortly. "
                  f"You can try again after {seconds} seconds.",
        "retry_after": seconds,
    }


class FieldErrors(Exception):
    def __init__(self, errors: dict):
        super().__init__(errors)
        self.errors = errors


def _no_store(response):
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def strings(data, required: tuple[str, ...]) -> dict:
    """The named string fields of a JSON object, or `FieldErrors`."""
    if not isinstance(data, dict):
        raise FieldErrors({"non_field_errors": ["Invalid value."]})
    errors = {name: ["Unknown field."] for name in data if name not in required}
    values = {}
    for name in required:
        if name not in data:
            errors[name] = ["This field is required."]
        elif not isinstance(data[name], str):
            errors[name] = ["Invalid value."]
        else:
            values[name] = data[name]
    if errors:
        raise FieldErrors(errors)
    return values


def normalized_email(value: str) -> str:
    """Stripped, domain lowercased, local part as typed -- the account rule."""
    address = value.strip()
    if not address or len(address) > MAX_EMAIL_LENGTH:
        raise FieldErrors({"email": ["Enter a valid email address."]})
    try:
        validate_email(address)
    except DjangoValidationError:
        raise FieldErrors({"email": ["Enter a valid email address."]}) from None
    return User.objects.normalize_email(address)


class RecoveryView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []
    parser_classes = [JSONParser]
    #: Which counter this endpoint's requests are counted against.
    limit_action = ""

    def limit_windows(self):
        raise NotImplementedError

    def post(self, request):
        length = request.META.get("CONTENT_LENGTH") or "0"
        if not length.isdigit() or int(length) > MAX_BODY_BYTES or len(request.body) > MAX_BODY_BYTES:
            return _no_store(Response(
                {"code": "payload_too_large", "detail": "Request body is too large."}, status=413,
            ))
        # A 415 is refused before counting; a body that is JSON-typed but not
        # JSON is still an attempt, so it is counted before it is refused.
        try:
            data, malformed = request.data, None
        except ParseError as exc:
            data, malformed = None, exc
        limits.admit_address(self.limit_action, limits.client_ip(request), self.limit_windows())
        if malformed is not None:
            raise malformed
        return self.handle(data)

    def handle(self, data):
        raise NotImplementedError

    def handle_exception(self, exc):
        if isinstance(exc, limits.Throttled):
            response = Response(
                {"code": "rate_limited", "detail": "Too many requests. Try again later.",
                 "retry_after": exc.retry_after},
                status=429,
            )
            response["Retry-After"] = str(exc.retry_after)
            return _no_store(response)
        if isinstance(exc, FieldErrors):
            return _no_store(Response({"code": "validation_error", "errors": exc.errors}, status=400))
        if isinstance(exc, service.PasswordRejected):
            return _no_store(Response({"code": "validation_error", "errors": exc.errors}, status=400))
        if isinstance(exc, service.InvalidLink):
            return _no_store(Response(INVALID_LINK, status=400))
        if isinstance(exc, ParseError):
            return _no_store(Response(
                {"code": "validation_error", "errors": {"non_field_errors": ["Invalid value."]}}, status=400,
            ))
        if isinstance(exc, DatabaseError):
            # The counters and the intent live in the database: without it,
            # no limit can be enforced and nothing can be accepted durably.
            response = Response(UNAVAILABLE, status=503)
            response["Retry-After"] = str(UNAVAILABLE_RETRY_SECONDS)
            return _no_store(response)
        if isinstance(exc, (MethodNotAllowed, UnsupportedMediaType)):
            return _no_store(super().handle_exception(exc))
        return super().handle_exception(exc)


class PasswordResetRequestView(RecoveryView):
    """POST /auth/password/reset/request/  {"email": "..."} -> always 202."""
    limit_action = "reset_request"

    def limit_windows(self):
        return limits.request_windows()

    def handle(self, data):
        email = normalized_email(strings(data, ("email",))["email"])
        service.admit_request(RecoveryPurpose.PASSWORD_RESET, email)
        return _no_store(Response(request_received(), status=202))


class PasswordResetConfirmView(RecoveryView):
    """POST /auth/password/reset/confirm/  {"token", "new_password", "confirm_password"}."""
    limit_action = "reset_confirm"

    def limit_windows(self):
        return limits.confirm_windows()

    def handle(self, data):
        fields = strings(data, ("token", "new_password", "confirm_password"))
        service.confirm_reset(fields["token"], fields["new_password"], fields["confirm_password"])
        return _no_store(Response({
            "code": "password_reset",
            "detail": "Password updated. Sign in with your new password.",
        }))
