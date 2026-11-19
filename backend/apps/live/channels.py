"""
Who hears a hint (ADR-073 decision 3), as Redis channel names.

The server assigns every channel. A browser never names one: the stream
subscribes each connection to its own user's channel and its role's, and a
publish names the people or the role that should refetch. IRIS's offices are
roles (ITSO, IERC, KTTO, RDCO), so an office's pool and its role share one
channel, `live:role:<role>`.
"""
from core.enums import Party

PREFIX = "live:"

#: Parties that are offices, whose pool has a channel. The Adviser party is a
#: person, never a pool: their changes go to the seat holder's own channel.
OFFICE_PARTIES = frozenset(str(p) for p in (Party.ITSO, Party.IERC, Party.KTTO, Party.RDCO))


def user_channel(user_id) -> str:
    return f"{PREFIX}user:{int(user_id)}"


def role_channel(role_name: str) -> str:
    return f"{PREFIX}role:{role_name.strip().lower()}"


def channels_for(user) -> list[str]:
    """The channels a signed-in account's stream listens on."""
    names = [user_channel(user.pk)]
    role = getattr(getattr(user, "role", None), "name", "") or ""
    if role:
        names.append(role_channel(role))
    return names


# --- topics: what a page reloads on (decision 1) --------------------------------

NOTIFICATIONS = "notifications"
REVIEWS = "reviews"
LIBRARY = "library"
QUEUES = "queues"


def record_topic(record_id) -> str:
    return f"record:{int(record_id)}"
