"""Required-capacity helper."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class CapacityThreshold:
    """Result of a required-capacity scan."""

    C_star: int | None
    achieved_slowdown: float | None
    T_static_at_C_star: int | None
    T_exe_at_C_star: int | None


@dataclass(frozen=True)
class ReferenceCapacityThreshold:
    """Result of a fixed-reference required-capacity scan."""

    C_ref_star: int | None
    achieved_T_exe: int | None
    achieved_ratio_to_T_ref: float | None
    T_static_at_C_ref_star: int | None
    stall_cycles_at_C_ref_star: int | None
    Delta_max_at_C_ref_star: int | None


def find_capacity_threshold(
    capacities: Iterable[int],
    epsilon: float,
    evaluator: Callable[[int], tuple[int, int, float]],
) -> CapacityThreshold:
    """Find the smallest C with slowdown <= 1 + epsilon.

    The evaluator returns `(T_static, T_exe, slowdown)` for a candidate capacity.
    """

    for capacity in capacities:
        t_static, t_exe, slowdown = evaluator(capacity)
        if slowdown <= 1.0 + epsilon:
            return CapacityThreshold(
                C_star=capacity,
                achieved_slowdown=slowdown,
                T_static_at_C_star=t_static,
                T_exe_at_C_star=t_exe,
            )
    return CapacityThreshold(None, None, None, None)


def find_reference_capacity_threshold(
    capacities: Iterable[int],
    epsilon: float,
    t_ref: int,
    evaluator: Callable[[int], tuple[int, int, int, int]],
) -> ReferenceCapacityThreshold:
    """Find the smallest C with T_exe <= (1+epsilon)*T_ref.

    The evaluator returns `(T_static, T_exe, stall_cycles, Delta_max)` for a
    candidate capacity. Unlike `find_capacity_threshold`, the denominator is
    fixed across schedules for the same workload and reference type.
    """

    if t_ref <= 0:
        raise ValueError("t_ref must be positive")
    target = (1.0 + epsilon) * t_ref
    for capacity in capacities:
        t_static, t_exe, stall_cycles, delta = evaluator(capacity)
        if t_exe <= target:
            return ReferenceCapacityThreshold(
                C_ref_star=capacity,
                achieved_T_exe=t_exe,
                achieved_ratio_to_T_ref=t_exe / t_ref,
                T_static_at_C_ref_star=t_static,
                stall_cycles_at_C_ref_star=stall_cycles,
                Delta_max_at_C_ref_star=delta,
            )
    return ReferenceCapacityThreshold(None, None, None, None, None, None)
