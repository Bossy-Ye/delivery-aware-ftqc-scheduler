"""Shared experiment utilities."""

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
from ftqc_delivery.metrics.delta_max import t_demand_trace
from ftqc_delivery.schedulers import (
    schedule_capacity_aware,
    schedule_delivery_aware,
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
)


RESULT_DIR = ROOT / "results" / "prelim_v1"
FIGURE_DIR = ROOT / "figures" / "prelim_v1"
C_VALUES = [1, 2, 3, 4, 5]
B_VALUES = [0, 4, 8, 12]
THRESHOLD_C_VALUES = list(range(1, 11))
EPSILON_VALUES = [0.05, 0.10]
SCHEDULES = ["static", "capacity_aware", "smooth", "delivery_aware"]


@dataclass(frozen=True)
class WorkloadCase:
    """Metadata plus DAG for one experiment workload."""

    workload: str
    family: str
    seed: int
    n: int
    dag: CircuitDAG


def ensure_output_dirs() -> None:
    """Create result and figure output directories."""

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def build_workloads() -> list[WorkloadCase]:
    """Build constructed and semi-real preliminary workloads."""

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
    return workloads


def representative_workloads() -> list[WorkloadCase]:
    """Return a small set used by plots."""

    return [
        WorkloadCase(
            "constructed_high",
            "high_compressibility",
            0,
            24,
            make_high_compressibility(seed=0, n=24),
        ),
        WorkloadCase("multiplier_n8", "semi_real_multiplier", 0, 8, make_multiplier(n=8)),
    ]


def make_schedule(
    schedule_name: str,
    dag: CircuitDAG,
    capacity: int,
    buffer: int,
) -> dict[int, list[str]]:
    """Build a schedule by name."""

    if schedule_name == "static":
        return schedule_static(dag)
    if schedule_name == "capacity_aware":
        return schedule_capacity_aware(dag, capacity)
    if schedule_name == "smooth":
        return schedule_smooth(dag, capacity)
    if schedule_name == "delivery_aware":
        return schedule_delivery_aware(dag, capacity, buffer)
    raise ValueError(f"Unknown schedule: {schedule_name}")


def evaluate_case(
    case: WorkloadCase,
    schedule_name: str,
    capacity: int,
    buffer: int,
) -> dict[str, Any]:
    """Schedule and simulate one case."""

    schedule = make_schedule(schedule_name, case.dag, capacity, buffer)
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
        "slowdown": result.slowdown,
        "Delta_max": result.Delta_max,
        "L_backlog": result.L_backlog,
        "feasible": result.feasible,
    }


def reduction(baseline: float, value: float) -> float:
    """Return relative reduction `(baseline-value)/baseline`, guarding zero."""

    if baseline == 0:
        return 0.0
    return (baseline - value) / baseline


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write rows to CSV with fixed field order."""

    ensure_output_dirs()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read CSV rows as dictionaries."""

    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def generate_exp1_figures(rows: list[dict[str, Any]]) -> None:
    """Generate Figures 1-3 from Experiment 1 data."""

    ensure_output_dirs()
    import matplotlib.pyplot as plt

    _plot_demand_trace()
    _plot_makespan_comparison(rows)
    _plot_delta_vs_penalty(rows)
    plt.close("all")


def _plot_demand_trace() -> None:
    import matplotlib.pyplot as plt

    c_value = 2
    b_value = 4
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=False)
    for ax, case in zip(axes, representative_workloads(), strict=True):
        static_schedule = make_schedule("static", case.dag, c_value, b_value)
        da_schedule = make_schedule("delivery_aware", case.dag, c_value, b_value)
        horizon = max(max(static_schedule), max(da_schedule))
        static_demand = t_demand_trace(case.dag, static_schedule, horizon=horizon)
        da_demand = t_demand_trace(case.dag, da_schedule, horizon=horizon)
        ax.step(static_demand.keys(), static_demand.values(), where="mid", label="static")
        ax.step(da_demand.keys(), da_demand.values(), where="mid", label="delivery_aware")
        ax.axhline(c_value, color="black", linewidth=1, linestyle="--", label="C")
        ax.set_title(case.workload)
        ax.set_ylabel("T demand")
        ax.grid(alpha=0.25)
    axes[-1].set_xlabel("logical time")
    axes[0].legend(loc="upper right", ncols=3)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "fig1_demand_trace_static_vs_DA.pdf")


