"""Strategy registry.

A registry rather than an ``if/else`` chain: adding a strategy is a
registration, not an edit to a growing conditional. Comparing one strategy
against another on the eval set becomes a configuration change.

The strategy id is recorded on every ChunkSet, so when a strategy changes,
that value says exactly which stored sets need rebuilding.
"""

from typing import Callable, TypeVar

from .ports import Chunker, EvaluationOnlyStrategy, UnknownChunkingStrategy
from .values import ChunkingOptions

_REGISTRY: dict[str, type] = {}
# Baselines kept for measurement only, never for ingestion (IR-1054).
_EVALUATION_ONLY: set[str] = set()

T = TypeVar("T")


def register_chunker(strategy_id: str, *, evaluation_only: bool = False) -> Callable[[type], type]:
    """Register a chunker class under ``strategy_id``."""

    def decorator(cls: type) -> type:
        if strategy_id in _REGISTRY and _REGISTRY[strategy_id] is not cls:
            raise ValueError(
                f"chunking strategy {strategy_id!r} is already registered to "
                f"{_REGISTRY[strategy_id].__name__}"
            )
        _REGISTRY[strategy_id] = cls
        if evaluation_only:
            _EVALUATION_ONLY.add(strategy_id)
        return cls

    return decorator


def registered_strategies() -> list[str]:
    """The strategy ids known to this process."""
    return sorted(_REGISTRY)


def ingestion_strategies() -> list[str]:
    """The strategy ids ingestion may use: every one but the baselines."""
    return sorted(set(_REGISTRY) - _EVALUATION_ONLY)


def require_ingestion_strategy(strategy_id: str) -> None:
    """Refuse a baseline that is registered for measurement only (IR-1054)."""
    if strategy_id in _EVALUATION_ONLY:
        raise EvaluationOnlyStrategy(strategy_id, ingestion_strategies())


def build_chunker(options: ChunkingOptions) -> Chunker:
    """Build the chunker named by ``options.strategy``.

    Raises ``UnknownChunkingStrategy`` — naming the ids it does know — rather
    than falling through to a default.
    """
    try:
        cls = _REGISTRY[options.strategy]
    except KeyError:
        raise UnknownChunkingStrategy(
            options.strategy, registered_strategies()
        ) from None
    return cls()
