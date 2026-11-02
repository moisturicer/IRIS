"""Which run a provider attempt belongs to (IR-725).

Set by the run service around an executor, so no port grows a parameter.
An attempt made outside any run is refused: AI-runtime paid work is run work.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass(frozen=True)
class RunBinding:
    run_id: uuid.UUID
    #: The claim's fence; a superseded or stopped run admits nothing.
    fence: int

    @property
    def key(self) -> str:
        return run_key(self.run_id)


def run_key(run_id) -> str:
    """Django's `run_key` for an AI run; per-run caps sum over it."""
    return f"airun:{uuid.UUID(str(run_id)).hex}"


_run: ContextVar[Optional[RunBinding]] = ContextVar("ai_admission_run", default=None)


@contextmanager
def bound(binding: RunBinding) -> Iterator[RunBinding]:
    token = _run.set(binding)
    try:
        yield binding
    finally:
        _run.reset(token)


def current() -> Optional[RunBinding]:
    return _run.get()
