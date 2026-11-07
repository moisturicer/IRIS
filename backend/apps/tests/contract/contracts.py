"""
The responses the contract test records and checks (IR-915).

One entry per fixture file in the repository's `contracts/` directory. Each
names the route, who asks, and what they send, against the same world the
access matrix uses (`apps/tests/access/world.py`), so a state every screen
reads (a paper in review, a published one, an owner's tracker) exists here
without a second fixture world.

**Slice 1**: the non-AI endpoints Discover, Paper View, My Library, My Reviews
and sign-in read. The AI endpoints are a second slice, through the
deterministic fake provider and with the AI area's owner told first.

Adding an entry fails the test until its fixture is recorded:

    UPDATE_CONTRACTS=1 python -m pytest apps/tests/contract -q

and the frontend maps the fixture to its type in
`frontend/src/test/contract/contract.test.ts`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.tests.access.world import World


@dataclass(frozen=True)
class Contract:
    #: The fixture's file name: `contracts/<name>.json`.
    name: str
    #: The URL name, as the access matrix keys it.
    route: str
    method: str
    #: A role of `world.ROLES`; `anon` sends no credentials.
    role: str
    #: URL kwargs, each the name of a world object whose pk it takes.
    kwargs: tuple[tuple[str, str], ...] = ()
    query: tuple[tuple[str, str], ...] = ()
    #: The request body, built from the world (a login names an account in it).
    body: Callable[[World], dict] | None = None
    #: Keys whose values are replaced in the stored sample (credentials).
    redact: tuple[str, ...] = ()


CONTRACTS: tuple[Contract, ...] = (
    # Discover and the paper page.
    Contract("record-list", "record-list", "GET", "other"),
    Contract("record-detail", "record-detail", "GET", "owner", kwargs=(("pk", "record"),)),
    Contract("record-detail-published", "record-detail", "GET", "other", kwargs=(("pk", "published"),)),
    Contract("record-tracker", "record-tracker", "GET", "owner", kwargs=(("pk", "record"),)),
    Contract("record-facets", "record-facets", "GET", "other"),
    Contract("classifications", "classifications", "GET", "other"),
    Contract("record-document-requests", "record-document-requests", "GET", "owner",
             kwargs=(("pk", "record"),)),
    # My Library and My Reviews.
    Contract("record-mine", "record-mine", "GET", "owner"),
    Contract("library-saves", "library-saves", "GET", "owner"),
    Contract("reviews-mine", "reviews-mine", "GET", "seated", query=(("tab", "in_review"),)),
    # Sign-in and the signed-in account.
    Contract("auth-login", "auth-login", "POST", "anon",
             body=lambda world: {"email": world.users["owner"].email, "password": "IrisDemo123!"},
             redact=("access", "refresh")),
    Contract("user-me", "user-me", "GET", "owner"),
)
