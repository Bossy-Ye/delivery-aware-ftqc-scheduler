"""Shared utilities for V2 preliminary experiments."""

from __future__ import annotations

import csv
import os
import sys
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

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.metrics.backlog import (
    backlog_active_length,
    buffer_adjusted_backlog,
    max_backlog,
    mean_backlog,
)
from ftqc_delivery.metrics.delta_max import t_demand_trace
from ftqc_delivery.schedulers import (
    DeliveryAwareV2Config,
    DeliveryAwareV2Weights,
    schedule_capacity_aware,
    schedule_delivery_aware,
    schedule_delivery_aware_v2,
    schedule_smooth,
    schedule_static,
)
from ftqc_delivery.simulator.deterministic import simulate_deterministic
from ftqc_delivery.workloads import (
    make_adder,
    make_approx_qft,
    make_exact_qft,
    make_high_compressibility,
    make_low_compressibility,
    make_medium_compressibility,
    make_multiplier,
    make_phase_estimation_like,
)


RESULT_DIR_V2 = ROOT / "results" / "prelim_v2"
FIGURE_DIR_V2 = ROOT / "figures" / "prelim_v2"
C_VALUES = [1, 2, 3, 4, 5]
B_VALUES = [0, 4, 8, 12]
EXPENSIVE_C_VALUES = [1, 2, 3]
EXPENSIVE_B_VALUES = [0, 8]
THRESHOLD_C_VALUES = list(range(1, 11))
EPSILON_VALUES = [0.05, 0.10]
SCHEDULES_V2 = [
    "static",
    "capacity_aware",
    "smooth",
    "delivery_aware_v1",
    "delivery_aware_v2",
]
SCHEDULE_COLORS = {
    "static": "#4c78a8",
    "capacity_aware": "#f58518",
    "smooth": "#54a24b",
    "delivery_aware_v1": "#b279a2",
    "delivery_aware_v2": "#e45756",
}
DEFAULT_DA_V2_CONFIG = DeliveryAwareV2Config()


@dataclass(frozen=True)
class WorkloadCase:
    """Metadata plus DAG for one V2 workload."""

    workload: str
    family: str
    seed: int
    n: int
    dag: CircuitDAG
    expensive: bool = False


def ensure_output_dirs() -> None:
    """Create V2 output directories."""

    RESULT_DIR_V2.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR_V2.mkdir(parents=True, exist_ok=True)


def load_da_v2_config(path: Path | None = None) -> DeliveryAwareV2Config:
    """Load DA-v2 weights from YAML if available, otherwise use defaults."""

    if path is None or not path.exists():
        return DEFAULT_DA_V2_CONFIG
    try:
        import yaml
    except ImportError:
        return DEFAULT_DA_V2_CONFIG
    data = yaml.safe_load(path.read_text()) or {}
    weights_data = data.get("weights", {})
    weights = DeliveryAwareV2Weights(
        lambda_exe=float(weights_data.get("lambda_exe", 2.0)),
        lambda_delta=float(weights_data.get("lambda_delta", 1.0)),
        lambda_backlog=float(weights_data.get("lambda_backlog", 1.0)),
        lambda_static=float(weights_data.get("lambda_static", 0.5)),
        lambda_critical=float(weights_data.get("lambda_critical", 0.5)),
    )
    return DeliveryAwareV2Config(
        lookahead_horizon=int(data.get("lookahead_horizon", 5)),
        weights=weights,
    )


def build_v2_workloads() -> list[WorkloadCase]:
    """Build V1 workloads plus larger/semi-real V2 stress tests."""

    workloads: list[WorkloadCase] = []
    for seed in [0, 1, 2, 3, 4]:
        workloads.extend(
            [
                WorkloadCase(
                    "constructed_high",
                    "high_compressibility",
                    seed,
                    24,
                    make_high_compressibility(seed=seed, n=24),
                ),
                WorkloadCase(
                    "constructed_medium",
                    "medium_compressibility",
                    seed,
                    24,
                    make_medium_compressibility(seed=seed, n=24),
                ),
                WorkloadCase(
                    "constructed_low",
                    "low_compressibility",
                    seed,
                    24,
                    make_low_compressibility(seed=seed, n=24),
                ),
            ]
        )

    for n in [8, 16]:
        workloads.append(WorkloadCase(f"adder_n{n}", "semi_real_adder", 0, n, make_adder(n=n)))
    for n in [4, 6, 8, 12]:
        workloads.append(
            WorkloadCase(f"multiplier_n{n}", "semi_real_multiplier", 0, n, make_multiplier(n=n))
        )
    workloads.append(WorkloadCase("exact_qft_n8", "semi_real_qft", 0, 8, make_exact_qft(n=8)))
    workloads.append(
        WorkloadCase("approx_qft_n12", "semi_real_qft", 0, 12, make_approx_qft(n=12))
    )

    workloads.extend(
        [
            WorkloadCase(
                "larger_multiplier_n16",
                "semi_real_multiplier_larger",
                0,
                16,
                make_multiplier(n=16),
                expensive=True,
            ),
            WorkloadCase(
                "phase_estimation_like_n10",
                "semi_real_phase_estimation_like",
                0,
                10,
                make_phase_estimation_like(n=10),
                expensive=True,
            ),
            WorkloadCase(
                "larger_exact_qft_n12",
                "semi_real_qft_larger",
                0,
                12,
                make_exact_qft(n=12),
                expensive=True,
            ),
        ]
    )
    return workloads


