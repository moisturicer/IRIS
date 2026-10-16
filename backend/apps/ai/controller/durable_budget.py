"""Controller bounds and pre-work charges survive worker redelivery (IR-597).

Evidence is deliberately rebuilt and reauthorized; only limits and counters
are restored. A charge commits before work, so a crashed worker cannot refund it.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.ai.research.budget import BudgetExhausted, Spend

_attempt = ContextVar("controller_budget_attempt", default=None)
_KEY = "controller_budget"
_COUNTERS = ("rounds", "subtask_calls", "tool_calls", "prompt_tokens")


@contextmanager
def bind(attempt):
    token = _attempt.set(attempt)
    try:
        yield
    finally:
        _attempt.reset(token)


@contextmanager
def _locked(attempt):
    from apps.ai.durable import _locked as owned

    with transaction.atomic():
        run = owned(attempt)
        payload = dict(run.request)
        state = dict(payload.get(_KEY, {}))
        yield state
        payload[_KEY] = state
        run.request = payload
        run.save(update_fields=["request"])


def declare():
    """Capture new-run bounds at submission, before settings can change."""
    from .budget import ControllerBudget
    from apps.ai.research.context import Budget

    return {"controller": asdict(ControllerBudget.from_settings()),
            "research": asdict(Budget.from_settings())}


def prepare_request(request, *, retry=False):
    """Pin a new controller run; a user retry keeps bounds, clears spend."""
    from .versions import CONTROLLER_ENGINE

    payload = dict(request)
    if (payload.get("pin") or {}).get("engine") != CONTROLLER_ENGINE:
        return payload
    state = dict(payload.get(_KEY) or declare())
    if retry:
        state.pop("spent", None)
    payload[_KEY] = state
    return payload


def pinned(name, factory, cls):
    """Read the declared bound before consulting mutable deployment settings."""
    attempt = _attempt.get()
    if attempt is None:
        return factory()
    with _locked(attempt) as state:
        if name not in state:
            state[name] = asdict(factory())
        return cls(**state[name])


def remaining_seconds(seconds):
    """Queue time and previous deliveries consume the declared wall allowance."""
    attempt = _attempt.get()
    if attempt is None:
        return seconds
    from apps.ai.durable import _locked as owned

    with transaction.atomic():
        run = owned(attempt)
        deadline = min(run.deadline_at, run.created_at + timedelta(seconds=seconds))
        return max(0.0, (deadline - timezone.now()).total_seconds())


def restore(spend, *, protected_tokens=0):
    spend.protected_prompt_tokens = protected_tokens
    attempt = _attempt.get()
    return DurableSpend(spend, attempt) if attempt is not None else spend


class DurableSpend(Spend):
    def __init__(self, spend, attempt):
        self.__dict__.update(spend.__dict__)
        self._attempt = attempt
        with _locked(attempt) as state:
            self._load(state)

    def _load(self, state):
        for name in _COUNTERS:
            setattr(self, name, state.get("spent", {}).get(name, 0))

    def _charge(self, method, *args, **kwargs):
        exhausted = None
        with _locked(self._attempt) as state:
            self._load(state)
            try:
                method(*args, **kwargs)
            except BudgetExhausted as exc:
                exhausted = exc
            state["spent"] = {name: getattr(self, name) for name in _COUNTERS}
        if exhausted is not None:
            raise exhausted

    def begin_round(self):
        self._charge(super().begin_round)

    def begin_subtask(self):
        self._charge(super().begin_subtask)

    def charge_call(self, *, subtask=True):
        self._charge(super().charge_call, subtask=subtask)

    def charge_prompt_tokens(self, tokens, *, answer=False):
        if not isinstance(tokens, int) or tokens < 0:
            raise ValueError("prompt charge must be a nonnegative integer")
        self._charge(super().charge_prompt_tokens, tokens, answer=answer)
