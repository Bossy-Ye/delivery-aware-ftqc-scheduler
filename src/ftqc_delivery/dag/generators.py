"""Small graph-construction helpers for workload generators."""

from __future__ import annotations

from .graph import CircuitDAG


def add_linear_chain(
    dag: CircuitDAG,
    prefix: str,
    length: int,
    start: str | None = None,
    op_type: str = "Clifford",
    t_every: int | None = None,
) -> list[str]:
    """Add a linear chain and return node IDs in chain order."""

    previous = start
    chain: list[str] = []
    for index in range(length):
        node_id = f"{prefix}_{index:04d}"
        node_type = "T" if t_every and index % t_every == 0 else op_type
        dag.add_node(node_id, node_type)
        if previous is not None:
            dag.add_edge(previous, node_id)
        previous = node_id
        chain.append(node_id)
    return chain


def add_burst(
    dag: CircuitDAG,
    prefix: str,
    count: int,
    predecessor: str,
    successor: str,
    op_type: str = "T",
) -> list[str]:
    """Add a burst of independent T-like gates between two boundary nodes."""

    nodes: list[str] = []
    for index in range(count):
        node_id = f"{prefix}_{index:04d}"
        dag.add_node(node_id, op_type)
        dag.add_edge(predecessor, node_id)
        dag.add_edge(node_id, successor)
        nodes.append(node_id)
    return nodes


def add_sink_join(dag: CircuitDAG, sink_id: str, predecessors: list[str]) -> None:
    """Add a sink node that joins multiple predecessors."""

    dag.add_node(sink_id, "Other")
    for predecessor in predecessors:
        dag.add_edge(predecessor, sink_id)