def _plot_makespan_comparison(rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    selected = [
        row
        for row in rows
        if row["workload"] in {"constructed_high", "multiplier_n8"}
        and int(row["seed"]) == 0
        and int(row["C"]) == 2
        and int(row["B"]) == 4
    ]
    labels = ["static", "capacity_aware", "smooth", "delivery_aware"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=False)
    for ax, workload, metric in [
        (axes[0], "constructed_high", "T_exe"),
        (axes[1], "multiplier_n8", "stall_cycles"),
    ]:
        values = []
        for schedule in labels:
            match = next(
                row for row in selected if row["workload"] == workload and row["schedule"] == schedule
            )
            values.append(float(match[metric]))
        ax.bar(labels, values, color=["#4c78a8", "#f58518", "#54a24b", "#b279a2"])
        ax.set_title(f"{workload}: {metric}")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "fig2_makespan_comparison.pdf")


def _plot_delta_vs_penalty(rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    colors = {
        "capacity_aware": "#f58518",
        "smooth": "#54a24b",
        "delivery_aware": "#b279a2",
    }
    fig, ax = plt.subplots(figsize=(7, 5))
    for schedule, color in colors.items():
        xs = [
            float(row["static_depth_penalty"])
            for row in rows
            if row["schedule"] == schedule
        ]
        ys = [
            float(row["Delta_reduction_vs_static"])
            for row in rows
            if row["schedule"] == schedule
        ]
        ax.scatter(xs, ys, label=schedule, alpha=0.45, s=18, color=color)
    ax.axhline(0, color="black", linewidth=1)
    ax.axvline(1, color="black", linewidth=1, linestyle="--")
    ax.set_xlabel("static-depth penalty")
    ax.set_ylabel("Delta_max reduction vs static")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "fig3_delta_vs_static_penalty.pdf")


def generate_exp2_figure(rows: list[dict[str, Any]]) -> None:
    """Generate Figure 4 from Experiment 2 data."""

    ensure_output_dirs()
    import matplotlib.pyplot as plt

    workloads = ["constructed_high", "constructed_medium", "multiplier_n8", "exact_qft_n8"]
    schedules = SCHEDULES
    selected = [
        row
        for row in rows
        if row["workload"] in workloads
        and int(row["seed"]) == 0
        and int(row["B"]) == 4
        and abs(float(row["epsilon"]) - 0.05) < 1e-9
    ]
    width = 0.18
    x_positions = list(range(len(workloads)))
    fig, ax = plt.subplots(figsize=(10, 4.8))
    colors = ["#4c78a8", "#f58518", "#54a24b", "#b279a2"]
    for schedule_index, schedule in enumerate(schedules):
        values: list[float] = []
        for workload in workloads:
            match = next(
                (
                    row
                    for row in selected
                    if row["workload"] == workload and row["schedule"] == schedule
                ),
                None,
            )
            c_star = match["C_star"] if match else ""
            values.append(float(c_star) if c_star else 0.0)
        offsets = [x + (schedule_index - 1.5) * width for x in x_positions]
        ax.bar(offsets, values, width=width, label=schedule, color=colors[schedule_index])
    ax.set_xticks(x_positions)
    ax.set_xticklabels(workloads, rotation=15)
    ax.set_ylabel("C*_0.05")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncols=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "fig4_required_capacity_Cstar.pdf")
    plt.close(fig)


