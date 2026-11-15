"""
What a sign-in refusal writes to the audit log (IR-659, ASVS 7.2.1).

Every refusal is one `FAILED_LOGIN` row whose `metadata` is exactly the email
tried, a `reason` and the client address (`client_address`, IR-656). Never a
password, a token or a link (ASVS 7.1.1). Decided 2026-11-15 (Hermoine
Zozobrado): the row names the account only when the password proved who it is
(`unverified`, `locked_by_admin`), so a guess at someone's address adds nothing
to their history; and axes writes one row per attempt it refuses, from its
lockout callable, in place of the view's.
"""
from __future__ import annotations

from apps.audit.services import create_audit_event

from .client_address import client_address
from .lockout import LOCKED_BY_ADMIN, TOO_MANY_ATTEMPTS  # noqa: F401  (the reasons, as the client is told them)

INVALID_CREDENTIALS = "invalid_credentials"
UNVERIFIED = "unverified"


def refused(request, email, reason, *, user=None) -> None:
    """One `FAILED_LOGIN` for this request. `request` is Django's, not DRF's wrapper."""
    create_audit_event(
        "FAILED_LOGIN", user,
        metadata={"email": email, "reason": reason, "ip": client_address(request)},
    )


def axes_refused(request) -> bool:
    """Axes refused this request (it marks it, IR-555): its lockout callable writes the row."""
    return bool(getattr(request, "axes_locked_out", False))
