"""Backlog shape metrics for fixed schedules."""

from __future__ import annotations

from dataclasses import dataclass

from ftqc_delivery.dag.graph import CircuitDAG

from .backlog import buffer_adjusted_backlog
from .makespan import logical_makespan


@dataclass(frozen=True)
class BacklogShape:
    """Summary of backlog persistence and area."""

    BacklogArea: int
    L_backlog: int
    max_backlog: int
    mean_backlog: float
    num_backlog_intervals: int
    longest_backlog_interval: int
    backlog_persistence_ratio: float


def backlog_shape_features(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
) -> BacklogShape:
    """Compute area, interval, and persistence metrics for backlog."""

    backlog = buffer_adjusted_backlog(dag, schedule, capacity, buffer)
    values = [backlog.get(time, 0) for time in range(1, logical_makespan(schedule) + 1)]
    area = sum(values)
    active = sum(1 for value in values if value > 0)
    max_value = max(values, default=0)
    mean_value = area / len(values) if values else 0.0
    intervals = 0
    longest = 0
    current = 0
    for value in values:
        if value > 0:
            current += 1
            if current == 1:
                intervals += 1
            longest = max(longest, current)
        else:
            current = 0
    persistence = active / len(values) if values else 0.0
    return BacklogShape(
        BacklogArea=area,
        L_backlog=active,
        max_backlog=max_value,
        mean_backlog=mean_value,
        num_backlog_intervals=intervals,
        longest_backlog_interval=longest,
        backlog_persistence_ratio=persistence,
    )
