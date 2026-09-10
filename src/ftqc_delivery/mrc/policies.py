"""Compilation policies for choosing implementations across two factory banks.

The policies differ in what they may look at:

``uniform_min_teq``
    Static. Compile every site the same way, picking the uniform choice with
    the fewest T-equivalents (one CCZ counted as two T through the catalyzed
    transformation). This is the natural rule if the resources are treated as
    fungible.
``min_weighted_count``
    Static, but rate-aware: minimise the total production time the demand
    implies, ``sum over resources of count / rate``, choosing per site.
``uniform_oracle``
    Simulates every uniform implementation of the whole program and keeps the
    winner. No static metric can beat it among uniform choices.
``two_term_descent``
    Global search, analytic only: coordinate descent on
    ``max(critical path, max over resources of count / rate)``.
``local_sim_greedy``
    Per site, simulate each implementation against the whole machine and keep
    the fastest.
``share_aware_greedy``
    The same, but each site sees only its fair share of the machine, scaled by
    how many sites run concurrently with it.
``sim_descent``
    Global coordinate descent on the simulator. This is the implementable
    heterogeneous selector under test.
``global_oracle``
    Exhaustive over every assignment where that is tractable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from itertools import product

from ftqc_delivery.rac.variants import Assignment, ProgramSpace, Site

from .execution import critical_path, execute, resource_counts
from .kernels import assignment_space, decision_sites
from .resources import CCZ, T, FactoryBank, Machine

#: One CCZ state is worth two T states through the catalyzed transformation.
T_EQUIVALENT = {T: 1.0, CCZ: 2.0}

POLICIES = (
    "uniform_min_teq",
    "min_weighted_count",
    "uniform_oracle",
    "two_term_descent",
    "local_sim_greedy",
    "share_aware_greedy",
    "proportional_split",
    "sim_descent",
)


@dataclass
class Outcome:
    """What a policy produced, and what it cost to produce it."""

    policy: str
    assignment: Assignment
    makespan: int
    seconds: float
    simulations: int = 0
    evaluations: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    ancillas: int = 0
    exhaustive: bool = False


def feasible_names(site: Site, machine: Machine) -> list[str]:
    """Return the variants of ``site`` that this machine can actually run.

    A machine with no CCZ bank and no conversion producing CCZ cannot run a
    CCZ-consuming implementation at all, so such variants are removed before
    any policy sees them. Every policy and the oracle use the same filter, so
    they always choose from the same set.
    """

    producible = set(machine.resources)
    for conversion in machine.conversions:
        producible.add(conversion.target)
    names = []
    for name in site.variant_names:
        dag = site.variant(name).fragment.to_dag(name)
        if set(resource_counts(dag)) <= producible:
            names.append(name)
    return names


def t_equivalents(counts: dict[str, int]) -> float:
    """Return the demand expressed in T-equivalent states."""

    return sum(T_EQUIVALENT.get(resource, 1.0) * count for resource, count in counts.items())


def mixture(counts: dict[str, int]) -> float:
    """Return the share of T-equivalent demand drawn from the CCZ bank."""

    total = t_equivalents(counts)
    if total <= 0:
        return 0.0
    return T_EQUIVALENT[CCZ] * counts.get(CCZ, 0) / total


def two_term_bound(dag, machine: Machine, clifford_weight: int = 1) -> float:
    """Return ``max(critical path, max over resources of count / rate)``.

    The single-resource study found this to be sufficient when there is one
    pool. Lifting it to several resources is the obvious generalisation, and
    testing whether it is still sufficient is one of this study's questions.
    """

    counts = resource_counts(dag)
    bound = float(critical_path(dag, clifford_weight))
    for resource, count in counts.items():
        bank = machine.bank(resource)
        if bank is None:
            if machine.rate(resource) <= 0 and not any(
                conversion.target == resource for conversion in machine.conversions
            ):
                return float("inf")
            continue
        bound = max(bound, float(bank.earliest_cycle_for(count, seed=machine.seed)))
    return bound


def uniform_assignments(
    program: ProgramSpace, machine: Machine | None = None
) -> list[Assignment]:
    """Return the assignments that compile every family the same way."""

    families = sorted({site.family for site in program.sites})
    options: dict[str, list[str]] = {}
    for family in families:
        names: list[str] = []
        for site in program.sites:
            if site.family == family:
                allowed = (
                    feasible_names(site, machine)
                    if machine is not None
                    else list(site.variant_names)
                )
                for name in allowed:
                    if name not in names:
                        names.append(name)
        options[family] = names

    assignments: list[Assignment] = []
    seen: set[tuple] = set()
    for combination in product(*[[(f, n) for n in options[f]] for f in families]):
        picked = dict(combination)
        assignment: Assignment = {}
        ok = True
        for site in program.sites:
            wanted = picked.get(site.family)
            allowed = (
                feasible_names(site, machine)
                if machine is not None
                else list(site.variant_names)
            )
            if wanted in allowed:
                assignment[site.site_id] = wanted
            elif allowed:
                assignment[site.site_id] = allowed[0]
            else:
                ok = False
                break
        if not ok:
            continue
        token = tuple(sorted(assignment.items()))
        if token not in seen:
            seen.add(token)
            assignments.append(assignment)
    return assignments


def concurrent_site_counts(program: ProgramSpace) -> dict[str, int]:
    """Return how many sites can be live at the same time as each site."""

    ids = [site.site_id for site in program.sites]
    index = {site_id: position for position, site_id in enumerate(ids)}
    successors: dict[str, set[str]] = {site_id: set() for site_id in ids}
    indegree = {site_id: 0 for site_id in ids}
    for predecessor, successor in program.edges:
        successors[predecessor].add(successor)
        indegree[successor] += 1

    order = [site_id for site_id in ids if indegree[site_id] == 0]
    queue = list(order)
    while queue:
        current = queue.pop()
        for successor in successors[current]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                order.append(successor)
                queue.append(successor)
    if len(order) < len(ids):
        order = ids

    reach: dict[str, set[int]] = {}
    for site_id in reversed(order):
        collected: set[int] = set()
        for successor in successors[site_id]:
            collected.add(index[successor])
            collected |= reach[successor]
        reach[site_id] = collected

    counts: dict[str, int] = {}
    for site_id in ids:
        ordered = reach[site_id] | {
            index[other] for other in ids if index[site_id] in reach[other]
        }
        counts[site_id] = len(ids) - len(ordered)
    return counts


def _makespan(program, assignment, machine, clifford_weight=1) -> int:
    return execute(
        program.instantiate(assignment), machine, clifford_weight=clifford_weight
    ).makespan


def _finish(policy, program, assignment, machine, start, **extra) -> Outcome:
    dag = program.instantiate(assignment)
    return Outcome(
        policy=policy,
        assignment=dict(assignment),
        makespan=execute(dag, machine).makespan,
        seconds=time.perf_counter() - start,
        counts=resource_counts(dag),
        ancillas=program.ancillas(assignment),
        **extra,
    )


def select_uniform_min_teq(program: ProgramSpace, machine: Machine) -> Outcome:
    """Return the uniform implementation with the fewest T-equivalent states."""

    start = time.perf_counter()
    best = min(
        uniform_assignments(program, machine),
        key=lambda assignment: (
            t_equivalents(resource_counts(program.instantiate(assignment))),
            critical_path(program.instantiate(assignment)),
        ),
    )
    return _finish("uniform_min_teq", program, best, machine, start)


def select_min_weighted_count(program: ProgramSpace, machine: Machine) -> Outcome:
    """Return the per-site choice minimising total production time implied."""

    start = time.perf_counter()
    assignment: Assignment = {}
    for site in program.sites:
        def cost(name: str) -> tuple:
            dag = site.variant(name).fragment.to_dag(name)
            counts = resource_counts(dag)
            weighted = 0.0
            for resource, count in counts.items():
                rate = machine.rate(resource)
                weighted += count / rate if rate > 0 else float("inf")
            return (weighted, critical_path(dag), name)

        allowed = feasible_names(site, machine) or list(site.variant_names)
        assignment[site.site_id] = min(allowed, key=cost)
    return _finish("min_weighted_count", program, assignment, machine, start)


def select_uniform_oracle(program: ProgramSpace, machine: Machine) -> Outcome:
    """Return the fastest uniform implementation, found by simulation."""

    start = time.perf_counter()
    best_assignment = None
    best_cost = None
    simulations = 0
    for assignment in uniform_assignments(program, machine):
        cost = _makespan(program, assignment, machine)
        simulations += 1
        if best_cost is None or cost < best_cost:
            best_cost, best_assignment = cost, assignment
    assert best_assignment is not None
    return _finish(
        "uniform_oracle", program, best_assignment, machine, start, simulations=simulations
    )


def select_local_sim_greedy(program: ProgramSpace, machine: Machine) -> Outcome:
    """Return the per-site choice that is fastest against the whole machine."""

    start = time.perf_counter()
    assignment: Assignment = {}
    simulations = 0
    for site in program.sites:
        best_name, best_key = None, None
        for name in feasible_names(site, machine):
            dag = site.variant(name).fragment.to_dag(name)
            cost = execute(dag, machine).makespan
            simulations += 1
            key = (cost, t_equivalents(resource_counts(dag)), name)
            if best_key is None or key < best_key:
                best_key, best_name = key, name
        assignment[site.site_id] = best_name or site.variants[0].name
    return _finish(
        "local_sim_greedy", program, assignment, machine, start, simulations=simulations
    )


def _scaled_machine(machine: Machine, share: int) -> Machine:
    """Return the machine divided by ``share`` concurrent consumers."""

    banks = []
    for bank in machine.banks:
        banks.append(
            FactoryBank(
                resource=bank.resource,
                count=max(1, round(bank.count / share)),
                period=bank.period,
                latency=bank.latency,
                buffer_capacity=(
                    bank.buffer_capacity
                    if bank.unbounded_buffer
                    else max(1, bank.buffer_capacity // share)
                ),
                tiles_per_factory=bank.tiles_per_factory,
                p_success=bank.p_success,
                stagger=bank.stagger,
            )
        )
    return Machine(
        banks=tuple(banks),
        conversions=machine.conversions,
        name=f"{machine.name}/share{share}",
        seed=machine.seed,
    )


def select_share_aware_greedy(program: ProgramSpace, machine: Machine) -> Outcome:
    """Return the per-site choice that is fastest against that site's share."""

    start = time.perf_counter()
    shares = concurrent_site_counts(program)
    cache: dict[int, Machine] = {}
    assignment: Assignment = {}
    simulations = 0
    for site in program.sites:
        share = max(1, shares.get(site.site_id, 1))
        scaled = cache.setdefault(share, _scaled_machine(machine, share))
        best_name, best_key = None, None
        for name in feasible_names(site, machine):
            dag = site.variant(name).fragment.to_dag(name)
            cost = execute(dag, scaled).makespan
            simulations += 1
            key = (cost, t_equivalents(resource_counts(dag)), name)
            if best_key is None or key < best_key:
                best_key, best_name = key, name
        assignment[site.site_id] = best_name or site.variants[0].name
    return _finish(
        "share_aware_greedy", program, assignment, machine, start, simulations=simulations
    )


