"""Tests for backlog summary metrics."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.metrics.backlog import backlog_active_length, max_backlog, mean_backlog


def test_backlog_summaries() -> None:
    dag = CircuitDAG("backlog_test")
    dag.add_node("a", "T")
    dag.add_node("b", "T")
    dag.add_node("c", "T")
    schedule = {1: ["a", "b"], 2: ["c"]}

    assert backlog_active_length(dag, schedule, capacity=1, buffer=0) == 2
    assert max_backlog(dag, schedule, capacity=1, buffer=0) == 1
    assert mean_backlog(dag, schedule, capacity=1, buffer=0) == 1.0
