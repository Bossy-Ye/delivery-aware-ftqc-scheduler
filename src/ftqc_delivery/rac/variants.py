"""Implementation variants, decision sites, and the program space they span.

A conventional compiler pipeline commits to one implementation of each
high-level operation, usually by minimising a static metric such as T-depth or
T-count. This module makes that commitment explicit and deferrable: a program
is a graph of *decision sites*, each site offers a set of semantically
equivalent *variants*, and an *assignment* picks one variant per site. Only
when an assignment is fixed does a concrete circuit DAG exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Iterable, Iterator, Sequence

from ftqc_delivery.dag.graph import CircuitDAG


@dataclass
class FragmentBuilder:
    """Incrementally build a sub-circuit for one decision site."""

    prefix: str
    _nodes: list[tuple[str, str]] = field(default_factory=list)
    _edges: list[tuple[str, str]] = field(default_factory=list)
    _counter: int = 0

    def add(self, op_type: str, predecessors: Iterable[str] = ()) -> str:
        """Add one operation and return its local node id."""

        node_id = f"{self.prefix}n{self._counter:05d}"
        self._counter += 1
        self._nodes.append((node_id, op_type))
        for predecessor in predecessors:
            self._edges.append((predecessor, node_id))
        return node_id

    def add_layer(
        self,
        op_type: str,
        width: int,
        predecessors: Iterable[str] = (),
    ) -> list[str]:
        """Add ``width`` parallel operations sharing the same predecessors."""

        predecessors = list(predecessors)
        return [self.add(op_type, predecessors) for _ in range(width)]

    def finish(self, ancillas: int = 0, notes: str = "") -> "Fragment":
        """Return the immutable fragment built so far."""

        return Fragment(
            nodes=tuple(self._nodes),
            edges=tuple(self._edges),
            ancillas=ancillas,
            notes=notes,
        )


@dataclass(frozen=True)
class Fragment:
    """An immutable sub-circuit with derived entry and exit boundaries."""

    nodes: tuple[tuple[str, str], ...]
    edges: tuple[tuple[str, str], ...]
    ancillas: int = 0
    notes: str = ""

    @property
    def entries(self) -> tuple[str, ...]:
        """Return nodes with no predecessor inside the fragment."""

        has_pred = {successor for _, successor in self.edges}
        return tuple(node_id for node_id, _ in self.nodes if node_id not in has_pred)

    @property
    def exits(self) -> tuple[str, ...]:
        """Return nodes with no successor inside the fragment."""

        has_succ = {predecessor for predecessor, _ in self.edges}
        return tuple(node_id for node_id, _ in self.nodes if node_id not in has_succ)

    def to_dag(self, name: str = "fragment") -> CircuitDAG:
        """Return this fragment as a standalone DAG."""

        dag = CircuitDAG(name=name)
        for node_id, op_type in self.nodes:
            dag.add_node(node_id, op_type)
        dag.add_edges_from(self.edges)
        return dag


@dataclass(frozen=True)
class Variant:
    """One semantically equivalent implementation of a decision site."""

    name: str
    family: str
    fragment: Fragment
    notes: str = ""


@dataclass(frozen=True)
class Site:
    """A point in the program where the compiler must choose an implementation."""

    site_id: str
    family: str
    variants: tuple[Variant, ...]

    def __post_init__(self) -> None:
        if not self.variants:
            raise ValueError(f"site {self.site_id!r} has no variants")
        names = [variant.name for variant in self.variants]
        if len(set(names)) != len(names):
            raise ValueError(f"site {self.site_id!r} has duplicate variant names")

    def variant(self, name: str) -> Variant:
        """Return the named variant."""

        for candidate in self.variants:
            if candidate.name == name:
                return candidate
        raise KeyError(f"site {self.site_id!r} has no variant {name!r}")

    @property
    def variant_names(self) -> tuple[str, ...]:
        """Return the variant names in declaration order."""

        return tuple(variant.name for variant in self.variants)


Assignment = dict[str, str]


@dataclass(frozen=True)
class ProgramSpace:
    """A program as a DAG of decision sites plus the variants at each site."""

    name: str
    sites: tuple[Site, ...]
    edges: tuple[tuple[str, str], ...] = ()
    meta: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        ids = [site.site_id for site in self.sites]
        if len(set(ids)) != len(ids):
            raise ValueError(f"program {self.name!r} has duplicate site ids")
        known = set(ids)
        for predecessor, successor in self.edges:
            if predecessor not in known or successor not in known:
                raise ValueError(
                    f"program {self.name!r} has an edge over unknown sites: "
                    f"{predecessor!r} -> {successor!r}"
                )

    def site(self, site_id: str) -> Site:
        """Return the named site."""

        for candidate in self.sites:
            if candidate.site_id == site_id:
                return candidate
        raise KeyError(f"program {self.name!r} has no site {site_id!r}")

    @property
    def num_assignments(self) -> int:
        """Return the size of the assignment space."""

        total = 1
        for site in self.sites:
            total *= len(site.variants)
        return total

    def default_assignment(self) -> Assignment:
        """Return the assignment picking each site's first declared variant."""

        return {site.site_id: site.variants[0].name for site in self.sites}

    def iter_assignments(self) -> Iterator[Assignment]:
        """Iterate over every assignment in the space, in deterministic order."""

        site_ids = [site.site_id for site in self.sites]
        options = [site.variant_names for site in self.sites]
        for combination in product(*options):
            yield dict(zip(site_ids, combination))

    def instantiate(self, assignment: Assignment) -> CircuitDAG:
        """Return the concrete circuit DAG produced by ``assignment``."""

        missing = {site.site_id for site in self.sites} - set(assignment)
        if missing:
            raise ValueError(f"assignment omits sites: {sorted(missing)[:8]}")

        dag = CircuitDAG(name=f"{self.name}")
        entries: dict[str, list[str]] = {}
        exits: dict[str, list[str]] = {}

        for site in self.sites:
            variant = site.variant(assignment[site.site_id])
            scope = f"{site.site_id}__{variant.name}__"
            for node_id, op_type in variant.fragment.nodes:
                dag.add_node(scope + node_id, op_type)
            for predecessor, successor in variant.fragment.edges:
                dag.add_edge(scope + predecessor, scope + successor)
            entries[site.site_id] = [scope + node_id for node_id in variant.fragment.entries]
            exits[site.site_id] = [scope + node_id for node_id in variant.fragment.exits]

        for predecessor, successor in self.edges:
            for tail_node in exits[predecessor]:
                for head_node in entries[successor]:
                    dag.add_edge(tail_node, head_node)

        return dag

    def ancillas(self, assignment: Assignment) -> int:
        """Return the total ancilla footprint claimed by an assignment."""

        return sum(
            self.site(site_id).variant(variant_name).fragment.ancillas
            for site_id, variant_name in assignment.items()
        )

    def describe(self) -> str:
        """Return a compact description for tables."""

        families = sorted({site.family for site in self.sites})
        return f"{self.name} sites={len(self.sites)} families={'+'.join(families)}"


def chain_edges(site_ids: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Return edges putting the given sites in a serial chain."""

    return tuple(zip(site_ids[:-1], site_ids[1:]))
