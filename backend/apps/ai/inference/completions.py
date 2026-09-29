"""A structured completion record for every model call (IR-387).

Diagnosing a bad answer becomes one query instead of reading four modules'
logs. Every call through a Profile's provider emits one record, on success and
on failure, naming the Inference task, the vendor, the model that actually
answered (which after a fallback is not the model configured first), whether
a fallback fired, whether reasoning arrived, and on failure the error kind.

**Structured logs, not a table.** Nothing yet needs a join a log query cannot
answer, and a table would add a migration and a retention policy for no
reader that exists yet -- it becomes one when IR-330 needs to join usage
against Turns. `LOGGER_NAME` is its own logger so an operator can route or
filter this stream independently of `apps.ai`'s other logging, and `extra`
carries the fields as LogRecord attributes for a handler that reads them
structurally, alongside the formatted message for one that does not.

**No Record content, no question text, no answer text, no reasoning text.**
This wraps the `LLMProvider` port, which only ever sees `system`/`user`
strings and returns text -- neither is read here, only measured: whether
reasoning arrived, which model answered. Token counts and cost are also
absent, by design -- they are IR-330's, and implementing them here would be a
second implementation to reconcile against that ticket's.

**Wraps the built stack, not `build_profile_llm`'s return value.**
`build_profile_llm` already returns a bare `FallbackLLMProvider` for a
Profile with same-vendor fallback models (IR-385), and existing tests assert
that type directly (`apps/ai/inference/tests/test_fallback.py`,
`test_profiles.py`). This decorator wraps *around* that, at
`CompositionRoot.llm_for` -- the one place every production caller reaches a
task's model through -- so `build_profile_llm`'s own contract is untouched.
"""

from __future__ import annotations

import logging
from typing import Iterator, Optional

from apps.ai.providers.ports import LLMProvider, StreamDelta
from apps.ai.resilience.circuit import CircuitOpen

from .profiles import Profile

LOGGER_NAME = "apps.ai.inference.completions"
logger = logging.getLogger(LOGGER_NAME)

#: What `error_kind` reads when the call was refused before it was made --
#: the breaker's own signal, not one of `ErrorKind`'s vendor-failure kinds.
#: `CircuitOpen` carries no `.kind`, because nothing was tried (see its own
#: docstring), so this names the refusal instead of mislabelling it unknown.
CIRCUIT_OPEN = "circuit_open"


class CompletionLoggingLLMProvider(LLMProvider):
    """Emits one structured completion record per call (IR-387).

    Wraps whichever provider `build_profile_llm` built for `profile` -- a
    lone adapter, or a `FallbackLLMProvider` walking a same-vendor model list
    -- and reads back what happened rather than re-deciding any of it:
    `fallback_fired` and the post-fallback model both come from comparing the
    model that actually answered to `profile.model`, the one configured
    first, the same comparison `answers/service.py:_model_that_answered`
    already makes for the same reason.
    """

    def __init__(self, provider: LLMProvider, profile: Profile) -> None:
        self._provider = provider
        self._profile = profile

    @property
    def model(self) -> str:
        return getattr(self._provider, "model", self._profile.model)

    @property
    def dialect(self):
        from apps.ai.providers.dialects import DEFAULT_DIALECT

        return getattr(self._provider, "dialect", DEFAULT_DIALECT)

    def _model_used(self) -> str:
        """Which model answered, or was last tried when every one failed.

        `last_model_used` exists only on `FallbackLLMProvider`; for a lone
        provider, or before any call has run, `.model` is the only model
        there ever was.
        """
        return getattr(self._provider, "last_model_used", None) or getattr(
            self._provider, "model", self._profile.model
        )

    @staticmethod
    def _error_kind(exc: BaseException) -> str:
        if isinstance(exc, CircuitOpen):
            return CIRCUIT_OPEN
        kind = getattr(exc, "kind", None)
        return kind.value if kind is not None else "unknown"

    def _record(
        self, *, model: str, reasoning_present: bool, error_kind: Optional[str]
    ) -> None:
        fallback_fired = model != self._profile.model
        logger.info(
            "inference completion task=%s vendor=%s model=%s "
            "fallback_fired=%s reasoning_present=%s error_kind=%s",
            self._profile.task.value,
            self._profile.vendor.value,
            model,
            fallback_fired,
            reasoning_present,
            error_kind or "",
            extra={
                "inference_task": self._profile.task.value,
                "vendor": self._profile.vendor.value,
                "model": model,
                "fallback_fired": fallback_fired,
                "reasoning_present": reasoning_present,
                "error_kind": error_kind,
            },
        )

    def generate(self, system: str, user: str) -> str:
        try:
            text = self._provider.generate(system, user)
        except Exception as exc:
            self._record(
                model=self._model_used(),
                reasoning_present=False,
                error_kind=self._error_kind(exc),
            )
            raise
        # `generate()` never carries reasoning -- the port only returns text;
        # `StreamDelta.reasoning` is `stream()`'s own channel (see ports.py).
        self._record(model=self._model_used(), reasoning_present=False, error_kind=None)
        return text

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        reasoning_present = False
        try:
            for delta in self._provider.stream(system, user):
                if delta.reasoning:
                    reasoning_present = True
                yield delta
        except Exception as exc:
            self._record(
                model=self._model_used(),
                reasoning_present=reasoning_present,
                error_kind=self._error_kind(exc),
            )
            raise
        else:
            self._record(
                model=self._model_used(),
                reasoning_present=reasoning_present,
                error_kind=None,
            )
