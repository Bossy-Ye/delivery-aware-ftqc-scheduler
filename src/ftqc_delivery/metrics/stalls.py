"""Stall-related helpers."""

from __future__ import annotations


def stall_fraction(stall_cycles: int, executable_makespan: int) -> float:
    """Return the fraction of executable cycles spent stalled."""

    if executable_makespan <= 0:
        return 0.0
    return stall_cycles / executable_makespan
