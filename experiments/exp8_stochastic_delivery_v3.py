"""Experiment 8: stochastic delivery robustness."""

from __future__ import annotations

from common_v3 import (
    NUM_TRIALS,
    P_ACC_VALUES,
    RESULT_DIR_V3,
    ROBUST_SCHEDULES,
    RHO,
    read_csv,
    schedule_for_v3,
    selected_robustness_settings,
    t_ref_asap,
    write_csv,
)
from ftqc_delivery.metrics.robustness import (
    simulate_stochastic_robustness_trial,
    summarize_stochastic_trials,
)


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "schedule",
    "C",
    "B",
    "p_acc",
    "num_trials",
    "T_ref_asap",
    "mean_T_exe",
    "median_T_exe",
    "p90_T_exe",
    "p95_T_exe",
    "p99_T_exe",
    "std_T_exe",
    "mean_ratio_to_T_ref",
    "p95_ratio_to_T_ref",
    "p99_ratio_to_T_ref",
    "mean_stall_cycles",
    "p95_stall_cycles",
    "stall_probability",
    "target_violation_prob_5pct",
    "target_violation_prob_10pct",
    "mean_BacklogArea",
    "p95_BacklogArea",
    "mean_L_backlog",
    "p95_L_backlog",
]


def main() -> None:
    failure_path = RESULT_DIR_V3 / "exp7_smooth_failure_cases.csv"
    failure_rows = read_csv(failure_path) if failure_path.exists() else []
    rows = []
    for setting in selected_robustness_settings(failure_rows):
        reference = t_ref_asap(setting.case)
        for p_acc in P_ACC_VALUES:
            for schedule_name in ROBUST_SCHEDULES:
                schedule = schedule_for_v3(
                    schedule_name,
                    setting.case,
                    setting.C,
                    setting.B,
                    p_acc=p_acc if schedule_name == "robust_smooth" else 1.0,
                    rho=RHO,
                )
                trials = [
                    simulate_stochastic_robustness_trial(
                        setting.case.dag,
                        schedule,
                        setting.C,
                        setting.B,
                        p_acc,
                        seed=100000 * setting.C
                        + 1000 * setting.B
                        + 17 * trial
                        + int(round(1000 * p_acc)),
                    )
                    for trial in range(NUM_TRIALS)
                ]
                summary = summarize_stochastic_trials(trials, reference)
                rows.append(
                    {
                        "workload": setting.case.workload,
                        "family": setting.case.family,
                        "seed": setting.case.seed,
                        "n": setting.case.n,
                        "schedule": schedule_name,
                        "C": setting.C,
                        "B": setting.B,
                        "p_acc": p_acc,
                        "num_trials": NUM_TRIALS,
                        "T_ref_asap": reference,
                        **summary,
                    }
                )

    write_csv(RESULT_DIR_V3 / "exp8_stochastic_delivery_v3.csv", rows, FIELDNAMES)
    print(f"Wrote {len(rows)} rows to {RESULT_DIR_V3 / 'exp8_stochastic_delivery_v3.csv'}")


if __name__ == "__main__":
    main()
