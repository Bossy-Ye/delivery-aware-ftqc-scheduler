"""Fixed-reference buffer threshold metrics."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class BufferThreshold:
    """Result of a fixed-reference buffer scan."""

    B_ref_star: int | None
    achieved_T_exe: int | None
    achieved_ratio_to_T_ref: float | None
    T_static_at_B_ref_star: int | None
    stall_cycles_at_B_ref_star: int | None
    Delta_max_at_B_ref_star: int | None


def find_buffer_reference_threshold(
    buffers: Iterable[int],
    epsilon: float,
    t_ref: int,
    evaluator: Callable[[int], tuple[int, int, int, int]],
) -> BufferThreshold:
    """Find the smallest B with T_exe <= (1+epsilon)*T_ref.

    The evaluator returns `(T_static, T_exe, stall_cycles, Delta_max)` for a
    candidate buffer at fixed delivery capacity.
    """

    if t_ref <= 0:
        raise ValueError("t_ref must be positive")
    target = (1.0 + epsilon) * t_ref
    for buffer in buffers:
        t_static, t_exe, stall_cycles, delta = evaluator(buffer)
        if t_exe <= target:
            return BufferThreshold(
                B_ref_star=buffer,
                achieved_T_exe=t_exe,
                achieved_ratio_to_T_ref=t_exe / t_ref,
                T_static_at_B_ref_star=t_static,
                stall_cycles_at_B_ref_star=stall_cycles,
                Delta_max_at_B_ref_star=delta,
            )
    return BufferThreshold(None, None, None, None, None, None)
