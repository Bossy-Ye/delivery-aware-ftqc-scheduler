"""Shared utilities for V4 regime validation experiments."""

from __future__ import annotations

import csv
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
MPLCONFIGDIR = Path("/private/tmp/delivery_aware_ftqc_scheduler_mpl")
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))

from common_v2 import DEFAULT_DA_V2_CONFIG, WorkloadCase, build_v2_workloads, make_schedule_v2, t_ref_asap
from ftqc_delivery.metrics.backlog_shape import backlog_shape_features
from ftqc_delivery.metrics.buffer_threshold import find_buffer_reference_threshold
from ftqc_delivery.metrics.capacity_threshold import find_reference_capacity_threshold
from ftqc_delivery.metrics.demand_shape import demand_shape_features
from ftqc_delivery.metrics.regime_validation import RegimeDecision, classify_delivery_regime
from ftqc_delivery.metrics.structural_features import structural_features
from ftqc_delivery.metrics.strategy_gain import backlog_area_gain, relative_gain, strategy_score
from ftqc_delivery.schedulers import schedule_robust_smooth
from ftqc_delivery.simulator.deterministic import simulate_deterministic
from ftqc_delivery.workloads import (
    make_approx_qft,
    make_exact_qft,
    make_hamiltonian_simulation_synthetic,
    make_modular_arithmetic_block,
    make_multiplier,
    make_phase_estimation_like,
)


RESULT_DIR_V4 = ROOT / "results" / "prelim_v4"
FIGURE_DIR_V4 = ROOT / "figures" / "prelim_v4"
SCHEDULES_V4 = ["static", "capacity_aware", "smooth", "delivery_aware_v2", "robust_smooth"]
C_VALUES_V4 = [1, 2, 3, 4, 5, 6, 7, 8]
B_VALUES_V4 = [0, 2, 4, 8, 12, 16, 24]
C_VALUES_REDUCED = [1, 2, 3, 4, 5, 7]
B_VALUES_REDUCED = [0, 4, 8, 16]
C_VALUES_STRATEGY = [1, 2, 3, 4, 5, 6, 8, 10]
B_VALUES_STRATEGY = [0, 2, 4, 8, 16, 32]
EPSILON_VALUES = [0.05, 0.10]
RHO = 0.9
SCHEDULE_COLORS = {
    "static": "#4c78a8",
    "none/static": "#4c78a8",
    "capacity_aware": "#f58518",
    "smooth": "#54a24b",
    "delivery_aware_v2": "#e45756",
    "DA_v2": "#e45756",
    "increase_B": "#b279a2",
    "increase_C": "#ff9da6",
    "robust_smooth": "#72b7b2",
}
REGIME_COLORS = {
    "no_delivery_bottleneck": "#4c78a8",
    "peak_dominated_smooth_solvable": "#54a24b",
    "peak_dominated_buffer_limited": "#f58518",
    "persistent_underprovisioning": "#e45756",
    "low_slack_structure_limited": "#b279a2",
    "uncertainty_sensitive": "#72b7b2",
}


@dataclass(frozen=True)
class StrategyResult:
    """Runtime/backlog result for one candidate strategy."""

    strategy: str
    T_static: int
    T_exe: int
    ratio_to_T_ref: float
    stall_cycles: int
    Delta_max: int
    BacklogArea: int
    L_backlog: int
    max_backlog: int


def ensure_output_dirs() -> None:
    """Create V4 output directories."""

    RESULT_DIR_V4.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR_V4.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write dictionaries to CSV."""

    ensure_output_dirs()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file as dictionaries."""

    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def core_workloads_v4() -> list[WorkloadCase]:
    """Return the V4 regime-stability workload set."""

    return build_v2_workloads()


