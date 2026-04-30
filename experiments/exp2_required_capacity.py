"""Experiment 2: required delivery capacity threshold."""

from __future__ import annotations

from common import (
    B_VALUES,
    EPSILON_VALUES,
    RESULT_DIR,
    SCHEDULES,
    THRESHOLD_C_VALUES,
    build_workloads,
    generate_exp2_figure,
    make_schedule,
    write_csv,
    write_preliminary_report,
)
from ftqc_delivery.metrics.capacity_threshold import find_capacity_threshold
from ftqc_delivery.simulator.deterministic import simulate_deterministic


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "schedule",
    "B",
    "epsilon",
    "C_star",
    "achieved_slowdown",
    "T_static_at_C_star",
    "T_exe_at_C_star",
]


def main() -> None:
    rows = []
    for case in build_workloads():
        for buffer in B_VALUES:
            for epsilon in EPSILON_VALUES:
                for schedule_name in SCHEDULES:

                    def evaluator(capacity: int) -> tuple[int, int, float]:
                        schedule = make_schedule(schedule_name, case.dag, capacity, buffer)
                        result = simulate_deterministic(case.dag, schedule, capacity, buffer)
                        return result.T_static, result.T_exe, result.slowdown

                    threshold = find_capacity_threshold(THRESHOLD_C_VALUES, epsilon, evaluator)
                    rows.append(
                        {
                            "workload": case.workload,
                            "family": case.family,
                            "seed": case.seed,
                            "n": case.n,
                            "schedule": schedule_name,
                            "B": buffer,
                            "epsilon": epsilon,
                            "C_star": threshold.C_star if threshold.C_star is not None else "",
                            "achieved_slowdown": threshold.achieved_slowdown
                            if threshold.achieved_slowdown is not None
                            else "",
                            "T_static_at_C_star": threshold.T_static_at_C_star
                            if threshold.T_static_at_C_star is not None
                            else "",
                            "T_exe_at_C_star": threshold.T_exe_at_C_star
                            if threshold.T_exe_at_C_star is not None
                            else "",
                        }
                    )

    out_path = RESULT_DIR / "exp2_required_capacity.csv"
    write_csv(out_path, rows, FIELDNAMES)
    generate_exp2_figure(rows)
    exp1_path = RESULT_DIR / "exp1_schedule_reshaping.csv"
    if exp1_path.exists():
        write_preliminary_report(exp1_path, out_path)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
