"""Small statistics the evaluation reports share."""

from __future__ import annotations

import math
from typing import Optional, Sequence


def percentile(values: Sequence[float], fraction: float) -> Optional[float]:
    """Nearest-rank, so a small sample reports a value it contains."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(math.ceil(fraction * len(ordered)), 1) - 1]
