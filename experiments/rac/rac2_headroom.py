"""Gate 2: is there headroom a compiler can actually exploit?

Knowing that T-depth picks badly is not a contribution. This script asks
whether a compiler can do better, and how much better than the strongest
simple thing it can be. The baseline ladder is deliberately stacked against
the proposed mechanism:

* A/B are the static-metric compilers;
* B+ is an idealised static compiler that somehow always knows which of the
  two static metrics to trust in the current regime;
* C is the previous study's flow, T-depth selection with a smoothed static
  delivery-aware schedule;
* D and D+ are greedy resource-aware policies that may *simulate* one site at
  a time, D+ additionally knowing how much contention that site faces;
* D++ simulates every family-uniform implementation of the whole program and
  keeps the winner.

The proposed policy is the only one that never simulates: it scores candidates
with the analytic supply-constrained cost model alone. The reference is the
exhaustive optimum wherever the assignment space is small enough to enumerate.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_rac import (
    RESULT_DIR,
    assignment_space,
    heterogeneous,
    program_meta,
    programs,
    ratio,
    site_count,
    summarize,
    variant_profile,
    write_csv,
)

from ftqc_delivery.rac.execution import execute
from ftqc_delivery.rac.regimes import main_regimes
from ftqc_delivery.rac.select import (
    best_uniform,
    legacy_schedule_makespan,
    reference_best,
    select_local_resource_greedy,
    select_resource_aware,
    select_share_aware_greedy,
    select_static,
)


BASELINES = (
    "min_t_count",
    "min_t_depth",
    "best_static",
    "legacy_smooth",
    "local_resource_greedy",
    "share_aware_greedy",
    "best_uniform",
)

CASE_FIELDS = [
    "program",
    "kernel",
    "concurrency",
    "decision_sites",
    "assignment_space",
    "regime",
    "rate",
    "buffer",
    "reference",
    "reference_exhaustive",
    "reference_heterogeneous",
    *[f"makespan_{name}" for name in BASELINES],
    "makespan_resource_aware",
    *[f"regret_{name}" for name in BASELINES],
    "regret_resource_aware",
    "strongest_baseline",
    "strongest_baseline_makespan",
    "headroom_available",
    "headroom_captured",
    "ours_heterogeneous",
    "ours_profile",
    "ours_cost_evaluations",
    "ours_ancillas",
    "best_static_ancillas",
    "ours_overflow",
    "ours_stalls",
]

SUMMARY_FIELDS = [
    "regime",
    "rate",
    "cases",
    "exhaustive_cases",
    *[f"regret_{name}_median" for name in BASELINES],
    "regret_resource_aware_median",
    *[f"regret_{name}_mean" for name in BASELINES],
    "regret_resource_aware_mean",
    "regret_resource_aware_p90",
    "regret_resource_aware_max",
    "cases_with_headroom",
    "headroom_captured_median",
    "headroom_captured_mean",
    "ours_beats_strongest_baseline",
    "ours_heterogeneous_rate",
]


def _makespan(program, assignment, supply, clifford_weight=1):
    return execute(
        program.instantiate(assignment),
        supply,
        clifford_weight=clifford_weight,
        record_trace=False,
    ).makespan


def _rows_for_program(index: int) -> list[dict[str, object]]:
    """Return every Gate 2 row for one pilot program."""

    case_rows: list[dict[str, object]] = []
    program = programs()[index]
    if True:
        meta = program_meta(program)
        for regime in main_regimes():
            supply = regime.supply
            makespans: dict[str, int] = {}
            assignments: dict[str, dict[str, str]] = {}

            assignments["min_t_count"] = select_static(program, "t_count")
            assignments["min_t_depth"] = select_static(program, "t_depth")
            for name in ("min_t_count", "min_t_depth"):
                makespans[name] = _makespan(program, assignments[name], supply)

            if makespans["min_t_count"] <= makespans["min_t_depth"]:
                assignments["best_static"] = assignments["min_t_count"]
            else:
                assignments["best_static"] = assignments["min_t_depth"]
            makespans["best_static"] = min(
                makespans["min_t_count"], makespans["min_t_depth"]
            )

            assignments["legacy_smooth"] = assignments["min_t_depth"]
            makespans["legacy_smooth"] = legacy_schedule_makespan(
                program.instantiate(assignments["min_t_depth"]), supply
            )

            assignments["local_resource_greedy"], _ = select_local_resource_greedy(
                program, supply
            )
            makespans["local_resource_greedy"] = _makespan(
                program, assignments["local_resource_greedy"], supply
            )

            assignments["share_aware_greedy"], _ = select_share_aware_greedy(
                program, supply
            )
            makespans["share_aware_greedy"] = _makespan(
                program, assignments["share_aware_greedy"], supply
            )

            assignments["best_uniform"], makespans["best_uniform"] = best_uniform(
                program, supply
            )

            ours_assignment, evaluations = select_resource_aware(program, supply)
            ours_dag = program.instantiate(ours_assignment)
            ours_trace = execute(ours_dag, supply, record_trace=True)
            makespans["resource_aware"] = ours_trace.makespan

            reference = reference_best(
                program,
                supply,
                extra=[ours_assignment, *assignments.values()],
            )

            strongest = min(BASELINES, key=lambda name: makespans[name])
            strongest_value = makespans[strongest]
            headroom = strongest_value - reference.makespan
            captured = (
                ratio(strongest_value - makespans["resource_aware"], headroom)
                if headroom > 0
                else float("nan")
            )

            row: dict[str, object] = {
                "program": program.name,
                "kernel": meta.get("kernel", ""),
                "concurrency": meta.get("concurrency", ""),
                "decision_sites": site_count(program),
                "assignment_space": assignment_space(program),
                "regime": regime.name,
                "rate": round(regime.rate, 4),
                "buffer": supply.buffer_capacity,
                "reference": reference.makespan,
                "reference_exhaustive": int(reference.exhaustive),
                "reference_heterogeneous": int(heterogeneous(reference.assignment)),
                "strongest_baseline": strongest,
                "strongest_baseline_makespan": strongest_value,
                "headroom_available": headroom,
                "headroom_captured": round(captured, 4) if captured == captured else "",
                "ours_heterogeneous": int(heterogeneous(ours_assignment)),
                "ours_profile": variant_profile(ours_assignment),
                "ours_cost_evaluations": evaluations,
                "ours_ancillas": program.ancillas(ours_assignment),
                "best_static_ancillas": program.ancillas(assignments["best_static"]),
                "ours_overflow": ours_trace.overflow,
                "ours_stalls": ours_trace.supply_stall_cycles,
            }
            for name in BASELINES:
                row[f"makespan_{name}"] = makespans[name]
                row[f"regret_{name}"] = round(
                    ratio(makespans[name], reference.makespan), 4
                )
            row["makespan_resource_aware"] = makespans["resource_aware"]
            row["regret_resource_aware"] = round(
                ratio(makespans["resource_aware"], reference.makespan), 4
            )
            case_rows.append(row)

    return case_rows


def main() -> None:
    """Run the Gate 2 sweep and write per-case and per-regime tables."""

    indices = list(range(len(programs())))
    case_rows: list[dict[str, object]] = []
    with Pool(processes=4) as pool:
        for done, rows in enumerate(pool.imap_unordered(_rows_for_program, indices), 1):
            case_rows.extend(rows)
            print(f"  done {done}/{len(indices)}", flush=True)
    case_rows.sort(key=lambda row: (str(row["program"]), float(row["rate"])))

    summary_rows = []
    for regime_name in sorted({row["regime"] for row in case_rows}, key=lambda n: n):
        subset = [row for row in case_rows if row["regime"] == regime_name]
        with_headroom = [row for row in subset if row["headroom_available"] > 0]
        captured = [
            float(row["headroom_captured"])
            for row in with_headroom
            if row["headroom_captured"] != ""
        ]
        summary: dict[str, object] = {
            "regime": regime_name,
            "rate": subset[0]["rate"],
            "cases": len(subset),
            "exhaustive_cases": sum(row["reference_exhaustive"] for row in subset),
            "cases_with_headroom": len(with_headroom),
            "headroom_captured_median": summarize(captured)["median"],
            "headroom_captured_mean": summarize(captured)["mean"],
            "ours_beats_strongest_baseline": sum(
                1
                for row in subset
                if row["makespan_resource_aware"] < row["strongest_baseline_makespan"]
            ),
            "ours_heterogeneous_rate": round(
                sum(row["ours_heterogeneous"] for row in subset) / len(subset), 4
            ),
        }
        for name in (*BASELINES, "resource_aware"):
            stats = summarize(row[f"regret_{name}"] for row in subset)
            summary[f"regret_{name}_median"] = stats["median"]
            summary[f"regret_{name}_mean"] = stats["mean"]
            if name == "resource_aware":
                summary["regret_resource_aware_p90"] = stats["p90"]
                summary["regret_resource_aware_max"] = stats["max"]
        summary_rows.append(summary)

    write_csv(RESULT_DIR / "rac2_cases.csv", case_rows, CASE_FIELDS)
    write_csv(RESULT_DIR / "rac2_summary.csv", summary_rows, SUMMARY_FIELDS)

    print()
    print(
        f"{'regime':10s} {'Tcount':>7s} {'Tdepth':>7s} {'bStat':>7s} {'legacy':>7s} "
        f"{'greedy':>7s} {'share':>7s} {'bUnif':>7s} {'ours':>7s} {'capt':>6s} {'wins':>5s}"
    )
    for row in summary_rows:
        print(
            f"{row['regime']:10s} {row['regret_min_t_count_median']:7.3f} "
            f"{row['regret_min_t_depth_median']:7.3f} {row['regret_best_static_median']:7.3f} "
            f"{row['regret_legacy_smooth_median']:7.3f} "
            f"{row['regret_local_resource_greedy_median']:7.3f} "
            f"{row['regret_share_aware_greedy_median']:7.3f} "
            f"{row['regret_best_uniform_median']:7.3f} "
            f"{row['regret_resource_aware_median']:7.3f} "
            f"{row['headroom_captured_median']:6.3f} "
            f"{row['ours_beats_strongest_baseline']:5d}"
        )


if __name__ == "__main__":
    main()