def parameters_for_case(case: WorkloadCase) -> tuple[list[int], list[int]]:
    """Return C and B scans for a workload."""

    if case.expensive:
        return EXPENSIVE_C_VALUES, EXPENSIVE_B_VALUES
    return C_VALUES, B_VALUES


def make_schedule_v2(
    schedule_name: str,
    dag: CircuitDAG,
    capacity: int,
    buffer: int,
    da_v2_config: DeliveryAwareV2Config = DEFAULT_DA_V2_CONFIG,
) -> dict[int, list[str]]:
    """Build a V2 schedule by name."""

    if schedule_name == "static":
        return schedule_static(dag)
    if schedule_name == "capacity_aware":
        return schedule_capacity_aware(dag, capacity)
    if schedule_name == "smooth":
        return schedule_smooth(dag, capacity)
    if schedule_name == "delivery_aware_v1":
        return schedule_delivery_aware(dag, capacity, buffer)
    if schedule_name == "delivery_aware_v2":
        return schedule_delivery_aware_v2(dag, capacity, buffer, da_v2_config)
    raise ValueError(f"Unknown schedule: {schedule_name}")


def t_ref_asap(case: WorkloadCase) -> int:
    """Return unconstrained ASAP logical depth for the workload."""

    return max(schedule_static(case.dag), default=0)


def t_ref_best(
    case: WorkloadCase,
    buffer: int,
    da_v2_config: DeliveryAwareV2Config = DEFAULT_DA_V2_CONFIG,
) -> int:
    """Return a sensitivity reference using best high-capacity static depth."""

    high_c = max(THRESHOLD_C_VALUES)
    schedules = [
        schedule_static(case.dag),
        schedule_capacity_aware(case.dag, high_c),
        schedule_smooth(case.dag, high_c),
        schedule_delivery_aware_v2(case.dag, high_c, buffer, da_v2_config),
    ]
    return min(max(schedule, default=0) for schedule in schedules)


def evaluate_case_v2(
    case: WorkloadCase,
    schedule_name: str,
    capacity: int,
    buffer: int,
    da_v2_config: DeliveryAwareV2Config,
    reference_asap: int | None = None,
) -> dict[str, Any]:
    """Schedule and simulate one V2 case."""

    if reference_asap is None:
        reference_asap = t_ref_asap(case)
    schedule = make_schedule_v2(schedule_name, case.dag, capacity, buffer, da_v2_config)
    result = simulate_deterministic(case.dag, schedule, capacity, buffer)
    return {
        "workload": case.workload,
        "family": case.family,
        "seed": case.seed,
        "n": case.n,
        "schedule": schedule_name,
        "C": capacity,
        "B": buffer,
        "T_static": result.T_static,
        "T_exe": result.T_exe,
        "stall_cycles": result.stall_cycles,
        "slowdown_vs_own_static": result.slowdown,
        "ratio_to_T_ref_asap": result.T_exe / reference_asap,
        "Delta_max": result.Delta_max,
        "L_backlog": result.L_backlog,
        "max_backlog": max_backlog(case.dag, schedule, capacity, buffer),
        "mean_backlog": mean_backlog(case.dag, schedule, capacity, buffer),
        "static_depth_penalty_vs_static": result.T_static / reference_asap,
    }


def reduction(baseline: float, value: float) -> float:
    """Return relative reduction `(baseline-value)/baseline`, guarding zero."""

    if baseline == 0:
        return 0.0
    return (baseline - value) / baseline


