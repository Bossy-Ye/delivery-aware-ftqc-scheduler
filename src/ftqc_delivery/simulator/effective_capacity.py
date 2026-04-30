"""Optional effective-capacity helper for transport-overhead scans."""

from __future__ import annotations

from math import floor


def effective_capacity(nominal_capacity: int, eta: float) -> int:
    """Return max(1, floor(eta*C)) for a nominal capacity and efficiency."""

    if nominal_capacity <= 0:
        raise ValueError("nominal_capacity must be positive")
    if eta < 0:
        raise ValueError("eta must be nonnegative")
    return max(1, floor(eta * nominal_capacity))
