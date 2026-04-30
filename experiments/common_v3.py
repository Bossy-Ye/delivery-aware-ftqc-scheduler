"""Shared utilities for V3 limit, failure-regime, and robustness analysis."""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
MPLCONFIGDIR = Path("/private/tmp/delivery_aware_ftqc_scheduler_mpl")
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))

from common_v2 import (  # noqa: E402
    DEFAULT_DA_V2_CONFIG,
    SCHEDULE_COLORS,
    WorkloadCase,
    build_v2_workloads,
    make_schedule_v2,
    t_ref_asap,
)
from ftqc_delivery.metrics.backlog_shape import backlog_shape_features
from ftqc_delivery.metrics.delta_max import delta_max
from ftqc_delivery.metrics.demand_shape import demand_shape_features
from ftqc_delivery.metrics.structural_features import structural_features
from ftqc_delivery.schedulers import (
    DeliveryAwareV2Config,
    DeliveryAwareV2Weights,
    schedule_robust_smooth,
    schedule_smooth,
)
from ftqc_delivery.simulator.deterministic import simulate_deterministic
from ftqc_delivery.workloads import (
    make_exact_qft,
    make_high_compressibility,
    make_low_compressibility,
    make_medium_compressibility,
    make_multiplier,
)


RESULT_DIR_V3 = ROOT / "results" / "prelim_v3"
FIGURE_DIR_V3 = ROOT / "figures" / "prelim_v3"
REPORT_SCHEDULES = ["static", "capacity_aware", "smooth", "delivery_aware_v1", "delivery_aware_v2"]
ROBUST_SCHEDULES = ["capacity_aware", "smooth", "delivery_aware_v2", "robust_smooth"]
P_ACC_VALUES = [1.0, 0.995, 0.99, 0.95, 0.90]
ETA_VALUES = [1.0, 0.9, 0.75, 0.5]
NUM_TRIALS = 200
RHO = 0.9
SCHEDULE_COLORS = dict(SCHEDULE_COLORS)
SCHEDULE_COLORS["robust_smooth"] = "#72b7b2"


@dataclass(frozen=True)
class CaseSetting:
    """A workload and delivery setting selected for V3 robustness scans."""

    case: WorkloadCase
    C: int
    B: int


def ensure_output_dirs() -> None:
    """Create V3 output directories."""

    RESULT_DIR_V3.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR_V3.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write dictionaries to CSV."""

    ensure_output_dirs()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read CSV rows as dictionaries."""

    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def workload_index() -> dict[tuple[str, int], WorkloadCase]:
    """Return V2 workload cases indexed by (workload, seed)."""

    return {(case.workload, case.seed): case for case in build_v2_workloads()}


def small_v3_cases() -> list[WorkloadCase]:
    """Return tiny cases used for near-optimal analysis."""

    return [
        WorkloadCase("small_high", "small_high", 0, 6, make_high_compressibility(seed=0, n=6)),
        WorkloadCase("small_medium", "small_medium", 0, 6, make_medium_compressibility(seed=0, n=6)),
        WorkloadCase("small_low", "small_low", 0, 6, make_low_compressibility(seed=0, n=6)),
    ]


def schedule_for_v3(
    schedule_name: str,
    case: WorkloadCase,
    capacity: int,
    buffer: int,
    p_acc: float = 1.0,
    rho: float = RHO,
) -> dict[int, list[str]]:
    """Build a V3 schedule, including robust_smooth."""

    if schedule_name == "robust_smooth":
        return schedule_robust_smooth(case.dag, capacity, p_acc=p_acc, rho=rho)
    return make_schedule_v2(schedule_name, case.dag, capacity, buffer, DEFAULT_DA_V2_CONFIG)


def near_optimal_candidates(
    case: WorkloadCase,
    capacity: int,
    buffer: int,
) -> dict[str, dict[int, list[str]]]:
    """Return a small candidate set for near-optimal deterministic reference."""

    candidates = {
        schedule_name: schedule_for_v3(schedule_name, case, capacity, buffer)
        for schedule_name in REPORT_SCHEDULES
    }
    for smooth_capacity in sorted({max(1, capacity - 1), capacity, capacity + 1, capacity + 2}):
        candidates[f"smooth_quota_{smooth_capacity}"] = schedule_smooth(case.dag, smooth_capacity)
    variants = {
        "da_v2_exe_heavy": DeliveryAwareV2Config(
            lookahead_horizon=5,
            weights=DeliveryAwareV2Weights(4.0, 1.0, 2.0, 0.5, 0.5),
        ),
        "da_v2_critical_heavy": DeliveryAwareV2Config(
            lookahead_horizon=5,
            weights=DeliveryAwareV2Weights(2.0, 1.0, 1.0, 0.5, 1.5),
        ),
        "da_v2_longer_lookahead": DeliveryAwareV2Config(
            lookahead_horizon=8,
            weights=DeliveryAwareV2Weights(),
        ),
    }
    for name, config in variants.items():
        candidates[name] = make_schedule_v2("delivery_aware_v2", case.dag, capacity, buffer, config)
    return candidates


