"""Placement of dynamic programs on networked QPUs, static and branch-aware.

The model is deliberately the standard one from the distributed-compilation
literature, so that nothing here is tuned to favour branch awareness:

* a remote two-qubit operation between QPUs at graph distance ``d`` consumes
  ``d`` EPR pairs, one per link, by entanglement swapping, and ``d`` units of
  link latency; a local operation consumes nothing;
* moving a qubit to another QPU by teleportation consumes ``d`` EPR pairs;
* each QPU holds at most ``capacity`` qubits.

A dynamic program is a sequence of segments, each either unconditional work
or a measurement-conditioned region whose branches carry probabilities.

Three compilation models are compared under the *same* true branch
probabilities:

``flat`` (Case 1)
    One placement minimising the cost of the program with every branch
    flattened in, each conditional interaction weighted 1. The strongest
    control-flow-insensitive compiler: it sees every branch but treats each
    as always executed.
``expected`` (Case 2)
    One placement minimising the expected cost.
``reconfigure`` (Case 3)
    A placement before each region and one per branch after it, every moved
    qubit charged by teleportation.

``blind`` reproduces what the audited compilers actually do, weighting branch
interactions zero. It is a reference point, not a baseline for the decision.
"""

from __future__ import annotations

import itertools
import random
from collections import deque
from dataclasses import dataclass, field

import numpy as np

Pair = tuple[int, int]


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Network:
    """QPUs, their capacities, and the links between them."""

    n_qpus: int
    capacity: int
    topology: str
    links: tuple[tuple[int, int], ...]
    distance: np.ndarray
    routes: dict

    def label(self) -> str:
        return f"{self.topology}{self.n_qpus}x{self.capacity}"


def _links(n: int, topology: str) -> list[tuple[int, int]]:
    if topology == "line":
        return [(i, i + 1) for i in range(n - 1)]
    if topology == "ring":
        return [(i, (i + 1) % n) for i in range(n)] if n > 2 else [(0, 1)]
    if topology == "full":
        return [(i, j) for i in range(n) for j in range(i + 1, n)]
    if topology == "grid":
        side = int(round(n**0.5))
        if side * side != n:
            raise ValueError("grid needs a square number of QPUs")
        out = []
        for r in range(side):
            for c in range(side):
                i = r * side + c
                if c + 1 < side:
                    out.append((i, i + 1))
                if r + 1 < side:
                    out.append((i, i + side))
        return out
    raise ValueError(f"unknown topology {topology!r}")


def build_network(n_qpus: int, capacity: int, topology: str) -> Network:
    """Return a network with all-pairs hop distances and one shortest route each."""

    # Links are stored with the smaller QPU first, the same orientation the
    # routes use, so a ring's wrap-around link is (0, n-1), not (n-1, 0).
    links = sorted({(min(a, b), max(a, b)) for a, b in _links(n_qpus, topology)})
    adjacency = {i: [] for i in range(n_qpus)}
    for a, b in links:
        adjacency[a].append(b)
        adjacency[b].append(a)
    distance = np.zeros((n_qpus, n_qpus), dtype=np.int64)
    routes: dict = {}
    for source in range(n_qpus):
        parent = {source: None}
        queue = deque([source])
        while queue:
            node = queue.popleft()
            for nxt in sorted(adjacency[node]):
                if nxt not in parent:
                    parent[nxt] = node
                    queue.append(nxt)
        for target in range(n_qpus):
            path, node = [], target
            while parent[node] is not None:
                path.append((min(node, parent[node]), max(node, parent[node])))
                node = parent[node]
            distance[source, target] = len(path)
            routes[(source, target)] = tuple(path)
    return Network(n_qpus, capacity, topology, tuple(links), distance, routes)


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """Unconditional work, or a region whose branches carry probabilities."""

    pairs: list[Pair] = field(default_factory=list)
    branches: list[tuple[float, list[Pair]]] | None = None

    @property
    def conditional(self) -> bool:
        return self.branches is not None


@dataclass
class DynamicProgram:
    """A program as a sequence of segments over integer qubits."""

    name: str
    n_qubits: int
    segments: list[Segment]
    source: str = ""
    note: str = ""

    def with_probability(self, p: float) -> "DynamicProgram":
        """Return a copy whose two-way regions take their first branch with ``p``."""

        segments = []
        for segment in self.segments:
            if segment.conditional and len(segment.branches) == 2:
                (_, a), (_, b) = segment.branches
                segments.append(Segment(branches=[(p, a), (1.0 - p, b)]))
            else:
                segments.append(segment)
        return DynamicProgram(self.name, self.n_qubits, segments, self.source, self.note)


