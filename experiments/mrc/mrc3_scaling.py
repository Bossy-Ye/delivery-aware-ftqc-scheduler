"""Does the mixture stay optimal, and stay worth having, as programs grow?

Concurrency and operand size are scaled independently. The exact optimum is
available far beyond the point where enumerating assignments becomes
impossible, because sites within a stage are interchangeable: the optimum over
assignments equals the optimum over multisets of choices per stage, and that
space grows polynomially rather than exponentially in the number of lanes.

Selector runtime is recorded alongside, so the cost of the decision can be
weighed against what it buys.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import RESULT_DIR, SIMPLE_BASELINES, ratio, summarize, write_csv

from ftqc_delivery.mrc.kernels import (
    assignment_space,
    multiplier_tree,
    oracle_bank,
    trotter_layers,
)
from ftqc_delivery.mrc.policies import (
    best_oracle,
    heterogeneity,
    mixture,
    run_policy,
    select_sim_descent,
    select_uniform_oracle,
    symmetric_space,
)
from ftqc_delivery.mrc.resources import CCZ, T, machine_for_capacity


FIELDS = [
    "family",
    "kernel",
    "concurrency",
    "size",
    "decision_sites",
    "assignment_space",
    "symmetric_space",
    "capacity_target",
    "ccz_share",
    "makespan_uniform_oracle",
    "makespan_best_simple",
    "best_simple_baseline",
    "makespan_sim_descent",
    "makespan_global_oracle",
    "oracle_exhaustive",
    "headroom_over_uniform_oracle",
    "headroom_over_best_simple",
    "sim_descent_regret",
    "oracle_heterogeneity",
    "oracle_ccz_share_of_demand",
    "seconds_uniform_oracle",
    "seconds_sim_descent",
    "seconds_global_oracle",
]

CAPACITIES = (0.25, 0.5, 1.0)
SHARES = (0.25, 0.5, 0.75)


def _cases():
    """Yield (family, kernel, concurrency, size) tuples spanning the scaling axes."""

    # One stage, so the symmetry reduction leaves a space that grows
    # polynomially in the number of lanes and the optimum stays exact.
    for lanes in (1, 2, 3, 4, 6, 8, 12, 16):
        yield ("trotter", trotter_layers(terms=lanes, layers=1, bits=10), lanes, 10)
    for bits in (4, 8, 16, 32):
        yield ("trotter_size", trotter_layers(terms=4, layers=1, bits=bits), 4, bits)
    for lanes in (2, 4, 8, 16):
        yield ("oracle_bank", oracle_bank(controls=16, lanes=lanes), lanes, 16)
    for rows in (4, 8, 16):
        yield ("multiplier", multiplier_tree(width=32, rows=rows), rows // 2, 32)
    for width in (16, 32, 64, 128):
        yield ("multiplier_size", multiplier_tree(width=width, rows=8), 4, width)


def _job(index: int) -> list[dict[str, object]]:
    """Run one scaling case across the machine grid."""

    family, program, concurrency, size = list(_cases())[index]
    rows: list[dict[str, object]] = []
    for capacity in CAPACITIES:
        for share in SHARES:
            machine = machine_for_capacity(capacity, share)
            uniform = select_uniform_oracle(program, machine)
            simple = {
                policy: run_policy(policy, program, machine).makespan
                for policy in SIMPLE_BASELINES
            }
            best_simple = min(simple, key=lambda name: simple[name])
            descent = select_sim_descent(program, machine)
            oracle = best_oracle(
                program,
                machine,
                time_budget=240.0,
                extra_seeds=[descent.assignment, uniform.assignment],
            )
            rows.append(
                {
                    "family": family,
                    "kernel": program.name,
                    "concurrency": concurrency,
                    "size": size,
                    "decision_sites": sum(
                        1 for site in program.sites if len(site.variants) > 1
                    ),
                    "assignment_space": assignment_space(program),
                    "symmetric_space": symmetric_space(program, machine),
                    "capacity_target": capacity,
                    "ccz_share": share,
                    "makespan_uniform_oracle": uniform.makespan,
                    "makespan_best_simple": simple[best_simple],
                    "best_simple_baseline": best_simple,
                    "makespan_sim_descent": descent.makespan,
                    "makespan_global_oracle": oracle.makespan,
                    "oracle_exhaustive": int(oracle.exhaustive),
                    "headroom_over_uniform_oracle": round(
                        ratio(uniform.makespan - oracle.makespan, uniform.makespan), 4
                    ),
                    "headroom_over_best_simple": round(
                        ratio(simple[best_simple] - oracle.makespan, simple[best_simple]),
                        4,
                    ),
                    "sim_descent_regret": round(
                        ratio(descent.makespan, oracle.makespan), 4
                    ),
                    "oracle_heterogeneity": round(
                        heterogeneity(program, oracle.assignment), 4
                    ),
                    "oracle_ccz_share_of_demand": round(mixture(oracle.counts), 4),
                    "seconds_uniform_oracle": round(uniform.seconds, 4),
                    "seconds_sim_descent": round(descent.seconds, 4),
                    "seconds_global_oracle": round(oracle.seconds, 4),
                }
            )
    return rows


def main() -> None:
    """Run the scaling study and write the table."""

    indices = list(range(len(list(_cases()))))
    rows: list[dict[str, object]] = []
    with Pool(processes=4) as pool:
        for done, produced in enumerate(pool.imap_unordered(_job, indices), 1):
            rows.extend(produced)
            print(f"  done {done}/{len(indices)}", flush=True)
    rows.sort(key=lambda row: (str(row["family"]), row["concurrency"], row["size"]))
    write_csv(RESULT_DIR / "mrc3_scaling.csv", rows, FIELDS)

    print()
    print(
        f"{'family':16s} {'conc':>5s} {'size':>5s} {'exh':>4s} {'vsUnif_med':>10s} "
        f"{'vsSimple_med':>12s} {'het':>5s} {'descent':>8s} {'orc_s':>7s}"
    )
    keys: list[tuple[str, int, int]] = []
    for row in rows:
        token = (row["family"], row["concurrency"], row["size"])
        if token not in keys:
            keys.append(token)
    for family, concurrency, size in keys:
        subset = [
            row
            for row in rows
            if row["family"] == family
            and row["concurrency"] == concurrency
            and row["size"] == size
        ]
        uniform = summarize(row["headroom_over_uniform_oracle"] for row in subset)
        simple = summarize(row["headroom_over_best_simple"] for row in subset)
        het = summarize(row["oracle_heterogeneity"] for row in subset)
        descent = summarize(row["sim_descent_regret"] for row in subset)
        seconds = summarize(row["seconds_global_oracle"] for row in subset)
        print(
            f"{family:16s} {concurrency:5d} {size:5d} "
            f"{sum(row['oracle_exhaustive'] for row in subset):4d} "
            f"{uniform['median']:10.3f} {simple['median']:12.3f} {het['mean']:5.2f} "
            f"{descent['mean']:8.3f} {seconds['mean']:7.1f}"
        )


if __name__ == "__main__":
    main()
