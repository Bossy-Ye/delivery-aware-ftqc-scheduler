"""An exploratory extension: more than one kind of magic state.

The main study isolates a single fungible resource, and finds that constrained
execution time is then well approximated by
``max(critical path, states / supply rate)``. That leaves nothing for a
compiler to do beyond evaluating a two-term formula.

Real fault-tolerant architectures produce several distinct resources. A
Toffoli can be realised from four T states through a measurement-based AND, or
consumed directly from a CCZ factory, and the two are produced by different
hardware at different rates. Choosing an implementation then means choosing
*which* factory to load, and the objective becomes balancing several
independent supplies rather than minimising one count. This module is the
smallest model in which that question can be asked; it exists to test whether
the negative result of the main study survives when the resource stops being
fungible.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from math import ceil

from ftqc_delivery.dag.graph import CircuitDAG

from .supply import SupplyModel
from .variants import FragmentBuilder, ProgramSpace, Site, Variant


#: Operation types that consume a magic state, and which resource each draws on.
RESOURCE_OF = {"T": "T", "Tdg": "T", "Tdag": "T", "T†": "T", "CCZ": "CCZ"}


def resource_of(op_type: str) -> str | None:
    """Return the resource an operation consumes, or ``None`` if it consumes none."""

    return RESOURCE_OF.get(op_type)


def resource_counts(dag: CircuitDAG) -> dict[str, int]:
    """Return how many states of each resource the circuit consumes."""

    counts: dict[str, int] = {}
    for node in dag.nodes.values():
        name = resource_of(node.op_type)
        if name is not None:
            counts[name] = counts.get(name, 0) + 1
    return counts


def weighted_depth(dag: CircuitDAG, clifford_weight: int = 1) -> int:
    """Return the critical-path length with every operation taking one cycle."""

    finish: dict[str, int] = {}
    for node_id in dag.topological_order():
        start = 0
        for predecessor in dag.predecessors(node_id):
            start = max(start, finish[predecessor])
        duration = 1 if resource_of(dag.op_type(node_id)) else clifford_weight
        finish[node_id] = start + duration
    return max(finish.values(), default=0)


@dataclass(frozen=True)
class MultiSupply:
    """A bank of factories per resource type."""

    banks: tuple[tuple[str, SupplyModel], ...]

    def bank(self, name: str) -> SupplyModel:
        """Return the factory bank producing ``name``."""

        for resource, supply in self.banks:
            if resource == name:
                return supply
        raise KeyError(f"no factory bank for resource {name!r}")

    @property
    def names(self) -> tuple[str, ...]:
        """Return the resource names in declaration order."""

        return tuple(resource for resource, _ in self.banks)

    def describe(self) -> str:
        """Return a compact identifier for tables."""

        return "+".join(
            f"{resource}@{supply.rate:g}" for resource, supply in self.banks
        )


def execute_multi(
    dag: CircuitDAG,
    supplies: MultiSupply,
    clifford_weight: int = 1,
    cycle_limit: int | None = None,
) -> int:
    """Return the constrained makespan under several independent factory banks.

    The scheduler is the same greedy list scheduler as the single-resource
    executor: everything ready starts, except that an operation waits until a
    state of *its own* resource is available.
    """

    order = dag.topological_order()
    rank = {node_id: index for index, node_id in enumerate(order)}
    successors = {node_id: sorted(dag.successors(node_id)) for node_id in order}
    kind = {node_id: resource_of(dag.op_type(node_id)) for node_id in order}
    remaining = {node_id: len(dag.predecessors(node_id)) for node_id in order}

    ready: dict[str | None, list[tuple[int, str]]] = {None: []}
    for name in supplies.names:
        ready[name] = []

    def push(node_id: str) -> None:
        heapq.heappush(ready[kind[node_id]], (rank[node_id], node_id))

    for node_id in order:
        if remaining[node_id] == 0:
            push(node_id)

    horizon = 1024
    series = {name: supplies.bank(name).arrival_series(horizon) for name in supplies.names}
    stock = {name: supplies.bank(name).initial_stock for name in supplies.names}
    finishing: dict[int, list[str]] = {}
    completed = 0
    total = len(order)
    cycle = 0
    last_finish = 0
    limit = cycle_limit if cycle_limit is not None else 64 * (total + 1) + 100_000

    while completed < total:
        cycle += 1
        if cycle > limit:
            raise RuntimeError(f"multi-resource execution of {dag.name!r} diverged")
        if cycle > horizon:
            horizon *= 4
            series = {
                name: supplies.bank(name).arrival_series(horizon)
                for name in supplies.names
            }

        for node_id in finishing.pop(cycle, ()):
            completed += 1
            for successor in successors[node_id]:
                remaining[successor] -= 1
                if remaining[successor] == 0:
                    push(successor)

        for name in supplies.names:
            supply = supplies.bank(name)
            stock[name] += series[name][cycle]
            if not supply.unbounded_buffer and stock[name] > supply.buffer_capacity:
                stock[name] = supply.buffer_capacity

        if clifford_weight == 0:
            while ready[None]:
                _, node_id = heapq.heappop(ready[None])
                completed += 1
                last_finish = max(last_finish, cycle - 1)
                for successor in successors[node_id]:
                    remaining[successor] -= 1
                    if remaining[successor] == 0:
                        push(successor)
        else:
            while ready[None]:
                _, node_id = heapq.heappop(ready[None])
                finishing.setdefault(cycle + clifford_weight, []).append(node_id)
                last_finish = max(last_finish, cycle + clifford_weight - 1)

        for name in supplies.names:
            while ready[name] and stock[name] > 0:
                _, node_id = heapq.heappop(ready[name])
                stock[name] -= 1
                finishing.setdefault(cycle + 1, []).append(node_id)
                last_finish = max(last_finish, cycle)

        if completed >= total:
            break

    return max(last_finish, 0)


def two_term_estimate(
    dag: CircuitDAG, supplies: MultiSupply, clifford_weight: int = 1
) -> float:
    """Return ``max(critical path, max over resources of count / rate)``.

    This is the single-resource rule of the main study, lifted to several
    resources in the obvious way. The point of the probe is that minimising it
    is no longer achievable by minimising any one static count: it requires
    *balancing* the loads placed on the different factories.
    """

    counts = resource_counts(dag)
    bound = float(weighted_depth(dag, clifford_weight))
    for name, count in counts.items():
        supply = supplies.bank(name)
        bound = max(bound, supply.production_latency + count / supply.rate)
    return bound


def _emit_layers(
    builder: FragmentBuilder, layers: tuple[tuple[str, int], ...], start: str
) -> str:
    frontier = [start]
    for op_type, width in layers:
        joint = builder.add("Clifford", frontier)
        frontier = builder.add_layer(op_type, width, [joint])
    return builder.add("Clifford", frontier)


#: Three ways to realise the same logical AND, drawing on different factories.
AND_IMPLEMENTATIONS = (
    ("t4", (("T", 2), ("T", 2)), "measurement-based AND, 4 T states"),
    ("ccz1", (("CCZ", 1),), "consumed directly from a CCZ factory, 1 CCZ state"),
    ("t7_d1", (("T", 7),), "T-depth-1 Toffoli, 7 T states in one layer"),
    ("ccz2_shallow", (("CCZ", 2),), "two CCZ states, one layer, extra fix-up"),
)


def make_and_site(site_id: str) -> Site:
    """Return one AND site offering the mixed-resource implementations."""

    variants = []
    for name, layers, note in AND_IMPLEMENTATIONS:
        builder = FragmentBuilder(prefix=f"{site_id}_{name}_")
        source = builder.add("Clifford")
        result = _emit_layers(builder, layers, source)
        builder.add("Clifford", [result])
        variants.append(
            Variant(name=name, family="and", fragment=builder.finish(notes=note), notes=note)
        )
    return Site(site_id=site_id, family="and", variants=tuple(variants))


def and_bank(lanes: int = 4, stages: int = 2) -> ProgramSpace:
    """Return stages of independent AND sites, each free to pick its factory."""

    sites: list[Site] = []
    edges: list[tuple[str, str]] = []
    previous: str | None = None
    for stage in range(stages):
        barrier_builder = FragmentBuilder(prefix=f"bar{stage:02d}_")
        barrier_builder.add("Clifford")
        barrier = Site(
            site_id=f"bar{stage:02d}",
            family="barrier",
            variants=(
                Variant(
                    name="barrier", family="barrier", fragment=barrier_builder.finish()
                ),
            ),
        )
        sites.append(barrier)
        if previous is not None:
            edges.append((previous, barrier.site_id))
        stage_sites = [make_and_site(f"s{stage:02d}_l{lane:02d}") for lane in range(lanes)]
        for site in stage_sites:
            sites.append(site)
            edges.append((barrier.site_id, site.site_id))
        closing_builder = FragmentBuilder(prefix=f"bar{stage:02d}end_")
        closing_builder.add("Clifford")
        closing = Site(
            site_id=f"bar{stage:02d}end",
            family="barrier",
            variants=(
                Variant(
                    name="barrier", family="barrier", fragment=closing_builder.finish()
                ),
            ),
        )
        sites.append(closing)
        for site in stage_sites:
            edges.append((site.site_id, closing.site_id))
        previous = closing.site_id

    return ProgramSpace(
        name=f"and_bank_l{lanes}_s{stages}",
        sites=tuple(sites),
        edges=tuple(edges),
        meta=(("kernel", "and_bank"), ("concurrency", str(lanes))),
    )


def balanced_selection(
    program: ProgramSpace, supplies: MultiSupply, clifford_weight: int = 1
) -> dict[str, str]:
    """Return the assignment minimising the multi-resource two-term estimate.

    Coordinate descent on the analytic estimate, seeded from every uniform
    assignment. Unlike the single-resource case there is no static metric whose
    per-site minimisation gives this answer, because the objective is a maximum
    over resources rather than a sum.
    """

    decision_sites = [site for site in program.sites if len(site.variants) > 1]
    seeds: list[dict[str, str]] = []
    names: set[str] = set()
    for site in decision_sites:
        names.update(site.variant_names)
    for choice in sorted(names):
        seeds.append(
            {
                site.site_id: (
                    choice if choice in site.variant_names else site.variants[0].name
                )
                for site in program.sites
            }
        )

    best: dict[str, str] | None = None
    best_cost = float("inf")
    for seed in seeds:
        current = dict(seed)
        current_cost = two_term_estimate(
            program.instantiate(current), supplies, clifford_weight
        )
        for _ in range(4):
            improved = False
            for site in decision_sites:
                incumbent = current[site.site_id]
                local_best, local_cost = incumbent, current_cost
                for variant_name in site.variant_names:
                    if variant_name == incumbent:
                        continue
                    current[site.site_id] = variant_name
                    candidate = two_term_estimate(
                        program.instantiate(current), supplies, clifford_weight
                    )
                    if candidate < local_cost - 1e-9:
                        local_cost, local_best = candidate, variant_name
                current[site.site_id] = local_best
                if local_best != incumbent:
                    current_cost = local_cost
                    improved = True
            if not improved:
                break
        if current_cost < best_cost - 1e-9:
            best_cost, best = current_cost, dict(current)
    assert best is not None
    return best


def factories(t_rate: float, ccz_rate: float, latency: int = 10, buffer: int = 32) -> MultiSupply:
    """Return a two-resource factory bank at the requested rates."""

    def bank(rate: float) -> SupplyModel:
        return SupplyModel(
            num_factories=max(1, ceil(rate * latency)),
            production_latency=latency,
            factory_period=latency,
            buffer_capacity=buffer,
        )

    return MultiSupply(banks=(("T", bank(t_rate)), ("CCZ", bank(ccz_rate))))
