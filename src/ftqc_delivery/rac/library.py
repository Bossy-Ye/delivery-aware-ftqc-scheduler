"""A library of semantically equivalent fault-tolerant implementations.

Every family in this module offers several implementations of the *same*
logical operation that differ in T-count, T-depth, and the shape of the magic
state demand they place on the machine over time. The parameters are stylised
but calibrated to the published fault-tolerant literature:

* ``and_gidney`` -- the measurement-based AND of Gidney (2018) costs 4 T states
  in 2 layers and uncomputes with Clifford operations and measurement only.
* ``toffoli_d3`` / ``toffoli_d2`` / ``toffoli_d1`` -- the ancilla/T-depth
  family of Amy, Maslov, Mosca and Roetteler (2013) and Selinger (2013): a
  Toffoli costs 7 T states and its T-depth can be lowered from 3 to 1 by
  spending 0, 1 or 4 ancillas, which forces all 7 states to be consumed in a
  single layer.
* the adder family interpolates between a ripple-carry adder (about ``n`` AND
  gates on a serial carry chain) and a carry-lookahead adder (about ``2n`` AND
  gates on a prefix tree of depth ``O(log n)``), through the standard blocked
  designs in between.
* the rotation family interpolates between sequential Ross-Selinger style
  synthesis and ancilla-assisted parallel synthesis, which lowers T-depth
  logarithmically at the price of extra T gates.

The point of the library is not to reproduce any single published circuit
exactly. It is to span the space of choices a fault-tolerant compiler actually
faces, with the T-count/T-depth/burstiness trade-offs that the literature
reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log2

from .variants import Fragment, FragmentBuilder, Variant


@dataclass(frozen=True)
class AndImplementation:
    """One fault-tolerant implementation of a logical AND / Toffoli."""

    name: str
    t_layers: tuple[int, ...]
    ancillas: int
    clifford_layers_per_t_layer: int = 1
    citation: str = ""

    @property
    def t_count(self) -> int:
        """Return the number of magic states consumed."""

        return sum(self.t_layers)

    @property
    def t_depth(self) -> int:
        """Return the number of sequential T layers."""

        return len(self.t_layers)

    @property
    def peak_demand(self) -> int:
        """Return the largest number of states requested in one layer."""

        return max(self.t_layers)


AND_GIDNEY = AndImplementation(
    name="and_gidney",
    t_layers=(2, 2),
    ancillas=1,
    citation="Gidney 2018, measurement-based AND, 4 T, free uncomputation",
)
TOFFOLI_D3 = AndImplementation(
    name="toffoli_d3",
    t_layers=(3, 3, 1),
    ancillas=0,
    citation="Amy-Maslov-Mosca-Roetteler 2013, T-count 7, T-depth 3, no ancilla",
)
TOFFOLI_D2 = AndImplementation(
    name="toffoli_d2",
    t_layers=(4, 3),
    ancillas=1,
    citation="Selinger 2013, T-count 7, T-depth 2, 1 ancilla",
)
TOFFOLI_D1 = AndImplementation(
    name="toffoli_d1",
    t_layers=(7,),
    ancillas=4,
    citation="Selinger 2013, T-count 7, T-depth 1, 4 ancillas",
)

AND_IMPLEMENTATIONS = (AND_GIDNEY, TOFFOLI_D3, TOFFOLI_D2, TOFFOLI_D1)


def _emit_and(
    builder: FragmentBuilder,
    implementation: AndImplementation,
    predecessors: list[str],
) -> str:
    """Emit one AND gate and return the node that carries its result."""

    frontier = list(predecessors)
    for layer_width in implementation.t_layers:
        for _ in range(implementation.clifford_layers_per_t_layer):
            frontier = [builder.add("Clifford", frontier)]
        frontier = builder.add_layer("T", layer_width, frontier)
    return builder.add("Clifford", frontier)


def _prefix_tree_levels(leaves: int) -> list[int]:
    """Return AND counts per level of a Brent-Kung style prefix computation.

    The forward sweep halves the active carries at each level and the backward
    sweep fills in the skipped positions, which reproduces the standard
    ``2m - 2`` operation count and ``2 log2(m)`` depth of a quantum
    carry-lookahead adder.
    """

    if leaves <= 1:
        return []
    forward: list[int] = []
    active = leaves
    while active > 1:
        active = active // 2
        forward.append(active)
    backward = [count for count in reversed(forward[:-1])]
    return [count for count in forward + backward if count > 0]


def make_and_variants(
    prefix: str,
    implementations: tuple[AndImplementation, ...] = AND_IMPLEMENTATIONS,
) -> tuple[Variant, ...]:
    """Return the variants of a single logical AND / Toffoli site."""

    variants: list[Variant] = []
    for implementation in implementations:
        builder = FragmentBuilder(prefix=f"{prefix}_{implementation.name}_")
        source = builder.add("Clifford")
        result = _emit_and(builder, implementation, [source])
        builder.add("Clifford", [result])
        variants.append(
            Variant(
                name=implementation.name,
                family="and",
                fragment=builder.finish(
                    ancillas=implementation.ancillas,
                    notes=implementation.citation,
                ),
                notes=implementation.citation,
            )
        )
    return tuple(variants)


def build_blocked_adder(
    width: int,
    block_size: int,
    implementation: AndImplementation = AND_GIDNEY,
    prefix: str = "add_",
) -> Fragment:
    """Return a ``width``-bit adder whose carry chain is cut into blocks.

    ``block_size >= width`` gives a pure ripple-carry adder: one serial chain
    of ``width - 1`` AND gates, minimum AND count, maximum depth, and a demand
    profile that never exceeds one AND at a time.

    Smaller blocks give the standard carry-select structure: each block
    speculatively computes its local carry chain in parallel with every other
    block, a Brent-Kung prefix tree of depth ``2 log2(blocks)`` resolves the
    inter-block carries, and a Clifford selection commits the right branch.
    That costs about ``2 * width`` AND gates instead of ``width``, cuts the
    depth to ``block_size + 2 log2(blocks)``, and asks for up to
    ``2 * blocks`` AND gates simultaneously. ``block_size == 1`` degenerates to
    a pure carry-lookahead adder: a prefix tree over every bit.
    """

    if width < 2:
        raise ValueError("width must be at least 2")
    if block_size < 1:
        raise ValueError("block_size must be at least 1")

    builder = FragmentBuilder(prefix=prefix)
    source = builder.add("Clifford")

    if block_size >= width:
        frontier = source
        for _ in range(width - 1):
            frontier = _emit_and(builder, implementation, [frontier])
        builder.add("Clifford", [frontier])
        return builder.finish(
            ancillas=implementation.ancillas,
            notes=f"ripple-carry, {width - 1} AND on a serial carry chain",
        )

    num_blocks = ceil(width / block_size)
    local_carries: list[str] = []
    speculative: list[str] = []
    for _ in range(num_blocks):
        for sink in (local_carries, speculative):
            frontier = source
            for _ in range(block_size - 1):
                frontier = _emit_and(builder, implementation, [frontier])
            sink.append(frontier)

    frontier_nodes = local_carries or [source]
    for level_width in _prefix_tree_levels(num_blocks):
        joint = builder.add("Clifford", sorted(set(frontier_nodes)))
        frontier_nodes = [
            _emit_and(builder, implementation, [joint]) for _ in range(level_width)
        ]
    builder.add("Clifford", sorted(set(frontier_nodes + speculative)))

    return builder.finish(
        ancillas=implementation.ancillas * max(1, 2 * num_blocks) + num_blocks,
        notes=(
            f"carry-select adder, block={block_size}, blocks={num_blocks}, "
            f"prefix levels={len(_prefix_tree_levels(num_blocks))}"
        ),
    )


def adder_block_sizes(width: int) -> tuple[int, ...]:
    """Return the block sizes spanning ripple to lookahead for a given width."""

    sizes = [width]
    size = max(2, width // 2)
    while size > 1:
        if size not in sizes:
            sizes.append(size)
        size //= 2
    sizes.append(1)
    return tuple(sorted(set(sizes), reverse=True))


def make_adder_variants(
    prefix: str,
    width: int,
    implementation: AndImplementation = AND_GIDNEY,
    block_sizes: tuple[int, ...] | None = None,
) -> tuple[Variant, ...]:
    """Return the ripple-to-lookahead variants of one ``width``-bit adder site."""

    block_sizes = block_sizes or adder_block_sizes(width)
    variants: list[Variant] = []
    for block_size in block_sizes:
        if block_size >= width:
            name = "ripple"
        elif block_size == 1:
            name = "lookahead"
        else:
            name = f"blocked{block_size}"
        fragment = build_blocked_adder(
            width=width,
            block_size=block_size,
            implementation=implementation,
            prefix=f"{prefix}_{name}_",
        )
        variants.append(
            Variant(name=name, family="adder", fragment=fragment, notes=fragment.notes)
        )
    return tuple(variants)


def build_mcx(
    controls: int,
    topology: str,
    implementation: AndImplementation = AND_GIDNEY,
    prefix: str = "mcx_",
) -> Fragment:
    """Return a multi-controlled X built from ``controls - 1`` AND gates.

    ``linear`` walks an ancilla chain and consumes one AND at a time.
    ``tree`` uses a balanced binary ancilla tree: the same AND count, depth
    ``O(log controls)``, but the first level requests ``controls / 2`` AND
    gates simultaneously.
    """

    if controls < 2:
        raise ValueError("controls must be at least 2")

    builder = FragmentBuilder(prefix=prefix)
    source = builder.add("Clifford")

    if topology == "linear":
        frontier = source
        for _ in range(controls - 1):
            frontier = _emit_and(builder, implementation, [frontier])
        builder.add("Clifford", [frontier])
        return builder.finish(
            ancillas=implementation.ancillas + controls - 1,
            notes=f"linear ancilla chain, {controls - 1} AND",
        )

    if topology != "tree":
        raise ValueError(f"unknown MCX topology {topology!r}")

    level_nodes = [source] * controls
    while len(level_nodes) > 1:
        joint = builder.add("Clifford", sorted(set(level_nodes)))
        pairs = len(level_nodes) // 2
        next_nodes = [_emit_and(builder, implementation, [joint]) for _ in range(pairs)]
        if len(level_nodes) % 2:
            next_nodes.append(joint)
        level_nodes = next_nodes
    builder.add("Clifford", level_nodes)
    return builder.finish(
        ancillas=implementation.ancillas * max(1, controls // 2) + controls,
        notes=f"balanced ancilla tree, depth {ceil(log2(controls))}",
    )


def make_mcx_variants(
    prefix: str,
    controls: int,
    implementation: AndImplementation = AND_GIDNEY,
) -> tuple[Variant, ...]:
    """Return the linear and tree variants of one multi-controlled X site."""

    return tuple(
        Variant(
            name=topology,
            family="mcx",
            fragment=build_mcx(
                controls=controls,
                topology=topology,
                implementation=implementation,
                prefix=f"{prefix}_{topology}_",
            ),
            notes=f"MCX with {controls} controls, {topology} ancilla structure",
        )
        for topology in ("linear", "tree")
    )


def build_rotation(
    t_budget: int,
    parallel_width: int,
    prefix: str = "rot_",
) -> Fragment:
    """Return a single-qubit rotation synthesised at a chosen degree of parallelism.

    ``parallel_width == 1`` is sequential Ross-Selinger style synthesis: the
    approximating sequence is walked one T gate at a time. Larger widths model
    ancilla-assisted parallel synthesis, which cuts T-depth by roughly the
    width at the price of extra T gates for the fix-up circuitry.
    """

    if t_budget < 1:
        raise ValueError("t_budget must be positive")
    if parallel_width < 1:
        raise ValueError("parallel_width must be positive")

    builder = FragmentBuilder(prefix=prefix)
    frontier = [builder.add("Clifford")]
    overhead = 0 if parallel_width == 1 else ceil(t_budget * 0.25 * log2(parallel_width))
    total = t_budget + overhead
    emitted = 0
    while emitted < total:
        width = min(parallel_width, total - emitted)
        joint = builder.add("Clifford", frontier)
        frontier = builder.add_layer("T", width, [joint])
        emitted += width
    builder.add("Clifford", frontier)
    return builder.finish(
        ancillas=0 if parallel_width == 1 else parallel_width,
        notes=(
            f"rotation synthesis, width={parallel_width}, "
            f"T={total} (base {t_budget} + {overhead} parallelisation overhead)"
        ),
    )


def rotation_widths(t_budget: int) -> tuple[int, ...]:
    """Return the parallelism levels offered for a rotation of a given T budget."""

    widths = [1]
    width = 2
    while width <= max(2, t_budget // 2):
        widths.append(width)
        width *= 2
    return tuple(widths)


def make_rotation_variants(
    prefix: str,
    t_budget: int,
    widths: tuple[int, ...] | None = None,
) -> tuple[Variant, ...]:
    """Return the sequential-to-parallel variants of one rotation site."""

    widths = widths or rotation_widths(t_budget)
    return tuple(
        Variant(
            name=f"width{width}",
            family="rotation",
            fragment=build_rotation(
                t_budget=t_budget,
                parallel_width=width,
                prefix=f"{prefix}_w{width}_",
            ),
            notes=f"rotation synthesis at parallel width {width}",
        )
        for width in widths
    )
