"""Tests for V3 analysis metrics."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.metrics.backlog_shape import backlog_shape_features
from ftqc_delivery.metrics.demand_shape import demand_shape_features
from ftqc_delivery.metrics.robustness import simulate_stochastic_robustness_trial
from ftqc_delivery.metrics.structural_features import structural_features
from ftqc_delivery.schedulers import robust_smooth_target_capacity
from ftqc_delivery.workloads import make_high_compressibility


def test_backlog_shape_area_and_intervals() -> None:
    dag = CircuitDAG("shape")
    dag.add_node("a", "T")
    dag.add_node("b", "T")
    dag.add_node("c", "T")
    schedule = {1: ["a", "b"], 2: ["c"]}

    shape = backlog_shape_features(dag, schedule, capacity=1, buffer=0)

    assert shape.BacklogArea == 2
    assert shape.L_backlog == 2
    assert shape.num_backlog_intervals == 1
    assert shape.longest_backlog_interval == 2


def test_demand_shape_detects_peak() -> None:
    dag = CircuitDAG("demand")
    dag.add_node("a", "T")
    dag.add_node("b", "T")
    dag.add_node("c", "Clifford")
    schedule = {1: ["a", "b"], 2: ["c"]}

    shape = demand_shape_features(dag, schedule)

    assert shape.D_peak == 2
    assert shape.D_peak_to_mean == 2.0
    assert shape.num_demand_peaks == 1


def test_structural_features_have_slack_for_high_case() -> None:
    dag = make_high_compressibility(seed=0, n=8)
    features = structural_features(dag)

    assert features.T_count > 0
    assert features.critical_path_length > 0
    assert features.ready_T_width_peak > 0


def test_robust_smooth_target_capacity() -> None:
    assert robust_smooth_target_capacity(capacity=5, p_acc=0.9, rho=0.9) == 4
    assert robust_smooth_target_capacity(capacity=1, p_acc=0.5, rho=0.9) == 1


def test_stochastic_robustness_trial_with_perfect_delivery() -> None:
    dag = CircuitDAG("stoch")
    dag.add_node("a", "T")
    dag.add_node("b", "T")
    schedule = {1: ["a", "b"]}

    trial = simulate_stochastic_robustness_trial(
        dag,
        schedule,
        capacity=1,
        buffer=0,
        p_acc=1.0,
        seed=0,
    )

    assert trial.T_exe == 2
    assert trial.stall_cycles == 1
    assert trial.BacklogArea == 1