def _descend(program, machine, score, seeds, max_rounds=4, max_evaluations=None):
    """Coordinate descent over site choices under an arbitrary score.

    ``max_evaluations`` caps the number of scored candidates. It is a hard stop
    rather than an estimate, so a caller with a wall-clock budget can honour it
    whatever the cost of one evaluation turns out to be.
    """

    sites = decision_sites(program)
    allowed = {site.site_id: feasible_names(site, machine) or list(site.variant_names)
               for site in sites}
    evaluations = 0
    best_assignment, best_cost = None, float("inf")
    def exhausted() -> bool:
        return max_evaluations is not None and evaluations >= max_evaluations

    for seed in seeds:
        if exhausted() and best_assignment is not None:
            break
        current = dict(seed)
        current_cost = score(current)
        evaluations += 1
        for _ in range(max_rounds):
            improved = False
            for site in sites:
                incumbent = current[site.site_id]
                local_best, local_cost = incumbent, current_cost
                for name in allowed[site.site_id]:
                    if name == incumbent or exhausted():
                        continue
                    current[site.site_id] = name
                    candidate = score(current)
                    evaluations += 1
                    if candidate < local_cost - 1e-9:
                        local_cost, local_best = candidate, name
                current[site.site_id] = local_best
                if local_best != incumbent:
                    current_cost = local_cost
                    improved = True
            if not improved or exhausted():
                break
        if current_cost < best_cost - 1e-9:
            best_cost, best_assignment = current_cost, dict(current)
    assert best_assignment is not None
    return best_assignment, evaluations


