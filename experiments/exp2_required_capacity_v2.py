"""Experiment 2 V2: fixed-reference delivery capacity threshold."""

from __future__ import annotations

from common_v2 import (
    B_VALUES,
    EPSILON_VALUES,
    RESULT_DIR_V2,
    SCHEDULES_V2,
    THRESHOLD_C_VALUES,
    build_v2_workloads,
    generate_v2_figures,
    load_da_v2_config,
    make_schedule_v2,
    read_csv,
    t_ref_asap,
    t_ref_best,
    write_csv,
    write_preliminary_report_v2,
)
from ftqc_delivery.metrics.capacity_threshold import find_reference_capacity_threshold
from ftqc_delivery.simulator.deterministic import simulate_deterministic


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "schedule",
    "B",
    "epsilon",
    "T_ref_type",
    "T_ref",
    "C_ref_star",
    "achieved_T_exe",
    "achieved_ratio_to_T_ref",
    "T_static_at_C_ref_star",
    "stall_cycles_at_C_ref_star",
    "Delta_max_at_C_ref_star",
]


def main() -> None:
    da_v2_config = load_da_v2_config()
    rows = []
    for case in build_v2_workloads():
        reference_asap = t_ref_asap(case)
        for buffer in B_VALUES:
            references = {
                "asap": reference_asap,
                "best": t_ref_best(case, buffer, da_v2_config),
            }
            for epsilon in EPSILON_VALUES:
                for ref_type, reference in references.items():
                    for schedule_name in SCHEDULES_V2:

                        def evaluator(capacity: int) -> tuple[int, int, int, int]:
                            schedule = make_schedule_v2(
                                schedule_name,
                                case.dag,
                                capacity,
                                buffer,
                                da_v2_config,
                            )
                            result = simulate_deterministic(
                                case.dag,
                                schedule,
                                capacity,
                                buffer,
                            )
                            return (
                                result.T_static,
                                result.T_exe,
                                result.stall_cycles,
                                result.Delta_max,
                            )

                        threshold = find_reference_capacity_threshold(
                            THRESHOLD_C_VALUES,
                            epsilon,
                            reference,
                            evaluator,
                        )
                        rows.append(
                            {
                                "workload": case.workload,
                                "family": case.family,
                                "seed": case.seed,
                                "n": case.n,
                                "schedule": schedule_name,
                                "B": buffer,
                                "epsilon": epsilon,
                                "T_ref_type": ref_type,
                                "T_ref": reference,
                                "C_ref_star": threshold.C_ref_star
                                if threshold.C_ref_star is not None
                                else "",
                                "achieved_T_exe": threshold.achieved_T_exe
                                if threshold.achieved_T_exe is not None
                                else "",
                                "achieved_ratio_to_T_ref": threshold.achieved_ratio_to_T_ref
                                if threshold.achieved_ratio_to_T_ref is not None
                                else "",
                                "T_static_at_C_ref_star": threshold.T_static_at_C_ref_star
                                if threshold.T_static_at_C_ref_star is not None
                                else "",
                                "stall_cycles_at_C_ref_star": threshold.stall_cycles_at_C_ref_star
                                if threshold.stall_cycles_at_C_ref_star is not None
                                else "",
                                "Delta_max_at_C_ref_star": threshold.Delta_max_at_C_ref_star
                                if threshold.Delta_max_at_C_ref_star is not None
                                else "",
                            }
                        )

    out_path = RESULT_DIR_V2 / "exp2_required_capacity_v2.csv"
    write_csv(out_path, rows, FIELDNAMES)
    exp1_path = RESULT_DIR_V2 / "exp1_schedule_reshaping_v2.csv"
    if exp1_path.exists():
        exp1_rows = read_csv(exp1_path)
        generate_v2_figures(exp1_rows, rows)
        write_preliminary_report_v2(exp1_path, out_path)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
