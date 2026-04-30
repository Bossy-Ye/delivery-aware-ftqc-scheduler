"""Backlog metrics under bounded magic-state delivery."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG

from .delta_max import cumulative_demand


def buffer_adjusted_backlog(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
) -> dict[int, int]:
    """Compute backlog[t] = max(0, A_sigma[t] - (C*t + B))."""

    cumulative = cumulative_demand(dag, schedule)
    return {
        time: max(0, total - (capacity * time + buffer))
        for time, total in cumulative.items()
    }


def backlog_active_length(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
) -> int:
    """Count logical time steps where buffer-adjusted backlog is positive."""

    backlog = buffer_adjusted_backlog(dag, schedule, capacity, buffer)
    return sum(1 for value in backlog.values() if value > 0)


def max_backlog(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
) -> int:
    """Return the maximum buffer-adjusted backlog over logical time."""

    backlog = buffer_adjusted_backlog(dag, schedule, capacity, buffer)
    return max(backlog.values(), default=0)


def mean_backlog(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
) -> float:
    """Return mean buffer-adjusted backlog over occupied logical time."""

    backlog = buffer_adjusted_backlog(dag, schedule, capacity, buffer)
    if not backlog:
        return 0.0
    return sum(backlog.values()) / len(backlog)
