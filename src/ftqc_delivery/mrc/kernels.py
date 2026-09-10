"""Pilot kernels: programs whose decision sites compete for two factory banks.

Each kernel is a :class:`ProgramSpace` from the single-resource study, reused
unchanged: a graph of decision sites, each offering semantically equivalent
implementations. What differs here is that the implementations draw on
different factories, so choosing them is a load-balancing problem.

The structural covariate that matters is concurrency: how many sites are live
at once and therefore contend for the same banks at the same time.
"""

from __future__ import annotations

from ftqc_delivery.rac.variants import FragmentBuilder, ProgramSpace, Site, Variant

from .library import (
    CORE_REALISATIONS,
    REALISATIONS,
    adder_variants,
    and_variants,
    mcx_variants,
    rotation_variants,
)


def _barrier(site_id: str) -> Site:
    """Return a single-variant synchronisation site.

    Barriers keep stage boundaries linear in the number of sites and cost the
    same under every assignment, so they cannot bias a comparison.
    """

    builder = FragmentBuilder(prefix=f"{site_id}_")
    builder.add("Clifford")
    return Site(
        site_id=site_id,
        family="barrier",
        variants=(Variant(name="barrier", family="barrier", fragment=builder.finish()),),
    )


def staged(name: str, stages: list[list[Site]], meta: dict[str, str]) -> ProgramSpace:
    """Assemble stages of mutually independent sites into a serial pipeline."""

    sites: list[Site] = []
    edges: list[tuple[str, str]] = []
    previous: str | None = None
    for index, stage in enumerate(stages):
        opening = _barrier(f"{name}_b{index:02d}")
        sites.append(opening)
        if previous is not None:
            edges.append((previous, opening.site_id))
        for site in stage:
            sites.append(site)
            edges.append((opening.site_id, site.site_id))
        closing = _barrier(f"{name}_b{index:02d}e")
        sites.append(closing)
        for site in stage:
            edges.append((site.site_id, closing.site_id))
        previous = closing.site_id
    return ProgramSpace(
        name=name,
        sites=tuple(sites),
        edges=tuple(edges),
        meta=tuple(sorted(meta.items())),
    )


def modular_exponentiation(width: int = 32, steps: int = 3) -> ProgramSpace:
    """Return Shor-style modular exponentiation: a serial chain of adders."""

    stages = [
        [
            Site(
                site_id=f"modexp_s{step:02d}_{half}",
                family="adder",
                variants=adder_variants(f"modexp_s{step:02d}_{half}", width),
            )
        ]
        for step in range(steps)
        for half in ("a", "b")
    ]
    return staged(
        f"modexp_w{width}_s{steps}",
        stages,
        {"kernel": "modexp", "concurrency": "1", "width": str(width)},
    )


