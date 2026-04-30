"""Experiment 7: mine smooth failure cases and explanatory features."""

from __future__ import annotations

from collections import defaultdict

from common_v3 import (
    RESULT_DIR_V3,
    read_csv,
    schedule_for_v3,
    selected_robustness_settings,
    workload_index,
    write_csv,
)
from ftqc_delivery.metrics.backlog_shape import backlog_shape_features
from ftqc_delivery.metrics.demand_shape import demand_shape_features
from ftqc_delivery.metrics.structural_features import structural_features


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "C",
    "B",
    "T_ref_asap",
    "smooth_T_static",
    "smooth_T_exe",
    "smooth_ratio_to_T_ref",
    "smooth_stall_cycles",
    "smooth_Delta_max",
    "smooth_L_backlog",
    "smooth_BacklogArea",
    "smooth_max_backlog",
    "smooth_num_backlog_intervals",
    "smooth_longest_backlog_interval",
    "failure_reason",
    "failure_score",
    "T_count",
    "critical_path_length",
    "slack_ratio",
    "mean_slack",
    "median_slack",
    "p90_slack",
    "fraction_zero_slack",
    "fraction_slack_ge_2",
    "fraction_slack_ge_5",
    "ready_T_width_peak",
    "ready_T_width_mean",
    "D_peak",
    "D_mean",
    "D_std",
    "D_cv",
    "D_peak_to_mean",
    "num_demand_peaks",
    "demand_entropy",
    "demand_gini",
    "B_over_C",
    "mean_demand_over_C",
    "peak_demand_over_C",
    "supply_tightness",
]


def _smooth_c_ref_worse_flags(rows: list[dict[str, str]]) -> set[tuple[str, str, str, str, str]]:
    flags: set[tuple[str, str, str, str, str]] = set()
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["T_ref_type"] != "asap" or abs(float(row["epsilon"]) - 0.05) > 1e-12:
            continue
        key = (row["workload"], row["family"], row["seed"], row["n"], row["B"])
        grouped[key].append(row)
    for key, group in grouped.items():
        finite = [row for row in group if row["C_ref_star"]]
        if not finite:
            continue
        best = min(int(row["C_ref_star"]) for row in finite)
        smooth = next((row for row in finite if row["schedule"] == "smooth"), None)
        if smooth and int(smooth["C_ref_star"]) > best:
            flags.add(key)
    return flags


def _smooth_opt_gap(exp6_rows: list[dict[str, str]]) -> dict[tuple[str, str, str, str], float]:
    return {
        (row["workload"], row["seed"], row["C"], row["B"]): float(row["gap_Texe_percent"])
        for row in exp6_rows
        if row["schedule"] == "smooth"
    }


