"""Adapting a ``Record`` to the disclosure policy's inputs (IR-127).

The impure edge of an otherwise pure module: it reads model attributes and,
by default, the clock. Everything that decides anything lives in
``disclosure.py`` and takes values.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .disclosure import DisclosureInputs, EmbargoUnknown


def inputs_for_record(record: Any, today: Optional[date] = None) -> DisclosureInputs:
    """Read the three governing facts off a record.

    **Embargo is read with ``getattr`` and defaults to ``EmbargoUnknown``.**
    ``Record`` carries no embargo field today, so there is nothing truthful to
    report and the policy refuses -- deliberately, because the alternative is
    to report "not embargoed" on the strength of a field nobody implemented,
    and send unpublished work to a commercial vendor because of it.

    Reading it dynamically rather than hardcoding the sentinel means the day
    an ``embargoed_until`` field is added to ``Record``, this adapter honours
    it without also having to be remembered. Until then the refusal is loud:
    every record is withheld, which is the correct failure direction for a
    gate whose whole purpose is to stop content leaving.

    Consent is ``Record.dpa_accepted`` (IR-226) -- the per-disclosure stamp,
    not ``User.consent_given``, which records that a person accepted terms
    once at signup and says nothing about this submission.
    """
    return DisclosureInputs(
        is_ip=bool(record.is_ip),
        embargoed_until=getattr(record, "embargoed_until", EmbargoUnknown),
        consent_given=bool(record.dpa_accepted),
        today=today if today is not None else date.today(),
    )