def add_pairwise_reductions(group: list[dict[str, Any]]) -> None:
    """Add V2 paired reduction columns to a group sharing workload/C/B."""

    by_schedule = {row["schedule"]: row for row in group}
    baseline_names = {
        "static": "static",
        "smooth": "smooth",
        "ca": "capacity_aware",
        "DA_v1": "delivery_aware_v1",
    }
    for row in group:
        for suffix, schedule_name in baseline_names.items():
            baseline = by_schedule[schedule_name]
            row[f"Texe_reduction_vs_{suffix}"] = reduction(baseline["T_exe"], row["T_exe"])
            row[f"Delta_reduction_vs_{suffix}"] = reduction(
                baseline["Delta_max"], row["Delta_max"]
            )
            row[f"stall_reduction_vs_{suffix}"] = reduction(
                baseline["stall_cycles"], row["stall_cycles"]
            )
            row[f"Lbacklog_reduction_vs_{suffix}"] = reduction(
                baseline["L_backlog"], row["L_backlog"]
            )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write rows to CSV with fixed field order."""

    ensure_output_dirs()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read CSV rows as dictionaries."""

    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def generate_v2_figures(exp1_rows: list[dict[str, Any]], exp2_rows: list[dict[str, Any]]) -> None:
    """Generate the five V2 preliminary figures."""

    ensure_output_dirs()
    import matplotlib.pyplot as plt

    _plot_v2_demand_trace()
    _plot_v2_paired_t_exe(exp1_rows)
    _plot_v2_pareto(exp1_rows)
    _plot_v2_c_ref_star(exp2_rows)
    _plot_v2_backlog(exp1_rows)
    plt.close("all")


def _plot_v2_demand_trace() -> None:
    import matplotlib.pyplot as plt

    c_value = 2
    b_value = 4
    cases = [
        WorkloadCase(
            "constructed_high",
            "high_compressibility",
            0,
            24,
            make_high_compressibility(seed=0, n=24),
        ),
        WorkloadCase("multiplier_n8", "semi_real_multiplier", 0, 8, make_multiplier(n=8)),
        WorkloadCase("exact_qft_n8", "semi_real_qft", 0, 8, make_exact_qft(n=8)),
    ]
    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=False)
    for ax, case in zip(axes, cases, strict=True):
        schedules = {
            "static": make_schedule_v2("static", case.dag, c_value, b_value),
            "smooth": make_schedule_v2("smooth", case.dag, c_value, b_value),
            "delivery_aware_v2": make_schedule_v2(
                "delivery_aware_v2", case.dag, c_value, b_value, DEFAULT_DA_V2_CONFIG
            ),
        }
        horizon = max(max(schedule) for schedule in schedules.values())
        for schedule_name, schedule in schedules.items():
            demand = t_demand_trace(case.dag, schedule, horizon=horizon)
            ax.step(
                demand.keys(),
                demand.values(),
                where="mid",
                label=schedule_name,
                color=SCHEDULE_COLORS[schedule_name],
            )
        ax.axhline(c_value, color="black", linewidth=1, linestyle="--", label="C")
        ax.set_title(case.workload)
        ax.set_ylabel("T demand")
        ax.grid(alpha=0.25)
    axes[-1].set_xlabel("logical time")
    axes[0].legend(loc="upper right", ncols=4)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V2 / "fig1_demand_trace_static_smooth_DAv2.pdf")


def _da_v2_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["schedule"] == "delivery_aware_v2"]


def _plot_v2_paired_t_exe(rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    da_rows = _da_v2_rows(rows)
    labels = ["static", "smooth", "ca", "DA_v1"]
    data = [[float(row[f"Texe_reduction_vs_{label}"]) for row in da_rows] for label in labels]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.boxplot(data, labels=labels, showfliers=False)
    ax.axhline(0, color="black", linewidth=1)
    ax.set_ylabel("DA_v2 paired T_exe reduction")
    ax.set_title("DA_v2 paired executable-runtime improvements")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V2 / "fig2_paired_Texe_improvement.pdf")


