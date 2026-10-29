"""
What a table cell says, and how one is fired and judged (IR-615).

A cell is one role making one request. Its declared outcome is one of four,
and they are judged on HTTP behaviour alone, never on permission classes:

* `ANON`  401 -- no credentials, refused before anything is looked up.
* `DENY`  403 -- the caller may know the object exists, and may not do this.
* `HIDE`  404 -- the caller may not know the object exists. The response must
          be **byte-for-byte the response to the same request naming an id
          that does not exist** (IR-153; ADR-022 §Amendment 4), or it confirms
          what it refuses to show.
* `OK`        -- authorization passed: anything but 401, 403, 404, 405 or a
          server error. A permitted caller may still get a 400 for the moment
          (submitting a record already in review) or the body; asserting 200
          would couple the matrix to every serializer and fixture, and fail
          for reasons it does not test (the IR-165 matrix's rule 2).

A cell may also be a `KnownDefect`: the outcome the route *should* have, with
the filed `area-security` bug that says it does not yet. The cell passes
while the route still misbehaves and **fails the day it starts behaving
correctly**, so the marker is removed when the bug is fixed and never
outlives it. The declared outcome is never loosened to match the code.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable


class Outcome(enum.Enum):
    ANON = 401
    DENY = 403
    HIDE = 404
    OK = 0
    STUB = 501  # A declared, unimplemented endpoint; never accepted by OK.


ANON, DENY, HIDE, OK, STUB = Outcome.ANON, Outcome.DENY, Outcome.HIDE, Outcome.OK, Outcome.STUB

#: Statuses that are never an `OK`: each is a refusal, a wrong method, or a fault.
NOT_PERMITTED = {401, 403, 404, 405}


@dataclass(frozen=True)
class KnownDefect:
    """The correct outcome, and the bug filed because the route does not give it."""

    should_be: Outcome
    issue: str
    #: What the route does instead, so the cell says what is wrong in one line.
    does: str


Cell = Outcome | KnownDefect


@dataclass(frozen=True)
class Ref:
    """A fixture object's id (or another attribute), resolved when the request is built."""

    name: str
    attr: str = "pk"


#: Replaced by a fresh upload each time a request is built.
@dataclass(frozen=True)
class Upload:
    filename: str = "paper.pdf"


#: Replaced by the world's download token.
DOWNLOAD_TOKEN = object()


@dataclass(frozen=True)
class Call:
    """How to fire a route: path kwargs, query string and body, any of them `Ref`s."""

    kwargs: dict = field(default_factory=dict)
    query: dict = field(default_factory=dict)
    data: dict | None = None
    format: str = "json"
    objects: tuple[str, ...] = ()  # Body/query ids governed by object visibility.

    @property
    def refs(self) -> set[str]:
        found: set[str] = set()

        def scan(value):
            if isinstance(value, Ref):
                found.add(value.name)
            elif isinstance(value, dict):
                for v in value.values():
                    scan(v)
            elif isinstance(value, (list, tuple)):
                for v in value:
                    scan(v)

        scan([self.kwargs, self.query, self.data])
        return found

    @property
    def object_refs(self) -> set[str]:
        """The fixtures named in the path: what makes this an object route."""
        return {v.name for v in self.kwargs.values() if isinstance(v, Ref)} | set(self.objects)


def resolve(value, lookup: Callable[[Ref], object], token: str):
    if isinstance(value, Ref):
        return lookup(value)
    if isinstance(value, Upload):
        from .world import pdf

        return pdf(value.filename)
    if value is DOWNLOAD_TOKEN:
        return token
    if isinstance(value, dict):
        return {k: resolve(v, lookup, token) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, lookup, token) for v in value]
    return value


@dataclass(frozen=True)
class Case:
    """One way of calling a route, and what each role gets."""

    call: Call
    cells: tuple[Cell, ...]
    #: Names a case when a method needs more than one (a valid and a forged token).
    label: str = ""

    def cell(self, role: str) -> Cell:
        from .world import ROLES

        return self.cells[ROLES.index(role)]


def row(*cells: Cell) -> tuple[Cell, ...]:
    """One cell per role, in `world.ROLES` order."""
    from .world import ROLES

    if len(cells) != len(ROLES):
        raise ValueError(f"a row has {len(ROLES)} cells, one per role in {ROLES}; got {len(cells)}")
    return cells


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


@dataclass(frozen=True)
class Observed:
    """One role's response to a case, and what it gets when the object is missing."""

    response: Response
    #: The same request with each path id in turn replaced by a missing one.
    #: Empty for a route with no object in its path.
    missing: tuple[Response, ...] = ()
    #: May this role know the path's object exists? (`World.can_see`)
    can_see: bool = True
    #: Why this route may answer a hidden object differently from a missing
    #: one, citing where that was decided. Empty: it may not.
    waiver: str = ""


def _reads_as_missing(observed: Observed) -> bool:
    return any(observed.response == m for m in observed.missing)


def judge(declared: Cell, observed: Observed) -> tuple[bool, str]:
    """
    Did `observed` give the `declared` outcome?

    Two checks on top of the status. A `HIDE` must read exactly like a
    missing id. And **any** refusal of a role that may not know the object
    exists -- a 403 as much as a 404 -- must read like a missing id too,
    whatever the table says, unless the route carries a cited waiver: that is
    the IR-153 rule, and it is checked from visibility, not from the table, so
    a wrong row cannot excuse a leak.

    Reading like *any* missing variant is enough. A role that gets the same
    answer for this object as for some id that does not exist has learned
    nothing, and a nested route (a version of a record) has one variant per
    level.
    """
    status, body = observed.response.status, observed.response.body
    if isinstance(declared, KnownDefect):
        correct, _ = judge(declared.should_be, observed)
        if correct:
            return False, (
                f"now gives {declared.should_be.name} as declared-correct, so {declared.issue} "
                "looks fixed: remove its KnownDefect marker"
            )
        return True, ""

    if declared is STUB:
        return (status == 501, "" if status == 501 else f"expected declared stub 501, got {status}")
    if status >= 500:
        return False, f"server error {status}: {body[:300]!r}"
    if declared is OK:
        if status in NOT_PERMITTED:
            return False, f"expected OK, got {status}: {body[:160]!r}"
        return True, ""
    if status != declared.value:
        return False, f"expected {declared.name} ({declared.value}), got {status}: {body[:160]!r}"

    hidden = not observed.can_see and not observed.waiver
    if observed.missing and (declared is HIDE or hidden) and not _reads_as_missing(observed):
        first = observed.missing[0]
        return False, (
            f"{status} {body[:120]!r} differs from a missing id's "
            f"{first.status} {first.body[:120]!r}: it confirms the object exists"
        )
    return True, ""
