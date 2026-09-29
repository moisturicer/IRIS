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

**The contradiction IR-321 recorded here is gone (IR-376, then IR-385).** It
was that `FallbackLLMProvider` and `build_resilient_llm`'s multi-config path
implemented a Groq-primary/OpenRouter-fallback list, which
[ADR-008](../../../../docs/adr/008-ai-degradation-to-fts.md) rejected by name
and [ADR-021](../../../../docs/adr/021-openai-compatible-inference-provider.md)
restated as *"one provider per environment"*. Both ADRs were amended on
2026-09-28:

* ADR-008 §Amendment permits a **fallback list of models inside one vendor
  account** -- same `base_url`, same `api_key`, a different `model` -- and
  confirms **cross-vendor failover stays rejected**.
* ADR-021 §Amendment replaces "one provider per environment" with **one adapter
  per protocol, vendor chosen per Inference task**. Two vendors configured for
  two different tasks is not failover.

IR-385 made the code match: the `LLM_FALLBACK_*` second vendor is **deleted,
not disabled** -- the settings and the config they built are gone, so there is
no longer a switch a deployment could throw to cross a vendor boundary. What
is left is a list of models on one account, which is what
`FallbackLLMProvider` walks, and only for a vendor whose dialect does not
resolve the list itself (`VendorDialect.resolves_fallback` -- OpenRouter does,
so IRIS makes one request there rather than looping).

**One breaker per Inference task, not per model (IR-386).** `_wrap` keys a
breaker on `LLMProviderConfig.key` (`base_url::model`), which is right for the
flat, task-less settings `build_resilient_llm` still serves, but would let two
Inference tasks pointed at the same vendor and model share a breaker --
`summary` hitting a rate limit would then also stop `answer`, for a reason
that has nothing to do with answering. `build_task_llm` is what
`apps/ai/inference/providers.py` uses instead: one breaker around a whole
task's model list, keyed on the task rather than on any one model in it, so
exhausting the list is what opens it rather than the first model's failure.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Dict, Iterator, Optional, Sequence, Tuple

from apps.ai.providers.dialects import DEFAULT_DIALECT, VendorDialect
from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.ports import LLMProvider, StreamDelta

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

#: Worth trying the next model in the list for -- the same three kinds
#: `composition._vendor_failures` degrades retrieval on, for the same reason:
#: each means *this vendor*, not *the question*, is the problem. `auth` and
#: `context_overflow` are deliberately absent -- see the module docstring.
_SWITCH_KINDS = (ErrorKind.RATE_LIMIT, ErrorKind.NETWORK, ErrorKind.TIMEOUT)


def is_switchable_failure(exc: BaseException) -> bool:
    """Whether `FallbackLLMProvider` should try the next model for `exc`.

    A kind another model cannot fix -- `auth`, `context_overflow`, `unknown`
    -- stops the walk rather than spending the rest of the list on a failure
    that repeats identically (ADR-008 §Amendment).

    An open circuit always qualifies -- the breaker itself already decided
    this provider is down -- without needing a `.kind` to read.
    """
    if isinstance(exc, CircuitOpen):
        return True
    return getattr(exc, "kind", None) in _SWITCH_KINDS


# -- streaming through a decorator -------------------------------------------
#
# The rule all three decorators below follow: **retry and failover are
# permitted only before the first delta is yielded** (IR-334). Once a token
# has reached the reader's screen, re-running the call would repeat text they
# have already read, so a failure after first output propagates instead.
#
# `_open_stream` is how that line is drawn. It starts the stream and pulls one
# delta, so everything a vendor fails on at connection time -- a bad key, an
# exhausted quota, a dropped socket -- happens inside whatever guard the
# caller wrapped it in, and everything after is a plain pass-through.


def _open_stream(
    make_stream: Callable[[], Iterator[StreamDelta]],
) -> Tuple[Optional[StreamDelta], Iterator[StreamDelta]]:
    """Start a stream and take its first delta, or ``None`` if it was empty."""
    iterator = iter(make_stream())
    try:
        return next(iterator), iterator
    except StopIteration:
        return None, iter(())


