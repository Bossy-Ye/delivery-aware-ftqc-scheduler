"""Tests for demand and Delta_max metrics."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.metrics.delta_max import cumulative_demand, delta_max, t_demand_trace


def test_t_demand_and_cumulative_demand() -> None:
    dag = CircuitDAG("metric_test")
    dag.add_node("a", "T")
    dag.add_node("b", "Tdg")
    dag.add_node("c", "Clifford")
    schedule = {1: ["a", "c"], 2: ["b"]}

    assert t_demand_trace(dag, schedule) == {1: 1, 2: 1}
    assert cumulative_demand(dag, schedule) == {1: 1, 2: 2}


def test_delta_max_uses_one_indexed_time() -> None:
    dag = CircuitDAG("delta_test")
    dag.add_node("a", "T")
    dag.add_node("b", "T")
    schedule = {1: ["a", "b"]}

    assert delta_max(dag, schedule, capacity=1) == 1
