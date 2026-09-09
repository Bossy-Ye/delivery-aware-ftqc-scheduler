"""Pilot programs: decision-site graphs mirroring real fault-tolerant kernels.

Each program is a :class:`ProgramSpace`, so it fixes the dependency structure
between operations but leaves the implementation of each operation open. The
important structural covariate is *concurrency*: how many decision sites are
live at the same time and therefore compete for the same factory bank. Serial
kernels expose one site at a time, wide kernels expose many.
"""

from __future__ import annotations

from math import ceil

from .library import (
    AND_GIDNEY,
    AndImplementation,
    make_adder_variants,
    make_and_variants,
    make_mcx_variants,
    make_rotation_variants,
)
from .variants import FragmentBuilder, ProgramSpace, Site, Variant


def _barrier_site(site_id: str) -> Site:
    """Return a single-variant synchronisation site.

    Barriers keep stage boundaries linear in the number of sites instead of
    quadratic, and they cost the same for every variant assignment, so they
    cannot bias a comparison between implementations.
    """

    builder = FragmentBuilder(prefix=f"{site_id}_")
    builder.add("Clifford")
    return Site(
        site_id=site_id,
        family="barrier",
        variants=(Variant(name="barrier", family="barrier", fragment=builder.finish()),),
    )


def _staged(
    name: str,
    stage_sites: list[list[Site]],
    meta: dict[str, str] | None = None,
) -> ProgramSpace:
    """Assemble stages of mutually independent sites into a serial pipeline."""

    sites: list[Site] = []
    edges: list[tuple[str, str]] = []
    previous_barrier: str | None = None

    for index, stage in enumerate(stage_sites):
        barrier = _barrier_site(f"{name}_bar{index:02d}")
        sites.append(barrier)
        if previous_barrier is not None:
            edges.append((previous_barrier, barrier.site_id))
        for site in stage:
            sites.append(site)
            edges.append((barrier.site_id, site.site_id))
        closing = _barrier_site(f"{name}_bar{index:02d}_end")
        sites.append(closing)
        for site in stage:
            edges.append((site.site_id, closing.site_id))
        previous_barrier = closing.site_id

    return ProgramSpace(
        name=name,
        sites=tuple(sites),
        edges=tuple(edges),
        meta=tuple(sorted((meta or {}).items())),
    )


def schoolbook_multiplier(
    width: int = 32,
    rows: int = 4,
    implementation: AndImplementation = AND_GIDNEY,
) -> ProgramSpace:
    """Return a multiplier that accumulates partial products one adder at a time.

    Every adder site depends on the previous one, so exactly one site is live
    at any moment and the whole factory bank serves a single implementation.
    """

    stages = [
        [
            Site(
                site_id=f"mul_add{row:02d}",
                family="adder",
                variants=make_adder_variants(f"mul_add{row:02d}", width, implementation),
            )
        ]
        for row in range(rows)
    ]
    return _staged(
        f"schoolbook_mult_w{width}_r{rows}",
        stages,
        {"kernel": "multiplier", "concurrency": "1", "width": str(width)},
    )