def _seeds(program: ProgramSpace, machine: Machine, limit: int = 8) -> list[Assignment]:
    """Return a spread of uniform assignments to start a search from."""

    candidates = uniform_assignments(program, machine)
    if len(candidates) <= limit:
        return candidates
    step = len(candidates) / limit
    return [candidates[min(len(candidates) - 1, int(index * step))] for index in range(limit)]


def select_two_term_descent(program: ProgramSpace, machine: Machine) -> Outcome:
    """Return the assignment minimising the lifted two-term bound."""

    start = time.perf_counter()
    assignment, evaluations = _descend(
        program,
        machine,
        lambda choice: two_term_bound(program.instantiate(choice), machine),
        _seeds(program, machine),
    )
    return _finish(
        "two_term_descent", program, assignment, machine, start, evaluations=evaluations
    )


def select_sim_descent(program: ProgramSpace, machine: Machine) -> Outcome:
    """Return the assignment found by coordinate descent on the simulator."""

    start = time.perf_counter()
    assignment, evaluations = _descend(
        program,
        machine,
        lambda choice: float(_makespan(program, choice, machine)),
        _seeds(program, machine),
    )
    return _finish(
        "sim_descent", program, assignment, machine, start, simulations=evaluations
    )


def global_oracle(
    program: ProgramSpace,
    machine: Machine,
    limit: int = 60_000,
    search_budget: float = 20.0,
    extra_seeds: Sequence[Assignment] = (),
) -> Outcome:
    """Return the exact best assignment where the space is small enough.

    When the space exceeds ``limit`` the answer is the best of every policy and
    of coordinate descent from many seeds, and ``exhaustive`` is False. Rows
    marked that way are excluded from any claim requiring an exact optimum.
    """

    start = time.perf_counter()
    sites = decision_sites(program)
    allowed = {
        site.site_id: feasible_names(site, machine) or list(site.variant_names)
        for site in sites
    }
    space = 1
    for names in allowed.values():
        space *= len(names)
    if 0 < space <= limit:
        base = program.default_assignment()
        for site in program.sites:
            if site.site_id in allowed:
                base[site.site_id] = allowed[site.site_id][0]
        best_assignment, best_cost, simulations = None, None, 0
        site_ids = list(allowed)
        for combination in product(*[allowed[site_id] for site_id in site_ids]):
            assignment = dict(base)
            assignment.update(dict(zip(site_ids, combination)))
            cost = _makespan(program, assignment, machine)
            simulations += 1
            if best_cost is None or cost < best_cost:
                best_cost, best_assignment = cost, dict(assignment)
        assert best_assignment is not None
        return _finish(
            "global_oracle",
            program,
            best_assignment,
            machine,
            start,
            simulations=simulations,
            exhaustive=True,
        )

    # Bound the fallback search too: with expensive simulations, fewer restarts.
    # The probe must use an expensive assignment, since simulation cost tracks
    # the makespan and the search will visit the expensive candidates.
    candidates = uniform_assignments(program, machine) or [program.default_assignment()]
    heaviest = max(
        candidates,
        key=lambda choice: t_equivalents(resource_counts(program.instantiate(choice))),
    )
    probe_start = time.perf_counter()
    _makespan(program, heaviest, machine)
    per_simulation = max(time.perf_counter() - probe_start, 1e-6)
    affordable = max(40, int(search_budget / per_simulation))
    seeds = _seeds(program, machine, limit=16)
    for policy in (select_uniform_oracle, select_share_aware_greedy, select_local_sim_greedy):
        seeds.append(policy(program, machine).assignment)
    # Seeding with what every policy produced guarantees the reference is at
    # least as good as any policy it is compared against, which a search-based
    # reference does not otherwise ensure.
    seeds.extend(dict(seed) for seed in extra_seeds)
    assignment, evaluations = _descend(
        program,
        machine,
        lambda choice: float(_makespan(program, choice, machine)),
        seeds,
        max_rounds=4,
        max_evaluations=affordable,
    )
    return _finish(
        "global_oracle",
        program,
        assignment,
        machine,
        start,
        simulations=evaluations,
        exhaustive=False,
    )


