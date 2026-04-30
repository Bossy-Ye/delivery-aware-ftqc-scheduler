"""Tests for V6 resource-aware objective helpers."""

from __future__ import annotations

from ftqc_delivery.metrics.resource_objective import (
    ResourceWeights,
    budget_feasible,
    pareto_dominated,
    resource_penalized_score,
)


def test_resource_penalized_score_charges_capacity_and_buffer() -> None:
    score = resource_penalized_score(
        t_exe=100,
        t_ref=100,
        backlog_area=50,
        delta_c=2,
        delta_b=4,
        weights=ResourceWeights(lambda_A=0.01, lambda_C=0.05, lambda_B=0.01),
    )

    assert score == 1.0 + 0.005 + 0.1 + 0.04


def test_budget_feasibility() -> None:
    assert budget_feasible(delta_c=1, delta_b=4, c_budget=1, b_budget=4)
    assert not budget_feasible(delta_c=2, delta_b=4, c_budget=1, b_budget=4)


def test_pareto_dominance() -> None:
    candidate = (1.2, 10.0, 1.0, 0.0)
    alternatives = [(1.1, 10.0, 1.0, 0.0), (1.3, 0.0, 0.0, 0.0)]

    assert pareto_dominated(candidate, alternatives)
