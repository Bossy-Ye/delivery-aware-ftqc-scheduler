"""Shared plumbing for the stateful-oracle go/no-go study."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Iterable, Sequence

from ftqc_delivery.mrc.resources import CCZ, T, Machine, coupled_machine
from ftqc_delivery.utils.io import read_csv_rows, write_csv_rows

ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "results" / "marsq_go_nogo"

#: Policies compared, in the order the contract names them.
P0, P1, P2 = "fixed_t", "fixed_ccz", "uniform_oracle"
SIMPLE_POOL = (
    "uniform_min_teq",
    "min_weighted_count",
    "two_term_descent",
    "local_sim_greedy",
    "share_aware_greedy",
    "proportional_split",
)
ALL_POLICIES = (P0, P1, P2) + SIMPLE_POOL

#: Deterministic seed for every randomised component.
SEED = 20260920


def machine_grid() -> list[tuple[str, Machine]]:
    """Return the frozen machine configurations, labelled.

    Model A is independent banks, B shares one raw stream between the T and
    CCZ distillers, and C adds the catalysed CCZ-to-2T conversion. Area is
    held fixed within a size so no model is given more hardware. The 3200-tile
    entry is the weakly constrained control.
    """

    grid: list[tuple[str, Machine]] = []
    for model in ("A", "B", "C"):
        for share in (0.25, 0.5, 0.75):
            grid.append((f"{model}_400_{share}", coupled_machine(model, 400, share, seed=SEED)))
    for model in ("A", "B", "C"):
        grid.append((f"{model}_800_0.5", coupled_machine(model, 800, 0.5, seed=SEED)))
    for model in ("B", "C"):
        grid.append(
            (f"{model}_400_0.5_scarce", coupled_machine(model, 400, 0.5, raw_scale=0.5, seed=SEED))
        )
    grid.append(("A_3200_0.5_abundant", coupled_machine("A", 3200, 0.5, seed=SEED)))
    return grid


def machine_meta(label: str, machine: Machine) -> dict[str, Any]:
    """Return the reproducible description of one machine."""

    parts = label.split("_")
    return {
        "machine": label,
        "model": parts[0],
        "tiles": parts[1],
        "ccz_share": parts[2],
        "regime": "abundant" if "abundant" in label else ("scarce" if "scarce" in label else "standard"),
        "t_rate": round(machine.rate(T), 4),
        "ccz_rate": round(machine.rate(CCZ), 4),
        "factory_tiles": machine.factory_tiles,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    write_csv_rows(path, rows, list(fieldnames))


def read_csv(path: Path) -> list[dict[str, str]]:
    return read_csv_rows(path)


def ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else float("nan")


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def summarise(values: Iterable[float]) -> dict[str, float]:
    data = [v for v in values if v == v]
    if not data:
        return {k: float("nan") for k in ("n", "mean", "median", "p25", "p75", "p90", "max")} | {"n": 0}
    return {
        "n": len(data),
        "mean": round(statistics.fmean(data), 4),
        "median": round(statistics.median(data), 4),
        "p25": round(percentile(data, 0.25), 4),
        "p75": round(percentile(data, 0.75), 4),
        "p90": round(percentile(data, 0.90), 4),
        "max": round(max(data), 4),
    }


def counts_above(values: Iterable[float]) -> dict[str, int]:
    data = list(values)
    return {
        "gt2pct": sum(1 for v in data if v > 0.02),
        "gt5pct": sum(1 for v in data if v > 0.05),
        "gt10pct": sum(1 for v in data if v > 0.10),
        "gt20pct": sum(1 for v in data if v > 0.20),
    }
