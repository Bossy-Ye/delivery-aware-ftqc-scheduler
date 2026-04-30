"""Tests for deterministic delivery simulation."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.simulator.deterministic import simulate_deterministic


def test_deterministic_simulator_inserts_stalls() -> None:
    dag = CircuitDAG("sim_test")
    dag.add_node("a", "T")
    dag.add_node("b", "T")
    schedule = {1: ["a", "b"]}

    result = simulate_deterministic(dag, schedule, capacity=1, buffer=0)

    assert result.T_static == 1
    assert result.T_exe == 2
    assert result.stall_cycles == 1
    assert result.slowdown == 2.0
    assert result.Delta_max == 1
    assert result.L_backlog == 1


def test_deterministic_simulator_uses_initial_buffer() -> None:
    dag = CircuitDAG("buffer_test")
    dag.add_node("a", "T")
    dag.add_node("b", "T")
    schedule = {1: ["a", "b"]}

    result = simulate_deterministic(dag, schedule, capacity=1, buffer=1)

    assert result.T_exe == 1
    assert result.stall_cycles == 0
    assert result.L_backlog == 0
