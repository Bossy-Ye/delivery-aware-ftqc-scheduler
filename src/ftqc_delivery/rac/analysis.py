"""Static structural analysis of a circuit DAG.

These helpers define the static metrics a conventional compiler optimizes
(T-count, T-depth) and the weighted dependency quantities the resource-aware
cost model needs (release times, tails, demand profiles).
"""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG


def node_duration(dag: CircuitDAG, node_id: str, clifford_weight: int = 1) -> int:
    """Return the execution duration of a node in logical cycles."""

    return 1 if dag.nodes[node_id].is_t else clifford_weight


def t_count(dag: CircuitDAG) -> int:
    """Return the number of magic states the circuit consumes."""

    return dag.num_t_gates()


def t_depth(dag: CircuitDAG) -> int:
    """Return the T-depth: the largest number of T gates on any directed path.

    This is the standard notion in which Clifford operations are treated as
    free and unlimited parallelism is available, so it is exactly the
    execution time of the circuit when magic states are unconstrained and
    Cliffords cost nothing.
    """

    longest: dict[str, int] = {}
    for node_id in dag.topological_order():
        best = 0
        for predecessor in dag.predecessors(node_id):
            best = max(best, longest[predecessor])
        longest[node_id] = best + (1 if dag.nodes[node_id].is_t else 0)
    return max(longest.values(), default=0)


def logical_depth(dag: CircuitDAG, clifford_weight: int = 1) -> int:
    """Return the weighted critical-path length with unlimited resources."""

    finish: dict[str, int] = {}
    for node_id in dag.topological_order():
        start = 0
        for predecessor in dag.predecessors(node_id):
            start = max(start, finish[predecessor])
        finish[node_id] = start + node_duration(dag, node_id, clifford_weight)
    return max(finish.values(), default=0)


def release_times(dag: CircuitDAG, clifford_weight: int = 1) -> dict[str, int]:
    """Return the earliest cycle at which each node can start, 1-indexed.

    A node with no predecessors is released at cycle 1. With
    ``clifford_weight == 0`` this collapses Clifford chains to zero cost, so
    release times count only T stages.
    """

    release: dict[str, int] = {}
    for node_id in dag.topological_order():
        start = 1
        for predecessor in dag.predecessors(node_id):
            start = max(
                start,
                release[predecessor] + node_duration(dag, predecessor, clifford_weight),
            )
        release[node_id] = start
    return release


def tails(
    dag: CircuitDAG, clifford_weight: int = 1, order: list[str] | None = None
) -> dict[str, int]:
    """Return the weighted longest path from the end of each node to any sink."""

    tail: dict[str, int] = {}
    for node_id in reversed(order if order is not None else dag.topological_order()):
        best = 0
        for successor in dag.successors(node_id):
            best = max(
                best,
                tail[successor] + node_duration(dag, successor, clifford_weight),
            )
        tail[node_id] = best
    return tail


def t_tails(dag: CircuitDAG, order: list[str] | None = None) -> dict[str, int]:
    """Return the number of T gates on the longest T-chain strictly after a node."""

    tail: dict[str, int] = {}
    for node_id in reversed(order if order is not None else dag.topological_order()):
        best = 0
        for successor in dag.successors(node_id):
            best = max(best, tail[successor] + (1 if dag.nodes[successor].is_t else 0))
        tail[node_id] = best
    return tail


def asap_t_demand(dag: CircuitDAG, clifford_weight: int = 1) -> dict[int, int]:
    """Return the T demand per cycle when every node starts as early as possible.

    This is the demand process ``D(t)`` a depth-oriented compiler implicitly
    requests: it is what the circuit would consume if magic states were free.
    """

    release = release_times(dag, clifford_weight)
    demand: dict[int, int] = {}
    for node_id, start in release.items():
        if dag.nodes[node_id].is_t:
            demand[start] = demand.get(start, 0) + 1
    return demand


def peak_asap_demand(dag: CircuitDAG, clifford_weight: int = 1) -> int:
    """Return the largest number of T gates the ASAP profile requests in one cycle."""

    demand = asap_t_demand(dag, clifford_weight)
    return max(demand.values(), default=0)


def demand_burstiness(dag: CircuitDAG, clifford_weight: int = 1) -> float:
    """Return peak-to-mean ratio of the unconstrained T demand profile.

    A value near 1 means the program requests magic states at a nearly constant
    rate; a large value means the program requests them in bursts.
    """

    demand = asap_t_demand(dag, clifford_weight)
    if not demand:
        return 0.0
    span = logical_depth(dag, clifford_weight)
    if span <= 0:
        return 0.0
    mean = sum(demand.values()) / span
    if mean <= 0:
        return 0.0
    return max(demand.values()) / mean


def ancilla_width(dag: CircuitDAG, clifford_weight: int = 1) -> int:
    """Return the peak number of concurrently running operations under ASAP.

    This is a coarse proxy for the logical qubit footprint a variant needs. It
    is reported rather than constrained, so that an implementation which wins
    only by demanding an unrealistic amount of space can be identified.
    """

    release = release_times(dag, clifford_weight)
    events: dict[int, int] = {}
    for node_id, start in release.items():
        duration = max(1, node_duration(dag, node_id, clifford_weight))
        events[start] = events.get(start, 0) + 1
        events[start + duration] = events.get(start + duration, 0) - 1
    running = 0
    peak = 0
    for cycle in sorted(events):
        running += events[cycle]
        peak = max(peak, running)
    return peak


def static_summary(dag: CircuitDAG, clifford_weight: int = 1) -> dict[str, float]:
    """Return every static metric a conventional compiler could optimize."""

    return {
        "t_count": t_count(dag),
        "t_depth": t_depth(dag),
        "logical_depth": logical_depth(dag, clifford_weight),
        "num_nodes": len(dag.nodes),
        "peak_asap_demand": peak_asap_demand(dag, clifford_weight),
        "burstiness": demand_burstiness(dag, clifford_weight),
        "ancilla_width": ancilla_width(dag, clifford_weight),
    }
