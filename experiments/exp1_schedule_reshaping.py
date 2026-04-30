"""Experiment 1: schedule reshaping under fixed delivery capacity and buffer."""

from __future__ import annotations

from common import (
    B_VALUES,
    C_VALUES,
    RESULT_DIR,
    SCHEDULES,
    build_workloads,
    evaluate_case,
    generate_exp1_figures,
    reduction,
    write_csv,
)


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "schedule",
    "C",
    "B",
    "T_static",
    "T_exe",
    "stall_cycles",
    "slowdown",
    "Delta_max",
    "L_backlog",
    "static_depth_penalty",
    "Delta_reduction_vs_static",
    "Texe_reduction_vs_static",
    "Delta_reduction_vs_smooth",
    "Texe_reduction_vs_smooth",
    "Delta_reduction_vs_ca",
    "Texe_reduction_vs_ca",
]


def main() -> None:
    rows = []
    for case in build_workloads():
        for capacity in C_VALUES:
            for buffer in B_VALUES:
                group = [
                    evaluate_case(case, schedule, capacity, buffer)
                    for schedule in SCHEDULES
                ]
                by_schedule = {row["schedule"]: row for row in group}
                static_depth = by_schedule["static"]["T_static"]
                for row in group:
                    row["static_depth_penalty"] = row["T_static"] / static_depth
                    row["Delta_reduction_vs_static"] = reduction(
                        by_schedule["static"]["Delta_max"], row["Delta_max"]
                    )
                    row["Texe_reduction_vs_static"] = reduction(
                        by_schedule["static"]["T_exe"], row["T_exe"]
                    )
                    row["Delta_reduction_vs_smooth"] = reduction(
                        by_schedule["smooth"]["Delta_max"], row["Delta_max"]
                    )
                    row["Texe_reduction_vs_smooth"] = reduction(
                        by_schedule["smooth"]["T_exe"], row["T_exe"]
                    )
                    row["Delta_reduction_vs_ca"] = reduction(
                        by_schedule["capacity_aware"]["Delta_max"], row["Delta_max"]
                    )
                    row["Texe_reduction_vs_ca"] = reduction(
                        by_schedule["capacity_aware"]["T_exe"], row["T_exe"]
                    )
                    row.pop("feasible")
                    rows.append(row)

    out_path = RESULT_DIR / "exp1_schedule_reshaping.csv"
    write_csv(out_path, rows, FIELDNAMES)
    generate_exp1_figures(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
