"""Tests for V4 framework metrics."""

from __future__ import annotations

from ftqc_delivery.metrics.buffer_threshold import find_buffer_reference_threshold
from ftqc_delivery.metrics.regime_validation import classify_delivery_regime
from ftqc_delivery.metrics.strategy_gain import backlog_area_gain, relative_gain, strategy_score
from ftqc_delivery.workloads import make_hamiltonian_simulation_synthetic, make_modular_arithmetic_block


def test_buffer_reference_threshold_uses_fixed_reference() -> None:
    def evaluator(buffer: int) -> tuple[int, int, int, int]:
        if buffer < 4:
            return 10, 12, 2, 2
        return 10, 10, 0, 0

    threshold = find_buffer_reference_threshold([0, 2, 4], 0.05, 10, evaluator)

    assert threshold.B_ref_star == 4
    assert threshold.achieved_ratio_to_T_ref == 1.0


def test_regime_classifier_detects_persistent_underprovisioning() -> None:
    decision = classify_delivery_regime(
        static_stall_cycles=5,
        static_delta_max=5,
        static_backlog_area=10,
        smooth_stall_cycles=4,
        smooth_delta_max=4,
        smooth_backlog_area=9,
        smooth_l_backlog=8,
        buffer=0,
        slack_ratio=0.8,
        fraction_zero_slack=0.1,
        supply_tightness=1.1,
        peak_demand_over_c=3.0,
        mean_demand_over_c=1.05,
        smooth_t_exe=20,
        static_t_exe=22,
    )

    assert decision.regime_label == "persistent_underprovisioning"
    assert decision.recommended_strategy == "increase_capacity"


def test_strategy_gain_helpers() -> None:
    assert relative_gain(100, 75) == 0.25
    assert backlog_area_gain(0, 10) == -10
    assert strategy_score(1.1, 20) == 1.3


def test_v4_synthetic_workloads_are_nonempty() -> None:
    modular = make_modular_arithmetic_block(n=6, repeats=2)
    hamiltonian = make_hamiltonian_simulation_synthetic(n=8, layers=2)

    assert modular.num_t_gates() > 0
    assert hamiltonian.num_t_gates() > 0