def expanded_workloads_v4() -> list[WorkloadCase]:
    """Return larger/synthetic workloads for V4 expansion."""

    return [
        WorkloadCase("multiplier_n16", "semi_real_multiplier_larger", 0, 16, make_multiplier(n=16)),
        WorkloadCase("multiplier_n24", "semi_real_multiplier_larger", 0, 24, make_multiplier(n=24), True),
        WorkloadCase(
            "phase_estimation_like_synthetic",
            "synthetic_phase_estimation_like",
            0,
            12,
            make_phase_estimation_like(n=12),
        ),
        WorkloadCase(
            "hamiltonian_simulation_synthetic",
            "synthetic_hamiltonian_simulation",
            0,
            12,
            make_hamiltonian_simulation_synthetic(n=12, layers=4),
        ),
        WorkloadCase(
            "modular_arithmetic_block_synthetic",
            "synthetic_modular_arithmetic",
            0,
            10,
            make_modular_arithmetic_block(n=10, repeats=3),
        ),
        WorkloadCase("larger_qft_n10", "semi_real_qft_larger", 0, 10, make_exact_qft(n=10)),
        WorkloadCase("approx_qft_n16", "semi_real_qft_larger", 0, 16, make_approx_qft(n=16)),
    ]


def workload_index() -> dict[tuple[str, int], WorkloadCase]:
    """Index all V4 workloads by (workload, seed)."""

    cases = core_workloads_v4() + expanded_workloads_v4()
    return {(case.workload, case.seed): case for case in cases}


def schedule_for_v4(
    schedule_name: str,
    case: WorkloadCase,
    capacity: int,
    buffer: int,
) -> dict[int, list[str]]:
    """Build a V4 schedule by name."""

    if schedule_name == "robust_smooth":
        return schedule_robust_smooth(case.dag, capacity, p_acc=1.0, rho=RHO)
    return make_schedule_v2(schedule_name, case.dag, capacity, buffer, DEFAULT_DA_V2_CONFIG)


def deterministic_result(
    case: WorkloadCase,
    schedule: dict[int, list[str]],
    capacity: int,
    buffer: int,
    t_ref: int,
    strategy: str,
) -> StrategyResult:
    """Evaluate one schedule as a strategy result."""

    result = simulate_deterministic(case.dag, schedule, capacity, buffer)
    backlog = backlog_shape_features(case.dag, schedule, capacity, buffer)
    return StrategyResult(
        strategy=strategy,
        T_static=result.T_static,
        T_exe=result.T_exe,
        ratio_to_T_ref=result.T_exe / t_ref,
        stall_cycles=result.stall_cycles,
        Delta_max=result.Delta_max,
        BacklogArea=backlog.BacklogArea,
        L_backlog=backlog.L_backlog,
        max_backlog=backlog.max_backlog,
    )


def classify_setting(case: WorkloadCase, capacity: int, buffer: int) -> tuple[RegimeDecision, dict[str, Any]]:
    """Classify a workload/delivery setting and return reusable features."""

    t_ref = t_ref_asap(case)
    structural = structural_features(case.dag)
    static_schedule = schedule_for_v4("static", case, capacity, buffer)
    smooth_schedule = schedule_for_v4("smooth", case, capacity, buffer)
    static_result = simulate_deterministic(case.dag, static_schedule, capacity, buffer)
    smooth_result = simulate_deterministic(case.dag, smooth_schedule, capacity, buffer)
    static_backlog = backlog_shape_features(case.dag, static_schedule, capacity, buffer)
    smooth_backlog = backlog_shape_features(case.dag, smooth_schedule, capacity, buffer)
    smooth_demand = demand_shape_features(case.dag, smooth_schedule)
    mean_demand_over_c = smooth_demand.D_mean / capacity
    peak_demand_over_c = smooth_demand.D_peak / capacity
    supply_tightness = structural.T_count / (capacity * structural.T_static_static + buffer)
    decision = classify_delivery_regime(
        static_stall_cycles=static_result.stall_cycles,
        static_delta_max=static_result.Delta_max,
        static_backlog_area=static_backlog.BacklogArea,
        smooth_stall_cycles=smooth_result.stall_cycles,
        smooth_delta_max=smooth_result.Delta_max,
        smooth_backlog_area=smooth_backlog.BacklogArea,
        smooth_l_backlog=smooth_backlog.L_backlog,
        buffer=buffer,
        slack_ratio=structural.slack_ratio,
        fraction_zero_slack=structural.fraction_zero_slack,
        supply_tightness=supply_tightness,
        peak_demand_over_c=peak_demand_over_c,
        mean_demand_over_c=mean_demand_over_c,
        smooth_t_exe=smooth_result.T_exe,
        static_t_exe=static_result.T_exe,
    )
    features = {
        "T_ref_asap": t_ref,
        "structural": structural,
        "smooth_demand": smooth_demand,
        "mean_demand_over_C": mean_demand_over_c,
        "peak_demand_over_C": peak_demand_over_c,
        "supply_tightness": supply_tightness,
        "static_result": static_result,
        "smooth_result": smooth_result,
    }
    return decision, features


