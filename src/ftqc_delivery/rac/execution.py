"""Constrained execution of a circuit DAG against a magic-state supply process.

Execution is a cycle-accurate greedy list scheduler. Every ready operation
starts as soon as the machine allows it, and a T gate is additionally gated on
a magic state being present in the buffer. Nothing else stalls the machine, so
the only source of slowdown relative to the dependency critical path is supply.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Callable, Sequence

from ftqc_delivery.dag.graph import CircuitDAG

from .analysis import node_duration, t_tails, tails
from .supply import SupplyModel


PriorityFn = Callable[[str], tuple]
PRIORITIES = ("topological", "critical_path", "t_critical")


@dataclass
class ExecutionTrace:
    """Cycle-accurate record of one constrained execution."""

    makespan: int
    t_executed: int
    supply_stall_cycles: int
    idle_cycles: int
    overflow: int
    demand: list[int] = field(default_factory=list)
    arrivals: list[int] = field(default_factory=list)
    stock: list[int] = field(default_factory=list)
    running: list[int] = field(default_factory=list)

    @property
    def stall_fraction(self) -> float:
        """Return the fraction of cycles spent waiting on magic states."""

        return self.supply_stall_cycles / self.makespan if self.makespan else 0.0


def make_priority(
    dag: CircuitDAG,
    name: str,
    clifford_weight: int = 1,
    topo_order: list[str] | None = None,
) -> PriorityFn:
    """Return a deterministic tie-breaking priority over ready nodes."""

    topo_order = topo_order if topo_order is not None else dag.topological_order()
    order = {node_id: index for index, node_id in enumerate(topo_order)}
    if name == "topological":
        return lambda node_id: (order[node_id],)
    if name == "critical_path":
        tail = tails(dag, clifford_weight, order=topo_order)
        return lambda node_id: (-tail[node_id], order[node_id])
    if name == "t_critical":
        tail = t_tails(dag, order=topo_order)
        return lambda node_id: (-tail[node_id], order[node_id])
    raise ValueError(f"unknown priority {name!r}")


def execute(
    dag: CircuitDAG,
    supply: SupplyModel,
    priority: str = "t_critical",
    clifford_weight: int = 1,
    max_parallel_ops: int | None = None,
    record_trace: bool = True,
    cycle_limit: int | None = None,
) -> ExecutionTrace:
    """Execute ``dag`` greedily under ``supply`` and return the resulting trace.

    Args:
        dag: The circuit to execute.
        supply: The magic-state supply process.
        priority: Tie-break order among simultaneously ready operations.
        clifford_weight: Cycles charged per non-T operation. Setting this to 0
            makes Clifford operations free, which isolates magic-state supply
            as the only cost beyond T-gate dependency structure.
        max_parallel_ops: Optional cap on operations started per cycle.
        record_trace: Whether to record per-cycle demand, supply and stock.
        cycle_limit: Safety bound on the simulated makespan.

    Returns:
        An :class:`ExecutionTrace` whose ``makespan`` is the constrained
        execution time in logical cycles.
    """

    if clifford_weight < 0:
        raise ValueError("clifford_weight must be nonnegative")

    order = dag.topological_order()
    key = make_priority(dag, priority, clifford_weight, topo_order=order)
    successors = {node_id: sorted(dag.successors(node_id)) for node_id in order}
    is_t = {node_id: dag.nodes[node_id].is_t for node_id in order}
    remaining_preds = {node_id: len(dag.predecessors(node_id)) for node_id in order}

    ready_t: list[tuple[tuple, str]] = []
    ready_other: list[tuple[tuple, str]] = []

    def push(node_id: str) -> None:
        heap = ready_t if is_t[node_id] else ready_other
        heapq.heappush(heap, (key(node_id), node_id))

    for node_id in order:
        if remaining_preds[node_id] == 0:
            push(node_id)

    total_nodes = len(order)
    completed = 0
    stock = supply.initial_stock
    if not supply.unbounded_buffer:
        stock = min(stock, supply.buffer_capacity)

    finishing: dict[int, list[str]] = {}
    demand_trace: list[int] = []
    arrival_trace: list[int] = []
    stock_trace: list[int] = []
    running_trace: list[int] = []
    supply_stall_cycles = 0
    idle_cycles = 0
    overflow = 0
    in_flight = 0
    last_finish = 0
    cycle = 0
    limit = cycle_limit if cycle_limit is not None else 64 * (total_nodes + 1) + 100_000
    horizon = 1024
    arrivals = supply.arrival_series(horizon)

    def retire(node_id: str) -> None:
        nonlocal completed
        completed += 1
        for successor in successors[node_id]:
            remaining_preds[successor] -= 1
            if remaining_preds[successor] == 0:
                push(successor)

    while completed < total_nodes:
        cycle += 1
        if cycle > limit:
            raise RuntimeError(f"execution of {dag.name!r} exceeded {limit} cycles")

        for node_id in finishing.pop(cycle, ()):
            in_flight -= 1
            retire(node_id)

        if cycle > horizon:
            horizon *= 4
            arrivals = supply.arrival_series(horizon)
        arrived = arrivals[cycle]
        accepted = arrived
        stock += arrived
        if not supply.unbounded_buffer and stock > supply.buffer_capacity:
            lost = stock - supply.buffer_capacity
            overflow += lost
            accepted -= lost
            stock = supply.buffer_capacity

        started = 0
        consumed = 0
        budget = max_parallel_ops if max_parallel_ops is not None else total_nodes

        if clifford_weight == 0:
            while ready_other:
                _, node_id = heapq.heappop(ready_other)
                last_finish = max(last_finish, cycle - 1)
                retire(node_id)
        else:
            while ready_other and started < budget:
                _, node_id = heapq.heappop(ready_other)
                finishing.setdefault(cycle + clifford_weight, []).append(node_id)
                last_finish = max(last_finish, cycle + clifford_weight - 1)
                in_flight += 1
                started += 1

        while ready_t and started < budget and stock > 0:
            _, node_id = heapq.heappop(ready_t)
            stock -= 1
            consumed += 1
            finishing.setdefault(cycle + 1, []).append(node_id)
            last_finish = max(last_finish, cycle)
            in_flight += 1
            started += 1

        if started == 0 and in_flight == 0 and completed < total_nodes:
            idle_cycles += 1
        if ready_t and stock <= 0:
            supply_stall_cycles += 1

        if record_trace:
            demand_trace.append(consumed)
            arrival_trace.append(accepted)
            stock_trace.append(stock)
            running_trace.append(in_flight)

        if completed >= total_nodes:
            break

    makespan = max(last_finish, 0)
    if record_trace:
        demand_trace = demand_trace[:makespan]
        arrival_trace = arrival_trace[:makespan]
        stock_trace = stock_trace[:makespan]
        running_trace = running_trace[:makespan]

    return ExecutionTrace(
        makespan=makespan,
        t_executed=sum(demand_trace) if record_trace else dag.num_t_gates(),
        supply_stall_cycles=supply_stall_cycles,
        idle_cycles=idle_cycles,
        overflow=overflow,
        demand=demand_trace,
        arrivals=arrival_trace,
        stock=stock_trace,
        running=running_trace,
    )


def best_execution(
    dag: CircuitDAG,
    supply: SupplyModel,
    priorities: Sequence[str] = PRIORITIES,
    clifford_weight: int = 1,
    max_parallel_ops: int | None = None,
) -> tuple[int, str]:
    """Return the best makespan over several tie-break priorities and its name.

    Scheduling order is a second-order effect in this model, but taking the
    best of a few deterministic priorities makes the execution side of every
    baseline as strong as possible, so that a measured difference is
    attributable to the compilation choice and not to scheduling luck.
    """

    best: tuple[int, str] | None = None
    for name in priorities:
        trace = execute(
            dag,
            supply,
            priority=name,
            clifford_weight=clifford_weight,
            max_parallel_ops=max_parallel_ops,
            record_trace=False,
        )
        if best is None or trace.makespan < best[0]:
            best = (trace.makespan, name)
    assert best is not None
    return best


def execution_time(
    dag: CircuitDAG,
    supply: SupplyModel,
    clifford_weight: int = 1,
    priority: str = "t_critical",
    max_parallel_ops: int | None = None,
) -> int:
    """Return the constrained makespan in logical cycles."""

    return execute(
        dag,
        supply,
        priority=priority,
        clifford_weight=clifford_weight,
        max_parallel_ops=max_parallel_ops,
        record_trace=False,
    ).makespan


def execute_fixed_schedule(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
    supply: SupplyModel,
    clifford_weight: int = 1,
) -> ExecutionTrace:
    """Execute a statically layered schedule under ``supply``.

    This reproduces the execution semantics of the preceding T-depth study: the
    compiler commits to a fixed sequence of logical layers, and the next layer
    cannot start until the current one has consumed every magic state it asks
    for. A layer whose demand exceeds what the factories deliver in one cycle
    drains over several cycles, which is what that study counted as stall
    cycles. Committing to layers up front is strictly weaker than dynamic list
    scheduling; the flow is included so the existing pipeline can be compared
    on equal footing.
    """

    dag.assert_valid_schedule(schedule)
    stock = supply.initial_stock
    if not supply.unbounded_buffer:
        stock = min(stock, supply.buffer_capacity)

    cycle = 0
    stalls = 0
    overflow = 0
    demand_trace: list[int] = []
    arrival_trace: list[int] = []
    stock_trace: list[int] = []
    limit = 64 * (len(dag.nodes) + 1) + 100_000

    def advance() -> int:
        nonlocal cycle, stock, overflow
        cycle += 1
        arrived = supply.arrivals(cycle)
        accepted = arrived
        stock += arrived
        if not supply.unbounded_buffer and stock > supply.buffer_capacity:
            lost = stock - supply.buffer_capacity
            overflow += lost
            accepted -= lost
            stock = supply.buffer_capacity
        return accepted

    for step in sorted(schedule):
        layer = schedule[step]
        needed = sum(1 for node_id in layer if dag.nodes[node_id].is_t)
        duration = max(
            (node_duration(dag, node_id, clifford_weight) for node_id in layer),
            default=1,
        )
        served = 0
        while True:
            accepted = advance()
            if cycle > limit:
                raise RuntimeError(f"fixed-schedule execution of {dag.name!r} diverged")
            taken = min(needed - served, stock)
            stock -= taken
            served += taken
            demand_trace.append(taken)
            arrival_trace.append(accepted)
            stock_trace.append(stock)
            if served >= needed:
                break
            stalls += 1
        for _ in range(max(0, duration - 1)):
            accepted = advance()
            demand_trace.append(0)
            arrival_trace.append(accepted)
            stock_trace.append(stock)

    return ExecutionTrace(
        makespan=cycle,
        t_executed=sum(demand_trace),
        supply_stall_cycles=stalls,
        idle_cycles=stalls,
        overflow=overflow,
        demand=demand_trace,
        arrivals=arrival_trace,
        stock=stock_trace,
        running=[],
    )
