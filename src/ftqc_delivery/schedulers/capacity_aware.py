"""Simple capacity-aware quota scheduler."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG

from .common import Schedule, ready_nodes, split_t_nodes


def schedule_capacity_aware(dag: CircuitDAG, capacity: int) -> Schedule:
    """Schedule ready T gates subject to a per-layer quota.

    This baseline is intentionally simple: it schedules non-T operations ASAP
    and then takes ready T gates in deterministic ID order up to `capacity`.
    It does not use slack, downstream urgency, or buffer-aware lookahead.
    """

    if capacity <= 0:
        raise ValueError("capacity must be positive")

    topo_order = dag.topological_order()
    scheduled: set[str] = set()
    schedule: Schedule = {}
    time_step = 1

    while len(scheduled) < len(dag.nodes):
        ready = ready_nodes(dag, scheduled, topo_order)
        if not ready:
            raise ValueError(f"No ready nodes while scheduling {dag.name!r}")

        non_t, t_nodes = split_t_nodes(dag, ready)
        layer = sorted(non_t) + sorted(t_nodes)[:capacity]
        if not layer:
            layer = sorted(t_nodes)[:1]

        schedule[time_step] = layer
        scheduled.update(layer)
        time_step += 1

    dag.assert_valid_schedule(schedule)
    return schedule