def _dominant_resource(site: Site, name: str) -> str | None:
    """Return the resource a variant draws on, if it draws on exactly one."""

    counts = resource_counts(site.variant(name).fragment.to_dag(name))
    present = [resource for resource, count in counts.items() if count > 0]
    return present[0] if len(present) == 1 else None


def select_proportional_split(program: ProgramSpace, machine: Machine) -> Outcome:
    """Split interchangeable sites between the banks in proportion to their rates.

    This is the obvious thing to try once the resources are known to be
    non-fungible, and it needs no search and no simulation: for each group of
    interchangeable sites, send a fraction of them to the CCZ bank equal to the
    CCZ bank's share of total T-equivalent capacity, and the rest to the T
    bank, picking the cheapest single-resource implementation on each side. If
    this captures the available headroom then nothing more elaborate is
    justified.
    """

    start = time.perf_counter()
    capacity = machine.rate(T) + T_EQUIVALENT[CCZ] * machine.rate(CCZ)
    ccz_fraction = (
        T_EQUIVALENT[CCZ] * machine.rate(CCZ) / capacity if capacity > 0 else 0.0
    )

    assignment: Assignment = program.default_assignment()
    for site in program.sites:
        allowed = feasible_names(site, machine)
        if allowed:
            assignment[site.site_id] = allowed[0]

    for group in symmetric_groups(program):
        template = group[0]
        allowed = feasible_names(template, machine) or list(template.variant_names)
        cheapest: dict[str, str] = {}
        for name in allowed:
            resource = _dominant_resource(template, name)
            if resource is None:
                continue
            counts = resource_counts(template.variant(name).fragment.to_dag(name))
            incumbent = cheapest.get(resource)
            if incumbent is None or t_equivalents(counts) < t_equivalents(
                resource_counts(template.variant(incumbent).fragment.to_dag(incumbent))
            ):
                cheapest[resource] = name

        if CCZ not in cheapest or T not in cheapest:
            only = cheapest.get(CCZ) or cheapest.get(T) or allowed[0]
            for site in group:
                assignment[site.site_id] = only
            continue

        on_ccz = int(round(len(group) * ccz_fraction))
        for index, site in enumerate(group):
            assignment[site.site_id] = cheapest[CCZ] if index < on_ccz else cheapest[T]

    return _finish("proportional_split", program, assignment, machine, start)


