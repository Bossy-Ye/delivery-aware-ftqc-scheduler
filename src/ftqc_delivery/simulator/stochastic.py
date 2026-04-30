"""Optional stochastic delivery simulator."""

from __future__ import annotations

import random
from dataclasses import dataclass

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.metrics.delta_max import t_demand_trace
from ftqc_delivery.metrics.makespan import logical_makespan


@dataclass(frozen=True)
class StochasticTrialResult:
    """Single stochastic delivery trial result."""

    T_static: int
    T_exe: int
    stall_cycles: int
    slowdown: float


def _binomial(rng: random.Random, n: int, p: float) -> int:
    return sum(1 for _ in range(n) if rng.random() < p)


def simulate_stochastic_trial(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
    p_acc: float,
    seed: int,
) -> StochasticTrialResult:
    """Execute one trial where delivered states per cycle follow Binomial(C, p)."""

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if not 0.0 <= p_acc <= 1.0:
        raise ValueError("p_acc must lie in [0, 1]")

    dag.assert_valid_schedule(schedule)
    rng = random.Random(seed)
    t_static = logical_makespan(schedule)
    demand = t_demand_trace(dag, schedule, horizon=t_static)
    available = buffer
    executable_time = 0
    stall_cycles = 0

    for logical_time in range(1, t_static + 1):
        executable_time += 1
        available += _binomial(rng, capacity, p_acc)
        needed = demand.get(logical_time, 0)
        while available < needed:
            stall_cycles += 1
            executable_time += 1
            available += _binomial(rng, capacity, p_acc)
        available -= needed

    slowdown = executable_time / t_static if t_static else 1.0
    return StochasticTrialResult(t_static, executable_time, stall_cycles, slowdown)
