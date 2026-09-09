"""Shared plumbing for the resource-aware compilation go/no-go experiments."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Iterable, Sequence

from ftqc_delivery.rac.analysis import (
    ancilla_width,
    demand_burstiness,
    logical_depth,
    peak_asap_demand,
    t_count,
    t_depth,
)
from ftqc_delivery.rac.programs import decision_sites, pilot_programs
from ftqc_delivery.rac.variants import ProgramSpace
from ftqc_delivery.utils.io import read_csv_rows, write_csv_rows


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "results" / "rac_pilot"
FIGURE_DIR = ROOT / "figures" / "rac_pilot"

POLICY_COLORS = {
    "min_t_count": "#4c78a8",
    "min_t_depth": "#e45756",
    "best_static": "#7f7f7f",
    "legacy_smooth": "#b279a2",
    "local_resource_greedy": "#f58518",
    "share_aware_greedy": "#72b7b2",
    "best_uniform": "#9d755d",
    "resource_aware": "#54a24b",
    "reference": "#54595d",
}

POLICY_LABELS = {
    "min_t_count": "A: minimise T-count",
    "min_t_depth": "B: minimise T-depth",
    "best_static": "B+: best of the two static metrics (timed)",
    "legacy_smooth": "C: prior study (T-depth + smoothed static schedule)",
    "local_resource_greedy": "D: greedy resource-aware (per site)",
    "share_aware_greedy": "D+: greedy, aware of its share of supply",
    "best_uniform": "D++: simulate every library implementation",
    "resource_aware": "Ours: supply-constrained selection",
    "reference": "E: reference / exhaustive optimum",
}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    """Write rows to ``path`` with a fixed column order."""

    write_csv_rows(path, rows, list(fieldnames))


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read rows written by :func:`write_csv`."""

    return read_csv_rows(path)


def programs() -> list[ProgramSpace]:
    """Return the pilot program set."""

    return pilot_programs()


def program_meta(program: ProgramSpace) -> dict[str, str]:
    """Return the metadata attached to a program."""

    return dict(program.meta)


def site_count(program: ProgramSpace) -> int:
    """Return the number of sites that actually offer a choice."""

    return len(decision_sites(program))


def assignment_space(program: ProgramSpace) -> int:
    """Return the number of distinct assignments over real decision sites."""

    total = 1
    for site in decision_sites(program):
        total *= len(site.variants)
    return total


def circuit_metrics(dag, clifford_weight: int = 1) -> dict[str, float]:
    """Return the static metrics of one instantiated circuit."""

    return {
        "t_count": t_count(dag),
        "t_depth": t_depth(dag),
        "logical_depth": logical_depth(dag, clifford_weight),
        "peak_demand": peak_asap_demand(dag, clifford_weight),
        "burstiness": round(demand_burstiness(dag, clifford_weight), 4),
        "ancilla_width": ancilla_width(dag, clifford_weight),
    }


def ratio(numerator: float, denominator: float) -> float:
    """Return a ratio, guarding against a zero denominator."""

    return float(numerator) / float(denominator) if denominator else float("nan")


def percentile(values: Sequence[float], fraction: float) -> float:
    """Return a nearest-rank percentile of ``values``."""

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


def assignment_token(assignment: dict[str, str]) -> str:
    """Return a stable, compact string form of an assignment."""

    return ";".join(f"{key}={value}" for key, value in sorted(assignment.items()))


def variant_profile(assignment: dict[str, str]) -> str:
    """Return the multiset of chosen variant names, for readable tables."""

    counts: dict[str, int] = {}
    for value in assignment.values():
        if value == "barrier":
            continue
        counts[value] = counts.get(value, 0) + 1
    return ",".join(f"{name}x{count}" for name, count in sorted(counts.items()))


def heterogeneous(assignment: dict[str, str]) -> bool:
    """Return whether an assignment gives different variants to sibling sites."""

    names = {value for value in assignment.values() if value != "barrier"}
    return len(names) > 1