def _plot_v2_pareto(rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 5))
    for schedule_name in ["capacity_aware", "smooth", "delivery_aware_v1", "delivery_aware_v2"]:
        xs = [
            float(row["static_depth_penalty_vs_static"])
            for row in rows
            if row["schedule"] == schedule_name
        ]
        ys = [
            float(row["Delta_reduction_vs_static"])
            for row in rows
            if row["schedule"] == schedule_name
        ]
        ax.scatter(
            xs,
            ys,
            label=schedule_name,
            alpha=0.4,
            s=18,
            color=SCHEDULE_COLORS[schedule_name],
        )
    ax.axhline(0, color="black", linewidth=1)
    ax.axvline(1, color="black", linewidth=1, linestyle="--")
    ax.set_xlabel("T_static(schedule) / T_static(static)")
    ax.set_ylabel("Delta_max reduction vs static")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V2 / "fig3_delta_vs_static_penalty_v2.pdf")


def _plot_v2_c_ref_star(rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    workloads = ["constructed_high", "multiplier_n8", "exact_qft_n8", "phase_estimation_like_n10"]
    selected = [
        row
        for row in rows
        if row["workload"] in workloads
        and int(row["seed"]) == 0
        and int(row["B"]) in {4, 8}
        and abs(float(row["epsilon"]) - 0.05) < 1e-9
        and row["T_ref_type"] == "asap"
    ]
    width = 0.15
    x_positions = list(range(len(workloads)))
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for schedule_index, schedule_name in enumerate(SCHEDULES_V2):
        values: list[float] = []
        for workload in workloads:
            matches = [
                row
                for row in selected
                if row["workload"] == workload and row["schedule"] == schedule_name
            ]
            match = sorted(matches, key=lambda row: int(row["B"]))[0] if matches else None
            c_star = match["C_ref_star"] if match else ""
            values.append(float(c_star) if c_star else max(THRESHOLD_C_VALUES) + 1)
        offsets = [x + (schedule_index - 2) * width for x in x_positions]
        ax.bar(
            offsets,
            values,
            width=width,
            label=schedule_name,
            color=SCHEDULE_COLORS[schedule_name],
        )
    ax.set_xticks(x_positions)
    ax.set_xticklabels(workloads, rotation=15)
    ax.set_ylabel("C_ref_star_0.05 (11 means target not met)")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncols=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V2 / "fig4_C_ref_star.pdf")


def _plot_v2_backlog(rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    metrics = ["L_backlog", "max_backlog", "mean_backlog"]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for ax, metric in zip(axes, metrics, strict=True):
        data = []
        for schedule_name in ["smooth", "delivery_aware_v2"]:
            data.append(
                [
                    float(row[metric])
                    for row in rows
                    if row["schedule"] == schedule_name
                    and row["family"] != "low_compressibility"
                ]
            )
        ax.boxplot(data, labels=["smooth", "DA_v2"], showfliers=False)
        ax.set_title(metric)
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V2 / "fig5_backlog_duration.pdf")


