"""Implementation variants that consume different mixtures of T and CCZ states.

Every entry records where its cost comes from. The costs are stylised in the
sense that Clifford structure is represented by a uniform one-cycle glue layer
between resource layers, identical across variants so that it cannot bias a
comparison; the resource counts and depths are the published ones.

Sources
-------
Gidney 2018, *Halving the cost of quantum addition*, Quantum 2, 74
    (arXiv:1709.06648). The temporary logical-AND costs 4 T states to compute
    and 0 to uncompute, which is where ``and_t4`` and the 4n T cost of a
    ripple-carry adder come from.
Gidney and Fowler 2019, *Efficient magic state factories with a catalyzed
    |CCZ> to 2|T> transformation*, Quantum 3, 135 (arXiv:1812.01238). A Toffoli
    is a CCZ up to Clifford conjugation, so it can be consumed directly from a
    CCZ factory: one CCZ state per Toffoli. Also the source of the catalyzed
    1 CCZ -> 2 T conversion.
Amy, Maslov, Mosca and Roetteler 2013, *A meet-in-the-middle algorithm for fast
    synthesis of depth-optimal quantum circuits*. Toffoli with T-count 7 and
    T-depth 3 using no ancillas.
Selinger 2013, *Quantum circuits of T-depth one*. Toffoli with T-count 7 and
    T-depth 1 using four ancillas.
Ross and Selinger 2016, *Optimal ancilla-free Clifford+T approximation of
    z-rotations*. T-count about 4 log2(1/eps) for a single-qubit rotation,
    synthesised as a sequential gate sequence.
Toffoli-count rotation synthesis (arXiv:2404.05618, Phys. Rev. Research 6,
    L042027). A single-qubit rotation using Clifford+Toffoli with expected
    Toffoli count below 4*ceil(log2(1/eps)) + 6 and expected depth below
    log2(1/eps) + 3, using 2*ceil(log2(1/eps)) ancillas.
Phase-gradient rotation. With a phase-gradient catalyst held in a register, a
    rotation becomes a b-bit addition controlled by the target qubit, costing
    roughly twice a bare adder in Toffoli count and depth, hence about 2b
    Toffolis for b bits of precision.
Draper, Kutin, Rains and Svore 2004, *A logarithmic-depth quantum carry-lookahead
    adder*. The lookahead and blocked adders trade about twice the AND count
    for logarithmic depth.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log2

from ftqc_delivery.rac.variants import Fragment, FragmentBuilder, Site, Variant


@dataclass(frozen=True)
class Realisation:
    """How one logical AND / Toffoli draws on the factories."""

    name: str
    layers: tuple[tuple[str, int], ...]
    ancillas: int
    source: str

    @property
    def counts(self) -> dict[str, int]:
        """Return the states of each kind that one AND consumes."""

        totals: dict[str, int] = {}
        for op_type, width in self.layers:
            totals[op_type] = totals.get(op_type, 0) + width
        return totals

    @property
    def depth(self) -> int:
        """Return the number of sequential resource layers."""

        return len(self.layers)


AND_CCZ = Realisation(
    name="ccz",
    layers=(("CCZ", 1),),
    ancillas=1,
    source="Toffoli is a CCZ up to Cliffords; one CCZ state (Gidney & Fowler 2019)",
)
AND_T4 = Realisation(
    name="t4",
    layers=(("T", 2), ("T", 2)),
    ancillas=1,
    source="Gidney 2018 temporary AND: 4 T to compute, 0 to uncompute",
)
TOF_T7_D3 = Realisation(
    name="t7d3",
    layers=(("T", 3), ("T", 3), ("T", 1)),
    ancillas=0,
    source="Amy, Maslov, Mosca & Roetteler 2013: T-count 7, T-depth 3, no ancilla",
)
TOF_T7_D1 = Realisation(
    name="t7d1",
    layers=(("T", 7),),
    ancillas=4,
    source="Selinger 2013: T-count 7, T-depth 1, four ancillas",
)

#: The realisations offered at a decision site, in a fixed order.
REALISATIONS = (AND_CCZ, AND_T4, TOF_T7_D3, TOF_T7_D1)
CORE_REALISATIONS = (AND_CCZ, AND_T4)


def _emit_and(builder: FragmentBuilder, realisation: Realisation, predecessors: list[str]) -> str:
    """Emit one AND gate and return the node carrying its result."""

    frontier = list(predecessors)
    for op_type, width in realisation.layers:
        joint = builder.add("Clifford", frontier)
        frontier = builder.add_layer(op_type, width, [joint])
    return builder.add("Clifford", frontier)


def _emit_and_sequence(
    builder: FragmentBuilder,
    realisations: list[Realisation],
    start: str,
) -> str:
    """Emit a serial chain of AND gates, one per entry of ``realisations``."""

    frontier = start
    for realisation in realisations:
        frontier = _emit_and(builder, realisation, [frontier])
    return frontier


def _prefix_levels(leaves: int) -> list[int]:
    """Return AND counts per level of a Brent-Kung prefix computation."""

    if leaves <= 1:
        return []
    forward: list[int] = []
    active = leaves
    while active > 1:
        active //= 2
        forward.append(active)
    backward = list(reversed(forward[:-1]))
    return [count for count in forward + backward if count > 0]


def _realisation_cycle(realisation: Realisation, index: int) -> Realisation:
    """Return the realisation to use for the ``index``-th AND of a mixed block."""

    if realisation.name != "mix":
        return realisation
    return AND_CCZ if index % 2 == 0 else AND_T4


AND_MIX = Realisation(
    name="mix",
    layers=(("CCZ", 1),),
    ancillas=1,
    source="alternate CCZ and 4-T ANDs inside one block; tests within-site mixing",
)


def build_adder(
    width: int,
    block_size: int,
    realisation: Realisation,
    prefix: str = "add_",
) -> Fragment:
    """Return a ``width``-bit adder whose carry chain is cut into blocks.

    ``block_size >= width`` is a ripple-carry adder: one serial chain of
    ``width - 1`` AND gates. Smaller blocks give the standard carry-select
    structure, costing about twice the AND count for a depth of
    ``block_size + 2 log2(blocks)``.
    """

    if width < 2:
        raise ValueError("width must be at least 2")
    if block_size < 1:
        raise ValueError("block_size must be at least 1")

    builder = FragmentBuilder(prefix=prefix)
    source = builder.add("Clifford")
    counter = 0

    def next_realisation() -> Realisation:
        nonlocal counter
        chosen = _realisation_cycle(realisation, counter)
        counter += 1
        return chosen

    if block_size >= width:
        _emit_and_sequence(
            builder, [next_realisation() for _ in range(width - 1)], source
        )
        exits = [node_id for node_id, _ in builder._nodes]
        builder.add("Clifford", [exits[-1]])
        return builder.finish(
            ancillas=realisation.ancillas,
            notes=f"ripple-carry, {width - 1} AND on a serial carry chain",
        )

    blocks = ceil(width / block_size)
    local: list[str] = []
    speculative: list[str] = []
    for _ in range(blocks):
        for sink in (local, speculative):
            sink.append(
                _emit_and_sequence(
                    builder,
                    [next_realisation() for _ in range(block_size - 1)],
                    source,
                )
            )

    frontier = local or [source]
    for level_width in _prefix_levels(blocks):
        joint = builder.add("Clifford", sorted(set(frontier)))
        frontier = [
            _emit_and(builder, next_realisation(), [joint]) for _ in range(level_width)
        ]
    builder.add("Clifford", sorted(set(list(frontier) + speculative)))

    return builder.finish(
        ancillas=realisation.ancillas * 2 * blocks + blocks,
        notes=(
            f"carry-select adder, block={block_size}, blocks={blocks}, "
            f"prefix levels={len(_prefix_levels(blocks))}"
        ),
    )


def build_mcx(
    controls: int,
    topology: str,
    realisation: Realisation,
    prefix: str = "mcx_",
) -> Fragment:
    """Return a multi-controlled X built from ``controls - 1`` AND gates."""

    if controls < 2:
        raise ValueError("controls must be at least 2")
    builder = FragmentBuilder(prefix=prefix)
    source = builder.add("Clifford")
    counter = 0

    def next_realisation() -> Realisation:
        nonlocal counter
        chosen = _realisation_cycle(realisation, counter)
        counter += 1
        return chosen

    if topology == "linear":
        tail = _emit_and_sequence(
            builder, [next_realisation() for _ in range(controls - 1)], source
        )
        builder.add("Clifford", [tail])
        return builder.finish(
            ancillas=realisation.ancillas + controls - 1,
            notes=f"linear ancilla chain, {controls - 1} AND",
        )
    if topology != "tree":
        raise ValueError(f"unknown MCX topology {topology!r}")

    level = [source] * controls
    while len(level) > 1:
        joint = builder.add("Clifford", sorted(set(level)))
        pairs = len(level) // 2
        nodes = [_emit_and(builder, next_realisation(), [joint]) for _ in range(pairs)]
        if len(level) % 2:
            nodes.append(joint)
        level = nodes
    builder.add("Clifford", level)
    return builder.finish(
        ancillas=realisation.ancillas * max(1, controls // 2) + controls,
        notes=f"balanced ancilla tree, depth {ceil(log2(controls))}",
    )


def build_rotation(
    bits: int,
    method: str,
    realisation: Realisation,
    prefix: str = "rot_",
    toffoli_scale: float = 1.0,
) -> Fragment:
    """Return a single-qubit rotation synthesised to ``bits`` of precision.

    ``rs`` is Ross-Selinger synthesis: about ``4 * bits`` T states applied as a
    sequential gate sequence, with no Toffoli structure and therefore no choice
    of factory. ``toffoli_log`` and ``phase_gradient`` are Toffoli-based, so
    each of their Toffolis can be drawn from a CCZ factory or built from T
    states, which is where the resource mixture becomes a compiler decision.

    ``toffoli_scale`` multiplies the Toffoli count of the Toffoli-based
    methods. At 1 the phase-gradient route costs exactly the same in
    T-equivalents as Ross-Selinger, which is what the published counts give;
    the parameter exists so that the sensitivity of the result to that
    coincidence can be measured rather than assumed.
    """

    if bits < 1:
        raise ValueError("bits must be positive")
    builder = FragmentBuilder(prefix=prefix)
    source = builder.add("Clifford")

    if method == "rs":
        frontier = source
        for _ in range(4 * bits):
            joint = builder.add("Clifford", [frontier])
            frontier = builder.add_layer("T", 1, [joint])[0]
        builder.add("Clifford", [frontier])
        return builder.finish(
            ancillas=0,
            notes=f"Ross-Selinger sequential synthesis, {4 * bits} T states",
        )

    counter = 0

    def next_realisation() -> Realisation:
        nonlocal counter
        chosen = _realisation_cycle(realisation, counter)
        counter += 1
        return chosen

    if method == "toffoli_log":
        total = max(1, round(toffoli_scale * (4 * bits + 6)))
        levels = max(1, bits + 3)
        per_level = ceil(total / levels)
        frontier = [source]
        emitted = 0
        while emitted < total:
            joint = builder.add("Clifford", sorted(set(frontier)))
            width = min(per_level, total - emitted)
            frontier = [_emit_and(builder, next_realisation(), [joint]) for _ in range(width)]
            emitted += width
        builder.add("Clifford", sorted(set(frontier)))
        return builder.finish(
            ancillas=2 * bits,
            notes=f"Toffoli-count synthesis, {total} Toffoli over {levels} levels",
        )

    if method == "phase_gradient":
        total = max(1, round(toffoli_scale * 2 * bits))
        tail = _emit_and_sequence(
            builder, [next_realisation() for _ in range(total)], source
        )
        builder.add("Clifford", [tail])
        return builder.finish(
            ancillas=bits,
            notes=f"phase-gradient addition, {total} Toffoli on a carry chain",
        )

    raise ValueError(f"unknown rotation method {method!r}")


def adder_variants(
    prefix: str,
    width: int,
    block_sizes: tuple[int, ...] | None = None,
    realisations: tuple[Realisation, ...] = CORE_REALISATIONS,
    include_mix: bool = True,
) -> tuple[Variant, ...]:
    """Return the adder implementations offered at one site."""

    if block_sizes is None:
        block_sizes = (width, max(2, width // 4)) if width >= 8 else (width,)
    options = list(realisations) + ([AND_MIX] if include_mix else [])
    variants: list[Variant] = []
    for block_size in block_sizes:
        shape = "ripple" if block_size >= width else f"select{block_size}"
        for realisation in options:
            name = f"{shape}_{realisation.name}"
            fragment = build_adder(width, block_size, realisation, prefix=f"{prefix}_{name}_")
            variants.append(
                Variant(
                    name=name,
                    family="adder",
                    fragment=fragment,
                    notes=f"{fragment.notes}; ANDs realised as {realisation.source}",
                )
            )
    return tuple(variants)


def mcx_variants(
    prefix: str,
    controls: int,
    realisations: tuple[Realisation, ...] = CORE_REALISATIONS,
) -> tuple[Variant, ...]:
    """Return the multi-controlled X implementations offered at one site."""

    variants: list[Variant] = []
    for topology in ("linear", "tree"):
        for realisation in realisations:
            name = f"{topology}_{realisation.name}"
            fragment = build_mcx(controls, topology, realisation, prefix=f"{prefix}_{name}_")
            variants.append(
                Variant(
                    name=name,
                    family="mcx",
                    fragment=fragment,
                    notes=f"{fragment.notes}; ANDs realised as {realisation.source}",
                )
            )
    return tuple(variants)


def rotation_variants(
    prefix: str,
    bits: int,
    realisations: tuple[Realisation, ...] = CORE_REALISATIONS,
    toffoli_scale: float = 1.0,
) -> tuple[Variant, ...]:
    """Return the rotation implementations offered at one site."""

    variants = [
        Variant(
            name="rs_t",
            family="rotation",
            fragment=build_rotation(bits, "rs", AND_T4, prefix=f"{prefix}_rs_"),
            notes="Ross-Selinger sequential T synthesis",
        )
    ]
    for method, label in (("toffoli_log", "toflog"), ("phase_gradient", "pg")):
        for realisation in realisations:
            name = f"{label}_{realisation.name}"
            fragment = build_rotation(
                bits,
                method,
                realisation,
                prefix=f"{prefix}_{name}_",
                toffoli_scale=toffoli_scale,
            )
            variants.append(
                Variant(
                    name=name,
                    family="rotation",
                    fragment=fragment,
                    notes=f"{fragment.notes}; Toffolis realised as {realisation.source}",
                )
            )
    return tuple(variants)


def and_variants(
    prefix: str, realisations: tuple[Realisation, ...] = REALISATIONS
) -> tuple[Variant, ...]:
    """Return the implementations of a single logical AND / Toffoli."""

    variants: list[Variant] = []
    for realisation in realisations:
        builder = FragmentBuilder(prefix=f"{prefix}_{realisation.name}_")
        source = builder.add("Clifford")
        result = _emit_and(builder, realisation, [source])
        builder.add("Clifford", [result])
        variants.append(
            Variant(
                name=realisation.name,
                family="and",
                fragment=builder.finish(
                    ancillas=realisation.ancillas, notes=realisation.source
                ),
                notes=realisation.source,
            )
        )
    return tuple(variants)


def variant_table() -> list[dict[str, object]]:
    """Return the literature-backed cost of every variant family, for the memo."""

    from .execution import critical_path, resource_counts

    rows: list[dict[str, object]] = []
    families = (
        ("and", lambda: and_variants("t")),
        ("adder n=32", lambda: adder_variants("a", 32)),
        ("mcx k=16", lambda: mcx_variants("m", 16)),
        ("rotation b=10", lambda: rotation_variants("r", 10)),
    )
    for family, builder in families:
        for variant in builder():
            dag = variant.fragment.to_dag(variant.name)
            counts = resource_counts(dag)
            rows.append(
                {
                    "family": family,
                    "variant": variant.name,
                    "T": counts.get("T", 0),
                    "CCZ": counts.get("CCZ", 0),
                    "t_equivalents": counts.get("T", 0) + 2 * counts.get("CCZ", 0),
                    "critical_path": critical_path(dag),
                    "ancillas": variant.fragment.ancillas,
                    "source": variant.notes,
                }
            )
    return rows
