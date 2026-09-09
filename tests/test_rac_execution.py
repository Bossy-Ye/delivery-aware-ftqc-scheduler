"""Tests for constrained execution against a magic-state supply process."""

from __future__ import annotations

import pytest

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.rac.analysis import t_depth
from ftqc_delivery.rac.execution import execute, execute_fixed_schedule
from ftqc_delivery.rac.supply import SupplyModel, saturating_supply
from ftqc_delivery.schedulers.smooth import schedule_smooth


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


@pytest.mark.parametrize("dag", [chain(6), fan(6), chain(1)])
def test_unconstrained_execution_equals_t_depth_when_cliffords_are_free(dag):
    """T-depth is exactly the execution time when nothing constrains the machine."""

    supply = saturating_supply(dag.num_t_gates())
    assert execute(dag, supply, clifford_weight=0).makespan == t_depth(dag)


def test_a_flat_rate_erases_the_difference_between_deep_and_wide():
    """A T-depth-1 circuit and a T-depth-5 circuit take the same time at rate 1."""

    supply = SupplyModel(num_factories=1, production_latency=1)
    assert execute(fan(5), supply, clifford_weight=0).makespan == 5
    assert execute(chain(5), supply, clifford_weight=0).makespan == 5


def test_every_t_gate_is_executed_exactly_once():
    supply = SupplyModel(num_factories=1, production_latency=3, buffer_capacity=2)
    trace = execute(fan(7), supply)
    assert sum(trace.demand) == 7


def test_a_full_buffer_loses_production():
    dag = chain(3)
    supply = SupplyModel(num_factories=4, production_latency=1, buffer_capacity=2)
    trace = execute(dag, supply)
    assert trace.overflow > 0


def test_an_unbounded_buffer_never_loses_production():
    dag = chain(3)
    supply = SupplyModel(num_factories=4, production_latency=1, buffer_capacity=-1)
    assert execute(dag, supply).overflow == 0


def test_slower_supply_never_makes_execution_faster():
    dag = fan(12)
    fast = execute(dag, SupplyModel(num_factories=4, production_latency=2)).makespan
    slow = execute(dag, SupplyModel(num_factories=1, production_latency=2)).makespan
    assert slow >= fast


def test_stalls_are_recorded_when_states_run_out():
    trace = execute(fan(6), SupplyModel(num_factories=1, production_latency=4))
    assert trace.supply_stall_cycles > 0


def test_priority_choice_does_not_change_the_work_done():
    dag = fan(9)
    supply = SupplyModel(num_factories=2, production_latency=3, buffer_capacity=4)
    for priority in ("topological", "critical_path", "t_critical"):
        assert sum(execute(dag, supply, priority=priority).demand) == 9


def test_unknown_priority_is_rejected():
    with pytest.raises(ValueError):
        execute(chain(2), saturating_supply(2), priority="nonsense")


def test_fixed_schedule_execution_never_beats_dynamic_scheduling():
    dag = fan(10)
    supply = SupplyModel(num_factories=2, production_latency=4, buffer_capacity=8)
    schedule = schedule_smooth(dag, capacity=1)
    static = execute_fixed_schedule(dag, schedule, supply).makespan
    dynamic = execute(dag, supply).makespan
    assert static >= dynamic


def test_fixed_schedule_drains_a_layer_wider_than_the_buffer():
    """A static layer asking for more states than fit in the buffer still finishes."""

    dag = fan(20)
    supply = SupplyModel(num_factories=1, production_latency=2, buffer_capacity=2)
    schedule = {1: ["src"], 2: [f"t{index}" for index in range(20)]}
    trace = execute_fixed_schedule(dag, schedule, supply)
    assert sum(trace.demand) == 20