def multiplier_tree(width: int = 32, rows: int = 8) -> ProgramSpace:
    """Return a multiplier that reduces partial products through an adder tree."""

    stages: list[list[Site]] = []
    remaining = rows
    level = 0
    while remaining > 1:
        adders = remaining // 2
        stages.append(
            [
                Site(
                    site_id=f"mul_l{level:02d}_{index:02d}",
                    family="adder",
                    variants=adder_variants(f"mul_l{level:02d}_{index:02d}", width),
                )
                for index in range(adders)
            ]
        )
        remaining = adders + (remaining % 2)
        level += 1
    return staged(
        f"multiplier_w{width}_r{rows}",
        stages,
        {"kernel": "multiplier", "concurrency": str(rows // 2), "width": str(width)},
    )


def qft_block(qubits: int = 6, bits: int = 10) -> ProgramSpace:
    """Return a QFT-shaped block: wide early rotation stages, narrow later ones."""

    stages = [
        [
            Site(
                site_id=f"qft_s{stage:02d}_{index:02d}",
                family="rotation",
                variants=rotation_variants(f"qft_s{stage:02d}_{index:02d}", bits),
            )
            for index in range(qubits - stage - 1)
        ]
        for stage in range(qubits - 1)
    ]
    stages = [stage for stage in stages if stage]
    return staged(
        f"qft_q{qubits}_b{bits}",
        stages,
        {"kernel": "qft", "concurrency": str(qubits - 1), "width": str(qubits)},
    )


def trotter_layers(terms: int = 6, layers: int = 2, bits: int = 10) -> ProgramSpace:
    """Return Trotterised layers of mutually independent rotations."""

    stages = [
        [
            Site(
                site_id=f"trot_l{layer:02d}_{term:02d}",
                family="rotation",
                variants=rotation_variants(f"trot_l{layer:02d}_{term:02d}", bits),
            )
            for term in range(terms)
        ]
        for layer in range(layers)
    ]
    return staged(
        f"trotter_t{terms}_l{layers}_b{bits}",
        stages,
        {"kernel": "trotter", "concurrency": str(terms), "width": str(terms)},
    )


def grover_iterations(controls: int = 16, iterations: int = 2, bits: int = 10) -> ProgramSpace:
    """Return Grover iterations: a multi-controlled oracle then a diffusion rotation."""

    stages: list[list[Site]] = []
    for iteration in range(iterations):
        stages.append(
            [
                Site(
                    site_id=f"grov_i{iteration:02d}_oracle",
                    family="mcx",
                    variants=mcx_variants(f"grov_i{iteration:02d}_oracle", controls),
                )
            ]
        )
        stages.append(
            [
                Site(
                    site_id=f"grov_i{iteration:02d}_diff",
                    family="rotation",
                    variants=rotation_variants(f"grov_i{iteration:02d}_diff", bits),
                )
            ]
        )
    return staged(
        f"grover_c{controls}_i{iterations}",
        stages,
        {"kernel": "grover", "concurrency": "1", "width": str(controls)},
    )


def oracle_bank(controls: int = 16, lanes: int = 4) -> ProgramSpace:
    """Return independent multi-controlled oracles evaluated in parallel lanes."""

    stages = [
        [
            Site(
                site_id=f"bank_l{lane:02d}",
                family="mcx",
                variants=mcx_variants(f"bank_l{lane:02d}", controls),
            )
            for lane in range(lanes)
        ]
    ]
    return staged(
        f"oracle_bank_c{controls}_l{lanes}",
        stages,
        {"kernel": "oracle_bank", "concurrency": str(lanes), "width": str(controls)},
    )


def phase_estimation(width: int = 32, rounds: int = 2, bits: int = 10) -> ProgramSpace:
    """Return phase estimation: controlled arithmetic followed by a rotation stage."""

    stages: list[list[Site]] = []
    for round_index in range(rounds):
        stages.append(
            [
                Site(
                    site_id=f"pe_r{round_index:02d}_add{lane}",
                    family="adder",
                    variants=adder_variants(f"pe_r{round_index:02d}_add{lane}", width),
                )
                for lane in range(2)
            ]
        )
        stages.append(
            [
                Site(
                    site_id=f"pe_r{round_index:02d}_rot{lane}",
                    family="rotation",
                    variants=rotation_variants(f"pe_r{round_index:02d}_rot{lane}", bits),
                )
                for lane in range(2)
            ]
        )
    return staged(
        f"phase_est_w{width}_r{rounds}",
        stages,
        {"kernel": "phase_estimation", "concurrency": "2", "width": str(width)},
    )


def mixed_kernel(width: int = 32, controls: int = 16, bits: int = 10, lanes: int = 2) -> ProgramSpace:
    """Return a kernel whose stages mix adder, oracle and rotation sites."""

    stages = [
        [
            Site(
                site_id=f"mix_add{lane:02d}",
                family="adder",
                variants=adder_variants(f"mix_add{lane:02d}", width),
            )
            for lane in range(lanes)
        ],
        [
            Site(
                site_id=f"mix_mcx{lane:02d}",
                family="mcx",
                variants=mcx_variants(f"mix_mcx{lane:02d}", controls),
            )
            for lane in range(lanes)
        ],
        [
            Site(
                site_id=f"mix_rot{lane:02d}",
                family="rotation",
                variants=rotation_variants(f"mix_rot{lane:02d}", bits),
            )
            for lane in range(lanes)
        ],
    ]
    return staged(
        f"mixed_w{width}_c{controls}_l{lanes}",
        stages,
        {"kernel": "mixed", "concurrency": str(lanes), "width": str(width)},
    )


def heterogeneous_stage(lanes: int = 4, width: int = 32, controls: int = 16, bits: int = 10) -> ProgramSpace:
    """Return one wide stage whose lanes are drawn from different families.

    Every lane runs concurrently and each may pick a different factory, so this
    is the shape in which a mixture, if it ever pays, should pay most.
    """

    stage: list[Site] = []
    for lane in range(lanes):
        which = lane % 3
        if which == 0:
            stage.append(
                Site(
                    site_id=f"het_l{lane:02d}_add",
                    family="adder",
                    variants=adder_variants(f"het_l{lane:02d}_add", width),
                )
            )
        elif which == 1:
            stage.append(
                Site(
                    site_id=f"het_l{lane:02d}_rot",
                    family="rotation",
                    variants=rotation_variants(f"het_l{lane:02d}_rot", bits),
                )
            )
        else:
            stage.append(
                Site(
                    site_id=f"het_l{lane:02d}_mcx",
                    family="mcx",
                    variants=mcx_variants(f"het_l{lane:02d}_mcx", controls),
                )
            )
    return staged(
        f"heterostage_l{lanes}",
        [stage],
        {"kernel": "heterostage", "concurrency": str(lanes), "width": str(width)},
    )


def and_ladder(stages: int = 3, lanes: int = 3) -> ProgramSpace:
    """Return stages of bare AND sites, the smallest kernel with a real choice."""

    grid = [
        [
            Site(
                site_id=f"and_s{stage:02d}_l{lane:02d}",
                family="and",
                variants=and_variants(f"and_s{stage:02d}_l{lane:02d}", REALISATIONS),
            )
            for lane in range(lanes)
        ]
        for stage in range(stages)
    ]
    return staged(
        f"and_ladder_s{stages}_l{lanes}",
        grid,
        {"kernel": "and_ladder", "concurrency": str(lanes), "width": "3"},
    )


def pilot_kernels() -> list[ProgramSpace]:
    """Return the diagnostic kernel set.

    Small enough that the global optimum can be enumerated for most entries,
    and spanning kernel family, operand size and concurrency.
    """

    kernels: list[ProgramSpace] = []
    for width in (16, 32, 64):
        kernels.append(modular_exponentiation(width=width, steps=2))
        kernels.append(multiplier_tree(width=width, rows=4))
    kernels.append(multiplier_tree(width=32, rows=8))
    for terms in (2, 3, 4):
        kernels.append(trotter_layers(terms=terms, layers=2, bits=10))
    for qubits in (4, 5):
        kernels.append(qft_block(qubits=qubits, bits=10))
    for controls in (8, 16, 32):
        kernels.append(grover_iterations(controls=controls, iterations=2, bits=10))
    for lanes in (2, 4):
        kernels.append(oracle_bank(controls=16, lanes=lanes))
    kernels.append(phase_estimation(width=32, rounds=1, bits=10))
    for lanes in (1, 2):
        kernels.append(mixed_kernel(width=32, controls=16, bits=10, lanes=lanes))
    for lanes in (3, 4):
        kernels.append(heterogeneous_stage(lanes=lanes))
    for lanes in (2, 3):
        kernels.append(and_ladder(stages=2, lanes=lanes))
    return kernels


def decision_sites(program: ProgramSpace) -> tuple[Site, ...]:
    """Return the sites that actually offer a choice."""

    return tuple(site for site in program.sites if len(site.variants) > 1)


def assignment_space(program: ProgramSpace) -> int:
    """Return the number of distinct assignments over the real decision sites."""

    total = 1
    for site in decision_sites(program):
        total *= len(site.variants)
    return total
