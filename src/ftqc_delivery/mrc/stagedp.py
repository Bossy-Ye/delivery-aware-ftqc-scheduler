"""A stage-wise dynamic-programming selector.

Why this shape. On the kernels where every uniform and per-site policy loses to
the global optimum, the optimum alternates which factory bank successive
stages draw on: while one stage runs on CCZ states, the T bank keeps producing
into its buffer, and the next stage is implemented from T to consume that
stock before it overflows. A per-site policy cannot see the stock the previous
stage left behind; a uniform policy cannot alternate at all. Single-stage
kernels never showed the failure, which is what this explanation predicts.

So the state a selector must carry between stages is the buffer contents at
the stage boundary, and nothing else about the past. That makes the problem a
shortest path over (stage, buffer state): each stage is scored from the state
its predecessor leaves, using either a small stage-local simulation or an
analytic two-term cost, and dominated states are pruned as the frontier moves
forward. Whole-program simulation is never required.
"""

from __future__ import annotations

import time
from itertools import combinations_with_replacement, product
from math import comb

from ftqc_delivery.rac.variants import Assignment, ProgramSpace, Site

from .execution import critical_path, execute, resource_counts
from .kernels import decision_sites
from .policies import Outcome, _finish, feasible_names, symmetric_groups
from .resources import Machine


def pipeline_stages(program: ProgramSpace) -> list[list[list[Site]]]:
    """Return decision sites grouped into ordered stages of interchangeable groups.

    A stage is the set of decision sites at the same depth in the site graph,
    measured in decision sites along the longest path from the program's
    sources. In the staged kernels this recovers the barrier-delimited stages
    exactly; for a general site graph it is a levelisation.
    """

    predecessors: dict[str, set[str]] = {site.site_id: set() for site in program.sites}
    for source, target in program.edges:
        predecessors[target].add(source)
    decision = {site.site_id for site in decision_sites(program)}

    depth: dict[str, int] = {}
    order: list[str] = []
    remaining = {site.site_id: len(predecessors[site.site_id]) for site in program.sites}
    successors: dict[str, set[str]] = {site.site_id: set() for site in program.sites}
    for source, target in program.edges:
        successors[source].add(target)
    queue = [site_id for site_id, count in remaining.items() if count == 0]
    while queue:
        current = queue.pop()
        order.append(current)
        for nxt in successors[current]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                queue.append(nxt)
    for site_id in order:
        best = 0
        for pred in predecessors[site_id]:
            best = max(best, depth[pred] + (1 if pred in decision else 0))
        depth[site_id] = best

    by_depth: dict[int, list[Site]] = {}
    for group in symmetric_groups(program):
        by_depth.setdefault(depth[group[0].site_id], []).append(group)
    return [by_depth[key] for key in sorted(by_depth)]


def stage_program(program: ProgramSpace, stage: list[list[Site]]) -> ProgramSpace:
    """Return a program containing only one stage's sites, run in parallel."""

    sites = tuple(site for group in stage for site in group)
    return ProgramSpace(name=f"{program.name}_stage", sites=sites, edges=(), meta=program.meta)


def stage_choices(stage: list[list[Site]], machine: Machine, limit: int = 4000):
    """Yield assignments for one stage: one multiset of variants per group.

    Groups are interchangeable sites, so a multiset per group is exact. When
    the product over groups is too large -- which happens on extracted real
    programs, where most groups are singletons -- sites of the same family in
    the stage are pooled and one multiset is enumerated per family, assigned
    to the sites in order. That is a heuristic symmetry, and it is what keeps
    the stage-wise search polynomial on real circuits.
    """

    per_group = []
    total = 1
    for group in stage:
        names = feasible_names(group[0], machine) or list(group[0].variant_names)
        per_group.append((group, names))
        total *= comb(len(group) + len(names) - 1, len(names) - 1)
    if total <= limit:
        iters = [list(combinations_with_replacement(names, len(group))) for group, names in per_group]
        for combination in product(*iters):
            assignment: Assignment = {}
            for (group, _), picks in zip(per_group, combination):
                for site, name in zip(group, picks):
                    assignment[site.site_id] = name
            yield assignment
        return

    pooled: dict[tuple, list[Site]] = {}
    for group, names in per_group:
        pooled.setdefault(tuple(names), []).extend(group)
    pools = list(pooled.items())
    pooled_total = 1
    for names, sites in pools:
        pooled_total *= comb(len(sites) + len(names) - 1, len(names) - 1)
    if pooled_total <= limit:
        iters = [list(combinations_with_replacement(names, len(sites))) for names, sites in pools]
    else:
        # Even the pooled multisets are too many: take uniform choices per
        # pool plus even two-way splits, which is where the alternation lives.
        iters = []
        for names, sites in pools:
            options = [tuple([name] * len(sites)) for name in names]
            half = len(sites) // 2
            for i, first in enumerate(names):
                for second in names[i + 1:]:
                    options.append(tuple([first] * half + [second] * (len(sites) - half)))
            iters.append(options)
    for combination in product(*iters):
        assignment = {}
        for (names, sites), picks in zip(pools, combination):
            for site, name in zip(sites, picks):
                assignment[site.site_id] = name
        yield assignment


