"""May this record's content leave the deployment? (IR-127)

[ADR-015] §Security Impact puts a gate in front of every outbound call to a
commercial AI vendor, and this is it. Anything refused here is **not sent to
Voyage and is not AI-processed by any provider** -- there is no local model to
fall back to (ADR-008 rejected one, and ADR-015's original local lane was
removed the same day for contradicting that). A refusal degrades to the same
PostgreSQL full-text path a vendor outage degrades to.

Three inputs, kept independent because ADR-015 names them independently and a
single combined flag is how a case goes missing: IP status, embargo, consent.

Pure -- no database, no network, no clock. ``today`` is passed in rather than
read, so an embargo boundary is testable without freezing time. The decision
is a value, not a side effect; enforcing it is the caller's job (D and E).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date
from typing import Union


class _EmbargoUnknown:
    """Sentinel: nobody knows whether this record is under embargo.

    Distinct from ``None`` (which means *known* not to be embargoed) because
    the two must not behave alike. ``Record`` carries no embargo field today,
    so its adapter has nothing truthful to pass, and reading a missing value
    as "not embargoed" would send unpublished work to a vendor on the strength
    of a field that was never implemented. Unknown refuses.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "EmbargoUnknown"

    def __bool__(self) -> bool:
        # Refuses to be truthiness-tested into meaning "no embargo".
        raise TypeError(
            "EmbargoUnknown has no truth value -- an unknown embargo must be "
            "handled explicitly, not treated as absent."
        )


#: The single instance. Compare with ``is``.
EmbargoUnknown = _EmbargoUnknown()

#: ``None`` means known-not-embargoed; a date means embargoed until that day.
Embargo = Union[date, None, _EmbargoUnknown]


class Reason(enum.Enum):
    """Why a disclosure was refused. One member per independent input, plus
    the unknown case, so a caller can log precisely what to fix."""

    UNRELEASED_IP = "unreleased_ip"
    EMBARGOED = "embargoed"
    NO_CONSENT = "no_consent"
    EMBARGO_UNKNOWN = "embargo_unknown"


_EXPLANATIONS = {
    Reason.UNRELEASED_IP: (
        "the record is marked intellectual property, and disclosing unpublished "
        "IP to a third party can defeat a later claim over it"
    ),
    Reason.EMBARGOED: "the record is under embargo",
    Reason.NO_CONSENT: "the author has not consented to this disclosure",
    Reason.EMBARGO_UNKNOWN: (
        "whether the record is under embargo could not be determined, and an "
        "undetermined embargo is treated as an embargo"
    ),
}


@dataclass(frozen=True)
class DisclosureInputs:
    """The governing facts, as values rather than as a ``Record``.

    Taking facts rather than a model keeps this testable without a database
    and keeps the policy usable for a chunk, a record, or anything else that
    can answer these three questions.
    """

    is_ip: bool
    embargoed_until: Embargo
    consent_given: bool
    today: date


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reasons: tuple[Reason, ...] = ()

    def __bool__(self) -> bool:
        """So ``if may_disclose(...):`` cannot read a refusal as permission."""
        return self.allowed

    def explain(self) -> str:
        """A sentence a caller can log, so every call site does not invent one."""
        if self.allowed:
            return "disclosure permitted"
        causes = "; ".join(_EXPLANATIONS[reason] for reason in self.reasons)
        return f"disclosure refused: {causes}"


def _embargo_reason(embargo: Embargo, today: date) -> Reason | None:
    if embargo is EmbargoUnknown:
        return Reason.EMBARGO_UNKNOWN
    if embargo is None:
        return None
    # The embargo runs *until* its date, so on the day itself it is spent.
    return Reason.EMBARGOED if embargo > today else None


def may_disclose(inputs: DisclosureInputs) -> Decision:
    """Decide whether this content may be sent to a commercial AI vendor.

    Every failing input is reported, not just the first: a refusal naming one
    cause sends the reader to fix one thing and be refused again.
    """
    reasons: list[Reason] = []

    if inputs.is_ip:
        reasons.append(Reason.UNRELEASED_IP)

    embargo_reason = _embargo_reason(inputs.embargoed_until, inputs.today)
    if embargo_reason is not None:
        reasons.append(embargo_reason)

    if not inputs.consent_given:
        reasons.append(Reason.NO_CONSENT)

    return Decision(allowed=not reasons, reasons=tuple(reasons))
