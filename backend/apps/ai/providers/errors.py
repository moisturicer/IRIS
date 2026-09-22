"""Classifying a vendor failure by kind, not just by exception type (IR-320).

`OpenAICompatibleAdapter` and the Voyage adapter each collapse every vendor
failure into one exception type (`LLMUnavailable`, `VoyageError`) -- that is
the anti-corruption boundary IR-131/IR-128 built, and it stays. What it did
not carry was *why*: a missing key, a spent rate limit, a dropped connection
and an over-long prompt were all, to every caller, the identical event.

This module is the small, closed vocabulary that boundary now attaches, and
the classifiers that fill it in -- from the vendor's actual HTTP status or SDK
exception type first, falling back to a message heuristic only when the
vendor gives nothing better to read.

Deliberately not a general-purpose taxonomy. A caller here makes exactly one
decision from a kind -- retry it, degrade past it, or neither -- so a kind
nothing branches on (a 404, a 409, a malformed response) stays `UNKNOWN`
rather than growing the vocabulary to name it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional


class ErrorKind(enum.Enum):
    """Why a vendor call failed, as far as a caller needs to act on it."""

    #: The credential was missing, wrong, or the account lacks permission.
    #: Retrying changes nothing, and degrading to full-text search would only
    #: hide a configuration mistake behind a worse answer every time.
    AUTH = "auth"

    #: The account or lane is over its quota for this window. Retrying makes
    #: the outage worse (it spends more of a budget that is already gone);
    #: this is the one kind a caller should let the outage show through.
    RATE_LIMIT = "rate_limit"

    #: The request never reached the vendor, or its response never arrived --
    #: a dropped connection, DNS failure, or reset. Transient by nature, and
    #: the classic case for a retry or a degrade.
    NETWORK = "network"

    #: The vendor was reached but did not answer in time. Kept distinct from
    #: `NETWORK` because a caller may want a different retry budget for a slow
    #: vendor than for an unreachable one.
    TIMEOUT = "timeout"

    #: The request itself was too large for the model. Retrying or degrading
    #: both fail identically -- the request does not get shorter on its own --
    #: so a caller should treat this as a real error, not an outage.
    CONTEXT_OVERFLOW = "context_overflow"

    #: Anything else: a response the vendor's own SDK does not model, a
    #: malformed body, or a message this module's heuristics do not recognise.
    #: The safe default -- an unrecognised failure is treated as a real error,
    #: not silently assumed to be one of the kinds above.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifiedError:
    """A vendor failure, classified at the adapter boundary.

    ``original`` is kept rather than discarded: a caller may still want the
    vendor's own message, and re-raising the domain exception built from
    ``original`` (not a new exception built from the classification alone) is
    what lets a caller that only understands `LLMUnavailable`/`VoyageError`
    keep working unmodified -- this adds information to the boundary, it does
    not replace it.
    """

    kind: ErrorKind
    original: BaseException


#: Phrases that mean "the request was too large for the model", drawn from
#: what OpenAI-compatible vendors and Voyage actually say in a 400 body. A
#: closed list, not a general-purpose parser: extending it is the cost of
#: supporting a vendor whose wording is not covered yet.
_CONTEXT_OVERFLOW_HINTS = (
    "context length",
    "context_length",
    "maximum context",
    "too many tokens",
    "reduce the length",
    "token limit",
)


def _looks_like_context_overflow(code: Optional[str], message: str) -> bool:
    if code and "context_length" in code:
        return True
    lowered = (message or "").lower()
    return any(hint in lowered for hint in _CONTEXT_OVERFLOW_HINTS)


def classify_status_code(
    status_code: int, code: Optional[str], message: str
) -> ErrorKind:
    """Classify an HTTP-shaped vendor failure. Every vendor here speaks HTTP
    status codes even when their SDKs wrap them differently, so this is the
    one function both adapters' status-based paths share."""
    if status_code in (401, 403):
        return ErrorKind.AUTH
    if status_code == 429:
        return ErrorKind.RATE_LIMIT
    if status_code == 400 and _looks_like_context_overflow(code, message):
        return ErrorKind.CONTEXT_OVERFLOW
    if status_code >= 500:
        # A vendor's own server error is not "our network", but it is the
        # same shape of transient, worth-a-retry failure -- and IRIS has no
        # kind that distinguishes "their server" from "the wire between us".
        return ErrorKind.NETWORK
    return ErrorKind.UNKNOWN


def classify_message(message: str) -> ErrorKind:
    """Classify a failure that carried no status code to read -- a bare
    exception whose only signal is its text. Used only when the SDK- or
    status-based path finds nothing better, per this module's docstring."""
    lowered = (message or "").lower()
    if _looks_like_context_overflow(None, message):
        return ErrorKind.CONTEXT_OVERFLOW
    if "timed out" in lowered or "timeout" in lowered:
        return ErrorKind.TIMEOUT
    if "rate limit" in lowered or "429" in lowered:
        return ErrorKind.RATE_LIMIT
    if (
        "unauthorized" in lowered
        or "authentication" in lowered
        or "forbidden" in lowered
        or "401" in lowered
        or "403" in lowered
    ):
        return ErrorKind.AUTH
    if "connection" in lowered or "network" in lowered:
        return ErrorKind.NETWORK
    return ErrorKind.UNKNOWN
