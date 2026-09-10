"""Tests for multi-resource execution and the literature-backed variant costs."""

from __future__ import annotations

import pytest

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.mrc.execution import (
    critical_path,
    execute,
    resource_counts,
    resource_of,
)
from ftqc_delivery.mrc.library import (
    AND_CCZ,
    AND_T4,
    TOF_T7_D1,
    TOF_T7_D3,
    adder_variants,
    build_adder,
    build_mcx,
    build_rotation,
    rotation_variants,
)
from ftqc_delivery.mrc.resources import (
    CATALYZED_CCZ_TO_T,
    CCZ,
    T,
    build_machine,
)


def fan(op_type: str, width: int) -> CircuitDAG:
    dag = CircuitDAG("fan")
    dag.add_node("src", "Clifford")
    for index in range(width):
        dag.add_node(f"n{index}", op_type)
        dag.add_edge("src", f"n{index}")
    return dag


def test_operations_map_to_their_own_resource():
    assert resource_of("T") == T
    assert resource_of("CCZ") == CCZ
    assert resource_of("Clifford") is None


def test_each_bank_serves_only_its_own_operations():
    """A CCZ surplus does not help a T-starved circuit without a conversion."""

    dag = fan("T", 10)
    starved = build_machine(t_factories=1, ccz_factories=20)
    plenty = build_machine(t_factories=11, ccz_factories=1)
    assert execute(dag, starved).makespan > execute(dag, plenty).makespan


def test_a_conversion_lets_one_bank_cover_for_the_other():
    dag = fan("T", 20)
    without = build_machine(t_factories=1, ccz_factories=12)
    with_conversion = build_machine(
        t_factories=1, ccz_factories=12, conversions=(CATALYZED_CCZ_TO_T,)
    )
    plain = execute(dag, without).makespan
    converted = execute(dag, with_conversion, record_trace=True)
    assert converted.makespan < plain
    assert converted.conversions["1CCZ->2T"] > 0


def test_a_missing_bank_is_reported_rather_than_hanging():
    dag = fan("CCZ", 3)
    with pytest.raises(RuntimeError):
        execute(dag, build_machine(t_factories=4, ccz_factories=0))


def test_every_operation_runs_exactly_once():
    dag = CircuitDAG("mixed")
    dag.add_node("src", "Clifford")
    for index in range(5):
        dag.add_node(f"t{index}", "T")
        dag.add_edge("src", f"t{index}")
    for index in range(3):
        dag.add_node(f"c{index}", "CCZ")
        dag.add_edge("src", f"c{index}")
    trace = execute(dag, build_machine(t_factories=11, ccz_factories=6), record_trace=True)
    assert trace.consumed == {T: 5, CCZ: 3}


def test_more_capacity_never_slows_execution():
    dag = fan("T", 30)
    slow = execute(dag, build_machine(t_factories=2, ccz_factories=1)).makespan
    fast = execute(dag, build_machine(t_factories=22, ccz_factories=1)).makespan
    assert fast <= slow


def test_stalls_are_recorded_for_the_starved_resource():
    trace = execute(fan("T", 8), build_machine(t_factories=1, ccz_factories=1))
    assert trace.stalls[T] > 0


def test_a_full_buffer_loses_production():
    dag = CircuitDAG("chain")
    previous = None
    for index in range(3):
        dag.add_node(f"t{index}", "T")
        if previous:
            dag.add_edge(previous, f"t{index}")
        previous = f"t{index}"
    trace = execute(dag, build_machine(t_factories=44, ccz_factories=1, buffer_capacity=2))
    assert trace.overflow[T] > 0


def test_and_realisations_match_their_sources():
    """Gidney's AND is 4 T; a Toffoli from a CCZ factory is one CCZ state."""

    assert AND_T4.counts == {"T": 4}
    assert AND_CCZ.counts == {"CCZ": 1}
    assert TOF_T7_D3.counts == {"T": 7} and TOF_T7_D3.depth == 3
    assert TOF_T7_D1.counts == {"T": 7} and TOF_T7_D1.depth == 1


def test_ripple_adder_costs_one_and_per_bit():
    """A ripple-carry adder is n-1 ANDs, so 4(n-1) T or (n-1) CCZ states."""

    width = 16
    ccz = build_adder(width, width, AND_CCZ).to_dag("ccz")
    t4 = build_adder(width, width, AND_T4).to_dag("t4")
    assert resource_counts(ccz) == {CCZ: width - 1}
    assert resource_counts(t4) == {T: 4 * (width - 1)}


def test_carry_select_trades_states_for_depth():
    width = 32
    ripple = build_adder(width, width, AND_CCZ).to_dag("ripple")
    select = build_adder(width, 8, AND_CCZ).to_dag("select")
    assert resource_counts(select)[CCZ] > resource_counts(ripple)[CCZ]
    assert critical_path(select) < critical_path(ripple)


def test_rotation_costs_match_the_cited_syntheses():
    """Ross-Selinger is 4b T; phase-gradient is 2b Toffolis; log synthesis 4b+6."""

    bits = 10
    rs = build_rotation(bits, "rs", AND_T4).to_dag("rs")
    pg = build_rotation(bits, "phase_gradient", AND_CCZ).to_dag("pg")
    log = build_rotation(bits, "toffoli_log", AND_CCZ).to_dag("log")
    assert resource_counts(rs) == {T: 4 * bits}
    assert resource_counts(pg) == {CCZ: 2 * bits}
    assert resource_counts(log) == {CCZ: 4 * bits + 6}


def test_the_two_rotation_routes_cost_the_same_in_t_equivalents():
    """Ross-Selinger and phase-gradient are equal value, drawn from different banks.

    This is the cleanest instance of the decision under study: the choice is
    purely which factory to load, with no fungible cost difference at all.
    """

    bits = 10
    rs = resource_counts(build_rotation(bits, "rs", AND_T4).to_dag("rs"))
    pg = resource_counts(build_rotation(bits, "phase_gradient", AND_CCZ).to_dag("pg"))
    assert rs[T] == 2 * pg[CCZ]


def test_mcx_tree_is_shallower_than_a_chain_at_equal_cost():
    linear = build_mcx(16, "linear", AND_CCZ).to_dag("linear")
    tree = build_mcx(16, "tree", AND_CCZ).to_dag("tree")
    assert resource_counts(linear) == resource_counts(tree)
    assert critical_path(tree) < critical_path(linear)


def test_variant_sets_span_both_banks():
    for variants in (adder_variants("a", 16), rotation_variants("r", 8)):
        drawn = set()
        for variant in variants:
            drawn |= set(resource_counts(variant.fragment.to_dag(variant.name)))
        assert drawn == {T, CCZ}
