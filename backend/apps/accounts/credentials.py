"""Ending every existing credential when a password changes (ADR-045 §4).

One primitive for both a reset and an authenticated change, so neither can
leave a sign-in or a reset link alive by forgetting a step:

- `User.credential_version` goes up, and every access and refresh token
  carries the old number in its `cv` claim, so authentication and refresh
  refuse them from the next request (`apps.accounts.authentication`);
- every open `UserSession` ends and every outstanding refresh token is
  blacklisted, so the sessions list says so too;
- every unused reset link is revoked -- it was bound to the old version, and
  this makes the revocation visible rather than implied;
- a Django-auth session dies with the password hash it was keyed on.

Verification links survive: only a reset is bound to the password (§3).
"""

from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import RecoveryPurpose, RecoveryToken, UserSession
from core.enums import SessionEndReason


def set_password_and_invalidate(user, raw_password, at) -> None:
    """Store ``raw_password`` and end every credential ``user`` held.

    The caller holds ``user``'s row lock (``select_for_update``) inside a
    transaction, so a concurrent sign-in serialises against it: `LoginView`
    takes the same lock before it mints tokens.
    """
    user.set_password(raw_password)
    user.credential_version += 1
    user.save(update_fields=["password", "credential_version"])

    UserSession.objects.filter(user=user, ended_at__isnull=True).update(
        ended_at=at, ended_reason=SessionEndReason.PASSWORD_CHANGED,
    )
    outstanding = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in outstanding], ignore_conflicts=True
    )
    RecoveryToken.objects.filter(
        user=user, purpose=RecoveryPurpose.PASSWORD_RESET,
        consumed_at__isnull=True, revoked_at__isnull=True,
    ).update(revoked_at=at)