SELECTORS = {
    "uniform_min_teq": select_uniform_min_teq,
    "min_weighted_count": select_min_weighted_count,
    "uniform_oracle": select_uniform_oracle,
    "two_term_descent": select_two_term_descent,
    "local_sim_greedy": select_local_sim_greedy,
    "share_aware_greedy": select_share_aware_greedy,
    "proportional_split": select_proportional_split,
    "sim_descent": select_sim_descent,
}


def run_policy(policy: str, program: ProgramSpace, machine: Machine) -> Outcome:
    """Run one named policy end to end."""

    if policy not in SELECTORS:
        raise ValueError(f"unknown policy {policy!r}")
    return SELECTORS[policy](program, machine)


def heterogeneity(program: ProgramSpace, assignment: Assignment) -> float:
    """Return how far an assignment departs from compiling each family uniformly.

    A library-style compiler picks one implementation per *family*, so an
    assignment that gives adders one implementation and rotations another is
    still uniform in the sense that matters. What this measures is mixing
    *within* a family: the fraction of sites whose variant differs from the
    most common variant among the sites of its own family. That is exactly the
    freedom the uniform baselines do not have.
    """

    sites = decision_sites(program)
    if not sites:
        return 0.0
    by_family: dict[str, list[str]] = {}
    for site in sites:
        by_family.setdefault(site.family, []).append(assignment[site.site_id])
    deviating = 0
    for picks in by_family.values():
        most_common = max(set(picks), key=picks.count)
        deviating += len(picks) - picks.count(most_common)
    return deviating / len(sites)


