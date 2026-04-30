"""Slack-based smoothing scheduler."""

from __future__ import annotations

from math import ceil

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.dag.slack import alap_times

from .common import Schedule, planning_horizon, ready_nodes, split_t_nodes


def schedule_smooth(dag: CircuitDAG, capacity: int = 1) -> Schedule:
    """Spread ready T gates using slack, without delivery/backlog scoring.

    The heuristic computes ALAP latest starts over a conservative horizon and
    schedules urgent T gates first. Flexible T gates are admitted according to a
    global cumulative demand target, so bursts are spread when slack permits.
    """

    if capacity <= 0:
        raise ValueError("capacity must be positive")

    horizon = planning_horizon(dag, capacity)
    latest = alap_times(dag, horizon=horizon)
    total_t = dag.num_t_gates()
    topo_order = dag.topological_order()
    scheduled: set[str] = set()
    cumulative_t = 0
    schedule: Schedule = {}
    time_step = 1

    while len(scheduled) < len(dag.nodes):
        ready = ready_nodes(dag, scheduled, topo_order)
        if not ready:
            raise ValueError(f"No ready nodes while scheduling {dag.name!r}")

        non_t, t_nodes = split_t_nodes(dag, ready)
        layer = sorted(non_t)

        target_cumulative = min(total_t, ceil(total_t * min(time_step, horizon) / horizon))
        desired = max(0, target_cumulative - cumulative_t)
        quota = min(capacity, max(desired, 0))

        def slack_key(node_id: str) -> tuple[int, str]:
            return (latest[node_id] - time_step, node_id)

        urgent = [node_id for node_id in t_nodes if latest[node_id] <= time_step]
        flexible = [node_id for node_id in t_nodes if node_id not in urgent]
        selected_t = sorted(urgent, key=slack_key)
        remaining_slots = max(0, quota - len(selected_t))
        selected_t.extend(sorted(flexible, key=slack_key)[:remaining_slots])

        if not layer and not selected_t and t_nodes:
            selected_t = [sorted(t_nodes, key=slack_key)[0]]

        layer.extend(selected_t)
        schedule[time_step] = layer
        scheduled.update(layer)
        cumulative_t += len(selected_t)
        time_step += 1

    dag.assert_valid_schedule(schedule)
    return schedule
