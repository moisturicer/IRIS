"""What a provider attempt needs to know about the work around it (IR-545).

Three context variables, so no port grows a parameter:

* the **workload** -- which lane a call is charged to. The code that starts
  the work names it (chat, research, ingestion, overview); a call made
  outside any named workload is charged to its provider's own default lane.
* the **run** -- a key that per-run caps sum over, and the denials the run
  met, which a queued run journals as an explicit busy status.
* the **attempt** -- set only while one physical attempt is in progress, so
  the adapter can say when the request left (`mark_sent`) and what the vendor
  reported (`report_usage`) without knowing admission exists.

A generator's body runs in its caller's context, and under ASGI each step of a
streamed response may run in a different thread with a copied context. So a
generator is never wrapped in a ``with`` block spanning its yields: `stepwise`
enters the scopes around each step instead, and around its close.
"""

from __future__ import annotations

import functools
import uuid
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, ContextManager, Iterator, Optional

if TYPE_CHECKING:
    from .limits import Ceiling

_workload: ContextVar[Optional[str]] = ContextVar("admission_workload", default=None)
_run: ContextVar[Optional["RunScope"]] = ContextVar("admission_run", default=None)
_attempt: ContextVar[Optional["AttemptUsage"]] = ContextVar("admission_attempt", default=None)
_send_guard: ContextVar[Optional[Callable]] = ContextVar("provider_send_guard", default=None)
_usage_observer: ContextVar[Optional[list]] = ContextVar("provider_usage_observer", default=None)
_work_item: ContextVar[Optional[str]] = ContextVar("provider_work_item", default=None)


@dataclass
class RunScope:
    key: str
    ceiling: Optional["Ceiling"] = None
    #: Reason codes, in the order they were met.
    denials: list = field(default_factory=list)


@dataclass
class AttemptUsage:
    sent: bool = False
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    model: Optional[str] = None
    cost_usd: Optional[float] = None

    @property
    def reported(self) -> bool:
        return self.input_tokens is not None and self.output_tokens is not None


# -- workload -----------------------------------------------------------------


@contextmanager
def workload(lane: str) -> Iterator[None]:
    token = _workload.set(lane)
    try:
        yield
    finally:
        _workload.reset(token)


def charged_to(lane: str):
    """Decorate a plain (not generator) function to run as ``lane``'s work."""

    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            with workload(lane):
                return function(*args, **kwargs)

        return wrapper

    return decorate


def lane_for(default: str) -> str:
    """The named workload, or ``default`` (the provider's own lane)."""
    return _workload.get() or default


# -- run ----------------------------------------------------------------------


def new_run(key: Optional[str] = None, *, ceiling: Optional["Ceiling"] = None) -> RunScope:
    return RunScope(key or f"req:{uuid.uuid4().hex}", ceiling=ceiling)


@contextmanager
def run(scope: Optional[RunScope] = None) -> Iterator[RunScope]:
    """Open ``scope`` (a new one if ``None``), unless a run is already open:
    an outer run -- a queued question -- keeps its key when the orchestrator
    inside opens its own. Pass the same `RunScope` to every step of one run
    so its denials accumulate."""
    current = _run.get()
    if current is not None:
        yield current
        return
    scope = scope or new_run()
    token = _run.set(scope)
    try:
        yield scope
    finally:
        _run.reset(token)


def current_run() -> Optional[RunScope]:
    return _run.get()


@contextmanager
def work_item(key: str) -> Iterator[None]:
    """Attribute a sub-operation while retaining the encompassing run's ceiling."""
    token = _work_item.set(key)
    try:
        yield
    finally:
        _work_item.reset(token)


def current_work_item() -> Optional[str]:
    return _work_item.get()


def note_denial(reason: str) -> None:
    scope = _run.get()
    if scope is not None:
        scope.denials.append(reason)


# -- attempt ------------------------------------------------------------------


@contextmanager
def attempt_usage(usage: AttemptUsage) -> Iterator[AttemptUsage]:
    token = _attempt.set(usage)
    try:
        yield usage
    finally:
        _attempt.reset(token)


@contextmanager
def before_send(guard: Callable) -> Iterator[None]:
    """A workload's permission/context check immediately before each transport."""
    token = _send_guard.set(guard)
    try:
        yield
    finally:
        _send_guard.reset(token)


@contextmanager
def observe_usage() -> Iterator[list[AttemptUsage]]:
    """Observe current-call response metadata independently of ledger settlement."""
    reports = []
    token = _usage_observer.set(reports)
    try:
        yield reports
    finally:
        _usage_observer.reset(token)


def mark_sent(*, model: Optional[str] = None) -> None:
    """Called by an adapter immediately before handing a request to its
    transport. An attempt that ends before this is released, not charged."""
    guard = _send_guard.get()
    if guard is not None:
        guard(model)
    usage = _attempt.get()
    if usage is not None:
        usage.sent = True


def report_usage(
    *,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    model: Optional[str] = None,
    cost_usd: Optional[float] = None,
) -> None:
    """What the vendor said the attempt used. Anything left ``None`` is
    charged at its reservation."""
    observer = _usage_observer.get()
    if observer is not None:
        observer.append(AttemptUsage(
            input_tokens=input_tokens, output_tokens=output_tokens,
            model=model, cost_usd=cost_usd,
        ))
    usage = _attempt.get()
    if usage is None:
        return
    if input_tokens is not None:
        usage.input_tokens = int(input_tokens)
    if output_tokens is not None:
        usage.output_tokens = int(output_tokens)
    if model:
        usage.model = str(model)
    if cost_usd is not None:
        usage.cost_usd = float(cost_usd)


# -- generators ---------------------------------------------------------------


def stepwise(events: Iterator, *scopes: Callable[[], ContextManager]):
    """``events``, with ``scopes`` entered around every step and the close.

    Forwards the generator's return value, so ``yield from stepwise(...)``
    reads like ``yield from events``.
    """

    def entered() -> ExitStack:
        stack = ExitStack()
        for scope in scopes:
            stack.enter_context(scope())
        return stack

    while True:
        with entered():
            try:
                item = next(events)
            except StopIteration as stop:
                return stop.value
        try:
            yield item
        except GeneratorExit:
            close = getattr(events, "close", None)
            if close is not None:
                with entered():
                    close()
            raise
