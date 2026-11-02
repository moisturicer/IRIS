"""Adapting a ``Record`` to the disclosure policy's inputs (IR-127).

The impure edge of an otherwise pure module: it reads model attributes.
Everything that decides anything lives in ``disclosure.py`` and takes values.
"""

from __future__ import annotations

from typing import Any

from .disclosure import Decision, DisclosureInputs, may_disclose


def inputs_for_record(record: Any) -> DisclosureInputs:
    """Read the three governing facts off a record.

    Embargo is ``Record.embargo_state`` (ADR-052 §3), which reads an unanswered
    paper as ``UNKNOWN``. It is not the date column: a blank date is what an
    unanswered paper and an answered "no" both store, and reading it as "no
    embargo" would clear every paper that was never asked.

    Consent is ``Record.dpa_accepted`` (IR-226) -- the per-disclosure stamp,
    not ``User.consent_given``, which records that a person accepted terms
    once at signup and says nothing about this submission.
    """
    return DisclosureInputs(
        is_ip=bool(record.is_ip),
        embargo=record.embargo_state,
        consent_given=bool(record.dpa_accepted),
    )


def decision_for_record(record: Any) -> Decision:
    """The gate's verdict on a record, as one call.

    The two steps are separable and stay separable — that is what keeps the
    policy testable without a database. But every caller that enforces the
    gate wants both, and a caller assembling them itself is a caller that can
    assemble them wrongly: passing a ``Record`` where inputs belong type-checks
    at runtime right up to the point where ``is_ip`` is read off a dataclass
    that has one.
    """
    return may_disclose(inputs_for_record(record))
