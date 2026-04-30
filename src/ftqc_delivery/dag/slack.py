"""ASAP/ALAP timing, slack, and simple criticality metrics."""

from __future__ import annotations

from collections import deque

from .graph import CircuitDAG


def asap_times(dag: CircuitDAG) -> dict[str, int]:
    """Compute earliest feasible 1-indexed logical time for each node."""

    times: dict[str, int] = {}
    for node_id in dag.topological_order():
        predecessors = dag.predecessors(node_id)
        if not predecessors:
            times[node_id] = 1
        else:
            times[node_id] = 1 + max(times[pred] for pred in predecessors)
    return times


def alap_times(dag: CircuitDAG, horizon: int | None = None) -> dict[str, int]:
    """Compute latest feasible 1-indexed logical time for each node."""

    asap = asap_times(dag)
    if horizon is None:
        horizon = max(asap.values(), default=0)

    latest: dict[str, int] = {}
    for node_id in reversed(dag.topological_order()):
        successors = dag.successors(node_id)
        if not successors:
            latest[node_id] = horizon
        else:
            latest[node_id] = min(latest[succ] - 1 for succ in successors)
    return latest


def slack_times(dag: CircuitDAG, horizon: int | None = None) -> dict[str, int]:
    """Compute ALAP-ASAP slack for each node."""

    asap = asap_times(dag)
    alap = alap_times(dag, horizon=horizon)
    return {node_id: alap[node_id] - asap[node_id] for node_id in dag.nodes}


def longest_paths_to_sink(dag: CircuitDAG) -> dict[str, int]:
    """Return the longest remaining path length from each node to any sink."""

    distance: dict[str, int] = {}
    for node_id in reversed(dag.topological_order()):
        successors = dag.successors(node_id)
        if not successors:
            distance[node_id] = 0
        else:
            distance[node_id] = 1 + max(distance[succ] for succ in successors)
    return distance


def descendant_counts(dag: CircuitDAG) -> dict[str, int]:
    """Return the number of descendants reachable from each node."""

    descendants: dict[str, set[str]] = {node_id: set() for node_id in dag.nodes}
    for node_id in reversed(dag.topological_order()):
        reached: set[str] = set()
        for successor in dag.successors(node_id):
            reached.add(successor)
            reached.update(descendants[successor])
        descendants[node_id] = reached
    return {node_id: len(reached) for node_id, reached in descendants.items()}


def normalize_scores(values: dict[str, int | float]) -> dict[str, float]:
    """Normalize nonnegative scores to [0, 1]."""

    if not values:
        return {}
    max_value = max(values.values())
    if max_value <= 0:
        return {key: 0.0 for key in values}
    return {key: float(value) / float(max_value) for key, value in values.items()}


def ready_nodes(dag: CircuitDAG, scheduled: set[str]) -> list[str]:
    """Return deterministic ready nodes given a set of already scheduled nodes."""

    ready: list[str] = []
    for node_id in dag.topological_order():
        if node_id in scheduled:
            continue
        if dag.predecessors(node_id).issubset(scheduled):
            ready.append(node_id)
    return ready
