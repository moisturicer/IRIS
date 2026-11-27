"""
The student guided tours an account has been shown (IR-1342).

A newly registered Student is walked through each main page the first time it
opens it, and through the Publish dialog the first time it opens. Which tours
an account has seen is remembered on the account (`User.tours_seen`), so a tour
runs once on any browser or device, not once per browser.

`TOUR_KEYS` is the closed list of tours. The server accepts no other key, and
the frontend reads the same list from `frontend/src/features/onboarding/
tourKeys.json`; `test_tours.py` fails if the two differ.

**Adding a tour later.** Append its key here and to the JSON file. Migration
`0025_tours_seen` marked every account that existed when it ran as having seen
the keys *as they were then*, frozen inside that migration. So a key added
afterwards is offered to every Student who has not seen it, including students
who registered before it existed. If a new tour must reach new accounts only,
its change ships with its own data migration marking existing accounts, as
`0025` did. That is decided per tour, in the change that adds it.
"""
from __future__ import annotations

from django.db import transaction

TOUR_KEYS: tuple[str, ...] = (
    "discover",
    "library",
    "ask",
    "calls",
    "guidelines",
    "notifications",
    "publish",
)


class UnknownTour(ValueError):
    """A key that is not in `TOUR_KEYS`."""


def mark_seen(user, key: str) -> list[str]:
    """Record that `user` has been shown tour `key`, and return their seen keys.

    Idempotent. The row is locked for the read-modify-write, so two tabs
    finishing two tours at once both land; nothing else on the row is written.
    """
    if key not in TOUR_KEYS:
        raise UnknownTour(key)
    from apps.accounts.models import User

    with transaction.atomic():
        seen = User.objects.select_for_update().values_list("tours_seen", flat=True).get(pk=user.pk)
        seen = list(seen or [])
        if key not in seen:
            seen.append(key)
            User.objects.filter(pk=user.pk).update(tours_seen=seen)
    user.tours_seen = seen
    return seen