def main() -> None:
    exp1 = read_csv(RESULT_DIR_V3.parents[0] / "prelim_v2" / "exp1_schedule_reshaping_v2.csv")
    exp2 = read_csv(RESULT_DIR_V3.parents[0] / "prelim_v2" / "exp2_required_capacity_v2.csv")
    exp6 = read_csv(RESULT_DIR_V3 / "exp6_optimal_gap_analysis.csv")
    c_ref_worse = _smooth_c_ref_worse_flags(exp2)
    opt_gap = _smooth_opt_gap(exp6)
    workloads = workload_index()
    rows = []

    for row in exp1:
        if row["schedule"] != "smooth":
            continue
        c = int(row["C"])
        b = int(row["B"])
        case = workloads[(row["workload"], int(row["seed"]))]
        schedule = schedule_for_v3("smooth", case, c, b)
        structural = structural_features(case.dag)
        demand = demand_shape_features(case.dag, schedule)
        backlog = backlog_shape_features(case.dag, schedule, c, b)
        ratio = float(row["ratio_to_T_ref_asap"])
        gap_opt = opt_gap.get((row["workload"], row["seed"], row["C"], row["B"]), 0.0)

        reasons: list[str] = []
        if int(float(row["stall_cycles"])) > 0:
            reasons.append("smooth_stalls")
        if int(float(row["Delta_max"])) > b:
            reasons.append("Delta_max_gt_B")
        if backlog.L_backlog > 0:
            reasons.append("positive_L_backlog")
        if backlog.BacklogArea > 0:
            reasons.append("positive_BacklogArea")
        if ratio > 1.05:
            reasons.append("misses_1.05_T_ref")
        if gap_opt > 0.05:
            reasons.append("gap_to_opt_gt_5pct")
        c_ref_key = (row["workload"], row["family"], row["seed"], row["n"], row["B"])
        if c_ref_key in c_ref_worse:
            reasons.append("C_ref_star_worse_than_best")
        if not reasons:
            continue

        mean_demand_over_c = demand.D_mean / c if c else 0.0
        peak_demand_over_c = demand.D_peak / c if c else 0.0
        supply_tightness = structural.T_count / (c * structural.T_static_static + b)
        failure_score = (
            max(0.0, ratio - 1.05)
            + 0.1 * backlog.L_backlog
            + 0.1 * backlog.BacklogArea
            + gap_opt
        )

        rows.append(
            {
                "workload": row["workload"],
                "family": row["family"],
                "seed": row["seed"],
                "n": row["n"],
                "C": c,
                "B": b,
                "T_ref_asap": row["T_exe"] if ratio == 1 else float(row["T_exe"]) / ratio,
                "smooth_T_static": row["T_static"],
                "smooth_T_exe": row["T_exe"],
                "smooth_ratio_to_T_ref": ratio,
                "smooth_stall_cycles": row["stall_cycles"],
                "smooth_Delta_max": row["Delta_max"],
                "smooth_L_backlog": backlog.L_backlog,
                "smooth_BacklogArea": backlog.BacklogArea,
                "smooth_max_backlog": backlog.max_backlog,
                "smooth_num_backlog_intervals": backlog.num_backlog_intervals,
                "smooth_longest_backlog_interval": backlog.longest_backlog_interval,
                "failure_reason": ";".join(reasons),
                "failure_score": failure_score,
                "T_count": structural.T_count,
                "critical_path_length": structural.critical_path_length,
                "slack_ratio": structural.slack_ratio,
                "mean_slack": structural.mean_slack,
                "median_slack": structural.median_slack,
                "p90_slack": structural.p90_slack,
                "fraction_zero_slack": structural.fraction_zero_slack,
                "fraction_slack_ge_2": structural.fraction_slack_ge_2,
                "fraction_slack_ge_5": structural.fraction_slack_ge_5,
                "ready_T_width_peak": structural.ready_T_width_peak,
                "ready_T_width_mean": structural.ready_T_width_mean,
                "D_peak": demand.D_peak,
                "D_mean": demand.D_mean,
                "D_std": demand.D_std,
                "D_cv": demand.D_cv,
                "D_peak_to_mean": demand.D_peak_to_mean,
                "num_demand_peaks": demand.num_demand_peaks,
                "demand_entropy": demand.demand_entropy,
                "demand_gini": demand.demand_gini,
                "B_over_C": b / c,
                "mean_demand_over_C": mean_demand_over_c,
                "peak_demand_over_C": peak_demand_over_c,
                "supply_tightness": supply_tightness,
            }
        )

    write_csv(RESULT_DIR_V3 / "exp7_smooth_failure_cases.csv", rows, FIELDNAMES)
    _write_summary(rows)
    print(f"Wrote {len(rows)} rows to {RESULT_DIR_V3 / 'exp7_smooth_failure_cases.csv'}")


def _write_summary(rows: list[dict[str, object]]) -> None:
    top = sorted(rows, key=lambda row: float(row["failure_score"]), reverse=True)[:10]
    persistent = sum(1 for row in rows if float(row["smooth_L_backlog"]) > 0)
    high_tightness = sum(1 for row in rows if float(row["supply_tightness"]) >= 0.9)
    high_peak = sum(1 for row in rows if float(row["peak_demand_over_C"]) >= 2.0)
    lines = [
        "# Smooth Failure Mining Summary",
        "",
        f"Total failure cases: {len(rows)}",
        f"Cases with positive backlog duration: {persistent}",
        f"Cases with supply_tightness >= 0.9: {high_tightness}",
        f"Cases with peak_demand_over_C >= 2: {high_peak}",
        "",
        "## Top smooth failure regimes",
        "",
    ]
    for index, row in enumerate(top, start=1):
        lines.append(
            f"{index}. {row['workload']} seed={row['seed']} C={row['C']} B={row['B']} "
            f"score={float(row['failure_score']):.3f} reasons={row['failure_reason']}"
        )
    (RESULT_DIR_V3 / "exp7_smooth_failure_summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
