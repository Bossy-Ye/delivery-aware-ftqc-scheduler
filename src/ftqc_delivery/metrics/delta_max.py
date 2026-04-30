"""Demand-trace and Delta_max metrics."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG, is_t_gate


def _horizon(schedule: dict[int, list[str]], horizon: int | None = None) -> int:
    return horizon if horizon is not None else max(schedule, default=0)


def t_demand_trace(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    horizon: int | None = None,
) -> dict[int, int]:
    """Compute D_sigma[t], the number of T/Tdg gates scheduled at each time."""

    max_time = _horizon(schedule, horizon)
    demand = {time: 0 for time in range(1, max_time + 1)}
    for time_step, node_ids in schedule.items():
        demand.setdefault(time_step, 0)
        demand[time_step] += sum(1 for node_id in node_ids if is_t_gate(dag.op_type(node_id)))
    return dict(sorted(demand.items()))


def cumulative_demand(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    horizon: int | None = None,
) -> dict[int, int]:
    """Compute A_sigma[t] = sum_{tau <= t} D_sigma[tau]."""

    demand = t_demand_trace(dag, schedule, horizon=horizon)
    cumulative: dict[int, int] = {}
    running = 0
    for time_step in sorted(demand):
        running += demand[time_step]
        cumulative[time_step] = running
    return cumulative


def delta_max(dag: CircuitDAG, schedule: dict[int, list[str]], capacity: int) -> int:
    """Compute max_t max(0, A_sigma[t] - C*t) with 1-indexed logical time."""

    cumulative = cumulative_demand(dag, schedule)
    if not cumulative:
        return 0
    return max(0, max(total - capacity * time for time, total in cumulative.items()))
