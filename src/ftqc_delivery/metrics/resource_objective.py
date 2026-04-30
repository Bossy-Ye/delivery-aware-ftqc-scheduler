"""Resource-aware strategy objective utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceWeights:
    """Weights for resource-aware strategy scoring."""

    lambda_A: float = 0.01
    lambda_C: float = 0.05
    lambda_B: float = 0.01


def normalized_backlog_area(backlog_area: float, t_ref: float) -> float:
    """Normalize backlog area by the fixed reference runtime."""

    if t_ref <= 0:
        raise ValueError("t_ref must be positive")
    return backlog_area / max(1.0, t_ref)


def resource_penalized_score(
    *,
    t_exe: float,
    t_ref: float,
    backlog_area: float,
    delta_c: float,
    delta_b: float,
    weights: ResourceWeights = ResourceWeights(),
) -> float:
    """Compute runtime + backlog + resource expansion score."""

    if t_ref <= 0:
        raise ValueError("t_ref must be positive")
    return (
        t_exe / t_ref
        + weights.lambda_A * normalized_backlog_area(backlog_area, t_ref)
        + weights.lambda_C * max(0.0, delta_c)
        + weights.lambda_B * max(0.0, delta_b)
    )


def budget_feasible(delta_c: float, delta_b: float, c_budget: int, b_budget: int) -> bool:
    """Return whether a strategy is feasible under resource budgets."""

    return delta_c <= c_budget and delta_b <= b_budget


def pareto_dominated(
    candidate: tuple[float, float, float, float],
    alternatives: list[tuple[float, float, float, float]],
) -> bool:
    """Return whether candidate is Pareto dominated.

    Metric order is `(T_exe/T_ref, BacklogArea, DeltaC, DeltaB)` and lower is
    better for every metric.
    """

    for other in alternatives:
        no_worse = all(other_value <= candidate_value for other_value, candidate_value in zip(other, candidate, strict=True))
        strictly_better = any(other_value < candidate_value for other_value, candidate_value in zip(other, candidate, strict=True))
        if no_worse and strictly_better:
            return True
    return False


def near_pareto(
    candidate: tuple[float, float, float, float],
    pareto_points: list[tuple[float, float, float, float]],
    runtime_tol: float = 0.01,
    backlog_tol: float = 0.05,
) -> bool:
    """Return whether candidate is close to any Pareto point in runtime/backlog."""

    runtime, backlog, _, _ = candidate
    for point in pareto_points:
        p_runtime, p_backlog, _, _ = point
        runtime_ok = runtime <= p_runtime * (1.0 + runtime_tol)
        backlog_ok = backlog <= p_backlog * (1.0 + backlog_tol) if p_backlog > 0 else backlog <= 0
        if runtime_ok and backlog_ok:
            return True
    return False
