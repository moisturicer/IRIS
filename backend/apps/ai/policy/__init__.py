"""Disclosure policy: what may be sent to a commercial AI vendor (IR-127).

ADR-015 §Security Impact makes this the gate in front of every outbound call.
Import from here rather than reaching into the submodules.
"""

from .disclosure import (
    Decision,
    DisclosureInputs,
    EmbargoUnknown,
    Reason,
    may_disclose,
)
from .records import decision_for_record, inputs_for_record

__all__ = [
    "Decision",
    "DisclosureInputs",
    "EmbargoUnknown",
    "Reason",
    "may_disclose",
    "decision_for_record",
    "inputs_for_record",
]
