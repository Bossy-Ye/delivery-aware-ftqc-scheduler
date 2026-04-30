"""Depth-oriented ASAP scheduler."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG

from .common import Schedule, ready_nodes


def schedule_static(dag: CircuitDAG) -> Schedule:
    """Schedule every operation as early as dependencies allow."""

    topo_order = dag.topological_order()
    scheduled: set[str] = set()
    schedule: Schedule = {}
    time_step = 1

    while len(scheduled) < len(dag.nodes):
        ready = ready_nodes(dag, scheduled, topo_order)
        if not ready:
            raise ValueError(f"No ready nodes while scheduling {dag.name!r}")
        schedule[time_step] = sorted(ready)
        scheduled.update(ready)
        time_step += 1

    dag.assert_valid_schedule(schedule)
    return schedule