def space_time(
    program: ProgramSpace,
    assignment: Assignment,
    machine: Machine,
    makespan: int,
    data_tiles: int,
) -> int:
    """Return makespan times the tiles the machine and program occupy.

    The factory banks are charged, so a policy cannot look good by assuming a
    factory it does not pay for, and the ancillas the chosen implementations
    need are charged too.
    """

    return makespan * (machine.factory_tiles + data_tiles + program.ancillas(assignment))


def symmetric_groups(program: ProgramSpace) -> list[list[Site]]:
    """Group decision sites that are interchangeable in the program graph.

    Two sites are interchangeable when they have the same predecessors, the
    same successors and the same variant set, which in the staged kernels means
    they sit in the same stage and offer the same implementations. Swapping the
    choices of two such sites cannot change the makespan, so the optimum over
    all assignments equals the optimum over multisets of choices per group.
    """

    predecessors: dict[str, set[str]] = {site.site_id: set() for site in program.sites}
    successors: dict[str, set[str]] = {site.site_id: set() for site in program.sites}
    for source, target in program.edges:
        successors[source].add(target)
        predecessors[target].add(source)

    groups: dict[tuple, list[Site]] = {}
    for site in decision_sites(program):
        signature = (
            tuple(sorted(predecessors[site.site_id])),
            tuple(sorted(successors[site.site_id])),
            site.variant_names,
        )
        groups.setdefault(signature, []).append(site)
    return [sorted(group, key=lambda site: site.site_id) for group in groups.values()]


def symmetric_space(program: ProgramSpace, machine: Machine) -> int:
    """Return how many assignments remain after collapsing interchangeable sites."""

    from math import comb

    total = 1
    for group in symmetric_groups(program):
        names = feasible_names(group[0], machine) or list(group[0].variant_names)
        total *= comb(len(group) + len(names) - 1, len(names) - 1) if len(names) > 1 else 1
    return total


def symmetric_oracle(
    program: ProgramSpace, machine: Machine, limit: int = 200_000
) -> Outcome | None:
    """Return the exact optimum, enumerating multisets rather than assignments.

    Returns ``None`` when even the collapsed space exceeds ``limit``. When it
    returns an outcome, that outcome is the true global optimum: the reduction
    is exact, not a heuristic.
    """

    from itertools import combinations_with_replacement

    start = time.perf_counter()
    groups = symmetric_groups(program)
    if not groups:
        return None
    if symmetric_space(program, machine) > limit:
        return None

    choices = []
    for group in groups:
        names = feasible_names(group[0], machine) or list(group[0].variant_names)
        choices.append(list(combinations_with_replacement(names, len(group))))

    base = program.default_assignment()
    for site in program.sites:
        allowed = feasible_names(site, machine)
        if allowed:
            base[site.site_id] = allowed[0]

    best_assignment, best_cost, simulations = None, None, 0
    for combination in product(*choices):
        assignment = dict(base)
        for group, picks in zip(groups, combination):
            for site, name in zip(group, picks):
                assignment[site.site_id] = name
        cost = _makespan(program, assignment, machine)
        simulations += 1
        if best_cost is None or cost < best_cost:
            best_cost, best_assignment = cost, dict(assignment)
    assert best_assignment is not None
    return _finish(
        "global_oracle",
        program,
        best_assignment,
        machine,
        start,
        simulations=simulations,
        exhaustive=True,
    )


