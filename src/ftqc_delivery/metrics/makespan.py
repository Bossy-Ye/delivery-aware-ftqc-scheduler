"""Logical makespan helpers."""

from __future__ import annotations


def logical_makespan(schedule: dict[int, list[str]]) -> int:
    """Return the last logical time step occupied by a schedule."""

    return max(schedule, default=0)
