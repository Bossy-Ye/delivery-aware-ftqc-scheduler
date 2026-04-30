"""Experiment 1 V2: schedule reshaping with DA-v2 and smooth as main baseline."""

from __future__ import annotations

from common_v2 import (
    B_VALUES,
    C_VALUES,
    RESULT_DIR_V2,
    SCHEDULES_V2,
    add_pairwise_reductions,
    build_v2_workloads,
    evaluate_case_v2,
    load_da_v2_config,
    parameters_for_case,
    t_ref_asap,
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
    "slowdown_vs_own_static",
    "ratio_to_T_ref_asap",
    "Delta_max",
    "L_backlog",
    "max_backlog",
    "mean_backlog",
    "static_depth_penalty_vs_static",
    "Texe_reduction_vs_static",
    "Texe_reduction_vs_smooth",
    "Texe_reduction_vs_ca",
    "Texe_reduction_vs_DA_v1",
    "Delta_reduction_vs_static",
    "Delta_reduction_vs_smooth",
    "Delta_reduction_vs_ca",
    "Delta_reduction_vs_DA_v1",
    "stall_reduction_vs_static",
    "stall_reduction_vs_smooth",
    "stall_reduction_vs_ca",
    "stall_reduction_vs_DA_v1",
    "Lbacklog_reduction_vs_static",
    "Lbacklog_reduction_vs_smooth",
    "Lbacklog_reduction_vs_ca",
    "Lbacklog_reduction_vs_DA_v1",
]


def main() -> None:
    da_v2_config = load_da_v2_config()
    rows = []
    for case in build_v2_workloads():
        reference = t_ref_asap(case)
        c_values, b_values = parameters_for_case(case)
        for capacity in c_values:
            for buffer in b_values:
                group = [
                    evaluate_case_v2(
                        case,
                        schedule,
                        capacity,
                        buffer,
                        da_v2_config,
                        reference_asap=reference,
                    )
                    for schedule in SCHEDULES_V2
                ]
                add_pairwise_reductions(group)
                rows.extend(group)

    out_path = RESULT_DIR_V2 / "exp1_schedule_reshaping_v2.csv"
    write_csv(out_path, rows, FIELDNAMES)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
