"""Shared plumbing for the T/CCZ implementation-selection study."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Iterable, Sequence

from ftqc_delivery.mrc.execution import critical_path, resource_counts
from ftqc_delivery.mrc.kernels import assignment_space, decision_sites, pilot_kernels
from ftqc_delivery.mrc.policies import t_equivalents
from ftqc_delivery.mrc.resources import CCZ, T, Machine
from ftqc_delivery.rac.variants import ProgramSpace
from ftqc_delivery.utils.io import read_csv_rows, write_csv_rows


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "results" / "mrc_pilot"
FIGURE_DIR = ROOT / "figures" / "mrc_pilot"

POLICY_LABELS = {
    "uniform_min_teq": "uniform, fewest T-equivalents (static)",
    "min_weighted_count": "per-site weighted resource count (static)",
    "uniform_oracle": "best uniform implementation (simulated)",
    "two_term_descent": "max(critical path, demand/rate) search",
    "local_sim_greedy": "per-site local simulation",
    "share_aware_greedy": "per-site share-aware greedy",
    "proportional_split": "split sites in proportion to bank rates",
    "sim_descent": "global heterogeneous search (simulated)",
    "global_oracle": "global optimum",
}

POLICY_COLORS = {
    "uniform_min_teq": "#4c78a8",
    "min_weighted_count": "#9d755d",
    "uniform_oracle": "#e45756",
    "two_term_descent": "#b279a2",
    "local_sim_greedy": "#f58518",
    "share_aware_greedy": "#72b7b2",
    "proportional_split": "#ff9da6",
    "sim_descent": "#54a24b",
    "global_oracle": "#54595d",
}

#: Baselines that do not get to mix implementations within a family.
SIMPLE_BASELINES = (
    "uniform_min_teq",
    "min_weighted_count",
    "uniform_oracle",
    "two_term_descent",
    "local_sim_greedy",
    "share_aware_greedy",
    "proportional_split",
)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    """Write rows with a fixed column order."""

    write_csv_rows(path, rows, list(fieldnames))


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read rows written by :func:`write_csv`."""

    return read_csv_rows(path)


def kernels() -> list[ProgramSpace]:
    """Return the pilot kernel set."""

    return pilot_kernels()


def kernel_meta(program: ProgramSpace) -> dict[str, str]:
    """Return the metadata attached to a kernel."""

    return dict(program.meta)


def ratio(numerator: float, denominator: float) -> float:
    """Return a ratio, guarding against a zero denominator."""

    return float(numerator) / float(denominator) if denominator else float("nan")


def percentile(values: Sequence[float], fraction: float) -> float:
    """Return a nearest-rank percentile."""

    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def summarize(values: Iterable[float]) -> dict[str, float]:
    """Return the distribution summary used throughout the study."""

    data = [value for value in values if value == value]
    if not data:
        return {"n": 0, "mean": float("nan"), "median": float("nan"),
                "p90": float("nan"), "p95": float("nan"), "max": float("nan")}
    return {
        "n": len(data),
        "mean": round(statistics.fmean(data), 4),
        "median": round(statistics.median(data), 4),
        "p90": round(percentile(data, 0.90), 4),
        "p95": round(percentile(data, 0.95), 4),
        "max": round(max(data), 4),
    }


def capacity_of(machine: Machine) -> float:
    """Return the machine's total capacity in T-equivalent states per cycle."""

    return machine.rate(T) + 2.0 * machine.rate(CCZ)


def supply_pressure(program: ProgramSpace, assignment, machine: Machine) -> float:
    """Return demand over what the machine can deliver along the critical path.

    Values above 1 mean the program is supply-bound: the factories, not the
    dependency structure, decide the makespan. Below 1 the choice of
    implementation cannot matter much however the resources are split.
    """

    dag = program.instantiate(assignment)
    demand = t_equivalents(resource_counts(dag))
    capacity = capacity_of(machine)
    path = critical_path(dag)
    if capacity <= 0 or path <= 0:
        return float("inf")
    return (demand / capacity) / path


def data_tiles(program: ProgramSpace) -> int:
    """Return a coarse data-register size, used to price the space overhead."""

    meta = kernel_meta(program)
    try:
        return max(8, 2 * int(meta.get("width", "16")))
    except ValueError:
        return 32


def sites_and_space(program: ProgramSpace) -> tuple[int, int]:
    """Return the number of real decision sites and the assignment space size."""

    return len(decision_sites(program)), assignment_space(program)