def best_oracle(
    program: ProgramSpace,
    machine: Machine,
    limit: int = 40_000,
    symmetric_limit: int = 25_000,
    time_budget: float = 60.0,
    extra_seeds: Sequence[Assignment] = (),
) -> Outcome:
    """Return the strongest optimality reference affordable within a time budget.

    Exact enumeration is preferred, and the symmetry reduction makes it
    tractable at concurrencies where enumerating assignments is not. Whether it
    is affordable depends on the cost of one simulation as much as on the
    number of candidates, and that cost varies by two orders of magnitude
    across these kernels, so the budget is measured in seconds: one simulation
    is timed, and exact enumeration is used only if the projected total fits.

    The budget is a resource limit, not a correctness condition. Whatever is
    returned reports whether it is exact, and rows that are not are excluded
    from claims that require a proven optimum.
    """

    # Simulation cost tracks the makespan, and the makespan varies by an order
    # of magnitude across assignments, so the probe uses the most expensive
    # uniform assignment rather than the default one. Probing with a cheap
    # candidate would understate the cost of enumeration by roughly that factor.
    candidates = uniform_assignments(program, machine) or [program.default_assignment()]
    heaviest = max(
        candidates,
        key=lambda choice: t_equivalents(resource_counts(program.instantiate(choice))),
    )
    probe_start = time.perf_counter()
    _makespan(program, heaviest, machine)
    per_simulation = max(time.perf_counter() - probe_start, 1e-6)

    reduced_space = symmetric_space(program, machine)
    if (
        reduced_space <= symmetric_limit
        and reduced_space * per_simulation <= time_budget
    ):
        reduced = symmetric_oracle(program, machine, limit=symmetric_limit)
        if reduced is not None:
            return reduced

    space = 1
    for site in decision_sites(program):
        space *= len(feasible_names(site, machine) or list(site.variant_names))
    if space <= limit and space * per_simulation <= time_budget:
        return global_oracle(program, machine, limit=limit)

    return global_oracle(
        program,
        machine,
        limit=0,
        search_budget=time_budget,
        extra_seeds=extra_seeds,
    )


def _dominant_resource(site: Site, name: str) -> str | None:
    """Return the resource a variant draws on, if it draws on exactly one."""

    counts = resource_counts(site.variant(name).fragment.to_dag(name))
    present = [resource for resource, count in counts.items() if count > 0]
    return present[0] if len(present) == 1 else None


def select_proportional_split(program: ProgramSpace, machine: Machine) -> Outcome:
    """Split interchangeable sites between the banks in proportion to their rates.

    This is the obvious thing to try once the resources are known to be
    non-fungible, and it needs no search and no simulation: for each group of
    interchangeable sites, send a fraction of them to the CCZ bank equal to the
    CCZ bank's share of total T-equivalent capacity, and the rest to the T
    bank, picking the cheapest single-resource implementation on each side. If
    this captures the available headroom then nothing more elaborate is
    justified.
    """

    start = time.perf_counter()
    capacity = machine.rate(T) + T_EQUIVALENT[CCZ] * machine.rate(CCZ)
    ccz_fraction = (
        T_EQUIVALENT[CCZ] * machine.rate(CCZ) / capacity if capacity > 0 else 0.0
    )

    assignment: Assignment = program.default_assignment()
    for site in program.sites:
        allowed = feasible_names(site, machine)
        if allowed:
            assignment[site.site_id] = allowed[0]

    for group in symmetric_groups(program):
        template = group[0]
        allowed = feasible_names(template, machine) or list(template.variant_names)
        cheapest: dict[str, str] = {}
        for name in allowed:
            resource = _dominant_resource(template, name)
            if resource is None:
                continue
            counts = resource_counts(template.variant(name).fragment.to_dag(name))
            incumbent = cheapest.get(resource)
            if incumbent is None or t_equivalents(counts) < t_equivalents(
                resource_counts(template.variant(incumbent).fragment.to_dag(incumbent))
            ):
                cheapest[resource] = name

        if CCZ not in cheapest or T not in cheapest:
            only = cheapest.get(CCZ) or cheapest.get(T) or allowed[0]
            for site in group:
                assignment[site.site_id] = only
            continue

        on_ccz = int(round(len(group) * ccz_fraction))
        for index, site in enumerate(group):
            assignment[site.site_id] = cheapest[CCZ] if index < on_ccz else cheapest[T]

    return _finish("proportional_split", program, assignment, machine, start)


SELECTORS = {
    "uniform_min_teq": select_uniform_min_teq,
    "min_weighted_count": select_min_weighted_count,
    "uniform_oracle": select_uniform_oracle,
    "two_term_descent": select_two_term_descent,
    "local_sim_greedy": select_local_sim_greedy,
    "share_aware_greedy": select_share_aware_greedy,
    "proportional_split": select_proportional_split,
    "sim_descent": select_sim_descent,
}


def run_policy(policy: str, program: ProgramSpace, machine: Machine) -> Outcome:
    """Run one named policy end to end."""

    if policy not in SELECTORS:
        raise ValueError(f"unknown policy {policy!r}")
    return SELECTORS[policy](program, machine)


