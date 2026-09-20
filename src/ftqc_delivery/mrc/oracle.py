"""The stateful oracle, and a provable bound on what any assignment can reach.

The oracle answers one question: over all ways of choosing an implementation
at every decision site, what is the shortest execution the machine admits?
Every candidate is scored by running the whole program on the machine with
:func:`~ftqc_delivery.mrc.execution.execute`, which carries stock, factory
phase, buffer occupancy and in-flight conversions from the first cycle to the
last and never resets them at a stage boundary. The oracle is therefore
stateful by construction: a choice made early is paid for, or rewarded, by
every choice that follows.

Formally the search is over ``a = (a_1, ..., a_n)``, one action per decision
site, and the objective is the makespan of the resulting execution, in which
the resource state evolves as ``S_{t+1} = g(S_t, a_t)`` with ``g`` the
simulator's own transition. No abstraction of the state is imposed.

Three answer qualities are distinguished and never conflated:

``proven``
    Exhaustive over the whole space, or over the exact symmetry reduction of
    it. This is the optimum.
``bounded``
    The best assignment an iterated search found, reported together with a
    lower bound that no assignment can beat. The optimum lies between them.
``heuristic``
    A single search with no bound. Only produced if a bound cannot be built.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ftqc_delivery.rac.variants import Assignment, ProgramSpace

from .execution import critical_path, execute, resource_counts
from .kernels import decision_sites
from .policies import (
    Outcome,
    _finish,
    _makespan,
    feasible_names,
    run_policy,
    symmetric_oracle,
    symmetric_space,
    t_equivalents,
    uniform_assignments,
)
from .resources import Machine


@dataclass
class OracleResult:
    """What the oracle found, and how sure it is."""

    outcome: Outcome
    status: str
    lower_bound: float
    simulations: int
    seconds: float

    @property
    def makespan(self) -> int:
        return self.outcome.makespan

    @property
    def assignment(self) -> Assignment:
        return self.outcome.assignment

    @property
    def proven(self) -> bool:
        return self.status == "proven"

    def gap(self) -> float:
        """Return how far the reported answer may still be from the optimum."""

        if self.status == "proven" or self.lower_bound <= 0:
            return 0.0
        return (self.makespan - self.lower_bound) / self.makespan


# ---------------------------------------------------------------------------
# Lower bound
# ---------------------------------------------------------------------------


def _raw_cost_per_unit(machine: Machine) -> dict[str, float]:
    """Return how many raw states each produced state costs.

    In the coupled models T and CCZ are both distilled from one raw stream, so
    a bound that looks at each product separately misses the competition
    between them. Following each conversion back to its bank gives the raw
    cost of one unit of the product.
    """

    banked = {bank.resource for bank in machine.banks}
    cost: dict[str, float] = {resource: 1.0 for resource in banked}
    for conversion in machine.conversions:
        if conversion.source in banked and conversion.outputs > 0:
            per_unit = conversion.inputs / conversion.outputs
            current = cost.get(conversion.target)
            cost[conversion.target] = per_unit if current is None else min(current, per_unit)
    return cost


def _feasible_base(program: ProgramSpace, machine: Machine) -> Assignment:
    """Return an assignment this machine can actually run."""

    base = program.default_assignment()
    for site in program.sites:
        names = feasible_names(site, machine)
        if names:
            base[site.site_id] = names[0]
    return base


def _per_site_minima(program: ProgramSpace, machine: Machine) -> tuple[dict[str, int], float, dict[str, float]]:
    """Return the least demand any assignment can place on the machine.

    Three quantities, each a sum over sites of a minimum taken over that
    site's own variants, so each is attainable-or-lower for every assignment:

    * per resource, the fewest states of that resource;
    * the fewest T-equivalents, counting one CCZ as two T;
    * per bank, the fewest raw states consumed through the conversions.

    The per-resource minima are taken over the union of resources used by any
    variant, so a variant that avoids a resource entirely contributes a zero
    rather than being skipped.
    """

    totals: dict[str, int] = {}
    teq_total = 0.0
    raw_totals: dict[str, float] = {}
    raw_per_unit = _raw_cost_per_unit(machine)

    for site in program.sites:
        names = feasible_names(site, machine) or list(site.variant_names)
        per_variant = [
            resource_counts(site.variant(name).fragment.to_dag(name)) for name in names
        ]
        if not per_variant:
            continue
        resources = set().union(*[set(counts) for counts in per_variant])
        for resource in resources:
            totals[resource] = totals.get(resource, 0) + min(
                counts.get(resource, 0) for counts in per_variant
            )
        teq_total += min(t_equivalents(counts) for counts in per_variant)
        for bank_resource in {bank.resource for bank in machine.banks}:
            costs = []
            for counts in per_variant:
                cost = 0.0
                for resource, count in counts.items():
                    producers = [
                        c for c in machine.conversions
                        if c.target == resource and c.source == bank_resource
                    ]
                    if producers:
                        cost += count * raw_per_unit.get(resource, 0.0)
                    elif resource == bank_resource:
                        cost += count
                costs.append(cost)
            raw_totals[bank_resource] = raw_totals.get(bank_resource, 0.0) + min(costs)
    return totals, teq_total, raw_totals


def _pooled_arrival_cycle(machine: Machine, teq_needed: float) -> float:
    """Return when pooled production could first cover ``teq_needed``.

    Pooling the banks into one interchangeable supply can only help, so the
    cycle at which the pooled stream has delivered the demand is never later
    than any real execution that must respect which bank produced what.
    """

    if teq_needed <= 0:
        return 0.0
    horizon = 64
    while horizon <= 1 << 22:
        delivered = 0.0
        series = {
            bank.resource: bank.arrival_series(horizon, seed=machine.seed)
            for bank in machine.banks
        }
        for cycle in range(horizon):
            for resource, arrivals in series.items():
                if cycle < len(arrivals):
                    delivered += t_equivalents({resource: arrivals[cycle]})
            if delivered >= teq_needed:
                return float(cycle)
        horizon *= 4
    return 0.0


def assignment_lower_bound(program: ProgramSpace, machine: Machine) -> float:
    """Return a value no assignment of this program can execute faster than.

    Each term below is a valid bound for every assignment, so their maximum is
    too:

    * the critical path with every site at its shortest variant, since
      shortening one site cannot lengthen any path;
    * for each resource, the delivery time of the fewest states any assignment
      could need, delivery time being non-decreasing in the count;
    * the delivery time of the fewest T-equivalents, against the two banks
      pooled into one interchangeable supply, which can only be optimistic;
    * for a machine that distils its products from a raw bank, the delivery
      time of the fewest raw states, which is what couples the products.

    The bound ignores every scheduling constraint beyond these, so it is
    loose; its purpose is to bound how much room an unproven case can still
    hide, not to predict the optimum.
    """

    minimal: Assignment = _feasible_base(program, machine)
    for site in program.sites:
        names = feasible_names(site, machine) or list(site.variant_names)
        minimal[site.site_id] = min(
            names, key=lambda name: critical_path(site.variant(name).fragment.to_dag(name))
        )
    bound = float(critical_path(program.instantiate(minimal)))

    demand, teq_total, raw_totals = _per_site_minima(program, machine)
    for resource, count in demand.items():
        if count <= 0:
            continue
        bank = machine.bank(resource)
        if bank is not None:
            bound = max(bound, float(bank.earliest_cycle_for(count, seed=machine.seed)))
            continue
        rate = machine.rate(resource)
        producers = [c for c in machine.conversions if c.target == resource]
        if not producers or rate <= 0:
            continue
        lead = min(c.latency for c in producers)
        source_bank = machine.bank(producers[0].source)
        lead += source_bank.first_output if source_bank else 0
        bound = max(bound, lead + count / rate)

    bound = max(bound, _pooled_arrival_cycle(machine, teq_total))

    for resource, raw_needed in raw_totals.items():
        bank = machine.bank(resource)
        if bank is not None and raw_needed > 0:
            bound = max(
                bound, float(bank.earliest_cycle_for(int(raw_needed), seed=machine.seed))
            )
    return bound


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _neighbourhood_descent(
    program: ProgramSpace,
    machine: Machine,
    start: Assignment,
    allowed: dict[str, list[str]],
    budget_end: float,
    best: tuple[int, Assignment],
) -> tuple[tuple[int, Assignment], int]:
    """Improve ``start`` by single-site moves until nothing helps."""

    current = dict(start)
    current_cost = _makespan(program, current, machine)
    simulations = 1
    if current_cost < best[0]:
        best = (current_cost, dict(current))
    improved = True
    while improved and time.perf_counter() < budget_end:
        improved = False
        for site_id, names in allowed.items():
            if time.perf_counter() >= budget_end:
                break
            original = current[site_id]
            for name in names:
                if name == original:
                    continue
                current[site_id] = name
                cost = _makespan(program, current, machine)
                simulations += 1
                if cost < current_cost:
                    current_cost, original, improved = cost, name, True
                    if cost < best[0]:
                        best = (cost, dict(current))
                else:
                    current[site_id] = original
            current[site_id] = original
    return best, simulations


def bounded_search(
    program: ProgramSpace,
    machine: Machine,
    seeds: list[Assignment],
    time_budget: float = 30.0,
    seed: int = 20260920,
) -> tuple[Assignment, int, int]:
    """Return the best assignment an iterated local search can find.

    Descent from every seed, then repeated random perturbation of the best
    assignment found so far. The random stream is seeded, so the same call
    returns the same answer every time.
    """

    rng = random.Random(seed)
    allowed = {
        site.site_id: (feasible_names(site, machine) or list(site.variant_names))
        for site in decision_sites(program)
    }
    allowed = {site_id: names for site_id, names in allowed.items() if len(names) > 1}
    if not allowed:
        base = program.default_assignment()
        return base, _makespan(program, base, machine), 1

    budget_end = time.perf_counter() + time_budget
    best: tuple[int, Assignment] = (1 << 62, program.default_assignment())
    simulations = 0
    for candidate in seeds:
        if time.perf_counter() >= budget_end:
            break
        best, used = _neighbourhood_descent(program, machine, candidate, allowed, budget_end, best)
        simulations += used

    site_ids = list(allowed)
    while time.perf_counter() < budget_end:
        perturbed = dict(best[1])
        for site_id in rng.sample(site_ids, k=min(len(site_ids), rng.randint(1, 3))):
            perturbed[site_id] = rng.choice(allowed[site_id])
        best, used = _neighbourhood_descent(program, machine, perturbed, allowed, budget_end, best)
        simulations += used
    return best[1], best[0], simulations


POLICY_SEEDS = (
    "uniform_min_teq",
    "min_weighted_count",
    "uniform_oracle",
    "two_term_descent",
    "local_sim_greedy",
    "share_aware_greedy",
    "proportional_split",
    "sim_descent",
)


def stateful_oracle(
    program: ProgramSpace,
    machine: Machine,
    exact_limit: int = 200_000,
    exact_time_budget: float = 45.0,
    search_budget: float = 30.0,
    extra_seeds: tuple[Assignment, ...] = (),
    seed: int = 20260920,
) -> OracleResult:
    """Return the best assignment, exactly where that is affordable.

    Exhaustive enumeration is preferred and is run over the exact symmetry
    reduction, which is a relabelling argument rather than a heuristic, so its
    answer is the true optimum. Where the reduced space or the projected
    simulation time is too large, an iterated search runs instead and the
    answer is reported as ``bounded`` alongside a value no assignment can beat.
    """

    start = time.perf_counter()
    reduced = symmetric_space(program, machine)
    probe_start = time.perf_counter()
    _makespan(program, _feasible_base(program, machine), machine)
    per_simulation = max(time.perf_counter() - probe_start, 1e-6)

    lower = assignment_lower_bound(program, machine)

    if reduced <= exact_limit and reduced * per_simulation <= exact_time_budget:
        exact = symmetric_oracle(program, machine, limit=exact_limit)
        if exact is not None:
            return OracleResult(
                outcome=exact,
                status="proven",
                lower_bound=lower,
                simulations=exact.simulations,
                seconds=time.perf_counter() - start,
            )

    seeds = [outcome.assignment for outcome in (run_policy(name, program, machine) for name in POLICY_SEEDS)]
    seeds.extend(uniform_assignments(program, machine))
    seeds.extend(extra_seeds)
    assignment, cost, simulations = bounded_search(
        program, machine, seeds, time_budget=search_budget, seed=seed
    )
    outcome = _finish("stateful_oracle", program, assignment, machine, start, simulations=simulations)
    return OracleResult(
        outcome=outcome,
        status="bounded",
        lower_bound=lower,
        simulations=simulations,
        seconds=time.perf_counter() - start,
    )
