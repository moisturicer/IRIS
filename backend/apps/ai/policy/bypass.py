"""Standing beside the disclosure gate, in development only (IR-317).

ADR-015 §A development bypass permits this and permits nothing else. The gate
in ``disclosure.py`` is unchanged and still refuses every record, because
``Record`` carries no embargo field and an undetermined embargo is treated as
an embargo (IR-250). What this module adds is a way to *stand beside* that
refusal while CIT-U decides what an embargo is — not a rule that answers the
question for them.

**Why a labelled switch rather than a plausible rule.** The tempting shortcut
is "published records are not embargoed", which sounds defensible and is
therefore the dangerous option: months later nobody can separate CIT-U's
policy from a placeholder added to unblock a sprint. ``BYPASS_FOR_DEVELOPMENT``
cannot be mistaken for a decision.

**Why no field.** Adding ``Record.embargoed_until`` now reads as ``None`` on
every existing row, and ``None`` means *known not embargoed* — which does not
open the gate temporarily, it removes it permanently and silently. The bypass
is runtime only, so IR-250 lands as one migration and a deliberate backfill.

**The conditions are here, not in a docstring elsewhere.** It refuses to start
under ``DEBUG=False``, it logs on every use, it is reported by
``/api/v1/ai/status/``, and it is off unless set. ``apps/ai/tests/
test_disclosure_bypass.py`` fails if any of those stops being true — including
if this module is half-removed.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .disclosure import Decision

logger = logging.getLogger(__name__)

#: The one name. Referenced rather than spelled out again in the guard message
#: and the tests, so a rename cannot leave a check pointing at a dead setting.
SETTING = "AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT"

#: A permitting decision, shaped like the gate's own so both the query path
#: (which asks for truthiness) and the indexing path (which asks a refusal
#: why) can take this predicate without a second contract.
_BYPASSED = Decision(allowed=True)


def bypass_enabled() -> bool:
    """Whether the bypass is on. ``getattr`` so a settings module that has not
    heard of it reads as off rather than as a crash."""
    return bool(getattr(settings, SETTING, False))


def permit_everything(record: Any) -> Decision:
    """Permit this record's content to leave, and say so out loud.

    A warning per record rather than one at startup: the startup line scrolls
    away, and the question a log reader is actually asking months later is
    "was *this* content sent under the bypass?"
    """
    logger.warning(
        "%s is on: the ADR-015 disclosure gate was bypassed for record %s. "
        "Content is being sent to a commercial vendor without an embargo "
        "check (IR-317, removed by IR-250).",
        SETTING,
        getattr(record, "pk", record),
    )
    return _BYPASSED


def permits_query(record: Any) -> bool:
    """The same bypass in the query lane's shape.

    ``CompositionRoot`` and ``GroundedAnswerService`` take a predicate
    returning ``bool``; the indexing path takes one returning a ``Decision``,
    because a refusal there has to say why. ``Decision`` is truthy, so one
    function would *work* in both — and would make one of the two annotations
    a lie. Two lines is cheaper than a type that is wrong at a call site.
    """
    return bool(permit_everything(record))


def bypass_configuration_problem(*, enabled: bool, debug: bool) -> Optional[str]:
    """What is wrong with this combination, or ``None``.

    Pure and keyword-only, like ``config.settings.validation``: the rule is
    testable against crafted inputs instead of by booting Django once per
    broken environment, which is the only way a fail-fast path gets verified.
    """
    if enabled and not debug:
        return (
            f"{SETTING} is set while DEBUG is off. It disables ADR-015's "
            f"disclosure gate, which is the control that stops unpublished "
            f"student work reaching a commercial vendor, and it exists for "
            f"development only. Unset it, or set DEBUG on a machine where "
            f"that is appropriate."
        )
    return None


def verify_bypass_configuration() -> None:
    """Refuse to start rather than quietly run without the gate.

    The same posture ADR-015 requirement 3 takes toward a missing
    ``VOYAGE_API_KEY``: taking the service down is louder than serving
    requests with a security control switched off.
    """
    problem = bypass_configuration_problem(
        enabled=bypass_enabled(), debug=bool(settings.DEBUG)
    )
    if problem is not None:
        raise ImproperlyConfigured(problem)


def install_bypass_if_enabled() -> bool:
    """Wire the permissive predicate into the query lane, if it is on.

    Through ``install_composition_root`` rather than by changing a default:
    the seam already exists for tests, the production default stays the real
    gate, and removing this function removes the bypass from the browser path
    entirely.
    """
    if not bypass_enabled():
        return False

    from apps.ai.composition import (
        CompositionRoot,
        composition_root_installed,
        install_composition_root,
    )

    if composition_root_installed():
        # `ready()` runs more than once in a test session, and a bypass that
        # reinstalls itself over a root somebody else installed would silently
        # reopen the gate under a test that set out to assert it closed.
        return False

    install_composition_root(CompositionRoot(permits=permits_query))
    logger.warning(
        "%s is on: Ask IRIS is answering with the disclosure gate bypassed. "
        "Development only — IR-317.",
        SETTING,
    )
    return True