def schedule_metrics(
    case: WorkloadCase,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
) -> dict[str, Any]:
    """Return deterministic runtime and backlog-shape metrics for a schedule."""

    result = simulate_deterministic(case.dag, schedule, capacity, buffer)
    shape = backlog_shape_features(case.dag, schedule, capacity, buffer)
    return {
        "T_static": result.T_static,
        "T_exe": result.T_exe,
        "Delta_max": result.Delta_max,
        "stall_cycles": result.stall_cycles,
        "L_backlog": shape.L_backlog,
        "BacklogArea": shape.BacklogArea,
        "max_backlog": shape.max_backlog,
        "mean_backlog": shape.mean_backlog,
        "num_backlog_intervals": shape.num_backlog_intervals,
        "longest_backlog_interval": shape.longest_backlog_interval,
        "backlog_persistence_ratio": shape.backlog_persistence_ratio,
    }


def selected_robustness_settings(failure_rows: list[dict[str, str]] | None = None) -> list[CaseSetting]:
    """Select core and mined failure settings for stochastic/effective scans."""

    index = workload_index()
    settings: dict[tuple[str, int, int, int], CaseSetting] = {}
    for workload in ["constructed_high", "constructed_medium", "multiplier_n8", "exact_qft_n8"]:
        case = index[(workload, 0)]
        settings[(case.workload, case.seed, 2, 4)] = CaseSetting(case, 2, 4)

    if failure_rows:
        top = sorted(failure_rows, key=lambda row: float(row["failure_score"]), reverse=True)[:2]
        for row in top:
            key = (row["workload"], int(row["seed"]))
            case = index.get(key)
            if case is None:
                continue
            c = int(row["C"])
            b = int(row["B"])
            settings[(case.workload, case.seed, c, b)] = CaseSetting(case, c, b)
    return list(settings.values())


def generate_v3_figures() -> None:
    """Generate all V3 figures from existing experiment outputs."""

    ensure_output_dirs()
    import matplotlib.pyplot as plt

    _figure_gap_to_optimal()
    _figure_regime_map()
    _figure_backlog_shape()
    _figure_stochastic_tail()
    _figure_target_violation()
    _figure_effective_capacity()
    plt.close("all")


def _figure_gap_to_optimal() -> None:
    import matplotlib.pyplot as plt

    rows = read_csv(RESULT_DIR_V3 / "exp6_optimal_gap_analysis.csv")
    schedules = ["static", "capacity_aware", "smooth", "delivery_aware_v2"]
    data = [
        [float(row["gap_Texe_percent"]) for row in rows if row["schedule"] == schedule]
        for schedule in schedules
    ]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.boxplot(data, labels=schedules, showfliers=False)
    ax.axhline(0.05, color="black", linewidth=1, linestyle="--", label="5%")
    ax.set_ylabel("gap_Texe_percent")
    ax.set_title("Gap to near-optimal deterministic reference")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V3 / "fig1_smooth_gap_to_optimal.pdf")


def _figure_regime_map() -> None:
    import matplotlib.pyplot as plt

    rows = read_csv(RESULT_DIR_V3 / "exp10_regime_map.csv")
    labels = sorted({row["regime_label"] for row in rows})
    colors = {label: f"C{index}" for index, label in enumerate(labels)}
    fig, ax = plt.subplots(figsize=(7, 5))
    for label in labels:
        selected = [row for row in rows if row["regime_label"] == label]
        ax.scatter(
            [float(row["slack_ratio"]) for row in selected],
            [float(row["supply_tightness"]) for row in selected],
            s=24,
            alpha=0.55,
            label=label,
            color=colors[label],
        )
    ax.set_xlabel("slack_ratio")
    ax.set_ylabel("supply_tightness")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V3 / "fig2_regime_map.pdf")


