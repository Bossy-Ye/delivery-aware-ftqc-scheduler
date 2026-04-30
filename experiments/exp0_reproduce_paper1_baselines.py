"""Experiment 0: baseline sanity check."""

from __future__ import annotations

from common import B_VALUES, C_VALUES, RESULT_DIR, SCHEDULES, build_workloads, evaluate_case, write_csv


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
    "feasible",
]


def main() -> None:
    rows = []
    workloads = build_workloads()[:6]
    for case in workloads:
        for capacity in C_VALUES:
            for buffer in B_VALUES:
                for schedule in SCHEDULES[:3]:
                    rows.append(evaluate_case(case, schedule, capacity, buffer))
    write_csv(RESULT_DIR / "exp0_baseline_check.csv", rows, FIELDNAMES)
    print(f"Wrote {len(rows)} rows to {RESULT_DIR / 'exp0_baseline_check.csv'}")


if __name__ == "__main__":
    main()
