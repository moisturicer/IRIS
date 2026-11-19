"""
The rules RDCO's Setup (IR-971) and an Adviser's My Templates (IR-975) share.

ADR-063 decision 8 gives an Adviser's Template "the same file rules as Setup's
Templates", so each rule is written once here. Only what is truly common lives
here; each module adds its own rules beside these (Setup's name may not be
"Manuscript" and is unique per record type, for example).

Every rule raises the caller's own error class with the caller's own wording,
so each screen keeps its messages and each view keeps catching its own error.
"""

from __future__ import annotations

from typing import Iterable

from .scanning import upload_problem
from .template_files import template_problem

MAX_NAME_CHARS = 200
MAX_DESCRIPTION_CHARS = 2000


def check_file(file, user, *, where: str, error: type[Exception]) -> None:
    """
    Setup's file rules, then the malware scan (ADR-074). Call it before the
    change's transaction opens, so the audit of a file refused as unsafe is
    never rolled back with the change.
    """
    problem = template_problem(file) or upload_problem(file, user=user, where=where)
    if problem:
        raise error(problem)


def name(value, *, what: str, missing: str, error: type[Exception]) -> str:
    """A required, trimmed name or title of at most 200 characters."""
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise error(missing)
    if len(text) > MAX_NAME_CHARS:
        raise error(f"Keep the {what} to {MAX_NAME_CHARS} characters.")
    return text


def description(value, *, error: type[Exception]) -> str:
    """Plain text, trimmed, at most 2,000 characters. Missing is empty."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise error("A description is plain text.")
    text = value.strip()
    if len(text) > MAX_DESCRIPTION_CHARS:
        raise error(f"Keep the description to {MAX_DESCRIPTION_CHARS} characters.")
    return text


def only_fields(changes: dict, allowed: set[str], *, error: type[Exception]) -> None:
    unknown = set(changes) - allowed
    if unknown:
        raise error(f"These can't be changed here: {', '.join(sorted(unknown))}.")


def order_ids(order, *, error: type[Exception], ask: str) -> list[int]:
    """The ids a reorder sends, as a list of integers. A string or a mapping is refused."""
    if not isinstance(order, (list, tuple)):
        raise error(ask)
    try:
        return [int(pk) for pk in order]
    except (TypeError, ValueError):
        raise error(ask)


def check_complete_order(ids: list[int], current: Iterable[int], *, error: type[Exception], mismatch: str) -> None:
    """The order names every current item exactly once."""
    current = list(current)
    if len(ids) != len(set(ids)) or set(ids) != set(current):
        raise error(mismatch)
