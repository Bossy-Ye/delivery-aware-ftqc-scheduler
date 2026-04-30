"""Experiment 9: effective-capacity robustness under routing/transport loss."""

from __future__ import annotations

from math import floor

from common_v3 import (
    ETA_VALUES,
    RESULT_DIR_V3,
    ROBUST_SCHEDULES,
    RHO,
    read_csv,
    schedule_for_v3,
    selected_robustness_settings,
    t_ref_asap,
    write_csv,
)
from ftqc_delivery.metrics.backlog_shape import backlog_shape_features
from ftqc_delivery.simulator.deterministic import simulate_deterministic


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "schedule",
    "C_nominal",
    "eta",
    "C_eff",
    "B",
    "T_ref_asap",
    "T_static",
    "T_exe",
    "ratio_to_T_ref",
    "stall_cycles",
    "Delta_max",
    "BacklogArea",
    "L_backlog",
    "max_backlog",
    "target_violation_5pct",
    "degradation_vs_eta_1",
]


def main() -> None:
    failure_path = RESULT_DIR_V3 / "exp7_smooth_failure_cases.csv"
    failure_rows = read_csv(failure_path) if failure_path.exists() else []
    raw_rows = []
    for setting in selected_robustness_settings(failure_rows):
        reference = t_ref_asap(setting.case)
        for schedule_name in ROBUST_SCHEDULES:
            eta1_t_exe: int | None = None
            for eta in ETA_VALUES:
                c_eff = max(1, floor(eta * setting.C))
                schedule_capacity = c_eff if schedule_name == "robust_smooth" else setting.C
                schedule = schedule_for_v3(
                    schedule_name,
                    setting.case,
                    schedule_capacity,
                    setting.B,
                    p_acc=1.0,
                    rho=RHO,
                )
                result = simulate_deterministic(setting.case.dag, schedule, c_eff, setting.B)
                backlog = backlog_shape_features(setting.case.dag, schedule, c_eff, setting.B)
                if eta == 1.0:
                    eta1_t_exe = result.T_exe
                degradation = (
                    (result.T_exe - eta1_t_exe) / eta1_t_exe
                    if eta1_t_exe
                    else 0.0
                )
                raw_rows.append(
                    {
                        "workload": setting.case.workload,
                        "family": setting.case.family,
                        "seed": setting.case.seed,
                        "n": setting.case.n,
                        "schedule": schedule_name,
                        "C_nominal": setting.C,
                        "eta": eta,
                        "C_eff": c_eff,
                        "B": setting.B,
                        "T_ref_asap": reference,
                        "T_static": result.T_static,
                        "T_exe": result.T_exe,
                        "ratio_to_T_ref": result.T_exe / reference,
                        "stall_cycles": result.stall_cycles,
                        "Delta_max": result.Delta_max,
                        "BacklogArea": backlog.BacklogArea,
                        "L_backlog": backlog.L_backlog,
                        "max_backlog": backlog.max_backlog,
                        "target_violation_5pct": int(result.T_exe > 1.05 * reference),
                        "degradation_vs_eta_1": degradation,
                    }
                )

    write_csv(RESULT_DIR_V3 / "exp9_effective_capacity_v3.csv", raw_rows, FIELDNAMES)
    print(f"Wrote {len(raw_rows)} rows to {RESULT_DIR_V3 / 'exp9_effective_capacity_v3.csv'}")


if __name__ == "__main__":
    main()
