"""Adapting a ``Record`` to the disclosure policy's inputs (IR-127).

The impure edge of an otherwise pure module: it reads model attributes.
Everything that decides anything lives in ``disclosure.py`` and takes values.
"""

from __future__ import annotations

from typing import Any

from .disclosure import Decision, DisclosureInputs, Reason, may_disclose

#: The one refusal a reader is told (ADR-054 decision 8).
NO_CONSENT = Reason.NO_CONSENT.value


def inputs_for_record(record: Any) -> DisclosureInputs:
    """Read the three governing facts off a record.

    Embargo is ``Record.embargo_state`` (ADR-052 §3), which reads an unanswered
    paper as ``UNKNOWN``. It is not the date column: a blank date is what an
    unanswered paper and an answered "no" both store, and reading it as "no
    embargo" would clear every paper that was never asked.

    The IP release is ``Record.ip_released`` (ADR-052 §11), KTTO's act. The mark
    itself stays on the paper, so ``is_ip`` alone still says it is IP.

    Consent is ``Record.ai_consent`` (ADR-054 decisions 9-10, IR-791) -- the
    Contact person's answer, copied onto the paper when its draft was created and
    kept. It is not the person's *current* answer (``User.ai_consent``), which can
    change later without moving a paper, and not the old per-paper stamp
    (``Record.dpa_accepted``), which stopped counting. Only ``True`` is consent:
    ``False`` is a No, and ``None`` is no answer stored, which is refused too.
    """
    return DisclosureInputs(
        is_ip=bool(record.is_ip),
        ip_released=bool(record.ip_released),
        embargo=record.embargo_state,
        consent_given=record.ai_consent is True,
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


def reader_refusal(record: Any) -> str | None:
    """``NO_CONSENT`` for a stored No only; never another reason (ADR-052)."""
    # The gate merges No with no answer; only a No is reported as one.
    if record.ai_consent is not False:
        return None
    return NO_CONSENT if Reason.NO_CONSENT in decision_for_record(record).reasons else None
