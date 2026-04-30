"""Robust slack-smoothing baseline with a delivery safety margin."""

from __future__ import annotations

from math import floor

from ftqc_delivery.dag.graph import CircuitDAG

from .smooth import schedule_smooth


def robust_smooth_target_capacity(
    capacity: int,
    p_acc: float = 1.0,
    rho: float = 0.9,
) -> int:
    """Return max(1, floor(rho*C*p_acc)) for robust smoothing."""

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if not 0.0 <= p_acc <= 1.0:
        raise ValueError("p_acc must lie in [0, 1]")
    if rho <= 0:
        raise ValueError("rho must be positive")
    return max(1, floor(rho * capacity * p_acc))


def schedule_robust_smooth(
    dag: CircuitDAG,
    capacity: int,
    p_acc: float = 1.0,
    rho: float = 0.9,
) -> dict[int, list[str]]:
    """Schedule using smooth with a conservative target delivery rate."""

    return schedule_smooth(dag, robust_smooth_target_capacity(capacity, p_acc, rho))
