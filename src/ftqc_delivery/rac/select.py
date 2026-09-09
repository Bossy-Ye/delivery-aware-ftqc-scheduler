"""Compilation policies that choose an implementation for every decision site.

Each policy maps a :class:`ProgramSpace` and a :class:`SupplyModel` to an
assignment. They differ only in what information they are allowed to use:

* the static-metric policies see the circuit but not the machine;
* the local resource policy sees the machine but only one site at a time, and
  is allowed to *simulate* that site, which is strictly more information than
  the resource-aware policy gets;
* the resource-aware policy sees the whole program and the machine, but only
  through the analytic cost model, never through simulation;
* the oracle simulates every assignment and is the optimality reference.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from itertools import product
from typing import Callable, Sequence

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.schedulers.smooth import schedule_smooth

from .analysis import logical_depth, t_count, t_depth
from .cost import SupplyProfile, default_horizon, estimate
from .execution import execute, execute_fixed_schedule
from .programs import decision_sites
from .supply import SupplyModel
from .variants import Assignment, ProgramSpace, Site


POLICIES = (
    "min_t_count",
    "min_t_depth",
    "legacy_smooth",
    "local_resource_greedy",
    "share_aware_greedy",
    "resource_aware",
)


@dataclass
class SelectionResult:
    """The outcome of running one compilation policy."""

    policy: str
    assignment: Assignment
    makespan: int
    cost_model_evaluations: int = 0
    simulations: int = 0
    seconds: float = 0.0
    detail: dict[str, float] = field(default_factory=dict)


def _static_site_key(site: Site, objective: str, clifford_weight: int) -> Callable[[str], tuple]:
    def key(variant_name: str) -> tuple:
        dag = site.variant(variant_name).fragment.to_dag(variant_name)
        if objective == "t_depth":
            return (t_depth(dag), t_count(dag), logical_depth(dag, clifford_weight), variant_name)
        if objective == "t_count":
            return (t_count(dag), t_depth(dag), logical_depth(dag, clifford_weight), variant_name)
        raise ValueError(f"unknown static objective {objective!r}")

    return key


def select_static(program: ProgramSpace, objective: str, clifford_weight: int = 1) -> Assignment:
    """Return the assignment a conventional static-metric compiler produces.

    Program T-depth is the largest sum of site T-depths along any path and
    program T-count is the sum over all sites, so minimising the metric at each
    site independently minimises it globally. This is exactly what a
    T-depth-oriented or T-count-oriented pass does.
    """

    assignment: Assignment = {}
    for site in program.sites:
        key = _static_site_key(site, objective, clifford_weight)
        assignment[site.site_id] = min(site.variant_names, key=key)
    return assignment


def select_local_resource_greedy(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
) -> tuple[Assignment, int]:
    """Return the assignment minimising each site's own constrained runtime.

    Every site is simulated in isolation against the full factory bank and the
    fastest implementation is kept. This is the strongest simple resource-aware
    policy: it knows the machine and is allowed to run it, but it cannot see
    that concurrent sites share the same factories.
    """

    assignment: Assignment = {}
    simulations = 0
    for site in program.sites:
        best_name = None
        best_cost = None
        for variant_name in site.variant_names:
            dag = site.variant(variant_name).fragment.to_dag(variant_name)
            cost = execute(
                dag,
                supply,
                clifford_weight=clifford_weight,
                record_trace=False,
            ).makespan
            simulations += 1
            key = (cost, t_count(dag), variant_name)
            if best_cost is None or key < best_cost:
                best_cost = key
                best_name = variant_name
        assert best_name is not None
        assignment[site.site_id] = best_name
    return assignment, simulations


def _analytic_local_seed(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int,
) -> Assignment:
    """Return a per-site seed chosen with the analytic model only."""

    assignment: Assignment = {}
    for site in program.sites:
        best_name = None
        best_cost = None
        for variant_name in site.variant_names:
            dag = site.variant(variant_name).fragment.to_dag(variant_name)
            cost = estimate(dag, supply, model="sccp", clifford_weight=clifford_weight)
            key = (cost, t_count(dag), variant_name)
            if best_cost is None or key < best_cost:
                best_cost = key
                best_name = variant_name
        assert best_name is not None
        assignment[site.site_id] = best_name
    return assignment


def select_resource_aware(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
    model: str = "sccp",
    max_rounds: int = 4,
    seeds: Sequence[Assignment] | None = None,
) -> tuple[Assignment, int]:
    """Return the assignment chosen by supply-constrained coordinate descent.

    The search never simulates. It scores a candidate assignment with the
    analytic cost model and improves one site at a time until no single-site
    change helps, restarting from several cheap seeds. Because the cost model
    is aware of when states arrive rather than only how many are needed, the
    search can trade a deeper implementation at one site for a smoother demand
    profile across concurrent sites.
    """

    if seeds is None:
        seeds = [
            select_static(program, "t_depth", clifford_weight),
            select_static(program, "t_count", clifford_weight),
            _analytic_local_seed(program, supply, clifford_weight),
        ]

    sites = decision_sites(program)
    evaluations = 0
    profile: SupplyProfile | None = None
    best_assignment: Assignment | None = None
    best_cost = float("inf")

    def score(assignment: Assignment) -> float:
        nonlocal evaluations, profile
        dag = program.instantiate(assignment)
        if profile is None:
            profile = SupplyProfile.build(
                supply, default_horizon(dag, supply, clifford_weight) * 2
            )
        evaluations += 1
        return estimate(
            dag, supply, model=model, clifford_weight=clifford_weight, profile=profile
        )

    for seed in seeds:
        current = dict(seed)
        current_cost = score(current)
        for _ in range(max_rounds):
            improved = False
            for site in sites:
                incumbent = current[site.site_id]
                local_best = incumbent
                local_cost = current_cost
                for variant_name in site.variant_names:
                    if variant_name == incumbent:
                        continue
                    current[site.site_id] = variant_name
                    candidate_cost = score(current)
                    if candidate_cost < local_cost - 1e-9:
                        local_cost = candidate_cost
                        local_best = variant_name
                current[site.site_id] = local_best
                if local_best != incumbent:
                    current_cost = local_cost
                    improved = True
            if not improved:
                break
        if current_cost < best_cost - 1e-9:
            best_cost = current_cost
            best_assignment = dict(current)

    assert best_assignment is not None
    return best_assignment, evaluations


def select_oracle(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
    limit: int = 4000,
) -> tuple[Assignment, int, int, bool]:
    """Return the best assignment found by exhaustive simulation.

    Returns the assignment, its makespan, the number of simulations, and
    whether the enumeration was complete.
    """

    best_assignment: Assignment | None = None
    best_makespan = None
    simulations = 0
    complete = True

    for assignment in program.iter_assignments():
        if simulations >= limit:
            complete = False
            break
        dag = program.instantiate(assignment)
        makespan = execute(
            dag, supply, clifford_weight=clifford_weight, record_trace=False
        ).makespan
        simulations += 1
        if best_makespan is None or makespan < best_makespan:
            best_makespan = makespan
            best_assignment = dict(assignment)

    assert best_assignment is not None and best_makespan is not None
    return best_assignment, best_makespan, simulations, complete


def legacy_schedule_makespan(
    dag: CircuitDAG,
    supply: SupplyModel,
    clifford_weight: int = 1,
) -> int:
    """Return the makespan of the previous study's static delivery-aware schedule."""

    capacity = max(1, int(round(supply.rate)))
    schedule = schedule_smooth(dag, capacity=capacity)
    return execute_fixed_schedule(
        dag, schedule, supply, clifford_weight=clifford_weight
    ).makespan