def weights(program: DynamicProgram, mode: str) -> dict[Pair, float]:
    """Return the interaction weights a compiler of the given kind optimises."""

    out: dict[Pair, float] = {}

    def add(pair: Pair, w: float) -> None:
        a, b = pair
        if a == b or w == 0:
            return
        key = (a, b) if a < b else (b, a)
        out[key] = out.get(key, 0.0) + w

    for segment in program.segments:
        if not segment.conditional:
            for pair in segment.pairs:
                add(pair, 1.0)
            continue
        for probability, pairs in segment.branches:
            w = {"flat": 1.0, "expected": probability, "blind": 0.0}[mode]
            for pair in pairs:
                add(pair, w)
    return out


# ---------------------------------------------------------------------------
# Cost of a placement
# ---------------------------------------------------------------------------


def evaluate(program: DynamicProgram, placement: np.ndarray, network: Network) -> dict[str, float]:
    """Return expected and worst-case communication of one fixed placement."""

    D = network.distance
    link_load: dict[tuple[int, int], float] = {link: 0.0 for link in network.links}

    def cost(pairs: list[Pair], weight: float) -> tuple[float, float]:
        epr = remote = 0.0
        for a, b in pairs:
            qa, qb = placement[a], placement[b]
            d = D[qa, qb]
            if d:
                epr += d
                remote += 1
                for link in network.routes[(qa, qb)]:
                    link_load[link] += weight
        return epr, remote

    expected_epr = expected_remote = worst_epr = worst_remote = 0.0
    for segment in program.segments:
        if not segment.conditional:
            e, r = cost(segment.pairs, 1.0)
            expected_epr += e
            expected_remote += r
            worst_epr += e
            worst_remote += r
            continue
        branch_costs = []
        for probability, pairs in segment.branches:
            e, r = cost(pairs, probability)
            expected_epr += probability * e
            expected_remote += probability * r
            branch_costs.append((e, r))
        worst_epr += max(e for e, _ in branch_costs)
        worst_remote += max(r for _, r in branch_costs)
    return {
        "expected_epr": expected_epr,
        "worst_epr": worst_epr,
        "expected_remote": expected_remote,
        "worst_remote": worst_remote,
        "max_link_load": max(link_load.values(), default=0.0),
    }


def weighted_cost(w: dict[Pair, float], placement: np.ndarray, D: np.ndarray) -> float:
    return float(sum(weight * D[placement[a], placement[b]] for (a, b), weight in w.items()))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _feasible_assignments(n: int, k: int, capacity: int):
    """Yield every assignment of n qubits to k QPUs within capacity."""

    for assignment in itertools.product(range(k), repeat=n):
        counts = np.bincount(assignment, minlength=k)
        if counts.max() <= capacity:
            yield assignment


def exhaustive_optimum(w: dict[Pair, float], n: int, network: Network, limit: int = 3_000_000):
    """Return (best cost, every optimal placement), or None if the space is too big."""

    k, cap = network.n_qpus, network.capacity
    if k**n > limit:
        return None
    D = network.distance
    all_assignments = np.array(list(itertools.product(range(k), repeat=n)), dtype=np.int64)
    counts = np.stack([(all_assignments == q).sum(axis=1) for q in range(k)], axis=1)
    feasible = all_assignments[(counts <= cap).all(axis=1)]
    if len(feasible) == 0:
        raise ValueError("no feasible placement")
    total = np.zeros(len(feasible))
    for (a, b), weight in w.items():
        total += weight * D[feasible[:, a], feasible[:, b]]
    best = total.min()
    optimal = feasible[np.isclose(total, best)]
    return float(best), optimal


def local_search(
    w: dict[Pair, float], n: int, network: Network, seed: int = 20260924, restarts: int = 24
) -> tuple[float, np.ndarray]:
    """Return the best placement found by restarted swap-and-move descent.

    Moves are a qubit to a QPU with spare capacity, or a swap of two qubits
    on different QPUs; first improvement is taken. Deterministic for a seed.
    """

    rng = random.Random(seed)
    k, cap = network.n_qpus, network.capacity
    D = network.distance
    neighbours: dict[int, list[tuple[int, float]]] = {i: [] for i in range(n)}
    for (a, b), weight in w.items():
        neighbours[a].append((b, weight))
        neighbours[b].append((a, weight))

    def delta_move(p: np.ndarray, q: int, target: int) -> float:
        before = sum(weight * D[p[q], p[o]] for o, weight in neighbours[q])
        after = sum(weight * D[target, p[o]] for o, weight in neighbours[q] if o != q)
        return after - before

    best_cost, best = float("inf"), None
    for restart in range(restarts):
        order = list(range(n))
        rng.shuffle(order)
        p = np.zeros(n, dtype=np.int64)
        fill = [0] * k
        for i, q in enumerate(order):
            target = min(range(k), key=lambda x: (fill[x] >= cap, rng.random()))
            p[q] = target
            fill[target] += 1
        improved = True
        while improved:
            improved = False
            for q in range(n):
                for target in range(k):
                    if target == p[q] or fill[target] >= cap:
                        continue
                    if delta_move(p, q, target) < -1e-12:
                        fill[p[q]] -= 1
                        p[q] = target
                        fill[target] += 1
                        improved = True
            for q1 in range(n):
                for q2 in range(q1 + 1, n):
                    if p[q1] == p[q2]:
                        continue
                    a, b = p[q1], p[q2]
                    d = delta_move(p, q1, b)
                    p[q1] = b
                    d += delta_move(p, q2, a)
                    p[q1] = a
                    if d < -1e-12:
                        p[q1], p[q2] = b, a
                        improved = True
        c = weighted_cost(w, p, D)
        if c < best_cost - 1e-12:
            best_cost, best = c, p.copy()
    return best_cost, best


