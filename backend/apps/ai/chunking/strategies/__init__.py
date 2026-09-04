"""Chunking strategies.

Importing this package registers every strategy it ships, which is what makes
``registered_strategies()`` meaningful and what lets the shared contract suite
discover them all.
"""

from . import fixed_window  # noqa: F401  (import registers the strategy)
from . import structural  # noqa: F401  (import registers the strategy)

__all__ = ["fixed_window", "structural"]