def run_policy(
    policy: str,
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
) -> SelectionResult:
    """Run one compilation policy end to end and measure the result."""

    start = time.perf_counter()
    evaluations = 0
    simulations = 0

    if policy == "min_t_depth":
        assignment = select_static(program, "t_depth", clifford_weight)
    elif policy == "min_t_count":
        assignment = select_static(program, "t_count", clifford_weight)
    elif policy == "legacy_smooth":
        assignment = select_static(program, "t_depth", clifford_weight)
    elif policy == "local_resource_greedy":
        assignment, simulations = select_local_resource_greedy(
            program, supply, clifford_weight
        )
    elif policy == "share_aware_greedy":
        assignment, simulations = select_share_aware_greedy(
            program, supply, clifford_weight
        )
    elif policy == "resource_aware":
        assignment, evaluations = select_resource_aware(
            program, supply, clifford_weight=clifford_weight
        )
    else:
        raise ValueError(f"unknown policy {policy!r}")

    dag = program.instantiate(assignment)
    if policy == "legacy_smooth":
        makespan = legacy_schedule_makespan(dag, supply, clifford_weight)
    else:
        makespan = execute(
            dag, supply, clifford_weight=clifford_weight, record_trace=False
        ).makespan

    return SelectionResult(
        policy=policy,
        assignment=assignment,
        makespan=makespan,
        cost_model_evaluations=evaluations,
        simulations=simulations,
        seconds=time.perf_counter() - start,
    )


def enumerate_variant_makespans(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
    limit: int = 4000,
) -> list[tuple[Assignment, int]]:
    """Return the makespan of every assignment, up to ``limit`` candidates."""

    rows: list[tuple[Assignment, int]] = []
    for index, assignment in enumerate(program.iter_assignments()):
        if index >= limit:
            break
        dag = program.instantiate(assignment)
        rows.append(
            (
                dict(assignment),
                execute(
                    dag, supply, clifford_weight=clifford_weight, record_trace=False
                ).makespan,
            )
        )
    return rows


