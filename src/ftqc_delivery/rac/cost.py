"""Analytic cost models for resource-aware compilation.

Everything in this module is a *static* estimate: it reads the dependency
structure of a candidate circuit and the parameters of the supply process, and
returns a predicted execution time without ever running the machine. That
restriction is deliberate. A compiler cannot afford to simulate every candidate
it considers, so a selection mechanism is only interesting if it works from a
cost model of this kind.

The central model is the *supply-constrained critical path* (SCCP). The
familiar critical-path bound says a program cannot finish before its longest
dependency chain. SCCP adds the dual statement for a rate-limited consumable:
for any deadline structure in the program, the magic states that must be
consumed late enough and early enough cannot be delivered faster than the
factories produce them. Taking the maximum over all such windows yields a
bound that is aware of dependencies, T-count, factory throughput, production
latency, and buffer capacity at once.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from math import ceil

from ftqc_delivery.dag.graph import CircuitDAG

from .analysis import (
    asap_t_demand,
    logical_depth,
    release_times,
    t_count,
    t_depth,
    tails,
)
from .supply import SupplyModel


MODELS = (
    "deps_only",
    "t_count_only",
    "deps_plus_count",
    "deps_plus_throughput",
    "sccp",
    "sccp_plus",
)


@dataclass
class SupplyProfile:
    """Precomputed cumulative arrivals of a supply process."""

    supply: SupplyModel
    horizon: int
    cumulative: list[int]

    @classmethod
    def build(cls, supply: SupplyModel, horizon: int) -> "SupplyProfile":
        """Return the cumulative arrival curve up to ``horizon`` cycles."""

        horizon = max(1, int(horizon))
        cumulative = [0] * (horizon + 1)
        running = 0
        for cycle in range(1, horizon + 1):
            running += supply.arrivals(cycle)
            cumulative[cycle] = running
        return cls(supply=supply, horizon=horizon, cumulative=cumulative)

    def upto(self, cycle: int) -> int:
        """Return the number of states produced by the end of ``cycle``."""

        if cycle <= 0:
            return 0
        if cycle >= self.horizon:
            extra = cycle - self.horizon
            return self.cumulative[self.horizon] + int(extra * self.supply.rate)
        return self.cumulative[cycle]

    def earliest_cycle_for(self, start: int, needed: int, carried: int) -> int:
        """Return the first cycle at or after ``start`` delivering ``needed`` states.

        ``carried`` is an upper bound on the stock already held entering
        ``start``. The answer counts that stock, so it is optimistic and the
        resulting bound stays valid.
        """

        if needed <= carried:
            return start
        target = self.upto(start - 1) + (needed - carried)
        if target <= self.cumulative[self.horizon]:
            index = bisect_left(self.cumulative, target)
            return max(start, index)
        deficit = target - self.cumulative[self.horizon]
        return max(start, self.horizon + ceil(deficit / self.supply.rate))

    def carried_stock(self, cycle: int) -> int:
        """Return an upper bound on the stock held entering ``cycle``."""

        produced = self.supply.initial_stock + self.upto(cycle - 1)
        if self.supply.unbounded_buffer:
            return produced
        return min(produced, self.supply.buffer_capacity)


def default_horizon(dag: CircuitDAG, supply: SupplyModel, clifford_weight: int = 1) -> int:
    """Return a horizon comfortably past any plausible makespan."""

    states = t_count(dag)
    depth = logical_depth(dag, clifford_weight)
    supply_span = supply.production_latency + int(states / supply.rate) + supply.period
    return 2 * max(depth, supply_span) + 128


def _thresholds(values: list[int], limit: int) -> list[int]:
    """Return at most ``limit`` distinct values spread across ``values``."""

    unique = sorted(set(values))
    if len(unique) <= limit:
        return unique
    step = len(unique) / limit
    picked = {unique[min(len(unique) - 1, int(index * step))] for index in range(limit)}
    picked.add(unique[0])
    picked.add(unique[-1])
    return sorted(picked)


def sccp_bound(
    dag: CircuitDAG,
    supply: SupplyModel,
    clifford_weight: int = 1,
    profile: SupplyProfile | None = None,
    threshold_limit: int = 48,
    use_buffer: bool = True,
) -> int:
    """Return the supply-constrained critical-path lower bound on execution time.

    For every pair of thresholds ``(a, b)`` the set of T gates that cannot start
    before cycle ``a`` and that carry at least ``b`` cycles of work behind them
    must all be supplied at or after ``a``. The factories therefore fix the
    earliest cycle at which the last of them can start, and ``b`` more cycles
    must follow. The bound is the largest such value, and it is never smaller
    than the plain dependency critical path.
    """

    if profile is None:
        profile = SupplyProfile.build(supply, default_horizon(dag, supply, clifford_weight))

    best = logical_depth(dag, clifford_weight)
    release = release_times(dag, clifford_weight)
    tail = tails(dag, clifford_weight)
    gates = [
        (release[node_id], tail[node_id])
        for node_id in dag.nodes
        if dag.nodes[node_id].is_t
    ]
    if not gates:
        return best

    starts = _thresholds([item[0] for item in gates], threshold_limit)
    ends = _thresholds([item[1] for item in gates], threshold_limit)
    gates.sort(key=lambda item: -item[0])

    for start in starts:
        eligible = sorted((item[1] for item in gates if item[0] >= start), reverse=True)
        if not eligible:
            continue
        carried = profile.carried_stock(start) if use_buffer else profile.upto(start - 1) + supply.initial_stock
        for end in ends:
            count = _count_at_least(eligible, end)
            if count == 0:
                continue
            cycle = profile.earliest_cycle_for(start, count, carried)
            best = max(best, cycle + end)
    return best


def _count_at_least(sorted_desc: list[int], threshold: int) -> int:
    """Return how many entries of a descending list are at least ``threshold``."""

    low, high = 0, len(sorted_desc)
    while low < high:
        mid = (low + high) // 2
        if sorted_desc[mid] >= threshold:
            low = mid + 1
        else:
            high = mid
    return low


def estimate(
    dag: CircuitDAG,
    supply: SupplyModel,
    model: str = "sccp",
    clifford_weight: int = 1,
    profile: SupplyProfile | None = None,
) -> float:
    """Return the predicted execution time under one cost model.

    The models form an information ladder, which is what the ablation study
    varies:

    ``deps_only``
        the dependency critical path, i.e. what a depth-oriented compiler sees.
    ``t_count_only``
        total magic states divided by the steady-state supply rate.
    ``deps_plus_count``
        the larger of the two above, plus production latency.
    ``deps_plus_throughput``
        SCCP with an unbounded buffer, so arrival timing matters but storage
        does not.
    ``sccp``
        the window bound, which uses the buffer cap to limit carried stock.
    ``sccp_plus``
        the window bound together with the fluid buffer term, so production
        wasted at a full buffer is charged. This is the model the
        resource-aware compiler minimises.
    """

    depth = logical_depth(dag, clifford_weight)
    states = t_count(dag)

    if model == "deps_only":
        return float(depth)
    if model == "t_count_only":
        return float(supply.production_latency + states / supply.rate)
    if model == "deps_plus_count":
        return float(max(depth, supply.production_latency + states / supply.rate))
    if model == "deps_plus_throughput":
        return float(
            sccp_bound(
                dag,
                supply,
                clifford_weight=clifford_weight,
                profile=profile,
                use_buffer=False,
            )
        )
    if model == "sccp":
        return float(
            sccp_bound(dag, supply, clifford_weight=clifford_weight, profile=profile)
        )
    if model == "sccp_plus":
        return sccp_plus(dag, supply, clifford_weight=clifford_weight, profile=profile)
    raise ValueError(f"unknown cost model {model!r}")


def static_selection_key(dag: CircuitDAG, objective: str, clifford_weight: int = 1) -> tuple:
    """Return the sort key a conventional static-metric compiler would use."""

    if objective == "t_depth":
        return (t_depth(dag), t_count(dag), logical_depth(dag, clifford_weight))
    if objective == "t_count":
        return (t_count(dag), t_depth(dag), logical_depth(dag, clifford_weight))
    if objective == "logical_depth":
        return (logical_depth(dag, clifford_weight), t_count(dag), t_depth(dag))
    raise ValueError(f"unknown static objective {objective!r}")


def layered_profile_estimate(
    dag: CircuitDAG,
    supply: SupplyModel,
    clifford_weight: int = 1,
    profile: SupplyProfile | None = None,
) -> int:
    """Return a dependency-gated fluid estimate of the execution time.

    This refines :func:`profile_estimate` with the observation that deferred
    demand is not fungible: a T gate whose predecessors have not run cannot
    consume a state even when one is sitting in the buffer. The circuit's
    unconstrained demand profile is therefore replayed one layer per cycle, and
    a layer only retires once every state it asks for has been delivered. A
    burst that the factories cannot cover in one cycle stalls the profile while
    the buffer keeps filling, which is exactly the situation in which
    production is lost to a full buffer.
    """

    demand = asap_t_demand(dag, clifford_weight)
    depth = logical_depth(dag, clifford_weight)
    if not demand:
        return depth

    total = t_count(dag)
    if profile is None:
        profile = SupplyProfile.build(supply, default_horizon(dag, supply, clifford_weight))

    last_layer = max(demand)
    stock = supply.initial_stock
    if not supply.unbounded_buffer:
        stock = min(stock, supply.buffer_capacity)

    layer = 0
    residual = 0
    served = 0
    cycle = 0
    limit = profile.horizon * 4 + 1024
    while served < total and cycle <= limit:
        cycle += 1
        stock += profile.upto(cycle) - profile.upto(cycle - 1)
        if not supply.unbounded_buffer and stock > supply.buffer_capacity:
            stock = supply.buffer_capacity
        if residual == 0 and layer < last_layer:
            layer += 1
            residual = demand.get(layer, 0)
        taken = min(residual, stock)
        stock -= taken
        served += taken
        residual -= taken

    return max(cycle, depth)


def profile_estimate(
    dag: CircuitDAG,
    supply: SupplyModel,
    clifford_weight: int = 1,
    profile: SupplyProfile | None = None,
) -> int:
    """Return a fluid supply/demand estimate of the execution time.

    The circuit is reduced to its unconstrained demand profile ``D(t)`` and
    matched against the arrival process ``S(t)`` by a one-dimensional
    recurrence on the buffer: unmet demand is carried forward as backlog, and
    production that arrives at a full buffer is lost. No dependency graph is
    traversed and no scheduling decision is made, so this stays a cost model
    rather than a simulation, but unlike :func:`sccp_bound` it charges for
    supply wasted during a lull. That is what makes it sensitive to demand
    *shape* and therefore to buffer capacity.
    """

    demand = asap_t_demand(dag, clifford_weight)
    if not demand:
        return logical_depth(dag, clifford_weight)

    total = t_count(dag)
    if profile is None:
        profile = SupplyProfile.build(supply, default_horizon(dag, supply, clifford_weight))

    last_demand_cycle = max(demand)
    stock = supply.initial_stock
    if not supply.unbounded_buffer:
        stock = min(stock, supply.buffer_capacity)

    backlog = 0
    served = 0
    cycle = 0
    limit = profile.horizon * 4 + 1024
    while served < total:
        cycle += 1
        if cycle > limit:
            break
        stock += profile.upto(cycle) - profile.upto(cycle - 1)
        if not supply.unbounded_buffer and stock > supply.buffer_capacity:
            stock = supply.buffer_capacity
        wanted = demand.get(cycle, 0) + backlog
        taken = min(wanted, stock)
        stock -= taken
        served += taken
        backlog = wanted - taken

    return max(cycle, last_demand_cycle, logical_depth(dag, clifford_weight))


def sccp_plus(
    dag: CircuitDAG,
    supply: SupplyModel,
    clifford_weight: int = 1,
    profile: SupplyProfile | None = None,
) -> float:
    """Return the selection cost model: the window bound plus the buffer term.

    :func:`sccp_bound` is a certified lower bound; :func:`profile_estimate`
    charges for production wasted at a full buffer but ignores dependency
    windows. Taking the larger of the two keeps each one's strength, at the
    price of no longer being a bound.

    Measured against simulation this is barely better than the window bound
    alone, because the fluid model reads demand off the *unconstrained*
    profile and therefore misses the overflow that only appears once the
    constraint itself has spread the demand out. Predicting that residual loss
    without simulating is the main open problem left by this study; see
    :func:`layered_profile_estimate` for an attempt that overshoots badly.
    """

    if profile is None:
        profile = SupplyProfile.build(supply, default_horizon(dag, supply, clifford_weight))
    window = sccp_bound(dag, supply, clifford_weight=clifford_weight, profile=profile)
    fluid = profile_estimate(dag, supply, clifford_weight=clifford_weight, profile=profile)
    return float(max(window, fluid))