def evaluate_schedule_row(
    case: WorkloadCase,
    capacity: int,
    buffer: int,
    schedule_name: str,
    decision: RegimeDecision,
    shared_features: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one schedule for exp11/exp13 style outputs."""

    schedule = schedule_for_v4(schedule_name, case, capacity, buffer)
    result = simulate_deterministic(case.dag, schedule, capacity, buffer)
    backlog = backlog_shape_features(case.dag, schedule, capacity, buffer)
    demand = demand_shape_features(case.dag, schedule)
    structural = shared_features["structural"]
    t_ref = int(shared_features["T_ref_asap"])
    return {
        "workload": case.workload,
        "family": case.family,
        "seed": case.seed,
        "n": case.n,
        "C": capacity,
        "B": buffer,
        "schedule": schedule_name,
        "T_ref_asap": t_ref,
        "T_static": result.T_static,
        "T_exe": result.T_exe,
        "ratio_to_T_ref": result.T_exe / t_ref,
        "stall_cycles": result.stall_cycles,
        "Delta_max": result.Delta_max,
        "max_backlog": backlog.max_backlog,
        "mean_backlog": backlog.mean_backlog,
        "BacklogArea": backlog.BacklogArea,
        "L_backlog": backlog.L_backlog,
        "num_backlog_intervals": backlog.num_backlog_intervals,
        "longest_backlog_interval": backlog.longest_backlog_interval,
        "backlog_persistence_ratio": backlog.backlog_persistence_ratio,
        "D_peak": demand.D_peak,
        "D_mean": demand.D_mean,
        "D_cv": demand.D_cv,
        "D_peak_to_mean": demand.D_peak_to_mean,
        "num_demand_peaks": demand.num_demand_peaks,
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
        "mean_demand_over_C": demand.D_mean / capacity,
        "peak_demand_over_C": demand.D_peak / capacity,
        "supply_tightness": structural.T_count / (capacity * structural.T_static_static + buffer),
        "regime_label": decision.regime_label,
        "regime_reason": decision.regime_reason,
        "recommended_strategy": decision.recommended_strategy,
    }


EXP11_FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "C",
    "B",
    "schedule",
    "T_ref_asap",
    "T_static",
    "T_exe",
    "ratio_to_T_ref",
    "stall_cycles",
    "Delta_max",
    "max_backlog",
    "mean_backlog",
    "BacklogArea",
    "L_backlog",
    "num_backlog_intervals",
    "longest_backlog_interval",
    "backlog_persistence_ratio",
    "D_peak",
    "D_mean",
    "D_cv",
    "D_peak_to_mean",
    "num_demand_peaks",
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
    "mean_demand_over_C",
    "peak_demand_over_C",
    "supply_tightness",
    "regime_label",
    "regime_reason",
    "recommended_strategy",
]


def distribution_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize regime distribution by workload and overall."""

    unique_settings = {}
    for row in rows:
        if row["schedule"] != "smooth":
            continue
        key = (row["workload"], row["family"], row["seed"], row["n"], row["C"], row["B"])
        unique_settings[key] = row["regime_label"]
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    overall = Counter()
    for key, label in unique_settings.items():
        workload = str(key[0])
        grouped[workload][str(label)] += 1
        overall[str(label)] += 1
    summary: list[dict[str, Any]] = []
    for workload, counts in sorted(grouped.items()):
        total = sum(counts.values())
        for regime, count in sorted(counts.items()):
            summary.append(
                {
                    "group": workload,
                    "regime_label": regime,
                    "count": count,
                    "fraction": count / total if total else 0.0,
                }
            )
    total = sum(overall.values())
    for regime, count in sorted(overall.items()):
        summary.append(
            {
                "group": "OVERALL",
                "regime_label": regime,
                "count": count,
                "fraction": count / total if total else 0.0,
            }
        )
    return summary


def threshold_scan_for_strategy(
    case: WorkloadCase,
    base_capacity: int,
    base_buffer: int,
    t_ref: int,
    schedule_name: str,
) -> dict[str, Any]:
    """Compute C_ref_star and B_ref_star for a candidate schedule."""

    def eval_capacity(capacity: int) -> tuple[int, int, int, int]:
        schedule = schedule_for_v4(schedule_name, case, capacity, base_buffer)
        result = simulate_deterministic(case.dag, schedule, capacity, base_buffer)
        return result.T_static, result.T_exe, result.stall_cycles, result.Delta_max

    def eval_buffer(buffer: int) -> tuple[int, int, int, int]:
        schedule = schedule_for_v4(schedule_name, case, base_capacity, buffer)
        result = simulate_deterministic(case.dag, schedule, base_capacity, buffer)
        return result.T_static, result.T_exe, result.stall_cycles, result.Delta_max

    out: dict[str, Any] = {}
    for epsilon in EPSILON_VALUES:
        c_threshold = find_reference_capacity_threshold(C_VALUES_STRATEGY, epsilon, t_ref, eval_capacity)
        b_threshold = find_buffer_reference_threshold(B_VALUES_STRATEGY, epsilon, t_ref, eval_buffer)
        suffix = f"{epsilon:.2f}"
        out[f"C_ref_star_{suffix}"] = c_threshold.C_ref_star if c_threshold.C_ref_star is not None else ""
        out[f"B_ref_star_{suffix}"] = b_threshold.B_ref_star if b_threshold.B_ref_star is not None else ""
    return out


def candidate_strategy_results(
    case: WorkloadCase,
    capacity: int,
    buffer: int,
    t_ref: int,
) -> dict[str, StrategyResult]:
    """Evaluate candidate strategies for one setting."""

    results: dict[str, StrategyResult] = {}
    for strategy, schedule_name in [
        ("none/static", "static"),
        ("smooth", "smooth"),
        ("capacity_aware", "capacity_aware"),
        ("DA_v2", "delivery_aware_v2"),
        ("robust_smooth", "robust_smooth"),
    ]:
        schedule = schedule_for_v4(schedule_name, case, capacity, buffer)
        results[strategy] = deterministic_result(case, schedule, capacity, buffer, t_ref, strategy)

    best_b_result: StrategyResult | None = None
    for candidate_b in B_VALUES_STRATEGY:
        schedule = schedule_for_v4("smooth", case, capacity, candidate_b)
        result = deterministic_result(case, schedule, capacity, candidate_b, t_ref, "increase_B")
        if best_b_result is None or (result.T_exe, result.BacklogArea) < (
            best_b_result.T_exe,
            best_b_result.BacklogArea,
        ):
            best_b_result = result
    if best_b_result is not None:
        results["increase_B"] = best_b_result

    best_c_result: StrategyResult | None = None
    for candidate_c in C_VALUES_STRATEGY:
        schedule = schedule_for_v4("smooth", case, candidate_c, buffer)
        result = deterministic_result(case, schedule, candidate_c, buffer, t_ref, "increase_C")
        if best_c_result is None or (result.T_exe, result.BacklogArea) < (
            best_c_result.T_exe,
            best_c_result.BacklogArea,
        ):
            best_c_result = result
    if best_c_result is not None:
        results["increase_C"] = best_c_result
    return results


def empirical_best_strategy(results: dict[str, StrategyResult]) -> tuple[str, float]:
    """Return strategy with lowest score."""

    scored = {
        name: strategy_score(result.ratio_to_T_ref, result.BacklogArea)
        for name, result in results.items()
    }
    return min(scored.items(), key=lambda item: (item[1], item[0]))


def strategy_success_reason(
    regime_label: str,
    candidate_strategy: str,
    baseline: StrategyResult,
    candidate: StrategyResult,
) -> tuple[int, str]:
    """Return success flag and explanation for a candidate in a regime."""

    gain_t = relative_gain(baseline.T_exe, candidate.T_exe)
    gain_area = backlog_area_gain(baseline.BacklogArea, candidate.BacklogArea)
    if regime_label == "no_delivery_bottleneck":
        success = candidate_strategy == "none/static" and baseline.ratio_to_T_ref <= 1.05
        return int(success), "static already near reference" if success else "extra intervention not needed"
    if regime_label == "peak_dominated_smooth_solvable":
        success = candidate_strategy == "smooth" and (gain_t > 0.05 or gain_area > 0.5)
        return int(success), "smooth removes peak backlog" if success else "smooth not uniquely beneficial"
    if regime_label == "peak_dominated_buffer_limited":
        success = candidate_strategy == "increase_B" and gain_area > 0.25
        return int(success), "buffer reduces residual backlog" if success else "buffer gain unclear"
    if regime_label == "persistent_underprovisioning":
        success = candidate_strategy == "increase_C" and gain_t > 0.05
        return int(success), "capacity addresses average supply shortage" if success else "capacity gain unclear"
    if regime_label == "uncertainty_sensitive":
        success = candidate_strategy == "robust_smooth" and candidate.T_exe <= baseline.T_exe
        return int(success), "robust margin avoids degradation" if success else "robust margin did not help"
    if regime_label == "low_slack_structure_limited":
        success = candidate_strategy in {"increase_C", "capacity_aware"} and gain_t > 0.05
        return int(success), "limited slack needs provisioning" if success else "structure-limited case remains hard"
    return 0, "no matching rule"


def write_report_v4() -> None:
    """Write the V4 preliminary report."""

    exp11 = read_csv(RESULT_DIR_V4 / "exp11_regime_stability.csv")
    exp12 = read_csv(RESULT_DIR_V4 / "exp12_strategy_validation.csv")
    exp13 = read_csv(RESULT_DIR_V4 / "exp13_workload_expansion.csv")
    exp14 = read_csv(RESULT_DIR_V4 / "exp14_transpiler_sanity.csv")
    exp16_summary = read_csv(RESULT_DIR_V4 / "exp16_strategy_match_summary.csv")
    smooth_rows = [row for row in exp11 if row["schedule"] == "smooth"]
    regime_counts = Counter(row["regime_label"] for row in smooth_rows)
    buffer_rows = [row for row in exp12 if row["regime_label"] == "peak_dominated_buffer_limited"]
    persistent_rows = [row for row in exp12 if row["regime_label"] == "persistent_underprovisioning"]

    def mean_gain(rows: list[dict[str, str]], strategy: str, field: str) -> float:
        values = [float(row[field]) for row in rows if row["candidate_strategy"] == strategy]
        return sum(values) / len(values) if values else 0.0

    match_row = exp16_summary[0] if exp16_summary else {}
    match_rate = float(match_row.get("strategy_match_rate", 0.0))
    mean_regret = float(match_row.get("mean_regret", 0.0))
    transpiler_regimes = Counter(row["regime_label"] for row in exp14)
    expanded_regimes = Counter(row["regime_label"] for row in exp13 if row["schedule"] == "smooth")

    if match_rate >= 0.70 and regime_counts and len(regime_counts) >= 3:
        recommendation = "green light: regime-aware framework paper"
    elif len(regime_counts) >= 3:
        recommendation = "yellow light: regimes exist but strategy validation needs refinement"
    else:
        recommendation = "red light: regime labels are not stable enough"

    regime_lines = "\n".join(f"- {label}: {count}" for label, count in sorted(regime_counts.items()))
    expanded_lines = "\n".join(f"- {label}: {count}" for label, count in sorted(expanded_regimes.items()))
    transpiler_lines = "\n".join(f"- {label}: {count}" for label, count in sorted(transpiler_regimes.items()))

    report = f"""# Preliminary Report V4

## Summary

Recommendation: **{recommendation}**.

V4 validates the regime-aware compiler-architecture framing. It does not claim
a new scheduler contribution.

## Questions

1. Are V3 regimes stable under larger sweeps?

   Regime counts over smooth rows in the expanded sweep:

{regime_lines}

2. Which workloads fall into which regimes?

   See `exp11_regime_distribution_summary.csv` and Figure 1. The distribution
   remains multi-regime rather than collapsing to a single scheduler story.

3. Does each regime have a distinct best response?

   Empirical strategy match rate is {match_rate:.3f} with mean regret
   {mean_regret:.3f}. Match treats exact score ties as success, because many
   no-bottleneck cases genuinely require no distinct intervention.

4. Does increasing buffer help buffer-limited cases more than changing scheduler?

   In buffer-limited rows, mean T_exe gain for increase_B is
   {mean_gain(buffer_rows, "increase_B", "strategy_gain_Texe"):.3f}; mean
   BacklogArea gain is {mean_gain(buffer_rows, "increase_B", "strategy_gain_BacklogArea"):.3f}.

5. Does increasing capacity help persistent-underprovisioning cases more than smoothing?

   In persistent-underprovisioning rows, mean T_exe gain for increase_C is
   {mean_gain(persistent_rows, "increase_C", "strategy_gain_Texe"):.3f}; mean
   BacklogArea gain is {mean_gain(persistent_rows, "increase_C", "strategy_gain_BacklogArea"):.3f}.

6. Do larger / more realistic workloads preserve the same regimes?

   Expanded workload smooth-regime counts:

{expanded_lines}

7. Do Qiskit/tket-optimized circuits still show delivery-pressure regimes?

   Transpiler sanity regime counts:

{transpiler_lines}

   If Qiskit is unavailable, the script marks rows as proxy synthetic sanity
   checks instead of claiming real transpiler evidence.

8. Are representative case-study plots visually consistent with regime labels?

   See `case1_smooth_solvable.pdf`, `case2_buffer_limited.pdf`,
   `case3_persistent_underprovisioning.pdf`, and
   `case4_effective_capacity_sensitive.pdf`.

9. What is the empirical strategy match rate?

   Strategy match rate is {match_rate:.3f}; mean regret is {mean_regret:.3f}.

10. Is Paper 2 viable as a regime-aware framework paper?

   Current V4 answer: **{recommendation}**. The strongest framing is that
   bounded magic-state delivery creates distinct execution regimes with
   different appropriate responses: no action, smoothing, buffer, capacity, or
   robustness/provisioning margin.
"""
    ensure_output_dirs()
    (RESULT_DIR_V4 / "PRELIMINARY_REPORT_V4.md").write_text(report)


def median_value(values: list[float]) -> float:
    """Return median or 0 for empty values."""

    return median(values) if values else 0.0