def write_preliminary_report_v2(exp1_path: Path, exp2_path: Path, exp5_path: Path | None = None) -> None:
    """Write the V2 preliminary report with direct smooth comparisons."""

    exp1 = read_csv(exp1_path)
    exp2 = read_csv(exp2_path)
    exp5 = read_csv(exp5_path) if exp5_path and exp5_path.exists() else []
    da_rows = [row for row in exp1 if row["schedule"] == "delivery_aware_v2"]
    nontrivial = [row for row in da_rows if row["family"] != "low_compressibility"]
    real_rows = [row for row in da_rows if row["family"].startswith("semi_real")]

    def counts(column: str, source: list[dict[str, str]]) -> tuple[int, int, int]:
        better = sum(1 for row in source if float(row[column]) > 1e-12)
        worse = sum(1 for row in source if float(row[column]) < -1e-12)
        equal = len(source) - better - worse
        return better, equal, worse

    texe_vs_v1 = counts("Texe_reduction_vs_DA_v1", da_rows)
    texe_vs_smooth = counts("Texe_reduction_vs_smooth", nontrivial)
    texe_vs_static = counts("Texe_reduction_vs_static", da_rows)
    delta_vs_smooth = counts("Delta_reduction_vs_smooth", nontrivial)
    backlog_vs_smooth = counts("Lbacklog_reduction_vs_smooth", nontrivial)
    real_vs_smooth = counts("Texe_reduction_vs_smooth", real_rows)

    cstar_better = 0
    cstar_equal = 0
    cstar_worse = 0
    cstar_missing = 0
    grouped: dict[tuple[str, str, str, str, str, str, str], dict[str, dict[str, str]]] = {}
    for row in exp2:
        if row["T_ref_type"] != "asap":
            continue
        key = (
            row["workload"],
            row["family"],
            row["seed"],
            row["n"],
            row["B"],
            row["epsilon"],
            row["T_ref_type"],
        )
        grouped.setdefault(key, {})[row["schedule"]] = row
    for schedules in grouped.values():
        da = schedules.get("delivery_aware_v2")
        smooth = schedules.get("smooth")
        if not da or not smooth or not da["C_ref_star"] or not smooth["C_ref_star"]:
            cstar_missing += 1
            continue
        da_c = int(da["C_ref_star"])
        smooth_c = int(smooth["C_ref_star"])
        if da_c < smooth_c:
            cstar_better += 1
        elif da_c == smooth_c:
            cstar_equal += 1
        else:
            cstar_worse += 1

    optimal_note = "The optional small optimal comparison was not run."
    if exp5:
        da_gaps = [
            float(row["gap_percent"])
            for row in exp5
            if row["schedule"] == "delivery_aware_v2"
        ]
        smooth_gaps = [float(row["gap_percent"]) for row in exp5 if row["schedule"] == "smooth"]
        if da_gaps and smooth_gaps:
            optimal_note = (
                f"Small near-optimal comparison: DA_v2 mean gap {sum(da_gaps)/len(da_gaps):.3f}, "
                f"smooth mean gap {sum(smooth_gaps)/len(smooth_gaps):.3f}."
            )

    smooth_better_rate = texe_vs_smooth[0] / max(1, len(nontrivial))
    smooth_worse_rate = texe_vs_smooth[2] / max(1, len(nontrivial))
    cstar_signal = cstar_better > 0 and cstar_better >= cstar_worse
    if smooth_better_rate >= 0.20 and smooth_worse_rate < 0.10 and cstar_signal:
        recommendation = "new scheduler paper"
    elif smooth_better_rate > 0.05 or cstar_better > 0:
        recommendation = "schedule trade-off framework paper"
    else:
        recommendation = "stop/redesign"

    report = f"""# Preliminary Report V2

## Summary

Recommendation: **{recommendation}**.

This report is intentionally conservative. The main comparison is DA_v2 versus
`sigma_smooth`, not DA_v2 versus `sigma_static`. The arithmetic, QFT, multiplier,
and phase-estimation-like workloads are still semi-real trace-level
approximations, not full circuit extraction.

## Questions

1. Does DA_v2 beat DA_v1?

   T_exe vs DA_v1: better/equal/worse = {texe_vs_v1[0]}/{texe_vs_v1[1]}/{texe_vs_v1[2]}.

2. Does DA_v2 beat smooth?

   On nontrivial cases, T_exe vs smooth: better/equal/worse =
   {texe_vs_smooth[0]}/{texe_vs_smooth[1]}/{texe_vs_smooth[2]}.

3. Does DA_v2 reduce absolute T_exe?

   Relative to static, T_exe better/equal/worse =
   {texe_vs_static[0]}/{texe_vs_static[1]}/{texe_vs_static[2]}.

4. Does DA_v2 reduce Delta_max?

   Relative to smooth on nontrivial cases, Delta_max better/equal/worse =
   {delta_vs_smooth[0]}/{delta_vs_smooth[1]}/{delta_vs_smooth[2]}.

5. Does DA_v2 reduce backlog duration?

   Relative to smooth on nontrivial cases, L_backlog better/equal/worse =
   {backlog_vs_smooth[0]}/{backlog_vs_smooth[1]}/{backlog_vs_smooth[2]}.

6. Does DA_v2 reduce corrected C_ref_star?

   Against smooth under T_ref_asap, C_ref_star better/equal/worse/missing =
   {cstar_better}/{cstar_equal}/{cstar_worse}/{cstar_missing}.

7. Does DA_v2 work on real workloads?

   On semi-real approximations, T_exe vs smooth better/equal/worse =
   {real_vs_smooth[0]}/{real_vs_smooth[1]}/{real_vs_smooth[2]}.

8. Is smooth already near-optimal under deterministic delivery?

   {optimal_note}

9. Should Paper 2 continue as a new scheduler paper, schedule trade-off
   framework paper, robustness/stochastic delivery paper, or stop/redesign?

   Current deterministic V2 signal says: **{recommendation}**. This is not a
   new-scheduler-paper signal. If the project continues, it should be reframed
   around schedule trade-offs, robustness, and limits of delivery-aware
   scheduling, with `sigma_smooth` treated as a strong baseline rather than a
   weak foil.
"""
    ensure_output_dirs()
    (RESULT_DIR_V2 / "PRELIMINARY_REPORT_V2.md").write_text(report)
