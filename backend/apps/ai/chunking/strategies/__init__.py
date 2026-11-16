"""Chunking strategies.

Importing this package registers the production strategy, which is what makes
``registered_strategies()`` meaningful. The fixed-window baseline lives in
``apps.ai.evaluation.fixed_window`` and registers for measurement only
(IR-1054).
"""

from . import structural  # noqa: F401  (import registers the strategy)

__all__ = ["structural"]
