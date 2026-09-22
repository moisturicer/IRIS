"""Resilience decorators around the `LLMProvider` port (IR-321).

`apps/ai/resilience/{retry,circuit,rate_limit}.py` were written and unit-tested
by IR-132 but never composed around a provider -- `CompositionRoot.llm()`
returned a bare `OpenAICompatibleAdapter`, so a single flaky vendor response
was a failed answer on the first try, with no retry and no circuit trip. This
module is that composition, built the same way `apps/ai/retrieval/degraded.py`
composes around `Retriever`: a decorator implementing the port, not behaviour
folded into the adapter, because an adapter that retries internally cannot be
tested for the failure it hides.

**Behaviour is driven by `ErrorKind`, not by exception type (IR-320).** Three
decisions, not two:

* `network`/`timeout` -- transient. Retried once against the *same* provider
  (`RetryingLLMProvider`), then, if still failing, treated as switch-worthy.
* `rate_limit` -- retrying spends more of a budget that is already gone
  (`retry.py`'s own rule). Never retried; always switch-worthy.
* `auth`/`context_overflow`/`unknown` -- retrying or switching provider both
  answer identically: a bad key is still a bad key on the next attempt, an
  over-long prompt is still over-long, and an unclassified failure is treated
  as a real error rather than assumed to be one of the kinds above (see
  `errors.py`'s own docstring). These give up immediately -- this is what
  keeps a misconfigured key from being silently retried, which is the ADR-021
  "no silent fall-through" rule this must not regress.

**Circuit breaker state must outlive one request.** `apps.ai.composition
.composition_root()` returns a *new* `CompositionRoot()` on every call when
nothing is installed -- so a breaker built inside `CompositionRoot.llm()`
would never accumulate a failure past the request that saw it, and could
never trip. `breaker_for()` is a process-lifetime registry keyed on the
provider's own identity, the same shape `rate_limit.py` uses Redis for across
replicas -- here the state only has to survive across requests in one process,
so a plain dict guarded by a lock is enough.

**The contradiction this ticket carries, recorded rather than reconciled**
(CLAUDE.md's source-of-truth rule). `FallbackLLMProvider` and
`build_resilient_llm`'s multi-config path exist because IR-321's acceptance
criteria ask for a Groq-primary/OpenRouter-fallback provider list.
[ADR-008](../../../../docs/adr/008-ai-degradation-to-fts.md) explicitly
rejected exactly this: *"A secondary LLM provider for failover ... a second
API key, a second data-governance question, a second cost line and a second
integration to test."*
[ADR-021](../../../../docs/adr/021-openai-compatible-inference-provider.md)
restates it: *"This is one provider per environment, selected by
configuration"* -- not two providers live at once. Built anyway, per an
explicit decision to implement as specced and flag the conflict for a human to
resolve (amend ADR-008, or revert this half of IR-321). Kept off by default:
`LLM_FALLBACK_API_KEY` is empty in every `.env.example` and in
`config/settings/base.py`, so a deployment that does not opt in runs exactly
the single-provider policy ADR-021 describes today.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Sequence

from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.ports import LLMProvider

from .circuit import CircuitBreaker, CircuitOpen
from .retry import retry_with_backoff

logger = logging.getLogger(__name__)

#: One retry, on the interactive path -- a person is waiting on this answer,
#: unlike `retry_with_backoff`'s own default of 3, which is sized for a batch
#: lane with nobody watching a spinner (IR-321's "not 3" rule).
INTERACTIVE_RETRY_ATTEMPTS = 2

#: Retrying changes nothing for these -- a bad key, an over-long prompt and an
#: unclassified failure all fail the same way again. Only what is left out of
#: this list (`network`, `timeout`) is ever retried.
_GIVE_UP_ON_RETRY = (
    ErrorKind.AUTH,
    ErrorKind.RATE_LIMIT,
    ErrorKind.CONTEXT_OVERFLOW,
    ErrorKind.UNKNOWN,
)

#: Worth trying the next configured provider for -- the same three kinds
#: `composition._vendor_failures` degrades retrieval on, for the same reason:
#: each means *this vendor*, not *the question*, is the problem. `auth` and
#: `context_overflow` are deliberately absent -- see the module docstring.
_SWITCH_KINDS = (ErrorKind.RATE_LIMIT, ErrorKind.NETWORK, ErrorKind.TIMEOUT)


def is_switchable_failure(exc: BaseException) -> bool:
    """Whether `FallbackLLMProvider` should try the next provider for `exc`.

    An open circuit always qualifies -- the breaker itself already decided
    this provider is down -- without needing a `.kind` to read.
    """
    if isinstance(exc, CircuitOpen):
        return True
    return getattr(exc, "kind", None) in _SWITCH_KINDS


class RetryingLLMProvider(LLMProvider):
    """Retries a transient (`network`/`timeout`) failure against the same
    provider, bounded to `attempts` tries in total.

    `sleep` is injectable, like `retry_with_backoff`'s own parameter, so a
    test asserts the retry happened without living through the delay.
    """

    def __init__(
        self,
        provider: LLMProvider,
        attempts: int = INTERACTIVE_RETRY_ATTEMPTS,
        sleep: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._provider = provider
        self._attempts = attempts
        self._sleep = sleep

    @property
    def model(self) -> str:
        return getattr(self._provider, "model", "unknown")

    def generate(self, system: str, user: str) -> str:
        kwargs = {} if self._sleep is None else {"sleep": self._sleep}
        return retry_with_backoff(
            lambda: self._provider.generate(system, user),
            attempts=self._attempts,
            give_up_on_kind=_GIVE_UP_ON_RETRY,
            **kwargs,
        )


class CircuitBreakingLLMProvider(LLMProvider):
    """Refuses to call a provider whose circuit is open, rather than waiting
    out its timeout again.

    `breaker` has no default that would be safe to rely on in production --
    a caller building one here would get a breaker private to this instance,
    which is exactly the "never trips" bug this module's docstring describes.
    Production wiring always passes the shared instance from `breaker_for`;
    an omitted `breaker` is for a decorator test that has no reason to care.
    """

    def __init__(
        self, provider: LLMProvider, breaker: Optional[CircuitBreaker] = None
    ) -> None:
        self._provider = provider
        self._breaker = breaker or CircuitBreaker()

    @property
    def model(self) -> str:
        return getattr(self._provider, "model", "unknown")

    def generate(self, system: str, user: str) -> str:
        return self._breaker.call(lambda: self._provider.generate(system, user))


class FallbackLLMProvider(LLMProvider):
    """Tries each provider in order, switching to the next on a switch-worthy
    failure (IR-321) and giving up immediately on any other.

    **The model that answered is recorded on `last_model_used`.** ADR-023's
    recall measurement assumes one model per evaluation run; a silent
    fallback to a different model mid-run is exactly the confound that
    assumption cannot survive undetected, so a caller reads which model
    actually produced the answer rather than assuming it was the first one
    configured.
    """

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        switch_on: Callable[[BaseException], bool] = is_switchable_failure,
    ) -> None:
        if not providers:
            raise ValueError("FallbackLLMProvider needs at least one provider")
        self._providers = list(providers)
        self._switch_on = switch_on
        self.last_model_used: Optional[str] = None

    @property
    def model(self) -> str:
        return self.last_model_used or getattr(self._providers[0], "model", "unknown")

    def generate(self, system: str, user: str) -> str:
        failure: Optional[BaseException] = None
        for provider in self._providers:
            try:
                text = provider.generate(system, user)
            except Exception as exc:
                if not self._switch_on(exc):
                    raise
                failure = exc
                logger.warning(
                    "LLM provider %s unavailable (%s); trying the next "
                    "configured provider",
                    getattr(provider, "model", "?"),
                    getattr(exc, "kind", type(exc).__name__),
                )
                continue
            self.last_model_used = getattr(provider, "model", None)
            return text
        # Every provider raised and every raise was switch-worthy, or there
        # was exactly one provider -- either way `failure` was set on the
        # last pass through the loop above.
        assert failure is not None
        raise failure


# -- process-lifetime circuit state ------------------------------------------

_breakers: Dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def breaker_for(key: str) -> CircuitBreaker:
    """The shared breaker for the provider identified by `key`.

    One entry per configured provider, not one per call: a fresh
    `CompositionRoot()` is built on most requests (see module docstring), and
    this registry is what lets the failures it observes still add up.
    """
    with _breakers_lock:
        breaker = _breakers.get(key)
        if breaker is None:
            breaker = CircuitBreaker()
            _breakers[key] = breaker
        return breaker


def reset_llm_breakers() -> None:
    """Clear every breaker this process has built. Test-only: a tripped
    breaker from one test must not leak into the next one sharing this
    module-level registry."""
    with _breakers_lock:
        _breakers.clear()


# -- building the configured stack -------------------------------------------


@dataclass(frozen=True)
class LLMProviderConfig:
    """One candidate provider: enough to build an `OpenAICompatibleAdapter`
    (ADR-021 -- one adapter, keyed on the wire protocol, covers every vendor
    in scope) and to identify it for `breaker_for`."""

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None

    @property
    def key(self) -> str:
        return f"{self.base_url or ''}::{self.model or ''}"


def _wrap(config: LLMProviderConfig) -> LLMProvider:
    from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

    adapter = OpenAICompatibleAdapter(
        base_url=config.base_url or None,
        api_key=config.api_key or None,
        model=config.model or None,
    )
    retrying = RetryingLLMProvider(adapter)
    return CircuitBreakingLLMProvider(retrying, breaker=breaker_for(config.key))


def _configured_providers() -> list[LLMProviderConfig]:
    """The provider list `LLM_*`/`LLM_FALLBACK_*` describe.

    The fallback entry is included only when `LLM_FALLBACK_API_KEY` is set --
    the same signal ADR-008 itself names ("a second API key") for what makes
    this a second provider rather than a typo'd first one. Unset, this
    returns exactly the one config every deployment already reads today.
    """
    from django.conf import settings

    configs = [
        LLMProviderConfig(
            base_url=getattr(settings, "LLM_BASE_URL", None),
            api_key=getattr(settings, "LLM_API_KEY", None),
            model=getattr(settings, "LLM_MODEL", None),
        )
    ]
    if getattr(settings, "LLM_FALLBACK_API_KEY", ""):
        configs.append(
            LLMProviderConfig(
                base_url=getattr(settings, "LLM_FALLBACK_BASE_URL", None),
                api_key=getattr(settings, "LLM_FALLBACK_API_KEY", None),
                model=getattr(settings, "LLM_FALLBACK_MODEL", None),
            )
        )
    return configs


def build_resilient_llm(
    configs: Optional[Sequence[LLMProviderConfig]] = None,
) -> LLMProvider:
    """The `LLMProvider` `CompositionRoot.llm()` uses by default: each
    candidate wrapped in retry and circuit-breaking, and the whole list
    wrapped in `FallbackLLMProvider` when there is more than one.

    `configs` defaults to what settings describe -- explicit only for a
    caller (a test, an operator script) that wants a provider list with no
    vendor account, the same shape `CompositionRoot(llm=...)` already gives a
    caller that wants no resilience wrapping at all.
    """
    resolved = list(configs) if configs is not None else _configured_providers()
    if not resolved:
        raise ValueError("build_resilient_llm needs at least one provider config")

    wrapped = [_wrap(config) for config in resolved]
    if len(wrapped) == 1:
        return wrapped[0]
    return FallbackLLMProvider(wrapped)
