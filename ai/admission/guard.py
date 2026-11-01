"""The check just before each physical send (IR-725, ADR-049 §8).

Run still running under the fence and deadline, reader active, provider
no-training. Record evidence is withheld: the AI runtime has no disclosure
decision yet, so it fails closed.
"""

from __future__ import annotations

from typing import Iterable

import asyncpg

from . import errors
from .errors import AdmissionDenied
from .scope import RunBinding

NO_TRAINING = "no-training"


class SendGuard:
    def __init__(self, dsn: str):
        self.dsn = dsn

    async def check(self, binding: RunBinding, pin, dependencies: Iterable = ()) -> None:
        if pin.data_policy != NO_TRAINING:
            raise AdmissionDenied(errors.PROVIDER_REFUSED)
        if tuple(dependencies):
            raise AdmissionDenied(errors.WITHHELD)
        try:
            conn = await asyncpg.connect(self.dsn)
            try:
                row = await conn.fetchrow(
                    """SELECT state, fence, deadline_at <= now() AS overdue,
                              coalesce(grant_expires_at > now(), false) AS granted,
                              iris_authz.reader_status(reader_id) AS reader
                         FROM iris_ai.ask_run WHERE id = $1""",
                    binding.run_id,
                )
            finally:
                await conn.close()
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
            raise AdmissionDenied(errors.STORE_UNAVAILABLE) from None
        if row is None or row["state"] != "running" or row["fence"] != binding.fence:
            raise AdmissionDenied(errors.RUN_CANCELLED)
        if row["overdue"]:
            raise AdmissionDenied(errors.DEADLINE)
        if row["reader"] != "active" or not row["granted"]:
            raise AdmissionDenied(errors.ACCESS_REVOKED)
