"""Does global heterogeneous selection beat uniform and local policies?

For every kernel and every machine in the experiment matrix this script runs
each compilation policy and the global optimum, and records the gap between
them. The metric that answers the question is ``headroom_over_uniform_oracle``:
the fraction of makespan that mixing implementations *within a family* buys
over the best implementation a library-style compiler could pick for that
family. Every other comparison is context for that one.

Capacity is swept as well as the split between the banks, because a program
whose runtime is set by its dependency structure cannot be helped by any
resource decision; the ``supply_pressure`` column says which regime each case
is in.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import (
    RESULT_DIR,
    SIMPLE_BASELINES,
    capacity_of,
    data_tiles,
    kernel_meta,
    kernels,
    ratio,
    sites_and_space,
    summarize,
    supply_pressure,
    write_csv,
)

from ftqc_delivery.mrc.policies import (
    POLICIES,
    best_oracle,
    heterogeneity,
    mixture,
    run_policy,
    space_time,
)
from ftqc_delivery.mrc.resources import CCZ, T, machine_for_capacity


#: Total production capacity in T-equivalent states per logical cycle.
CAPACITIES = (0.25, 0.5, 1.0, 2.0)

#: Fraction of that capacity held by the CCZ bank.
CCZ_SHARES = (0.1, 0.25, 0.5, 0.75, 0.9)

ORACLE_LIMIT = 40_000

FIELDS = [
    "kernel",
    "family",
    "concurrency",
    "decision_sites",
    "assignment_space",
    "capacity_target",
    "ccz_share",
    "t_rate",
    "ccz_rate",
    "capacity_achieved",
    "imbalance",
    "factory_tiles",
    "supply_pressure",
    *[f"makespan_{policy}" for policy in POLICIES],
    "makespan_global_oracle",
    "oracle_exhaustive",
    *[f"regret_{policy}" for policy in POLICIES],
    "best_simple_baseline",
    "makespan_best_simple",
    "headroom_over_uniform_oracle",
    "headroom_over_best_simple",
    "oracle_heterogeneity",
    "oracle_ccz_share_of_demand",
    "uniform_ccz_share_of_demand",
    "oracle_space_time",
    "uniform_space_time",
    "space_time_ratio",
    *[f"seconds_{policy}" for policy in POLICIES],
    "seconds_global_oracle",
]


def _rows_for_kernel(index: int) -> list[dict[str, object]]:
    """Return every row of the matrix for one kernel."""

    program = kernels()[index]
    meta = kernel_meta(program)
    site_count, space = sites_and_space(program)
    tiles = data_tiles(program)
    rows: list[dict[str, object]] = []

    for capacity in CAPACITIES:
        for share in CCZ_SHARES:
            machine = machine_for_capacity(capacity, share)
            outcomes = {policy: run_policy(policy, program, machine) for policy in POLICIES}
            oracle = best_oracle(
                program,
                machine,
                limit=ORACLE_LIMIT,
                extra_seeds=[outcome.assignment for outcome in outcomes.values()],
            )

            uniform = outcomes["uniform_oracle"]
            best_simple = min(SIMPLE_BASELINES, key=lambda name: outcomes[name].makespan)
            best_simple_makespan = outcomes[best_simple].makespan

            row: dict[str, object] = {
                "kernel": program.name,
                "family": meta.get("kernel", ""),
                "concurrency": meta.get("concurrency", ""),
                "decision_sites": site_count,
                "assignment_space": space,
                "capacity_target": capacity,
                "ccz_share": share,
                "t_rate": round(machine.rate(T), 4),
                "ccz_rate": round(machine.rate(CCZ), 4),
                "capacity_achieved": round(capacity_of(machine), 4),
                "imbalance": round(machine.imbalance, 4),
                "factory_tiles": machine.factory_tiles,
                "supply_pressure": round(
                    supply_pressure(program, oracle.assignment, machine), 4
                ),
                "makespan_global_oracle": oracle.makespan,
                "oracle_exhaustive": int(oracle.exhaustive),
                "best_simple_baseline": best_simple,
                "makespan_best_simple": best_simple_makespan,
                "headroom_over_uniform_oracle": round(
                    ratio(uniform.makespan - oracle.makespan, uniform.makespan), 4
                ),
                "headroom_over_best_simple": round(
                    ratio(best_simple_makespan - oracle.makespan, best_simple_makespan), 4
                ),
                "oracle_heterogeneity": round(heterogeneity(program, oracle.assignment), 4),
                "oracle_ccz_share_of_demand": round(mixture(oracle.counts), 4),
                "uniform_ccz_share_of_demand": round(mixture(uniform.counts), 4),
                "oracle_space_time": space_time(
                    program, oracle.assignment, machine, oracle.makespan, tiles
                ),
                "uniform_space_time": space_time(
                    program, uniform.assignment, machine, uniform.makespan, tiles
                ),
                "seconds_global_oracle": round(oracle.seconds, 4),
            }
            row["space_time_ratio"] = round(
                ratio(row["oracle_space_time"], row["uniform_space_time"]), 4
            )
            for policy in POLICIES:
                row[f"makespan_{policy}"] = outcomes[policy].makespan
                row[f"regret_{policy}"] = round(
                    ratio(outcomes[policy].makespan, oracle.makespan), 4
                )
                row[f"seconds_{policy}"] = round(outcomes[policy].seconds, 4)
            rows.append(row)
    return rows


def main() -> None:
    """Run the matrix and write the per-case and summary tables."""

    indices = list(range(len(kernels())))
    rows: list[dict[str, object]] = []
    with Pool(processes=4) as pool:
        for done, produced in enumerate(pool.imap_unordered(_rows_for_kernel, indices), 1):
            rows.extend(produced)
            print(f"  done {done}/{len(indices)}", flush=True)
    rows.sort(key=lambda row: (str(row["kernel"]), row["capacity_target"], row["ccz_share"]))
    write_csv(RESULT_DIR / "mrc1_cases.csv", rows, FIELDS)

    summary_fields = [
        "capacity_target",
        "ccz_share",
        "cases",
        "exhaustive_cases",
        "headroom_over_uniform_median",
        "headroom_over_uniform_p90",
        "headroom_over_uniform_max",
        "headroom_over_best_simple_median",
        "headroom_over_best_simple_p90",
        "headroom_over_best_simple_max",
        "cases_over_5pct",
        "oracle_heterogeneity_mean",
        "regret_sim_descent_mean",
        "regret_share_aware_greedy_mean",
        "regret_uniform_oracle_mean",
    ]
    summary_rows = []
    for capacity in CAPACITIES:
        for share in CCZ_SHARES:
            subset = [
                row
                for row in rows
                if row["capacity_target"] == capacity and row["ccz_share"] == share
            ]
            if not subset:
                continue
            uniform = summarize(row["headroom_over_uniform_oracle"] for row in subset)
            simple = summarize(row["headroom_over_best_simple"] for row in subset)
            summary_rows.append(
                {
                    "capacity_target": capacity,
                    "ccz_share": share,
                    "cases": len(subset),
                    "exhaustive_cases": sum(row["oracle_exhaustive"] for row in subset),
                    "headroom_over_uniform_median": uniform["median"],
                    "headroom_over_uniform_p90": uniform["p90"],
                    "headroom_over_uniform_max": uniform["max"],
                    "headroom_over_best_simple_median": simple["median"],
                    "headroom_over_best_simple_p90": simple["p90"],
                    "headroom_over_best_simple_max": simple["max"],
                    "cases_over_5pct": sum(
                        1 for row in subset if row["headroom_over_best_simple"] > 0.05
                    ),
                    "oracle_heterogeneity_mean": summarize(
                        row["oracle_heterogeneity"] for row in subset
                    )["mean"],
                    "regret_sim_descent_mean": summarize(
                        row["regret_sim_descent"] for row in subset
                    )["mean"],
                    "regret_share_aware_greedy_mean": summarize(
                        row["regret_share_aware_greedy"] for row in subset
                    )["mean"],
                    "regret_uniform_oracle_mean": summarize(
                        row["regret_uniform_oracle"] for row in subset
                    )["mean"],
                }
            )
    write_csv(RESULT_DIR / "mrc1_summary.csv", summary_rows, summary_fields)

    print()
    print(
        f"{'cap':>5s} {'ccz%':>5s} {'n':>4s} {'exh':>4s} "
        f"{'vsUnif_med':>10s} {'vsUnif_p90':>10s} {'vsUnif_max':>10s} "
        f"{'vsSimple_med':>12s} {'vsSimple_max':>12s} {'>5%':>4s} {'het':>5s}"
    )
    for row in summary_rows:
        print(
            f"{row['capacity_target']:5.2f} {row['ccz_share']:5.2f} {row['cases']:4d} "
            f"{row['exhaustive_cases']:4d} "
            f"{row['headroom_over_uniform_median']:10.3f} "
            f"{row['headroom_over_uniform_p90']:10.3f} "
            f"{row['headroom_over_uniform_max']:10.3f} "
            f"{row['headroom_over_best_simple_median']:12.3f} "
            f"{row['headroom_over_best_simple_max']:12.3f} "
            f"{row['cases_over_5pct']:4d} {row['oracle_heterogeneity_mean']:5.2f}"
        )


if __name__ == "__main__":
    main()
