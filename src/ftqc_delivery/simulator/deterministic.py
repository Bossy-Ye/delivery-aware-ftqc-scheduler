"""Deterministic bounded-delivery simulator."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.metrics.backlog import backlog_active_length
from ftqc_delivery.metrics.delta_max import delta_max, t_demand_trace
from ftqc_delivery.metrics.makespan import logical_makespan


@dataclass(frozen=True)
class DeterministicSimulationResult:
    """Summary of executing a fixed logical schedule under bounded delivery."""

    T_static: int
    T_exe: int
    stall_cycles: int
    slowdown: float
    Delta_max: int
    L_backlog: int
    feasible: bool = True


def simulate_deterministic(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
) -> DeterministicSimulationResult:
    """Execute a fixed schedule with capacity C and initial buffer B.

    At each executable cycle, `capacity` magic states are delivered before the
    logical layer consumes its scheduled T/Tdg gates. If the layer lacks enough
    available states, stall cycles are inserted until it can execute.
    """

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if buffer < 0:
        raise ValueError("buffer must be nonnegative")

    dag.assert_valid_schedule(schedule)
    t_static = logical_makespan(schedule)
    demand = t_demand_trace(dag, schedule, horizon=t_static)

    available = buffer
    executable_time = 0
    stall_cycles = 0

    for logical_time in range(1, t_static + 1):
        executable_time += 1
        available += capacity
        needed = demand.get(logical_time, 0)
        if available < needed:
            missing = needed - available
            stalls = ceil(missing / capacity)
            stall_cycles += stalls
            executable_time += stalls
            available += stalls * capacity
        available -= needed

    slowdown = executable_time / t_static if t_static else 1.0
    return DeterministicSimulationResult(
        T_static=t_static,
        T_exe=executable_time,
        stall_cycles=stall_cycles,
        slowdown=slowdown,
        Delta_max=delta_max(dag, schedule, capacity),
        L_backlog=backlog_active_length(dag, schedule, capacity, buffer),
        feasible=True,
    )
