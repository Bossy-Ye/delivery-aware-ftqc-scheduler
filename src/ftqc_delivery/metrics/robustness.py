"""Robustness simulation and summary metrics."""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import sqrt

from ftqc_delivery.dag.graph import CircuitDAG

from .delta_max import t_demand_trace
from .makespan import logical_makespan


@dataclass(frozen=True)
class RobustStochasticTrial:
    """One stochastic delivery trial with tail-risk diagnostics."""

    T_static: int
    T_exe: int
    stall_cycles: int
    BacklogArea: int
    L_backlog: int
    max_backlog: int


def percentile(values: list[float], q: float) -> float:
    """Return a linear-interpolated percentile for q in [0, 1]."""

    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def simulate_stochastic_robustness_trial(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
    p_acc: float,
    seed: int,
) -> RobustStochasticTrial:
    """Run one stochastic delivery trial and collect tail-risk backlog metrics."""

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if not 0.0 <= p_acc <= 1.0:
        raise ValueError("p_acc must lie in [0, 1]")
    dag.assert_valid_schedule(schedule)
    rng = random.Random(seed)
    demand = t_demand_trace(dag, schedule, horizon=logical_makespan(schedule))
    available = buffer
    executable_time = 0
    stall_cycles = 0
    backlog_area = 0
    backlog_active = 0
    max_backlog = 0

    for logical_time in range(1, logical_makespan(schedule) + 1):
        executable_time += 1
        delivered = sum(1 for _ in range(capacity) if rng.random() < p_acc)
        available += delivered
        needed = demand.get(logical_time, 0)
        shortage = max(0, needed - available)
        if shortage > 0:
            backlog_area += shortage
            backlog_active += 1
            max_backlog = max(max_backlog, shortage)
        while available < needed:
            stall_cycles += 1
            executable_time += 1
            delivered = sum(1 for _ in range(capacity) if rng.random() < p_acc)
            available += delivered
        available -= needed

    return RobustStochasticTrial(
        T_static=logical_makespan(schedule),
        T_exe=executable_time,
        stall_cycles=stall_cycles,
        BacklogArea=backlog_area,
        L_backlog=backlog_active,
        max_backlog=max_backlog,
    )


def summarize_stochastic_trials(
    trials: list[RobustStochasticTrial],
    t_ref: int,
) -> dict[str, float]:
    """Summarize stochastic trials for V3 robustness analysis."""

    if not trials:
        raise ValueError("trials must not be empty")
    t_exe = [trial.T_exe for trial in trials]
    ratios = [trial.T_exe / t_ref for trial in trials]
    stalls = [trial.stall_cycles for trial in trials]
    areas = [trial.BacklogArea for trial in trials]
    lengths = [trial.L_backlog for trial in trials]
    mean_t = sum(t_exe) / len(t_exe)
    std_t = sqrt(sum((value - mean_t) ** 2 for value in t_exe) / len(t_exe))
    return {
        "mean_T_exe": mean_t,
        "median_T_exe": percentile([float(value) for value in t_exe], 0.5),
        "p90_T_exe": percentile([float(value) for value in t_exe], 0.9),
        "p95_T_exe": percentile([float(value) for value in t_exe], 0.95),
        "p99_T_exe": percentile([float(value) for value in t_exe], 0.99),
        "std_T_exe": std_t,
        "mean_ratio_to_T_ref": sum(ratios) / len(ratios),
        "p95_ratio_to_T_ref": percentile(ratios, 0.95),
        "p99_ratio_to_T_ref": percentile(ratios, 0.99),
        "mean_stall_cycles": sum(stalls) / len(stalls),
        "p95_stall_cycles": percentile([float(value) for value in stalls], 0.95),
        "stall_probability": sum(1 for value in stalls if value > 0) / len(stalls),
        "target_violation_prob_5pct": sum(1 for value in ratios if value > 1.05) / len(ratios),
        "target_violation_prob_10pct": sum(1 for value in ratios if value > 1.10) / len(ratios),
        "mean_BacklogArea": sum(areas) / len(areas),
        "p95_BacklogArea": percentile([float(value) for value in areas], 0.95),
        "mean_L_backlog": sum(lengths) / len(lengths),
        "p95_L_backlog": percentile([float(value) for value in lengths], 0.95),
    }
