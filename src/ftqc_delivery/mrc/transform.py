"""Semantics-preserving transformations that change only *when* work may run.

Two transformations, deliberately opposite in what they do to parallelism, so
that a makespan change can be attributed rather than guessed at.

``commuting``
    Conventional lowering makes one gate depend on the previous gate touching
    any of its lines. That is stricter than the physics: a control line is
    read, not written, and two gates that only read a line commute exactly.
    Building the dependency graph from reads and writes instead of from bare
    contact removes those false edges. The gate list is untouched, so the
    T-count, the operation multiset and the logical computation are identical;
    only the set of legal orderings grows.

``pacing``
    The opposite move. Starting from a graph, chain the magic-consuming sites
    so that at most ``k`` of them may ever be in flight. Adding edges to a
    directed acyclic graph can only remove orderings, never add one, so
    semantics are preserved for free. Depth grows. If a makespan still falls,
    the cause cannot be reduced depth or reduced work; it can only be that
    demand met supply more evenly.

Why the commuting graph is sound
--------------------------------
Two gates that the graph leaves unordered never write a line the other
touches. For the gates modelled here that implies they commute exactly: an
X-type gate is ``sum_x |x><x|_controls (X^f(x))_target`` and a diagonal gate is
``sum_x c(x) |x><x|``, so two of them sharing only read lines are both block
diagonal in the same basis and act on disjoint targets. Every pair the graph
leaves unordered therefore commutes, and any two linear extensions of the
graph differ by a sequence of adjacent transpositions of commuting gates.
They denote the same unitary.

:func:`check_pairwise_commutation` verifies the premise directly on a graph,
and :func:`random_linear_extension` produces orderings for the numerical
checks that confirm it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ftqc_delivery.rac.variants import ProgramSpace

from .execution import resource_counts
from .extract import GateRecord, canonical_name

#: Gates that write exactly their last line and read the rest.
X_TYPE = {"x", "cnot", "cx", "toffoli", "ccx", "ccnot", "mcx"}
#: Gates diagonal in the computational basis: every line is read, none written.
DIAGONAL = {
    "z", "s", "sdg", "t", "tdg", "cz", "ccz", "rz", "zpowgate", "phase", "p",
    "cphase", "cp", "rzviaphasegradient", "zpowconstviaphasegradient",
}


def reads_writes(gate: GateRecord) -> tuple[frozenset[int], frozenset[int]]:
    """Return the lines this gate reads and the lines it writes.

    Anything not recognised is treated as writing every line it touches, so an
    unmodelled gate can only make the graph stricter, never looser.
    """

    name = canonical_name(gate.name)
    if name in DIAGONAL:
        return frozenset(gate.qubits), frozenset()
    if name in X_TYPE and gate.qubits:
        return frozenset(gate.qubits[:-1]), frozenset(gate.qubits[-1:])
    return frozenset(), frozenset(gate.qubits)


def conventional_edges(gates: list[GateRecord]) -> list[tuple[int, int]]:
    """Return the edges of the lowering that depends on bare line contact."""

    edges: list[tuple[int, int]] = []
    last: dict[int, int] = {}
    for index, gate in enumerate(gates):
        for predecessor in sorted({last[q] for q in gate.qubits if q in last}):
            edges.append((predecessor, index))
        for q in gate.qubits:
            last[q] = index
    return edges


def commuting_edges(gates: list[GateRecord]) -> list[tuple[int, int]]:
    """Return the edges of the read/write lowering.

    Read-after-write and write-after-write order two gates, and so does
    write-after-read, which is the anti-dependency that keeps a line's value
    alive until its last reader. Read-after-read is not an edge.
    """

    edges: list[tuple[int, int]] = []
    last_write: dict[int, int] = {}
    reads_since: dict[int, set[int]] = {}
    for index, gate in enumerate(gates):
        reads, writes = reads_writes(gate)
        predecessors: set[int] = set()
        for q in reads | writes:
            if q in last_write:
                predecessors.add(last_write[q])
        for q in writes:
            predecessors |= reads_since.get(q, set())
        for predecessor in sorted(predecessors):
            edges.append((predecessor, index))
        for q in writes:
            last_write[q] = index
            reads_since[q] = set()
        for q in reads:
            reads_since.setdefault(q, set()).add(index)
    return edges


# ---------------------------------------------------------------------------
# Soundness checks
# ---------------------------------------------------------------------------


def _reachability(count: int, edges: list[tuple[int, int]]) -> list[set[int]]:
    """Return, for each node, everything reachable from it."""

    successors: dict[int, list[int]] = {i: [] for i in range(count)}
    for source, target in edges:
        successors[source].append(target)
    reach: list[set[int]] = [set() for _ in range(count)]
    for node in range(count - 1, -1, -1):
        collected: set[int] = set()
        for nxt in successors[node]:
            collected.add(nxt)
            collected |= reach[nxt]
        reach[node] = collected
    return reach


def check_pairwise_commutation(
    gates: list[GateRecord], edges: list[tuple[int, int]]
) -> tuple[bool, list[tuple[int, int]]]:
    """Return whether every unordered pair of gates commutes, and the offenders.

    Two gates commute for this purpose when neither writes a line the other
    reads or writes. Checking every unordered pair is the premise of the
    argument that all linear extensions denote the same unitary, so it is
    checked rather than assumed.
    """

    reach = _reachability(len(gates), edges)
    profiles = [reads_writes(gate) for gate in gates]
    offenders: list[tuple[int, int]] = []
    for i in range(len(gates)):
        for j in range(i + 1, len(gates)):
            if j in reach[i] or i in reach[j]:
                continue
            reads_i, writes_i = profiles[i]
            reads_j, writes_j = profiles[j]
            if writes_i & (reads_j | writes_j) or writes_j & (reads_i | writes_i):
                offenders.append((i, j))
                if len(offenders) >= 8:
                    return False, offenders
    return not offenders, offenders


def random_linear_extension(
    count: int, edges: list[tuple[int, int]], seed: int
) -> list[int]:
    """Return a random topological order of the graph."""

    rng = random.Random(seed)
    indegree = [0] * count
    successors: dict[int, list[int]] = {i: [] for i in range(count)}
    for source, target in edges:
        successors[source].append(target)
        indegree[target] += 1
    ready = [i for i in range(count) if indegree[i] == 0]
    order: list[int] = []
    while ready:
        choice = rng.randrange(len(ready))
        ready[choice], ready[-1] = ready[-1], ready[choice]
        node = ready.pop()
        order.append(node)
        for nxt in successors[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if len(order) != count:
        raise ValueError("graph has a cycle")
    return order


# ---------------------------------------------------------------------------
# Rebuilding a program under new edges
# ---------------------------------------------------------------------------


def _site_id(index: int) -> str:
    return f"g{index:05d}"


def reshape(program: ProgramSpace, edges: list[tuple[int, int]]) -> ProgramSpace:
    """Return ``program`` with its dependency edges replaced.

    The sites, and therefore every implementation choice, resource count and
    gate, are carried over untouched. Only the edges change.
    """

    index_of = {site.site_id: i for i, site in enumerate(program.sites)}
    keep = [
        (_site_id(a), _site_id(b))
        for a, b in edges
        if _site_id(a) in index_of and _site_id(b) in index_of
    ]
    return ProgramSpace(
        name=program.name, sites=program.sites, edges=tuple(keep), meta=program.meta
    )


def consuming_site_ids(program: ProgramSpace) -> list[str]:
    """Return the sites that consume magic states, in program order."""

    out = []
    for site in program.sites:
        if any(
            resource_counts(variant.fragment.to_dag(variant.name))
            for variant in site.variants
        ):
            out.append(site.site_id)
    return out


def pace(program: ProgramSpace, width: int) -> ProgramSpace:
    """Return ``program`` with magic-consuming sites paced ``width`` at a time.

    Site ``i`` of the consuming sequence is made to wait for site ``i - width``,
    so at most ``width`` of them can ever be in flight. Only edges are added,
    and adding an edge to an acyclic graph removes orderings rather than
    creating them, so every schedule of the result was already a legal
    schedule of the input. Depth grows; the work does not change.
    """

    if width < 1:
        raise ValueError("width must be at least 1")
    consuming = consuming_site_ids(program)
    extra = [
        (consuming[i - width], consuming[i]) for i in range(width, len(consuming))
    ]
    existing = set(program.edges)
    edges = list(program.edges) + [e for e in extra if e not in existing]
    return ProgramSpace(
        name=program.name, sites=program.sites, edges=tuple(edges), meta=program.meta
    )


@dataclass(frozen=True)
class DemandTrace:
    """Per-stage magic-state demand of a program under a fixed assignment."""

    per_stage: tuple[dict[str, int], ...]

    @property
    def peak(self) -> float:
        return max((sum(stage.values()) for stage in self.per_stage), default=0)

    @property
    def total(self) -> float:
        return sum(sum(stage.values()) for stage in self.per_stage)

    def burstiness(self) -> float:
        """Return the coefficient of variation of per-stage demand."""

        loads = [float(sum(stage.values())) for stage in self.per_stage]
        if not loads:
            return 0.0
        mean = sum(loads) / len(loads)
        if mean <= 0:
            return 0.0
        variance = sum((x - mean) ** 2 for x in loads) / len(loads)
        return variance**0.5 / mean