def _yield_from_opened(
    opened: Tuple[Optional[StreamDelta], Iterator[StreamDelta]],
) -> Iterator[StreamDelta]:
    first, rest = opened
    if first is not None:
        yield first
    yield from rest


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

    @property
    def dialect(self) -> VendorDialect:
        return getattr(self._provider, "dialect", DEFAULT_DIALECT)

    def generate(self, system: str, user: str) -> str:
        kwargs = {} if self._sleep is None else {"sleep": self._sleep}
        return retry_with_backoff(
            lambda: self._provider.generate(system, user),
            attempts=self._attempts,
            give_up_on_kind=_GIVE_UP_ON_RETRY,
            **kwargs,
        )

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        """The same retry, around opening the stream only.

        Without this the port's buffering default ran instead, and every
        answer arrived as one delta once generation had entirely finished --
        the limitation `ChatStreamView` recorded.
        """
        kwargs = {} if self._sleep is None else {"sleep": self._sleep}
        yield from _yield_from_opened(
            retry_with_backoff(
                lambda: _open_stream(lambda: self._provider.stream(system, user)),
                attempts=self._attempts,
                give_up_on_kind=_GIVE_UP_ON_RETRY,
                **kwargs,
            )
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

    @property
    def dialect(self) -> VendorDialect:
        return getattr(self._provider, "dialect", DEFAULT_DIALECT)

    def generate(self, system: str, user: str) -> str:
        return self._breaker.call(lambda: self._provider.generate(system, user))

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        """Guards opening the stream, not consuming it.

        A vendor that produced a first token is not the down vendor this
        breaker exists to stop us hammering, so a failure later in the stream
        is not counted against it. Wrapping the whole consumption instead is
        not an option anyway: `call` records success the moment its operation
        returns, and a generator returns before it has produced anything.
        """
        yield from _yield_from_opened(
            self._breaker.call(
                lambda: _open_stream(lambda: self._provider.stream(system, user))
            )
        )


class FallbackLLMProvider(LLMProvider):
    """Tries each model in order, switching to the next on a switch-worthy
    failure (IR-321) and giving up immediately on any other.

    **Every entry is the same vendor account** (ADR-008 §Amendment, IR-385):
    one `base_url` and one `api_key`, differing only in `model`. Exhausting
    the list raises the last failure, which the answer path turns into the
    explicit unavailable state with sources still returned -- it never
    reaches a second vendor, because there is no longer one to reach.

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

    @property
    def dialect(self) -> VendorDialect:
        """The dialect of whichever provider is next to be tried.

        The list is same-vendor (ADR-008 §Amendment), so every entry agrees;
        the first is read rather than the one that last answered so this is
        the same before any call as after one.
        """
        return getattr(self._providers[0], "dialect", DEFAULT_DIALECT)

    def generate(self, system: str, user: str) -> str:
        failure: Optional[BaseException] = None
        for provider in self._providers:
            try:
                text = provider.generate(system, user)
            except Exception as exc:
                if not self._switch_on(exc):
                    raise
                failure = exc
                self._log_switch(provider, exc)
                continue
            self.last_model_used = getattr(provider, "model", None)
            return text
        # Every provider raised and every raise was switch-worthy, or there
        # was exactly one provider -- either way `failure` was set on the
        # last pass through the loop above.
        assert failure is not None
        raise failure

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        """The same walk down the provider list, switching only while the
        stream has produced nothing.

        A provider that failed after its first delta is not retried on the
        next one: the reader has already seen text, and a second provider
        would start its own answer from the beginning underneath it.
        """
        failure: Optional[BaseException] = None
        for provider in self._providers:
            try:
                opened = _open_stream(lambda p=provider: p.stream(system, user))
            except Exception as exc:
                if not self._switch_on(exc):
                    raise
                failure = exc
                self._log_switch(provider, exc)
                continue
            self.last_model_used = getattr(provider, "model", None)
            yield from _yield_from_opened(opened)
            return
        assert failure is not None
        raise failure

    def _log_switch(self, provider: LLMProvider, exc: BaseException) -> None:
        logger.warning(
            "LLM provider %s unavailable (%s); trying the next "
            "configured provider",
            getattr(provider, "model", "?"),
            getattr(exc, "kind", type(exc).__name__),
        )


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
    #: `None` inherits `LLM_REASONING_EFFORT`; `""` sends no reasoning
    #: configuration at all (IR-380).
    reasoning_effort: Optional[str] = None
    #: Which vendor dialect shapes this provider's requests (IR-382). `None`
    #: takes the default, which is what every caller sent before dialects
    #: existed -- so an unset vendor is unchanged behaviour, not a gap.
    vendor: Optional[str] = None
    #: The rest of the model list, for a vendor that resolves it itself in
    #: one request (IR-385). Empty for a vendor IRIS loops for, where each
    #: model is its own config with its own breaker.
    fallback_models: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.base_url or ''}::{self.model or ''}"


def _build_retrying(config: LLMProviderConfig) -> LLMProvider:
    """The adapter `config` describes, retried but not yet circuit-broken.

    Where the breaker goes is the caller's decision: `_wrap` puts one around
    each legacy config below, `build_task_llm` puts one around a whole
    Inference task's model list instead (IR-386). Both start from this same
    unbroken candidate rather than duplicating the adapter construction.
    """
    from apps.ai.providers.dialects import dialect_for
    from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

    adapter = OpenAICompatibleAdapter(
        base_url=config.base_url or None,
        api_key=config.api_key or None,
        model=config.model or None,
        reasoning_effort=config.reasoning_effort,
        dialect=dialect_for(config.vendor),
        fallback_models=config.fallback_models,
    )
    return RetryingLLMProvider(adapter)


def _wrap(config: LLMProviderConfig) -> LLMProvider:
    return CircuitBreakingLLMProvider(
        _build_retrying(config), breaker=breaker_for(config.key)
    )


def build_task_llm(
    configs: Sequence[LLMProviderConfig], breaker_key: str
) -> LLMProvider:
    """Every candidate in `configs` retried individually, combined into a
    `FallbackLLMProvider` when there is more than one, under **one** circuit
    breaker for the whole list, keyed by `breaker_key` (IR-386).

    This is what an Inference task's model list is built with instead of
    `build_resilient_llm`: that function gives every config its own breaker
    (`_wrap`), which is right for the flat, task-less `LLM_*` settings it
    still serves, but wrong for a Profile's fallback list, where a switch
    inside `FallbackLLMProvider` would otherwise trip the *first* model's
    breaker on a failure the list as a whole recovered from. Here the breaker
    sees a failure only when `combined` itself raises -- every candidate in
    one call having raised, or there being nothing left to switch to -- so
    exhausting the list is what counts against it, not one model along the
    way.

    `breaker_key` also stops two Inference tasks pointed at the same vendor
    and model from sharing a breaker: `_wrap`'s key is the model's own
    identity (`base_url::model`), which cannot tell two tasks apart when
    both happen to name the same one.
    """
    if not configs:
        raise ValueError("build_task_llm needs at least one provider config")

    candidates = [_build_retrying(config) for config in configs]
    combined = candidates[0] if len(candidates) == 1 else FallbackLLMProvider(candidates)
    return CircuitBreakingLLMProvider(combined, breaker=breaker_for(breaker_key))


def _configured_providers() -> list[LLMProviderConfig]:
    """The one provider the flat `LLM_*` settings describe.

    One, not a list: the `LLM_FALLBACK_*` second vendor was deleted in
    IR-385, so the flat settings describe a single account again. A model
    list is per Inference task now (`LLM_<TASK>_FALLBACK_MODELS`), resolved
    in `apps/ai/inference/providers.py` rather than read from here.
    """
    from django.conf import settings

    return [
        LLMProviderConfig(
            base_url=getattr(settings, "LLM_BASE_URL", None),
            api_key=getattr(settings, "LLM_API_KEY", None),
            model=getattr(settings, "LLM_MODEL", None),
        )
    ]


def any_provider_reachable() -> bool:
    """Whether at least one configured provider's breaker is not open
    (IR-252).

    Reads breaker state only -- it never calls a vendor to answer this. A
    breaker only opens after real `generate()` calls actually failed against
    it (`CircuitBreakingLLMProvider`), so this is the process's own memory of
    which configured providers have been observed to work, not a guess from
    a key string. One config since IR-385 deleted the cross-vendor entry,
    so this reads that provider's own breaker.

    Lives here rather than in `apps/ai/composition.py`, which used to read
    `breaker_for` and `_configured_providers` directly: this module already
    owns the breaker registry and the provider list, and a second module
    walking both is the "second copy of that knowledge" the composition
    root's own docstring warns against -- just one layer removed from the
    setting itself.
    """
    from apps.ai.resilience.circuit import CircuitState

    return any(
        breaker_for(config.key).state is not CircuitState.OPEN
        for config in _configured_providers()
    )


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
