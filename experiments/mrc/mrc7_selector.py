"""Phase 5: evaluate the stage-DP selector against the exact optimum.

Every case of the main matrix is re-solved with the stage-wise dynamic
program, in analytic mode, analytic mode with a small simulated refinement,
and stage-local simulation mode. The machine for each case is rebuilt from its
recorded parameters and the optimum is read from the recorded table, so the
selector is judged against the same proven optima as every baseline.
"""

from __future__ import annotations

import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import RESULT_DIR, kernels, ratio, read_csv, summarize, write_csv

from ftqc_delivery.mrc.resources import machine_for_capacity
from ftqc_delivery.mrc.stagedp import select_stage_dp


MODES = (("analytic", 0), ("analytic", 5), ("sim", 0))
FIELDS = [
    "kernel", "family", "capacity_target", "ccz_share", "oracle_exhaustive",
    "makespan_global_oracle", "makespan_uniform_oracle", "makespan_best_simple",
    "makespan_sim_descent", "seconds_sim_descent",
    "makespan_stage_dp_analytic", "seconds_stage_dp_analytic",
    "makespan_stage_dp_analytic_r5", "seconds_stage_dp_analytic_r5",
    "makespan_stage_dp_sim", "seconds_stage_dp_sim",
    "regret_stage_dp_analytic", "regret_stage_dp_analytic_r5", "regret_stage_dp_sim",
    "regret_sim_descent", "regret_best_simple",
]


def _job(name: str) -> list[dict[str, object]]:
    program = {k.name: k for k in kernels()}[name]
    rows = []
    for case in read_csv(RESULT_DIR / "mrc1_cases.csv"):
        if case["kernel"] != name:
            continue
        machine = machine_for_capacity(float(case["capacity_target"]), float(case["ccz_share"]))
        optimum = int(case["makespan_global_oracle"])
        row = {
            "kernel": name,
            "family": case["family"],
            "capacity_target": float(case["capacity_target"]),
            "ccz_share": float(case["ccz_share"]),
            "oracle_exhaustive": int(case["oracle_exhaustive"]),
            "makespan_global_oracle": optimum,
            "makespan_uniform_oracle": int(case["makespan_uniform_oracle"]),
            "makespan_best_simple": int(case["makespan_best_simple"]),
            "makespan_sim_descent": int(case["makespan_sim_descent"]),
            "seconds_sim_descent": float(case["seconds_sim_descent"]),
            "regret_sim_descent": round(ratio(int(case["makespan_sim_descent"]), optimum), 4),
            "regret_best_simple": round(ratio(int(case["makespan_best_simple"]), optimum), 4),
        }
        for mode, refine in MODES:
            label = f"stage_dp_{mode}" + (f"_r{refine}" if refine else "")
            start = time.perf_counter()
            outcome = select_stage_dp(program, machine, mode=mode, refine=refine)
            row[f"makespan_{label}"] = outcome.makespan
            row[f"seconds_{label}"] = round(time.perf_counter() - start, 4)
            row[f"regret_{label}"] = round(ratio(outcome.makespan, optimum), 4)
        rows.append(row)
    return rows


def main() -> None:
    names = [k.name for k in kernels()]
    rows: list[dict[str, object]] = []
    with Pool(processes=2) as pool:
        for done, produced in enumerate(pool.imap_unordered(_job, names), 1):
            rows.extend(produced)
            print(f"  done {done}/{len(names)}", flush=True)
    rows.sort(key=lambda r: (r["kernel"], r["capacity_target"], r["ccz_share"]))
    write_csv(RESULT_DIR / "mrc7_selector.csv", rows, FIELDS)

    exact = [r for r in rows if r["oracle_exhaustive"] == 1]
    print(f"\n{len(rows)} cases, {len(exact)} with a proven optimum")
    print(f"{'selector':28s} {'mean':>6s} {'median':>7s} {'p90':>6s} {'max':>6s} {'>1.05':>6s} {'>1.10':>6s} {'sec_med':>8s} {'sec_max':>8s}")
    for label in ("best_simple", "sim_descent", "stage_dp_analytic", "stage_dp_analytic_r5", "stage_dp_sim"):
        regrets = [r[f"regret_{label}"] for r in exact]
        stats = summarize(regrets)
        secs = summarize(r[f"seconds_{label}"] for r in exact) if f"seconds_{label}" in exact[0] else {"median": float("nan"), "max": float("nan")}
        print(f"{label:28s} {stats['mean']:6.3f} {stats['median']:7.3f} {stats['p90']:6.3f} {stats['max']:6.3f} "
              f"{sum(1 for x in regrets if x > 1.05):6d} {sum(1 for x in regrets if x > 1.10):6d} {secs['median']:8.3f} {secs['max']:8.3f}")
    print("\nby family (exact rows), mean regret of stage_dp_analytic_r5 vs best simple:")
    for fam in sorted({r["family"] for r in exact}):
        sub = [r for r in exact if r["family"] == fam]
        print(f"  {fam:16s} n={len(sub):3d} dp_r5={summarize(r['regret_stage_dp_analytic_r5'] for r in sub)['mean']:.3f} dp_sim={summarize(r['regret_stage_dp_sim'] for r in sub)['mean']:.3f} simple={summarize(r['regret_best_simple'] for r in sub)['mean']:.3f}")


if __name__ == "__main__":
    main()
