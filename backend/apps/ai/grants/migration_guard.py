"""Migrations never run as a research runtime login (IR-718, ADR-049 §7).

Checked on every `migrate`, forward or back, via `pre_migrate`.
"""

from __future__ import annotations

from django.db import connections

RUNTIME_ROLES = ("iris_ai_runtime", "iris_django_runtime")


class RuntimeLoginRefused(Exception):
    pass


def runtime_role_of_login(cursor) -> str | None:
    """The runtime role the connected login belongs to, if any.

    Superusers are members of every role; they count as maintenance.
    """
    cursor.execute(
        """SELECT r.rolname FROM pg_roles r, pg_roles me
            WHERE me.rolname = current_user AND NOT me.rolsuper
              AND r.rolname = ANY(%s) AND pg_has_role(current_user, r.oid, 'MEMBER')
            ORDER BY r.rolname LIMIT 1""",
        [list(RUNTIME_ROLES)],
    )
    row = cursor.fetchone()
    return row[0] if row else None


def refuse_runtime_login(sender=None, using="default", **kwargs) -> None:
    """`pre_migrate` receiver."""
    with connections[using].cursor() as cursor:
        role = runtime_role_of_login(cursor)
    if role is not None:
        raise RuntimeLoginRefused(f"migrations must not run as a research runtime login ({role})")