def uniform_assignments(program: ProgramSpace) -> list[Assignment]:
    """Return the assignments a library-style compiler could realistically emit.

    Each family of sites is compiled uniformly -- every adder as a ripple-carry
    adder, or every adder as a blocked adder, and so on -- and the returned list
    is the cross product over families. These are the candidate implementations
    of the whole program that a conventional flow chooses between, so they are
    the right universe for asking whether a static metric picks the fastest one.
    """

    families = sorted({site.family for site in program.sites})
    per_family: dict[str, list[str]] = {}
    for family in families:
        names: list[str] = []
        for site in program.sites:
            if site.family == family:
                for name in site.variant_names:
                    if name not in names:
                        names.append(name)
        per_family[family] = names

    choices = [[(family, name) for name in per_family[family]] for family in families]
    assignments: list[Assignment] = []
    seen: set[tuple] = set()
    for combination in product(*choices):
        picked = dict(combination)
        assignment: Assignment = {}
        feasible = True
        for site in program.sites:
            wanted = picked.get(site.family)
            if wanted in site.variant_names:
                assignment[site.site_id] = wanted
            else:
                feasible = False
                break
        if not feasible:
            continue
        token = tuple(sorted(assignment.items()))
        if token not in seen:
            seen.add(token)
            assignments.append(assignment)
    return assignments


def select_simulated_descent(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
    seeds: Sequence[Assignment] | None = None,
    max_rounds: int = 4,
) -> tuple[Assignment, int, int]:
    """Return the best assignment found by coordinate descent on true makespan.

    This is a search reference, not a compilation policy: it is allowed to run
    the machine on every candidate it considers, which no compiler can do.
    """

    if seeds is None:
        seeds = [
            select_static(program, "t_depth", clifford_weight),
            select_static(program, "t_count", clifford_weight),
        ]
        seeds.extend(uniform_assignments(program))

    sites = decision_sites(program)
    simulations = 0

    def cost(assignment: Assignment) -> int:
        nonlocal simulations
        simulations += 1
        return execute(
            program.instantiate(assignment),
            supply,
            clifford_weight=clifford_weight,
            record_trace=False,
        ).makespan

    best_assignment: Assignment | None = None
    best_cost: int | None = None

    for seed in seeds:
        current = dict(seed)
        current_cost = cost(current)
        for _ in range(max_rounds):
            improved = False
            for site in sites:
                incumbent = current[site.site_id]
                local_best, local_cost = incumbent, current_cost
                for variant_name in site.variant_names:
                    if variant_name == incumbent:
                        continue
                    current[site.site_id] = variant_name
                    candidate = cost(current)
                    if candidate < local_cost:
                        local_cost, local_best = candidate, variant_name
                current[site.site_id] = local_best
                if local_best != incumbent:
                    current_cost = local_cost
                    improved = True
            if not improved:
                break
        if best_cost is None or current_cost < best_cost:
            best_cost, best_assignment = current_cost, dict(current)

    assert best_assignment is not None and best_cost is not None
    return best_assignment, best_cost, simulations


def _spread(items: list[Assignment], limit: int) -> list[Assignment]:
    """Return at most ``limit`` items spread evenly across the input list."""

    if len(items) <= limit:
        return list(items)
    step = len(items) / limit
    return [items[min(len(items) - 1, int(index * step))] for index in range(limit)]


@dataclass
class Reference:
    """The best known assignment, and whether it is provably optimal."""

    assignment: Assignment
    makespan: int
    exhaustive: bool
    simulations: int
    candidates: int


def reference_best(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
    exhaustive_limit: int = 6000,
    extra: Sequence[Assignment] = (),
    seed_limit: int = 8,
) -> Reference:
    """Return the optimality reference for one program and supply regime.

    When the assignment space is small enough it is enumerated exhaustively and
    the answer is the true optimum. Otherwise the reference is the best of a
    broad search: every policy's answer, every family-uniform assignment, and
    coordinate descent on the simulator seeded from each of those. Rows
    produced that way are marked non-exhaustive and are excluded from any claim
    that requires a proven optimum.
    """

    space = 1
    for site in decision_sites(program):
        space *= len(site.variants)

    if space <= exhaustive_limit:
        assignment, makespan, simulations, complete = select_oracle(
            program, supply, clifford_weight, limit=exhaustive_limit + 1
        )
        if complete:
            return Reference(
                assignment=assignment,
                makespan=makespan,
                exhaustive=True,
                simulations=simulations,
                candidates=space,
            )

    seeds = [
        select_static(program, "t_depth", clifford_weight),
        select_static(program, "t_count", clifford_weight),
    ]
    seeds.extend(dict(item) for item in extra)
    seeds.extend(_spread(uniform_assignments(program), seed_limit))
    deduped: list[Assignment] = []
    seen: set[tuple] = set()
    for candidate in seeds:
        token = tuple(sorted(candidate.items()))
        if token not in seen:
            seen.add(token)
            deduped.append(candidate)
    assignment, makespan, simulations = select_simulated_descent(
        program, supply, clifford_weight, seeds=deduped[: seed_limit + len(extra) + 2]
    )
    return Reference(
        assignment=assignment,
        makespan=makespan,
        exhaustive=False,
        simulations=simulations,
        candidates=space,
    )


