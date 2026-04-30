"""Experiment 6: optimal / near-optimal gap analysis."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from common_v3 import (
    REPORT_SCHEDULES,
    RESULT_DIR_V3,
    near_optimal_candidates,
    schedule_metrics,
    small_v3_cases,
    write_csv,
)


FIELDNAMES = [
    "workload",
    "seed",
    "C",
    "B",
    "schedule",
    "T_static",
    "T_exe",
    "T_exe_opt",
    "gap_Texe",
    "gap_Texe_percent",
    "Delta_max",
    "Delta_max_opt",
    "gap_Delta",
    "stall_cycles",
    "stall_cycles_opt",
    "gap_stall",
    "L_backlog",
    "L_backlog_opt",
    "gap_L_backlog",
    "BacklogArea",
    "BacklogArea_opt",
    "gap_BacklogArea",
    "is_near_optimal_0cycle",
    "is_near_optimal_1cycle",
    "is_near_optimal_5percent",
]


SUMMARY_FIELDNAMES = [
    "schedule",
    "mean_gap_Texe",
    "median_gap_Texe",
    "max_gap_Texe",
    "fraction_within_0cycle",
    "fraction_within_1cycle",
    "fraction_within_5percent",
]


def main() -> None:
    rows = []
    for case in small_v3_cases():
        for capacity in [1, 2]:
            for buffer in [0, 2]:
                candidates = near_optimal_candidates(case, capacity, buffer)
                metrics = {
                    name: schedule_metrics(case, schedule, capacity, buffer)
                    for name, schedule in candidates.items()
                }
                best_name, opt = min(
                    metrics.items(),
                    key=lambda item: (item[1]["T_exe"], item[1]["T_static"], item[0]),
                )
                del best_name
                for schedule_name in REPORT_SCHEDULES + ["optimal_or_near_optimal"]:
                    values = opt if schedule_name == "optimal_or_near_optimal" else metrics[schedule_name]
                    gap_t = values["T_exe"] - opt["T_exe"]
                    gap_percent = gap_t / opt["T_exe"] if opt["T_exe"] else 0.0
                    rows.append(
                        {
                            "workload": case.workload,
                            "seed": case.seed,
                            "C": capacity,
                            "B": buffer,
                            "schedule": schedule_name,
                            "T_static": values["T_static"],
                            "T_exe": values["T_exe"],
                            "T_exe_opt": opt["T_exe"],
                            "gap_Texe": gap_t,
                            "gap_Texe_percent": gap_percent,
                            "Delta_max": values["Delta_max"],
                            "Delta_max_opt": opt["Delta_max"],
                            "gap_Delta": values["Delta_max"] - opt["Delta_max"],
                            "stall_cycles": values["stall_cycles"],
                            "stall_cycles_opt": opt["stall_cycles"],
                            "gap_stall": values["stall_cycles"] - opt["stall_cycles"],
                            "L_backlog": values["L_backlog"],
                            "L_backlog_opt": opt["L_backlog"],
                            "gap_L_backlog": values["L_backlog"] - opt["L_backlog"],
                            "BacklogArea": values["BacklogArea"],
                            "BacklogArea_opt": opt["BacklogArea"],
                            "gap_BacklogArea": values["BacklogArea"] - opt["BacklogArea"],
                            "is_near_optimal_0cycle": int(gap_t <= 0),
                            "is_near_optimal_1cycle": int(gap_t <= 1),
                            "is_near_optimal_5percent": int(gap_percent <= 0.05),
                        }
                    )

    write_csv(RESULT_DIR_V3 / "exp6_optimal_gap_analysis.csv", rows, FIELDNAMES)

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["schedule"])].append(row)
    summary = []
    for schedule_name, schedule_rows in sorted(grouped.items()):
        gaps = [float(row["gap_Texe"]) for row in schedule_rows]
        summary.append(
            {
                "schedule": schedule_name,
                "mean_gap_Texe": sum(gaps) / len(gaps),
                "median_gap_Texe": median(gaps),
                "max_gap_Texe": max(gaps),
                "fraction_within_0cycle": sum(
                    int(row["is_near_optimal_0cycle"]) for row in schedule_rows
                )
                / len(schedule_rows),
                "fraction_within_1cycle": sum(
                    int(row["is_near_optimal_1cycle"]) for row in schedule_rows
                )
                / len(schedule_rows),
                "fraction_within_5percent": sum(
                    int(row["is_near_optimal_5percent"]) for row in schedule_rows
                )
                / len(schedule_rows),
            }
        )
    write_csv(RESULT_DIR_V3 / "exp6_optimal_gap_summary.csv", summary, SUMMARY_FIELDNAMES)
    print(f"Wrote {len(rows)} rows to {RESULT_DIR_V3 / 'exp6_optimal_gap_analysis.csv'}")


if __name__ == "__main__":
    main()
