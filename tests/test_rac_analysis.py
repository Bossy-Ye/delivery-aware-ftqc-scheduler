"""Tests for the static metrics a conventional compiler optimises."""

from __future__ import annotations

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.rac.analysis import (
    ancilla_width,
    asap_t_demand,
    demand_burstiness,
    logical_depth,
    peak_asap_demand,
    t_count,
    t_depth,
    t_tails,
)


def chain(length: int) -> CircuitDAG:
    dag = CircuitDAG("chain")
    previous = None
    for index in range(length):
        node_id = f"t{index}"
        dag.add_node(node_id, "T")
        if previous is not None:
            dag.add_edge(previous, node_id)
        previous = node_id
    return dag


def fan(width: int) -> CircuitDAG:
    dag = CircuitDAG("fan")
    dag.add_node("src", "Clifford")
    for index in range(width):
        dag.add_node(f"t{index}", "T")
        dag.add_edge("src", f"t{index}")
    return dag


def test_t_depth_counts_the_longest_t_chain():
    assert t_depth(chain(5)) == 5
    assert t_depth(fan(5)) == 1


def test_t_count_is_independent_of_shape():
    assert t_count(chain(5)) == t_count(fan(5)) == 5


def test_clifford_weight_zero_removes_clifford_cost():
    assert logical_depth(fan(5), clifford_weight=0) == 1
    assert logical_depth(fan(5), clifford_weight=1) == 2


def test_demand_profile_reflects_parallelism():
    assert peak_asap_demand(fan(5)) == 5
    assert peak_asap_demand(chain(5)) == 1
    assert asap_t_demand(chain(3)) == {1: 1, 2: 1, 3: 1}


def test_burstiness_is_larger_for_a_fan_than_a_chain():
    assert demand_burstiness(fan(8)) > demand_burstiness(chain(8))


def test_t_tails_measures_remaining_t_work():
    tails = t_tails(chain(4))
    assert tails["t0"] == 3
    assert tails["t3"] == 0


def test_ancilla_width_tracks_concurrency():
    assert ancilla_width(fan(6)) >= 6
    assert ancilla_width(chain(6)) == 1
