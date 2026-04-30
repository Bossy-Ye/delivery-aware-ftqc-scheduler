"""Shared scheduler helpers."""

from __future__ import annotations

from math import ceil

from ftqc_delivery.dag.graph import CircuitDAG, is_t_gate
from ftqc_delivery.dag.slack import asap_times


Schedule = dict[int, list[str]]


def ready_nodes(dag: CircuitDAG, scheduled: set[str], topo_order: list[str]) -> list[str]:
    """Return ready unscheduled nodes in topological order."""

    return [
        node_id
        for node_id in topo_order
        if node_id not in scheduled and dag.predecessors(node_id).issubset(scheduled)
    ]


def split_t_nodes(dag: CircuitDAG, node_ids: list[str]) -> tuple[list[str], list[str]]:
    """Split node IDs into non-T and T/Tdg nodes."""

    non_t = [node_id for node_id in node_ids if not is_t_gate(dag.op_type(node_id))]
    t_nodes = [node_id for node_id in node_ids if is_t_gate(dag.op_type(node_id))]
    return non_t, t_nodes


def planning_horizon(dag: CircuitDAG, capacity: int) -> int:
    """Return a conservative logical horizon for slack-based heuristics."""

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    asap = asap_times(dag)
    base_depth = max(asap.values(), default=0)
    t_depth_floor = ceil(dag.num_t_gates() / capacity) + 2
    return max(base_depth, t_depth_floor)


def schedule_depth(schedule: Schedule) -> int:
    """Return the last occupied logical time."""

    return max(schedule, default=0)
