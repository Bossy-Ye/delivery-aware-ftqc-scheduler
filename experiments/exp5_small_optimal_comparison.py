"""Experiment 5 V2: small near-optimal comparison.

This is not an exact optimizer. It builds a near-optimal reference by taking the
best deterministic runtime found among the main schedulers and several small
DA-v2/smoothing variants. The point is to test whether smooth is already close
to the best schedule found on tiny instances.
"""

from __future__ import annotations

from common_v2 import (
    DEFAULT_DA_V2_CONFIG,
    RESULT_DIR_V2,
    SCHEDULES_V2,
    WorkloadCase,
    make_schedule_v2,
    write_csv,
    write_preliminary_report_v2,
)
from ftqc_delivery.schedulers import DeliveryAwareV2Config, DeliveryAwareV2Weights, schedule_smooth
from ftqc_delivery.simulator.deterministic import simulate_deterministic
from ftqc_delivery.workloads import (
    make_high_compressibility,
    make_low_compressibility,
    make_medium_compressibility,
)


FIELDNAMES = [
    "workload",
    "seed",
    "C",
    "B",
    "schedule",
    "T_static",
    "T_exe",
    "gap_to_optimal",
    "gap_percent",
    "Delta_max",
    "stall_cycles",
]


def small_cases() -> list[WorkloadCase]:
    """Return tiny constructed DAGs for near-optimal comparison."""

    return [
        WorkloadCase("small_high", "small_high", 0, 6, make_high_compressibility(seed=0, n=6)),
        WorkloadCase(
            "small_medium",
            "small_medium",
            0,
            6,
            make_medium_compressibility(seed=0, n=6),
        ),
        WorkloadCase("small_low", "small_low", 0, 6, make_low_compressibility(seed=0, n=6)),
    ]


def near_optimal_candidates(case: WorkloadCase, capacity: int, buffer: int) -> dict[str, dict[int, list[str]]]:
    """Build a small candidate set used as a near-optimal reference."""

    candidates = {
        schedule_name: make_schedule_v2(schedule_name, case.dag, capacity, buffer, DEFAULT_DA_V2_CONFIG)
        for schedule_name in SCHEDULES_V2
    }
    for smooth_capacity in sorted({max(1, capacity - 1), capacity, capacity + 1, capacity + 2}):
        candidates[f"smooth_quota_{smooth_capacity}"] = schedule_smooth(case.dag, smooth_capacity)

    configs = {
        "da_v2_exe_heavy": DeliveryAwareV2Config(
            lookahead_horizon=5,
            weights=DeliveryAwareV2Weights(
                lambda_exe=4.0,
                lambda_delta=1.0,
                lambda_backlog=2.0,
                lambda_static=0.5,
                lambda_critical=0.5,
            ),
        ),
        "da_v2_critical_heavy": DeliveryAwareV2Config(
            lookahead_horizon=5,
            weights=DeliveryAwareV2Weights(
                lambda_exe=2.0,
                lambda_delta=1.0,
                lambda_backlog=1.0,
                lambda_static=0.5,
                lambda_critical=1.5,
            ),
        ),
        "da_v2_longer_lookahead": DeliveryAwareV2Config(
            lookahead_horizon=8,
            weights=DeliveryAwareV2Weights(),
        ),
    }
    for name, config in configs.items():
        candidates[name] = make_schedule_v2("delivery_aware_v2", case.dag, capacity, buffer, config)
    return candidates


def main() -> None:
    rows = []
    for case in small_cases():
        for capacity in [1, 2]:
            for buffer in [0, 2]:
                candidate_schedules = near_optimal_candidates(case, capacity, buffer)
                candidate_results = {
                    name: simulate_deterministic(case.dag, schedule, capacity, buffer)
                    for name, schedule in candidate_schedules.items()
                }
                best_name, best_result = min(
                    candidate_results.items(),
                    key=lambda item: (item[1].T_exe, item[1].T_static, item[0]),
                )

                report_names = SCHEDULES_V2 + ["optimal_or_near_optimal"]
                for schedule_name in report_names:
                    result = (
                        best_result
                        if schedule_name == "optimal_or_near_optimal"
                        else candidate_results[schedule_name]
                    )
                    gap = result.T_exe - best_result.T_exe
                    rows.append(
                        {
                            "workload": case.workload,
                            "seed": case.seed,
                            "C": capacity,
                            "B": buffer,
                            "schedule": schedule_name,
                            "T_static": result.T_static,
                            "T_exe": result.T_exe,
                            "gap_to_optimal": gap,
                            "gap_percent": gap / best_result.T_exe if best_result.T_exe else 0.0,
                            "Delta_max": result.Delta_max,
                            "stall_cycles": result.stall_cycles,
                        }
                    )

    out_path = RESULT_DIR_V2 / "exp5_small_optimal_comparison.csv"
    write_csv(out_path, rows, FIELDNAMES)
    exp1_path = RESULT_DIR_V2 / "exp1_schedule_reshaping_v2.csv"
    exp2_path = RESULT_DIR_V2 / "exp2_required_capacity_v2.csv"
    if exp1_path.exists() and exp2_path.exists():
        write_preliminary_report_v2(exp1_path, exp2_path, out_path)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