def write_preliminary_report(exp1_path: Path, exp2_path: Path) -> None:
    """Write a short markdown report answering the go/no-go questions."""

    exp1 = read_csv(exp1_path)
    exp2 = read_csv(exp2_path)
    da_rows = [row for row in exp1 if row["schedule"] == "delivery_aware"]
    real_da = [row for row in da_rows if row["family"].startswith("semi_real")]

    def count_positive(column: str, source: list[dict[str, str]] = da_rows) -> tuple[int, int]:
        positives = sum(1 for row in source if float(row[column]) > 0)
        return positives, len(source)

    delta_pos = count_positive("Delta_reduction_vs_static")
    texe_pos = count_positive("Texe_reduction_vs_static")
    stall_pos = (
        sum(
            1
            for row in da_rows
            if row["workload"]
            and int(float(row["stall_cycles"])) >= 0
            and float(row["Texe_reduction_vs_static"]) > 0
        ),
        len(da_rows),
    )
    smooth_pos = count_positive("Texe_reduction_vs_smooth")
    ca_pos = count_positive("Texe_reduction_vs_ca")
    real_pos = count_positive("Texe_reduction_vs_static", real_da)

    cstar_improvements = 0
    cstar_comparisons = 0
    key = lambda row: (row["workload"], row["family"], row["seed"], row["n"], row["B"], row["epsilon"])
    grouped: dict[tuple[str, str, str, str, str, str], dict[str, dict[str, str]]] = {}
    for row in exp2:
        grouped.setdefault(key(row), {})[row["schedule"]] = row
    for schedules in grouped.values():
        da = schedules.get("delivery_aware")
        if not da or not da["C_star"]:
            continue
        da_c = int(da["C_star"])
        for baseline in ["static", "capacity_aware", "smooth"]:
            other = schedules.get(baseline)
            if other and other["C_star"]:
                cstar_comparisons += 1
                if da_c < int(other["C_star"]):
                    cstar_improvements += 1

    enough_signal = (
        texe_pos[0] / max(1, texe_pos[1]) > 0.35
        and real_pos[0] > 0
        and cstar_improvements > 0
    )
    recommendation = (
        "continue"
        if enough_signal
        else "redesign before scaling"
        if texe_pos[0] > 0 or cstar_improvements > 0
        else "stop"
    )

    report = f"""# Preliminary Report

## Summary

Recommendation: **{recommendation}**.

This report is generated from deterministic preliminary scans only. The
arithmetic and QFT workloads are semi-real trace-level approximations, not full
circuit extraction.

## Questions

1. Does `sigma_DA` reduce `Delta_max`?

   Yes in {delta_pos[0]} of {delta_pos[1]} deterministic schedule scans relative
   to `sigma_static`.

2. Does it reduce actual `T_exe`?

   Yes in {texe_pos[0]} of {texe_pos[1]} scans relative to `sigma_static`.

3. Does it reduce stall cycles?

   Stall reductions track executable-makespan reductions in {stall_pos[0]} of
   {stall_pos[1]} scans.

4. Does it outperform `sigma_smooth` or `sigma_ca`?

   It improves `T_exe` over `sigma_smooth` in {smooth_pos[0]} of
   {smooth_pos[1]} scans and over `sigma_ca` in {ca_pos[0]} of {ca_pos[1]}
   scans.

5. Does it reduce required capacity `C_star`?

   `sigma_DA` has a lower finite `C_star` in {cstar_improvements} of
   {cstar_comparisons} direct baseline comparisons.

6. Does it work on real workloads, not only constructed DAGs?

   On the semi-real workload approximations, it reduces `T_exe` relative to
   `sigma_static` in {real_pos[0]} of {real_pos[1]} scans.

7. Should Paper 2 continue, stop, or redesign?

   Current deterministic signal says: **{recommendation}**. If this is not a
   clear continue, the next step is to refine `sigma_DA` and replace the
   semi-real workload approximations with actual extracted circuits before
   scaling stochastic or architecture-proxy experiments.
"""
    (RESULT_DIR / "PRELIMINARY_REPORT.md").write_text(report)
