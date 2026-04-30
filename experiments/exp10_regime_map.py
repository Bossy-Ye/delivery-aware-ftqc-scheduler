"""Experiment 10: rule-based regime map for smooth success/failure."""

from __future__ import annotations

from collections import defaultdict

from common_v3 import (
    RESULT_DIR_V3,
    generate_v3_figures,
    read_csv,
    workload_index,
    write_csv,
    write_v3_report,
)


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "C",
    "B",
    "regime_label",
    "regime_reason",
    "recommended_strategy",
    "slack_ratio",
    "supply_tightness",
    "peak_demand_over_C",
    "mean_demand_over_C",
    "smooth_L_backlog",
    "smooth_BacklogArea",
]


def _uncertainty_sensitive_keys(
    stochastic_rows: list[dict[str, str]],
    effective_rows: list[dict[str, str]],
) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    for row in stochastic_rows:
        if row["schedule"] != "smooth":
            continue
        if float(row["p_acc"]) <= 0.95 and (
            float(row["p95_ratio_to_T_ref"]) > 1.10
            or float(row["target_violation_prob_5pct"]) > 0.2
        ):
            keys.add((row["workload"], row["seed"], row["C"], row["B"]))
    for row in effective_rows:
        if row["schedule"] != "smooth":
            continue
        if float(row["eta"]) <= 0.75 and float(row["degradation_vs_eta_1"]) > 0.20:
            keys.add((row["workload"], row["seed"], row["C_nominal"], row["B"]))
    return keys


def _classify(
    smooth_failure: dict[str, str] | None,
    static_row: dict[str, str],
    smooth_row: dict[str, str],
    uncertainty_sensitive: bool,
) -> tuple[str, str, str]:
    b = int(smooth_row["B"])
    static_stall = int(float(static_row["stall_cycles"]))
    static_delta = float(static_row["Delta_max"])
    smooth_stall = int(float(smooth_row["stall_cycles"]))
    smooth_delta = float(smooth_row["Delta_max"])
    smooth_l = float(smooth_failure["smooth_L_backlog"]) if smooth_failure else float(smooth_row["L_backlog"])
    smooth_area = float(smooth_failure["smooth_BacklogArea"]) if smooth_failure else 0.0
    slack_ratio = float(smooth_failure["slack_ratio"]) if smooth_failure else 0.0
    fraction_zero = float(smooth_failure["fraction_zero_slack"]) if smooth_failure else 0.0
    supply_tightness = float(smooth_failure["supply_tightness"]) if smooth_failure else 0.0
    peak_over_c = float(smooth_failure["peak_demand_over_C"]) if smooth_failure else 0.0
    mean_over_c = float(smooth_failure["mean_demand_over_C"]) if smooth_failure else 0.0
    texe_reduction = float(smooth_row["Texe_reduction_vs_static"])

    if uncertainty_sensitive:
        return (
            "uncertainty_sensitive",
            "deterministic schedule degrades under stochastic or effective-capacity loss",
            "robust_scheduling",
        )
    if static_stall == 0 and static_delta <= b:
        return ("no_delivery_bottleneck", "static schedule has no delivery bottleneck", "none")
    if (
        static_delta > b
        and smooth_stall == 0
        and smooth_area == 0
        and slack_ratio >= 0.5
    ):
        return (
            "peak_dominated_smooth_solvable",
            "static has bursts but smooth removes backlog with available slack",
            "smooth",
        )
    if mean_over_c >= 1.0 or (supply_tightness >= 0.95 and smooth_l > 0):
        return (
            "persistent_underprovisioning",
            "average demand is too close to available supply for scheduling alone",
            "increase_capacity",
        )
    if slack_ratio <= 0.1 and fraction_zero >= 0.8 and static_stall > 0 and texe_reduction < 0.05:
        return (
            "low_slack_structure_limited",
            "few T gates can move, so smoothing cannot reshape demand",
            "architecture_provisioning",
        )
    if peak_over_c >= 2.0 and smooth_delta < static_delta and smooth_l > 0:
        return (
            "peak_dominated_buffer_limited",
            "smoothing reduces peaks but buffer remains too small",
            "increase_buffer",
        )
    if smooth_l > 0 or smooth_delta > b:
        return (
            "peak_dominated_buffer_limited",
            "smooth still has residual backlog after peak reduction",
            "increase_buffer",
        )
    return ("peak_dominated_smooth_solvable", "smooth is sufficient in this setting", "smooth")


def main() -> None:
    exp1 = read_csv(RESULT_DIR_V3.parents[0] / "prelim_v2" / "exp1_schedule_reshaping_v2.csv")
    exp7 = read_csv(RESULT_DIR_V3 / "exp7_smooth_failure_cases.csv")
    exp8 = read_csv(RESULT_DIR_V3 / "exp8_stochastic_delivery_v3.csv")
    exp9 = read_csv(RESULT_DIR_V3 / "exp9_effective_capacity_v3.csv")
    failures = {
        (row["workload"], row["seed"], row["C"], row["B"]): row
        for row in exp7
    }
    uncertain = _uncertainty_sensitive_keys(exp8, exp9)
    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in exp1:
        key = (row["workload"], row["seed"], row["C"], row["B"])
        grouped[key][row["schedule"]] = row

    rows = []
    for key, schedules in grouped.items():
        static_row = schedules.get("static")
        smooth_row = schedules.get("smooth")
        if static_row is None or smooth_row is None:
            continue
        failure = failures.get(key)
        label, reason, strategy = _classify(failure, static_row, smooth_row, key in uncertain)
        if failure:
            slack_ratio = failure["slack_ratio"]
            supply_tightness = failure["supply_tightness"]
            peak_over_c = failure["peak_demand_over_C"]
            mean_over_c = failure["mean_demand_over_C"]
            smooth_l = failure["smooth_L_backlog"]
            smooth_area = failure["smooth_BacklogArea"]
        else:
            slack_ratio = 0.0
            supply_tightness = 0.0
            peak_over_c = 0.0
            mean_over_c = 0.0
            smooth_l = smooth_row["L_backlog"]
            smooth_area = 0.0
        rows.append(
            {
                "workload": smooth_row["workload"],
                "family": smooth_row["family"],
                "seed": smooth_row["seed"],
                "n": smooth_row["n"],
                "C": smooth_row["C"],
                "B": smooth_row["B"],
                "regime_label": label,
                "regime_reason": reason,
                "recommended_strategy": strategy,
                "slack_ratio": slack_ratio,
                "supply_tightness": supply_tightness,
                "peak_demand_over_C": peak_over_c,
                "mean_demand_over_C": mean_over_c,
                "smooth_L_backlog": smooth_l,
                "smooth_BacklogArea": smooth_area,
            }
        )

    write_csv(RESULT_DIR_V3 / "exp10_regime_map.csv", rows, FIELDNAMES)
    generate_v3_figures()
    write_v3_report()
    print(f"Wrote {len(rows)} rows to {RESULT_DIR_V3 / 'exp10_regime_map.csv'}")


if __name__ == "__main__":
    main()
