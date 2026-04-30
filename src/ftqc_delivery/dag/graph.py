"""Lightweight circuit DAG representation used by the schedulers."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable


T_GATE_TYPES = {"T", "Tdg", "Tdag", "T†"}


def is_t_gate(op_type: str) -> bool:
    """Return whether an operation consumes one magic state."""

    return op_type in T_GATE_TYPES


@dataclass
class Node:
    """A node in a circuit DAG."""

    node_id: str
    op_type: str = "Other"
    predecessors: set[str] = field(default_factory=set)
    successors: set[str] = field(default_factory=set)

    @property
    def is_t(self) -> bool:
        """Return whether the node consumes one T state."""

        return is_t_gate(self.op_type)


class CircuitDAG:
    """A deterministic, minimal DAG container for scheduling experiments."""

    def __init__(self, name: str = "dag") -> None:
        self.name = name
        self.nodes: dict[str, Node] = {}

    def add_node(self, node_id: str, op_type: str = "Other") -> None:
        """Add a node if needed, preserving existing edges."""

        if node_id in self.nodes:
            self.nodes[node_id].op_type = op_type
            return
        self.nodes[node_id] = Node(node_id=node_id, op_type=op_type)

    def add_edge(self, predecessor: str, successor: str) -> None:
        """Add a precedence edge between two existing or implicit nodes."""

        if predecessor not in self.nodes:
            self.add_node(predecessor)
        if successor not in self.nodes:
            self.add_node(successor)
        self.nodes[predecessor].successors.add(successor)
        self.nodes[successor].predecessors.add(predecessor)

    def add_edges_from(self, edges: Iterable[tuple[str, str]]) -> None:
        """Add multiple precedence edges."""

        for predecessor, successor in edges:
            self.add_edge(predecessor, successor)

    def successors(self, node_id: str) -> set[str]:
        """Return successors of a node."""

        return set(self.nodes[node_id].successors)

    def predecessors(self, node_id: str) -> set[str]:
        """Return predecessors of a node."""

        return set(self.nodes[node_id].predecessors)

    def op_type(self, node_id: str) -> str:
        """Return the operation type of a node."""

        return self.nodes[node_id].op_type

    def t_nodes(self) -> list[str]:
        """Return all T/Tdg node IDs in deterministic order."""

        return [node_id for node_id in sorted(self.nodes) if self.nodes[node_id].is_t]

    def num_t_gates(self) -> int:
        """Return the number of magic-state-consuming operations."""

        return len(self.t_nodes())

    def topological_order(self) -> list[str]:
        """Return a deterministic topological order or raise on cycles."""

        indegree = {node_id: len(node.predecessors) for node_id, node in self.nodes.items()}
        ready = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
        order: list[str] = []

        while ready:
            node_id = ready.popleft()
            order.append(node_id)
            for successor in sorted(self.nodes[node_id].successors):
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.append(successor)
            ready = deque(sorted(ready))

        if len(order) != len(self.nodes):
            raise ValueError(f"DAG {self.name!r} contains a cycle")
        return order

    def copy(self, name: str | None = None) -> "CircuitDAG":
        """Return a structural copy."""

        copied = CircuitDAG(name=name or self.name)
        for node_id, node in self.nodes.items():
            copied.add_node(node_id, node.op_type)
        for node_id, node in self.nodes.items():
            for successor in node.successors:
                copied.add_edge(node_id, successor)
        return copied

    def schedule_to_time_map(self, schedule: dict[int, list[str]]) -> dict[str, int]:
        """Convert a time-to-node-list schedule to an inverse time map."""

        time_by_node: dict[str, int] = {}
        for time_step, node_ids in schedule.items():
            for node_id in node_ids:
                if node_id in time_by_node:
                    raise ValueError(f"Node {node_id!r} appears more than once in schedule")
                time_by_node[node_id] = time_step
        return time_by_node

    def time_map_to_schedule(self, time_by_node: dict[str, int]) -> dict[int, list[str]]:
        """Convert a node-to-time mapping to deterministic schedule layers."""

        by_time: dict[int, list[str]] = defaultdict(list)
        for node_id, time_step in time_by_node.items():
            by_time[time_step].append(node_id)
        return {time: sorted(nodes) for time, nodes in sorted(by_time.items())}

    def assert_valid_schedule(self, schedule: dict[int, list[str]]) -> None:
        """Raise if a schedule omits nodes, duplicates nodes, or violates dependencies."""

        time_by_node = self.schedule_to_time_map(schedule)
        missing = set(self.nodes) - set(time_by_node)
        extra = set(time_by_node) - set(self.nodes)
        if missing:
            raise ValueError(f"Schedule omits nodes: {sorted(missing)[:8]}")
        if extra:
            raise ValueError(f"Schedule contains unknown nodes: {sorted(extra)[:8]}")

        for node_id, node in self.nodes.items():
            node_time = time_by_node[node_id]
            if node_time < 1:
                raise ValueError(f"Node {node_id!r} is scheduled before logical time 1")
            for predecessor in node.predecessors:
                if time_by_node[predecessor] >= node_time:
                    raise ValueError(
                        f"Dependency violation: {predecessor!r}@{time_by_node[predecessor]} "
                        f"must precede {node_id!r}@{node_time}"
                    )

    def is_valid_schedule(self, schedule: dict[int, list[str]]) -> bool:
        """Return whether a schedule is valid for this DAG."""

        try:
            self.assert_valid_schedule(schedule)
        except ValueError:
            return False
        return True

    @staticmethod
    def max_time(schedule: dict[int, list[str]]) -> int:
        """Return the last logical time step of a schedule."""

        return max(schedule, default=0)