def _figure_backlog_shape() -> None:
    import matplotlib.pyplot as plt

    rows = sorted(
        read_csv(RESULT_DIR_V3 / "exp7_smooth_failure_cases.csv"),
        key=lambda row: float(row["failure_score"]),
        reverse=True,
    )[:12]
    labels = [f"{row['workload']} C{row['C']} B{row['B']}" for row in rows]
    metrics = ["smooth_BacklogArea", "smooth_L_backlog", "smooth_longest_backlog_interval", "smooth_Delta_max"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    for ax, metric in zip(axes.ravel(), metrics, strict=True):
        ax.bar(range(len(rows)), [float(row[metric]) for row in rows], color="#4c78a8")
        ax.set_title(metric)
        ax.set_xticks(range(len(rows)))
        ax.set_xticklabels(labels, rotation=70, ha="right", fontsize=7)
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V3 / "fig3_backlog_shape.pdf")


def _mean_by(rows: list[dict[str, str]], key_fields: list[str], value_field: str) -> dict[tuple[str, ...], float]:
    grouped: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in key_fields)].append(float(row[value_field]))
    return {key: sum(values) / len(values) for key, values in grouped.items()}


def _figure_stochastic_tail() -> None:
    import matplotlib.pyplot as plt

    rows = read_csv(RESULT_DIR_V3 / "exp8_stochastic_delivery_v3.csv")
    grouped = _mean_by(rows, ["schedule", "p_acc"], "p95_ratio_to_T_ref")
    fig, ax = plt.subplots(figsize=(7, 4.8))
    for schedule in ROBUST_SCHEDULES:
        keys = sorted((key for key in grouped if key[0] == schedule), key=lambda key: float(key[1]))
        ax.plot(
            [float(key[1]) for key in keys],
            [grouped[key] for key in keys],
            marker="o",
            label=schedule,
            color=SCHEDULE_COLORS.get(schedule, "#e45756"),
        )
    ax.invert_xaxis()
    ax.set_xlabel("p_acc")
    ax.set_ylabel("mean p95(T_exe / T_ref)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V3 / "fig4_stochastic_tail_runtime.pdf")


def _figure_target_violation() -> None:
    import matplotlib.pyplot as plt

    rows = read_csv(RESULT_DIR_V3 / "exp8_stochastic_delivery_v3.csv")
    grouped = _mean_by(rows, ["schedule", "p_acc"], "target_violation_prob_5pct")
    fig, ax = plt.subplots(figsize=(7, 4.8))
    for schedule in ROBUST_SCHEDULES:
        keys = sorted((key for key in grouped if key[0] == schedule), key=lambda key: float(key[1]))
        ax.plot(
            [float(key[1]) for key in keys],
            [grouped[key] for key in keys],
            marker="o",
            label=schedule,
            color=SCHEDULE_COLORS.get(schedule, "#e45756"),
        )
    ax.invert_xaxis()
    ax.set_xlabel("p_acc")
    ax.set_ylabel("P(T_exe > 1.05 T_ref)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V3 / "fig5_target_violation_probability.pdf")


def _figure_effective_capacity() -> None:
    import matplotlib.pyplot as plt

    rows = read_csv(RESULT_DIR_V3 / "exp9_effective_capacity_v3.csv")
    grouped = _mean_by(rows, ["schedule", "eta"], "degradation_vs_eta_1")
    fig, ax = plt.subplots(figsize=(7, 4.8))
    for schedule in ROBUST_SCHEDULES:
        keys = sorted((key for key in grouped if key[0] == schedule), key=lambda key: float(key[1]))
        ax.plot(
            [float(key[1]) for key in keys],
            [grouped[key] for key in keys],
            marker="o",
            label=schedule,
            color=SCHEDULE_COLORS.get(schedule, "#e45756"),
        )
    ax.invert_xaxis()
    ax.set_xlabel("eta")
    ax.set_ylabel("mean degradation vs eta=1")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V3 / "fig6_effective_capacity_degradation.pdf")


def write_v3_report() -> None:
    """Write the V3 preliminary report from generated outputs."""

    exp6_summary = read_csv(RESULT_DIR_V3 / "exp6_optimal_gap_summary.csv")
    exp7 = read_csv(RESULT_DIR_V3 / "exp7_smooth_failure_cases.csv")
    exp8 = read_csv(RESULT_DIR_V3 / "exp8_stochastic_delivery_v3.csv")
    exp9 = read_csv(RESULT_DIR_V3 / "exp9_effective_capacity_v3.csv")
    exp10 = read_csv(RESULT_DIR_V3 / "exp10_regime_map.csv")
    summary_by_schedule = {row["schedule"]: row for row in exp6_summary}
    smooth_summary = summary_by_schedule.get("smooth", {})
    smooth_within_1 = float(smooth_summary.get("fraction_within_1cycle", 0.0))
    smooth_mean_gap = float(smooth_summary.get("mean_gap_Texe", 0.0))
    smooth_max_gap = float(smooth_summary.get("max_gap_Texe", 0.0))
    top_failures = sorted(exp7, key=lambda row: float(row["failure_score"]), reverse=True)[:5]
    regime_counts: dict[str, int] = defaultdict(int)
    for row in exp10:
        regime_counts[row["regime_label"]] += 1

    def average(rows: list[dict[str, str]], schedule: str, field: str, predicate) -> float:
        selected = [float(row[field]) for row in rows if row["schedule"] == schedule and predicate(row)]
        return sum(selected) / len(selected) if selected else 0.0

    smooth_p95_low = average(exp8, "smooth", "p95_ratio_to_T_ref", lambda row: float(row["p_acc"]) <= 0.95)
    robust_p95_low = average(exp8, "robust_smooth", "p95_ratio_to_T_ref", lambda row: float(row["p_acc"]) <= 0.95)
    smooth_violate_low = average(
        exp8,
        "smooth",
        "target_violation_prob_5pct",
        lambda row: float(row["p_acc"]) <= 0.95,
    )
    robust_violate_low = average(
        exp8,
        "robust_smooth",
        "target_violation_prob_5pct",
        lambda row: float(row["p_acc"]) <= 0.95,
    )
    smooth_eta_low = average(
        exp9,
        "smooth",
        "degradation_vs_eta_1",
        lambda row: float(row["eta"]) <= 0.75,
    )
    robust_eta_low = average(
        exp9,
        "robust_smooth",
        "degradation_vs_eta_1",
        lambda row: float(row["eta"]) <= 0.75,
    )

    if smooth_within_1 >= 0.90 and smooth_p95_low <= robust_p95_low and smooth_eta_low <= robust_eta_low:
        recommendation = "stop / merge into Paper 1"
    elif robust_p95_low < smooth_p95_low or robust_violate_low < smooth_violate_low:
        recommendation = "robustness paper"
    elif any(label in regime_counts for label in ["persistent_underprovisioning", "low_slack_structure_limited"]):
        recommendation = "regime-aware framework paper"
    else:
        recommendation = "stop / redesign"

    failure_lines = "\n".join(
        f"- {row['workload']} seed={row['seed']} C={row['C']} B={row['B']}: "
        f"{row['failure_reason']} score={float(row['failure_score']):.3f}"
        for row in top_failures
    )
    regime_lines = "\n".join(
        f"- {label}: {count}" for label, count in sorted(regime_counts.items())
    )

    report = f"""# Preliminary Report V3

## Summary

Recommendation: **{recommendation}**.

V3 does not attempt to make DA look better. It asks whether smooth is near
optimal, when it fails, and whether stochastic or effective-capacity uncertainty
creates a real Paper 2 opening.

## Questions

1. Is smooth near-optimal in deterministic small instances?

   Smooth mean gap to the near-optimal reference is {smooth_mean_gap:.3f}
   cycles, max gap is {smooth_max_gap:.3f} cycles, and the fraction within
   one cycle is {smooth_within_1:.3f}.

2. What is the average and worst gap between smooth and optimal?

   Mean gap: {smooth_mean_gap:.3f}. Worst gap: {smooth_max_gap:.3f}.

3. Where does smooth fail?

{failure_lines if failure_lines else "- No smooth failure cases were mined."}

4. Are failures peak-dominated or persistence-dominated?

   See `exp7_smooth_failure_cases.csv` and Figure 3. The regime counts below
   summarize whether failures are bottleneck-free, peak/buffer limited,
   persistent, low-slack, or uncertainty-sensitive.

5. Does stochastic supply break smooth?

   For p_acc <= 0.95, average smooth p95(T_exe/T_ref) is
   {smooth_p95_low:.3f}; robust_smooth is {robust_p95_low:.3f}.

6. Does effective capacity degradation break smooth?

   For eta <= 0.75, average smooth degradation is {smooth_eta_low:.3f};
   robust_smooth is {robust_eta_low:.3f}.

7. Does robust_smooth help?

   For p_acc <= 0.95, smooth 5% target violation probability averages
   {smooth_violate_low:.3f}; robust_smooth averages {robust_violate_low:.3f}.
   Robust_smooth helps only if these tail metrics decrease without large
   deterministic penalties.

8. What regimes can be identified?

{regime_lines}

9. What is the recommended next direction?

   **{recommendation}**. If smooth is near-optimal and robust, stop or merge the
   insight into Paper 1. If uncertainty breaks smooth and robust_smooth helps,
   pivot to robust demand shaping. If failures cluster structurally, pivot to a
   regime-aware compiler-architecture framework.
"""
    ensure_output_dirs()
    (RESULT_DIR_V3 / "PRELIMINARY_REPORT_V3.md").write_text(report)