def _stage_cost_sim(sub: ProgramSpace, assignment: Assignment, machine: Machine, entry: dict[str, int]):
    """Return (duration, exit stock) by simulating one stage from ``entry``."""

    trace = execute(sub.instantiate(assignment), machine.with_initial_stock(entry))
    return trace.makespan, {r: c for r, c in trace.final_stock.items()}


def _stage_cost_analytic(sub: ProgramSpace, assignment: Assignment, machine: Machine, entry: dict[str, int]):
    """Return (duration, exit stock) from a two-term model with carried stock.

    Duration is the larger of the stage's critical path and, for each
    resource, the first cycle by which the stage's demand net of the stock it
    inherits has been produced. Exit stock is what the banks produce during
    that time, plus the inherited stock, minus what the stage consumes, capped
    by the buffer. Factory phase at the stage boundary is ignored.
    """

    dag = sub.instantiate(assignment)
    counts = resource_counts(dag)
    duration = float(critical_path(dag))
    for resource, count in counts.items():
        need = max(0, count - entry.get(resource, 0))
        bank = machine.bank(resource)
        if bank is not None:
            duration = max(duration, float(bank.earliest_cycle_for(need, seed=machine.seed)))
        else:
            rate = machine.rate(resource)
            if rate <= 0:
                return float("inf"), dict(entry)
            producers = [c for c in machine.conversions if c.target == resource]
            lead = min(c.latency for c in producers) if producers and need > 0 else 0
            duration = max(duration, lead + need / rate)
    exit_stock: dict[str, int] = {}
    for resource in machine.producible:
        bank = machine.bank(resource)
        produced = (
            sum(bank.arrival_series(int(duration) + 1, seed=machine.seed)[: int(duration) + 1])
            if bank is not None
            else int(machine.rate(resource) * duration)
        )
        level = entry.get(resource, 0) + produced - counts.get(resource, 0)
        cap = machine.buffer(resource)
        exit_stock[resource] = max(0, min(level, cap) if cap >= 0 else level)
    return duration, exit_stock


def _dominated(time_a, stock_a, time_b, stock_b) -> bool:
    """Return whether (time_a, stock_a) is dominated by (time_b, stock_b)."""

    if time_b > time_a:
        return False
    if any(stock_b.get(r, 0) < stock_a.get(r, 0) for r in set(stock_a) | set(stock_b)):
        return False
    return time_b < time_a or any(stock_b.get(r, 0) > stock_a.get(r, 0) for r in set(stock_a) | set(stock_b))


def select_stage_dp(
    program: ProgramSpace,
    machine: Machine,
    mode: str = "analytic",
    refine: int = 0,
    frontier_limit: int = 64,
) -> Outcome:
    """Choose implementations by dynamic programming over stages and buffer state.

    ``mode`` selects the stage cost: ``sim`` runs the stage on the machine from
    the inherited buffer state (a small simulation, never the whole program);
    ``analytic`` uses the two-term model with carried stock. ``refine`` keeps
    that many best DP solutions and picks among them by one full simulation
    each, which bounds the price of the analytic model's blind spots.
    """

    start = time.perf_counter()
    stages = pipeline_stages(program)
    cost = _stage_cost_sim if mode == "sim" else _stage_cost_analytic
    evaluations = 0

    initial = {resource: machine.initial(resource) for resource in machine.producible}
    frontier: list[tuple[float, dict[str, int], list[Assignment]]] = [(0.0, initial, [])]

    for stage in stages:
        sub = stage_program(program, stage)
        choices = list(stage_choices(stage, machine))
        candidates: list[tuple[float, dict[str, int], list[Assignment]]] = []
        for elapsed, entry, history in frontier:
            for choice in choices:
                duration, exit_stock = cost(sub, choice, machine, entry)
                evaluations += 1
                candidates.append((elapsed + duration, exit_stock, history + [choice]))
        candidates.sort(key=lambda item: item[0])
        kept: list[tuple[float, dict[str, int], list[Assignment]]] = []
        for candidate in candidates:
            if any(_dominated(candidate[0], candidate[1], other[0], other[1]) for other in kept):
                continue
            kept.append(candidate)
            if len(kept) >= frontier_limit:
                break
        frontier = kept

    frontier.sort(key=lambda item: item[0])
    finalists = frontier[: max(1, refine)] if refine else frontier[:1]
    best_assignment: Assignment | None = None
    best_value = None
    simulations = 0
    for predicted, _, history in finalists:
        assignment = program.default_assignment()
        for choice in history:
            assignment.update(choice)
        if refine:
            value = execute(program.instantiate(assignment), machine).makespan
            simulations += 1
        else:
            value = predicted
        if best_value is None or value < best_value:
            best_value, best_assignment = value, assignment
    assert best_assignment is not None
    label = f"stage_dp_{mode}" + (f"_r{refine}" if refine else "")
    return _finish(label, program, best_assignment, machine, start, evaluations=evaluations, simulations=simulations)
