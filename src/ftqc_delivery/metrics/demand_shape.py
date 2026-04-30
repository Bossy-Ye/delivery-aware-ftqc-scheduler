"""Demand-trace shape metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import log2, sqrt

from ftqc_delivery.dag.graph import CircuitDAG

from .delta_max import t_demand_trace


@dataclass(frozen=True)
class DemandShape:
    """Summary statistics for T-demand burstiness."""

    D_peak: int
    D_mean: float
    D_std: float
    D_cv: float
    D_peak_to_mean: float
    num_demand_peaks: int
    demand_entropy: float
    demand_gini: float
    demand_burstiness_index: float


def _gini(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    total = sum(sorted_values)
    if total == 0:
        return 0.0
    n = len(sorted_values)
    weighted_sum = sum((index + 1) * value for index, value in enumerate(sorted_values))
    return (2 * weighted_sum) / (n * total) - (n + 1) / n


def demand_shape_features(
    dag: CircuitDAG,
    schedule: dict[int, list[str]],
) -> DemandShape:
    """Compute demand-shape metrics from D_sigma(t)."""

    demand = t_demand_trace(dag, schedule)
    values = list(demand.values())
    if not values:
        return DemandShape(0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0)
    peak = max(values)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    std = sqrt(variance)
    cv = std / mean if mean else 0.0
    peak_to_mean = peak / mean if mean else 0.0
    demand_peaks = sum(1 for value in values if peak > 0 and value == peak)
    total = sum(values)
    entropy = 0.0
    if total > 0:
        for value in values:
            if value > 0:
                p = value / total
                entropy -= p * log2(p)
    burstiness = (peak - mean) / peak if peak else 0.0
    return DemandShape(
        D_peak=peak,
        D_mean=mean,
        D_std=std,
        D_cv=cv,
        D_peak_to_mean=peak_to_mean,
        num_demand_peaks=demand_peaks,
        demand_entropy=entropy,
        demand_gini=_gini([float(value) for value in values]),
        demand_burstiness_index=burstiness,
    )


def demand_shape_dict(dag: CircuitDAG, schedule: dict[int, list[str]]) -> dict[str, float]:
    """Return demand-shape metrics as a dictionary."""

    return asdict(demand_shape_features(dag, schedule))
