"""Verified identity inside PostgreSQL (IR-717, ADR-049 §7).

`research_identity` opens a short transaction and binds a grant to it with
`iris_authz.begin_research`; the binding ends at commit or rollback, so a
pooled connection never carries it into the next transaction.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

from django.db import connections, transaction


def _value(raw):
    return json.loads(raw) if isinstance(raw, str) else raw


def verify(token: str, purpose: str, *, using: str = "default") -> dict | None:
    """The grant's claims if PostgreSQL accepts it now, else None."""
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT iris_authz.verify_research_grant(%s, %s)", [token, purpose])
        return _value(cursor.fetchone()[0])


@contextmanager
def research_identity(token: str, purpose: str, *, using: str = "default"):
    """Run the body in one transaction as the grant's verified principal."""
    with transaction.atomic(using=using):
        with connections[using].cursor() as cursor:
            cursor.execute("SELECT iris_authz.begin_research(%s, %s)", [token, purpose])
            claims = _value(cursor.fetchone()[0])
        yield claims