def optimise(w: dict[Pair, float], n: int, network: Network, seed: int = 20260924):
    """Return (cost, placement, method), exact when the space allows."""

    exact = exhaustive_optimum(w, n, network)
    if exact is not None:
        cost, optimal = exact
        return cost, optimal[0], "exhaustive", optimal
    cost, placement = local_search(w, n, network, seed=seed)
    return cost, placement, "local_search", None


# ---------------------------------------------------------------------------
# Case 3: branch-dependent placement, reconfiguration charged
# ---------------------------------------------------------------------------


def move_cost(before: np.ndarray, after: np.ndarray, D: np.ndarray) -> float:
    """Return EPR pairs to teleport every qubit whose QPU changes."""

    return float(sum(D[a, b] for a, b in zip(before, after) if a != b))


def feasible_placements(n: int, network: Network, limit: int = 4000) -> np.ndarray | None:
    """Return every feasible placement, or None when there are too many."""

    k, cap = network.n_qpus, network.capacity
    if k**n > 5_000_000:
        return None
    grid = np.array(list(itertools.product(range(k), repeat=n)), dtype=np.int64)
    counts = np.stack([(grid == q).sum(axis=1) for q in range(k)], axis=1)
    feasible = grid[(counts <= cap).all(axis=1)]
    return feasible if len(feasible) <= limit else None


def _segment_cost_vector(pairs: list[Pair], F: np.ndarray, D: np.ndarray) -> np.ndarray:
    out = np.zeros(len(F))
    for a, b in pairs:
        out += D[F[:, a], F[:, b]]
    return out


def reconfiguration_oracle(program: DynamicProgram, network: Network) -> dict | None:
    """Return the exact optimum when branches may re-place qubits, or None.

    Placements may change only at branch points: after a measurement each
    branch may teleport qubits to a new placement, paying the hop distance for
    every qubit moved, and everything after the branch runs from wherever that
    branch ended up. The initial placement is free. The optimum over all such
    strategies is computed exactly by dynamic programming backwards over the
    segments, with the state being the current placement:

    * after the last segment the cost-to-go is zero;
    * an unconditional segment adds its cost under the current placement;
    * a conditional segment takes, for each branch, the cheapest of moving to
      any feasible placement, paying the move, the branch and the cost-to-go
      from there, weighted by the branch probability.

    Returns None when the feasible placements are too many to enumerate.
    """

    F = feasible_placements(program.n_qubits, network)
    if F is None:
        return None
    D = network.distance
    # move[i, j]: EPR pairs to teleport from placement i to placement j.
    move = np.zeros((len(F), len(F)))
    for q in range(program.n_qubits):
        move += D[F[:, q][:, None], F[:, q][None, :]]

    value = np.zeros(len(F))
    choice_moves = np.zeros(len(F))
    for segment in reversed(program.segments):
        if not segment.conditional:
            value = value + _segment_cost_vector(segment.pairs, F, D)
            continue
        new_value = np.zeros(len(F))
        new_moves = np.zeros(len(F))
        for probability, pairs in segment.branches:
            reach = _segment_cost_vector(pairs, F, D) + value
            total = move + reach[None, :]
            best = total.argmin(axis=1)
            new_value += probability * total[np.arange(len(F)), best]
            new_moves += probability * (move[np.arange(len(F)), best] + choice_moves[best])
        value, choice_moves = new_value, new_moves
    start = int(value.argmin())
    return {
        "expected_epr": float(value[start]),
        "reconfiguration_epr": float(choice_moves[start]),
        "initial_placement": F[start],
        "feasible_placements": len(F),
    }
