"""Cycle-accurate execution against several independent factory banks.

The scheduler is a greedy list scheduler: everything whose predecessors have
finished starts immediately, except that an operation consuming a magic state
waits until a state *of its own kind* is in that resource's buffer. Clifford
operations cost one cycle and consume nothing.

If the machine declares conversions, a small greedy controller runs them: a
conversion starts when the target resource has demand it cannot serve and the
source has stock left over after covering its own ready demand. That is the
mechanism by which the two resources become partly fungible, and switching it
on is the study's main falsification control.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from ftqc_delivery.dag.graph import CircuitDAG

from .resources import Machine

#: Operation types that consume a magic state, and which one.
RESOURCE_OF = {"T": "T", "Tdg": "T", "Tdag": "T", "CCZ": "CCZ"}


def resource_of(op_type: str) -> str | None:
    """Return the resource an operation consumes, or ``None`` for Cliffords."""

    return RESOURCE_OF.get(op_type)


def resource_counts(dag: CircuitDAG) -> dict[str, int]:
    """Return how many states of each kind the circuit consumes."""

    counts: dict[str, int] = {}
    for node in dag.nodes.values():
        name = resource_of(node.op_type)
        if name is not None:
            counts[name] = counts.get(name, 0) + 1
    return counts


def critical_path(dag: CircuitDAG, clifford_weight: int = 1) -> int:
    """Return the longest path length with every operation taking one cycle."""

    finish: dict[str, int] = {}
    for node_id in dag.topological_order():
        start = 0
        for predecessor in dag.predecessors(node_id):
            start = max(start, finish[predecessor])
        duration = 1 if resource_of(dag.op_type(node_id)) else clifford_weight
        finish[node_id] = start + duration
    return max(finish.values(), default=0)


def resource_tails(dag: CircuitDAG, clifford_weight: int = 1) -> dict[str, int]:
    """Return the longest remaining path after each node finishes."""

    tail: dict[str, int] = {}
    for node_id in reversed(dag.topological_order()):
        best = 0
        for successor in dag.successors(node_id):
            duration = 1 if resource_of(dag.op_type(successor)) else clifford_weight
            best = max(best, tail[successor] + duration)
        tail[node_id] = best
    return tail


@dataclass
class Trace:
    """What happened during one constrained execution."""

    makespan: int
    consumed: dict[str, int] = field(default_factory=dict)
    stalls: dict[str, int] = field(default_factory=dict)
    overflow: dict[str, int] = field(default_factory=dict)
    conversions: dict[str, int] = field(default_factory=dict)
    demand_series: dict[str, list[int]] = field(default_factory=dict)
    arrival_series: dict[str, list[int]] = field(default_factory=dict)
    stock_series: dict[str, list[int]] = field(default_factory=dict)

    @property
    def total_stalls(self) -> int:
        """Return the cycles spent waiting on some magic state."""

        return sum(self.stalls.values())


def execute(
    dag: CircuitDAG,
    machine: Machine,
    clifford_weight: int = 1,
    priority: str = "critical",
    record_trace: bool = False,
    cycle_limit: int | None = None,
) -> Trace:
    """Run ``dag`` on ``machine`` and return the resulting trace.

    Args:
        dag: The circuit to execute.
        machine: Factory banks and any conversions between them.
        clifford_weight: Cycles charged per non-consuming operation.
        priority: ``critical`` prefers operations with the most work behind
            them; ``topological`` breaks ties by program order.
        record_trace: Whether to keep the per-cycle series.
        cycle_limit: Safety bound on the simulated makespan.

    Returns:
        A :class:`Trace` whose ``makespan`` is the execution time in logical
        cycles.

    Raises:
        RuntimeError: If a resource the circuit needs has no factory bank, so
            execution could never finish.
    """

    order = dag.topological_order()
    kind = {node_id: resource_of(dag.op_type(node_id)) for node_id in order}
    needed = {value for value in kind.values() if value is not None}
    producible = set(machine.resources)
    for conversion in machine.conversions:
        producible.add(conversion.target)
    missing = needed - producible
    if missing:
        raise RuntimeError(
            f"machine cannot produce {sorted(missing)} required by {dag.name!r}"
        )

    rank = {node_id: index for index, node_id in enumerate(order)}
    if priority == "critical":
        tail = resource_tails(dag, clifford_weight)
        key = {node_id: (-tail[node_id], rank[node_id]) for node_id in order}
    elif priority == "topological":
        key = {node_id: (rank[node_id],) for node_id in order}
    else:
        raise ValueError(f"unknown priority {priority!r}")

    successors = {node_id: sorted(dag.successors(node_id)) for node_id in order}
    remaining = {node_id: len(dag.predecessors(node_id)) for node_id in order}

    ready: dict[str | None, list[tuple[tuple, str]]] = {None: []}
    for resource in machine.resources:
        ready[resource] = []
    for resource in producible:
        ready.setdefault(resource, [])

    def push(node_id: str) -> None:
        heapq.heappush(ready[kind[node_id]], (key[node_id], node_id))

    for node_id in order:
        if remaining[node_id] == 0:
            push(node_id)

    horizon = 2048
    arrivals = {
        bank.resource: bank.arrival_series(horizon, seed=machine.seed)
        for bank in machine.banks
    }
    stock = {resource: 0 for resource in producible}
    consumed = {resource: 0 for resource in producible}
    stalls = {resource: 0 for resource in producible}
    overflow = {resource: 0 for resource in producible}
    conversion_labels = {
        conversion: f"{conversion.inputs}{conversion.source}->"
        f"{conversion.outputs}{conversion.target}"
        for conversion in machine.conversions
    }
    conversions_run = {label: 0 for label in conversion_labels.values()}
    pending: dict[int, list[tuple[str, int, str]]] = {}
    in_flight = {label: 0 for label in conversion_labels.values()}

    demand_series = {resource: [] for resource in producible}
    arrival_series = {resource: [] for resource in producible}
    stock_series = {resource: [] for resource in producible}

    finishing: dict[int, list[str]] = {}
    completed = 0
    total = len(order)
    cycle = 0
    last_finish = 0
    limit = cycle_limit if cycle_limit is not None else 200 * (total + 1) + 200_000

    while completed < total:
        cycle += 1
        if cycle > limit:
            raise RuntimeError(f"execution of {dag.name!r} exceeded {limit} cycles")
        if cycle >= horizon:
            horizon *= 4
            arrivals = {
                bank.resource: bank.arrival_series(horizon, seed=machine.seed)
                for bank in machine.banks
            }

        for node_id in finishing.pop(cycle, ()):
            completed += 1
            for successor in successors[node_id]:
                remaining[successor] -= 1
                if remaining[successor] == 0:
                    push(successor)

        arrived = {resource: 0 for resource in producible}
        for resource, series in arrivals.items():
            arrived[resource] += series[cycle]
        for resource, count, label in pending.pop(cycle, ()):
            arrived[resource] += count
            in_flight[label] -= 1

        for resource in producible:
            bank = machine.bank(resource)
            stock[resource] += arrived[resource]
            if bank is not None and not bank.unbounded_buffer:
                if stock[resource] > bank.buffer_capacity:
                    overflow[resource] += stock[resource] - bank.buffer_capacity
                    arrived[resource] -= stock[resource] - bank.buffer_capacity
                    stock[resource] = bank.buffer_capacity

        _run_conversions(
            machine,
            conversion_labels,
            stock,
            ready,
            pending,
            in_flight,
            conversions_run,
            cycle,
        )

        started = 0
        used = {resource: 0 for resource in producible}

        if clifford_weight == 0:
            while ready[None]:
                _, node_id = heapq.heappop(ready[None])
                last_finish = max(last_finish, cycle - 1)
                completed += 1
                for successor in successors[node_id]:
                    remaining[successor] -= 1
                    if remaining[successor] == 0:
                        push(successor)
        else:
            while ready[None]:
                _, node_id = heapq.heappop(ready[None])
                finishing.setdefault(cycle + clifford_weight, []).append(node_id)
                last_finish = max(last_finish, cycle + clifford_weight - 1)
                started += 1

        for resource in producible:
            queue = ready[resource]
            while queue and stock[resource] > 0:
                _, node_id = heapq.heappop(queue)
                stock[resource] -= 1
                consumed[resource] += 1
                used[resource] += 1
                finishing.setdefault(cycle + 1, []).append(node_id)
                last_finish = max(last_finish, cycle)
                started += 1
            if queue and stock[resource] <= 0:
                stalls[resource] += 1

        if record_trace:
            for resource in producible:
                demand_series[resource].append(used[resource])
                arrival_series[resource].append(arrived[resource])
                stock_series[resource].append(stock[resource])

        if completed >= total:
            break

    makespan = max(last_finish, 0)
    if record_trace:
        for resource in producible:
            demand_series[resource] = demand_series[resource][:makespan]
            arrival_series[resource] = arrival_series[resource][:makespan]
            stock_series[resource] = stock_series[resource][:makespan]

    return Trace(
        makespan=makespan,
        consumed=consumed,
        stalls=stalls,
        overflow=overflow,
        conversions=conversions_run,
        demand_series=demand_series,
        arrival_series=arrival_series,
        stock_series=stock_series,
    )


def _run_conversions(
    machine, labels, stock, ready, pending, in_flight, counters, cycle
) -> None:
    """Start any conversions that would unblock a starved resource.

    A conversion is worth starting when the target has work waiting that it
    cannot serve, and the source has more stock than its own waiting work
    needs. Both conditions are checked against the queues as they stand, so the
    controller never starves one resource to feed another.
    """

    for conversion in machine.conversions:
        label = labels[conversion]
        while in_flight[label] < conversion.concurrency:
            target_waiting = len(ready.get(conversion.target, ()))
            if target_waiting == 0 or stock.get(conversion.target, 0) > 0:
                break
            source_waiting = len(ready.get(conversion.source, ()))
            if stock.get(conversion.source, 0) - conversion.inputs < source_waiting:
                break
            stock[conversion.source] -= conversion.inputs
            in_flight[label] += 1
            pending.setdefault(cycle + conversion.latency, []).append(
                (conversion.target, conversion.outputs, label)
            )
            counters[label] += 1


def execution_time(
    dag: CircuitDAG,
    machine: Machine,
    clifford_weight: int = 1,
    priority: str = "critical",
) -> int:
    """Return the constrained makespan in logical cycles."""

    return execute(
        dag, machine, clifford_weight=clifford_weight, priority=priority
    ).makespan