def best_uniform(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
) -> tuple[Assignment, int]:
    """Return the fastest family-uniform implementation, found by simulation.

    This is the strongest baseline a conventional flow can reach without a new
    abstraction: try every library implementation of the program, run each one,
    and keep the winner. Beating it requires giving concurrent sites *different*
    implementations, which no static metric and no per-library choice can
    express.
    """

    best_assignment: Assignment | None = None
    best_cost: int | None = None
    for assignment in uniform_assignments(program):
        cost = execute(
            program.instantiate(assignment),
            supply,
            clifford_weight=clifford_weight,
            record_trace=False,
        ).makespan
        if best_cost is None or cost < best_cost:
            best_cost, best_assignment = cost, dict(assignment)
    assert best_assignment is not None and best_cost is not None
    return best_assignment, best_cost


def concurrent_site_counts(program: ProgramSpace) -> dict[str, int]:
    """Return how many sites can be live at the same time as each site.

    Two sites are concurrent when neither reaches the other in the site-level
    dependency graph. The count includes the site itself, so a strictly serial
    program gives 1 everywhere.
    """

    site_ids = [site.site_id for site in program.sites]
    index = {site_id: position for position, site_id in enumerate(site_ids)}
    successors: dict[str, set[str]] = {site_id: set() for site_id in site_ids}
    for predecessor, successor in program.edges:
        successors[predecessor].add(successor)

    indegree = {site_id: 0 for site_id in site_ids}
    for predecessor, successor in program.edges:
        indegree[successor] += 1
    order: list[str] = [site_id for site_id in site_ids if indegree[site_id] == 0]
    queue = list(order)
    while queue:
        current = queue.pop()
        for successor in successors[current]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                order.append(successor)
                queue.append(successor)
    if len(order) < len(site_ids):
        order = site_ids

    reach: dict[str, set[int]] = {site_id: set() for site_id in site_ids}
    for site_id in reversed(order):
        collected: set[int] = set()
        for successor in successors[site_id]:
            collected.add(index[successor])
            collected |= reach[successor]
        reach[site_id] = collected

    counts: dict[str, int] = {}
    for site_id in site_ids:
        ahead = reach[site_id]
        behind = {
            index[other]
            for other in site_ids
            if index[site_id] in reach[other]
        }
        ordered = ahead | behind
        counts[site_id] = len(site_ids) - len(ordered) - 1 + 1
    return counts


def select_share_aware_greedy(
    program: ProgramSpace,
    supply: SupplyModel,
    clifford_weight: int = 1,
) -> tuple[Assignment, int]:
    """Return a per-site choice made against that site's fair share of supply.

    Each site is simulated in isolation against a factory bank scaled down by
    the number of sites that run concurrently with it. This is the strongest
    *separable* resource-aware policy: it knows the machine, knows how much
    contention it faces, and may simulate. What it still cannot do is give two
    concurrent sites different implementations on purpose.
    """

    counts = concurrent_site_counts(program)
    assignment: Assignment = {}
    simulations = 0
    for site in program.sites:
        share = max(1, counts.get(site.site_id, 1))
        scaled = SupplyModel(
            num_factories=max(1, round(supply.num_factories / share)),
            production_latency=supply.production_latency,
            factory_period=supply.period,
            buffer_capacity=(
                supply.buffer_capacity
                if supply.unbounded_buffer
                else max(1, supply.buffer_capacity // share)
            ),
            stagger=supply.stagger,
            initial_stock=supply.initial_stock // share,
        )
        best_name = None
        best_key = None
        for variant_name in site.variant_names:
            dag = site.variant(variant_name).fragment.to_dag(variant_name)
            cost = execute(
                dag, scaled, clifford_weight=clifford_weight, record_trace=False
            ).makespan
            simulations += 1
            key = (cost, t_count(dag), variant_name)
            if best_key is None or key < best_key:
                best_key, best_name = key, variant_name
        assert best_name is not None
        assignment[site.site_id] = best_name
    return assignment, simulations
