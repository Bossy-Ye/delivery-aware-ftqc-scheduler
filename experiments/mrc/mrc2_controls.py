"""Falsification controls and robustness sweeps.

Four things are varied here, each of which could show that the headroom found
in the main matrix is not what it appears to be.

*Pooled control.* The same total capacity is placed in a single bank and only
the implementations that draw on that bank are offered. The resources are then
fungible by construction, and the single-resource study says the headroom
should vanish. If it does not, the effect was never about non-fungibility.

*Conversion control.* The machine is given the real protocols that turn one
resource into the other -- the catalyzed one CCZ to two T, and the eight T to
one CCZ distillation. These make the banks partly interchangeable at a lossy
exchange rate, so the headroom should shrink towards the pooled control.

*Buffer, latency and failures.* Storage, production latency and distillation
failures are swept, to check the effect is not an artefact of one convenient
setting.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import (
    RESULT_DIR,
    SIMPLE_BASELINES,
    kernel_meta,
    kernels,
    ratio,
    summarize,
    write_csv,
)

from ftqc_delivery.mrc.execution import resource_counts
from ftqc_delivery.mrc.kernels import decision_sites
from ftqc_delivery.mrc.policies import (
    feasible_names,
    best_oracle,
    heterogeneity,
    mixture,
    run_policy,
    select_uniform_oracle,
)
from ftqc_delivery.mrc.resources import (
    CATALYZED_CCZ_TO_T,
    CCZ,
    T,
    T_TO_CCZ_DISTILLATION,
    UNBOUNDED,
    Machine,
    machine_for_capacity,
)
from ftqc_delivery.rac.variants import ProgramSpace, Site


SUBSET = (
    "trotter_t2_l2_b10",
    "trotter_t3_l2_b10",
    "qft_q4_b10",
    "multiplier_w32_r4",
    "heterostage_l3",
    "and_ladder_s2_l2",
    "mixed_w32_c16_l1",
    "oracle_bank_c16_l4",
)

CAPACITIES = (0.25, 0.5, 1.0)
SHARES = (0.25, 0.5, 0.75)
ORACLE_LIMIT = 40_000

FIELDS = [
    "kernel",
    "control",
    "setting",
    "capacity_target",
    "ccz_share",
    "t_rate",
    "ccz_rate",
    "buffer",
    "latency",
    "p_success",
    "seed",
    "makespan_uniform_oracle",
    "makespan_best_simple",
    "best_simple_baseline",
    "makespan_global_oracle",
    "oracle_exhaustive",
    "headroom_over_uniform_oracle",
    "headroom_over_best_simple",
    "oracle_heterogeneity",
    "oracle_ccz_share_of_demand",
]


def _single_bank_program(program: ProgramSpace, machine: Machine) -> ProgramSpace:
    """Return the program with only the variants this machine can run.

    Used by the pooled control, where the machine has one bank, so every site
    is restricted to the implementations drawing on it.
    """

    sites = []
    for site in program.sites:
        allowed = feasible_names(site, machine)
        if not allowed:
            allowed = list(site.variant_names)
        sites.append(
            Site(
                site_id=site.site_id,
                family=site.family,
                variants=tuple(site.variant(name) for name in allowed),
            )
        )
    return ProgramSpace(
        name=f"{program.name}_pooled",
        sites=tuple(sites),
        edges=program.edges,
        meta=program.meta,
    )


def _measure(program, machine, control, setting, extra) -> dict[str, object]:
    """Run the comparison once and return a row."""

    uniform = select_uniform_oracle(program, machine)
    simple = {}
    for policy in SIMPLE_BASELINES:
        simple[policy] = run_policy(policy, program, machine).makespan
    best_simple = min(simple, key=lambda name: simple[name])
    oracle = best_oracle(program, machine, limit=ORACLE_LIMIT)
    row = {
        "kernel": program.name,
        "control": control,
        "setting": setting,
        "t_rate": round(machine.rate(T), 4),
        "ccz_rate": round(machine.rate(CCZ), 4),
        "makespan_uniform_oracle": uniform.makespan,
        "makespan_best_simple": simple[best_simple],
        "best_simple_baseline": best_simple,
        "makespan_global_oracle": oracle.makespan,
        "oracle_exhaustive": int(oracle.exhaustive),
        "headroom_over_uniform_oracle": round(
            ratio(uniform.makespan - oracle.makespan, uniform.makespan), 4
        ),
        "headroom_over_best_simple": round(
            ratio(simple[best_simple] - oracle.makespan, simple[best_simple]), 4
        ),
        "oracle_heterogeneity": round(heterogeneity(program, oracle.assignment), 4),
        "oracle_ccz_share_of_demand": round(mixture(oracle.counts), 4),
    }
    row.update(extra)
    return row


def _rows_for_kernel(name: str) -> list[dict[str, object]]:
    """Return every control row for one kernel."""

    catalogue = {program.name: program for program in kernels()}
    program = catalogue[name]
    rows: list[dict[str, object]] = []

    for capacity in CAPACITIES:
        for share in SHARES:
            base = {
                "capacity_target": capacity,
                "ccz_share": share,
                "buffer": 32,
                "latency": 0,
                "p_success": 1.0,
                "seed": 0,
            }

            machine = machine_for_capacity(capacity, share)
            rows.append(_measure(program, machine, "baseline", "two banks", dict(base)))

            # Pooled control: all capacity in one bank, only its variants offered.
            for pooled_share, label in ((0.0, "pooled into T"), (1.0, "pooled into CCZ")):
                pooled_machine = machine_for_capacity(capacity, pooled_share)
                pooled_program = _single_bank_program(program, pooled_machine)
                rows.append(
                    _measure(
                        pooled_program,
                        pooled_machine,
                        "pooled",
                        label,
                        dict(base, ccz_share=pooled_share),
                    )
                )

            # Conversion control: the banks become partly interchangeable.
            for conversions, label in (
                ((CATALYZED_CCZ_TO_T,), "CCZ->2T only"),
                ((CATALYZED_CCZ_TO_T, T_TO_CCZ_DISTILLATION), "both directions"),
            ):
                converting = machine_for_capacity(capacity, share, conversions=conversions)
                rows.append(
                    _measure(program, converting, "conversion", label, dict(base))
                )

    # Robustness sweeps at one representative operating point.
    for buffer in (2, 8, 32, 128, UNBOUNDED):
        machine = machine_for_capacity(0.5, 0.5, buffer_capacity=buffer)
        rows.append(
            _measure(
                program,
                machine,
                "buffer",
                f"B={buffer}",
                {
                    "capacity_target": 0.5,
                    "ccz_share": 0.5,
                    "buffer": buffer,
                    "latency": 0,
                    "p_success": 1.0,
                    "seed": 0,
                },
            )
        )
    for latency in (0, 10, 50, 200):
        machine = machine_for_capacity(0.5, 0.5, latency=latency)
        rows.append(
            _measure(
                program,
                machine,
                "latency",
                f"L={latency}",
                {
                    "capacity_target": 0.5,
                    "ccz_share": 0.5,
                    "buffer": 32,
                    "latency": latency,
                    "p_success": 1.0,
                    "seed": 0,
                },
            )
        )
    for p_success in (1.0, 0.9, 0.7):
        for seed in (0, 1, 2):
            if p_success == 1.0 and seed > 0:
                continue
            machine = machine_for_capacity(0.5, 0.5, p_success=p_success, seed=seed)
            rows.append(
                _measure(
                    program,
                    machine,
                    "failures",
                    f"p={p_success:g} seed={seed}",
                    {
                        "capacity_target": 0.5,
                        "ccz_share": 0.5,
                        "buffer": 32,
                        "latency": 0,
                        "p_success": p_success,
                        "seed": seed,
                    },
                )
            )
    return rows


def main() -> None:
    """Run every control and write the table."""

    rows: list[dict[str, object]] = []
    with Pool(processes=4) as pool:
        for done, produced in enumerate(pool.imap_unordered(_rows_for_kernel, SUBSET), 1):
            rows.extend(produced)
            print(f"  done {done}/{len(SUBSET)}", flush=True)
    rows.sort(key=lambda row: (str(row["kernel"]), str(row["control"]), str(row["setting"])))
    write_csv(RESULT_DIR / "mrc2_controls.csv", rows, FIELDS)

    print()
    print(f"{'control':12s} {'setting':18s} {'n':>4s} {'vsUnif_med':>10s} {'vsUnif_p90':>10s} {'vsUnif_max':>10s} {'het':>5s}")
    seen: list[tuple[str, str]] = []
    for row in rows:
        token = (row["control"], row["setting"])
        if token in seen:
            continue
        seen.append(token)
    for control, setting in seen:
        subset = [
            row for row in rows if row["control"] == control and row["setting"] == setting
        ]
        stats = summarize(row["headroom_over_uniform_oracle"] for row in subset)
        het = summarize(row["oracle_heterogeneity"] for row in subset)
        print(
            f"{control:12s} {setting:18s} {len(subset):4d} {stats['median']:10.3f} "
            f"{stats['p90']:10.3f} {stats['max']:10.3f} {het['mean']:5.2f}"
        )


if __name__ == "__main__":
    main()