def heterogeneity(program: ProgramSpace, assignment: Assignment) -> float:
    """Return how far an assignment departs from compiling each family uniformly.

    A library-style compiler picks one implementation per *family*, so an
    assignment that gives adders one implementation and rotations another is
    still uniform in the sense that matters. What this measures is mixing
    *within* a family: the fraction of sites whose variant differs from the
    most common variant among the sites of its own family. That is exactly the
    freedom the uniform baselines do not have.
    """

    sites = decision_sites(program)
    if not sites:
        return 0.0
    by_family: dict[str, list[str]] = {}
    for site in sites:
        by_family.setdefault(site.family, []).append(assignment[site.site_id])
    deviating = 0
    for picks in by_family.values():
        most_common = max(set(picks), key=picks.count)
        deviating += len(picks) - picks.count(most_common)
    return deviating / len(sites)


def space_time(
    program: ProgramSpace,
    assignment: Assignment,
    machine: Machine,
    makespan: int,
    data_tiles: int,
) -> int:
    """Return makespan times the tiles the machine and program occupy.

    The factory banks are charged, so a policy cannot look good by assuming a
    factory it does not pay for, and the ancillas the chosen implementations
    need are charged too.
    """

    return makespan * (machine.factory_tiles + data_tiles + program.ancillas(assignment))


def symmetric_groups(program: ProgramSpace) -> list[list[Site]]:
    """Group decision sites that are interchangeable in the program graph.

    Two sites are interchangeable when they have the same predecessors, the
    same successors and the same variant set, which in the staged kernels means
    they sit in the same stage and offer the same implementations. Swapping the
    choices of two such sites cannot change the makespan, so the optimum over
    all assignments equals the optimum over multisets of choices per group.
    """

    predecessors: dict[str, set[str]] = {site.site_id: set() for site in program.sites}
    successors: dict[str, set[str]] = {site.site_id: set() for site in program.sites}
    for source, target in program.edges:
        successors[source].add(target)
        predecessors[target].add(source)

    groups: dict[tuple, list[Site]] = {}
    for site in decision_sites(program):
        signature = (
            tuple(sorted(predecessors[site.site_id])),
            tuple(sorted(successors[site.site_id])),
            site.variant_names,
        )
        groups.setdefault(signature, []).append(site)
    return [sorted(group, key=lambda site: site.site_id) for group in groups.values()]


def symmetric_space(program: ProgramSpace, machine: Machine) -> int:
    """Return how many assignments remain after collapsing interchangeable sites."""

    from math import comb

    total = 1
    for group in symmetric_groups(program):
        names = feasible_names(group[0], machine) or list(group[0].variant_names)
        total *= comb(len(group) + len(names) - 1, len(names) - 1) if len(names) > 1 else 1
    return total


def symmetric_oracle(
    program: ProgramSpace, machine: Machine, limit: int = 200_000
) -> Outcome | None:
    """Return the exact optimum, enumerating multisets rather than assignments.

    Returns ``None`` when even the collapsed space exceeds ``limit``. When it
    returns an outcome, that outcome is the true global optimum: the reduction
    is exact, not a heuristic.
    """

    from itertools import combinations_with_replacement

    start = time.perf_counter()
    groups = symmetric_groups(program)
    if not groups:
        return None
    if symmetric_space(program, machine) > limit:
        return None

    choices = []
    for group in groups:
        names = feasible_names(group[0], machine) or list(group[0].variant_names)
        choices.append(list(combinations_with_replacement(names, len(group))))

    base = program.default_assignment()
    for site in program.sites:
        allowed = feasible_names(site, machine)
        if allowed:
            base[site.site_id] = allowed[0]

    best_assignment, best_cost, simulations = None, None, 0
    for combination in product(*choices):
        assignment = dict(base)
        for group, picks in zip(groups, combination):
            for site, name in zip(group, picks):
                assignment[site.site_id] = name
        cost = _makespan(program, assignment, machine)
        simulations += 1
        if best_cost is None or cost < best_cost:
            best_cost, best_assignment = cost, dict(assignment)
    assert best_assignment is not None
    return _finish(
        "global_oracle",
        program,
        best_assignment,
        machine,
        start,
        simulations=simulations,
        exhaustive=True,
    )