def reduction_tree_multiplier(
    width: int = 32,
    rows: int = 8,
    implementation: AndImplementation = AND_GIDNEY,
) -> ProgramSpace:
    """Return a multiplier that reduces partial products through an adder tree.

    The first stage runs ``rows / 2`` adders concurrently, so the peak demand
    of a chosen implementation is multiplied by the stage width.
    """

    stages: list[list[Site]] = []
    remaining = rows
    level = 0
    while remaining > 1:
        adders = remaining // 2
        stages.append(
            [
                Site(
                    site_id=f"tree_l{level:02d}_add{index:02d}",
                    family="adder",
                    variants=make_adder_variants(
                        f"tree_l{level:02d}_add{index:02d}", width, implementation
                    ),
                )
                for index in range(adders)
            ]
        )
        remaining = adders + (remaining % 2)
        level += 1
    return _staged(
        f"reduction_tree_mult_w{width}_r{rows}",
        stages,
        {"kernel": "multiplier", "concurrency": str(rows // 2), "width": str(width)},
    )


def modular_exponentiation(
    width: int = 32,
    steps: int = 3,
    implementation: AndImplementation = AND_GIDNEY,
) -> ProgramSpace:
    """Return a strictly serial modular-arithmetic pipeline."""

    stages = [
        [
            Site(
                site_id=f"modexp_s{step:02d}_add{half}",
                family="adder",
                variants=make_adder_variants(
                    f"modexp_s{step:02d}_add{half}", width, implementation
                ),
            )
        ]
        for step in range(steps)
        for half in range(2)
    ]
    return _staged(
        f"modexp_w{width}_s{steps}",
        stages,
        {"kernel": "modexp", "concurrency": "1", "width": str(width)},
    )


def qft_rotation_block(qubits: int = 8, t_budget: int = 32) -> ProgramSpace:
    """Return a QFT-shaped block of rotations.

    Stage ``i`` holds the ``qubits - i - 1`` controlled rotations that follow
    the ``i``-th Hadamard. They are mutually independent, so early stages are
    wide and later stages narrow.
    """

    stages = [
        [
            Site(
                site_id=f"qft_s{stage:02d}_rot{index:02d}",
                family="rotation",
                variants=make_rotation_variants(
                    f"qft_s{stage:02d}_rot{index:02d}", t_budget
                ),
            )
            for index in range(qubits - stage - 1)
        ]
        for stage in range(qubits - 1)
    ]
    stages = [stage for stage in stages if stage]
    return _staged(
        f"qft_q{qubits}_t{t_budget}",
        stages,
        {"kernel": "qft", "concurrency": str(qubits - 1), "width": str(qubits)},
    )


def trotter_layers(terms: int = 6, layers: int = 3, t_budget: int = 32) -> ProgramSpace:
    """Return Trotterised Hamiltonian layers of mutually independent rotations."""

    stages = [
        [
            Site(
                site_id=f"trot_l{layer:02d}_term{term:02d}",
                family="rotation",
                variants=make_rotation_variants(
                    f"trot_l{layer:02d}_term{term:02d}", t_budget
                ),
            )
            for term in range(terms)
        ]
        for layer in range(layers)
    ]
    return _staged(
        f"trotter_t{terms}_l{layers}_b{t_budget}",
        stages,
        {"kernel": "trotter", "concurrency": str(terms), "width": str(terms)},
    )


def grover_iterations(
    controls: int = 16,
    iterations: int = 3,
    t_budget: int = 32,
    implementation: AndImplementation = AND_GIDNEY,
) -> ProgramSpace:
    """Return Grover iterations: a multi-controlled oracle plus a diffusion rotation."""

    stages: list[list[Site]] = []
    for iteration in range(iterations):
        stages.append(
            [
                Site(
                    site_id=f"grov_i{iteration:02d}_oracle",
                    family="mcx",
                    variants=make_mcx_variants(
                        f"grov_i{iteration:02d}_oracle", controls, implementation
                    ),
                )
            ]
        )
        stages.append(
            [
                Site(
                    site_id=f"grov_i{iteration:02d}_diff",
                    family="rotation",
                    variants=make_rotation_variants(
                        f"grov_i{iteration:02d}_diff", t_budget
                    ),
                )
            ]
        )
    return _staged(
        f"grover_c{controls}_i{iterations}",
        stages,
        {"kernel": "grover", "concurrency": "1", "width": str(controls)},
    )


def parallel_oracle_bank(
    controls: int = 16,
    lanes: int = 4,
    implementation: AndImplementation = AND_GIDNEY,
) -> ProgramSpace:
    """Return independent multi-controlled oracles evaluated in parallel lanes."""

    stages = [
        [
            Site(
                site_id=f"bank_lane{lane:02d}",
                family="mcx",
                variants=make_mcx_variants(f"bank_lane{lane:02d}", controls, implementation),
            )
            for lane in range(lanes)
        ]
    ]
    return _staged(
        f"oracle_bank_c{controls}_l{lanes}",
        stages,
        {"kernel": "oracle_bank", "concurrency": str(lanes), "width": str(controls)},
    )


def mixed_kernel(
    width: int = 32,
    controls: int = 16,
    t_budget: int = 32,
    lanes: int = 2,
    implementation: AndImplementation = AND_GIDNEY,
) -> ProgramSpace:
    """Return a kernel mixing adder, oracle and rotation sites in parallel lanes."""

    stages: list[list[Site]] = []
    stages.append(
        [
            Site(
                site_id=f"mix_add{lane:02d}",
                family="adder",
                variants=make_adder_variants(f"mix_add{lane:02d}", width, implementation),
            )
            for lane in range(lanes)
        ]
    )
    stages.append(
        [
            Site(
                site_id=f"mix_mcx{lane:02d}",
                family="mcx",
                variants=make_mcx_variants(f"mix_mcx{lane:02d}", controls, implementation),
            )
            for lane in range(lanes)
        ]
    )
    stages.append(
        [
            Site(
                site_id=f"mix_rot{lane:02d}",
                family="rotation",
                variants=make_rotation_variants(f"mix_rot{lane:02d}", t_budget),
            )
            for lane in range(lanes)
        ]
    )
    return _staged(
        f"mixed_w{width}_c{controls}_l{lanes}",
        stages,
        {"kernel": "mixed", "concurrency": str(lanes), "width": str(width)},
    )


def toffoli_ladder(count: int = 4, lanes: int = 2) -> ProgramSpace:
    """Return stages of independent Toffoli sites drawn from the AMMR/Selinger family."""

    stages = [
        [
            Site(
                site_id=f"tof_s{stage:02d}_l{lane:02d}",
                family="and",
                variants=make_and_variants(f"tof_s{stage:02d}_l{lane:02d}"),
            )
            for lane in range(lanes)
        ]
        for stage in range(count)
    ]
    return _staged(
        f"toffoli_ladder_n{count}_l{lanes}",
        stages,
        {"kernel": "toffoli", "concurrency": str(lanes), "width": str(count)},
    )


def pilot_programs() -> list[ProgramSpace]:
    """Return the diagnostic program set used by the go/no-go study.

    The set is intentionally small and spans four axes: kernel family, operand
    size, the number of decision sites, and site-level concurrency. Programs
    with at most a few thousand assignments can be solved exhaustively, which
    is what makes an optimality reference available.
    """

    programs: list[ProgramSpace] = []
    for width in (16, 32, 64):
        programs.append(schoolbook_multiplier(width=width, rows=3))
        programs.append(modular_exponentiation(width=width, steps=2))
        programs.append(reduction_tree_multiplier(width=width, rows=4))
        programs.append(reduction_tree_multiplier(width=width, rows=8))
    for controls in (8, 16, 32):
        programs.append(grover_iterations(controls=controls, iterations=2))
        programs.append(parallel_oracle_bank(controls=controls, lanes=4))
    for qubits in (5, 6):
        programs.append(qft_rotation_block(qubits=qubits, t_budget=32))
    for terms in (2, 4, 8):
        programs.append(trotter_layers(terms=terms, layers=2, t_budget=32))
    for lanes in (1, 2, 4):
        programs.append(mixed_kernel(width=32, controls=16, t_budget=32, lanes=lanes))
    programs.append(toffoli_ladder(count=3, lanes=2))
    programs.append(toffoli_ladder(count=3, lanes=4))
    return programs


def decision_sites(program: ProgramSpace) -> tuple[Site, ...]:
    """Return the sites that actually offer a choice."""

    return tuple(site for site in program.sites if len(site.variants) > 1)


def assignment_space_size(program: ProgramSpace) -> int:
    """Return the number of distinct assignments over the real decision sites."""

    total = 1
    for site in decision_sites(program):
        total *= len(site.variants)
    return total


def summarize_pilot() -> list[dict[str, object]]:
    """Return one summary row per pilot program."""

    rows: list[dict[str, object]] = []
    for program in pilot_programs():
        sites = decision_sites(program)
        rows.append(
            {
                "program": program.name,
                "kernel": dict(program.meta).get("kernel", ""),
                "concurrency": dict(program.meta).get("concurrency", ""),
                "decision_sites": len(sites),
                "assignments": assignment_space_size(program),
                "families": "+".join(sorted({site.family for site in sites})),
            }
        )
    return rows


def exhaustive_budget(program: ProgramSpace, limit: int = 20_000) -> bool:
    """Return whether the assignment space is small enough to enumerate."""

    return assignment_space_size(program) <= limit


def ceil_div(numerator: int, denominator: int) -> int:
    """Return the ceiling of an integer division."""

    return ceil(numerator / denominator)
