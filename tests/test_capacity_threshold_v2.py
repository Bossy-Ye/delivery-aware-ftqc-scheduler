"""Tests for fixed-reference capacity threshold."""

from __future__ import annotations

from ftqc_delivery.metrics.capacity_threshold import find_reference_capacity_threshold


def test_reference_capacity_threshold_uses_fixed_denominator() -> None:
    def evaluator(capacity: int) -> tuple[int, int, int, int]:
        if capacity == 1:
            return 20, 20, 0, 0
        return 10, 10, 0, 0

    old_style_would_accept_capacity_one = 20 / 20 <= 1.05
    threshold = find_reference_capacity_threshold(
        capacities=[1, 2],
        epsilon=0.05,
        t_ref=10,
        evaluator=evaluator,
    )

    assert old_style_would_accept_capacity_one
    assert threshold.C_ref_star == 2
    assert threshold.achieved_ratio_to_T_ref == 1.0
